"""USB Video Class (UVC) camera for generic USB microscopes and webcams.

Uses OpenCV VideoCapture — works on macOS and Windows without proprietary SDKs.
"""

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

logger = logging.getLogger(__name__)


class UVCCamera(CameraInterface):
    """Generic UVC camera accessed via OpenCV."""

    def __init__(self, device_index: int = 0, camera_id: str = "uvc_microscope"):
        self._device_index = device_index
        self._camera_id = camera_id
        self._cap: Optional[cv2.VideoCapture] = None
        self._opened = False
        self._acquiring = False

        self._exposure_us = 10000.0
        self._gain_db = 0.0
        self._pixel_format = "BGR8"
        self._grayscale = True

        self._roi_x = 0
        self._roi_y = 0
        self._roi_w = 0
        self._roi_h = 0

        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._frame_event = threading.Event()
        self._frame_id = 0

        self._acq_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._trigger_mode = "freerun"

        self._width = 0
        self._height = 0
        self._actual_fps = 0.0
        self._fps_samples: list[float] = []
        self._last_frame_time = 0.0

    def open(self) -> None:
        if self._opened:
            return
        self._cap = cv2.VideoCapture(self._device_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open UVC device at index {self._device_index}. "
                "Check USB connection and ensure no other app is using the camera."
            )
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._roi_w = self._width
        self._roi_h = self._height
        self._opened = True
        logger.info(
            "UVC camera opened: index=%d, %dx%d",
            self._device_index, self._width, self._height,
        )

    def close(self) -> None:
        if self._acquiring:
            self.stop_acquisition()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
        logger.info("UVC camera closed: %s", self._camera_id)

    def start_acquisition(self) -> None:
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            return
        self._frame_id = 0
        self._stop_event.clear()
        self._frame_event.clear()
        self._acquiring = True
        self._acq_thread = threading.Thread(
            target=self._grab_loop, daemon=True, name=f"uvc-grab-{self._camera_id}",
        )
        self._acq_thread.start()
        logger.info("UVC acquisition started: %s", self._camera_id)

    def stop_acquisition(self) -> None:
        if not self._acquiring:
            return
        self._stop_event.set()
        if self._acq_thread is not None:
            self._acq_thread.join(timeout=5.0)
            self._acq_thread = None
        self._acquiring = False
        logger.info("UVC acquisition stopped: %s", self._camera_id)

    def _grab_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._cap is None or not self._cap.isOpened():
                self._stop_event.wait(0.1)
                continue

            ret, bgr_frame = self._cap.read()
            if not ret:
                self._stop_event.wait(0.01)
                continue

            now = time.monotonic()
            if self._last_frame_time > 0:
                dt = now - self._last_frame_time
                if dt > 0:
                    self._fps_samples.append(1.0 / dt)
                    if len(self._fps_samples) > 30:
                        self._fps_samples.pop(0)
                    self._actual_fps = sum(self._fps_samples) / len(self._fps_samples)
            self._last_frame_time = now

            if self._grayscale:
                frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
            else:
                frame = bgr_frame

            if self._roi_x > 0 or self._roi_y > 0 or self._roi_w < self._width or self._roi_h < self._height:
                x2 = min(self._roi_x + self._roi_w, frame.shape[1])
                y2 = min(self._roi_y + self._roi_h, frame.shape[0])
                frame = frame[self._roi_y:y2, self._roi_x:x2]

            meta = FrameMetadata(
                timestamp_ns=time.time_ns(),
                frame_id=self._frame_id,
                exposure_us=self._exposure_us,
                gain_db=self._gain_db,
                camera_id=self._camera_id,
                pixel_format="Mono8" if self._grayscale else "BGR8",
                width=frame.shape[1],
                height=frame.shape[0],
            )

            with self._lock:
                self._latest_frame = frame
                self._latest_meta = meta
                self._frame_id += 1
            self._frame_event.set()

    def get_frame(self, timeout_ms: int = 1000) -> tuple[np.ndarray, FrameMetadata]:
        if not self._acquiring:
            raise RuntimeError("Acquisition is not running")
        self._frame_event.clear()
        if not self._frame_event.wait(timeout=timeout_ms / 1000.0):
            raise TimeoutError(f"No frame within {timeout_ms} ms")
        with self._lock:
            if self._latest_frame is None or self._latest_meta is None:
                raise RuntimeError("Frame data unexpectedly None")
            return self._latest_frame, self._latest_meta

    def set_exposure(self, us: float) -> None:
        self._exposure_us = us
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, us / 1_000_000.0)

    def set_gain(self, db: float) -> None:
        self._gain_db = db
        if self._cap is not None:
            self._cap.set(cv2.CAP_PROP_GAIN, db)

    def get_exposure_range(self) -> tuple[float, float]:
        return (100.0, 1_000_000.0)

    def get_gain_range(self) -> tuple[float, float]:
        return (0.0, 48.0)

    def set_pixel_format(self, fmt: str) -> None:
        if fmt in ("Mono8", "Gray8"):
            self._grayscale = True
            self._pixel_format = "Mono8"
        elif fmt in ("BGR8", "Color"):
            self._grayscale = False
            self._pixel_format = "BGR8"
        else:
            raise ValueError(f"UVC supports Mono8 or BGR8, got '{fmt}'")

    def get_pixel_formats(self) -> list[str]:
        return ["Mono8", "BGR8"]

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        if x == 0 and y == 0 and width == 0 and height == 0:
            self._roi_x, self._roi_y = 0, 0
            self._roi_w, self._roi_h = self._width, self._height
        else:
            self._roi_x, self._roi_y = x, y
            self._roi_w, self._roi_h = width, height

    def get_sensor_size(self) -> tuple[int, int]:
        return (self._width, self._height)

    def get_camera_info(self) -> dict:
        backend = ""
        if self._cap is not None:
            backend = self._cap.getBackendName()
        return {
            "model": f"UVC Device #{self._device_index}",
            "serial": self._camera_id,
            "firmware": "N/A",
            "sdk_version": f"OpenCV {cv2.__version__}",
            "interface": "UVC/USB",
            "backend": backend,
            "resolution": f"{self._width}x{self._height}",
        }

    def set_trigger_mode(self, mode: str) -> None:
        self._trigger_mode = mode

    def get_frame_rate(self) -> float:
        return self._actual_fps

    def is_acquiring(self) -> bool:
        return self._acquiring


def enumerate_uvc_devices(max_index: int = 4) -> list[dict]:
    """Probe UVC device indices to find connected cameras.

    On macOS, camera access requires a privacy permission grant. If the app
    hasn't been authorized yet, OpenCV will fail silently. The first successful
    open triggers the macOS permission dialog.
    """
    import platform
    found = []

    backend = cv2.CAP_ANY
    if platform.system() == "Darwin":
        backend = cv2.CAP_AVFOUNDATION

    for idx in range(max_index):
        try:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    be_name = cap.getBackendName()
                    cap.release()
                    found.append({
                        "device_index": idx,
                        "width": w,
                        "height": h,
                        "backend": be_name,
                        "sdk": "uvc",
                        "serial": f"uvc_{idx}",
                        "model": f"UVC Camera #{idx} ({w}x{h})",
                    })
                    logger.info("UVC device found: index=%d, %dx%d (%s)", idx, w, h, be_name)
                else:
                    cap.release()
                    logger.debug("UVC index %d opened but no frame — likely permission denied", idx)
            else:
                cap.release()
        except Exception:
            logger.debug("UVC probe index %d failed", idx, exc_info=True)
    return found

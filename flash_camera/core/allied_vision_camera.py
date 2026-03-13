"""Allied Vision camera implementation using VmbPy (Vimba X SDK)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

try:
    import vmbpy
    _HAS_VMBPY = True
except ImportError:
    _HAS_VMBPY = False

logger = logging.getLogger(__name__)

_PIXEL_FORMAT_MAP: dict[str, str] = {
    "Mono8": "Mono8",
    "Mono12": "Mono12",
    "Mono16": "Mono16",
    "BayerRG8": "BayerRG8",
    "BayerRG12": "BayerRG12",
}


def _vimba_pixel_format(fmt: str):
    """Resolve a Vimba PixelFormat enum member by name."""
    vimba_name = _PIXEL_FORMAT_MAP.get(fmt, fmt)
    return getattr(vmbpy.PixelFormat, vimba_name)


class AlliedVisionCamera(CameraInterface):
    """Wraps VmbPy for Allied Vision cameras (Alvium, Goldeye, etc.)."""

    def __init__(self, device_id: Optional[str] = None):
        if not _HAS_VMBPY:
            raise RuntimeError(
                "vmbpy is not installed. Install the Vimba X SDK and "
                "'pip install vmbpy' to use Allied Vision cameras."
            )
        self._device_id = device_id
        self._vmb: Optional[vmbpy.VmbSystem] = None
        self._cam: Optional[vmbpy.Camera] = None
        self._acquiring = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._frame_event = threading.Event()
        self._frame_id = 0
        self._exposure_us = 1000.0
        self._gain_db = 0.0
        self._pixel_format = "Mono8"
        self._dropped_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        logger.info("Opening Allied Vision camera (device_id=%s)", self._device_id)
        self._vmb = vmbpy.VmbSystem.get_instance()
        self._vmb.__enter__()

        cameras = self._vmb.get_all_cameras()
        if not cameras:
            raise RuntimeError("No Allied Vision cameras detected")

        if self._device_id:
            try:
                self._cam = self._vmb.get_camera_by_id(self._device_id)
            except vmbpy.VmbCameraError:
                raise RuntimeError(
                    f"Camera '{self._device_id}' not found. "
                    f"Available: {[c.get_id() for c in cameras]}"
                )
        else:
            self._cam = cameras[0]
            logger.info("Auto-selected camera: %s", self._cam.get_id())

        self._cam.__enter__()
        self._apply_initial_settings()
        logger.info("Allied Vision camera opened: %s", self._cam.get_id())

    def _apply_initial_settings(self) -> None:
        try:
            self._cam.ExposureTime.set(self._exposure_us)
        except Exception:
            logger.debug("Could not set initial exposure")
        try:
            self._cam.Gain.set(self._gain_db)
        except Exception:
            logger.debug("Could not set initial gain")

    def close(self) -> None:
        logger.info("Closing Allied Vision camera")
        if self._acquiring:
            self.stop_acquisition()
        if self._cam is not None:
            try:
                self._cam.__exit__(None, None, None)
            except Exception:
                logger.warning("Error closing camera handle", exc_info=True)
            self._cam = None
        if self._vmb is not None:
            try:
                self._vmb.__exit__(None, None, None)
            except Exception:
                logger.warning("Error closing VmbSystem", exc_info=True)
            self._vmb = None

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def start_acquisition(self) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            logger.warning("Acquisition already running")
            return
        self._frame_id = 0
        self._dropped_count = 0
        self._frame_event.clear()
        self._cam.start_streaming(handler=self._frame_callback, buffer_count=10)
        self._acquiring = True
        logger.info("Acquisition started")

    def stop_acquisition(self) -> None:
        if not self._acquiring:
            return
        try:
            self._cam.stop_streaming()
        except Exception:
            logger.warning("Error stopping stream", exc_info=True)
        self._acquiring = False
        logger.info("Acquisition stopped (dropped=%d)", self._dropped_count)

    def _frame_callback(self, cam: vmbpy.Camera, stream: vmbpy.Stream, frame: vmbpy.Frame) -> None:
        status = frame.get_status()
        if status == vmbpy.FrameStatus.Complete:
            arr = frame.as_numpy_ndarray().copy()
            meta = FrameMetadata(
                timestamp_ns=frame.get_timestamp(),
                frame_id=self._frame_id,
                exposure_us=self._exposure_us,
                gain_db=self._gain_db,
                camera_id="allied_vision",
                pixel_format=self._pixel_format,
                width=arr.shape[1],
                height=arr.shape[0],
                dropped=False,
            )
            with self._lock:
                self._latest_frame = arr
                self._latest_meta = meta
                self._frame_id += 1
            self._frame_event.set()
        else:
            self._dropped_count += 1
            logger.debug("Dropped frame (status=%s)", status)

        cam.queue_frame(frame)

    def get_frame(self, timeout_ms: int = 1000) -> tuple[np.ndarray, FrameMetadata]:
        if not self._acquiring:
            raise RuntimeError("Acquisition is not running")
        self._frame_event.clear()
        if not self._frame_event.wait(timeout=timeout_ms / 1000.0):
            raise TimeoutError(f"No frame received within {timeout_ms} ms")
        with self._lock:
            frame = self._latest_frame
            meta = self._latest_meta
        if frame is None or meta is None:
            raise RuntimeError("Frame data unexpectedly None")
        return frame, meta

    # ------------------------------------------------------------------
    # Exposure / Gain
    # ------------------------------------------------------------------

    def set_exposure(self, us: float) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        self._cam.ExposureTime.set(us)
        self._exposure_us = us
        logger.debug("Exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        self._cam.Gain.set(db)
        self._gain_db = db
        logger.debug("Gain set to %.1f dB", db)

    def get_exposure_range(self) -> tuple[float, float]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        feat = self._cam.ExposureTime
        return (feat.get_range()[0], feat.get_range()[1])

    def get_gain_range(self) -> tuple[float, float]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        feat = self._cam.Gain
        return (feat.get_range()[0], feat.get_range()[1])

    # ------------------------------------------------------------------
    # Pixel format
    # ------------------------------------------------------------------

    def set_pixel_format(self, fmt: str) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing pixel format")
        vimba_fmt = _vimba_pixel_format(fmt)
        self._cam.set_pixel_format(vimba_fmt)
        self._pixel_format = fmt
        logger.debug("Pixel format set to %s", fmt)

    def get_pixel_formats(self) -> list[str]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        vimba_fmts = self._cam.get_pixel_formats()
        reverse_map = {v: k for k, v in _PIXEL_FORMAT_MAP.items()}
        results: list[str] = []
        for vf in vimba_fmts:
            name = vf.name if hasattr(vf, "name") else str(vf)
            results.append(reverse_map.get(name, name))
        return results

    # ------------------------------------------------------------------
    # ROI / Sensor
    # ------------------------------------------------------------------

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing ROI")
        if x == 0 and y == 0 and width == 0 and height == 0:
            sensor_w, sensor_h = self.get_sensor_size()
            self._cam.OffsetX.set(0)
            self._cam.OffsetY.set(0)
            self._cam.Width.set(sensor_w)
            self._cam.Height.set(sensor_h)
        else:
            self._cam.OffsetX.set(x)
            self._cam.OffsetY.set(y)
            self._cam.Width.set(width)
            self._cam.Height.set(height)
        logger.debug("ROI set to (%d, %d, %d, %d)", x, y, width, height)

    def get_sensor_size(self) -> tuple[int, int]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        return (self._cam.SensorWidth.get(), self._cam.SensorHeight.get())

    # ------------------------------------------------------------------
    # Info / Trigger / FPS
    # ------------------------------------------------------------------

    def get_camera_info(self) -> dict:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        return {
            "model": self._cam.get_model(),
            "serial": self._cam.get_serial(),
            "firmware": self._cam.get_firmware_version() if hasattr(self._cam, "get_firmware_version") else "N/A",
            "sdk_version": vmbpy.VmbSystem.get_instance().get_version(),
            "interface": "allied_vision / VmbPy",
        }

    def set_trigger_mode(self, mode: str) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if mode == "freerun":
            self._cam.TriggerMode.set("Off")
        elif mode == "software":
            self._cam.TriggerMode.set("On")
            self._cam.TriggerSource.set("Software")
        elif mode == "hardware_rising":
            self._cam.TriggerMode.set("On")
            self._cam.TriggerSource.set("Line1")
            self._cam.TriggerActivation.set("RisingEdge")
        elif mode == "hardware_falling":
            self._cam.TriggerMode.set("On")
            self._cam.TriggerSource.set("Line1")
            self._cam.TriggerActivation.set("FallingEdge")
        else:
            raise ValueError(f"Unknown trigger mode: {mode}")
        logger.debug("Trigger mode set to %s", mode)

    def get_frame_rate(self) -> float:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            return self._cam.AcquisitionFrameRate.get()
        except Exception:
            return 0.0

    def is_acquiring(self) -> bool:
        return self._acquiring

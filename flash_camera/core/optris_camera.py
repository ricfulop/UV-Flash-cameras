"""Optris PI 640 thermal camera via libirimager / pyoptris.

The Optris SDK provides 16-bit temperature frames where each pixel value
represents temperature in deci-Kelvin (value / 10.0 = Kelvin).
This maps naturally to our uint16 TIFF pipeline.

SDK availability: Windows-only (libirimager). On macOS/Linux, falls back to
a stub that raises ImportError with installation guidance.
"""

import logging
import platform
import threading
import time
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

logger = logging.getLogger(__name__)

_HAS_OPTRIS = False
_optris = None
try:
    if platform.system() == "Windows":
        import ctypes
        import ctypes.util
        _lib_path = ctypes.util.find_library("libirimager")
        if _lib_path:
            _HAS_OPTRIS = True
except Exception:
    pass

try:
    import pyoptris
    _optris = pyoptris
    _HAS_OPTRIS = True
except ImportError:
    pass


class OptrisCamera(CameraInterface):
    """Optris PI 640 infrared thermal camera.

    Wraps the Optris SDK (pyoptris or libirimager) for 16-bit thermal frame
    acquisition. Each pixel is temperature in deci-Kelvin.
    """

    SENSOR_WIDTH = 640
    SENSOR_HEIGHT = 480

    def __init__(self, serial: str = "", camera_id: str = "optris_thermal",
                 config_xml: str = ""):
        self._serial = serial
        self._camera_id = camera_id
        self._config_xml = config_xml

        self._opened = False
        self._acquiring = False
        self._pixel_format = "Thermal16"

        self._exposure_us = 1000.0
        self._gain_db = 0.0
        self._emissivity = 0.95
        self._ambient_temp_c = 23.0

        self._roi_x = 0
        self._roi_y = 0
        self._roi_w = self.SENSOR_WIDTH
        self._roi_h = self.SENSOR_HEIGHT

        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._frame_event = threading.Event()
        self._frame_id = 0

        self._acq_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._trigger_mode = "freerun"

        self._actual_fps = 0.0
        self._fps_samples: list[float] = []
        self._last_frame_time = 0.0
        self._target_fps = 32.0

        self._sdk_handle = None

    def open(self) -> None:
        if self._opened:
            return

        if _HAS_OPTRIS and _optris is not None:
            try:
                if self._config_xml:
                    _optris.usb_init(self._config_xml)
                else:
                    _optris.usb_init()
                w, h = _optris.get_thermal_image_size()
                self._roi_w = w
                self._roi_h = h
                self._sdk_handle = True
                logger.info("Optris SDK initialized: %dx%d", w, h)
            except Exception:
                logger.exception("Optris SDK init failed — using simulated thermal")
                self._sdk_handle = None
        else:
            logger.warning(
                "Optris SDK not available on %s. "
                "Install pyoptris (Windows) or use simulated mode.",
                platform.system(),
            )
            self._sdk_handle = None

        self._opened = True
        logger.info("Optris camera opened: %s", self._camera_id)

    def close(self) -> None:
        if self._acquiring:
            self.stop_acquisition()
        if self._sdk_handle and _optris is not None:
            try:
                _optris.terminate()
            except Exception:
                pass
        self._sdk_handle = None
        self._opened = False
        logger.info("Optris camera closed: %s", self._camera_id)

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
            target=self._grab_loop, daemon=True,
            name=f"optris-grab-{self._camera_id}",
        )
        self._acq_thread.start()
        logger.info("Optris acquisition started")

    def stop_acquisition(self) -> None:
        if not self._acquiring:
            return
        self._stop_event.set()
        if self._acq_thread is not None:
            self._acq_thread.join(timeout=5.0)
            self._acq_thread = None
        self._acquiring = False
        logger.info("Optris acquisition stopped")

    def _grab_loop(self) -> None:
        interval = 1.0 / self._target_fps
        while not self._stop_event.is_set():
            t0 = time.monotonic()
            frame = self._grab_one_frame()
            if frame is None:
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

            if self._roi_x > 0 or self._roi_y > 0:
                x2 = min(self._roi_x + self._roi_w, frame.shape[1])
                y2 = min(self._roi_y + self._roi_h, frame.shape[0])
                frame = frame[self._roi_y:y2, self._roi_x:x2]

            meta = FrameMetadata(
                timestamp_ns=time.time_ns(),
                frame_id=self._frame_id,
                exposure_us=self._exposure_us,
                gain_db=self._gain_db,
                camera_id=self._camera_id,
                pixel_format=self._pixel_format,
                width=frame.shape[1],
                height=frame.shape[0],
            )
            with self._lock:
                self._latest_frame = frame
                self._latest_meta = meta
                self._frame_id += 1
            self._frame_event.set()

            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

    def _grab_one_frame(self) -> Optional[np.ndarray]:
        if self._sdk_handle and _optris is not None:
            try:
                return _optris.get_thermal_image()
            except Exception:
                logger.debug("Optris grab failed", exc_info=True)
                return None

        return self._synthesize_thermal_frame()

    def _synthesize_thermal_frame(self) -> np.ndarray:
        """Generate a simulated thermal frame for testing without hardware."""
        w, h = self._roi_w, self._roi_h
        ambient_dk = int((self._ambient_temp_c + 273.15) * 10)
        base = np.full((h, w), ambient_dk, dtype=np.uint16)

        cy, cx = h // 2, w // 2
        yy, xx = np.ogrid[:h, :w]
        r2 = ((yy - cy) / (h * 0.3)) ** 2 + ((xx - cx) / (w * 0.3)) ** 2
        hotspot = np.clip(1.0 - r2, 0.0, 1.0)
        hot_delta = int(50 * 10)
        base = base + (hotspot * hot_delta).astype(np.uint16)

        noise = np.random.default_rng().integers(-5, 5, (h, w), dtype=np.int16)
        return np.clip(base.astype(np.int32) + noise, 0, 65535).astype(np.uint16)

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

    def set_gain(self, db: float) -> None:
        self._gain_db = db

    def get_exposure_range(self) -> tuple[float, float]:
        return (100.0, 100_000.0)

    def get_gain_range(self) -> tuple[float, float]:
        return (0.0, 24.0)

    def set_pixel_format(self, fmt: str) -> None:
        if fmt not in ("Thermal16", "Mono16", "Mono8"):
            raise ValueError(f"Optris supports Thermal16, Mono16, Mono8 — got '{fmt}'")
        self._pixel_format = fmt

    def get_pixel_formats(self) -> list[str]:
        return ["Thermal16", "Mono16", "Mono8"]

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        if x == 0 and y == 0 and width == 0 and height == 0:
            self._roi_x, self._roi_y = 0, 0
            self._roi_w = self.SENSOR_WIDTH
            self._roi_h = self.SENSOR_HEIGHT
        else:
            self._roi_x, self._roi_y = x, y
            self._roi_w, self._roi_h = width, height

    def get_sensor_size(self) -> tuple[int, int]:
        return (self.SENSOR_WIDTH, self.SENSOR_HEIGHT)

    def get_camera_info(self) -> dict:
        return {
            "model": "Optris PI 640",
            "serial": self._serial or self._camera_id,
            "firmware": "N/A",
            "sdk_version": "pyoptris" if _HAS_OPTRIS else "simulated",
            "interface": "USB",
            "sensor": "640x480 LWIR",
            "spectral_range": "7.5-13 µm",
            "temperature_range": "-20°C to 900°C",
            "emissivity": self._emissivity,
            "resolution": f"{self.SENSOR_WIDTH}x{self.SENSOR_HEIGHT}",
        }

    def set_trigger_mode(self, mode: str) -> None:
        self._trigger_mode = mode

    def get_frame_rate(self) -> float:
        return self._actual_fps

    def is_acquiring(self) -> bool:
        return self._acquiring

    def set_emissivity(self, eps: float) -> None:
        self._emissivity = max(0.01, min(1.0, eps))
        if self._sdk_handle and _optris is not None:
            try:
                _optris.set_radiation_parameters(self._emissivity, 1.0)
            except Exception:
                pass

    def set_ambient_temperature(self, temp_c: float) -> None:
        self._ambient_temp_c = temp_c

    @staticmethod
    def frame_to_celsius(frame: np.ndarray) -> np.ndarray:
        """Convert deci-Kelvin uint16 frame to Celsius float32."""
        return (frame.astype(np.float32) / 10.0) - 273.15


def enumerate_optris_devices() -> list[dict]:
    """Try to detect connected Optris cameras."""
    if not _HAS_OPTRIS:
        return []
    found = []
    try:
        if _optris is not None:
            _optris.usb_init()
            w, h = _optris.get_thermal_image_size()
            found.append({
                "serial": "optris_pi640",
                "model": "Optris PI 640",
                "width": w,
                "height": h,
                "sdk": "optris",
            })
            _optris.terminate()
    except Exception:
        logger.debug("Optris enumeration failed", exc_info=True)
    return found

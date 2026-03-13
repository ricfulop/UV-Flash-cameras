"""Simulated camera for testing without hardware.

Generates synthetic frames (gradient + noise) at configurable resolution.
Supports an optional ``simulate_flash`` mode that produces bright burst frames
to mimic UV flash events.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

logger = logging.getLogger(__name__)

_SUPPORTED_FORMATS = ["Mono8", "Mono12"]


class SimulatedCamera(CameraInterface):
    """Software-only camera that produces synthetic test frames."""

    def __init__(
        self,
        width: int = 3840,
        height: int = 2160,
        camera_id: str = "simulated",
        frame_rate: float = 30.0,
    ):
        self._sensor_width = width
        self._sensor_height = height
        self._camera_id = camera_id
        self._target_fps = frame_rate

        self._pixel_format = "Mono8"
        self._exposure_us = 1000.0
        self._gain_db = 0.0

        self._roi_x = 0
        self._roi_y = 0
        self._roi_w = width
        self._roi_h = height

        self._acquiring = False
        self._opened = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._frame_event = threading.Event()
        self._frame_id = 0
        self._dropped_count = 0

        self._gen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.simulate_flash = False
        self._flash_intensity = 0.95
        self._flash_duration_frames = 3
        self._flash_counter = 0

        self._trigger_mode = "freerun"

        self._rng = np.random.default_rng(42)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self._opened:
            logger.warning("Simulated camera already open")
            return
        self._opened = True
        logger.info(
            "Simulated camera opened (%dx%d, %s, %.0f fps)",
            self._sensor_width,
            self._sensor_height,
            self._pixel_format,
            self._target_fps,
        )

    def close(self) -> None:
        if self._acquiring:
            self.stop_acquisition()
        self._opened = False
        logger.info("Simulated camera closed")

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def start_acquisition(self) -> None:
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            logger.warning("Acquisition already running")
            return
        self._frame_id = 0
        self._dropped_count = 0
        self._stop_event.clear()
        self._frame_event.clear()

        self._gen_thread = threading.Thread(
            target=self._generation_loop, daemon=True, name="sim-cam-gen"
        )
        self._acquiring = True
        self._gen_thread.start()
        logger.info("Simulated acquisition started")

    def stop_acquisition(self) -> None:
        if not self._acquiring:
            return
        self._stop_event.set()
        if self._gen_thread is not None:
            self._gen_thread.join(timeout=3.0)
            self._gen_thread = None
        self._acquiring = False
        logger.info("Simulated acquisition stopped")

    def _generation_loop(self) -> None:
        interval = 1.0 / self._target_fps
        next_time = time.monotonic()

        while not self._stop_event.is_set():
            now = time.monotonic()
            sleep_dur = next_time - now
            if sleep_dur > 0:
                if self._stop_event.wait(timeout=sleep_dur):
                    break

            frame = self._synthesize_frame()
            meta = FrameMetadata(
                timestamp_ns=time.time_ns(),
                frame_id=self._frame_id,
                exposure_us=self._exposure_us,
                gain_db=self._gain_db,
                camera_id=self._camera_id,
                pixel_format=self._pixel_format,
                width=frame.shape[1],
                height=frame.shape[0],
                dropped=False,
            )
            with self._lock:
                self._latest_frame = frame
                self._latest_meta = meta
                self._frame_id += 1
            self._frame_event.set()

            next_time += interval
            if next_time < time.monotonic():
                next_time = time.monotonic() + interval

    def _synthesize_frame(self) -> np.ndarray:
        w, h = self._roi_w, self._roi_h
        is_12bit = self._pixel_format == "Mono12"
        dtype = np.uint16 if is_12bit else np.uint8
        max_val = 4095 if is_12bit else 255

        grad_h = np.linspace(0, 0.3, h, dtype=np.float32)[:, np.newaxis]
        grad_w = np.linspace(0, 0.3, w, dtype=np.float32)[np.newaxis, :]
        gradient = grad_h + grad_w

        gain_factor = 10.0 ** (self._gain_db / 20.0)
        exposure_factor = min(self._exposure_us / 10000.0, 1.0)
        base_level = np.clip(gradient * gain_factor * exposure_factor, 0.0, 1.0)

        noise_sigma = 0.02 * gain_factor
        noise = self._rng.normal(0, noise_sigma, (h, w)).astype(np.float32)

        frame_f = base_level + noise

        if self.simulate_flash and self._flash_counter > 0:
            flash_level = self._flash_intensity * gain_factor * exposure_factor
            cy, cx = h // 2, w // 2
            ry, rx = h // 4, w // 4
            yy, xx = np.ogrid[:h, :w]
            ellipse = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2
            flash_mask = np.clip(1.0 - ellipse, 0.0, 1.0).astype(np.float32)
            frame_f += flash_mask * flash_level
            self._flash_counter -= 1

        frame_f = np.clip(frame_f, 0.0, 1.0)
        return (frame_f * max_val).astype(dtype)

    def trigger_flash(self, duration_frames: Optional[int] = None) -> None:
        """Activate simulated flash burst for the next N frames."""
        self._flash_counter = duration_frames or self._flash_duration_frames
        logger.debug("Flash triggered for %d frames", self._flash_counter)

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
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if us < 10.0 or us > 10_000_000.0:
            raise ValueError(f"Exposure {us} µs out of simulated range [10, 10000000]")
        self._exposure_us = us
        logger.debug("Simulated exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if db < 0.0 or db > 48.0:
            raise ValueError(f"Gain {db} dB out of simulated range [0, 48]")
        self._gain_db = db
        logger.debug("Simulated gain set to %.1f dB", db)

    def get_exposure_range(self) -> tuple[float, float]:
        return (10.0, 10_000_000.0)

    def get_gain_range(self) -> tuple[float, float]:
        return (0.0, 48.0)

    # ------------------------------------------------------------------
    # Pixel format
    # ------------------------------------------------------------------

    def set_pixel_format(self, fmt: str) -> None:
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing pixel format")
        if fmt not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{fmt}'. Available: {_SUPPORTED_FORMATS}"
            )
        self._pixel_format = fmt
        logger.debug("Simulated pixel format set to %s", fmt)

    def get_pixel_formats(self) -> list[str]:
        return list(_SUPPORTED_FORMATS)

    # ------------------------------------------------------------------
    # ROI / Sensor
    # ------------------------------------------------------------------

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        if not self._opened:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing ROI")

        if x == 0 and y == 0 and width == 0 and height == 0:
            self._roi_x = 0
            self._roi_y = 0
            self._roi_w = self._sensor_width
            self._roi_h = self._sensor_height
        else:
            if x + width > self._sensor_width or y + height > self._sensor_height:
                raise ValueError(
                    f"ROI ({x},{y},{width},{height}) exceeds sensor "
                    f"({self._sensor_width}x{self._sensor_height})"
                )
            self._roi_x = x
            self._roi_y = y
            self._roi_w = width
            self._roi_h = height
        logger.debug(
            "Simulated ROI set to (%d, %d, %d, %d)",
            self._roi_x, self._roi_y, self._roi_w, self._roi_h,
        )

    def get_sensor_size(self) -> tuple[int, int]:
        return (self._sensor_width, self._sensor_height)

    # ------------------------------------------------------------------
    # Info / Trigger / FPS
    # ------------------------------------------------------------------

    def get_camera_info(self) -> dict:
        return {
            "model": "SimulatedCamera",
            "serial": self._camera_id,
            "firmware": "N/A",
            "sdk_version": "numpy " + np.__version__,
            "interface": "simulated",
            "resolution": f"{self._sensor_width}x{self._sensor_height}",
        }

    def set_trigger_mode(self, mode: str) -> None:
        if mode not in ("freerun", "software", "hardware_rising", "hardware_falling"):
            raise ValueError(f"Unknown trigger mode: {mode}")
        self._trigger_mode = mode
        if mode != "freerun":
            logger.info(
                "Simulated camera ignoring trigger mode '%s' — "
                "always runs in freerun internally",
                mode,
            )
        logger.debug("Trigger mode set to %s", mode)

    def get_frame_rate(self) -> float:
        return self._target_fps

    def is_acquiring(self) -> bool:
        return self._acquiring

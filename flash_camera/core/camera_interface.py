from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import time


@dataclass
class FrameMetadata:
    timestamp_ns: int
    frame_id: int
    exposure_us: float
    gain_db: float
    camera_id: str
    pixel_format: str
    width: int = 0
    height: int = 0
    dropped: bool = False


class CameraInterface(ABC):

    @abstractmethod
    def open(self) -> None:
        """Connect to camera, allocate buffers."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""

    @abstractmethod
    def start_acquisition(self) -> None:
        """Begin continuous frame streaming."""

    @abstractmethod
    def stop_acquisition(self) -> None:
        """Stop streaming."""

    @abstractmethod
    def get_frame(self, timeout_ms: int = 1000) -> tuple[np.ndarray, FrameMetadata]:
        """Return (image_array, metadata). Blocks up to timeout."""

    @abstractmethod
    def set_exposure(self, us: float) -> None:
        """Set exposure time in microseconds."""

    @abstractmethod
    def set_gain(self, db: float) -> None:
        """Set analog gain in dB."""

    @abstractmethod
    def get_exposure_range(self) -> tuple[float, float]:
        """Return (min_us, max_us)."""

    @abstractmethod
    def get_gain_range(self) -> tuple[float, float]:
        """Return (min_db, max_db)."""

    @abstractmethod
    def set_pixel_format(self, fmt: str) -> None:
        """Set pixel format (e.g., Mono8, Mono12, Mono16, BayerRG8)."""

    @abstractmethod
    def get_pixel_formats(self) -> list[str]:
        """Return available pixel formats."""

    @abstractmethod
    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        """Set region of interest. Set all to 0 for full frame."""

    @abstractmethod
    def get_sensor_size(self) -> tuple[int, int]:
        """Return (width, height) in pixels."""

    @abstractmethod
    def get_camera_info(self) -> dict:
        """Return dict with model, serial, firmware, SDK version."""

    @abstractmethod
    def set_trigger_mode(self, mode: str) -> None:
        """Set trigger: 'freerun', 'software', 'hardware_rising', 'hardware_falling'."""

    @abstractmethod
    def get_frame_rate(self) -> float:
        """Return current/actual frame rate in fps."""

    @abstractmethod
    def is_acquiring(self) -> bool:
        """Return True if camera is currently streaming."""

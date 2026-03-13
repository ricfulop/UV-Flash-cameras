"""Thread-safe ring buffer for pre-trigger frame capture."""

import logging
import threading
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import FrameMetadata

logger = logging.getLogger(__name__)


class FrameRingBuffer:
    def __init__(
        self,
        duration_s: float = 2.0,
        max_fps: float = 30.0,
        width: int = 3840,
        height: int = 2160,
        dtype: type = np.uint16,
    ) -> None:
        self._lock = threading.Lock()
        self._duration_s = duration_s
        self._max_fps = max_fps
        self._width = width
        self._height = height
        self._dtype = dtype
        self._capacity = max(1, int(duration_s * max_fps))
        self._pool: list[np.ndarray] = [
            np.empty((height, width), dtype=dtype) for _ in range(self._capacity)
        ]
        self._metadata: list[Optional[FrameMetadata]] = [None] * self._capacity
        self._head = 0
        self._count = 0

    def push(self, frame: np.ndarray, metadata: FrameMetadata) -> None:
        with self._lock:
            dst = self._pool[self._head]
            if frame.shape != dst.shape or frame.dtype != dst.dtype:
                raise ValueError(
                    f"Frame shape {frame.shape} or dtype {frame.dtype} "
                    f"does not match buffer ({dst.shape}, {dst.dtype})"
                )
            np.copyto(dst, frame)
            self._metadata[self._head] = metadata
            self._head = (self._head + 1) % self._capacity
            if self._count < self._capacity:
                self._count += 1

    def flush(self) -> list[tuple[np.ndarray, FrameMetadata]]:
        with self._lock:
            if self._count == 0:
                return []
            start = (self._head - self._count) % self._capacity
            result: list[tuple[np.ndarray, FrameMetadata]] = []
            for i in range(self._count):
                idx = (start + i) % self._capacity
                meta = self._metadata[idx]
                if meta is not None:
                    result.append((self._pool[idx].copy(), meta))
            self._head = 0
            self._count = 0
            for i in range(len(self._metadata)):
                self._metadata[i] = None
            return result

    def get_depth(self) -> int:
        with self._lock:
            return self._count

    def get_duration_s(self) -> float:
        with self._lock:
            if self._count < 2:
                return 0.0
            start = (self._head - self._count) % self._capacity
            first_meta = self._metadata[start]
            last_idx = (self._head - 1) % self._capacity
            last_meta = self._metadata[last_idx]
            if first_meta is None or last_meta is None:
                return 0.0
            return (last_meta.timestamp_ns - first_meta.timestamp_ns) / 1e9

    def clear(self) -> None:
        with self._lock:
            self._head = 0
            self._count = 0
            for i in range(len(self._metadata)):
                self._metadata[i] = None

    def resize(
        self,
        duration_s: Optional[float] = None,
        max_fps: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        dtype: Optional[type] = None,
    ) -> None:
        with self._lock:
            self._duration_s = duration_s if duration_s is not None else self._duration_s
            self._max_fps = max_fps if max_fps is not None else self._max_fps
            self._width = width if width is not None else self._width
            self._height = height if height is not None else self._height
            self._dtype = dtype if dtype is not None else self._dtype
            self._capacity = max(1, int(self._duration_s * self._max_fps))
            self._pool = [
                np.empty((self._height, self._width), dtype=self._dtype)
                for _ in range(self._capacity)
            ]
            self._metadata = [None] * self._capacity
            self._head = 0
            self._count = 0

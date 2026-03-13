"""Recording quality preset definitions."""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QualityPreset:
    name: str
    bit_depth: str
    max_fps: float
    tiff_compression: str
    description: str


PRESETS: dict[str, QualityPreset] = {
    "maximum": QualityPreset(
        name="maximum",
        bit_depth="Mono12",
        max_fps=30.0,
        tiff_compression="none",
        description="Full dynamic range, no compression",
    ),
    "high": QualityPreset(
        name="high",
        bit_depth="Mono12",
        max_fps=30.0,
        tiff_compression="lzw",
        description="Full dynamic range, LZW compressed",
    ),
    "balanced": QualityPreset(
        name="balanced",
        bit_depth="Mono12",
        max_fps=15.0,
        tiff_compression="lzw",
        description="Half rate, LZW compressed",
    ),
    "fast": QualityPreset(
        name="fast",
        bit_depth="Mono8",
        max_fps=30.0,
        tiff_compression="none",
        description="8-bit, no compression, high speed",
    ),
    "compact": QualityPreset(
        name="compact",
        bit_depth="Mono8",
        max_fps=15.0,
        tiff_compression="lzw",
        description="8-bit, half rate, LZW compressed",
    ),
    "custom": QualityPreset(
        name="custom",
        bit_depth="Mono12",
        max_fps=30.0,
        tiff_compression="lzw",
        description="User-defined settings",
    ),
}


def get_preset(name: str) -> QualityPreset:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset: {name}")
    return PRESETS[name]


def dtype_for_bit_depth(bit_depth: str) -> np.dtype:
    if bit_depth == "Mono8":
        return np.dtype(np.uint8)
    if bit_depth == "Mono12" or bit_depth == "Mono16":
        return np.dtype(np.uint16)
    raise ValueError(f"Unsupported bit depth: {bit_depth}")


def _bytes_per_pixel(bit_depth: str) -> int:
    if bit_depth == "Mono8":
        return 1
    if bit_depth in ("Mono12", "Mono16"):
        return 2
    return 2


def estimate_storage_rate(
    preset: QualityPreset,
    num_cameras: int = 2,
    width: int = 3840,
    height: int = 2160,
) -> float:
    bpp = _bytes_per_pixel(preset.bit_depth)
    raw_bytes_per_sec = width * height * bpp * preset.max_fps * num_cameras
    if preset.tiff_compression == "lzw":
        raw_bytes_per_sec *= 0.6
    return raw_bytes_per_sec / (1024 * 1024)


def estimate_storage_per_minute(
    preset: QualityPreset,
    num_cameras: int = 2,
    width: int = 3840,
    height: int = 2160,
) -> float:
    return estimate_storage_rate(preset, num_cameras, width, height) * 60 / 1024


def pixel_format_for_preset(preset: QualityPreset) -> str:
    return preset.bit_depth

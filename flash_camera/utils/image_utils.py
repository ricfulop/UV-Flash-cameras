"""
Image processing utilities for display and analysis.
"""

import logging
from typing import Literal

import cv2
import numpy as np

logger = logging.getLogger(__name__)

COLORMAP_NAMES: dict[str, int] = {
    "inferno": cv2.COLORMAP_INFERNO,
    "viridis": cv2.COLORMAP_VIRIDIS,
    "plasma": cv2.COLORMAP_PLASMA,
}


def mono12_to_8bit(frame: np.ndarray) -> np.ndarray:
    if frame.dtype != np.uint16:
        raise ValueError("Expected uint16 for 12-bit input")
    shifted = frame >> 4
    scaled = np.clip(shifted, 0, 255).astype(np.uint8)
    return scaled


def apply_colormap(
    frame_8bit: np.ndarray,
    colormap: Literal["gray", "inferno", "viridis", "plasma"] = "gray",
) -> np.ndarray:
    if colormap == "gray":
        return cv2.cvtColor(frame_8bit, cv2.COLOR_GRAY2BGR)
    return cv2.applyColorMap(frame_8bit, COLORMAP_NAMES[colormap])


def compute_histogram(frame: np.ndarray, bins: int = 256) -> tuple[np.ndarray, np.ndarray]:
    flat = frame.ravel()
    if np.issubdtype(flat.dtype, np.integer):
        max_val = int(np.iinfo(flat.dtype).max)
    else:
        max_val = max(float(flat.max()), 1.0)
    max_val = max(max_val, 1)
    counts, bin_edges = np.histogram(flat, bins=bins, range=(0, max_val))
    return counts.astype(np.float64), bin_edges


def apply_flat_field(frame: np.ndarray, reference: np.ndarray) -> np.ndarray:
    ref_safe = np.where(reference > 0, reference.astype(np.float64), np.nan)
    mean_ref = np.nanmean(ref_safe)
    corrected = np.where(ref_safe > 0, frame.astype(np.float64) * mean_ref / ref_safe, 0)
    return np.clip(corrected, 0, np.iinfo(frame.dtype).max).astype(frame.dtype)


def calculate_scale_bar(
    fov_mm: tuple[float, float], image_width: int
) -> tuple[int, str]:
    fov_x, fov_y = fov_mm
    fov_horizontal = max(fov_x, fov_y, 0.001)
    mm_per_px = fov_horizontal / image_width
    nice_sizes = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
    target_mm = fov_horizontal * 0.15
    best_mm = min(nice_sizes, key=lambda x: abs(x - target_mm))
    pixel_length = max(1, int(round(best_mm / mm_per_px)))
    if best_mm >= 1:
        label = f"{int(best_mm)} mm"
    else:
        label = f"{best_mm} mm"
    return pixel_length, label


def draw_crosshair(
    image: np.ndarray,
    color: tuple[int, int, int] = (255, 255, 255),
    thickness: int = 1,
) -> np.ndarray:
    h, w = image.shape[:2]
    cx, cy = w // 2, h // 2
    size = min(w, h) // 8
    result = image.copy()
    if len(result.shape) == 2:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    cv2.line(result, (cx - size, cy), (cx + size, cy), color, thickness)
    cv2.line(result, (cx, cy - size), (cx, cy + size), color, thickness)
    return result


def draw_scale_bar(
    image: np.ndarray,
    pixel_length: int,
    label: str,
    position: Literal["bottom_left", "bottom_right", "top_left", "top_right"] = "bottom_left",
) -> np.ndarray:
    h, w = image.shape[:2]
    margin = 10
    bar_h = 4
    if position == "bottom_left":
        x1, y1 = margin, h - margin - bar_h
    elif position == "bottom_right":
        x1, y1 = w - margin - pixel_length, h - margin - bar_h
    elif position == "top_left":
        x1, y1 = margin, margin
    else:
        x1, y1 = w - margin - pixel_length, margin
    x2, y2 = x1 + pixel_length, y1 + bar_h
    result = image.copy()
    if len(result.shape) == 2:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(result, (x1, y1), (x2, y2), (255, 255, 255), -1)
    cv2.rectangle(result, (x1, y1), (x2, y2), (0, 0, 0), 1)
    text_y = y1 - 4 if "top" in position else y2 + 14
    cv2.putText(result, label, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    return result


def compute_mean_intensity(frame: np.ndarray) -> float:
    return float(np.mean(frame))

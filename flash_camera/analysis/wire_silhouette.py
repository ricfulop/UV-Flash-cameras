"""Stereo silhouette metrology for the 3D wire dilatometer."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - OpenCV is a declared dependency.
    cv2 = None


@dataclass(frozen=True)
class WireViewMeasurement:
    """Subpixel edge-derived centerline from one camera view."""

    x_px: list[float]
    edge_low_px: list[float]
    edge_high_px: list[float]
    center_px: list[float]
    width_px: list[float]
    pixel_size_um: float
    dark_on_bright: bool
    threshold: float
    coverage_fraction: float
    contrast: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WireTubeModel:
    """Time-varying tube model for one synchronized stereo frame pair."""

    x_mm: list[float]
    y_mm: list[float]
    z_mm: list[float]
    diameter_mm: list[float]
    arc_length_mm: float
    end_to_end_length_mm: float
    max_lateral_bow_mm: float
    max_vertical_bow_mm: float
    mean_diameter_mm: float
    quality: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _as_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame.astype(np.float32)
    if frame.ndim == 3:
        return np.mean(frame, axis=2, dtype=np.float32)
    raise ValueError("frame must be 2D grayscale or 3D color")


def _otsu_threshold(gray: np.ndarray) -> float:
    if cv2 is not None:
        scaled = gray
        if gray.dtype != np.uint8:
            max_val = float(np.max(gray)) or 1.0
            scaled = np.clip(gray / max_val * 255.0, 0, 255).astype(np.uint8)
        threshold, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return float(threshold) / 255.0 * float(np.max(gray) or 1.0)
    return float(np.percentile(gray, 35))


def segment_silhouette(
    frame: np.ndarray,
    *,
    threshold: float | None = None,
    dark_on_bright: bool = True,
) -> tuple[np.ndarray, float]:
    """Segment the wire silhouette from a bright backlit frame."""

    gray = _as_gray(frame)
    threshold_value = _otsu_threshold(gray) if threshold is None else float(threshold)
    mask = gray <= threshold_value if dark_on_bright else gray >= threshold_value
    return mask, threshold_value


def extract_wire_view(
    frame: np.ndarray,
    *,
    pixel_size_um: float,
    threshold: float | None = None,
    dark_on_bright: bool = True,
    min_width_px: int = 3,
) -> WireViewMeasurement:
    """Extract 2D wire edges, centerline, and width from a silhouette image.

    The wire is assumed to run primarily along the image x-axis. The method is
    deliberately simple and deterministic for v1: each image column yields the
    first and last silhouette pixels, then downstream calibration handles scale.
    """

    gray = _as_gray(frame)
    mask, threshold_value = segment_silhouette(
        gray,
        threshold=threshold,
        dark_on_bright=dark_on_bright,
    )

    x_vals: list[float] = []
    edge_low: list[float] = []
    edge_high: list[float] = []
    center: list[float] = []
    width: list[float] = []

    for x_idx in range(mask.shape[1]):
        ys = np.flatnonzero(mask[:, x_idx])
        if ys.size < min_width_px:
            continue
        lo = float(ys[0])
        hi = float(ys[-1])
        x_vals.append(float(x_idx))
        edge_low.append(lo)
        edge_high.append(hi)
        center.append(0.5 * (lo + hi))
        width.append(hi - lo + 1.0)

    if not x_vals:
        raise ValueError("No wire silhouette found")

    foreground = gray[mask]
    background = gray[~mask]
    contrast = 0.0
    if foreground.size and background.size:
        contrast = abs(float(np.mean(background)) - float(np.mean(foreground)))

    return WireViewMeasurement(
        x_px=x_vals,
        edge_low_px=edge_low,
        edge_high_px=edge_high,
        center_px=center,
        width_px=width,
        pixel_size_um=pixel_size_um,
        dark_on_bright=dark_on_bright,
        threshold=threshold_value,
        coverage_fraction=len(x_vals) / mask.shape[1],
        contrast=contrast,
    )


def _interp_to_common_x(view: WireViewMeasurement, common_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(view.x_px, dtype=np.float64)
    center = np.asarray(view.center_px, dtype=np.float64)
    width = np.asarray(view.width_px, dtype=np.float64)
    return np.interp(common_x, x, center), np.interp(common_x, x, width)


def reconstruct_tube_model(
    front_view: WireViewMeasurement,
    top_view: WireViewMeasurement,
    *,
    n_points: int = 256,
) -> WireTubeModel:
    """Fuse front and top orthogonal silhouette views into a 3D tube model."""

    front_x = np.asarray(front_view.x_px, dtype=np.float64)
    top_x = np.asarray(top_view.x_px, dtype=np.float64)
    x_min = max(float(front_x.min()), float(top_x.min()))
    x_max = min(float(front_x.max()), float(top_x.max()))
    if x_max <= x_min:
        raise ValueError("Front and top views do not overlap in axial x")

    common_x = np.linspace(x_min, x_max, max(2, n_points))
    front_center, front_width = _interp_to_common_x(front_view, common_x)
    top_center, top_width = _interp_to_common_x(top_view, common_x)

    px_mm_front = front_view.pixel_size_um / 1000.0
    px_mm_top = top_view.pixel_size_um / 1000.0
    px_mm_x = 0.5 * (px_mm_front + px_mm_top)

    x_mm = (common_x - common_x[0]) * px_mm_x
    y_mm = (top_center - np.median(top_center)) * px_mm_top
    z_mm = (front_center - np.median(front_center)) * px_mm_front
    diameter_mm = 0.5 * (front_width * px_mm_front + top_width * px_mm_top)

    diffs = np.diff(np.column_stack([x_mm, y_mm, z_mm]), axis=0)
    arc_length = float(np.sum(np.linalg.norm(diffs, axis=1)))
    end_to_end = float(
        np.linalg.norm([x_mm[-1] - x_mm[0], y_mm[-1] - y_mm[0], z_mm[-1] - z_mm[0]])
    )

    quality = {
        "front_coverage_fraction": front_view.coverage_fraction,
        "top_coverage_fraction": top_view.coverage_fraction,
        "front_contrast": front_view.contrast,
        "top_contrast": top_view.contrast,
        "shared_x_points": int(common_x.size),
    }

    return WireTubeModel(
        x_mm=x_mm.tolist(),
        y_mm=y_mm.tolist(),
        z_mm=z_mm.tolist(),
        diameter_mm=diameter_mm.tolist(),
        arc_length_mm=arc_length,
        end_to_end_length_mm=end_to_end,
        max_lateral_bow_mm=float(np.max(np.abs(y_mm))),
        max_vertical_bow_mm=float(np.max(np.abs(z_mm))),
        mean_diameter_mm=float(np.mean(diameter_mm)),
        quality=quality,
    )


def analyze_stereo_pair(
    front_frame: np.ndarray,
    top_frame: np.ndarray,
    *,
    pixel_size_um: float = 17.1,
    threshold: float | None = None,
) -> WireTubeModel:
    """Run the v1 wire pipeline for a synchronized front/top frame pair."""

    front = extract_wire_view(front_frame, pixel_size_um=pixel_size_um, threshold=threshold)
    top = extract_wire_view(top_frame, pixel_size_um=pixel_size_um, threshold=threshold)
    return reconstruct_tube_model(front, top)


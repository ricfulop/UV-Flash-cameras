"""Export utility for flash camera sessions.

Reads a session's JSON metadata and can:
- Produce a side-by-side montage of both cameras
- Extract single frames by index or timestamp
- Compute frame-to-frame intensity statistics
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _load_session(session_dir: str) -> dict:
    from flash_camera.utils.metadata import load_metadata
    meta_path = Path(session_dir) / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No metadata.json in {session_dir}")
    return load_metadata(str(meta_path))


def _list_tiffs(cam_dir: Path) -> list[Path]:
    return sorted(cam_dir.glob("frame_*.tiff")) + sorted(cam_dir.glob("frame_*.tif"))


def extract_frame(session_dir: str, camera_id: str, frame_index: int, output: str | None = None):
    """Extract a single frame by index."""
    import tifffile

    cam_dir = Path(session_dir) / camera_id
    tiffs = _list_tiffs(cam_dir)
    if frame_index >= len(tiffs):
        raise IndexError(f"Frame {frame_index} out of range (0-{len(tiffs) - 1})")

    frame = tifffile.imread(str(tiffs[frame_index]))
    if output:
        tifffile.imwrite(output, frame)
        logger.info("Extracted frame %d to %s", frame_index, output)
    return frame


def compute_intensity_stats(session_dir: str, camera_id: str) -> dict:
    """Compute frame-to-frame intensity statistics for flash event detection."""
    import tifffile

    cam_dir = Path(session_dir) / camera_id
    tiffs = _list_tiffs(cam_dir)
    if not tiffs:
        return {"error": "No TIFF files found"}

    means = []
    maxes = []
    mins = []
    for path in tiffs:
        frame = tifffile.imread(str(path))
        means.append(float(np.mean(frame)))
        maxes.append(float(np.max(frame)))
        mins.append(float(np.min(frame)))

    means_arr = np.array(means)
    return {
        "camera_id": camera_id,
        "num_frames": len(tiffs),
        "mean_intensity": means,
        "max_intensity": maxes,
        "min_intensity": mins,
        "overall_mean": float(np.mean(means_arr)),
        "overall_std": float(np.std(means_arr)),
        "peak_frame_index": int(np.argmax(means_arr)),
        "peak_mean_intensity": float(np.max(means_arr)),
    }


def create_montage(session_dir: str, frame_index: int = 0, output: str | None = None):
    """Create side-by-side montage of both cameras at the given frame index."""
    import tifffile
    import cv2

    session = Path(session_dir)
    metadata = _load_session(session_dir)
    cameras = list(metadata.get("cameras", {}).keys())

    frames = []
    for cam_id in cameras:
        cam_dir = session / cam_id
        tiffs = _list_tiffs(cam_dir)
        if frame_index < len(tiffs):
            frame = tifffile.imread(str(tiffs[frame_index]))
            if frame.dtype == np.uint16:
                frame = (frame / 16).astype(np.uint8)
            frames.append(frame)

    if len(frames) < 2:
        logger.warning("Need at least 2 cameras for montage, got %d", len(frames))
        if frames:
            montage = frames[0]
        else:
            return None
    else:
        target_h = min(f.shape[0] for f in frames)
        resized = []
        for f in frames:
            scale = target_h / f.shape[0]
            new_w = int(f.shape[1] * scale)
            r = cv2.resize(f, (new_w, target_h))
            resized.append(r)
        montage = np.hstack(resized)

    out_path = output or str(session / f"montage_frame_{frame_index:06d}.tiff")
    tifffile.imwrite(out_path, montage)
    logger.info("Montage saved to %s", out_path)
    return montage


def compute_wire_metrics(
    session_dir: str,
    *,
    front_camera: str | None = None,
    top_camera: str | None = None,
    frame_index: int = 0,
    output: str | None = None,
) -> dict:
    """Compute 3D wire tube metrics for one synchronized frame pair."""

    import json
    import tifffile
    from flash_camera.analysis.wire_silhouette import analyze_stereo_pair

    session = Path(session_dir)
    metadata = _load_session(session_dir)
    dil = metadata.get("dilatometer", {})
    pair = dil.get("camera_pair", {})
    optics = dil.get("optics", {})
    front_id = front_camera or pair.get("front")
    top_id = top_camera or pair.get("top")
    if not front_id or not top_id:
        raise ValueError("front_camera and top_camera are required")

    front_files = _list_tiffs(session / front_id)
    top_files = _list_tiffs(session / top_id)
    if frame_index >= len(front_files) or frame_index >= len(top_files):
        raise IndexError("frame_index is outside available stereo frame range")

    pixel_size_um = float(optics.get("pixel_size_um", 17.1))
    front_frame = tifffile.imread(str(front_files[frame_index]))
    top_frame = tifffile.imread(str(top_files[frame_index]))
    model = analyze_stereo_pair(
        front_frame,
        top_frame,
        pixel_size_um=pixel_size_um,
    )
    result = {
        "session_dir": str(session),
        "front_camera": front_id,
        "top_camera": top_id,
        "frame_index": frame_index,
        "pixel_size_um": pixel_size_um,
        "wire_model": model.to_dict(),
    }
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
    return result


def compute_balluffi_result(
    *,
    macro_strain: float | None = None,
    initial_length_mm: float | None = None,
    current_length_mm: float | None = None,
    lattice_strain: float | None = None,
    cte_strain: float | None = None,
    output: str | None = None,
) -> dict:
    """Compute Balluffi-style apparent defect swelling."""

    import json
    from flash_camera.analysis.balluffi import calculate_balluffi, calculate_from_lengths

    if macro_strain is None:
        if initial_length_mm is None or current_length_mm is None:
            raise ValueError("Provide macro_strain or both initial_length_mm and current_length_mm")
        result = calculate_from_lengths(
            initial_length_mm,
            current_length_mm,
            epsilon_lattice=lattice_strain,
            epsilon_cte=cte_strain,
        ).to_dict()
    else:
        result = calculate_balluffi(
            macro_strain,
            epsilon_lattice=lattice_strain,
            epsilon_cte=cte_strain,
        ).to_dict()
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
    return result


def get_dic_backend_status(output: str | None = None) -> dict:
    """Return availability of primary and optional DIC/metrology backends."""

    import json
    from flash_camera.analysis.dic_backends import backend_status, primary_backend_name

    result = {
        "primary_backend": primary_backend_name(),
        "backends": backend_status(),
    }
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description="Flash Camera Session Export Utility")
    sub = parser.add_subparsers(dest="command")

    ext = sub.add_parser("extract", help="Extract a single frame")
    ext.add_argument("session_dir")
    ext.add_argument("camera_id")
    ext.add_argument("frame_index", type=int)
    ext.add_argument("--output", "-o", default=None)

    stats = sub.add_parser("stats", help="Compute intensity statistics")
    stats.add_argument("session_dir")
    stats.add_argument("camera_id")

    mont = sub.add_parser("montage", help="Create side-by-side montage")
    mont.add_argument("session_dir")
    mont.add_argument("--frame", "-f", type=int, default=0)
    mont.add_argument("--output", "-o", default=None)

    wire = sub.add_parser("wire-metrics", help="Compute 3D wire metrics from a front/top frame pair")
    wire.add_argument("session_dir")
    wire.add_argument("--front-camera", default=None)
    wire.add_argument("--top-camera", default=None)
    wire.add_argument("--frame", "-f", type=int, default=0)
    wire.add_argument("--output", "-o", default=None)

    balluffi = sub.add_parser("balluffi", help="Compute Balluffi-style apparent defect swelling")
    balluffi.add_argument("--macro-strain", type=float, default=None)
    balluffi.add_argument("--initial-length-mm", type=float, default=None)
    balluffi.add_argument("--current-length-mm", type=float, default=None)
    balluffi.add_argument("--lattice-strain", type=float, default=None)
    balluffi.add_argument("--cte-strain", type=float, default=None)
    balluffi.add_argument("--output", "-o", default=None)

    backends = sub.add_parser("dic-backends", help="Show DIC/metrology backend availability")
    backends.add_argument("--output", "-o", default=None)

    info = sub.add_parser("info", help="Show session metadata")
    info.add_argument("session_dir")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "extract":
        extract_frame(args.session_dir, args.camera_id, args.frame_index, args.output)

    elif args.command == "stats":
        import json
        result = compute_intensity_stats(args.session_dir, args.camera_id)
        result_display = {k: v for k, v in result.items() if k not in ("mean_intensity", "max_intensity", "min_intensity")}
        print(json.dumps(result_display, indent=2))

    elif args.command == "montage":
        create_montage(args.session_dir, args.frame, args.output)

    elif args.command == "wire-metrics":
        import json
        result = compute_wire_metrics(
            args.session_dir,
            front_camera=args.front_camera,
            top_camera=args.top_camera,
            frame_index=args.frame,
            output=args.output,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "balluffi":
        import json
        result = compute_balluffi_result(
            macro_strain=args.macro_strain,
            initial_length_mm=args.initial_length_mm,
            current_length_mm=args.current_length_mm,
            lattice_strain=args.lattice_strain,
            cte_strain=args.cte_strain,
            output=args.output,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "dic-backends":
        import json
        result = get_dic_backend_status(output=args.output)
        print(json.dumps(result, indent=2))

    elif args.command == "info":
        import json
        meta = _load_session(args.session_dir)
        print(json.dumps(meta, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

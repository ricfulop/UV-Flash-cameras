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

    elif args.command == "info":
        import json
        meta = _load_session(args.session_dir)
        print(json.dumps(meta, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

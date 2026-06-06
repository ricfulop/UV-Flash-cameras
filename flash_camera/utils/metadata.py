"""
JSON sidecar read/write for session metadata.
"""

import json
import logging
from pathlib import Path
from flash_camera.utils.timestamp import get_utc_timestamp

logger = logging.getLogger(__name__)


def create_session_metadata(
    session_id: str,
    operator: str,
    quality_preset: str | dict,
    cameras_info: dict,
    reactor_conditions: dict,
    oes_sync: dict | None,
    file_paths: dict,
    *,
    dilatometer: dict | None = None,
    start_time_utc: str | None = None,
    duration_s: float = 0.0,
) -> dict:
    if isinstance(quality_preset, dict):
        recording_quality = quality_preset
    else:
        recording_quality = {
            "preset": quality_preset,
            "bit_depth": "",
            "max_fps": None,
            "tiff_compression": "",
            "actual_avg_write_mb_s": None,
        }
    return {
        "session_id": session_id,
        "operator": operator,
        "recording_quality": recording_quality,
        "start_time_utc": start_time_utc or get_utc_timestamp(),
        "duration_s": duration_s,
        "cameras": cameras_info,
        "reactor_conditions": reactor_conditions,
        "oes_sync": oes_sync or {},
        "dilatometer": dilatometer or {},
        "file_paths": file_paths,
    }


def save_metadata(metadata: dict, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)


def load_metadata(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def update_metadata(path: str, updates: dict) -> None:
    metadata = load_metadata(path)
    _deep_merge(metadata, updates)
    save_metadata(metadata, path)


def _deep_merge(base: dict, updates: dict) -> None:
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def create_default_reactor_conditions() -> dict:
    return {
        "gas": "",
        "pressure_torr": None,
        "voltage_v": None,
        "current_a": None,
        "notes": "",
    }

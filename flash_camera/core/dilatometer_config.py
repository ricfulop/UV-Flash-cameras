"""Configuration helpers for the 3D wire dilatometer mode."""

from __future__ import annotations

from copy import deepcopy


DEFAULT_DILATOMETER_CONFIG = {
    "enabled": True,
    "mode": "wire_silhouette_3d",
    "camera_pair": {
        "front": "basler",
        "top": "allied_vision",
    },
    "coordinate_system": {
        "x": "between fixed clips",
        "y": "lateral/front-back",
        "z": "vertical",
    },
    "optics": {
        "lens": "0.16X SilverTL-class telecentric",
        "reference_lens": "Edmund Optics #56-675",
        "working_distance_mm": 177.0,
        "working_distance_tolerance_mm": 3.0,
        "depth_of_field_mm_at_f10": 19.74,
        "pixel_size_um": 17.1,
        "field_of_view_mm": [48.6, 48.6],
        "high_accuracy_bow_envelope_mm": 10.0,
        "quality_flag_bow_envelope_mm": 20.0,
    },
    "illumination": {
        "wavelength_nm": 470,
        "geometry": "strobed backlight silhouette",
        "filter": "470 nm bandpass OD4+",
        "secondary_modes": ["405 nm near-UV", "365 nm UV with quartz optics"],
    },
    "calibration": {
        "calibration_file": "",
        "target": "dot-grid or ChArUco at specimen plane",
        "requires_3d_or_depth_sweep": True,
        "scale_validation": "gauge pin or known-diameter wire",
    },
    "quality_control": {
        "min_edge_contrast": None,
        "max_saturation_fraction": None,
        "store_edge_confidence": True,
        "store_fiducial_reprojection_error": True,
    },
    "balluffi": {
        "default_material": "Pt",
        "default_cte_strain_to_1000k": 0.009,
        "dilute_warning_fraction": 0.02,
        "label_without_lattice_data": "apparent defect swelling",
    },
}


def get_dilatometer_config(config: dict) -> dict:
    """Return merged dilatometer config with v1 defaults filled in."""

    merged = deepcopy(DEFAULT_DILATOMETER_CONFIG)
    user_cfg = config.get("dilatometer") or {}
    _deep_merge(merged, user_cfg)
    return merged


def build_dilatometer_metadata(
    config: dict,
    *,
    connected_camera_ids: list[str],
    cameras_info: dict | None = None,
) -> dict:
    """Build a JSON-serializable session metadata block for the stereo rig."""

    dil_cfg = get_dilatometer_config(config)
    pair = dil_cfg.get("camera_pair", {})
    missing = [
        cam_id
        for cam_id in (pair.get("front"), pair.get("top"))
        if cam_id and cam_id not in connected_camera_ids
    ]
    metadata = deepcopy(dil_cfg)
    metadata["connected_camera_ids"] = list(connected_camera_ids)
    metadata["missing_pair_cameras"] = missing
    metadata["ready_for_stereo_reconstruction"] = not missing and bool(pair.get("front") and pair.get("top"))
    if cameras_info is not None:
        metadata["camera_inventory"] = {
            cam_id: cameras_info.get(cam_id, {})
            for cam_id in (pair.get("front"), pair.get("top"))
            if cam_id
        }
    return metadata


def _deep_merge(base: dict, updates: dict) -> None:
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


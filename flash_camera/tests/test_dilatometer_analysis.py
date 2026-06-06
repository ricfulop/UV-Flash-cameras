import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import tifffile

from flash_camera.analysis.balluffi import (
    DEFECT_LOOKUP_TABLE,
    calculate_balluffi,
    calculate_from_lengths,
    constant_cte_strain,
)
from flash_camera.analysis.dic_backends import backend_status, primary_backend_name
from flash_camera.analysis.wire_silhouette import (
    analyze_stereo_pair,
    extract_wire_view,
    reconstruct_tube_model,
)
from flash_camera.core.dilatometer_config import build_dilatometer_metadata
from flash_camera.utils.export_session import (
    compute_balluffi_result,
    compute_wire_metrics,
    get_dic_backend_status,
)


def _synthetic_wire_frame(
    *,
    width: int = 160,
    height: int = 80,
    center: float = 40.0,
    amplitude: float = 0.0,
    thickness: int = 6,
) -> np.ndarray:
    frame = np.full((height, width), 255, dtype=np.uint8)
    xs = np.arange(width)
    centers = center + amplitude * np.sin(2 * np.pi * xs / width)
    half = thickness // 2
    for x, cy in enumerate(centers):
        lo = max(0, int(round(cy)) - half)
        hi = min(height, int(round(cy)) + half + 1)
        frame[lo:hi, x] = 0
    return frame


def test_balluffi_uses_cte_when_lattice_missing():
    result = calculate_balluffi(0.042333333333333334, epsilon_cte=0.009)

    assert result.epsilon_excess == pytest.approx(0.03333333333333333)
    assert result.c_app_mol_percent == pytest.approx(10.0)
    assert result.warning is not None
    assert DEFECT_LOOKUP_TABLE[1]["c_app_mol_percent"] == 10.0


def test_constant_cte_strain():
    assert constant_cte_strain(9e-6, 300.0, 1000.0) == pytest.approx(0.0063)


def test_balluffi_from_lengths_uses_3d_arc_length_strain():
    result = calculate_from_lengths(48.0, 50.016, epsilon_cte=0.009)

    assert result.epsilon_macro == pytest.approx(0.042)
    assert result.c_app_mol_percent == pytest.approx(9.9)


def test_wire_silhouette_extracts_centerline_and_width():
    frame = _synthetic_wire_frame(thickness=7)
    view = extract_wire_view(frame, pixel_size_um=17.1)

    assert view.coverage_fraction == 1.0
    assert np.mean(view.width_px) == 7.0
    assert abs(np.mean(view.center_px) - 40.0) < 0.1
    assert view.contrast > 100


def test_reconstruct_tube_model_reports_bowing_and_length():
    front = extract_wire_view(
        _synthetic_wire_frame(center=40.0, amplitude=4.0),
        pixel_size_um=17.1,
    )
    top = extract_wire_view(
        _synthetic_wire_frame(center=35.0, amplitude=3.0),
        pixel_size_um=17.1,
    )
    model = reconstruct_tube_model(front, top, n_points=64)

    assert model.arc_length_mm > model.end_to_end_length_mm
    assert model.max_lateral_bow_mm > 0.04
    assert model.max_vertical_bow_mm > 0.05
    assert model.mean_diameter_mm > 0.09
    assert model.quality["shared_x_points"] == 64


def test_analyze_stereo_pair_returns_model():
    model = analyze_stereo_pair(
        _synthetic_wire_frame(center=40.0),
        _synthetic_wire_frame(center=42.0),
        pixel_size_um=17.1,
    )

    assert model.arc_length_mm > 0
    assert len(model.x_mm) == 256


def test_dilatometer_metadata_flags_missing_pair_camera():
    metadata = build_dilatometer_metadata(
        {
            "dilatometer": {
                "camera_pair": {
                    "front": "basler",
                    "top": "allied_vision",
                }
            }
        },
        connected_camera_ids=["basler"],
        cameras_info={"basler": {"model": "a2A2840-48umUV"}},
    )

    assert metadata["ready_for_stereo_reconstruction"] is False
    assert metadata["missing_pair_cameras"] == ["allied_vision"]
    assert metadata["camera_inventory"]["basler"]["model"] == "a2A2840-48umUV"


def test_export_wire_metrics_and_balluffi_result():
    with tempfile.TemporaryDirectory() as tmpdir:
        session = Path(tmpdir)
        (session / "basler").mkdir()
        (session / "allied_vision").mkdir()
        tifffile.imwrite(session / "basler" / "frame_00000000.tiff", _synthetic_wire_frame())
        tifffile.imwrite(session / "allied_vision" / "frame_00000000.tiff", _synthetic_wire_frame())
        metadata = {
            "cameras": {"basler": {}, "allied_vision": {}},
            "dilatometer": {
                "camera_pair": {"front": "basler", "top": "allied_vision"},
                "optics": {"pixel_size_um": 17.1},
            },
        }
        (session / "metadata.json").write_text(json.dumps(metadata))

        wire = compute_wire_metrics(str(session))
        assert wire["wire_model"]["arc_length_mm"] > 0

        balluffi = compute_balluffi_result(macro_strain=0.02, cte_strain=0.009)
        assert balluffi["c_app_mol_percent"] == pytest.approx(3.3)

        balluffi_from_lengths = compute_balluffi_result(
            initial_length_mm=48.0,
            current_length_mm=50.016,
            cte_strain=0.009,
        )
        assert balluffi_from_lengths["c_app_mol_percent"] == pytest.approx(9.9)


def test_dic_backend_registry_prioritizes_opencv_wire_pipeline():
    status = backend_status()
    exported = get_dic_backend_status()

    assert primary_backend_name() == "opencv_wire_silhouette"
    assert exported["primary_backend"] == "opencv_wire_silhouette"
    assert "opencv_wire_silhouette" in status
    assert "dice" in status
    assert status["opencv_wire_silhouette"]["role"] == "primary_wire_pipeline"


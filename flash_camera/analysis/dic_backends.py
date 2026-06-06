"""Backend registry for wire metrology and optional DIC validation tools."""

from __future__ import annotations

import importlib.util
import shutil


BACKENDS = {
    "opencv_wire_silhouette": {
        "role": "primary_wire_pipeline",
        "kind": "python",
        "module": "cv2",
        "notes": "Primary v1 path for 250 um wire silhouettes and 3D tube reconstruction.",
    },
    "dice": {
        "role": "foil_or_coupon_validation",
        "kind": "command",
        "command": "dice",
        "notes": "Open-source DICe backend for textured foils or calibration coupons.",
    },
    "opencorr": {
        "role": "method_development_validation",
        "kind": "command",
        "command": "opencorr",
        "notes": "Optional OpenCorr C++ stereo-DIC validation backend.",
    },
    "multidic": {
        "role": "matlab_reference",
        "kind": "manual",
        "notes": "MATLAB MultiDIC reference workflow for saved images, not production wire tracking.",
    },
}


def backend_status() -> dict:
    """Return availability/status for configured analysis backends."""

    status = {}
    for name, cfg in BACKENDS.items():
        kind = cfg["kind"]
        available = False
        detail = ""
        if kind == "python":
            module = cfg["module"]
            available = importlib.util.find_spec(module) is not None
            detail = f"python module {module}"
        elif kind == "command":
            command = cfg["command"]
            path = shutil.which(command)
            available = path is not None
            detail = path or f"command {command} not found"
        elif kind == "manual":
            detail = "manual external workflow"

        status[name] = {
            "available": available,
            "role": cfg["role"],
            "detail": detail,
            "notes": cfg["notes"],
        }
    return status


def primary_backend_name() -> str:
    return "opencv_wire_silhouette"


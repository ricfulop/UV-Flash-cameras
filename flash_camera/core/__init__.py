"""Core camera abstractions and implementations."""

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

__all__ = [
    "CameraInterface",
    "FrameMetadata",
    "AlliedVisionCamera",
    "BaslerCamera",
    "SimulatedCamera",
]


def AlliedVisionCamera(*args, **kwargs):
    """Lazy import to avoid hard dependency on vmbpy."""
    from flash_camera.core.allied_vision_camera import AlliedVisionCamera as _Cls
    return _Cls(*args, **kwargs)


def BaslerCamera(*args, **kwargs):
    """Lazy import to avoid hard dependency on pypylon."""
    from flash_camera.core.basler_camera import BaslerCamera as _Cls
    return _Cls(*args, **kwargs)


def SimulatedCamera(*args, **kwargs):
    """Lazy import — always available (numpy only)."""
    from flash_camera.core.simulated_camera import SimulatedCamera as _Cls
    return _Cls(*args, **kwargs)

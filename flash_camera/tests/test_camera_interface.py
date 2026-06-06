"""Tests for camera implementations."""

import numpy as np
import pytest

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata
from flash_camera.core.camera_manager import CameraManager, CameraSlot
from flash_camera.core.simulated_camera import SimulatedCamera


def test_vimbax_connect_uses_device_id(monkeypatch):
    calls = {}

    class FakeAlliedVisionCamera:
        def __init__(self, device_id=None):
            calls["device_id"] = device_id

        def open(self):
            calls["opened"] = True

        def get_pixel_formats(self):
            return []

        def set_exposure(self, us):
            calls["exposure_us"] = us

        def set_gain(self, db):
            calls["gain_db"] = db

    import flash_camera.core.allied_vision_camera as allied_module

    monkeypatch.setattr(allied_module, "AlliedVisionCamera", FakeAlliedVisionCamera)

    manager = CameraManager(config={})
    slot = CameraSlot(
        camera_id="allied_vision",
        role="overview",
        sdk="vimbax",
        config={},
    )

    manager._connect_hardware(
        slot,
        hw_dev={"sdk": "vimbax", "serial": "DEV_123"},
        cfg={"default_exposure_us": 500, "default_gain_db": 0.0},
    )

    assert calls["device_id"] == "DEV_123"
    assert calls["opened"] is True
    assert slot.connected is True
    assert slot.camera is not None


class TestSimulatedCamera:

    def test_open_close(self):
        cam = SimulatedCamera(width=640, height=480, camera_id="test")
        cam.open()
        assert cam.is_acquiring() is False
        cam.close()

    def test_acquisition(self):
        cam = SimulatedCamera(width=640, height=480, camera_id="test", frame_rate=60.0)
        cam.open()
        cam.start_acquisition()
        assert cam.is_acquiring() is True

        frame, meta = cam.get_frame(timeout_ms=2000)
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (480, 640)
        assert frame.dtype == np.uint8
        assert isinstance(meta, FrameMetadata)
        assert meta.camera_id == "test"
        assert meta.pixel_format == "Mono8"

        cam.stop_acquisition()
        assert cam.is_acquiring() is False
        cam.close()

    def test_mono12(self):
        cam = SimulatedCamera(width=640, height=480, camera_id="test")
        cam.open()
        cam.set_pixel_format("Mono12")
        cam.start_acquisition()
        frame, meta = cam.get_frame(timeout_ms=2000)
        assert frame.dtype == np.uint16
        assert meta.pixel_format == "Mono12"
        cam.stop_acquisition()
        cam.close()

    def test_exposure_gain(self):
        cam = SimulatedCamera(width=640, height=480)
        cam.open()
        cam.set_exposure(5000.0)
        cam.set_gain(12.0)
        assert cam.get_exposure_range() == (10.0, 10_000_000.0)
        assert cam.get_gain_range() == (0.0, 48.0)
        cam.close()

    def test_sensor_info(self):
        cam = SimulatedCamera(width=1920, height=1080)
        cam.open()
        assert cam.get_sensor_size() == (1920, 1080)
        info = cam.get_camera_info()
        assert "model" in info
        assert "serial" in info
        cam.close()

    def test_roi(self):
        cam = SimulatedCamera(width=1920, height=1080)
        cam.open()
        cam.set_roi(100, 100, 800, 600)
        cam.start_acquisition()
        frame, _ = cam.get_frame(timeout_ms=2000)
        assert frame.shape == (600, 800)
        cam.stop_acquisition()
        cam.set_roi(0, 0, 0, 0)
        cam.start_acquisition()
        frame, _ = cam.get_frame(timeout_ms=2000)
        assert frame.shape == (1080, 1920)
        cam.stop_acquisition()
        cam.close()

    def test_flash_simulation(self):
        cam = SimulatedCamera(width=320, height=240, frame_rate=60.0)
        cam.open()
        cam.start_acquisition()

        frame_dark, _ = cam.get_frame(timeout_ms=2000)
        dark_mean = float(np.mean(frame_dark))

        cam.simulate_flash = True
        cam.trigger_flash(duration_frames=5)
        frame_flash, _ = cam.get_frame(timeout_ms=2000)
        flash_mean = float(np.mean(frame_flash))

        assert flash_mean > dark_mean

        cam.stop_acquisition()
        cam.close()

    def test_pixel_formats(self):
        cam = SimulatedCamera()
        cam.open()
        fmts = cam.get_pixel_formats()
        assert "Mono8" in fmts
        assert "Mono12" in fmts
        cam.close()

    def test_trigger_modes(self):
        cam = SimulatedCamera()
        cam.open()
        cam.set_trigger_mode("freerun")
        cam.set_trigger_mode("software")
        with pytest.raises(ValueError):
            cam.set_trigger_mode("invalid_mode")
        cam.close()

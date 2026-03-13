"""Camera discovery, lifecycle management, and frame distribution."""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata
from flash_camera.core.frame_buffer import FrameRingBuffer
from flash_camera.core.quality_presets import dtype_for_bit_depth

logger = logging.getLogger(__name__)

_CAMERA_ROLES = {
    "allied_vision": "overview",
    "basler": "closeup_filtered",
}


class CameraSlot:
    """Manages one camera's lifecycle: discovery, acquisition thread, ring buffer."""

    def __init__(self, camera_id: str, role: str, config: dict):
        self.camera_id = camera_id
        self.role = role
        self.config = config
        self.camera: Optional[CameraInterface] = None
        self.connected = False
        self.acquiring = False

        self.ring_buffer: Optional[FrameRingBuffer] = None
        self._acq_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._frame_callback = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        self._dropped_count = 0

    def set_frame_callback(self, callback):
        """Set callback(camera_id, frame, metadata) invoked on each new frame."""
        self._frame_callback = callback

    def init_ring_buffer(self, duration_s: float, max_fps: float, bit_depth: str):
        dtype = dtype_for_bit_depth(bit_depth).type
        w, h = 3840, 2160
        if self.camera is not None:
            try:
                w, h = self.camera.get_sensor_size()
            except Exception:
                pass
        self.ring_buffer = FrameRingBuffer(
            duration_s=duration_s, max_fps=max_fps,
            width=w, height=h, dtype=dtype,
        )

    def start_acquisition(self):
        if self.camera is None or self.acquiring:
            return
        self._stop_event.clear()
        self._frame_count = 0
        self._dropped_count = 0
        self.camera.start_acquisition()
        self.acquiring = True
        self._acq_thread = threading.Thread(
            target=self._acquisition_loop, daemon=True,
            name=f"acq-{self.camera_id}",
        )
        self._acq_thread.start()
        logger.info("Acquisition started for %s", self.camera_id)

    def stop_acquisition(self):
        if not self.acquiring:
            return
        self._stop_event.set()
        if self._acq_thread is not None:
            self._acq_thread.join(timeout=5.0)
            self._acq_thread = None
        if self.camera is not None:
            try:
                self.camera.stop_acquisition()
            except Exception:
                logger.exception("Error stopping acquisition for %s", self.camera_id)
        self.acquiring = False
        logger.info("Acquisition stopped for %s", self.camera_id)

    def _acquisition_loop(self):
        while not self._stop_event.is_set():
            try:
                frame, meta = self.camera.get_frame(timeout_ms=500)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("Frame grab error on %s", self.camera_id)
                self._dropped_count += 1
                continue

            self._frame_count += 1
            with self._lock:
                self._latest_frame = frame
                self._latest_meta = meta

            if self.ring_buffer is not None:
                try:
                    self.ring_buffer.push(frame, meta)
                except ValueError:
                    pass

            if self._frame_callback is not None:
                try:
                    self._frame_callback(self.camera_id, frame, meta)
                except Exception:
                    logger.exception("Frame callback error for %s", self.camera_id)

    def get_latest_frame(self) -> Optional[tuple[np.ndarray, FrameMetadata]]:
        with self._lock:
            if self._latest_frame is not None and self._latest_meta is not None:
                return self._latest_frame, self._latest_meta
        return None

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def dropped_count(self) -> int:
        return self._dropped_count


class CameraManager:
    """Manages discovery and lifecycle of all cameras."""

    def __init__(self, config: dict):
        self._config = config
        self._slots: dict[str, CameraSlot] = {}
        self._use_simulated = False

    @property
    def slots(self) -> dict[str, CameraSlot]:
        return self._slots

    def discover_cameras(self, use_simulated: bool = False) -> list[str]:
        """Discover cameras. If use_simulated=True, create simulated cameras."""
        self._use_simulated = use_simulated
        found = []
        cam_configs = self._config.get("cameras", {})

        if use_simulated:
            for cam_id, cam_cfg in cam_configs.items():
                role = cam_cfg.get("role", _CAMERA_ROLES.get(cam_id, "unknown"))
                slot = CameraSlot(cam_id, role, cam_cfg)
                self._slots[cam_id] = slot
                self._connect_simulated(slot, cam_cfg)
                found.append(cam_id)
            return found

        for cam_id, cam_cfg in cam_configs.items():
            role = cam_cfg.get("role", _CAMERA_ROLES.get(cam_id, "unknown"))
            slot = CameraSlot(cam_id, role, cam_cfg)
            self._slots[cam_id] = slot

            serial = cam_cfg.get("serial", "")
            if serial and "SERIAL_HERE" not in serial:
                try:
                    self._connect_hardware(slot, cam_id, serial, cam_cfg)
                    found.append(cam_id)
                except Exception:
                    logger.exception("Failed to connect %s (serial=%s)", cam_id, serial)
            else:
                logger.info("No valid serial for %s — using simulated", cam_id)
                self._connect_simulated(slot, cam_cfg)
                found.append(cam_id)

        return found

    def _connect_hardware(self, slot: CameraSlot, cam_id: str, serial: str, cfg: dict):
        if cam_id == "allied_vision":
            from flash_camera.core.allied_vision_camera import AlliedVisionCamera
            cam = AlliedVisionCamera(serial=serial)
        elif cam_id == "basler":
            from flash_camera.core.basler_camera import BaslerCamera
            cam = BaslerCamera(serial=serial)
        else:
            raise ValueError(f"Unknown camera type: {cam_id}")

        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        logger.info("Hardware camera %s connected (serial=%s)", cam_id, serial)

    def _connect_simulated(self, slot: CameraSlot, cfg: dict):
        from flash_camera.core.simulated_camera import SimulatedCamera
        cam = SimulatedCamera(camera_id=slot.camera_id, frame_rate=30.0)
        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        logger.info("Simulated camera %s connected", slot.camera_id)

    def _apply_defaults(self, cam: CameraInterface, cfg: dict):
        try:
            fmt = cfg.get("default_pixel_format", "Mono8")
            if fmt in cam.get_pixel_formats():
                cam.set_pixel_format(fmt)
        except Exception:
            logger.warning("Could not set default pixel format")

        try:
            exp = cfg.get("default_exposure_us", 500)
            cam.set_exposure(float(exp))
        except Exception:
            logger.warning("Could not set default exposure")

        try:
            gain = cfg.get("default_gain_db", 0.0)
            cam.set_gain(float(gain))
        except Exception:
            logger.warning("Could not set default gain")

    def init_ring_buffers(self, duration_s: float = 2.0, max_fps: float = 30.0, bit_depth: str = "Mono12"):
        for slot in self._slots.values():
            if slot.connected:
                slot.init_ring_buffer(duration_s, max_fps, bit_depth)

    def start_all(self):
        for slot in self._slots.values():
            if slot.connected:
                slot.start_acquisition()

    def stop_all(self):
        for slot in self._slots.values():
            slot.stop_acquisition()

    def close_all(self):
        self.stop_all()
        for slot in self._slots.values():
            if slot.camera is not None:
                try:
                    slot.camera.close()
                except Exception:
                    logger.exception("Error closing %s", slot.camera_id)
                slot.camera = None
                slot.connected = False

    def get_connected_ids(self) -> list[str]:
        return [cid for cid, s in self._slots.items() if s.connected]

    def rescan(self) -> list[str]:
        self.close_all()
        self._slots.clear()
        return self.discover_cameras(use_simulated=self._use_simulated)

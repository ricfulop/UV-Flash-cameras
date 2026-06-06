"""Camera discovery, lifecycle management, and frame distribution.

Supports auto-detection across all available SDKs:
- Allied Vision (VmbPy / Vimba X)
- Basler (pypylon / Pylon)
- UVC (OpenCV — USB microscopes, webcams)
- Optris (pyoptris / libirimager — thermal cameras)
- Simulated (numpy — always available for testing)
"""

import logging
import threading
import time
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata
from flash_camera.core.frame_buffer import FrameRingBuffer
from flash_camera.core.quality_presets import dtype_for_bit_depth

logger = logging.getLogger(__name__)

SDK_ROLE_HINTS = {
    "vimbax": "overview",
    "pylon": "closeup_filtered",
    "uvc": "microscope",
    "optris": "thermal",
    "simulated": "simulated",
}


class CameraSlot:
    """Manages one camera's lifecycle: acquisition thread, ring buffer."""

    def __init__(self, camera_id: str, role: str, sdk: str, config: dict):
        self.camera_id = camera_id
        self.role = role
        self.sdk = sdk
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
        self._frame_callback = callback

    def init_ring_buffer(self, duration_s: float, max_fps: float, bit_depth: str):
        dtype = dtype_for_bit_depth(bit_depth).type
        w, h = 640, 480
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


def _enumerate_vimbax() -> list[dict]:
    """Enumerate Allied Vision cameras via Vimba X SDK."""
    try:
        import vmbpy
        with vmbpy.VmbSystem.get_instance() as vmb:
            cams = vmb.get_all_cameras()
            results = []
            for cam in cams:
                results.append({
                    "serial": cam.get_id(),
                    "model": cam.get_model(),
                    "sdk": "vimbax",
                    "interface": "USB3",
                })
            return results
    except ImportError:
        logger.debug("VmbPy not installed — skipping Allied Vision enumeration")
    except Exception:
        logger.debug("Vimba X enumeration failed", exc_info=True)
    return []


def _enumerate_pylon() -> list[dict]:
    """Enumerate Basler cameras via Pylon SDK."""
    try:
        from pypylon import pylon
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        results = []
        for dev in devices:
            results.append({
                "serial": dev.GetSerialNumber(),
                "model": dev.GetModelName(),
                "sdk": "pylon",
                "interface": dev.GetDeviceClass(),
            })
        return results
    except ImportError:
        logger.debug("pypylon not installed — skipping Basler enumeration")
    except Exception:
        logger.debug("Pylon enumeration failed", exc_info=True)
    return []


def _enumerate_uvc() -> list[dict]:
    """Enumerate UVC (USB webcam/microscope) devices via OpenCV."""
    try:
        from flash_camera.core.uvc_camera import enumerate_uvc_devices
        return enumerate_uvc_devices()
    except Exception:
        logger.debug("UVC enumeration failed", exc_info=True)
    return []


def _enumerate_optris() -> list[dict]:
    """Enumerate Optris thermal cameras."""
    try:
        from flash_camera.core.optris_camera import enumerate_optris_devices
        return enumerate_optris_devices()
    except Exception:
        logger.debug("Optris enumeration failed", exc_info=True)
    return []


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
        """Auto-discover cameras across all SDKs, or use simulated if requested."""
        self._use_simulated = use_simulated
        found = []
        cam_configs = self._config.get("cameras", {})

        if use_simulated:
            for cam_id, cam_cfg in cam_configs.items():
                sdk = cam_cfg.get("sdk", "simulated")
                role = cam_cfg.get("role", SDK_ROLE_HINTS.get(sdk, "unknown"))
                slot = CameraSlot(cam_id, role, sdk, cam_cfg)
                self._slots[cam_id] = slot
                self._connect_simulated(slot, cam_cfg)
                found.append(cam_id)
            return found

        # --- Hardware mode: only show cameras that are physically present ---
        logger.info("Scanning for connected cameras...")
        hw_devices = self._scan_all_hardware()

        if not hw_devices:
            logger.warning("No cameras detected on any transport layer")
            return found

        matched_hw_indices = set()

        # Pass 1: match config entries to discovered hardware by serial or device_index
        for cam_id, cam_cfg in cam_configs.items():
            sdk = cam_cfg.get("sdk", "")
            serial = cam_cfg.get("serial", "")
            role = cam_cfg.get("role", SDK_ROLE_HINTS.get(sdk, "unknown"))

            if serial and "SERIAL_HERE" not in serial:
                for i, hw_dev in enumerate(hw_devices):
                    if i in matched_hw_indices:
                        continue
                    if hw_dev.get("serial") == serial:
                        slot = CameraSlot(cam_id, role, hw_dev["sdk"], cam_cfg)
                        self._slots[cam_id] = slot
                        try:
                            self._connect_hardware(slot, hw_dev, cam_cfg)
                            matched_hw_indices.add(i)
                            found.append(cam_id)
                            logger.info("Config camera '%s' matched to %s (serial=%s)",
                                        cam_id, hw_dev.get("model", "?"), serial)
                        except Exception:
                            logger.exception("Failed to connect config camera %s", cam_id)
                        break

            elif sdk == "uvc":
                dev_idx = cam_cfg.get("device_index", -1)
                if dev_idx >= 0:
                    for i, hw_dev in enumerate(hw_devices):
                        if i in matched_hw_indices:
                            continue
                        if hw_dev.get("sdk") == "uvc" and hw_dev.get("device_index") == dev_idx:
                            slot = CameraSlot(cam_id, role, "uvc", cam_cfg)
                            self._slots[cam_id] = slot
                            try:
                                self._connect_uvc(slot, dev_idx, cam_cfg)
                                matched_hw_indices.add(i)
                                found.append(cam_id)
                                logger.info("Config camera '%s' matched to UVC device %d", cam_id, dev_idx)
                            except Exception:
                                logger.exception("Failed to connect UVC device %d", dev_idx)
                            break

        # Pass 2: auto-add unmatched hardware from proprietary SDKs only.
        # UVC/Optris devices are NOT auto-added — they could be webcams, phones,
        # etc. Only explicitly configured UVC devices get connected.
        for i, hw_dev in enumerate(hw_devices):
            if i in matched_hw_indices:
                continue

            hw_sdk = hw_dev.get("sdk", "")
            if hw_sdk in ("uvc", "optris"):
                logger.debug("Skipping auto-discovery of %s device (must be in config)", hw_sdk)
                continue

            hw_serial = hw_dev.get("serial", "")
            hw_model = hw_dev.get("model", "")
            cam_id = f"{hw_sdk}_{hw_serial}" if hw_serial else f"{hw_sdk}_{i}"
            display_name = hw_model or cam_id

            if cam_id in self._slots:
                continue

            role = SDK_ROLE_HINTS.get(hw_sdk, "unknown")
            slot = CameraSlot(cam_id, role, hw_sdk, {})
            self._slots[cam_id] = slot

            try:
                self._connect_hardware(slot, hw_dev, {})
                found.append(cam_id)
                logger.info("Auto-discovered: %s — %s (%s)", cam_id, display_name, hw_sdk)
            except Exception:
                logger.exception("Failed to auto-connect %s", cam_id)

        return found

    def _scan_all_hardware(self) -> list[dict]:
        cam_configs = self._config.get("cameras", {})
        configured_sdks = {cfg.get("sdk", "") for cfg in cam_configs.values()}

        devices = []
        devices.extend(_enumerate_vimbax())
        devices.extend(_enumerate_pylon())

        if "uvc" in configured_sdks:
            devices.extend(_enumerate_uvc())
        else:
            logger.debug("Skipping UVC scan — no UVC cameras in config")

        if "optris" in configured_sdks:
            devices.extend(_enumerate_optris())
        else:
            logger.debug("Skipping Optris scan — no Optris cameras in config")

        logger.info("Hardware scan found %d device(s): %s",
                     len(devices),
                     [(d.get("sdk"), d.get("serial", d.get("device_index", "?"))) for d in devices])
        return devices

    def _find_hw_device(self, devices: list[dict], serial: str, sdk: str) -> Optional[dict]:
        for dev in devices:
            dev_serial = dev.get("serial", "")
            dev_sdk = dev.get("sdk", "")
            if dev_serial == serial:
                return dev
            if sdk and dev_sdk == sdk and dev_serial == serial:
                return dev
        return None

    def _connect_hardware(self, slot: CameraSlot, hw_dev: dict, cfg: dict):
        sdk = hw_dev.get("sdk", "")
        serial = hw_dev.get("serial", "")

        if sdk == "vimbax":
            from flash_camera.core.allied_vision_camera import AlliedVisionCamera
            cam = AlliedVisionCamera(device_id=serial)
        elif sdk == "pylon":
            from flash_camera.core.basler_camera import BaslerCamera
            cam = BaslerCamera(serial_number=serial)
        elif sdk == "uvc":
            from flash_camera.core.uvc_camera import UVCCamera
            dev_idx = hw_dev.get("device_index", 0)
            cam = UVCCamera(device_index=dev_idx, camera_id=slot.camera_id)
        elif sdk == "optris":
            from flash_camera.core.optris_camera import OptrisCamera
            cam = OptrisCamera(serial=serial, camera_id=slot.camera_id)
        else:
            raise ValueError(f"Unknown SDK: {sdk}")

        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        slot.sdk = sdk
        logger.info("Hardware camera %s connected (sdk=%s, serial=%s)", slot.camera_id, sdk, serial)

    def _connect_uvc(self, slot: CameraSlot, device_index: int, cfg: dict):
        from flash_camera.core.uvc_camera import UVCCamera
        cam = UVCCamera(device_index=device_index, camera_id=slot.camera_id)
        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        slot.sdk = "uvc"
        logger.info("UVC camera %s connected (index=%d)", slot.camera_id, device_index)

    def _connect_optris(self, slot: CameraSlot, serial: str, cfg: dict):
        from flash_camera.core.optris_camera import OptrisCamera
        config_xml = cfg.get("config_xml", "")
        cam = OptrisCamera(serial=serial, camera_id=slot.camera_id, config_xml=config_xml)
        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        slot.sdk = "optris"
        logger.info("Optris camera %s connected", slot.camera_id)

    def _connect_simulated(self, slot: CameraSlot, cfg: dict):
        from flash_camera.core.simulated_camera import SimulatedCamera
        w = cfg.get("simulated_width", 640)
        h = cfg.get("simulated_height", 480)
        cam = SimulatedCamera(
            width=w, height=h,
            camera_id=slot.camera_id,
            frame_rate=cfg.get("simulated_fps", 30.0),
        )
        cam.open()
        self._apply_defaults(cam, cfg)
        slot.camera = cam
        slot.connected = True
        slot.sdk = "simulated"
        logger.info("Simulated camera %s connected", slot.camera_id)

    def _apply_defaults(self, cam: CameraInterface, cfg: dict):
        try:
            fmt = cfg.get("default_pixel_format", "")
            if fmt and fmt in cam.get_pixel_formats():
                cam.set_pixel_format(fmt)
        except Exception:
            logger.warning("Could not set default pixel format")
        try:
            exp = cfg.get("default_exposure_us")
            if exp is not None:
                cam.set_exposure(float(exp))
        except Exception:
            logger.warning("Could not set default exposure")
        try:
            gain = cfg.get("default_gain_db")
            if gain is not None:
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

"""Basler camera implementation using pypylon (Pylon SDK)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np

from flash_camera.core.camera_interface import CameraInterface, FrameMetadata

try:
    from pypylon import pylon
    _HAS_PYPYLON = True
except ImportError:
    _HAS_PYPYLON = False

logger = logging.getLogger(__name__)

_PIXEL_FORMAT_MAP: dict[str, str] = {
    "Mono8": "Mono8",
    "Mono12": "Mono12",
    "Mono12p": "Mono12p",
    "Mono16": "Mono16",
    "BayerRG8": "BayerRG8",
    "BayerRG12": "BayerRG12",
}

_REVERSE_PIXEL_FORMAT_MAP = {v: k for k, v in _PIXEL_FORMAT_MAP.items()}


class BaslerCamera(CameraInterface):
    """Wraps pypylon for Basler cameras (ace, dart, boost, etc.)."""

    def __init__(self, serial_number: Optional[str] = None):
        if not _HAS_PYPYLON:
            raise RuntimeError(
                "pypylon is not installed. Install the Pylon SDK and "
                "'pip install pypylon' to use Basler cameras."
            )
        self._serial_number = serial_number
        self._cam: Optional[pylon.InstantCamera] = None
        self._acquiring = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_meta: Optional[FrameMetadata] = None
        self._frame_event = threading.Event()
        self._frame_id = 0
        self._exposure_us = 1000.0
        self._gain_db = 0.0
        self._pixel_format = "Mono8"
        self._dropped_count = 0
        self._grab_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        logger.info("Opening Basler camera (serial=%s)", self._serial_number)

        if self._serial_number:
            tlf = pylon.TlFactory.GetInstance()
            di = pylon.DeviceInfo()
            di.SetSerialNumber(self._serial_number)
            devices = tlf.EnumerateDevices([di])
            if not devices:
                raise RuntimeError(
                    f"Basler camera with serial '{self._serial_number}' not found"
                )
            self._cam = pylon.InstantCamera(tlf.CreateDevice(devices[0]))
        else:
            self._cam = pylon.InstantCamera(
                pylon.TlFactory.GetInstance().CreateFirstDevice()
            )

        self._cam.Open()
        self._apply_initial_settings()
        logger.info(
            "Basler camera opened: %s (serial %s)",
            self._cam.GetDeviceInfo().GetModelName(),
            self._cam.GetDeviceInfo().GetSerialNumber(),
        )

    def _apply_initial_settings(self) -> None:
        try:
            self._cam.ExposureTime.SetValue(self._exposure_us)
        except Exception:
            try:
                self._cam.ExposureTimeAbs.SetValue(self._exposure_us)
            except Exception:
                logger.debug("Could not set initial exposure")
        try:
            self._cam.Gain.SetValue(self._gain_db)
        except Exception:
            try:
                self._cam.GainRaw.SetValue(int(self._gain_db))
            except Exception:
                logger.debug("Could not set initial gain")

    def close(self) -> None:
        logger.info("Closing Basler camera")
        if self._acquiring:
            self.stop_acquisition()
        if self._cam is not None:
            try:
                self._cam.Close()
            except Exception:
                logger.warning("Error closing Basler camera", exc_info=True)
            self._cam = None

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def start_acquisition(self) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            logger.warning("Acquisition already running")
            return
        self._frame_id = 0
        self._dropped_count = 0
        self._stop_event.clear()
        self._frame_event.clear()

        self._cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        self._grab_thread = threading.Thread(
            target=self._grab_loop, daemon=True, name="basler-grab"
        )
        self._acquiring = True
        self._grab_thread.start()
        logger.info("Acquisition started")

    def stop_acquisition(self) -> None:
        if not self._acquiring:
            return
        self._stop_event.set()
        if self._grab_thread is not None:
            self._grab_thread.join(timeout=3.0)
            self._grab_thread = None
        try:
            self._cam.StopGrabbing()
        except Exception:
            logger.warning("Error stopping grab", exc_info=True)
        self._acquiring = False
        logger.info("Acquisition stopped (dropped=%d)", self._dropped_count)

    def _grab_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                grab_result = self._cam.RetrieveResult(
                    500, pylon.TimeoutHandling_Return
                )
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.warning("Grab error", exc_info=True)
                continue

            if grab_result is None:
                continue

            try:
                if grab_result.GrabSucceeded():
                    arr = grab_result.GetArray().copy()
                    meta = FrameMetadata(
                        timestamp_ns=grab_result.TimeStamp if hasattr(grab_result, "TimeStamp") else time.time_ns(),
                        frame_id=self._frame_id,
                        exposure_us=self._exposure_us,
                        gain_db=self._gain_db,
                        camera_id="basler",
                        pixel_format=self._pixel_format,
                        width=arr.shape[1],
                        height=arr.shape[0],
                        dropped=False,
                    )
                    with self._lock:
                        self._latest_frame = arr
                        self._latest_meta = meta
                        self._frame_id += 1
                    self._frame_event.set()
                else:
                    self._dropped_count += 1
                    logger.debug(
                        "Dropped frame: %s", grab_result.GetErrorDescription()
                    )
            finally:
                grab_result.Release()

    def get_frame(self, timeout_ms: int = 1000) -> tuple[np.ndarray, FrameMetadata]:
        if not self._acquiring:
            raise RuntimeError("Acquisition is not running")
        self._frame_event.clear()
        if not self._frame_event.wait(timeout=timeout_ms / 1000.0):
            raise TimeoutError(f"No frame received within {timeout_ms} ms")
        with self._lock:
            frame = self._latest_frame
            meta = self._latest_meta
        if frame is None or meta is None:
            raise RuntimeError("Frame data unexpectedly None")
        return frame, meta

    # ------------------------------------------------------------------
    # Exposure / Gain
    # ------------------------------------------------------------------

    def set_exposure(self, us: float) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            self._cam.ExposureTime.SetValue(us)
        except Exception:
            self._cam.ExposureTimeAbs.SetValue(us)
        self._exposure_us = us
        logger.debug("Exposure set to %.1f µs", us)

    def set_gain(self, db: float) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            self._cam.Gain.SetValue(db)
        except Exception:
            self._cam.GainRaw.SetValue(int(db))
        self._gain_db = db
        logger.debug("Gain set to %.1f dB", db)

    def get_exposure_range(self) -> tuple[float, float]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            feat = self._cam.ExposureTime
        except Exception:
            feat = self._cam.ExposureTimeAbs
        return (feat.GetMin(), feat.GetMax())

    def get_gain_range(self) -> tuple[float, float]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            feat = self._cam.Gain
        except Exception:
            feat = self._cam.GainRaw
        return (feat.GetMin(), feat.GetMax())

    # ------------------------------------------------------------------
    # Pixel format
    # ------------------------------------------------------------------

    def set_pixel_format(self, fmt: str) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing pixel format")
        pylon_name = _PIXEL_FORMAT_MAP.get(fmt, fmt)
        self._cam.PixelFormat.SetValue(pylon_name)
        self._pixel_format = fmt
        logger.debug("Pixel format set to %s", fmt)

    def get_pixel_formats(self) -> list[str]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        pylon_fmts = self._cam.PixelFormat.Symbolics
        return [_REVERSE_PIXEL_FORMAT_MAP.get(f, f) for f in pylon_fmts]

    # ------------------------------------------------------------------
    # ROI / Sensor
    # ------------------------------------------------------------------

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if self._acquiring:
            raise RuntimeError("Stop acquisition before changing ROI")

        if x == 0 and y == 0 and width == 0 and height == 0:
            self._cam.OffsetX.SetValue(0)
            self._cam.OffsetY.SetValue(0)
            self._cam.Width.SetValue(self._cam.Width.GetMax())
            self._cam.Height.SetValue(self._cam.Height.GetMax())
        else:
            self._cam.OffsetX.SetValue(0)
            self._cam.OffsetY.SetValue(0)
            self._cam.Width.SetValue(width)
            self._cam.Height.SetValue(height)
            self._cam.OffsetX.SetValue(x)
            self._cam.OffsetY.SetValue(y)
        logger.debug("ROI set to (%d, %d, %d, %d)", x, y, width, height)

    def get_sensor_size(self) -> tuple[int, int]:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        return (self._cam.SensorWidth.GetValue(), self._cam.SensorHeight.GetValue())

    # ------------------------------------------------------------------
    # Info / Trigger / FPS
    # ------------------------------------------------------------------

    def get_camera_info(self) -> dict:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        info = self._cam.GetDeviceInfo()
        return {
            "model": info.GetModelName(),
            "serial": info.GetSerialNumber(),
            "firmware": info.GetDeviceFirmwareVersion() if hasattr(info, "GetDeviceFirmwareVersion") else "N/A",
            "sdk_version": pylon.GetPylonVersionString() if hasattr(pylon, "GetPylonVersionString") else "N/A",
            "interface": "basler / pypylon",
        }

    def set_trigger_mode(self, mode: str) -> None:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        if mode == "freerun":
            self._cam.TriggerMode.SetValue("Off")
        elif mode == "software":
            self._cam.TriggerMode.SetValue("On")
            self._cam.TriggerSource.SetValue("Software")
        elif mode == "hardware_rising":
            self._cam.TriggerMode.SetValue("On")
            self._cam.TriggerSource.SetValue("Line1")
            self._cam.TriggerActivation.SetValue("RisingEdge")
        elif mode == "hardware_falling":
            self._cam.TriggerMode.SetValue("On")
            self._cam.TriggerSource.SetValue("Line1")
            self._cam.TriggerActivation.SetValue("FallingEdge")
        else:
            raise ValueError(f"Unknown trigger mode: {mode}")
        logger.debug("Trigger mode set to %s", mode)

    def get_frame_rate(self) -> float:
        if self._cam is None:
            raise RuntimeError("Camera is not open")
        try:
            return self._cam.ResultingFrameRate.GetValue()
        except Exception:
            try:
                return self._cam.ResultingFrameRateAbs.GetValue()
            except Exception:
                return 0.0

    def is_acquiring(self) -> bool:
        return self._acquiring

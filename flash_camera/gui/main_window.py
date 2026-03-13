"""Top-level application window with dual viewports and unified controls."""

import logging
import os
import sys
import time
from functools import partial
from pathlib import Path

import numpy as np
import yaml
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QObject
from PyQt6.QtGui import QAction, QKeySequence, QPalette, QColor, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from flash_camera.core.camera_manager import CameraManager
from flash_camera.core.quality_presets import (
    PRESETS,
    QualityPreset,
    get_preset,
    estimate_storage_rate,
)
from flash_camera.core.recorder import RecordingSession, H265Encoder
from flash_camera.core.ipc_bus import IPCBus
from flash_camera.utils.timestamp import (
    get_utc_timestamp,
    TimestampSynchronizer,
)
from flash_camera.utils.metadata import (
    create_session_metadata,
    create_default_reactor_conditions,
    save_metadata,
)

from flash_camera.gui.live_view import LiveViewWidget
from flash_camera.gui.histogram_widget import HistogramWidget
from flash_camera.gui.camera_panel import CameraPanel
from flash_camera.gui.filter_selector import FilterSelector
from flash_camera.gui.quality_selector import QualitySelector
from flash_camera.gui.recording_controls import RecordingControls
from flash_camera.gui.overlay_controls import OverlayControls

logger = logging.getLogger(__name__)

_FILTER_LABELS = {
    "no_filter": "",
    "uv_shortpass": "UV ≤400nm",
    "810nm_ArI": "810nm Ar I",
    "780nm": "780nm Ar II/OH",
}

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
}
QSplitter::handle {
    background-color: #3a3a3a;
    width: 3px;
}
QStatusBar {
    background-color: #1a1a1a;
    color: #aaaaaa;
    font-size: 11px;
}
"""


class FrameDispatcher(QObject):
    """Receives frames from acquisition threads and dispatches to GUI on main thread."""
    frame_ready = pyqtSignal(str, object, object)


class MainWindow(QMainWindow):

    def __init__(self, config: dict, use_simulated: bool = False):
        super().__init__()
        self._config = config
        self._use_simulated = use_simulated

        self._recording = False
        self._recording_session: RecordingSession | None = None
        self._record_start_time: float = 0.0
        self._encoding_jobs: list[H265Encoder] = []
        self._oes_sync_data: dict = {}

        self._timestamp_sync = TimestampSynchronizer()
        self._frame_dispatcher = FrameDispatcher(self)
        self._frame_dispatcher.frame_ready.connect(self._on_frame_from_camera)

        self.setWindowTitle("Flash Camera — Dual UV Imaging")
        self.setMinimumSize(1200, 800)
        self.resize(1600, 1000)
        self.setStyleSheet(DARK_STYLE)

        self._init_camera_manager()
        self._init_ipc()
        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._setup_timers()

        self._start_cameras()

    def _init_camera_manager(self):
        self._cam_mgr = CameraManager(self._config)
        found = self._cam_mgr.discover_cameras(use_simulated=self._use_simulated)
        logger.info("Cameras discovered: %s", found)

        rec_cfg = self._config.get("recording", {})
        bit_depth = "Mono12"
        self._cam_mgr.init_ring_buffers(
            duration_s=rec_cfg.get("pretrigger_buffer_s", 2.0),
            max_fps=30.0,
            bit_depth=bit_depth,
        )

        for slot in self._cam_mgr.slots.values():
            slot.set_frame_callback(self._frame_callback)
            self._timestamp_sync.register_camera(slot.camera_id)

    def _init_ipc(self):
        zmq_cfg = self._config.get("zmq", {})
        try:
            self._ipc = IPCBus(
                pub_port=zmq_cfg.get("camera_pub_port", 5556),
                sub_port=zmq_cfg.get("oes_pub_port", 5555),
                heartbeat_interval_s=zmq_cfg.get("heartbeat_interval_s", 1.0),
            )
            self._ipc.start()
            self._ipc.set_status(cameras_connected=self._cam_mgr.get_connected_ids())
        except Exception:
            logger.exception("Failed to start IPC bus — running without OES integration")
            self._ipc = None

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        self._build_top_bar(main_layout)

        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        self._av_viewport = self._build_camera_viewport("allied_vision", "overview")
        self._basler_viewport = self._build_camera_viewport("basler", "closeup_filtered")

        body_splitter.addWidget(self._av_viewport["container"])
        body_splitter.addWidget(self._basler_viewport["container"])
        body_splitter.setSizes([500, 500])
        main_layout.addWidget(body_splitter, stretch=1)

        self._build_bottom_bar(main_layout)

    def _build_top_bar(self, parent_layout):
        bar = QHBoxLayout()
        bar.setSpacing(12)

        title = QLabel("Flash Camera")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4a90d9;")
        bar.addWidget(title)

        self._oes_indicator = QLabel("● OES Disconnected")
        self._oes_indicator.setStyleSheet("color: #ff4444; font-size: 12px;")
        bar.addWidget(self._oes_indicator)

        bar.addStretch()

        self._overlay_controls = OverlayControls()
        bar.addWidget(self._overlay_controls)

        parent_layout.addLayout(bar)

    def _build_camera_viewport(self, camera_id: str, role: str) -> dict:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        live_view = LiveViewWidget()
        cam_cfg = self._config.get("cameras", {}).get(camera_id, {})
        fov = cam_cfg.get("fov_mm")
        if fov:
            live_view.set_fov_mm(tuple(fov))
        layout.addWidget(live_view, stretch=1)

        histogram = HistogramWidget()
        layout.addWidget(histogram)

        controls_row = QHBoxLayout()
        panel = CameraPanel(camera_id, role)
        controls_row.addWidget(panel)

        filter_sel = None
        if camera_id == "basler":
            filter_sel = FilterSelector()
            default_filter = cam_cfg.get("default_filter", "no_filter")
            filter_sel.set_filter(default_filter)
            controls_row.addWidget(filter_sel)

        layout.addLayout(controls_row)

        slot = self._cam_mgr.slots.get(camera_id)
        if slot and slot.connected:
            panel.set_connected(True)
            cam = slot.camera
            if cam is not None:
                try:
                    panel.set_exposure_range(*cam.get_exposure_range())
                    panel.set_gain_range(*cam.get_gain_range())
                    panel.set_pixel_formats(cam.get_pixel_formats())
                    cfg = self._config.get("cameras", {}).get(camera_id, {})
                    panel.update_values(
                        cfg.get("default_exposure_us", 500),
                        cfg.get("default_gain_db", 0.0),
                        cfg.get("default_pixel_format", "Mono8"),
                    )
                except Exception:
                    logger.exception("Failed to initialize panel for %s", camera_id)
        else:
            panel.set_connected(False)

        return {
            "container": container,
            "live_view": live_view,
            "histogram": histogram,
            "panel": panel,
            "filter_selector": filter_sel,
            "camera_id": camera_id,
        }

    def _build_bottom_bar(self, parent_layout):
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._quality_selector = QualitySelector()
        bottom.addWidget(self._quality_selector, stretch=1)

        self._recording_controls = RecordingControls()
        bottom.addWidget(self._recording_controls, stretch=2)

        parent_layout.addLayout(bottom)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _connect_signals(self):
        self._recording_controls.record_start_requested.connect(self._start_recording)
        self._recording_controls.record_stop_requested.connect(self._stop_recording)

        self._quality_selector.preset_changed.connect(self._on_preset_changed)

        self._overlay_controls.crosshair_toggled.connect(
            lambda v: (
                self._av_viewport["live_view"].set_crosshair_visible(v),
                self._basler_viewport["live_view"].set_crosshair_visible(v),
            )
        )
        self._overlay_controls.scale_bar_toggled.connect(
            lambda v: (
                self._av_viewport["live_view"].set_scale_bar_visible(v),
                self._basler_viewport["live_view"].set_scale_bar_visible(v),
            )
        )
        self._overlay_controls.info_toggled.connect(
            lambda v: (
                self._av_viewport["live_view"].set_info_visible(v),
                self._basler_viewport["live_view"].set_info_visible(v),
            )
        )
        self._overlay_controls.colormap_changed.connect(
            lambda v: (
                self._av_viewport["live_view"].set_colormap(v),
                self._basler_viewport["live_view"].set_colormap(v),
            )
        )

        for vp in (self._av_viewport, self._basler_viewport):
            cam_id = vp["camera_id"]
            vp["panel"].exposure_changed.connect(partial(self._set_camera_exposure, cam_id))
            vp["panel"].gain_changed.connect(partial(self._set_camera_gain, cam_id))
            vp["panel"].pixel_format_changed.connect(partial(self._set_camera_pixel_format, cam_id))
            vp["panel"].roi_changed.connect(partial(self._set_camera_roi, cam_id))
            vp["panel"].rescan_requested.connect(self._rescan_cameras)

        fs = self._basler_viewport.get("filter_selector")
        if fs:
            fs.filter_changed.connect(self._on_filter_changed)

        if self._ipc is not None:
            self._ipc.record_start_received.connect(self._on_oes_record_start)
            self._ipc.record_stop_received.connect(self._on_oes_record_stop)
            self._ipc.heartbeat_timeout.connect(self._on_oes_timeout)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._toggle_recording)
        QShortcut(QKeySequence(Qt.Key.Key_T), self, self._software_trigger)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Q), self, self._cycle_quality_preset)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._exit_fullscreen)

    def _setup_timers(self):
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._update_display_stats)
        self._display_timer.start(200)

        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._update_recording_stats)

        self._encoding_timer = QTimer(self)
        self._encoding_timer.timeout.connect(self._update_encoding_progress)

    def _start_cameras(self):
        self._cam_mgr.start_all()
        connected = self._cam_mgr.get_connected_ids()
        if self._ipc is not None:
            self._ipc.set_status(cameras_connected=connected)

    # ── Frame handling ──────────────────────────────────────────

    def _frame_callback(self, camera_id: str, frame: np.ndarray, meta):
        """Called from acquisition thread — dispatch to main thread via signal."""
        self._frame_dispatcher.frame_ready.emit(camera_id, frame, meta)

        if self._recording and self._recording_session is not None:
            self._recording_session.write_frame(camera_id, frame, meta)

    @pyqtSlot(str, object, object)
    def _on_frame_from_camera(self, camera_id: str, frame: np.ndarray, meta):
        """Handle frame on the main GUI thread."""
        vp = self._av_viewport if camera_id == "allied_vision" else self._basler_viewport

        meta_dict = {
            "exposure_us": meta.exposure_us,
            "gain_db": meta.gain_db,
            "pixel_format": meta.pixel_format,
            "frame_counter": meta.frame_id,
        }
        vp["live_view"].update_frame(frame, meta_dict)
        vp["histogram"].update_histogram(frame)

    # ── Camera controls ────────────────────────────────────────

    def _set_camera_exposure(self, camera_id: str, us: float):
        slot = self._cam_mgr.slots.get(camera_id)
        if slot and slot.camera:
            try:
                slot.camera.set_exposure(us)
            except Exception:
                logger.exception("Failed to set exposure on %s", camera_id)

    def _set_camera_gain(self, camera_id: str, db: float):
        slot = self._cam_mgr.slots.get(camera_id)
        if slot and slot.camera:
            try:
                slot.camera.set_gain(db)
            except Exception:
                logger.exception("Failed to set gain on %s", camera_id)

    def _set_camera_pixel_format(self, camera_id: str, fmt: str):
        slot = self._cam_mgr.slots.get(camera_id)
        if slot and slot.camera:
            try:
                was_acquiring = slot.acquiring
                if was_acquiring:
                    slot.stop_acquisition()
                slot.camera.set_pixel_format(fmt)
                if was_acquiring:
                    slot.start_acquisition()
                self._quality_selector.preset_changed.emit("custom")
            except Exception:
                logger.exception("Failed to set pixel format on %s", camera_id)

    def _set_camera_roi(self, camera_id: str, x: int, y: int, w: int, h: int):
        slot = self._cam_mgr.slots.get(camera_id)
        if slot and slot.camera:
            try:
                was_acquiring = slot.acquiring
                if was_acquiring:
                    slot.stop_acquisition()
                slot.camera.set_roi(x, y, w, h)
                if was_acquiring:
                    slot.start_acquisition()
            except Exception:
                logger.exception("Failed to set ROI on %s", camera_id)

    def _on_preset_changed(self, preset_name: str):
        if self._recording:
            return
        preset = PRESETS.get(preset_name)
        if preset is None:
            return
        for cam_id, slot in self._cam_mgr.slots.items():
            if slot.camera is None:
                continue
            try:
                was_acquiring = slot.acquiring
                if was_acquiring:
                    slot.stop_acquisition()
                if preset.bit_depth in slot.camera.get_pixel_formats():
                    slot.camera.set_pixel_format(preset.bit_depth)
                if was_acquiring:
                    slot.start_acquisition()
            except Exception:
                logger.exception("Failed to apply preset to %s", cam_id)
            vp = self._av_viewport if cam_id == "allied_vision" else self._basler_viewport
            vp["panel"].update_values(
                slot.camera.get_exposure_range()[0],
                slot.camera.get_gain_range()[0],
                preset.bit_depth,
            )

    def _on_filter_changed(self, filter_key: str):
        label = _FILTER_LABELS.get(filter_key, "")
        self._basler_viewport["live_view"].set_filter_label(label)

    def _rescan_cameras(self):
        self._cam_mgr.rescan()
        for vp in (self._av_viewport, self._basler_viewport):
            cam_id = vp["camera_id"]
            slot = self._cam_mgr.slots.get(cam_id)
            vp["panel"].set_connected(slot.connected if slot else False)
        self._start_cameras()

    # ── Recording ──────────────────────────────────────────────

    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if self._recording:
            return

        rec_cfg = self._config.get("recording", {})
        data_root = rec_cfg.get("data_root", "./flash_data")
        session_name = self._recording_controls.get_session_name()

        preset_name = self._quality_selector.get_current_preset()
        preset = PRESETS.get(preset_name, PRESETS["high"])

        cameras = self._cam_mgr.get_connected_ids()
        if not cameras:
            self._recording_controls.show_warning("No cameras connected", "error")
            return

        self._recording_session = RecordingSession(
            data_root=data_root,
            session_name=session_name,
            quality_preset=preset,
            cameras=cameras,
        )

        for slot in self._cam_mgr.slots.values():
            if slot.ring_buffer is not None:
                buffered = slot.ring_buffer.flush()
                for frame, meta in buffered:
                    self._recording_session.write_frame(slot.camera_id, frame, meta)

        self._recording_session.start()
        self._recording = True
        self._record_start_time = time.monotonic()

        self._recording_controls.set_recording(True)
        self._quality_selector.set_locked(True)
        self._av_viewport["live_view"].set_recording(True)
        self._basler_viewport["live_view"].set_recording(True)
        for vp in (self._av_viewport, self._basler_viewport):
            vp["panel"].set_recording_mode(True)

        self._record_timer.start(100)

        if self._ipc is not None:
            self._ipc.publisher.publish_recording_state(
                "started", session_name, {c: 0 for c in cameras}
            )
            self._ipc.set_status(is_recording=True)

        self._status_bar.showMessage(f"Recording: {session_name}")
        logger.info("Recording started: %s", session_name)

    def _stop_recording(self):
        if not self._recording:
            return

        self._record_timer.stop()
        self._recording = False

        stats = {}
        if self._recording_session is not None:
            stats = self._recording_session.stop()
            session_dir = self._recording_session.session_dir

            self._save_session_metadata(session_dir, stats)

            try:
                encoders = self._recording_session.encode_previews()
                for enc in encoders:
                    self._encoding_jobs.append(enc)
                    self._recording_controls.add_encoding_job(
                        self._recording_session._session_name
                    )
                if encoders:
                    self._encoding_timer.start(500)
            except Exception:
                logger.exception("Failed to start H.265 encoding")

            self._recording_session = None

        self._recording_controls.set_recording(False)
        self._quality_selector.set_locked(False)
        self._av_viewport["live_view"].set_recording(False)
        self._basler_viewport["live_view"].set_recording(False)
        for vp in (self._av_viewport, self._basler_viewport):
            vp["panel"].set_recording_mode(False)

        if self._ipc is not None:
            frame_counts = {}
            for cam_id, cam_stats in stats.get("cameras", {}).items():
                frame_counts[cam_id] = cam_stats.get("frames_written", 0)
            self._ipc.publisher.publish_recording_state(
                "stopped",
                stats.get("session_name", ""),
                frame_counts,
            )
            self._ipc.set_status(is_recording=False)

        self._status_bar.showMessage("Recording stopped")
        logger.info("Recording stopped")

    def _save_session_metadata(self, session_dir: Path, stats: dict):
        session_name = self._recording_controls.get_session_name()
        operator = self._recording_controls.get_operator()
        notes = self._recording_controls.get_notes()

        preset_name = self._quality_selector.get_current_preset()
        quality = self._quality_selector.get_quality_settings()
        quality["preset"] = preset_name
        elapsed = stats.get("elapsed_s", 0.0)
        total_bytes = 0
        for cam_stats in stats.get("cameras", {}).values():
            total_bytes += cam_stats.get("frames_written", 0) * 3840 * 2160 * 2
        if elapsed > 0:
            quality["actual_avg_write_mb_s"] = total_bytes / elapsed / (1024 * 1024)

        cameras_info = {}
        for cam_id, slot in self._cam_mgr.slots.items():
            cam_data = {"frame_count": 0, "avg_fps": 0.0}
            cam_stats = stats.get("cameras", {}).get(cam_id, {})
            cam_data["frame_count"] = cam_stats.get("frames_written", 0)
            cam_data["avg_fps"] = cam_stats.get("write_rate_fps", 0.0)
            if slot.camera is not None:
                try:
                    info = slot.camera.get_camera_info()
                    cam_data.update(info)
                except Exception:
                    pass
            cam_cfg = self._config.get("cameras", {}).get(cam_id, {})
            cam_data["lens"] = cam_cfg.get("lens", "")
            cam_data["working_distance_mm"] = cam_cfg.get("working_distance_mm", 0)
            cam_data["fov_mm"] = cam_cfg.get("fov_mm", [])
            if cam_id == "basler":
                fs = self._basler_viewport.get("filter_selector")
                cam_data["filter_installed"] = fs.get_current_filter() if fs else "no_filter"
            cameras_info[cam_id] = cam_data

        reactor = create_default_reactor_conditions()
        reactor["notes"] = notes

        file_paths = {}
        for cam_id in self._cam_mgr.get_connected_ids():
            file_paths[f"{cam_id}_tiff"] = f"{session_name}/{cam_id}/"
            file_paths[f"{cam_id}_mp4"] = f"{session_name}/{cam_id}_preview.mp4"

        metadata = create_session_metadata(
            session_id=session_name,
            operator=operator,
            quality_preset=quality,
            cameras_info=cameras_info,
            reactor_conditions=reactor,
            oes_sync=self._oes_sync_data if self._oes_sync_data else None,
            file_paths=file_paths,
            duration_s=elapsed,
        )

        metadata_path = session_dir / "metadata.json"
        try:
            save_metadata(metadata, str(metadata_path))
            logger.info("Session metadata saved to %s", metadata_path)
        except Exception:
            logger.exception("Failed to save metadata")

    # ── Display updates ────────────────────────────────────────

    def _update_display_stats(self):
        for vp in (self._av_viewport, self._basler_viewport):
            cam_id = vp["camera_id"]
            slot = self._cam_mgr.slots.get(cam_id)
            if slot and slot.camera:
                try:
                    fps = slot.camera.get_frame_rate()
                    vp["panel"].set_frame_rate(fps)
                except Exception:
                    pass

        if self._ipc is not None:
            connected = self._ipc.is_oes_connected
            if connected:
                self._oes_indicator.setText("● OES Connected")
                self._oes_indicator.setStyleSheet("color: #44cc44; font-size: 12px;")
            else:
                self._oes_indicator.setText("● OES Disconnected")
                self._oes_indicator.setStyleSheet("color: #ff4444; font-size: 12px;")

    def _update_recording_stats(self):
        if not self._recording:
            return
        elapsed = time.monotonic() - self._record_start_time
        self._recording_controls.set_elapsed_time(elapsed)

        if self._recording_session is not None:
            stats = self._recording_session.get_stats()
            frame_counts = {}
            for cam_id, cam_stats in stats.get("cameras", {}).items():
                frame_counts[cam_id] = cam_stats.get("frames_written", 0)
            self._recording_controls.set_frame_counts(frame_counts)

            total_queue = sum(
                cs.get("queue_depth", 0) for cs in stats.get("cameras", {}).values()
            )
            if total_queue > 50:
                self._recording_controls.show_warning(
                    f"WRITE LAG: {total_queue} frames behind", "warning"
                )
            else:
                self._recording_controls.clear_warnings()

    def _update_encoding_progress(self):
        all_done = True
        for i, enc in enumerate(self._encoding_jobs):
            progress = enc.get_progress() * 100
            self._recording_controls.update_encoding_progress(
                f"job_{i}", progress
            )
            if enc.is_running():
                all_done = False
        if all_done and self._encoding_jobs:
            self._encoding_timer.stop()
            self._encoding_jobs.clear()

    # ── IPC handlers ──────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_oes_record_start(self, payload: dict):
        self._oes_sync_data = {
            "oes_session_file": payload.get("oes_file", ""),
            "oes_start_utc": payload.get("timestamp_utc", ""),
            "camera_start_utc": get_utc_timestamp(),
            "sync_method": "zmq_start_message",
            "triggered_by": "oes_app",
        }

        session_id = payload.get("session_id", "")
        if session_id:
            self._recording_controls._session_edit.setText(session_id)
        notes = payload.get("notes", "")
        if notes:
            self._recording_controls.set_notes(notes)

        self._start_recording()

    @pyqtSlot(dict)
    def _on_oes_record_stop(self, payload: dict):
        self._stop_recording()

    def _on_oes_timeout(self):
        self._oes_indicator.setText("● OES Disconnected")
        self._oes_indicator.setStyleSheet("color: #ff4444; font-size: 12px;")

    # ── Keyboard shortcuts ────────────────────────────────────

    def _software_trigger(self):
        for slot in self._cam_mgr.slots.values():
            if slot.camera:
                try:
                    slot.camera.set_trigger_mode("software")
                except Exception:
                    pass

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def _cycle_quality_preset(self):
        if self._recording:
            return
        order = ["maximum", "high", "balanced", "fast", "compact"]
        current = self._quality_selector.get_current_preset()
        try:
            idx = order.index(current)
            next_key = order[(idx + 1) % len(order)]
        except ValueError:
            next_key = "maximum"
        btn = self._quality_selector._buttons.get(next_key)
        if btn:
            btn.setChecked(True)
            self._quality_selector._on_preset_clicked(btn)

    # ── Cleanup ───────────────────────────────────────────────

    def closeEvent(self, event):
        if self._recording:
            reply = QMessageBox.question(
                self, "Recording Active",
                "A recording is in progress. Stop and save before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            self._stop_recording()

        if self._encoding_jobs:
            active = [e for e in self._encoding_jobs if e.is_running()]
            if active:
                reply = QMessageBox.question(
                    self, "Encoding in Progress",
                    f"{len(active)} encoding job(s) still running. Cancel them?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    for enc in active:
                        enc.cancel()

        self._cam_mgr.close_all()
        if self._ipc is not None:
            self._ipc.stop()
        event.accept()

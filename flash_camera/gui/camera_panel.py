"""Per-camera controls widget."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 14px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #4a90d9;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #3a3a3a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4a90d9;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 2px 4px;
    min-height: 22px;
}
QPushButton {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 4px 12px;
    min-height: 22px;
}
QPushButton:hover { background-color: #3a3a3a; }
QPushButton:pressed { background-color: #4a90d9; }
QPushButton:disabled { color: #555555; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3a3a3a;
    border-radius: 2px;
    background-color: #2a2a2a;
}
QCheckBox::indicator:checked { background-color: #4a90d9; }
"""

_ROLE_LABELS = {
    "overview": "Allied Vision (Overview)",
    "closeup_filtered": "Basler (Close-Up)",
}


class CameraPanel(QWidget):
    exposure_changed = pyqtSignal(float)
    gain_changed = pyqtSignal(float)
    pixel_format_changed = pyqtSignal(str)
    roi_changed = pyqtSignal(int, int, int, int)
    trigger_mode_changed = pyqtSignal(str)
    auto_exposure_toggled = pyqtSignal(bool)
    flat_field_loaded = pyqtSignal(str)
    flat_field_cleared = pyqtSignal()
    rescan_requested = pyqtSignal()

    def __init__(self, camera_id: str, camera_role: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._camera_id = camera_id
        self._camera_role = camera_role
        self._updating = False
        self.setStyleSheet(STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        title = QLabel(_ROLE_LABELS.get(self._camera_role, self._camera_id))
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #4a90d9;")
        root.addWidget(title)

        self._build_connection_row(root)
        self._build_exposure(root)
        self._build_gain(root)
        self._build_pixel_format(root)
        self._build_frame_rate(root)
        self._build_roi(root)
        self._build_trigger(root)
        self._build_auto_exposure(root)
        self._build_flat_field(root)
        root.addStretch()

    # --- connection -----------------------------------------------------------

    def _build_connection_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self._conn_dot = QLabel("●")
        self._conn_dot.setFixedWidth(16)
        self._set_dot_color(False)
        row.addWidget(self._conn_dot)
        self._conn_label = QLabel("Disconnected")
        row.addWidget(self._conn_label, 1)
        btn = QPushButton("Rescan")
        btn.setFixedWidth(60)
        btn.clicked.connect(self.rescan_requested.emit)
        row.addWidget(btn)
        layout.addLayout(row)

    def _set_dot_color(self, connected: bool) -> None:
        color = "#44cc44" if connected else "#ff4444"
        self._conn_dot.setStyleSheet(f"color: {color}; font-size: 16px;")

    # --- exposure -------------------------------------------------------------

    def _build_exposure(self, layout: QVBoxLayout) -> None:
        grp = QGroupBox("Exposure (µs)")
        gl = QHBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        self._exp_slider = QSlider(Qt.Orientation.Horizontal)
        self._exp_slider.setRange(0, 1000000)
        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setDecimals(1)
        self._exp_spin.setRange(0, 1_000_000)
        self._exp_spin.setSuffix(" µs")
        gl.addWidget(self._exp_slider, 1)
        gl.addWidget(self._exp_spin)
        layout.addWidget(grp)

        self._exp_slider.valueChanged.connect(self._on_exp_slider)
        self._exp_spin.valueChanged.connect(self._on_exp_spin)

    def _on_exp_slider(self, val: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._exp_spin.setValue(float(val))
        self._updating = False
        self.exposure_changed.emit(float(val))

    def _on_exp_spin(self, val: float) -> None:
        if self._updating:
            return
        self._updating = True
        self._exp_slider.setValue(int(val))
        self._updating = False
        self.exposure_changed.emit(val)

    # --- gain -----------------------------------------------------------------

    def _build_gain(self, layout: QVBoxLayout) -> None:
        grp = QGroupBox("Gain (dB)")
        gl = QHBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        self._gain_slider = QSlider(Qt.Orientation.Horizontal)
        self._gain_slider.setRange(0, 480)
        self._gain_spin = QDoubleSpinBox()
        self._gain_spin.setDecimals(1)
        self._gain_spin.setRange(0, 48.0)
        self._gain_spin.setSuffix(" dB")
        gl.addWidget(self._gain_slider, 1)
        gl.addWidget(self._gain_spin)
        layout.addWidget(grp)

        self._gain_slider.valueChanged.connect(self._on_gain_slider)
        self._gain_spin.valueChanged.connect(self._on_gain_spin)

    def _on_gain_slider(self, val: int) -> None:
        if self._updating:
            return
        self._updating = True
        db = val / 10.0
        self._gain_spin.setValue(db)
        self._updating = False
        self.gain_changed.emit(db)

    def _on_gain_spin(self, val: float) -> None:
        if self._updating:
            return
        self._updating = True
        self._gain_slider.setValue(int(val * 10))
        self._updating = False
        self.gain_changed.emit(val)

    # --- pixel format ---------------------------------------------------------

    def _build_pixel_format(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Pixel Format"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.currentTextChanged.connect(self._on_fmt)
        row.addWidget(self._fmt_combo, 1)
        layout.addLayout(row)

    def _on_fmt(self, text: str) -> None:
        if not self._updating and text:
            self.pixel_format_changed.emit(text)

    # --- frame rate -----------------------------------------------------------

    def _build_frame_rate(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Frame Rate"))
        self._fps_label = QLabel("— fps")
        self._fps_label.setStyleSheet("color: #4a90d9; font-weight: bold;")
        row.addWidget(self._fps_label)
        row.addStretch()
        layout.addLayout(row)

    # --- ROI ------------------------------------------------------------------

    def _build_roi(self, layout: QVBoxLayout) -> None:
        grp = QGroupBox("ROI")
        gl = QVBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        fields = QHBoxLayout()
        self._roi_spins: dict[str, QSpinBox] = {}
        for label in ("X", "Y", "W", "H"):
            fields.addWidget(QLabel(label))
            sb = QSpinBox()
            sb.setRange(0, 9999)
            sb.valueChanged.connect(self._on_roi)
            self._roi_spins[label] = sb
            fields.addWidget(sb)
        gl.addLayout(fields)
        btn = QPushButton("Full Frame")
        btn.clicked.connect(self._reset_roi)
        gl.addWidget(btn)
        layout.addWidget(grp)

    def _on_roi(self) -> None:
        if self._updating:
            return
        self.roi_changed.emit(
            self._roi_spins["X"].value(),
            self._roi_spins["Y"].value(),
            self._roi_spins["W"].value(),
            self._roi_spins["H"].value(),
        )

    def _reset_roi(self) -> None:
        self._updating = True
        for sb in self._roi_spins.values():
            sb.setValue(0)
        self._updating = False
        self.roi_changed.emit(0, 0, 0, 0)

    # --- trigger --------------------------------------------------------------

    def _build_trigger(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Trigger"))
        self._trigger_combo = QComboBox()
        self._trigger_combo.addItems(["Freerun", "Software Trigger"])
        self._trigger_combo.currentTextChanged.connect(self._on_trigger)
        row.addWidget(self._trigger_combo, 1)
        layout.addLayout(row)

    def _on_trigger(self, text: str) -> None:
        if not self._updating:
            self.trigger_mode_changed.emit(text)

    # --- auto-exposure --------------------------------------------------------

    def _build_auto_exposure(self, layout: QVBoxLayout) -> None:
        self._ae_check = QCheckBox("Auto-Exposure")
        self._ae_check.toggled.connect(self.auto_exposure_toggled.emit)
        layout.addWidget(self._ae_check)

    # --- flat-field -----------------------------------------------------------

    def _build_flat_field(self, layout: QVBoxLayout) -> None:
        grp = QGroupBox("Flat-Field Correction")
        gl = QVBoxLayout(grp)
        gl.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        load_btn = QPushButton("Load Reference")
        load_btn.clicked.connect(self._load_flat_field)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_flat_field)
        row.addWidget(load_btn)
        row.addWidget(clear_btn)
        gl.addLayout(row)
        self._ff_status = QLabel("No reference loaded")
        self._ff_status.setStyleSheet("color: #888888; font-style: italic;")
        gl.addWidget(self._ff_status)
        layout.addWidget(grp)

    def _load_flat_field(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Flat-Field Reference", "", "Images (*.tif *.tiff *.png *.npy)"
        )
        if path:
            self._ff_status.setText(Path(path).name)
            self._ff_status.setStyleSheet("color: #44cc44; font-style: italic;")
            self.flat_field_loaded.emit(path)

    def _clear_flat_field(self) -> None:
        self._ff_status.setText("No reference loaded")
        self._ff_status.setStyleSheet("color: #888888; font-style: italic;")
        self.flat_field_cleared.emit()

    # --- public API -----------------------------------------------------------

    def set_exposure_range(self, min_us: float, max_us: float) -> None:
        self._updating = True
        self._exp_slider.setRange(int(min_us), int(max_us))
        self._exp_spin.setRange(min_us, max_us)
        self._updating = False

    def set_gain_range(self, min_db: float, max_db: float) -> None:
        self._updating = True
        self._gain_slider.setRange(int(min_db * 10), int(max_db * 10))
        self._gain_spin.setRange(min_db, max_db)
        self._updating = False

    def set_pixel_formats(self, formats: list[str]) -> None:
        self._updating = True
        self._fmt_combo.clear()
        self._fmt_combo.addItems(formats)
        self._updating = False

    def set_connected(self, connected: bool) -> None:
        self._set_dot_color(connected)
        self._conn_label.setText("Connected" if connected else "Disconnected")

    def set_frame_rate(self, fps: float) -> None:
        self._fps_label.setText(f"{fps:.1f} fps")

    def set_recording_mode(self, recording: bool) -> None:
        self._ae_check.setDisabled(recording)
        self._trigger_combo.setDisabled(recording)
        self._fmt_combo.setDisabled(recording)
        for sb in self._roi_spins.values():
            sb.setDisabled(recording)

    def update_values(self, exposure_us: float, gain_db: float, pixel_format: str) -> None:
        self._updating = True
        self._exp_slider.setValue(int(exposure_us))
        self._exp_spin.setValue(exposure_us)
        self._gain_slider.setValue(int(gain_db * 10))
        self._gain_spin.setValue(gain_db)
        idx = self._fmt_combo.findText(pixel_format)
        if idx >= 0:
            self._fmt_combo.setCurrentIndex(idx)
        self._updating = False

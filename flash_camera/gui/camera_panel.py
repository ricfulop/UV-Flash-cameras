"""Per-camera controls widget — compact, scrollable layout."""

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
    QScrollArea,
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
    font-size: 11px;
}
QGroupBox {
    border: 1px solid #333333;
    border-radius: 3px;
    margin-top: 6px;
    padding: 4px 3px 3px 3px;
    font-weight: bold;
    font-size: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 6px;
    padding: 0 3px;
    color: #4a90d9;
    font-size: 10px;
}
QSlider::groove:horizontal {
    height: 3px;
    background: #3a3a3a;
    border-radius: 1px;
}
QSlider::handle:horizontal {
    background: #4a90d9;
    width: 10px;
    margin: -4px 0;
    border-radius: 5px;
}
QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 1px 3px;
    min-height: 18px;
    font-size: 11px;
}
QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    color: #cccccc;
    selection-background-color: #4a90d9;
    selection-color: #ffffff;
    border: 1px solid #333333;
}
QComboBox::drop-down {
    border: none;
    width: 16px;
}
QPushButton {
    background-color: #2a2a2a;
    border: 1px solid #333333;
    border-radius: 2px;
    padding: 2px 8px;
    min-height: 18px;
    font-size: 11px;
}
QPushButton:hover { background-color: #3a3a3a; }
QPushButton:pressed { background-color: #4a90d9; }
QPushButton:disabled { color: #555555; }
QCheckBox {
    spacing: 4px;
    font-size: 11px;
}
QCheckBox::indicator {
    width: 12px;
    height: 12px;
    border: 1px solid #333333;
    border-radius: 2px;
    background-color: #2a2a2a;
}
QCheckBox::indicator:checked { background-color: #4a90d9; }
QLabel {
    font-size: 11px;
}
QScrollArea {
    border: none;
    background: transparent;
}
"""

_ROLE_LABELS = {
    "overview": "Allied Vision (Overview)",
    "closeup_filtered": "Basler (Close-Up)",
    "microscope": "USB Microscope",
    "thermal": "Optris Thermal",
    "simulated": "Simulated Camera",
    "unknown": "Camera",
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)
        header.setSpacing(4)

        self._conn_dot = QLabel("●")
        self._conn_dot.setFixedWidth(12)
        self._set_dot_color(False)
        header.addWidget(self._conn_dot)

        title = QLabel(_ROLE_LABELS.get(self._camera_role, self._camera_id))
        title.setStyleSheet("font-size: 11px; font-weight: bold; color: #4a90d9;")
        header.addWidget(title, 1)

        self._fps_label = QLabel("— fps")
        self._fps_label.setStyleSheet("color: #4a90d9; font-weight: bold; font-size: 10px;")
        header.addWidget(self._fps_label)

        btn = QPushButton("Rescan")
        btn.setFixedWidth(50)
        btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 1px 4px; min-height: 16px; }"
            "QPushButton:hover { background-color: #3a3a3a; }"
        )
        btn.clicked.connect(self.rescan_requested.emit)
        header.addWidget(btn)

        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(2)

        self._build_exposure_gain_row(root)
        self._build_format_trigger_row(root)
        self._build_roi_row(root)
        root.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _build_exposure_gain_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(4)

        row.addWidget(QLabel("Exp"))
        self._exp_slider = QSlider(Qt.Orientation.Horizontal)
        self._exp_slider.setRange(0, 1000000)
        self._exp_slider.setMinimumWidth(40)
        row.addWidget(self._exp_slider, 1)
        self._exp_spin = QDoubleSpinBox()
        self._exp_spin.setDecimals(0)
        self._exp_spin.setRange(0, 1_000_000)
        self._exp_spin.setSuffix(" µs")
        self._exp_spin.setFixedWidth(80)
        row.addWidget(self._exp_spin)

        row.addWidget(QLabel("Gain"))
        self._gain_slider = QSlider(Qt.Orientation.Horizontal)
        self._gain_slider.setRange(0, 480)
        self._gain_slider.setMinimumWidth(30)
        row.addWidget(self._gain_slider, 1)
        self._gain_spin = QDoubleSpinBox()
        self._gain_spin.setDecimals(1)
        self._gain_spin.setRange(0, 48.0)
        self._gain_spin.setSuffix(" dB")
        self._gain_spin.setFixedWidth(65)
        row.addWidget(self._gain_spin)

        layout.addLayout(row)

        self._exp_slider.valueChanged.connect(self._on_exp_slider)
        self._exp_spin.valueChanged.connect(self._on_exp_spin)
        self._gain_slider.valueChanged.connect(self._on_gain_slider)
        self._gain_spin.valueChanged.connect(self._on_gain_spin)

    def _build_format_trigger_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(4)

        row.addWidget(QLabel("Format"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.setMinimumWidth(60)
        self._fmt_combo.currentTextChanged.connect(self._on_fmt)
        row.addWidget(self._fmt_combo, 1)

        row.addWidget(QLabel("Trigger"))
        self._trigger_combo = QComboBox()
        self._trigger_combo.addItems(["Freerun", "Software"])
        self._trigger_combo.setMinimumWidth(60)
        self._trigger_combo.currentTextChanged.connect(self._on_trigger)
        row.addWidget(self._trigger_combo, 1)

        layout.addLayout(row)

    def _build_roi_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(3)
        row.addWidget(QLabel("ROI"))
        self._roi_spins: dict[str, QSpinBox] = {}
        for label in ("X", "Y", "W", "H"):
            lbl = QLabel(label)
            lbl.setFixedWidth(10)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
            sb = QSpinBox()
            sb.setRange(0, 9999)
            sb.setFixedWidth(48)
            sb.valueChanged.connect(self._on_roi)
            self._roi_spins[label] = sb
            row.addWidget(sb)
        btn = QPushButton("Full")
        btn.setFixedWidth(34)
        btn.setStyleSheet("QPushButton { font-size: 10px; padding: 1px 2px; min-height: 16px; }")
        btn.clicked.connect(self._reset_roi)
        row.addWidget(btn)
        layout.addLayout(row)

    def _build_options_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        self._ae_check = QCheckBox("Auto-Exp")
        self._ae_check.toggled.connect(self.auto_exposure_toggled.emit)
        row.addWidget(self._ae_check)

        load_btn = QPushButton("Flat-Field")
        load_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 1px 4px; min-height: 16px; }")
        load_btn.clicked.connect(self._load_flat_field)
        row.addWidget(load_btn)

        self._ff_status = QLabel("")
        self._ff_status.setStyleSheet("color: #666666; font-size: 10px;")
        row.addWidget(self._ff_status, 1)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 1px 4px; min-height: 16px; }")
        clear_btn.clicked.connect(self._clear_flat_field)
        row.addWidget(clear_btn)
        layout.addLayout(row)

    # --- signal handlers -------------------------------------------------------

    def _set_dot_color(self, connected: bool) -> None:
        color = "#44cc44" if connected else "#ff4444"
        self._conn_dot.setStyleSheet(f"color: {color}; font-size: 14px;")

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

    def _on_gain_slider(self, val: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._gain_spin.setValue(val / 10.0)
        self._updating = False
        self.gain_changed.emit(val / 10.0)

    def _on_gain_spin(self, val: float) -> None:
        if self._updating:
            return
        self._updating = True
        self._gain_slider.setValue(int(val * 10))
        self._updating = False
        self.gain_changed.emit(val)

    def _on_fmt(self, text: str) -> None:
        if not self._updating and text:
            self.pixel_format_changed.emit(text)

    def _on_trigger(self, text: str) -> None:
        if not self._updating:
            self.trigger_mode_changed.emit(text)

    def _on_roi(self) -> None:
        if self._updating:
            return
        self.roi_changed.emit(
            self._roi_spins["X"].value(), self._roi_spins["Y"].value(),
            self._roi_spins["W"].value(), self._roi_spins["H"].value(),
        )

    def _reset_roi(self) -> None:
        self._updating = True
        for sb in self._roi_spins.values():
            sb.setValue(0)
        self._updating = False
        self.roi_changed.emit(0, 0, 0, 0)

    def _load_flat_field(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Flat-Field Reference", "", "Images (*.tif *.tiff *.png *.npy)")
        if path:
            self._ff_status.setText(Path(path).name)
            self._ff_status.setStyleSheet("color: #44cc44; font-size: 10px;")
            self.flat_field_loaded.emit(path)

    def _clear_flat_field(self) -> None:
        self._ff_status.setText("")
        self._ff_status.setStyleSheet("color: #666666; font-size: 10px;")
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

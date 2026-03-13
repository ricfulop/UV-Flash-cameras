"""Recording quality preset selector widget."""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from flash_camera.core.quality_presets import PRESETS, estimate_storage_per_minute

logger = logging.getLogger(__name__)

STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 12px;
}
QRadioButton {
    spacing: 4px;
    padding: 2px 4px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3a3a3a;
    border-radius: 7px;
    background-color: #2a2a2a;
}
QRadioButton::indicator:checked {
    background-color: #4a90d9;
    border-color: #4a90d9;
}
QComboBox, QDoubleSpinBox {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 2px 4px;
    min-height: 22px;
}
"""

_PRESET_ORDER = ["maximum", "high", "balanced", "fast", "compact", "custom"]


class QualitySelector(QWidget):
    preset_changed = pyqtSignal(str)
    custom_settings_changed = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._locked = False
        self.setStyleSheet(STYLE)
        self._buttons: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)
        self._build_ui()
        self._on_preset_clicked(self._buttons["maximum"])

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        title = QLabel("QUALITY")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #4a90d9;")
        root.addWidget(title)

        top_row = QHBoxLayout()
        for name in _PRESET_ORDER:
            preset = PRESETS[name]
            rb = QRadioButton(name.capitalize())
            rb.setProperty("preset_key", name)
            rb.setToolTip(preset.description)
            self._group.addButton(rb)
            self._buttons[name] = rb
            top_row.addWidget(rb)

        self._rate_label = QLabel("")
        self._rate_label.setStyleSheet("color: #4a90d9; font-weight: bold; padding-left: 8px;")
        top_row.addWidget(self._rate_label)
        top_row.addStretch()
        root.addLayout(top_row)

        self._buttons["maximum"].setChecked(True)
        self._group.buttonClicked.connect(self._on_preset_clicked)

        self._custom_container = QWidget()
        cl = QHBoxLayout(self._custom_container)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(8)

        cl.addWidget(QLabel("Bit Depth"))
        self._bit_depth_combo = QComboBox()
        self._bit_depth_combo.addItems(["Mono8", "Mono12"])
        self._bit_depth_combo.currentTextChanged.connect(self._emit_custom)
        cl.addWidget(self._bit_depth_combo)

        cl.addWidget(QLabel("Max FPS"))
        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 120.0)
        self._fps_spin.setValue(30.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.valueChanged.connect(self._emit_custom)
        cl.addWidget(self._fps_spin)

        cl.addWidget(QLabel("Compression"))
        self._comp_combo = QComboBox()
        self._comp_combo.addItems(["none", "lzw", "zstd"])
        self._comp_combo.currentTextChanged.connect(self._emit_custom)
        cl.addWidget(self._comp_combo)
        cl.addStretch()

        self._custom_container.setVisible(False)
        root.addWidget(self._custom_container)

        self._lock_label = QLabel("🔒 Locked during recording")
        self._lock_label.setStyleSheet("color: #ff4444; font-style: italic;")
        self._lock_label.setVisible(False)
        root.addWidget(self._lock_label)

    def _on_preset_clicked(self, button: QRadioButton) -> None:
        key = button.property("preset_key")
        is_custom = key == "custom"
        self._custom_container.setVisible(is_custom)
        self._update_rate(key)
        self.preset_changed.emit(key)

    def _update_rate(self, preset_key: str) -> None:
        preset = PRESETS.get(preset_key)
        if preset:
            gb_min = estimate_storage_per_minute(preset)
            self._rate_label.setText(f"~{gb_min:.0f} GB/min")

    def _emit_custom(self) -> None:
        settings = {
            "bit_depth": self._bit_depth_combo.currentText(),
            "max_fps": self._fps_spin.value(),
            "tiff_compression": self._comp_combo.currentText(),
        }
        self.custom_settings_changed.emit(settings)

    def get_current_preset(self) -> str:
        for key, rb in self._buttons.items():
            if rb.isChecked():
                return key
        return "maximum"

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._lock_label.setVisible(locked)
        for rb in self._buttons.values():
            rb.setDisabled(locked)
        self._bit_depth_combo.setDisabled(locked)
        self._fps_spin.setDisabled(locked)
        self._comp_combo.setDisabled(locked)

    def get_quality_settings(self) -> dict:
        key = self.get_current_preset()
        if key == "custom":
            return {
                "bit_depth": self._bit_depth_combo.currentText(),
                "max_fps": self._fps_spin.value(),
                "tiff_compression": self._comp_combo.currentText(),
            }
        preset = PRESETS[key]
        return {
            "bit_depth": preset.bit_depth,
            "max_fps": preset.max_fps,
            "tiff_compression": preset.tiff_compression,
        }

    def update_storage_estimate(self, rate_str: str) -> None:
        self._rate_label.setText(rate_str)

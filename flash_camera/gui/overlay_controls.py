"""Overlay toggle controls toolbar."""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QCheckBox, QComboBox, QLabel

logger = logging.getLogger(__name__)

_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 11px;
}
QCheckBox {
    spacing: 4px;
    color: #cccccc;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    border-radius: 2px;
    background-color: #2a2a2a;
}
QCheckBox::indicator:checked {
    background-color: #4a90d9;
    border-color: #4a90d9;
}
QComboBox {
    background-color: #2a2a2a;
    color: #cccccc;
    border: 1px solid #555555;
    border-radius: 2px;
    padding: 2px 18px 2px 6px;
    min-width: 80px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    color: #cccccc;
    selection-background-color: #4a90d9;
}
QLabel {
    color: #888888;
    font-size: 10px;
}
"""


class OverlayControls(QWidget):
    crosshair_toggled = pyqtSignal(bool)
    scale_bar_toggled = pyqtSignal(bool)
    info_toggled = pyqtSignal(bool)
    histogram_toggled = pyqtSignal(bool)
    colormap_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLE)
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        self._cb_crosshair = QCheckBox("Crosshair")
        self._cb_crosshair.setChecked(True)
        self._cb_crosshair.toggled.connect(self.crosshair_toggled)

        self._cb_scale_bar = QCheckBox("Scale Bar")
        self._cb_scale_bar.setChecked(False)
        self._cb_scale_bar.toggled.connect(self.scale_bar_toggled)

        self._cb_info = QCheckBox("Info")
        self._cb_info.setChecked(True)
        self._cb_info.toggled.connect(self.info_toggled)

        self._cb_histogram = QCheckBox("Histogram")
        self._cb_histogram.setChecked(True)
        self._cb_histogram.toggled.connect(self.histogram_toggled)

        self._lbl_cmap = QLabel("Colormap:")
        self._combo_cmap = QComboBox()
        self._combo_cmap.addItems(["gray", "inferno", "viridis", "plasma"])
        self._combo_cmap.currentTextChanged.connect(self.colormap_changed)

        layout.addWidget(self._cb_crosshair)
        layout.addWidget(self._cb_scale_bar)
        layout.addWidget(self._cb_info)
        layout.addWidget(self._cb_histogram)
        layout.addWidget(self._lbl_cmap)
        layout.addWidget(self._combo_cmap)
        layout.addStretch()

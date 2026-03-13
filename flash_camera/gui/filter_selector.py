"""Basler filter logging widget."""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QRadioButton,
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
QRadioButton {
    spacing: 6px;
    padding: 4px 6px;
    border-radius: 3px;
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
"""

_FILTERS = [
    ("no_filter", "No Filter", None),
    ("uv_shortpass", "UV Shortpass (≤400nm)", "#9b59b6"),
    ("810nm_ArI", "810nm Ar I", "#e74c3c"),
    ("780nm", "780nm Ar II/OH", "#8b0000"),
]


class FilterSelector(QWidget):
    filter_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        self._buttons: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        title = QLabel("FILTER")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #4a90d9;")
        root.addWidget(title)

        for key, label, color in _FILTERS:
            row = QHBoxLayout()
            row.setSpacing(6)

            if color:
                dot = QLabel("●")
                dot.setFixedWidth(16)
                dot.setStyleSheet(f"color: {color}; font-size: 16px;")
                row.addWidget(dot)

            rb = QRadioButton(label)
            rb.setProperty("filter_key", key)
            self._group.addButton(rb)
            self._buttons[key] = rb
            row.addWidget(rb, 1)
            root.addLayout(row)

        self._buttons["no_filter"].setChecked(True)
        self._group.buttonClicked.connect(self._on_clicked)
        root.addStretch()

    def _on_clicked(self, button: QRadioButton) -> None:
        key = button.property("filter_key")
        self._update_highlight()
        self.filter_changed.emit(key)

    def _update_highlight(self) -> None:
        for key, rb in self._buttons.items():
            if rb.isChecked():
                rb.setStyleSheet("background-color: #2a3a4a; border-radius: 3px;")
            else:
                rb.setStyleSheet("")

    def get_current_filter(self) -> str:
        for key, rb in self._buttons.items():
            if rb.isChecked():
                return key
        return "no_filter"

    def set_filter(self, key: str) -> None:
        rb = self._buttons.get(key)
        if rb:
            rb.setChecked(True)
            self._update_highlight()
        else:
            logger.warning("Unknown filter key: %s", key)

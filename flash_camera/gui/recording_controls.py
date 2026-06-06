"""Start/stop recording widget with session metadata and encoding progress."""

import logging
from datetime import datetime

from PyQt6.QtCore import (
    QPropertyAnimation,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
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
QLineEdit, QPlainTextEdit {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 4px;
}
QPushButton {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 6px 16px;
    min-height: 24px;
}
QPushButton:hover { background-color: #3a3a3a; }
QPushButton:disabled { color: #555555; }
QProgressBar {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    text-align: center;
    min-height: 16px;
}
QProgressBar::chunk {
    background-color: #4a90d9;
    border-radius: 2px;
}
"""


class RecordingControls(QWidget):
    record_start_requested = pyqtSignal()
    record_stop_requested = pyqtSignal()
    session_name_changed = pyqtSignal(str)
    operator_changed = pyqtSignal(str)
    notes_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._recording = False
        self._encoding_bars: dict[str, QProgressBar] = {}
        self._pulse_timer: QTimer | None = None
        self._pulse_on = False
        self.setStyleSheet(STYLE)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self._build_transport(root)
        self._build_metadata(root)
        self._build_frame_counters(root)
        self._build_encoding_section(root)
        self._build_warnings(root)
        root.addStretch()

    # --- transport controls ---------------------------------------------------

    def _build_transport(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()

        self._rec_btn = QPushButton("⏺  Record")
        self._rec_btn.setStyleSheet(
            "QPushButton { background-color: #aa2222; color: white; font-weight: bold; "
            "border-radius: 6px; padding: 8px 20px; font-size: 14px; }"
            "QPushButton:hover { background-color: #cc3333; }"
            "QPushButton:disabled { background-color: #3a2020; color: #555555; }"
        )
        self._rec_btn.clicked.connect(self._on_record)
        row.addWidget(self._rec_btn)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; font-weight: bold; "
            "border-radius: 6px; padding: 8px 20px; font-size: 14px; }"
            "QPushButton:hover { background-color: #3a3a3a; }"
            "QPushButton:disabled { color: #555555; }"
        )
        self._stop_btn.clicked.connect(self._on_stop)
        row.addWidget(self._stop_btn)

        self._timer_label = QLabel("00:00.0")
        self._timer_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; font-family: monospace; "
            "color: #cccccc; padding-left: 12px;"
        )
        row.addWidget(self._timer_label)
        row.addStretch()
        layout.addLayout(row)

    def _on_record(self) -> None:
        self.record_start_requested.emit()

    def _on_stop(self) -> None:
        self.record_stop_requested.emit()

    # --- metadata -------------------------------------------------------------

    def _build_metadata(self, layout: QVBoxLayout) -> None:
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Session"))
        self._session_edit = QLineEdit(self._default_session_name())
        self._session_edit.textChanged.connect(self.session_name_changed.emit)
        row1.addWidget(self._session_edit, 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Operator"))
        self._operator_edit = QLineEdit()
        self._operator_edit.setPlaceholderText("Name")
        self._operator_edit.textChanged.connect(self.operator_changed.emit)
        row2.addWidget(self._operator_edit, 1)
        layout.addLayout(row2)

        layout.addWidget(QLabel("Notes"))
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setMaximumHeight(60)
        self._notes_edit.setPlaceholderText("Session notes (can be pre-filled from OES)")
        self._notes_edit.textChanged.connect(lambda: self.notes_changed.emit(self._notes_edit.toPlainText()))
        layout.addWidget(self._notes_edit)

    @staticmethod
    def _default_session_name() -> str:
        return datetime.now().strftime("session_%Y%m%d_%H%M%S")

    # --- frame counters -------------------------------------------------------

    def _build_frame_counters(self, layout: QVBoxLayout) -> None:
        self._frame_counter_row = QHBoxLayout()
        self._frame_counter_labels: dict[str, QLabel] = {}
        self._frame_counter_row.addStretch()
        layout.addLayout(self._frame_counter_row)

    # --- encoding progress ----------------------------------------------------

    def _build_encoding_section(self, layout: QVBoxLayout) -> None:
        self._enc_title = QLabel("H.265 Encoding")
        self._enc_title.setStyleSheet("font-weight: bold; color: #4a90d9; margin-top: 4px;")
        self._enc_title.setVisible(False)
        layout.addWidget(self._enc_title)

        self._enc_area = QScrollArea()
        self._enc_area.setWidgetResizable(True)
        self._enc_area.setMaximumHeight(100)
        self._enc_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._enc_area.setVisible(False)
        self._enc_container = QWidget()
        self._enc_layout = QVBoxLayout(self._enc_container)
        self._enc_layout.setContentsMargins(0, 0, 0, 0)
        self._enc_layout.setSpacing(2)
        self._enc_area.setWidget(self._enc_container)
        layout.addWidget(self._enc_area)

    # --- warnings -------------------------------------------------------------

    def _build_warnings(self, layout: QVBoxLayout) -> None:
        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

    # --- pulse animation ------------------------------------------------------

    def _start_pulse(self) -> None:
        if self._pulse_timer is not None:
            return
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)
        self._pulse_timer.start(600)

    def _stop_pulse(self) -> None:
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None
        self._pulse_on = False
        self._rec_btn.setStyleSheet(
            "QPushButton { background-color: #aa2222; color: white; font-weight: bold; "
            "border-radius: 6px; padding: 8px 20px; font-size: 14px; }"
            "QPushButton:hover { background-color: #cc3333; }"
        )

    def _toggle_pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        bg = "#ff4444" if self._pulse_on else "#aa2222"
        self._rec_btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: white; font-weight: bold; "
            f"border-radius: 6px; padding: 8px 20px; font-size: 14px; }}"
        )

    # --- public API -----------------------------------------------------------

    def set_recording(self, active: bool) -> None:
        self._recording = active
        self._rec_btn.setDisabled(active)
        self._stop_btn.setEnabled(active)
        self._session_edit.setReadOnly(active)
        if active:
            self._timer_label.setStyleSheet(
                "font-size: 22px; font-weight: bold; font-family: monospace; "
                "color: #ff4444; padding-left: 12px;"
            )
            self._start_pulse()
        else:
            self._timer_label.setStyleSheet(
                "font-size: 22px; font-weight: bold; font-family: monospace; "
                "color: #cccccc; padding-left: 12px;"
            )
            self._stop_pulse()

    def set_elapsed_time(self, seconds: float) -> None:
        mins = int(seconds) // 60
        secs = seconds - mins * 60
        self._timer_label.setText(f"{mins:02d}:{secs:04.1f}")

    def set_frame_counts(self, counts: dict) -> None:
        for cam_id, count in counts.items():
            if cam_id not in self._frame_counter_labels:
                lbl = QLabel(f"{cam_id}: {count} frames")
                lbl.setStyleSheet("color: #4a90d9;")
                self._frame_counter_labels[cam_id] = lbl
                idx = self._frame_counter_row.count() - 1
                self._frame_counter_row.insertWidget(max(0, idx), lbl)
            else:
                self._frame_counter_labels[cam_id].setText(f"{cam_id}: {count} frames")

    def add_encoding_job(self, session_id: str) -> QProgressBar:
        self._enc_title.setVisible(True)
        self._enc_area.setVisible(True)
        row = QHBoxLayout()
        label = QLabel(session_id)
        label.setStyleSheet("font-size: 11px;")
        label.setFixedWidth(140)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        row.addWidget(label)
        row.addWidget(bar, 1)
        self._enc_layout.addLayout(row)
        self._encoding_bars[session_id] = bar
        return bar

    def update_encoding_progress(self, session_id: str, progress: float) -> None:
        bar = self._encoding_bars.get(session_id)
        if bar:
            bar.setValue(int(progress))
            if progress >= 100:
                bar.setStyleSheet("QProgressBar::chunk { background-color: #44cc44; }")

    def show_warning(self, message: str, level: str = "warning") -> None:
        colors = {"info": "#4a90d9", "warning": "#ffaa00", "error": "#ff4444"}
        color = colors.get(level, "#ffaa00")
        self._warning_label.setStyleSheet(
            f"color: {color}; background-color: #2a2020; "
            f"border: 1px solid {color}; border-radius: 3px; padding: 4px;"
        )
        self._warning_label.setText(message)
        self._warning_label.setVisible(True)

    def clear_warnings(self) -> None:
        self._warning_label.setVisible(False)
        self._warning_label.setText("")

    def get_session_name(self) -> str:
        return self._session_edit.text()

    def get_operator(self) -> str:
        return self._operator_edit.text()

    def get_notes(self) -> str:
        return self._notes_edit.toPlainText()

    def set_notes(self, text: str) -> None:
        self._notes_edit.setPlainText(text)

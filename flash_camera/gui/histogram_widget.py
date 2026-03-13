"""Live intensity histogram widget."""

import logging

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QWidget

from flash_camera.utils.image_utils import compute_histogram

logger = logging.getLogger(__name__)

_DISPLAY_BINS = 256


class HistogramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(90)
        self.setMinimumWidth(200)

        self._counts: np.ndarray | None = None
        self._bin_edges: np.ndarray | None = None
        self._log_scale = False
        self._min_val: float = 0.0
        self._max_val: float = 0.0
        self._mean_val: float = 0.0
        self._total_bins: int = 256

        self._apply_dark_style()

    def _apply_dark_style(self):
        self.setStyleSheet("background-color: #2a2a2a;")

    def update_histogram(self, frame: np.ndarray):
        if frame.dtype == np.uint16:
            self._total_bins = 4096
        else:
            self._total_bins = 256

        counts, bin_edges = compute_histogram(frame, bins=self._total_bins)
        self._bin_edges = bin_edges

        if self._total_bins > _DISPLAY_BINS:
            ratio = self._total_bins // _DISPLAY_BINS
            trimmed = counts[: ratio * _DISPLAY_BINS]
            self._counts = trimmed.reshape(_DISPLAY_BINS, ratio).sum(axis=1)
        else:
            self._counts = counts.copy()

        flat = frame.ravel()
        self._min_val = float(np.min(flat))
        self._max_val = float(np.max(flat))
        self._mean_val = float(np.mean(flat))

        self.update()

    def set_log_scale(self, enabled: bool):
        self._log_scale = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#2a2a2a"))

        if self._counts is None or len(self._counts) == 0:
            painter.end()
            return

        w = self.width()
        h = self.height()
        margin_top = 2
        margin_bottom = 16
        draw_h = h - margin_top - margin_bottom

        counts = self._counts.copy()
        if self._log_scale:
            counts = np.log1p(counts)
        peak = counts.max()
        if peak <= 0:
            painter.end()
            return

        num_bars = len(counts)
        bar_w = w / num_bars

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#aaaaaa")))

        for i in range(num_bars):
            bar_h = int(counts[i] / peak * draw_h)
            if bar_h < 1:
                continue
            x = int(i * bar_w)
            bw = max(1, int(bar_w))
            painter.drawRect(x, margin_top + draw_h - bar_h, bw, bar_h)

        max_edge = float(self._bin_edges[-1]) if self._bin_edges is not None else 255.0
        max_edge = max(max_edge, 1.0)

        def val_to_x(v: float) -> int:
            return int(v / max_edge * w)

        pen_min = QPen(QColor(0, 180, 255), 1)
        pen_mean = QPen(QColor(255, 255, 0), 1)
        pen_max = QPen(QColor(255, 80, 80), 1)

        for val, pen in [
            (self._min_val, pen_min),
            (self._mean_val, pen_mean),
            (self._max_val, pen_max),
        ]:
            x = val_to_x(val)
            painter.setPen(pen)
            painter.drawLine(x, margin_top, x, margin_top + draw_h)

        font = QFont("monospace", 7)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#cccccc")))
        stats = f"min:{self._min_val:.0f}  mean:{self._mean_val:.0f}  max:{self._max_val:.0f}"
        painter.drawText(4, h - 3, stats)

        painter.end()

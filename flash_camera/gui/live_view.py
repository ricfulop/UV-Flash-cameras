"""Live camera view widget with zoom, pan, and overlay rendering."""

import logging
import time

import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import QImage, QPainter, QPen, QColor, QFont, QBrush, QWheelEvent
from PyQt6.QtWidgets import QWidget

from flash_camera.utils.image_utils import (
    mono12_to_8bit,
    apply_colormap,
    calculate_scale_bar,
)

logger = logging.getLogger(__name__)


class LiveViewWidget(QWidget):
    roi_selected = pyqtSignal(int, int, int, int)

    _MIN_ZOOM = 0.1
    _MAX_ZOOM = 20.0
    _REFRESH_INTERVAL_MS = 67  # ~15 fps

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._frame: np.ndarray | None = None
        self._display_image: QImage | None = None
        self._colormap: str = "gray"

        self._zoom: float = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._panning = False
        self._pan_start = QPoint()
        self._pan_offset_start = QPointF()

        self._roi_drawing = False
        self._roi_start = QPoint()
        self._roi_end = QPoint()

        self._show_crosshair = True
        self._show_scale_bar = False
        self._show_info = True
        self._fov_mm: tuple[float, float] | None = None

        self._recording = False
        self._rec_blink = True
        self._disconnected = False
        self._filter_label: str = ""

        self._fps: float = 0.0
        self._exposure_us: float = 0.0
        self._gain_db: float = 0.0
        self._pixel_format: str = ""
        self._frame_counter: int = 0
        self._last_frame_time: float = 0.0
        self._fps_samples: list[float] = []

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(500)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.update)
        self._refresh_timer.start(self._REFRESH_INTERVAL_MS)

        self._dirty = False

        self._apply_dark_style()

    def _apply_dark_style(self):
        self.setStyleSheet("background-color: #1e1e1e;")

    # ── Public API ──────────────────────────────────────────────

    def update_frame(self, frame: np.ndarray, metadata: dict):
        now = time.monotonic()
        if self._last_frame_time > 0:
            dt = now - self._last_frame_time
            if dt > 0:
                self._fps_samples.append(1.0 / dt)
                if len(self._fps_samples) > 30:
                    self._fps_samples.pop(0)
                self._fps = sum(self._fps_samples) / len(self._fps_samples)
        self._last_frame_time = now

        self._exposure_us = metadata.get("exposure_us", self._exposure_us)
        self._gain_db = metadata.get("gain_db", self._gain_db)
        self._pixel_format = metadata.get("pixel_format", self._pixel_format)
        self._frame_counter = metadata.get("frame_counter", self._frame_counter + 1)

        self._frame = frame
        self._rebuild_display_image()
        self._dirty = True

    def set_colormap(self, name: str):
        self._colormap = name
        if self._frame is not None:
            self._rebuild_display_image()
            self._dirty = True

    def set_crosshair_visible(self, visible: bool):
        self._show_crosshair = visible
        self._dirty = True

    def set_scale_bar_visible(self, visible: bool):
        self._show_scale_bar = visible
        self._dirty = True

    def set_fov_mm(self, fov: tuple[float, float]):
        self._fov_mm = fov
        self._dirty = True

    def set_recording(self, recording: bool):
        self._recording = recording
        self._dirty = True

    def set_disconnected(self, disconnected: bool):
        self._disconnected = disconnected
        self._dirty = True

    def set_filter_label(self, label: str):
        self._filter_label = label
        self._dirty = True

    def set_info_visible(self, visible: bool):
        self._show_info = visible
        self._dirty = True

    def reset_zoom(self):
        self._zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._dirty = True

    # ── Internal ────────────────────────────────────────────────

    def _rebuild_display_image(self):
        frame = self._frame
        if frame is None:
            return
        if frame.dtype == np.uint16:
            frame = mono12_to_8bit(frame)
        elif frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        bgr = apply_colormap(frame, self._colormap)
        rgb = bgr[:, :, ::-1].copy()

        h, w, ch = rgb.shape
        self._display_image = QImage(
            rgb.data, w, h, w * ch, QImage.Format.Format_RGB888
        )
        self._display_image._np_ref = rgb

    def _toggle_blink(self):
        self._rec_blink = not self._rec_blink
        if self._recording:
            self._dirty = True

    def _image_rect(self) -> QRect:
        if self._display_image is None:
            return QRect()
        iw = self._display_image.width()
        ih = self._display_image.height()
        ww = self.width()
        wh = self.height()

        scale = min(ww / iw, wh / ih) * self._zoom
        sw = int(iw * scale)
        sh = int(ih * scale)
        x = int((ww - sw) / 2 + self._pan_offset.x())
        y = int((wh - sh) / 2 + self._pan_offset.y())
        return QRect(x, y, sw, sh)

    def _widget_to_image(self, pos: QPoint) -> QPoint | None:
        rect = self._image_rect()
        if rect.width() <= 0 or rect.height() <= 0 or self._display_image is None:
            return None
        ix = int((pos.x() - rect.x()) / rect.width() * self._display_image.width())
        iy = int((pos.y() - rect.y()) / rect.height() * self._display_image.height())
        return QPoint(ix, iy)

    # ── Paint ───────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if self._display_image is not None:
            rect = self._image_rect()
            painter.drawImage(rect, self._display_image)
            self._draw_overlays(painter, rect)

        if self._disconnected:
            self._draw_disconnected(painter)

        painter.end()
        self._dirty = False

    def _draw_overlays(self, painter: QPainter, rect: QRect):
        if self._show_crosshair:
            self._draw_crosshair(painter, rect)
        if self._show_scale_bar and self._fov_mm and self._display_image:
            self._draw_scale_bar(painter, rect)
        if self._show_info:
            self._draw_info(painter)
        if self._filter_label:
            self._draw_filter_label(painter)
        if self._recording:
            self._draw_recording(painter)
        if self._roi_drawing:
            self._draw_roi_rect(painter)

    def _draw_crosshair(self, painter: QPainter, rect: QRect):
        cx = rect.x() + rect.width() // 2
        cy = rect.y() + rect.height() // 2
        arm = min(rect.width(), rect.height()) // 8
        pen = QPen(QColor(0, 255, 0, 180), 1)
        painter.setPen(pen)
        painter.drawLine(cx - arm, cy, cx + arm, cy)
        painter.drawLine(cx, cy - arm, cx, cy + arm)

    def _draw_scale_bar(self, painter: QPainter, rect: QRect):
        pixel_length, label = calculate_scale_bar(
            self._fov_mm, self._display_image.width()
        )
        scale_x = rect.width() / self._display_image.width()
        bar_px = int(pixel_length * scale_x)
        bar_h = 4
        margin = 10
        x = rect.x() + margin
        y = rect.y() + rect.height() - margin - bar_h

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRect(x, y, bar_px, bar_h)

        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont("monospace", 8)
        painter.setFont(font)
        painter.drawText(x, y - 3, label)

    def _draw_info(self, painter: QPainter):
        lines = [
            f"FPS: {self._fps:.1f}",
            f"Exp: {self._exposure_us:.0f} µs",
            f"Gain: {self._gain_db:.1f} dB",
            f"Format: {self._pixel_format}",
            f"Frame: {self._frame_counter}",
        ]
        font = QFont("monospace", 9)
        painter.setFont(font)
        x, y = 8, 16
        painter.setPen(QPen(QColor(0, 0, 0, 160)))
        bg = QColor(0, 0, 0, 120)
        fm = painter.fontMetrics()
        line_h = fm.height() + 2
        max_w = max(fm.horizontalAdvance(l) for l in lines)
        painter.fillRect(x - 2, y - fm.ascent() - 1, max_w + 6, line_h * len(lines) + 2, bg)

        painter.setPen(QPen(QColor("#cccccc")))
        for line in lines:
            painter.drawText(x, y, line)
            y += line_h

    def _draw_filter_label(self, painter: QPainter):
        font = QFont("monospace", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(self._filter_label)
        pad = 6
        rx = self.width() - tw - pad * 2 - 4
        ry = 4
        painter.fillRect(rx, ry, tw + pad * 2, fm.height() + pad, QColor(100, 50, 180, 200))
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(rx + pad, ry + fm.ascent() + pad // 2, self._filter_label)

    def _draw_recording(self, painter: QPainter):
        if self._rec_blink:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 0, 0)))
            painter.drawEllipse(self.width() - 28, 8, 12, 12)
            painter.setPen(QPen(QColor(255, 0, 0)))
            font = QFont("monospace", 9, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(self.width() - 56, 18, "REC")

    def _draw_disconnected(self, painter: QPainter):
        overlay = QColor(180, 0, 0, 120)
        painter.fillRect(self.rect(), overlay)
        font = QFont("monospace", 20, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "DISCONNECTED")

    def _draw_roi_rect(self, painter: QPainter):
        pen = QPen(QColor(255, 255, 0, 200), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(255, 255, 0, 30)))
        painter.drawRect(QRect(self._roi_start, self._roi_end).normalized())

    # ── Mouse ───────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        self._zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, new_zoom))
        self._dirty = True
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self._pan_offset_start = QPointF(self._pan_offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._roi_drawing = True
            self._roi_start = event.pos()
            self._roi_end = event.pos()

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_offset = self._pan_offset_start + QPointF(delta)
            self._dirty = True
            self.update()
        elif self._roi_drawing:
            self._roi_end = event.pos()
            self._dirty = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self._roi_drawing:
            self._roi_drawing = False
            p1 = self._widget_to_image(self._roi_start)
            p2 = self._widget_to_image(self._roi_end)
            if p1 is not None and p2 is not None:
                x1, y1 = min(p1.x(), p2.x()), min(p1.y(), p2.y())
                x2, y2 = max(p1.x(), p2.x()), max(p1.y(), p2.y())
                if abs(x2 - x1) > 2 and abs(y2 - y1) > 2:
                    self.roi_selected.emit(x1, y1, x2, y2)
            self.update()

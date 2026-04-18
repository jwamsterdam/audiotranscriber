"""Small painted widgets used by the floating strip."""

from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from audiotranscriber.state import RecorderStatus


GREEN = QColor("#58cf5f")
RED = QColor("#ff3f3f")
YELLOW = QColor("#f3c12f")
INK = QColor("#f7f8f8")


class IconKind(str, Enum):
    STOP = "stop"
    PAUSE = "pause"
    EXPAND = "expand"
    COLLAPSE = "collapse"


class PrimaryRecordButton(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = RecorderStatus.IDLE
        self._pulse = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(90)
        self._pulse_timer.timeout.connect(self._advance_pulse)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCheckable(False)
        self.setFixedSize(56, 56)

    def set_status(self, status: RecorderStatus) -> None:
        self._status = status
        if status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING}:
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._pulse = 0.0
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(56, 56)

    def _advance_pulse(self) -> None:
        self._pulse = (self._pulse + 0.08) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = YELLOW if self._status in {RecorderStatus.PROCESSING, RecorderStatus.PAUSED} else RED
        center = QPointF(self.width() / 2, self.height() / 2)

        if self._status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING}:
            pulse_radius = 15 + self._pulse * 15
            pulse_alpha = int(30 * (1.0 - self._pulse))
            pulse = QColor(color)
            pulse.setAlpha(max(0, pulse_alpha))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(pulse, 3))
            painter.drawEllipse(center, pulse_radius, pulse_radius)

        halo = QColor(color)
        halo.setAlpha(34 if self._status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING} else 22)
        if self.isDown():
            halo.setAlpha(52)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, 22, 22)

        core = QColor(color)
        core.setAlpha(245)
        painter.setBrush(core)
        painter.drawEllipse(center, 11, 11)


class WaveformWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = RecorderStatus.IDLE
        self._phase = 0.0
        self._level = 0.0
        self._compact = False
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._advance)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        if compact:
            self.setFixedWidth(72)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setMinimumWidth(220)
            self.setMaximumWidth(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.updateGeometry()
        self.update()

    def set_status(self, status: RecorderStatus) -> None:
        self._status = status
        if status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING}:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def _advance(self) -> None:
        self._phase += 0.45
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        center_y = self.height() / 2
        gap = 7 if self._compact else 8
        bar_width = 4
        start_x = 2
        bars = 7 if self._compact else max(16, min(44, int((width - start_x) / gap)))
        if self._compact:
            start_x = max(2, (width - ((bars - 1) * gap + bar_width)) / 2)

        for index in range(bars):
            x = start_x + index * gap
            if x > width - bar_width:
                break

            seed = math.sin(index * 1.7) * 0.5 + math.sin(index * 0.43) * 0.5
            motion = math.sin(self._phase + index * 0.62)
            level_boost = 0.22 + self._level * 1.0
            amplitude = 10 if self._compact else 9
            height = 6 + abs(seed + motion * 0.45) * amplitude * level_boost

            color = self._bar_color(index, bars)
            if self._status in {RecorderStatus.IDLE, RecorderStatus.PAUSED}:
                color.setAlpha(120 if index % 2 else 80)
                height = 8 + abs(seed) * 12

            rect = QRectF(x, center_y - height / 2, bar_width, height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 2, 2)

    def _bar_color(self, index: int, bars: int) -> QColor:
        if self._status == RecorderStatus.RECORDING:
            midpoint = bars * 0.46
            if index < midpoint:
                return QColor("#61d85e")
            if index < bars * 0.66:
                return QColor("#e1d83b")
            if index < bars * 0.88:
                return QColor("#ff4545")
            return QColor("#737a7f")

        if self._status == RecorderStatus.PROCESSING:
            if index < bars * 0.58:
                return QColor("#f3c12f")
            if index < bars * 0.78:
                return QColor("#ff8644")
            return QColor("#686f75")

        return QColor("#7b8389")


class StripIconButton(QAbstractButton):
    def __init__(self, kind: IconKind, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCheckable(False)
        self.setFixedSize(48, 48)

    def set_kind(self, kind: IconKind) -> None:
        self._kind = kind
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(48, 48)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isDown():
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect().adjusted(6, 6, -6, -6), 8, 8)

        icon_color = QColor("#c8cdd0") if self._kind in {IconKind.EXPAND, IconKind.COLLAPSE} else INK
        icon_width = 3 if self._kind in {IconKind.EXPAND, IconKind.COLLAPSE} else 5
        pen = QPen(icon_color, icon_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(INK)

        if self._kind == IconKind.STOP:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(18, 17, 16, 16), 3, 3)
        elif self._kind == IconKind.PAUSE:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(18, 15, 5, 21), 2, 2)
            painter.drawRoundedRect(QRectF(30, 15, 5, 21), 2, 2)
        elif self._kind in {IconKind.EXPAND, IconKind.COLLAPSE}:
            path = QPainterPath()
            if self._kind == IconKind.EXPAND:
                path.moveTo(16, 20)
                path.lineTo(24, 29)
                path.lineTo(33, 20)
            else:
                path.moveTo(16, 29)
                path.lineTo(24, 20)
                path.lineTo(33, 29)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

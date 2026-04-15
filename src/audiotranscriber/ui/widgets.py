"""Small painted widgets used by the floating strip."""

from __future__ import annotations

import math
from enum import Enum

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from audiotranscriber.state import RecorderStatus


GREEN = QColor("#58cf5f")
RED = QColor("#ff3f3f")
YELLOW = QColor("#f3c12f")
INK = QColor("#f7f8f8")
MUTED = QColor("#6b7379")


class IconKind(str, Enum):
    STOP = "stop"
    PAUSE = "pause"
    RECORD = "record"
    EXPAND = "expand"
    COLLAPSE = "collapse"


class StatusDot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = RecorderStatus.IDLE
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(520)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self.setFixedSize(48, 48)

    def set_status(self, status: RecorderStatus) -> None:
        self._status = status
        self._blink_on = True
        if status == RecorderStatus.RECORDING:
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
        self.update()

    def _toggle_blink(self) -> None:
        self._blink_on = not self._blink_on
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._status == RecorderStatus.RECORDING:
            color = RED
            glow_alpha = 95 if self._blink_on else 24
            core_alpha = 255 if self._blink_on else 130
        elif self._status == RecorderStatus.PROCESSING:
            color = YELLOW
            glow_alpha = 34
            core_alpha = 255
        elif self._status == RecorderStatus.PAUSED:
            color = YELLOW
            glow_alpha = 20
            core_alpha = 210
        else:
            color = GREEN
            glow_alpha = 24
            core_alpha = 255

        glow = QColor(color)
        glow.setAlpha(glow_alpha)
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.drawEllipse(center, 20, 20)

        core = QColor(color)
        core.setAlpha(core_alpha)
        painter.setBrush(core)
        painter.drawEllipse(center, 10, 10)


class WaveformWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = RecorderStatus.IDLE
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._advance)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)

    def set_status(self, status: RecorderStatus) -> None:
        self._status = status
        if status in {RecorderStatus.RECORDING, RecorderStatus.PROCESSING}:
            self._timer.start()
        else:
            self._timer.stop()
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
        gap = 8
        bar_width = 4
        start_x = 2
        bars = max(16, min(44, int((width - start_x) / gap)))

        for index in range(bars):
            x = start_x + index * gap
            if x > width - bar_width:
                break

            seed = math.sin(index * 1.7) * 0.5 + math.sin(index * 0.43) * 0.5
            motion = math.sin(self._phase + index * 0.62)
            height = 8 + abs(seed + motion * 0.55) * 17

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

        if self._kind == IconKind.RECORD:
            center = QPointF(self.width() / 2, self.height() / 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 63, 63, 32))
            painter.drawEllipse(center, 18, 18)
            painter.setBrush(RED)
            painter.drawEllipse(center, 10, 10)
            return

        pen = QPen(INK, 5)
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


def animate_height(widget: QWidget, target_height: int, duration_ms: int = 180) -> QPropertyAnimation:
    animation = QPropertyAnimation(widget, b"maximumHeight", widget)
    animation.setDuration(duration_ms)
    animation.setStartValue(widget.maximumHeight())
    animation.setEndValue(target_height)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.start()
    return animation

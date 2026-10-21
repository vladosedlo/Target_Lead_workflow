"""Виджеты-индикаторы СВЯЗЬ и В ЗОНЕ ПУСКА."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QTimer, Property, QPropertyAnimation
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QFont, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel


class StatusLamp(QWidget):

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._on = False
        self._color_on = QColor(60, 220, 90)
        self._color_off = QColor(220, 60, 60)
        self._brightness = 1.0
        self.setMinimumSize(240, 110)
        # Лёгкая «пульсация»
        self._pulse = QTimer(self); self._pulse.setInterval(40)
        self._pulse.timeout.connect(self._tick); self._pulse.start()
        self._t = 0.0

    def sizeHint(self) -> QSize:
        return QSize(320, 130)

    def set_state(self, ok: bool, color_on: QColor = None, color_off: QColor = None):
        if color_on:  self._color_on = color_on
        if color_off: self._color_off = color_off
        self._on = ok
        self.update()

    def _tick(self):
        import math
        self._t += 0.05
        self._brightness = 0.85 + 0.15 * (0.5 + 0.5 * math.sin(self._t * 3))
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # фон-плашка
        p.setPen(QPen(QColor(44,58,74), 1))
        p.setBrush(QColor(27,35,44))
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1), 12, 12)
        # лампа — крупнее
        d = min(h - 28, 80)
        cx, cy = 22 + d/2, h/2
        base = self._color_on if self._on else self._color_off
        col = QColor(base)
        col.setRgbF(min(1, col.redF()*self._brightness),
                    min(1, col.greenF()*self._brightness),
                    min(1, col.blueF()*self._brightness))
        grad = QRadialGradient(cx-d*0.15, cy-d*0.15, d*0.7)
        grad.setColorAt(0, col.lighter(160))
        grad.setColorAt(1, col.darker(180))
        p.setBrush(grad); p.setPen(QPen(QColor(0,0,0,160), 2))
        p.drawEllipse(int(cx-d/2), int(cy-d/2), d, d)
        text_x0 = int(22 + d + 14)
        text_w  = w - text_x0 - 14
        text_rect = (text_x0, 0, text_w, h)
        f = QFont("Arial"); f.setBold(True)
        size = max(10, int(h * 0.42))
        for sz in range(size, 9, -1):
            f.setPointSize(sz)
            fm = self.fontMetrics() if False else None
            from PySide6.QtGui import QFontMetrics
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(self._title) <= text_w - 8 and fm.height() <= h - 8:
                break
        p.setFont(f); p.setPen(QColor(235,242,248))
        p.drawText(text_rect[0], text_rect[1], text_rect[2], text_rect[3],
                   Qt.AlignVCenter | Qt.AlignHCenter, self._title)


class IndicatorsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.link = StatusLamp("СВЯЗЬ")
        self.zone = StatusLamp("В ЗОНЕ")
        lay = QVBoxLayout(self); lay.setSpacing(10); lay.setContentsMargins(10,10,10,10)
        lay.addWidget(self.link); lay.addWidget(self.zone); lay.addStretch(1)
        self.set_link(False); self.set_zone(False)

    def set_link(self, ok: bool):
        self.link.set_state(ok)

    def set_zone(self, inside: bool):
        self.zone.set_state(inside)
"""Primary Flight Display (PFD) на QPainter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, QSize
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPolygonF,
                          QLinearGradient, QPainterPath, QTransform)
from PySide6.QtWidgets import QWidget

from .mandala_client import FlightData


SKY_TOP = QColor(32, 76, 247)
SKY_BOT = QColor(48, 129, 247)
GND_TOP = QColor(238, 88, 1)	
GND_BOT = QColor(150, 70, 30)
MAGENTA = QColor(232, 60, 200)
WHITE   = QColor(245, 245, 245)
BLACK   = QColor(10, 14, 18)
GREEN   = QColor(80, 220, 100)
CYAN    = QColor(120, 210, 255)
AMBER   = QColor(255, 200, 60)


class AvionicsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 350)
        self._data = FlightData()
        self._d = FlightData()
        self._anim = QTimer(self)
        self._anim.setInterval(16)  
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(720, 420)

    def set_data(self, fd: FlightData):
        self._data = fd

    # ---------- сглаживание ----------
    def _tick(self):
        a = 0.25  # коэффициент сглаживания
        s, t = self._d, self._data
        s.roll      += (t.roll - s.roll) * a
        s.pitch     += (t.pitch - s.pitch) * a
        s.yaw       = _lerp_angle(s.yaw, t.yaw, a)
        s.course    = _lerp_angle(s.course, t.course, a)
        s.wind_hdg  = _lerp_angle(s.wind_hdg, t.wind_hdg, a)
        s.altitude  += (t.altitude - s.altitude) * a
        s.airspeed  += (t.airspeed - s.airspeed) * a
        s.vspeed    += (t.vspeed - s.vspeed) * a
        s.rpm       += (t.rpm - s.rpm) * a
        s.agl       += (t.agl - s.agl) * a
        s.wind_spd  += (t.wind_spd - s.wind_spd) * a
        s.g_speed   += (t.g_speed - s.g_speed) * a
        s.cmd_roll  += (t.cmd_roll - s.cmd_roll) * a
        s.cmd_pitch += (t.cmd_pitch - s.cmd_pitch) * a
        s.ctr_throttle += (t.ctr_throttle - s.ctr_throttle) * a
        self.update()

    # ---------- отрисовка ----------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(8, 12, 16))

        ai_rect = QRectF(0, 0, w, h)
        self._draw_attitude(p, ai_rect)

        tape_w = max(72, int(w * 0.12))
        vsi_w  = max(64, int(w * 0.10))
        top_off = 30  # под компасную полосу (
        bot_off = 70  # под нижнюю строку
        self._draw_speed_tape(p, QRectF(2, top_off, tape_w, h - top_off - bot_off))
        self._draw_alt_tape  (p, QRectF(w - tape_w - vsi_w - 4, top_off, tape_w, h - top_off - bot_off))
        self._draw_vsi       (p, QRectF(w - vsi_w - 2, top_off, vsi_w, h - top_off - bot_off))

        # Командные планки
        self._draw_cmd_bars(p, ai_rect)

        
        self._draw_bottom_bar(p)
        p.end()

    # ----- искусств. горизонт -----
    def _draw_attitude(self, p: QPainter, r: QRectF):
        p.save()
        p.setClipRect(r)
        cx, cy = r.center().x(), r.center().y()
        roll = self._d.roll
        pitch = self._d.pitch
        # 1 градус тангажа = pitch_px пикселей (уменьшаем, чтобы метки были ближе)
        pitch_px = r.height() / 36.0

        p.translate(cx, cy)
        p.rotate(-roll)
        p.translate(0, pitch * pitch_px)

        # Небо / земля 
        big = max(r.width(), r.height()) * 2
        sky_grad = QLinearGradient(0, -big, 0, 0)
        sky_grad.setColorAt(0, SKY_TOP); sky_grad.setColorAt(1, SKY_BOT)
        p.fillRect(QRectF(-big, -big, 2*big, big), QBrush(sky_grad))
        gnd_grad = QLinearGradient(0, 0, 0, big)
        gnd_grad.setColorAt(0, GND_TOP); gnd_grad.setColorAt(1, GND_BOT)
        p.fillRect(QRectF(-big, 0, 2*big, big), QBrush(gnd_grad))

        # Линия горизонта
        pen = QPen(WHITE, 2); p.setPen(pen)
        p.drawLine(QPointF(-big, 0), QPointF(big, 0))

        # Шкала тангажа
        font = QFont("Arial", max(11, int(r.height()/32))); font.setBold(True)
        p.setFont(font)
        for deg in range(-90, 91, 5):
            if deg == 0:
                continue
            y = -deg * pitch_px
            length = 70 if deg % 10 == 0 else 36
            p.setPen(QPen(WHITE, 1.7))
            p.drawLine(QPointF(-length/2, y), QPointF(length/2, y))
            if deg % 10 == 0:
                p.setPen(WHITE)
                p.drawText(QRectF(-length/2-44, y-12, 34, 24), Qt.AlignVCenter | Qt.AlignRight, str(abs(deg)))
                p.drawText(QRectF(length/2+10, y-12, 34, 24), Qt.AlignVCenter | Qt.AlignLeft, str(abs(deg)))
        p.restore()

        # --- неподвижные оверлеи поверх горизонта ---
        p.save()
        p.translate(r.center())
        # Шкала крена сверху
        radius = min(r.width(), r.height()) * 0.38
        p.setPen(QPen(WHITE, 1.5))
        path = QPainterPath()
        path.arcMoveTo(QRectF(-radius, -radius, 2*radius, 2*radius), 30)
        path.arcTo(QRectF(-radius, -radius, 2*radius, 2*radius), 30, 120)
        p.drawPath(path)
        for ang in (-60,-45,-30,-20,-10,0,10,20,30,45,60):
            a = math.radians(90 + ang)  # 0 — сверху
            x1, y1 = math.cos(a)*radius, -math.sin(a)*radius
            l = 12 if ang % 30 == 0 or ang == 0 else 7
            x2, y2 = math.cos(a)*(radius+l), -math.sin(a)*(radius+l)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        # Стрелка крена (треугольник снизу шкалы), повёрнута на -roll
        p.save()
        p.rotate(-self._d.roll)
        tri = QPolygonF([QPointF(0, -radius+2), QPointF(-7, -radius+16), QPointF(7, -radius+16)])
        p.setBrush(WHITE); p.setPen(Qt.NoPen)
        p.drawPolygon(tri)
        p.restore()
        # Неподвижный треугольник-указатель
        tri2 = QPolygonF([QPointF(0, -radius-2), QPointF(-8, -radius-16), QPointF(8, -radius-16)])
        p.setBrush(WHITE); p.setPen(Qt.NoPen)
        p.drawPolygon(tri2)

        # Маркер самолёта в центре (как «крылышки»)
        pen = QPen(WHITE, 3); p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(-60,0), QPointF(-20,0))
        p.drawLine(QPointF(-20,0), QPointF(-20,10))
        p.drawLine(QPointF(20,0), QPointF(20,10))
        p.drawLine(QPointF(20,0), QPointF(60,0))
        # Маленький центральный «+»
        p.setPen(QPen(MAGENTA, 2))
        p.drawLine(QPointF(-6,0), QPointF(6,0))
        p.drawLine(QPointF(0,-6), QPointF(0,6))

        p.restore()

        # Компасная полоса сверху
        self._draw_heading_strip(p, QRectF(r.x(), 0, r.width(), 28))

        # Стрелка ветра — снизу справа от горизонта
        self._draw_wind(p, r)


    def _draw_heading_strip(self, p: QPainter, r: QRectF):
        p.save()
        p.fillRect(r, QColor(0,0,0,150))
        p.setClipRect(r)
        yaw = self._d.yaw % 360
        px_per_deg = r.width() / 90.0
        cx = r.center().x()
        p.setPen(QPen(WHITE, 1))
        f = QFont("Arial", 11); f.setBold(True); p.setFont(f)
        for deg in range(0, 360, 5):
            delta = ((deg - yaw + 540) % 360) - 180
            x = cx + delta * px_per_deg
            if x < r.left()-20 or x > r.right()+20: continue
            if deg % 10 == 0:
                p.drawLine(QPointF(x, r.bottom()-12), QPointF(x, r.bottom()))
                label = {0:"N",90:"E",180:"S",270:"W"}.get(deg, f"{deg:03d}")
                p.drawText(QRectF(x-24, r.top(), 48, r.height()-12), Qt.AlignHCenter|Qt.AlignVCenter, label)
            else:
                p.drawLine(QPointF(x, r.bottom()-6), QPointF(x, r.bottom()))
        # центральная метка курса
        p.setBrush(BLACK); p.setPen(QPen(WHITE,1))
        rect = QRectF(cx-26, r.top(), 52, r.height())
        p.drawRect(rect)
        p.setPen(WHITE); f = QFont("Arial",13); f.setBold(True); p.setFont(f)
        p.drawText(rect, Qt.AlignCenter, f"{int(round(self._d.yaw))%360:03d}")
        p.restore()

    def _draw_wind(self, p: QPainter, r: QRectF):
        # Положение — слева, рядом с лентой скорости, чтобы не залезать под высоту
        p.save()
        # отступ от ленты скорости (правее, чтобы не прилипало к шкале)
        tape_w = max(64, int(r.width()*0.11))
        ax = r.left() + tape_w + 90
        ay = r.bottom() - 60
        p.translate(ax, ay)
        # Положение стрелки = (wind_hdg - course); если отрицательно — +360
        rel = self._d.wind_hdg - self._d.course
        if rel < 0:
            rel += 360.0
        p.rotate(rel)
        p.setPen(QPen(WHITE, 2)); p.setBrush(WHITE)
        # Стрелка «носом вверх» — при rotate(rel) острие смотрит на азимут rel
        p.drawLine(QPointF(0,14), QPointF(0,-14))
        tri = QPolygonF([QPointF(0,-14), QPointF(-5,-6), QPointF(5,-6)])
        p.drawPolygon(tri)
        p.restore()
        # Значение скорости ветра — рядом со стрелкой
        p.setPen(WHITE); f = QFont("Arial",12); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(ax + 16, ay - 12, 100, 24),
                   Qt.AlignLeft|Qt.AlignVCenter,
                   f"{self._d.wind_spd:.1f}  {int(self._d.wind_hdg)%360:03d}°")

    # ----- лента скорости (поверх горизонта) -----
    def _draw_speed_tape(self, p: QPainter, r: QRectF):
        p.save()
        # Полупрозрачный фон со скруглением
        p.setPen(Qt.NoPen); p.setBrush(QColor(0,0,0,110))
        p.drawRoundedRect(r, 6, 6)
        p.setClipRect(r)
        v = self._d.airspeed
        px_per = r.height() / 40.0
        cy = r.center().y()
        p.setPen(QPen(WHITE,1)); f = QFont("Arial",11); f.setBold(True); p.setFont(f)
        start = int(v - 25); end = int(v + 25)
        for s in range(start, end+1):
            if s < 0: continue
            y = cy - (s - v) * px_per
            if s % 5 == 0:
                p.drawLine(QPointF(r.right()-14, y), QPointF(r.right()-2, y))
                p.drawText(QRectF(r.right()-56, y-11, 40, 22), Qt.AlignRight|Qt.AlignVCenter, str(s))
            else:
                p.drawLine(QPointF(r.right()-8, y), QPointF(r.right()-2, y))
        p.restore()
        # Текущая метка (выходит чуть за ленту вправо — «флажок»)
        p.save()
        box = QRectF(r.left()-2, cy-16, r.width()+12, 32)
        path = QPainterPath()
        path.moveTo(box.left(), box.top())
        path.lineTo(box.right()-8, box.top())
        path.lineTo(box.right(), box.center().y())
        path.lineTo(box.right()-8, box.bottom())
        path.lineTo(box.left(), box.bottom())
        path.closeSubpath()
        p.setBrush(QColor(0,0,0,220)); p.setPen(QPen(WHITE,1.2))
        p.drawPath(path)
        f = QFont("Arial",17); f.setBold(True); p.setFont(f); p.setPen(WHITE)
        p.drawText(box.adjusted(2,0,-10,0), Qt.AlignCenter, f"{v:.0f}")
        p.restore()
        # GS справа от ленты
        p.setPen(WHITE); f = QFont("Arial",11); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(r.right()+4, r.bottom()-20, 100, 20),
                   Qt.AlignLeft|Qt.AlignVCenter, f"GS {self._d.g_speed:.0f}")

    # ----- лента высоты -----
    def _draw_alt_tape(self, p: QPainter, r: QRectF):
        p.save()
        p.setPen(Qt.NoPen); p.setBrush(QColor(0,0,0,110))
        p.drawRoundedRect(r, 6, 6)
        p.setClipRect(r)
        v = self._d.altitude
        px_per = r.height() / 40.0
        cy = r.center().y()
        p.setPen(QPen(WHITE,1)); f = QFont("Arial",11); f.setBold(True); p.setFont(f)
        start = int(v - 25); end = int(v + 25)
        for s in range(start, end+1):
            y = cy - (s - v) * px_per
            if s % 5 == 0:
                p.drawLine(QPointF(r.left()+2, y), QPointF(r.left()+14, y))
                p.drawText(QRectF(r.left()+16, y-11, 44, 22), Qt.AlignLeft|Qt.AlignVCenter, str(s))
            else:
                p.drawLine(QPointF(r.left()+2, y), QPointF(r.left()+8, y))
        p.restore()
        # Флажок текущего значения (стрелка влево)
        p.save()
        box = QRectF(r.left()-10, cy-16, r.width()+10, 32)
        path = QPainterPath()
        path.moveTo(box.left()+8, box.center().y())
        path.lineTo(box.left()+16, box.top())
        path.lineTo(box.right(), box.top())
        path.lineTo(box.right(), box.bottom())
        path.lineTo(box.left()+16, box.bottom())
        path.closeSubpath()
        p.setBrush(QColor(0,0,0,220)); p.setPen(QPen(WHITE,1.2))
        p.drawPath(path)
        f = QFont("Arial",17); f.setBold(True); p.setFont(f); p.setPen(WHITE)
        p.drawText(box.adjusted(16,0,-2,0), Qt.AlignCenter, f"{v:.0f}")
        p.restore()

    def _draw_vsi(self, p: QPainter, r: QRectF):
        p.save()
        p.setPen(Qt.NoPen); p.setBrush(QColor(0,0,0,90))
        p.drawRoundedRect(r, 8, 8)

        p.setClipRect(r)
        cx = r.right() - 2
        cy = r.center().y()
        # Ограничения на радиус:
        #  - по высоте: верх/низ дуги при ±60° от горизонтали (sin60*r) <= h/2
        #  - по ширине: левая крайняя точка (угол 180°) >= r.left()
        #               => radius <= cx - r.left()
        radius_by_h = (r.height() * 0.48) / math.sin(math.radians(60))
        radius_by_w = (cx - r.left()) - 4
        radius = max(10.0, min(radius_by_h, radius_by_w))

        tick_major = radius * 0.10
        tick_minor = radius * 0.05
        label_off  = radius * 0.22
        font_px    = max(8, int(radius * 0.10))

        def vs_to_angle(vs):
            vs = max(-10.0, min(10.0, vs))
            return 180.0 - vs/10.0 * 60.0

        # Шкала
        p.setPen(QPen(WHITE,1)); f = QFont("Arial", font_px); f.setBold(True); p.setFont(f)
        for v in (-10,-5,-1,0,1,5,10):
            a = math.radians(vs_to_angle(v))
            tl = tick_major if v in (-10,-5,0,5,10) else tick_minor
            x1 = cx + math.cos(a)*radius
            y1 = cy - math.sin(a)*radius
            x2 = cx + math.cos(a)*(radius - tl)
            y2 = cy - math.sin(a)*(radius - tl)
            p.drawLine(QPointF(x1,y1), QPointF(x2,y2))
            if v in (-10,-5,5,10) or v == 0:
                xt = cx + math.cos(a)*(radius - label_off)
                yt = cy - math.sin(a)*(radius - label_off)
                lw = font_px*2.4; lh = font_px*1.8
                p.drawText(QRectF(xt-lw/2, yt-lh/2, lw, lh),
                           Qt.AlignCenter, str(v) if v else "0")
        # Дуга (от 120° до 240° — слева от центра)
        rect_arc = QRectF(cx - radius, cy - radius, 2*radius, 2*radius)
        p.setPen(QPen(WHITE, 1.5))
        p.drawArc(rect_arc, int(120*16), int(120*16))
        # Стрелка
        a = math.radians(vs_to_angle(self._d.vspeed))
        x_tip = cx + math.cos(a)*(radius - radius*0.04)
        y_tip = cy - math.sin(a)*(radius - radius*0.04)
        p.setPen(QPen(WHITE, max(2, radius*0.03)))
        p.drawLine(QPointF(cx + math.cos(a)*radius*0.08, cy - math.sin(a)*radius*0.08),
                   QPointF(x_tip, y_tip))
        # Цифра вертикальной скорости сверху ленты
        p.setPen(WHITE); f = QFont("Arial", max(9, font_px+2)); f.setBold(True); p.setFont(f)
        p.drawText(QRectF(r.left()+4, r.top()+2, r.width()-8, 20),
                   Qt.AlignLeft|Qt.AlignVCenter, f"{self._d.vspeed:+.1f}")
        p.restore()

    # ----- командные планки cmd_roll/cmd_pitch -----
    def _draw_cmd_bars(self, p: QPainter, r: QRectF):
        p.save()
        p.translate(r.center())
        dx = max(-90, min(90, self._d.cmd_roll * 6.0))
        dy = -max(-90, min(90, self._d.cmd_pitch * 6.0))

        dim_magenta = QColor(170, 70, 150)

        outline = QPen(QColor(0, 0, 0, 220), 8)
        outline.setCapStyle(Qt.FlatCap)
        fill = QPen(dim_magenta, 6)
        fill.setCapStyle(Qt.FlatCap)

        # Вертикальная (roll)
        p.setPen(outline)
        p.drawLine(QPointF(dx, -70), QPointF(dx, 70))
        p.setPen(fill)
        p.drawLine(QPointF(dx, -70), QPointF(dx, 70))

        # Горизонтальная (pitch)
        p.setPen(outline)
        p.drawLine(QPointF(-90, dy), QPointF(90, dy))
        p.setPen(fill)
        p.drawLine(QPointF(-90, dy), QPointF(90, dy))

        # Центральный неподвижный «+»
        p.setPen(QPen(WHITE, 1.5))
        p.drawLine(QPointF(-4, 0), QPointF(4, 0))
        p.drawLine(QPointF(0, -4), QPointF(0, 4))
        p.restore()

    # ----- нижняя строка (RPM и T — у центра) -----
    def _draw_bottom_bar(self, p: QPainter):
        h = self.height(); w = self.width()
        bh = 30
        rect = QRectF(0, h-bh, w, bh)
        p.fillRect(rect, QColor(0,0,0,160))
        f = QFont("Arial",13); f.setBold(True); p.setFont(f)
        rpm = f"{self._d.rpm:.0f}"
        thr = f"{self._d.ctr_throttle*100:.0f}"
        cx = w/2
        p.setPen(CYAN); p.drawText(QRectF(cx-160, h-bh, 60, bh), Qt.AlignVCenter|Qt.AlignRight, "RPM")
        p.setPen(WHITE); p.drawText(QRectF(cx-96, h-bh, 90, bh), Qt.AlignVCenter|Qt.AlignLeft, rpm)
        p.setPen(CYAN); p.drawText(QRectF(cx+14, h-bh, 24, bh), Qt.AlignVCenter|Qt.AlignLeft, "T")
        p.setPen(WHITE); p.drawText(QRectF(cx+38, h-bh, 90, bh), Qt.AlignVCenter|Qt.AlignLeft, thr)


def _lerp_angle(a: float, b: float, k: float) -> float:
    d = ((b - a + 540) % 360) - 180
    return (a + d * k) % 360
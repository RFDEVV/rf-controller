"""Logo aplikasi dan ikon navigasi (digambar dengan QPainter, tanpa file gambar)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

NAVY_TOP, NAVY_BOT = QColor("#18263D"), QColor("#0A101C")
BLUE, AMBER = QColor("#4DA3FF"), QColor("#FFB84D")

# Titik gelombang pulsa pada koordinat 0..1 (dipakai juga oleh tools/make_icon.py)
PULSE = [(0.13, 0.5), (0.36, 0.5), (0.43, 0.5), (0.48, 0.29), (0.545, 0.71), (0.60, 0.5), (0.64, 0.5), (0.87, 0.5)]


def pulse_points(rect, upto=1.0):
    """Titik pulsa sampai fraksi panjang 'upto' (untuk animasi menggambar)."""
    pts = [QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height()) for x, y in PULSE]
    seg = [math.hypot(pts[i + 1].x() - pts[i].x(), pts[i + 1].y() - pts[i].y()) for i in range(len(pts) - 1)]
    total, run, out = sum(seg), 0.0, [pts[0]]
    goal = total * max(0.0, min(1.0, upto))
    for i, s in enumerate(seg):
        if run + s <= goal:
            out.append(pts[i + 1])
            run += s
        else:
            f = (goal - run) / s if s else 0
            out.append(QPointF(pts[i].x() + (pts[i + 1].x() - pts[i].x()) * f, pts[i].y() + (pts[i + 1].y() - pts[i].y()) * f))
            break
    return out


def paint_logo(p, rect, ring=1.0, pulse=1.0, plate=True):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s = rect.width()
    if plate:
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0, NAVY_TOP)
        g.setColorAt(1, NAVY_BOT)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(rect, s * 0.22, s * 0.22)
    c = rect.center()
    r = s * 0.30
    arc = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    if ring > 0:
        halo = QColor(BLUE)
        halo.setAlphaF(0.22)
        p.setPen(QPen(halo, s * 0.11, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc, 90 * 16, int(-360 * 16 * ring))
        p.setPen(QPen(BLUE, s * 0.07, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc, 90 * 16, int(-360 * 16 * ring))
    if pulse > 0:
        pts = pulse_points(rect, pulse)
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        halo = QColor(AMBER)
        halo.setAlphaF(0.25)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(halo, s * 0.10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(AMBER, s * 0.055, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
    p.restore()


def draw_icon(p, name, r, color):
    """Ikon garis sederhana pada kotak r (QRectF)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if name == "dash":
        for i in range(2):
            for j in range(2):
                p.drawRoundedRect(QRectF(x + 1 + i * (w / 2), y + 1 + j * (h / 2), w / 2 - 3, h / 2 - 3), 2, 2)
    elif name == "pulse":
        path = QPainterPath(QPointF(x, y + h * 0.55))
        for fx, fy in [(0.3, 0.55), (0.4, 0.15), (0.55, 0.9), (0.65, 0.55), (1.0, 0.55)]:
            path.lineTo(x + w * fx, y + h * fy)
        p.drawPath(path)
    elif name == "wheel":
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        p.drawEllipse(r.center(), w * 0.1, w * 0.1)
        p.drawLine(QPointF(x + 1, y + h * 0.5), QPointF(x + w * 0.4, y + h * 0.5))
        p.drawLine(QPointF(x + w * 0.6, y + h * 0.5), QPointF(x + w - 1, y + h * 0.5))
        p.drawLine(QPointF(x + w * 0.5, y + h * 0.6), QPointF(x + w * 0.5, y + h - 1))
    elif name == "gear":
        c = r.center()
        p.drawEllipse(c, w * 0.22, w * 0.22)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(c.x() + math.cos(a) * w * 0.34, c.y() + math.sin(a) * w * 0.34),
                       QPointF(c.x() + math.cos(a) * w * 0.5, c.y() + math.sin(a) * w * 0.5))
    elif name == "button":
        p.drawRoundedRect(r.adjusted(1, 3, -1, -3), 5, 5)
        p.drawEllipse(r.center(), 2.5, 2.5)
    elif name == "output":
        p.drawRoundedRect(QRectF(x + 1, y + h * 0.28, w - 2, h * 0.5), 6, 6)
        p.drawLine(QPointF(x + w * 0.3, y + h * 0.4), QPointF(x + w * 0.3, y + h * 0.66))
        p.drawLine(QPointF(x + w * 0.2, y + h * 0.53), QPointF(x + w * 0.4, y + h * 0.53))
        p.drawEllipse(QPointF(x + w * 0.68, y + h * 0.48), 1.6, 1.6)
        p.drawEllipse(QPointF(x + w * 0.78, y + h * 0.6), 1.6, 1.6)
    elif name == "profile":
        for i in range(3):
            yy = y + h * (0.25 + i * 0.25)
            p.drawLine(QPointF(x + 2, yy), QPointF(x + w - 2, yy))
    elif name == "plug":
        p.drawLine(QPointF(x + w * 0.35, y), QPointF(x + w * 0.35, y + h * 0.3))
        p.drawLine(QPointF(x + w * 0.65, y), QPointF(x + w * 0.65, y + h * 0.3))
        p.drawRoundedRect(QRectF(x + w * 0.2, y + h * 0.3, w * 0.6, h * 0.32), 4, 4)
        p.drawLine(QPointF(x + w * 0.5, y + h * 0.62), QPointF(x + w * 0.5, y + h))
    elif name == "led":
        p.drawEllipse(QRectF(x + w * 0.2, y + 1, w * 0.6, w * 0.6))
        p.drawLine(QPointF(x + w * 0.35, y + h * 0.78), QPointF(x + w * 0.65, y + h * 0.78))
        p.drawLine(QPointF(x + w * 0.4, y + h * 0.95), QPointF(x + w * 0.6, y + h * 0.95))
    elif name == "oled":
        p.drawRoundedRect(QRectF(x + 1, y + h * 0.18, w - 2, h * 0.64), 3, 3)
        p.drawLine(QPointF(x + 4, y + h * 0.42), QPointF(x + w * 0.5, y + h * 0.42))
        p.drawLine(QPointF(x + 4, y + h * 0.6), QPointF(x + w * 0.75, y + h * 0.6))
    elif name == "wire":
        p.drawEllipse(QPointF(x + 3, y + h * 0.25), 2.5, 2.5)
        p.drawEllipse(QPointF(x + w - 3, y + h * 0.75), 2.5, 2.5)
        path = QPainterPath(QPointF(x + 5.5, y + h * 0.25))
        path.cubicTo(QPointF(x + w * 0.6, y + h * 0.25), QPointF(x + w * 0.4, y + h * 0.75), QPointF(x + w - 5.5, y + h * 0.75))
        p.drawPath(path)
    elif name == "chip":
        p.drawRoundedRect(r.adjusted(4, 4, -4, -4), 3, 3)
        for i in range(3):
            t = 0.3 + i * 0.2
            p.drawLine(QPointF(x + w * t, y), QPointF(x + w * t, y + 3))
            p.drawLine(QPointF(x + w * t, y + h - 3), QPointF(x + w * t, y + h))
            p.drawLine(QPointF(x, y + h * t), QPointF(x + 3, y + h * t))
            p.drawLine(QPointF(x + w - 3, y + h * t), QPointF(x + w, y + h * t))
    p.restore()

"""Widget kustom: dial gigi, scope pulsa, switch, segmented, toast, dan kontrol terikat parameter."""
import math
import time
from collections import deque

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation, Signal,
                            Property, QParallelAnimationGroup)
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy, QSlider,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QAbstractButton)

from .params import CODE_TABLE, TYPE_NAMES, curve, norm_raw
from .theme import head_font

THEME = None  # diisi oleh window


def theme():
    return THEME


def animate(anim_enabled=True):
    return THEME is None or THEME.animations


def make_anim(target, prop, start, end, ms=220, curve_=QEasingCurve.OutCubic):
    a = QPropertyAnimation(target, prop)
    a.setDuration(ms if animate() else 0)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(curve_)
    return a


class Card(QFrame):
    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(18, 16, 18, 16)
        self.v.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setProperty("role", "h2")
            self.v.addWidget(t)


def label(text, role=None, wrap=False):
    l = QLabel(text)
    if role:
        l.setProperty("role", role)
    l.setWordWrap(wrap)
    return l


# ---------------------------------------------------------------- Switch
class Toggle(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._p = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_p)
        self.toggled.connect(self._on_toggled)

    def _set_p(self, v):
        self._p = float(v)
        self.update()

    def _on_toggled(self, on):
        self._anim.stop()
        self._anim.setDuration(160 if animate() else 0)
        self._anim.setStartValue(self._p)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setCheckedSilent(self, on):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._p = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(c["border"]), QColor(c["accent"])
        mix = QColor(int(off.red() + (on.red() - off.red()) * self._p), int(off.green() + (on.green() - off.green()) * self._p),
                     int(off.blue() + (on.blue() - off.blue()) * self._p))
        p.setPen(Qt.NoPen)
        p.setBrush(mix)
        p.drawRoundedRect(self.rect(), 12, 12)
        x = 3 + self._p * (self.width() - 24 + 0)
        p.setBrush(QColor("#FFFFFF") if self._p > 0.5 else QColor(c["muted"]))
        p.drawEllipse(QRectF(x, 3, 18, 18))


# ---------------------------------------------------------------- Segmented
class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items  # [(label, value)]
        self.idx = 0
        self._pos = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, v):
        self._pos = float(v)
        self.update()

    def value(self):
        return self.items[self.idx][1]

    def set_value(self, val, silent=True):
        for i, (_, v) in enumerate(self.items):
            if v == val:
                self._go(i, silent)
                return

    def _go(self, i, silent):
        if i == self.idx and silent:
            return
        self._anim.stop()
        self._anim.setDuration(220 if animate() and not silent else 0)
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(i))
        self.idx = i
        self._anim.start()
        if not silent:
            self.changed.emit(self.items[i][1])

    def mousePressEvent(self, e):
        n = len(self.items)
        i = max(0, min(n - 1, int(e.position().x() / (self.width() / n))))
        if i != self.idx:
            self._go(i, False)

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(r, 10, 10)
        n = len(self.items)
        w = r.width() / n
        pill = QRectF(r.left() + 3 + self._pos * w, r.top() + 3, w - 6, r.height() - 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["accent"]))
        p.drawRoundedRect(pill, 8, 8)
        f = QFont(self.font())
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        for i, (name, _) in enumerate(self.items):
            near = max(0.0, 1 - abs(self._pos - i))
            col = QColor(c["muted"])
            top = QColor(c["accent_text"])
            mixc = QColor(int(col.red() + (top.red() - col.red()) * near), int(col.green() + (top.green() - col.green()) * near),
                          int(col.blue() + (top.blue() - col.blue()) * near))
            p.setPen(mixc)
            p.drawText(QRectF(r.left() + i * w, r.top(), w, r.height()), Qt.AlignCenter, name)


# ---------------------------------------------------------------- Bar animasi
class AnimBar(QWidget):
    """Bar horizontal; mode center untuk nilai -100..100."""

    def __init__(self, title, vmin=0, vmax=100, center=False, color="accent", unit="%", compact=False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.title, self.vmin, self.vmax, self.center, self.color, self.unit = title, vmin, vmax, center, color, unit
        self._v = float(vmin) if not center else 0.0
        self._target = self._v
        self.setFixedHeight(44)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._tick)
        self.markers = []

    def _tick(self, v):
        self._v = float(v)
        self.update()

    def set_value(self, v):
        if v == self._target:
            return
        self._target = v
        self._anim.stop()
        self._anim.setDuration(140 if animate() else 0)
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(float(v))
        self._anim.start()

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.compact:
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, 0, self.width() / 2, 18), Qt.AlignLeft | Qt.AlignVCenter, self.title)
            p.setPen(QColor(c["text"]))
            p.setFont(head_font(13))
            p.drawText(QRectF(self.width() / 2, 0, self.width() / 2, 18), Qt.AlignRight | Qt.AlignVCenter,
                       "%d %s" % (round(self._target), self.unit))
        track = QRectF(0, (self.height() - 8) / 2, self.width(), 8) if self.compact else QRectF(0, 26, self.width(), 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["surface2"] if False else c["border"]))
        p.drawRoundedRect(track, 4, 4)
        span = float(self.vmax - self.vmin)
        col = QColor(c[self.color])
        if self.center:
            mid = track.center().x()
            x = mid + (self._v / self.vmax) * (track.width() / 2)
            r = QRectF(min(mid, x), track.top(), abs(x - mid), track.height())
            p.setBrush(col)
            p.drawRoundedRect(r, 4, 4)
            p.setBrush(QColor(c["text"]))
            p.drawRect(QRectF(mid - 1, track.top() - 3, 2, track.height() + 6))
        else:
            frac = max(0.0, min(1.0, (self._v - self.vmin) / span))
            g = QLinearGradient(track.topLeft(), track.topRight())
            g.setColorAt(0, col.darker(130))
            g.setColorAt(1, col)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(track.left(), track.top(), max(8.0, track.width() * frac), track.height()), 4, 4)
        for m in self.markers:
            x = track.left() + track.width() * (m - self.vmin) / span
            p.setBrush(QColor(c["text"]))
            p.drawRect(QRectF(x - 0.5, track.top() - 2, 1, track.height() + 4))


# ---------------------------------------------------------------- Scope pulsa
class Scope(QWidget):
    COLORS = ["accent", "amber", "teal", "rose"]
    NAMES = ["CH1 setir", "CH2 gas", "CH3", "CH4"]
    WINDOW = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.data = [deque(maxlen=400) for _ in range(4)]
        self.sig = True
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def push(self, pw, sig):
        t = time.monotonic()
        self.sig = bool(sig)
        for i in range(4):
            self.data[i].append((t, pw[i]))

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 8, -6, -8)
        lo, hi = 800.0, 2200.0
        p.setPen(QPen(QColor(c["grid"]), 1))
        for k in range(5):
            y = r.top() + r.height() * k / 4
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        for k in range(1, 6):
            x = r.left() + r.width() * k / 6
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.setPen(QColor(c["muted"]))
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        for k, v in enumerate((2200, 1500, 800)):
            y = r.top() + r.height() * k / 2
            p.drawText(QRectF(r.left() + 4, y - (0 if k == 0 else 14 if k == 2 else 7), 60, 14), Qt.AlignLeft, "%d µs" % v)
        now = time.monotonic()
        for i in range(4):
            pts = [(t, v) for t, v in self.data[i] if now - t <= self.WINDOW]
            if len(pts) < 2:
                continue
            path = QPainterPath()
            first = True
            for t, v in pts:
                x = r.right() - (now - t) / self.WINDOW * r.width()
                y = r.bottom() - (max(lo, min(hi, v or lo)) - lo) / (hi - lo) * r.height()
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            col = QColor(c[self.COLORS[i]])
            glow = QColor(col)
            glow.setAlphaF(c["glow"] * 0.35)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(glow, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
            p.setPen(QPen(col, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
            ex, ey = path.currentPosition().x(), path.currentPosition().y()
            pulse = 3.5 + 1.5 * math.sin(now * 6 + i) if animate() else 4
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(ex, ey), pulse, pulse)
        if not self.sig:
            p.setPen(QColor(c["danger"]))
            p.setFont(head_font(15))
            p.drawText(r, Qt.AlignCenter, "Sinyal remot hilang")


# ---------------------------------------------------------------- Dial gigi
class GearDial(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.gas = 0.0
        self.brk = 0.0
        self.gear = 0
        self.st = 0
        self.rev = False
        self.lock = False
        self.thresholds = []
        self._gas_v = 0.0
        self._brk_v = 0.0
        self._old = ""
        self._cur = "N"
        self._roll = 1.0
        self._a = QVariantAnimation(self)
        self._a.setDuration(150)
        self._a.setEasingCurve(QEasingCurve.OutCubic)
        self._a.valueChanged.connect(self._tick)
        self._r = QVariantAnimation(self)
        self._r.setDuration(260)
        self._r.setEasingCurve(QEasingCurve.OutBack)
        self._r.valueChanged.connect(self._roll_tick)
        self._gas_t = self._brk_t = 0.0

    def _tick(self, v):
        self._gas_v += (self._gas_t - self._gas_v) * 0.35
        self._brk_v += (self._brk_t - self._brk_v) * 0.35
        self.update()

    def _roll_tick(self, v):
        self._roll = float(v)
        self.update()

    def set_state(self, gas, brk, gear, st, rev, lock, thresholds):
        self.thresholds = thresholds
        self.lock = lock
        text = "R" if rev else ("N" if gear == 0 else str(gear))
        if text != self._cur:
            self._old, self._cur = self._cur, text
            self._r.stop()
            self._r.setDuration(260 if animate() else 0)
            self._r.setStartValue(0.0)
            self._r.setEndValue(1.0)
            self._r.start()
        self.st = st
        self._gas_t, self._brk_t = float(gas), float(brk)
        if not animate():
            self._gas_v, self._brk_v = self._gas_t, self._brk_t
        self._a.stop()
        self._a.setDuration(150)
        self._a.setStartValue(0.0)
        self._a.setEndValue(1.0)
        self._a.start()

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 24
        cx, cy = self.width() / 2, self.height() / 2
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)
        start, span = 225, -270
        pen = QPen(QColor(c["border"]), 14, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, int(start * 16), int(span * 16))
        gas = max(0.0, min(100.0, self._gas_v))
        if gas > 0.5:
            col = QColor(c["accent"])
            glow = QColor(col)
            glow.setAlphaF(c["glow"] * 0.4)
            p.setPen(QPen(glow, 24, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, int(start * 16), int(span * gas / 100 * 16))
            p.setPen(QPen(col, 14, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, int(start * 16), int(span * gas / 100 * 16))
        brk = max(0.0, min(100.0, self._brk_v))
        inner = rect.adjusted(26, 26, -26, -26)
        p.setPen(QPen(QColor(c["border"]), 6, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(inner, int(start * 16), int(span * 16))
        if brk > 0.5:
            p.setPen(QPen(QColor(c["danger"]), 6, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(inner, int(start * 16), int(span * brk / 100 * 16))
        # tanda ambang gigi
        p.setPen(QPen(QColor(c["amber"]), 2))
        rad_o, rad_i = side / 2 + 10, side / 2 - 10
        for t in self.thresholds:
            ang = math.radians(start + span * t / 100.0)
            p.drawLine(QPointF(cx + rad_i * math.cos(ang), cy - rad_i * math.sin(ang)),
                       QPointF(cx + rad_o * math.cos(ang), cy - rad_o * math.sin(ang)))
        # angka gigi dengan roll
        p.setFont(head_font(int(side * 0.34), QFont.Bold))
        box = QRectF(cx - side * 0.3, cy - side * 0.26, side * 0.6, side * 0.42)
        p.save()
        p.setClipRect(box.adjusted(-10, -6, 10, 6))
        off = (1 - self._roll) * box.height() * 0.6
        if self._roll < 1.0 and self._old:
            p.setPen(QColor(c["muted"]))
            p.setOpacity(max(0.0, 1 - self._roll * 1.4))
            p.drawText(box.translated(0, -box.height() * 0.6 * self._roll), Qt.AlignCenter, self._old)
        p.setOpacity(min(1.0, self._roll * 1.2))
        col = QColor(c["danger"]) if self._cur == "R" else (QColor(c["amber"]) if self._cur != "N" else QColor(c["muted"]))
        p.setPen(col)
        p.drawText(box.translated(0, off), Qt.AlignCenter, self._cur)
        p.restore()
        names = {0: "Netral", 1: "Maju", 2: "Mengerem", 3: "Mundur", 4: "Mengerem", 5: "Pindah ke R"}
        p.setFont(head_font(15))
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(cx - 100, cy + side * 0.16, 200, 24), Qt.AlignCenter, names.get(self.st, ""))
        p.setFont(QFont(self.font().family(), 10))
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(cx - 100, cy + side * 0.16 + 24, 200, 20), Qt.AlignCenter, "Gigi terkunci" if self.lock else "Gas %d%%" % round(gas))


# ---------------------------------------------------------------- Kurva respons
class CurveView(QWidget):
    def __init__(self, store, ch, parent=None):
        super().__init__(parent)
        self.store, self.ch = store, ch
        self.setMinimumSize(180, 180)
        self.cur = 0.0
        store.changed.connect(lambda k: self.update())
        store.bulk.connect(self.update)

    def set_pulse(self, p):
        s, n = self.store, str(self.ch)
        self.cur = norm_raw(p, s.get("c%s_min" % n), s.get("c%s_mid" % n), s.get("c%s_max" % n), s.get("inv%s" % n))
        self.update()

    def paintEvent(self, _):
        c = THEME.c
        s, n = self.store, str(self.ch)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 16
        r = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(r, 10, 10)
        p.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
        p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
        dz, ex = s.get("dz%s" % n), s.get("ex%s" % n)
        path = QPainterPath()
        for i in range(-100, 101, 4):
            v = i / 100.0
            y = curve(v, dz, ex)
            pt = QPointF(r.center().x() + v * r.width() / 2, r.center().y() - y * r.height() / 2)
            path.moveTo(pt) if i == -100 else path.lineTo(pt)
        p.setPen(QPen(QColor(c["accent"]), 2.5, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        y = curve(self.cur, dz, ex)
        pt = QPointF(r.center().x() + self.cur * r.width() / 2, r.center().y() - y * r.height() / 2)
        p.setPen(Qt.NoPen)
        g = QColor(c["amber"])
        g.setAlphaF(0.3)
        p.setBrush(g)
        p.drawEllipse(pt, 9, 9)
        p.setBrush(QColor(c["amber"]))
        p.drawEllipse(pt, 5, 5)


# ---------------------------------------------------------------- Lampu status
class Lamp(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.on = False

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.update()

    def paintEvent(self, _):
        c = THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(c["teal"] if self.on else c["border"])
        if self.on:
            g = QColor(col)
            g.setAlphaF(0.35)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QRectF(0, 0, 14, 14))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(3, 3, 8, 8))


# ---------------------------------------------------------------- Toast
class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._out)
        self._grp = None

    def show_text(self, text, bad=False):
        c = THEME.c
        self.setStyleSheet("QLabel { background: %s; color: %s; border: 1px solid %s; border-radius: 10px; padding: 10px 18px; font-weight: 600; }"
                           % (c["surface"], c["danger"] if bad else c["text"], c["danger"] if bad else c["accent"]))
        self.setText(text)
        self.adjustSize()
        pw, ph = self.parent().width(), self.parent().height()
        x = (pw - self.width()) // 2
        y_end = ph - self.height() - 28
        self.move(x, y_end + 16)
        self.show()
        self.raise_()
        a1 = make_anim(self._fx, b"opacity", 0.0, 1.0, 200)
        a2 = make_anim(self, b"pos", self.pos(), QPointF(x, y_end).toPoint(), 240)
        self._grp = QParallelAnimationGroup(self)
        self._grp.addAnimation(a1)
        self._grp.addAnimation(a2)
        self._grp.start()
        self._timer.start(2200)

    def _out(self):
        a = make_anim(self._fx, b"opacity", 1.0, 0.0, 260)
        a.finished.connect(self.hide)
        self._grp = a
        a.start()


# ---------------------------------------------------------------- Tumpukan halaman beranimasi
class AnimStack(QStackedWidget):
    def go(self, i):
        if i == self.currentIndex():
            return
        self.setCurrentIndex(i)
        w = self.currentWidget()
        if not animate():
            return
        fx = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(fx)
        a1 = make_anim(fx, b"opacity", 0.0, 1.0, 260)
        end = w.pos()
        a2 = make_anim(w, b"pos", end + QPointF(0, 22).toPoint(), end, 300)
        grp = QParallelAnimationGroup(w)
        grp.addAnimation(a1)
        grp.addAnimation(a2)
        grp.finished.connect(lambda: w.setGraphicsEffect(None))
        grp.start()
        self._grp = grp


# ---------------------------------------------------------------- Kontrol terikat parameter
class PSlider(QWidget):
    def __init__(self, store, key, text, unit="", mn=None, mx=None, step=1, parent=None):
        super().__init__(parent)
        from .params import PARAMS
        self.store, self.key, self.unit = store, key, unit
        lo, hi = (PARAMS[key][1] if mn is None else mn), (PARAMS[key][2] if mx is None else mx)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(12)
        self.lab = QLabel(text)
        self.lab.setFixedWidth(210)
        self.sl = QSlider(Qt.Horizontal)
        self.sl.setRange(lo, hi)
        self.sl.setSingleStep(step)
        self.val = QLabel()
        self.val.setProperty("role", "value")
        self.val.setMinimumWidth(64)
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.lab)
        h.addWidget(self.sl, 1)
        h.addWidget(self.val)
        self.sl.setValue(store.get(key))
        self._show(store.get(key))
        self.sl.valueChanged.connect(self._user)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _show(self, v):
        self.val.setText("%d %s" % (v, self.unit))

    def _user(self, v):
        self._show(v)
        self.store.set(self.key, v)

    def _ext(self, k):
        if k == self.key:
            v = self.store.get(k)
            self.sl.blockSignals(True)
            self.sl.setValue(v)
            self.sl.blockSignals(False)
            self._show(v)


class PSwitch(QWidget):
    def __init__(self, store, key, text, hint=None, parent=None):
        super().__init__(parent)
        self.store, self.key = store, key
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 4)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(QLabel(text))
        if hint:
            col.addWidget(label(hint, "muted", True))
        h.addLayout(col, 1)
        self.t = Toggle()
        self.t.setCheckedSilent(bool(store.get(key)))
        self.t.toggled.connect(lambda on: store.set(key, 1 if on else 0))
        h.addWidget(self.t)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _ext(self, k):
        if k == self.key:
            self.t.setCheckedSilent(bool(self.store.get(k)))


class PSeg(QWidget):
    def __init__(self, store, key, items, parent=None):
        super().__init__(parent)
        self.store, self.key = store, key
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.seg = Segmented(items)
        self.seg.set_value(store.get(key))
        self.seg.changed.connect(lambda v: store.set(key, v))
        h.addWidget(self.seg)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _ext(self, k):
        if k == self.key:
            self.seg.set_value(self.store.get(k))


class PSpin(QWidget):
    def __init__(self, store, key, text, suffix="", parent=None):
        super().__init__(parent)
        from .params import PARAMS
        self.store, self.key = store, key
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.addWidget(QLabel(text), 1)
        self.sp = QSpinBox()
        self.sp.setRange(PARAMS[key][1], PARAMS[key][2])
        self.sp.setSuffix(suffix)
        self.sp.setFixedWidth(110)
        self.sp.setValue(store.get(key))
        self.sp.valueChanged.connect(lambda v: store.set(key, v))
        h.addWidget(self.sp)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _ext(self, k):
        if k == self.key:
            self.sp.blockSignals(True)
            self.sp.setValue(self.store.get(k))
            self.sp.blockSignals(False)


class PAction(QWidget):
    """Pilih aksi: tipe + kode. Disimpan sebagai tipe*256+kode."""

    def __init__(self, store, key, text, parent=None):
        super().__init__(parent)
        self.store, self.key = store, key
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        lab = QLabel(text)
        lab.setFixedWidth(130)
        h.addWidget(lab)
        self.tc = QComboBox()
        for n in TYPE_NAMES:
            self.tc.addItem(n)
        self.cc = QComboBox()
        self.cc.setMinimumWidth(170)
        h.addWidget(self.tc)
        h.addWidget(self.cc, 1)
        from PySide6.QtWidgets import QPushButton
        tb = QPushButton("Tes")
        tb.setToolTip("Kirim aksi ini ke PC sekarang, tanpa remot")
        tb.setFixedWidth(52)
        tb.clicked.connect(self._test)
        h.addWidget(tb)
        self._fill(store.get(key))
        self.tc.currentIndexChanged.connect(self._type_changed)
        self.cc.currentIndexChanged.connect(self._code_changed)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _test(self):
        link = self.store.link
        if link is not None and link.is_on() and self.store.get(self.key):
            link.send("TEST %d" % self.store.get(self.key))

    def _fill(self, v):
        t, code = v >> 8, v & 255
        self.tc.blockSignals(True)
        self.cc.blockSignals(True)
        self.tc.setCurrentIndex(t if t < len(TYPE_NAMES) else 0)
        self.cc.clear()
        for name, c in CODE_TABLE.get(t, []):
            self.cc.addItem(name, c)
        self.cc.setEnabled(t != 0)
        if t != 0:
            i = self.cc.findData(code)
            self.cc.setCurrentIndex(max(0, i))
        self.tc.blockSignals(False)
        self.cc.blockSignals(False)

    def _type_changed(self, t):
        self.cc.blockSignals(True)
        self.cc.clear()
        for name, c in CODE_TABLE.get(t, []):
            self.cc.addItem(name, c)
        self.cc.setEnabled(t != 0)
        self.cc.blockSignals(False)
        self.store.set(self.key, 0 if t == 0 else t * 256 + (self.cc.itemData(0) or 0))

    def _code_changed(self, i):
        t = self.tc.currentIndex()
        if t and i >= 0:
            self.store.set(self.key, t * 256 + self.cc.itemData(i))

    def _ext(self, k):
        if k == self.key:
            self._fill(self.store.get(k))


class PKey(QWidget):
    """Pilih satu tombol keyboard (kode mentah)."""

    def __init__(self, store, key, text, parent=None):
        super().__init__(parent)
        from .params import KEYS
        self.store, self.key = store, key
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 2, 0, 2)
        h.addWidget(QLabel(text), 1)
        self.cb = QComboBox()
        for n, c in KEYS:
            self.cb.addItem(n, c)
        self.cb.setFixedWidth(150)
        self._ext(key)
        self.cb.currentIndexChanged.connect(lambda i: store.set(key, self.cb.itemData(i)))
        h.addWidget(self.cb)
        store.changed.connect(self._ext)
        store.bulk.connect(lambda: self._ext(self.key))

    def _ext(self, k):
        if k == self.key:
            self.cb.blockSignals(True)
            self.cb.setCurrentIndex(max(0, self.cb.findData(self.store.get(k))))
            self.cb.blockSignals(False)

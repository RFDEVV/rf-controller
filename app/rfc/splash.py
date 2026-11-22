"""Splash beranimasi: cincin menggambar diri, gelombang pulsa menyapu, lalu judul muncul."""
from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import APP_NAME
from .brand import paint_logo
from .theme import head_font


def _ease(t, a, b):
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return 1 - (1 - x) ** 3


class Splash(QWidget):
    finished = Signal()
    STEPS = ["Memuat pengaturan", "Menyiapkan tampilan", "Mencari perangkat", "Siap"]

    def __init__(self, theme, duration=2300):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.theme = theme
        self.t = 0.0
        self.resize(520, 340)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(duration if theme.animations else 400)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._tick)
        self._anim.finished.connect(self._fade_out)
        self._out = None

    def start(self):
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr:
            self.move(scr.center().x() - self.width() // 2, scr.center().y() - self.height() // 2)
        self.setWindowOpacity(0.0)
        self.show()
        fade = QVariantAnimation(self)
        fade.setDuration(220)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        fade.start()
        self._fade_in = fade
        self._anim.start()

    def _tick(self, v):
        self.t = float(v)
        self.update()

    def _fade_out(self):
        self._out = QVariantAnimation(self)
        self._out.setDuration(260)
        self._out.setStartValue(1.0)
        self._out.setEndValue(0.0)
        self._out.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._out.finished.connect(self._done)
        self._out.start()

    def _done(self):
        self.close()
        self.finished.emit()

    def paintEvent(self, _):
        c = self.theme.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["surface"]))
        p.drawRoundedRect(card, 22, 22)
        t = self.t
        size = 132
        logo = QRectF(card.center().x() - size / 2, card.top() + 38, size, size)
        paint_logo(p, logo, ring=_ease(t, 0.02, 0.40), pulse=_ease(t, 0.22, 0.62), plate=True)
        a = _ease(t, 0.50, 0.72)
        p.setOpacity(a)
        p.setPen(QColor(c["text"]))
        p.setFont(head_font(30, QFont.DemiBold))
        p.drawText(QRectF(card.left(), logo.bottom() + 14 + (1 - a) * 8, card.width(), 40), Qt.AlignCenter, APP_NAME)
        p.setOpacity(a * 0.9)
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(self.font().family(), 11))
        p.drawText(QRectF(card.left(), logo.bottom() + 54 + (1 - a) * 8, card.width(), 22), Qt.AlignCenter, "Remot RC jadi controller game")
        p.setOpacity(1.0)
        bar = QRectF(card.left() + 70, card.bottom() - 46, card.width() - 140, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["border"]))
        p.drawRoundedRect(bar, 2.5, 2.5)
        prog = _ease(t, 0.05, 0.97)
        p.setBrush(QColor(c["accent"]))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * prog, bar.height()), 2.5, 2.5)
        step = self.STEPS[min(len(self.STEPS) - 1, int(prog * len(self.STEPS)))]
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(self.font().family(), 10))
        p.drawText(QRectF(card.left(), bar.bottom() + 6, card.width(), 20), Qt.AlignCenter, step)

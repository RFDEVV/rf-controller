"""Gambar remot vektor (setir, trigger, CH3, CH4, dial) dengan panah penjelasan dan animasi langsung."""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QTransform
from PySide6.QtWidgets import QWidget

from . import widgets as W
from .params import short_act
from .theme import head_font

KIND_TEXT = {1: "klik 1x", 2: "klik 2x", 3: "klik 3x", 9: "tahan lama", 0: "tes"}


class RemoteView(QWidget):
    DW, DH = 440.0, 400.0   # ukuran area gambar remot
    SIDE = 205              # lebar kolom label kiri dan kanan

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setMinimumSize(900 - 160, 400)
        self.live = dict(p=[0, 0, 0, 0], sig=0, steer=0, thr=0, gas=0, brk=0)
        self.flash = {3: (0.0, ""), 4: (0.0, "")}
        self._sm = {"steer": 0.0, "thr": 0.0}
        self.t = QTimer(self)
        self.t.setInterval(16)
        self.t.timeout.connect(self._tick)
        self.t.start()

    def on_gesture(self, ch, kind, act):
        if ch in (3, 4):
            self.flash[ch] = (time.monotonic(), "%s → %s" % (KIND_TEXT.get(kind, "?"), short_act(act)))

    def _tick(self):
        k = 0.35
        self._sm["steer"] += (self.live.get("steer", 0) - self._sm["steer"]) * k
        self._sm["thr"] += (self.live.get("thr", 0) - self._sm["thr"]) * k
        self.update()

    # ------------------------------------------------------------ gambar
    def paintEvent(self, _):
        c = W.THEME.c
        s = self.store
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        sc = min((w - 2 * self.SIDE - 20) / self.DW, (h - 10) / self.DH)
        ox = (w - self.DW * sc) / 2
        oy = (h - self.DH * sc) / 2
        tr = QTransform()
        tr.translate(ox, oy)
        tr.scale(sc, sc)

        def to_screen(x, y):
            q = tr.map(QPointF(x, y))
            return q

        now = time.monotonic()
        steer, thr = self._sm["steer"], self._sm["thr"]
        pw = self.live.get("p", [0, 0, 0, 0])
        lit3 = pw[2] > s.get("c3_thr") if pw[2] else False
        lit4 = pw[3] > s.get("c4_thr") if pw[3] else False

        p.save()
        p.setTransform(tr)
        self._draw_remote(p, c, steer, thr, lit3, lit4, now)
        p.restore()

        # ---- panah dan label
        left_x, right_x = 8.0, w - self.SIDE - 8.0
        items = [
            # (nomor, anchor desain, sisi, y label, judul, baris, warna, kunci flash)
            (1, (352, 118), "R", h * 0.14, "Setir (roda samping)", ["Kiri / kanan = belok", "Sekarang: %s" % self._steer_text(steer)], "accent", None),
            (2, (306, 280), "R", h * 0.62, "Trigger (CH2)", ["Tarik = gas, dorong = rem", "Sekarang: %s" % self._thr_text(thr)], "amber", None),
            (3, (140, 205), "L", h * 0.40,  "CH3  (tombol kiri)",
             ["1x: %s" % short_act(s.get("a_c3_1")), "2x: %s" % short_act(s.get("a_c3_2")), "3x: %s" % short_act(s.get("a_c3_3"))], "teal", 3),
            (4, (182, 224), "L", h * 0.70, "CH4  (tombol kanan)",
             ["1x: %s" % short_act(s.get("a_c4_1")), "2x: %s" % short_act(s.get("a_c4_2")),
              "3x: %s" % short_act(s.get("a_c4_3")), "tahan: %s" % short_act(s.get("a_c4_l"))], "rose", 4),
            (5, (212, 132), "L", h * 0.08, "Dial dan trim", ["Diatur di remot sendiri", "tidak dibaca ESP32"], "muted", None),
        ]
        for num, anc, side, ly, title, lines, ck, fk in items:
            self._callout(p, c, to_screen(*anc), side, left_x if side == "L" else right_x, ly, num, title, lines, ck, fk, now)

    def _steer_text(self, v):
        v = int(round(v))
        return "netral" if v == 0 else ("kanan %d%%" % v if v > 0 else "kiri %d%%" % -v)

    def _thr_text(self, v):
        v = int(round(v))
        return "netral" if v == 0 else ("gas %d%%" % v if v > 0 else "rem %d%%" % -v)

    def _callout(self, p, c, anc, side, bx, by, num, title, lines, ck, fk, now):
        col = QColor(c[ck])
        bw = float(self.SIDE)
        lh = 16
        bh = 30 + lh * len(lines) + 8
        box = QRectF(bx, by, bw, bh)
        active = False
        ftext = ""
        if fk:
            t0, ftext = self.flash[fk]
            age = now - t0
            active = age < 1.6
        # kotak
        p.setPen(QPen(col if active else QColor(c["border"]), 1.6 if active else 1))
        bg = QColor(c["surface"])
        p.setBrush(bg)
        p.drawRoundedRect(box, 10, 10)
        # garis penghubung
        ex = box.right() if side == "L" else box.left()
        ey = by + 15
        path = QPainterPath(QPointF(ex, ey))
        mx = (ex + anc.x()) / 2
        path.cubicTo(QPointF(mx, ey), QPointF(mx, anc.y()), anc)
        glow = QColor(col)
        glow.setAlphaF(0.25)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(glow, 5, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(anc, 4, 4)
        # nomor
        nb = QRectF(box.left() + 8, by + 7, 18, 18)
        p.setBrush(col)
        p.drawEllipse(nb)
        p.setPen(QColor(c["accent_text"]))
        p.setFont(head_font(11))
        p.drawText(nb, Qt.AlignCenter, str(num))
        # teks
        p.setPen(QColor(c["text"]))
        p.setFont(head_font(12))
        p.drawText(QRectF(box.left() + 32, by + 5, bw - 38, 22), Qt.AlignLeft | Qt.AlignVCenter, title)
        f = QFont(self.font().family())
        f.setPixelSize(12)
        p.setFont(f)
        for i, ln in enumerate(lines):
            p.setPen(QColor(c["muted"] if ck == "muted" else c["text"]))
            p.drawText(QRectF(box.left() + 12, by + 30 + i * lh, bw - 18, lh), Qt.AlignLeft | Qt.AlignVCenter, ln)
        if active and ftext:
            fade = max(0.0, 1.0 - (now - self.flash[fk][0]) / 1.6)
            tag = QRectF(box.left(), box.bottom() + 4, bw, 22)
            bgc = QColor(col)
            bgc.setAlphaF(0.18 + 0.5 * fade)
            p.setPen(Qt.NoPen)
            p.setBrush(bgc)
            p.drawRoundedRect(tag, 8, 8)
            p.setPen(QColor(c["text"]))
            p.setFont(head_font(11))
            p.drawText(tag, Qt.AlignCenter, ftext)

    # ------------------------------------------------------------ badan remot
    def _draw_remote(self, p, c, steer, thr, lit3, lit4, now):
        dark = W.THEME.dark
        body_top = QColor("#2A3547") if dark else QColor("#3A4658")
        body_bot = QColor("#121823") if dark else QColor("#1E2733")
        edge = QColor("#4A5A72") if dark else QColor("#0E1520")
        # bayangan lantai
        sh = QRadialGradient(QPointF(215, 392), 150)
        sh.setColorAt(0, QColor(0, 0, 0, 70 if dark else 40))
        sh.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(sh)
        p.drawEllipse(QPointF(215, 392), 150, 14)

        # genggaman
        grip = QPainterPath()
        grip.moveTo(160, 205)
        grip.lineTo(262, 215)
        grip.cubicTo(278, 280, 270, 345, 252, 384)
        grip.lineTo(190, 384)
        grip.cubicTo(165, 335, 150, 265, 160, 205)
        g = QLinearGradient(QPointF(160, 220), QPointF(270, 380))
        g.setColorAt(0, body_top)
        g.setColorAt(1, body_bot)
        p.setPen(QPen(edge, 1.4))
        p.setBrush(QBrush(g))
        p.drawPath(grip)
        p.setPen(QPen(QColor(0, 0, 0, 80), 2))
        for i in range(6):          # alur genggaman
            y = 262 + i * 18
            p.drawLine(QPointF(178 + i * 2, y), QPointF(256 - i * 2, y + 6))

        # bodi atas
        p.save()
        p.translate(215, 158)
        p.rotate(-9)
        top = QPainterPath()
        top.addRoundedRect(QRectF(-125, -62, 250, 124), 58, 58)
        g2 = QLinearGradient(QPointF(0, -62), QPointF(0, 62))
        g2.setColorAt(0, body_top)
        g2.setColorAt(1, body_bot)
        p.setPen(QPen(edge, 1.6))
        p.setBrush(QBrush(g2))
        p.drawPath(top)
        p.restore()

        # trigger
        p.save()
        p.translate(300, 238)
        p.rotate(max(-35.0, min(35.0, thr * 0.32)))
        tcol = QColor(c["amber"]) if thr > 4 else (QColor(c["danger"]) if thr < -4 else QColor("#5B6B82"))
        tgr = QPainterPath()
        tgr.addRoundedRect(QRectF(-8, -2, 17, 58), 8, 8)
        if abs(thr) > 4:
            glow = QColor(tcol)
            glow.setAlphaF(0.35)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(QRectF(-14, -6, 29, 66), 12, 12)
        p.setPen(QPen(edge, 1.2))
        p.setBrush(tcol)
        p.drawPath(tgr)
        p.restore()

        # roda
        self._wheel(p, c, steer, edge)

        # tombol +/- dan dial
        p.setPen(QPen(edge, 1))
        p.setBrush(QColor("#3B4860" if dark else "#46556D"))
        for (x, y) in ((176, 120), (252, 112)):
            p.drawEllipse(QPointF(x, y), 8, 8)
        p.setPen(QPen(QColor("#9FB0C8"), 1.4))
        p.drawLine(QPointF(172, 120), QPointF(180, 120))
        p.drawLine(QPointF(176, 116), QPointF(176, 124))
        p.drawLine(QPointF(248, 112), QPointF(256, 112))
        dial = QRadialGradient(QPointF(212, 132), 26)
        dial.setColorAt(0, QColor("#55667F"))
        dial.setColorAt(1, QColor("#1B2434"))
        p.setPen(QPen(edge, 1.4))
        p.setBrush(QBrush(dial))
        p.drawEllipse(QPointF(212, 132), 24, 24)
        p.setPen(QPen(QColor(c["accent"]), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(212, 132), QPointF(222, 116))
        p.setPen(QPen(QColor(c["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(184, 104, 56, 56), 40 * 16, 260 * 16)

        # saklar ON/OFF
        p.setPen(QPen(edge, 1))
        p.setBrush(QColor("#0E1520"))
        p.drawRoundedRect(QRectF(108, 236, 34, 14), 5, 5)
        p.setBrush(QColor(c["teal"]))
        p.drawRoundedRect(QRectF(111, 238, 14, 10), 3, 3)

        # CH3 dan CH4
        self._btn(p, c, QPointF(140, 205), "CH3", lit3, "teal", now, 3)
        self._btn(p, c, QPointF(182, 224), "CH4", lit4, "rose", now, 4)

    def _btn(self, p, c, ctr, name, lit, ck, now, ch):
        col = QColor(c[ck])
        t0, _ = self.flash[ch]
        age = now - t0
        if age < 0.9:
            k = age / 0.9
            ring = QColor(col)
            ring.setAlphaF(0.7 * (1 - k))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(ring, 3))
            p.drawEllipse(ctr, 12 + 22 * k, 12 + 22 * k)
        if lit:
            glow = QColor(col)
            glow.setAlphaF(0.4)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(ctr, 17, 17)
        g = QRadialGradient(ctr - QPointF(3, 3), 14)
        g.setColorAt(0, col.lighter(130) if lit else QColor("#55667F"))
        g.setColorAt(1, col if lit else QColor("#1E2838"))
        p.setPen(QPen(QColor("#0B111A"), 1.2))
        p.setBrush(QBrush(g))
        p.drawEllipse(ctr, 11, 11)
        p.setPen(QColor("#C7D3E6"))
        f = QFont(self.font().family())
        f.setPixelSize(8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(ctr.x() - 16, ctr.y() + 13, 32, 10), Qt.AlignCenter, name)

    def _wheel(self, p, c, steer, edge):
        ctr = QPointF(352, 170)
        rx, ry = 56.0, 74.0
        active = abs(steer) > 4
        if active:
            glow = QColor(c["accent"])
            glow.setAlphaF(0.30)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(ctr, rx + 12, ry + 12)
        p.setPen(QPen(edge, 1.6))
        p.setBrush(QColor("#0E141E"))
        p.drawEllipse(ctr, rx, ry)                       # ban
        p.setBrush(QColor("#1C2636"))
        p.drawEllipse(ctr, rx - 14, ry - 17)             # velg
        p.setBrush(QColor("#7C8CA6"))
        p.setPen(QPen(QColor("#2A364A"), 1))
        ang = steer * 0.55
        p.save()
        p.translate(ctr)
        p.rotate(ang)
        for i in range(5):
            p.save()
            p.rotate(i * 72)
            sp = QPainterPath()
            sp.moveTo(-6, 0)
            sp.lineTo(-4, -(ry - 22))
            sp.lineTo(4, -(ry - 22))
            sp.lineTo(6, 0)
            sp.closeSubpath()
            p.setBrush(QColor("#8FA0BB"))
            p.drawPath(sp)
            p.restore()
        p.setBrush(QColor("#CBD5E6"))
        p.setPen(QPen(QColor("#2A364A"), 1))
        p.drawEllipse(QPointF(0, 0), 11, 13)
        p.restore()
        if active:                                       # panah arah belok
            col = QColor(c["accent"])
            p.setPen(QPen(col, 3, Qt.SolidLine, Qt.RoundCap))
            d = 1 if steer > 0 else -1
            x0 = ctr.x() + d * 6
            y0 = ctr.y() - ry - 14
            p.drawLine(QPointF(x0 - d * 22, y0), QPointF(x0 + d * 22, y0))
            p.drawLine(QPointF(x0 + d * 22, y0), QPointF(x0 + d * 14, y0 - 6))
            p.drawLine(QPointF(x0 + d * 22, y0), QPointF(x0 + d * 14, y0 + 6))

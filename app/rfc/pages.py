"""Halaman-halaman aplikasi."""
import json
import os
import time

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
                               QComboBox)

from .flasher import Flasher
from .link import Link
from .params import DEFAULTS, PARAMS, PRESETS, resource_path
from .widgets import (AnimBar, Card, CurveView, GearDial, Lamp, PAction, PKey, PSeg, PSlider, PSpin, PSwitch, Scope,
                      label, make_anim)
from . import widgets as W


class Ctx(QObject):
    """Objek bersama yang dipakai semua halaman."""

    def __init__(self, store, link_getter, theme, toast, flasher):
        super().__init__()
        self.store, self.theme, self.toast, self.flasher = store, theme, toast, flasher
        self._link = link_getter
        self.restart = lambda: None

    @property
    def link(self):
        return self._link()


class Page(QScrollArea):
    title = ""
    subtitle = ""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("page")
        self.setWidget(body)
        self.col = QVBoxLayout(body)
        self.col.setContentsMargins(28, 8, 28, 28)
        self.col.setSpacing(16)

    def feed_live(self, d):
        pass

    def finish(self):
        self.col.addStretch(1)


def row2(a, b, ratio=(1, 1)):
    h = QHBoxLayout()
    h.setSpacing(16)
    h.addWidget(a, ratio[0])
    h.addWidget(b, ratio[1])
    return h


# =============================================================== Dashboard
class RemoteMap(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.pulses = [0, 0, 0, 0]
        self.setMinimumHeight(138)
        self.setToolTip("Peta fungsi channel remot")
        theme.changed.connect(self.update)

    def set_pulses(self, pulses):
        self.pulses = pulses
        self.update()

    def paintEvent(self, _):
        c = self.theme.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        body = QRectF(self.rect()).adjusted(w * 0.415, 20, -w * 0.415, -20)
        p.setPen(QPen(QColor(c["border"]), 1.5))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(body, 18, 18)
        wheel = body.center().x() - 13
        p.setPen(QPen(QColor(c["accent"]), 3))
        p.drawEllipse(QRectF(wheel - 16, mid - 16, 32, 32))
        p.setPen(QPen(QColor(c["muted"]), 2))
        p.drawLine(QPointF(wheel, mid - 13), QPointF(wheel, mid + 13))
        p.drawLine(QPointF(wheel - 12, mid), QPointF(wheel + 12, mid))
        p.setPen(QPen(QColor(c["amber"]), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(body.right() - 20, mid - 25), QPointF(body.right() - 20, mid + 3))
        for i, key in enumerate(("teal", "rose")):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c[key]))
            p.drawEllipse(QPointF(body.right() - 20, mid + 20 + i * 13), 4, 4)

        font = p.font()
        font.setPixelSize(10)
        p.setFont(font)
        entries = [
            (0, "CH1  Setir", c["accent"], 4, mid - 22, wheel - 18, mid - 5, Qt.AlignLeft),
            (2, "CH3  Klik 1/2/3", c["teal"], 4, mid + 29, body.right() - 22, mid + 20, Qt.AlignLeft),
            (1, "CH2  Gas / rem", c["amber"], w - 122, mid - 22, body.right() - 18, mid - 16, Qt.AlignRight),
            (3, "CH4  Klik / tahan", c["rose"], w - 122, mid + 29, body.right() - 20, mid + 33, Qt.AlignRight),
        ]
        for idx, text, color, tx, ty, ex, ey, align in entries:
            pulse = "—" if not self.pulses[idx] else "%d µs" % self.pulses[idx]
            p.setPen(QColor(color))
            p.drawText(QRectF(tx, ty - 12, 118, 15), align | Qt.AlignVCenter, text)
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(tx, ty + 2, 118, 14), align | Qt.AlignVCenter, pulse)
            start_x = tx + 118 if align == Qt.AlignLeft else tx
            p.setPen(QPen(QColor(color), 1.4))
            p.drawLine(QPointF(start_x, ty + 5), QPointF(ex, ey))
            p.setBrush(QColor(color))
            direction = 1 if ex > start_x else -1
            arrow = QPainterPath(QPointF(ex, ey))
            arrow.lineTo(ex - direction * 6, ey - 3)
            arrow.lineTo(ex - direction * 6, ey + 3)
            arrow.closeSubpath()
            p.drawPath(arrow)


class Dashboard(Page):
    title = "Dashboard"
    subtitle = "Pantau remot secara langsung"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        left = Card()
        self.dial = W.GearDial()
        left.v.addWidget(self.dial, 1)
        self.remote = RemoteMap(ctx.theme)
        left.v.addWidget(self.remote)
        chips = QHBoxLayout()
        self.b_mode = QPushButton("Gigi: otomatis")
        self.b_lock = QPushButton("Kunci gigi")
        self.b_out = QPushButton("Output: gamepad")
        for b, code in ((self.b_mode, 3), (self.b_lock, 4), (self.b_out, 5)):
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self.sys(c))
            chips.addWidget(b)
        left.v.addLayout(chips)

        right = QVBoxLayout()
        right.setSpacing(16)
        sc = Card("Pulsa channel (12 detik terakhir)")
        self.scope = Scope()
        sc.v.addWidget(self.scope, 1)
        self.legend = QLabel()
        sc.v.addWidget(self.legend)
        right.addWidget(sc, 3)
        bars = Card()
        self.b_steer = AnimBar("Setir", -100, 100, center=True, color="accent")
        self.b_gas = AnimBar("Gas", 0, 100, color="amber")
        self.b_brk = AnimBar("Rem", 0, 100, color="danger")
        for b in (self.b_steer, self.b_gas, self.b_brk):
            bars.v.addWidget(b)
        right.addWidget(bars, 2)
        h = QHBoxLayout()
        h.setSpacing(16)
        h.addWidget(left, 4)
        rw = QWidget()
        rw.setLayout(right)
        h.addWidget(rw, 6)
        self.col.addLayout(h, 1)
        self.last_p = [0, 0, 0, 0]
        ctx.theme.changed.connect(self._legend)
        self._legend()
        s.changed.connect(lambda k: self._refresh_btn() if k in ("gear_mode", "out_mode") else None)
        self._lock = False
        self._refresh_btn()

    def sys(self, code):
        if self.ctx.link and self.ctx.link.is_on():
            self.ctx.link.send("SYS %d" % code)
        else:
            self.ctx.toast.show_text("Hubungkan perangkat dulu", bad=True)

    def _refresh_btn(self):
        s = self.ctx.store
        self.b_mode.setText("Gigi: " + ["mati", "otomatis", "manual"][s.get("gear_mode")])
        self.b_out.setText("Output: " + ["gamepad", "keyboard", "mouse"][s.get("out_mode")])
        self.b_lock.setText("Gigi terkunci" if self._lock else "Kunci gigi")
        self.b_lock.setProperty("kind", "primary" if self._lock else "")
        self.b_lock.style().unpolish(self.b_lock)
        self.b_lock.style().polish(self.b_lock)

    def _legend(self):
        c = self.ctx.theme.c
        names = ["CH1 setir", "CH2 gas", "CH3", "CH4"]
        cols = ["accent", "amber", "teal", "rose"]
        parts = ["<span style='color:%s'>●</span> %s <b>%d µs</b>" % (c[cols[i]], names[i], self.last_p[i]) for i in range(4)]
        self.legend.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(parts))

    def feed_live(self, d):
        s = self.ctx.store
        self.scope.push(d["p"], d["sig"])
        self.last_p = d["p"]
        self.remote.set_pulses(d["p"])
        gm = s.get("gear_mode")
        th = [s.get("g_t%d" % i) for i in range(1, s.get("g_max") + 1)] if gm == 1 else []
        self.dial.set_state(d["gas"], d["brk"], d["gear"], d["st"], bool(d["rev"]), bool(d["lock"]), th)
        self.b_steer.set_value(d["steer"])
        self.b_gas.set_value(d["gas"])
        self.b_brk.set_value(d["brk"])
        self._lock = bool(d["lock"])
        self._refresh_btn()
        if int(time.monotonic() * 4) % 2 == 0:
            self._legend()


# =============================================================== Kalibrasi
class ChannelCard(Card):
    def __init__(self, ctx, n, name, analog):
        super().__init__("CH%d  %s" % (n, name))
        self.ctx, self.n, self.analog = ctx, n, analog
        s = ctx.store
        self.pw = 0
        self.lo = self.hi = None
        self.rec = False
        top = QHBoxLayout()
        self.num = QLabel("—")
        self.num.setProperty("role", "title")
        top.addWidget(self.num)
        top.addStretch(1)
        self.lamp = Lamp()
        self.stat = label("", "muted")
        top.addWidget(self.lamp)
        top.addWidget(self.stat)
        self.v.addLayout(top)
        self.bar = AnimBar("", 800, 2200, color=["accent", "amber", "teal", "rose"][n - 1], unit="µs")
        self.bar.setFixedHeight(30)
        self.v.addWidget(self.bar)
        self.seen = label("Rentang terekam: —", "muted")
        self.v.addWidget(self.seen)
        if analog:
            row = QHBoxLayout()
            b1 = QPushButton("Tandai tengah")
            self.b_rec = QPushButton("Rekam min / maks")
            self.b_rec.setCheckable(True)
            b1.clicked.connect(self.mark_mid)
            self.b_rec.toggled.connect(self.toggle_rec)
            row.addWidget(b1)
            row.addWidget(self.b_rec)
            self.v.addLayout(row)
            for k, t in (("c%d_min" % n, "Pulsa minimum"), ("c%d_mid" % n, "Pulsa tengah"), ("c%d_max" % n, "Pulsa maksimum")):
                self.v.addWidget(PSpin(s, k, t, " µs"))
            self.v.addWidget(PSwitch(s, "inv%d" % n, "Balik arah"))
        else:
            self.v.addWidget(PSeg(s, "c%d_type" % n, [
                ("Ditahan", 0), ("Pulsa sekali", 1), ("Toggle", 2),
            ]))
            self.v.addWidget(PSpin(s, "c%d_thr" % n, "Ambang tinggi/rendah", " µs"))
            row = QHBoxLayout()
            self.low, self.high = None, None
            bl, bh = QPushButton("Tandai rendah"), QPushButton("Tandai tinggi")
            bl.clicked.connect(lambda: self.mark_level(False))
            bh.clicked.connect(lambda: self.mark_level(True))
            row.addWidget(bl)
            row.addWidget(bh)
            self.v.addLayout(row)

    def mark_mid(self):
        if self.pw:
            self.ctx.store.set("c%d_mid" % self.n, self.pw)
            self.ctx.toast.show_text("Tengah CH%d = %d µs" % (self.n, self.pw))

    def toggle_rec(self, on):
        self.rec = on
        self.b_rec.setText("Berhenti dan terapkan" if on else "Rekam min / maks")
        if on:
            self.lo = self.hi = None
        elif self.lo is not None and self.hi - self.lo >= 100:
            st = self.ctx.store
            st.set("c%d_min" % self.n, self.lo)
            st.set("c%d_max" % self.n, self.hi)
            self.ctx.toast.show_text("Min %d, maks %d µs diterapkan" % (self.lo, self.hi))

    def mark_level(self, high):
        if not self.pw:
            return
        if high:
            self.high = self.pw
        else:
            self.low = self.pw
        if self.low and self.high and abs(self.high - self.low) >= 60:
            thr = (self.low + self.high) // 2
            self.ctx.store.set("c%d_thr" % self.n, thr)
            self.ctx.toast.show_text("Ambang CH%d = %d µs" % (self.n, thr))

    def feed(self, p, sig):
        self.pw = p
        self.num.setText("%d µs" % p if p else "—")
        self.bar.set_value(p if p else 800)
        if p:
            if self.rec or not self.analog:
                self.lo = p if self.lo is None else min(self.lo, p)
                self.hi = p if self.hi is None else max(self.hi, p)
            if self.lo is not None:
                self.seen.setText("Rentang terekam: %d – %d µs" % (self.lo, self.hi))
        if self.analog:
            self.lamp.set_on(bool(p))
            self.stat.setText("sinyal ada" if p else "tidak ada sinyal")
        else:
            thr = self.ctx.store.get("c%d_thr" % self.n)
            on = p > thr
            self.lamp.set_on(on)
            self.stat.setText("tinggi" if on else "rendah")


class Calibration(Page):
    title = "Pulsa dan kalibrasi"
    subtitle = "Lihat pulsa mentah dan atur rentang tiap channel"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cards = [ChannelCard(ctx, 1, "Setir", True), ChannelCard(ctx, 2, "Gas dan rem", True),
                      ChannelCard(ctx, 3, "Tombol 3", False), ChannelCard(ctx, 4, "Tombol 4", False)]
        g = QGridLayout()
        g.setSpacing(16)
        for i, c in enumerate(self.cards):
            g.addWidget(c, i // 2, i % 2)
        self.col.addLayout(g)
        self.col.addWidget(label("Tips: pulsa tombol CH3/CH4 di remot ini sekitar 900 dan 1200 µs. Tandai posisi rendah dan tinggi, ambang otomatis di tengahnya.", "muted", True))
        self.finish()

    def feed_live(self, d):
        for i, c in enumerate(self.cards):
            c.feed(d["p"][i], d["sig"])


# =============================================================== Setir & Gas
class SteerThrottle(Page):
    title = "Setir dan gas"
    subtitle = "Zona mati, peredam noise, kurva respons, dan logika rem/mundur"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        self.curves = []
        for n, name, lim in ((1, "Setir (CH1)", "st_limit"), (2, "Gas dan rem (CH2)", "thr_limit")):
            card = Card(name)
            cv = CurveView(s, n)
            cv.setFixedWidth(210)
            self.curves.append(cv)
            f = QVBoxLayout()
            f.addWidget(PSwitch(s, "inv%d" % n, "Balik arah gas / rem" if n == 2 else "Balik arah setir"))
            f.addWidget(PSlider(s, "dz%d" % n, "Zona mati", "%"))
            f.addWidget(PSlider(s, "ex%d" % n, "Kurva halus (ekspo)", "%"))
            f.addWidget(PSlider(s, "flt%d" % n, "Peredam noise", "%"))
            f.addWidget(PSlider(s, "nb%d" % n, "Pita netral anti-noise", "µs"))
            f.addWidget(PSlider(s, lim, "Batas maksimum", "%"))
            h = QHBoxLayout()
            h.setSpacing(18)
            h.addWidget(cv)
            h.addLayout(f, 1)
            card.v.addLayout(h)
            self.col.addWidget(card)
        rv = Card("Rem dan mundur")
        rv.v.addWidget(PSwitch(s, "rev_logic", "Logika rem lalu mundur",
                               "Tuas didorong saat melaju: rem dulu. Setelah netral dan didorong lagi: tombol gigi R ditekan dan mobil mundur."))
        rv.v.addWidget(PSlider(s, "brk_th", "Ambang mulai rem/mundur", "%"))
        rv.v.addWidget(PSlider(s, "nz", "Lebar zona netral", "%"))
        rv.v.addWidget(PSlider(s, "settle_ms", "Waktu tuas harus netral", "ms"))
        self.col.addWidget(rv)
        self.finish()

    def feed_live(self, d):
        self.curves[0].set_pulse(d["p"][0])
        self.curves[1].set_pulse(d["p"][1])


# =============================================================== Gigi
class Gears(Page):
    title = "Gigi"
    subtitle = "Otomatis menurut gas, atau manual lewat CH3"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        mode = Card("Mode gigi")
        mode.v.addWidget(PSeg(s, "gear_mode", [("Mati", 0), ("Otomatis", 1), ("Manual", 2)]))
        mode.v.addWidget(label("Otomatis: gigi naik dan turun mengikuti persentase gas. Manual: gigi hanya berubah lewat aksi Naik/Turun gigi di menu Tombol. Mati: tidak ada tombol gigi yang ditekan.", "muted", True))
        self.col.addWidget(mode)

        th = Card("Ambang gas per gigi")
        self.bar = AnimBar("Gas sekarang", 0, 100, color="amber")
        th.v.addWidget(self.bar)
        for i in range(1, 7):
            th.v.addWidget(PSlider(s, "g_t%d" % i, "Gigi %d aktif di gas ≥" % i, "%"))
        th.v.addWidget(PSlider(s, "g_max", "Gigi tertinggi", ""))
        th.v.addWidget(PSlider(s, "g_hyst", "Histeresis turun", "%"))
        th.v.addWidget(PSlider(s, "g_dwell", "Jeda minimal antar pindah gigi", "ms"))
        self.col.addWidget(th)
        s.changed.connect(self._mark)
        s.bulk.connect(lambda: self._mark("g_t1"))
        self._mark("g_t1")

        act = Card("Tombol yang ditekan")
        for k, t in (("a_gup", "Naik gigi"), ("a_gdn", "Turun gigi"), ("a_gr", "Gigi R (mundur)"), ("a_gdrive", "Keluar dari R (opsional)")):
            act.v.addWidget(PAction(s, k, t))
        act.v.addWidget(PSwitch(s, "g_direct", "Tombol langsung per gigi", "Tiap gigi punya tombolnya sendiri (misalnya angka 1 sampai 6), bukan naik/turun."))
        for i in range(1, 7):
            act.v.addWidget(PAction(s, "gk%d" % i, "Tombol gigi %d" % i))
        self.col.addWidget(act)
        self.finish()

    def _mark(self, k):
        if k.startswith("g_t") or k == "g_max":
            s = self.ctx.store
            self.bar.markers = [s.get("g_t%d" % i) for i in range(1, s.get("g_max") + 1)]
            self.bar.update()

    def feed_live(self, d):
        self.bar.set_value(d["gas"])


# =============================================================== Tombol
class Buttons(Page):
    title = "Tombol dan gestur"
    subtitle = "Klik 1x, 2x, 3x, tahan lama, dan aturan pulsa"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        c3 = Card("CH3  (tombol / pulsa)")
        c3.v.addWidget(PAction(s, "a_c3_1", "Klik 1x"))
        c3.v.addWidget(PAction(s, "a_c3_2", "Klik 2x"))
        c3.v.addWidget(PAction(s, "a_c3_3", "Klik 3x"))
        c3.v.addWidget(label("Pilih mode pulsa untuk hitung satu klik saat sinyal naik, atau mode toggle jika remot mengubah level tiap tekanan. Jenis dan ambang di menu Deteksi pulsa.", "muted", True))
        self.col.addWidget(c3)
        c4 = Card("CH4  (tombol / pulsa)")
        c4.v.addWidget(PAction(s, "a_c4_1", "Klik 1x"))
        c4.v.addWidget(PAction(s, "a_c4_2", "Klik 2x"))
        c4.v.addWidget(PAction(s, "a_c4_3", "Klik 3x"))
        c4.v.addWidget(PAction(s, "a_c4_l", "Tahan lama"))
        c4.v.addWidget(label("Mode momentary membaca klik dan tahan. Mode pulsa membaca satu klik tiap pulsa naik; mode toggle membaca setiap perubahan level.", "muted", True))
        c4.v.addWidget(label("Preset Gamepad balap memetakan CH3/CH4 ke tombol gamepad A/B/X/Y, LB/RB, dan Start. Pemetaan ini tidak mengirim tombol keyboard.", "muted", True))
        self.col.addWidget(c4)
        tm = Card("Waktu gestur")
        tm.v.addWidget(PSlider(s, "click_ms", "Jeda antar klik", "ms"))
        tm.v.addWidget(PSlider(s, "long_ms", "Dianggap tahan lama setelah", "ms"))
        tm.v.addWidget(PSlider(s, "tap_ms", "Lama tombol ditekan saat klik", "ms"))
        self.col.addWidget(tm)
        pr = Card("Aturan pulsa")
        pr.v.addWidget(label("Aksi aktif selama pulsa sebuah channel berada di rentang yang kamu tentukan.", "muted", True))
        for i in range(1, 7):
            box = QFrame()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 8, 0, 4)
            bl.addWidget(PSeg(s, "pr%d_ch" % i, [("Mati", 0), ("CH1", 1), ("CH2", 2), ("CH3", 3), ("CH4", 4)]))
            r = QHBoxLayout()
            r.addWidget(PSpin(s, "pr%d_lo" % i, "Dari", " µs"))
            r.addSpacing(16)
            r.addWidget(PSpin(s, "pr%d_hi" % i, "Sampai", " µs"))
            bl.addLayout(r)
            bl.addWidget(PAction(s, "pr%d_a" % i, "Aksi"))
            if i < 6:
                ln = QFrame()
                ln.setFrameShape(QFrame.HLine)
                ln.setStyleSheet("color: %s;" % ctx.theme.c["border"])
                bl.addWidget(ln)
            pr.v.addWidget(box)
        self.col.addWidget(pr)
        self.finish()


# =============================================================== Output
class Output(Page):
    title = "Output"
    subtitle = "Pilih cara ESP32 tampil di PC"

    DESC = [
        "Gamepad: setir menjadi sumbu stik, gas dan rem sumbu terpisah. ESP32 tampil sebagai HID generik, bukan Xbox XInput; MSI App Player atau game tertentu mungkin tidak mendeteksinya. Untuk emulator, coba preset MSI App Player (keyboard WASD).",
        "Keyboard: setir menekan tombol kiri/kanan, gas dan rem menekan tombol maju/mundur. Mode halus memakai pulsa cepat untuk mendekati analog; beberapa game lebih stabil dengan mode halus dimatikan.",
        "Mouse: setir menggerakkan kursor ke kiri/kanan, gas dan rem tetap lewat tombol keyboard maju/mundur.",
    ]

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        c = Card("Mode output")
        c.v.addWidget(PSeg(s, "out_mode", [("Gamepad", 0), ("Keyboard", 1), ("Mouse", 2)]))
        self.desc = label("", "muted", True)
        c.v.addWidget(self.desc)
        self.col.addWidget(c)
        k = Card("Tombol keyboard untuk setir, gas, dan rem")
        for key, t in (("k_left", "Setir kiri"), ("k_right", "Setir kanan"), ("k_fwd", "Gas / maju"), ("k_back", "Rem / mundur")):
            k.v.addWidget(PKey(s, key, t))
        k.v.addWidget(PSwitch(s, "kb_pwm", "Mode halus (berkedip)", "Tombol ditekan-lepas cepat sesuai besar putaran, meniru analog."))
        k.v.addWidget(PSlider(s, "kb_period", "Periode kedip", "ms"))
        k.v.addWidget(PSlider(s, "kb_dz", "Ambang mulai menekan", "%"))
        self.col.addWidget(k)
        m = Card("Mouse")
        m.v.addWidget(PSlider(s, "m_speed", "Kecepatan kursor", ""))
        self.col.addWidget(m)
        sf = Card("Keamanan")
        sf.v.addWidget(PSlider(s, "failsafe_ms", "Lepas semua tombol jika sinyal hilang", "ms"))
        self.col.addWidget(sf)
        s.changed.connect(lambda key: self._desc() if key == "out_mode" else None)
        s.bulk.connect(self._desc)
        self._desc()
        self.finish()

    def _desc(self):
        self.desc.setText(self.DESC[self.ctx.store.get("out_mode")])


# =============================================================== Profil
def profile_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "RFController", "profiles")
    os.makedirs(d, exist_ok=True)
    return d


class Profiles(Page):
    title = "Profil"
    subtitle = "Simpan pengaturan per game dan terapkan sekali klik"

    def __init__(self, ctx):
        super().__init__(ctx)
        pre = Card("Preset bawaan")
        self.preset = QComboBox()
        for n in PRESETS:
            self.preset.addItem(n)
        ap = QPushButton("Terapkan preset")
        ap.clicked.connect(self.apply_preset)
        h = QHBoxLayout()
        h.addWidget(self.preset, 1)
        h.addWidget(ap)
        pre.v.addLayout(h)
        self.col.addWidget(pre)
        mine = Card("Profil saya")
        self.lst = QListWidget()
        self.lst.setMinimumHeight(180)
        self.lst.itemDoubleClicked.connect(lambda _: self.apply())
        mine.v.addWidget(self.lst)
        r = QHBoxLayout()
        for text, fn, kind in (("Terapkan", self.apply, "primary"), ("Simpan pengaturan saat ini…", self.save_new, ""),
                               ("Hapus", self.delete, ""), ("Impor…", self.imp, ""), ("Ekspor…", self.exp, "")):
            b = QPushButton(text)
            if kind:
                b.setProperty("kind", kind)
            b.clicked.connect(fn)
            r.addWidget(b)
        mine.v.addLayout(r)
        self.col.addWidget(mine)
        rs = Card("Setel ulang")
        b = QPushButton("Kembalikan semua ke bawaan")
        b.clicked.connect(self.reset)
        rs.v.addWidget(b)
        self.col.addWidget(rs)
        self.finish()
        self.refresh()

    def refresh(self):
        self.lst.clear()
        for f in sorted(os.listdir(profile_dir())):
            if f.endswith(".json"):
                self.lst.addItem(f[:-5])

    def _cur(self):
        it = self.lst.currentItem()
        return os.path.join(profile_dir(), it.text() + ".json") if it else None

    def apply_preset(self):
        d = dict(DEFAULTS)
        d.update(PRESETS[self.preset.currentText()])
        self._apply(d, self.preset.currentText())

    def _apply(self, d, name):
        self.ctx.store.load_profile(d, send=True)
        self.ctx.toast.show_text("Profil “%s” diterapkan" % name)

    def apply(self):
        p = self._cur()
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                self._apply(json.load(f)["params"], os.path.basename(p)[:-5])
        except (OSError, KeyError, ValueError):
            self.ctx.toast.show_text("File profil rusak", bad=True)

    def save_new(self):
        name, ok = QInputDialog.getText(self, "Simpan profil", "Nama profil (misalnya nama game):")
        name = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
        if ok and name:
            with open(os.path.join(profile_dir(), name + ".json"), "w", encoding="utf-8") as f:
                json.dump({"name": name, "version": 1, "params": self.ctx.store.v}, f, indent=1)
            self.refresh()
            self.ctx.toast.show_text("Profil “%s” tersimpan" % name)

    def delete(self):
        p = self._cur()
        if p and QMessageBox.question(self, "Hapus profil", "Hapus profil ini?") == QMessageBox.Yes:
            os.remove(p)
            self.refresh()

    def imp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Impor profil", "", "Profil (*.json)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)["params"]
                self._apply(d, os.path.basename(path)[:-5])
            except (OSError, KeyError, ValueError):
                self.ctx.toast.show_text("File bukan profil yang valid", bad=True)

    def exp(self):
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor profil", "profil.json", "Profil (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"name": os.path.basename(path), "version": 1, "params": self.ctx.store.v}, f, indent=1)

    def reset(self):
        if QMessageBox.question(self, "Setel ulang", "Kembalikan semua pengaturan ke bawaan?") == QMessageBox.Yes:
            self.ctx.store.reset_defaults()
            self.ctx.toast.show_text("Pengaturan dikembalikan ke bawaan")


# =============================================================== Firmware
class Firmware(Page):
    title = "Firmware"
    subtitle = "Pasang firmware RF Controller ke ESP32-S3"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.fl = ctx.flasher
        info = Card("Firmware")
        self.info = label("", "muted", True)
        info.v.addWidget(self.info)
        self.bundled = resource_path(os.path.join("fw", "rf-controller-merged.bin"))
        self.col.addWidget(info)
        fl = Card("Flash")
        r = QHBoxLayout()
        self.ports = QComboBox()
        rf = QPushButton("Segarkan")
        rf.clicked.connect(self.refresh_ports)
        r.addWidget(self.ports, 1)
        r.addWidget(rf)
        fl.v.addLayout(r)
        r2 = QHBoxLayout()
        self.b_boot = QPushButton("Masuk mode flash otomatis")
        self.b_boot.clicked.connect(self.enter_boot)
        self.b_flash = QPushButton("Flash firmware bawaan")
        self.b_flash.setProperty("kind", "primary")
        self.b_flash.clicked.connect(lambda: self.flash(self.bundled))
        self.b_file = QPushButton("Pilih file .bin…")
        self.b_file.clicked.connect(self.pick)
        for b in (self.b_boot, self.b_flash, self.b_file):
            r2.addWidget(b)
        fl.v.addLayout(r2)
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setTextVisible(False)
        fl.v.addWidget(self.prog)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)
        fl.v.addWidget(self.log)
        fl.v.addWidget(label("Cara manual: tahan tombol BOOT di board, tekan RESET sekali, lepas BOOT. Port baru muncul (VID 303A), pilih di atas lalu tekan Flash. Pakai port USB yang berlabel USB (bukan UART).", "muted", True))
        self.col.addWidget(fl)
        self.fl.log.connect(self.on_log)
        self.fl.progress.connect(self.prog.setValue)
        self.fl.done.connect(self.on_done)
        self.finish()
        self.refresh_ports()
        self.update_info()

    def update_info(self):
        have = os.path.isfile(self.bundled)
        fw = self.ctx.link.fw if self.ctx.link and self.ctx.link.is_on() else ""
        txt = "Firmware terdeteksi di perangkat: %s. " % fw if fw else "Belum ada perangkat terhubung. "
        txt += "Firmware bawaan aplikasi tersedia." if have else "Firmware bawaan tidak disertakan di versi ini, pilih file .bin secara manual."
        self.info.setText(txt)
        self.b_flash.setEnabled(have and not self.fl.busy())

    def refresh_ports(self):
        self.ports.clear()
        for name, text, rf in Link.list_ports():
            self.ports.addItem(text + ("   ← ESP32" if rf else ""), name)

    def enter_boot(self):
        link = self.ctx.link
        if link and link.is_on() and not link.demo:
            link.send("BOOTLOADER")
            self.on_log("Perintah masuk mode flash dikirim. Tunggu port baru muncul lalu tekan Segarkan.")
            QTimer.singleShot(2500, self.refresh_ports)
        else:
            self.on_log("Hubungkan perangkat dulu, atau masuk mode flash manual (tahan BOOT, tekan RESET).")

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih firmware", "", "Firmware (*.bin)")
        if path:
            self.flash(path)

    def flash(self, path):
        if not os.path.isfile(path):
            self.on_log("File firmware tidak ada.")
            return
        port = self.ports.currentData()
        if not port:
            self.on_log("Pilih port dulu.")
            return
        link = self.ctx.link
        if link and link.state != "off":
            link.close()
        self.prog.setValue(0)
        self.log.clear()
        self.b_flash.setEnabled(False)
        self.on_log("Flash %s ke %s…" % (os.path.basename(path), port))
        self.fl.start(port, path)

    def on_log(self, t):
        self.log.appendPlainText(t)

    def on_done(self, ok, msg):
        self.on_log(msg)
        self.ctx.toast.show_text("Flash selesai" if ok else "Flash gagal", bad=not ok)
        self.update_info()

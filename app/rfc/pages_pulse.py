"""Halaman Deteksi pulsa (semua channel) dan halaman OLED."""
import math
import time
from collections import deque

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from . import widgets as W
from .pages import Page
from .widgets import AnimBar, Card, Lamp, PSeg, PSlider, PSpin, PSwitch, label
from .theme import head_font

CH_NAMES = ["CH1 setir", "CH2 gas", "CH3 tombol", "CH4 tombol"]
CH_COLORS = ["accent", "amber", "teal", "rose"]
REST_SEC, SWEEP_SEC = 3.0, 8.0


def analyze(rest, sweep):
    """Hitung saran pengaturan dari sampel diam (rest) dan sampel gerak penuh (sweep).
    rest/sweep: daftar 4 daftar pulsa (µs). Mengembalikan (params, catatan)."""
    out, notes = {}, []
    allv = []
    for ch in range(4):
        r = [v for v in rest[ch] if v]
        s = [v for v in sweep[ch] if v]
        allv += r + s
        if len(r) < 5:
            notes.append("CH%d: tidak ada sinyal saat diam." % (ch + 1))
            continue
        mean = sum(r) / len(r)
        jit = max(r) - min(r)
        both = r + s
        lo, hi = min(both), max(both)
        if ch < 2:
            n = ch + 1
            mid = int(round(mean))
            nb = max(4, int(math.ceil(jit / 2.0)) + 2)
            if hi - lo < 200:
                notes.append("CH%d: gerakan kurang lebar (%d µs). Ulangi dan gerakkan sampai ujung." % (n, hi - lo))
                continue
            half = max(1, min(hi - mid, mid - lo))
            dz = max(2, min(40, int(math.ceil(1.5 * nb / half * 100))))
            out.update({"c%d_min" % n: lo, "c%d_mid" % n: mid, "c%d_max" % n: hi, "nb%d" % n: min(60, nb), "dz%d" % n: dz})
            notes.append("CH%d: tengah %d µs, goyangan diam %d µs, rentang %d sampai %d µs." % (n, mid, jit, lo, hi))
        else:
            n = ch + 1
            if hi - lo < 80:
                notes.append("CH%d: perubahan pulsa tidak terlihat. Tekan tombolnya saat merekam." % n)
                continue
            out["c%d_thr" % n] = (lo + hi) // 2
            out["btn_hys"] = max(out.get("btn_hys", 0), max(10, min(200, (hi - lo) // 4)))
            notes.append("CH%d: rendah %d µs, tinggi %d µs, ambang %d µs." % (n, lo, hi, (lo + hi) // 2))
    if allv:
        out["pv_min"] = max(200, min(1000, min(allv) - 200))
        out["pv_max"] = max(2000, min(3500, max(allv) + 200))
    return out, notes


class PulseLab(Page):
    title = "Deteksi pulsa"
    subtitle = "Pantau semua channel, deteksi otomatis, dan atur rentang sendiri"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        self.hist = [deque(maxlen=60) for _ in range(4)]   # ~3 detik
        self.seen = [[None, None] for _ in range(4)]
        self.last = [0, 0, 0, 0]
        self.sig = True
        self.phase = 0       # 0 diam-menunggu, 1 merekam diam, 2 merekam gerak, 3 hasil
        self.t0 = 0.0
        self.rest = [[] for _ in range(4)]
        self.sweep = [[] for _ in range(4)]
        self.result, self.notes = {}, []

        mon = Card("Monitor semua channel")
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(8)
        heads = ["Channel", "Sekarang", "Terendah", "Tertinggi", "Rata-rata 3 dtk", "Goyang", "Status"]
        for j, h in enumerate(heads):
            lb = QLabel(h)
            lb.setProperty("role", "muted")
            g.addWidget(lb, 0, j)
        self.cells = []
        self.bars = []
        for i in range(4):
            row = [QLabel(CH_NAMES[i])]
            for _ in range(5):
                lb = QLabel("—")
                lb.setProperty("role", "value")
                row.append(lb)
            st = QHBoxLayout()
            lamp = Lamp()
            txt = QLabel("—")
            st.addWidget(lamp)
            st.addWidget(txt)
            st.addStretch(1)
            wst = QWidget()
            wst.setLayout(st)
            row.append(wst)
            row.append(lamp)
            row.append(txt)
            self.cells.append(row)
            for j in range(7):
                g.addWidget(row[j], 1 + i * 2, j)
            bar = AnimBar("", 800, 2200, color=CH_COLORS[i], unit="µs", compact=True)
            bar.setFixedHeight(14)
            self.bars.append(bar)
            g.addWidget(bar, 2 + i * 2, 0, 1, 7)
        mon.v.addLayout(g)
        r = QHBoxLayout()
        b_reset = QPushButton("Reset terendah/tertinggi")
        b_reset.clicked.connect(self.reset_seen)
        r.addWidget(b_reset)
        r.addStretch(1)
        mon.v.addLayout(r)
        self.col.addWidget(mon)

        wz = Card("Deteksi otomatis semua channel")
        self.instr = label("Tekan Mulai. Pertama lepas semua kontrol remot selama 3 detik, lalu gerakkan semuanya sepenuhnya selama 8 detik.", "muted", True)
        wz.v.addWidget(self.instr)
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog.setTextVisible(False)
        wz.v.addWidget(self.prog)
        self.step = QLabel("Siap")
        self.step.setProperty("role", "h2")
        wz.v.addWidget(self.step)
        br = QHBoxLayout()
        self.b_go = QPushButton("Mulai deteksi")
        self.b_go.setProperty("kind", "primary")
        self.b_go.clicked.connect(self.start)
        self.b_apply = QPushButton("Terapkan hasil")
        self.b_apply.clicked.connect(self.apply)
        self.b_apply.setEnabled(False)
        br.addWidget(self.b_go)
        br.addWidget(self.b_apply)
        br.addStretch(1)
        wz.v.addLayout(br)
        self.res = label("", None, True)
        wz.v.addWidget(self.res)
        self.col.addWidget(wz)

        rg = Card("Rentang pulsa kustom")
        rg.v.addWidget(label("Isi sendiri kalau mau lebih presisi. Pita netral membuat posisi diam selalu tepat di tengah walau pulsa bergoyang beberapa µs.", "muted", True))
        for n, name in ((1, "CH1 setir"), (2, "CH2 gas dan rem")):
            rg.v.addWidget(label(name, "h2"))
            for k, t in (("c%d_min" % n, "Pulsa minimum"), ("c%d_mid" % n, "Pulsa tengah"), ("c%d_max" % n, "Pulsa maksimum")):
                rg.v.addWidget(PSpin(s, k, t, " µs"))
            rg.v.addWidget(PSlider(s, "nb%d" % n, "Pita netral (± dari tengah)", "µs"))
            rg.v.addWidget(PSlider(s, "dz%d" % n, "Zona mati", "%"))
            rg.v.addWidget(PSlider(s, "flt%d" % n, "Penghalus sinyal", "%"))
            rg.v.addWidget(PSwitch(s, "inv%d" % n, "Balik arah"))
        for n, name in ((3, "CH3 tombol"), (4, "CH4 tombol")):
            rg.v.addWidget(label(name, "h2"))
            rg.v.addWidget(PSeg(s, "c%d_type" % n, [("Ditahan (momentary)", 0), ("Bergantian tiap tekan", 1)]))
            rg.v.addWidget(PSpin(s, "c%d_thr" % n, "Ambang rendah/tinggi", " µs"))
        rg.v.addWidget(label("Semua channel", "h2"))
        rg.v.addWidget(PSlider(s, "btn_hys", "Histeresis tombol (± dari ambang)", "µs"))
        rg.v.addWidget(PSpin(s, "pv_min", "Pulsa dianggap sah mulai", " µs"))
        rg.v.addWidget(PSpin(s, "pv_max", "Pulsa dianggap sah sampai", " µs"))
        rg.v.addWidget(PSpin(s, "failsafe_ms", "Sinyal dianggap hilang setelah", " ms"))
        self.col.addWidget(rg)
        self.finish()

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # ---------------- statistik
    def reset_seen(self):
        self.seen = [[None, None] for _ in range(4)]

    def feed_live(self, d):
        self.sig = bool(d["sig"])
        self.last = d["p"]
        s = self.ctx.store
        for i, p in enumerate(d["p"]):
            if p:
                self.hist[i].append(p)
                lo, hi = self.seen[i]
                self.seen[i] = [p if lo is None else min(lo, p), p if hi is None else max(hi, p)]
            if self.phase == 1:
                self.rest[i].append(p)
            elif self.phase == 2:
                self.sweep[i].append(p)
        for i in range(4):
            p = self.last[i]
            c = self.cells[i]
            lo, hi = self.seen[i]
            h = list(self.hist[i])
            c[1].setText("%d µs" % p if p else "—")
            c[2].setText("%d" % lo if lo is not None else "—")
            c[3].setText("%d" % hi if hi is not None else "—")
            c[4].setText("%d" % (sum(h) / len(h)) if h else "—")
            c[5].setText("±%d" % ((max(h) - min(h)) / 2) if len(h) > 3 else "—")
            self.bars[i].set_value(p if p else 800)
            ok = bool(p) and s.get("pv_min") <= p <= s.get("pv_max")
            c[7].set_on(ok)
            if not p:
                c[8].setText("tidak ada sinyal")
            elif i < 2:
                mid, nb = s.get("c%d_mid" % (i + 1)), s.get("nb%d" % (i + 1))
                c[8].setText("netral" if abs(p - mid) <= nb else "bergerak")
            else:
                c[8].setText("tinggi" if p > s.get("c%d_thr" % (i + 1)) else "rendah")

    # ---------------- wizard
    def start(self):
        link = self.ctx.link
        if not link or not link.is_on():
            self.ctx.toast.show_text("Hubungkan perangkat dulu", bad=True)
            return
        self.rest = [[] for _ in range(4)]
        self.sweep = [[] for _ in range(4)]
        self.reset_seen()
        self.phase = 1
        self.t0 = time.monotonic()
        self.b_go.setEnabled(False)
        self.b_apply.setEnabled(False)
        self.res.setText("")

    def _tick(self):
        if self.phase not in (1, 2):
            return
        el = time.monotonic() - self.t0
        if self.phase == 1:
            self.step.setText("1 dari 2. Lepas semua kontrol, jangan sentuh remot")
            self.instr.setText("Merekam posisi diam untuk mencari titik tengah dan goyangan sinyal.")
            self.prog.setValue(int(min(1.0, el / REST_SEC) * 500))
            if el >= REST_SEC:
                self.phase, self.t0 = 2, time.monotonic()
        else:
            self.step.setText("2 dari 2. Gerakkan semuanya sampai ujung")
            self.instr.setText("Putar setir penuh kiri dan kanan, tarik dan dorong trigger penuh, tekan CH3 dan CH4 beberapa kali.")
            self.prog.setValue(500 + int(min(1.0, el / SWEEP_SEC) * 500))
            if el >= SWEEP_SEC:
                self.finish_wizard()

    def finish_wizard(self):
        self.phase = 3
        self.result, self.notes = analyze(self.rest, self.sweep)
        self.step.setText("Selesai")
        self.instr.setText("Periksa hasil di bawah. Tekan Terapkan hasil untuk memakainya, atau Mulai deteksi untuk mengulang.")
        self.res.setText("<br>".join(self.notes) if self.notes else "Tidak ada hasil.")
        self.b_go.setEnabled(True)
        self.b_apply.setEnabled(bool(self.result))
        self.prog.setValue(1000)

    def apply(self):
        if not self.result:
            return
        for k, v in self.result.items():
            self.ctx.store.set(k, v)
        self.ctx.toast.show_text("%d pengaturan pulsa diterapkan" % len(self.result))
        self.b_apply.setEnabled(False)


# =============================================================== OLED
class OledPreview(QWidget):
    """Pratinjau layar OLED 128x64 (meniru tampilan firmware)."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.live = dict(p=[0, 0, 0, 0], sig=0, steer=0, gas=0, brk=0, gear=0, st=0, rev=0, lock=0, gmode=1, omode=0)
        self.setMinimumHeight(290)
        self.t = QTimer(self)
        self.t.setInterval(100)
        self.t.timeout.connect(self.update)
        self.t.start()

    def _page(self):
        s = self.store
        mode = s.get("oled_page")
        if mode:
            return mode - 1
        return int(time.monotonic() // max(2, s.get("oled_cycle"))) % 3

    def paintEvent(self, _):
        c = W.THEME.c
        s = self.store
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        sc = max(1.0, min((self.width() - 40) / 128.0, (self.height() - 30) / 64.0))
        w, h = 128 * sc, 64 * sc
        x0, y0 = (self.width() - w) / 2, (self.height() - h) / 2
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(QRectF(x0 - 14, y0 - 14, w + 28, h + 28), 12, 12)
        if not s.get("oled_en"):
            p.setBrush(QColor("#000000"))
            p.drawRect(QRectF(x0, y0, w, h))
            p.setPen(QColor("#555555"))
            p.drawText(QRectF(x0, y0, w, h), Qt.AlignCenter, "OLED mati")
            return
        contrast = 0.35 + 0.65 * s.get("oled_contrast") / 255.0
        fg = QColor(int(120 * contrast + 40), int(200 * contrast + 30), min(255, int(255 * contrast)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#02060B"))
        p.drawRect(QRectF(x0, y0, w, h))
        p.save()
        p.translate(x0, y0)
        p.scale(sc, sc)
        if s.get("oled_rot"):
            p.translate(128, 64)
            p.rotate(180)
        p.setClipRect(QRectF(0, 0, 128, 64))
        self._draw(p, fg, self._page())
        p.restore()

    def _text(self, p, x, y, t, px=8, bold=False):
        f = QFont("DejaVu Sans Mono, Consolas")
        f.setPixelSize(px)
        f.setBold(bold)
        p.setFont(f)
        p.drawText(QRectF(x, y - px, 128, px + 3), Qt.AlignLeft | Qt.AlignBottom, t)

    def _bar(self, p, x, y, w, h, pct, center):
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x + 0.5, y + 0.5, w - 1, h - 1))
        p.setBrush(p.pen().color())
        if center:
            mid = x + w / 2
            ln = abs(pct) * (w / 2 - 2) / 100
            p.drawRect(QRectF(mid if pct >= 0 else mid - ln, y + 2, ln, h - 4))
        else:
            p.drawRect(QRectF(x + 2, y + 2, max(0, min(100, pct)) * (w - 4) / 100, h - 4))

    def _draw(self, p, fg, page):
        d, s = self.live, self.store
        p.setPen(QPen(fg, 1))
        if page == 0:
            self._text(p, 0, 9, ["PAD", "KEY", "MOUSE"][s.get("out_mode") % 3])
            self._text(p, 36, 9, ["GIGI OFF", "AUTO", "MANUAL"][s.get("gear_mode") % 3])
            if d["lock"]:
                self._text(p, 92, 9, "LOCK")
            p.drawLine(0, 12, 128, 12)
            if not d["sig"]:
                if int(time.monotonic() * 2) % 2:
                    self._text(p, 18, 42, "NO SIGNAL", 12, True)
                self._text(p, 12, 60, "Nyalakan remot")
                return
            g = "R" if d["rev"] else ("N" if d["gear"] == 0 else str(d["gear"]))
            self._text(p, 8, 54, g, 38, True)
            self._text(p, 52, 25, ["NETRAL", "MAJU", "REM", "MUNDUR", "REM"][d["st"] % 5])
            self._text(p, 52, 38, "GAS")
            self._bar(p, 76, 30, 50, 9, d["gas"], False)
            self._text(p, 52, 51, "REM")
            self._bar(p, 76, 43, 50, 9, d["brk"], False)
            self._text(p, 52, 63, "STR %d" % d["steer"])
        elif page == 1:
            for i, (nm, v, ctr) in enumerate((("SETIR", d["steer"], True), ("GAS", d["gas"], False), ("REM", d["brk"], False))):
                y = 11 + i * 20
                self._text(p, 0, y, nm)
                self._bar(p, 40, y - 9, 60, 11, v, ctr)
                self._text(p, 104, y, str(v))
            self._text(p, 0, 63, "G%d  %s" % (d["gear"], "R" if d["rev"] else "D"))
        else:
            for i in range(4):
                y = 12 + i * 16
                pv = d["p"][i]
                self._text(p, 0, y, "CH%d %4d" % (i + 1, pv))
                self._bar(p, 68, y - 9, 58, 10, max(0, min(100, (pv - 800) * 100 // 1400)) if pv else 0, False)


class Oled(Page):
    title = "OLED"
    subtitle = "Layar kecil I2C di board (SDA GPIO1, SCL GPIO2)"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        pv = Card("Pratinjau")
        self.prev = OledPreview(s)
        pv.v.addWidget(self.prev)
        self.col.addWidget(pv)
        c = Card("Tampilan")
        c.v.addWidget(PSwitch(s, "oled_en", "OLED aktif", "Berlaku setelah ESP32 dimulai ulang."))
        c.v.addWidget(label("Halaman", "h2"))
        c.v.addWidget(PSeg(s, "oled_page", [("Otomatis", 0), ("Status", 1), ("Bar", 2), ("Pulsa", 3)]))
        c.v.addWidget(PSlider(s, "oled_cycle", "Ganti halaman tiap (mode otomatis)", "dtk"))
        c.v.addWidget(PSlider(s, "oled_contrast", "Kecerahan layar", ""))
        c.v.addWidget(PSwitch(s, "oled_rot", "Putar layar 180°"))
        c.v.addWidget(label("Aksi sistem Ganti halaman OLED bisa dipasang ke tombol CH3/CH4 di menu Tombol dan gestur.", "muted", True))
        self.col.addWidget(c)
        hw = Card("Perangkat keras")
        hw.v.addWidget(label("Tipe layar", "h2"))
        hw.v.addWidget(PSeg(s, "oled_type", [("SSD1306", 0), ("SH1106 (1,3 inci)", 1)]))
        hw.v.addWidget(PSpin(s, "oled_sda", "Pin SDA (GPIO)"))
        hw.v.addWidget(PSpin(s, "oled_scl", "Pin SCL (GPIO)"))
        hw.v.addWidget(label("Alamat I2C 0x3C, daya 3,3 V. Kalau layar kosong, coba ganti tipe ke SH1106 dan cek urutan pin VCC/GND di modul. Perubahan pin dan tipe berlaku setelah simpan dan mulai ulang.", "muted", True))
        b = QPushButton("Simpan dan mulai ulang ESP32")
        b.clicked.connect(lambda: ctx.restart())
        hw.v.addWidget(b)
        self.col.addWidget(hw)
        self.finish()

    def feed_live(self, d):
        self.prev.live = d

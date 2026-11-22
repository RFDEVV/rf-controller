"""Halaman Koneksi, LED, dan Wiring."""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from . import widgets as W
from .link import Link
from .pages import Page
from .params import PARAMS, led_color
from .widgets import Card, PSeg, PSlider, PSwitch, label
from .theme import head_font


def hline(color):
    ln = QFrame()
    ln.setFrameShape(QFrame.HLine)
    ln.setStyleSheet("color: %s;" % color)
    return ln


# =============================================================== Koneksi
class Connection(Page):
    title = "Koneksi"
    subtitle = "Kabel USB, WiFi serumah, atau Bluetooth"

    WIFI_STATE = {0: "WiFi mati", 1: "Mencari jaringan…", 2: "Terhubung ke jaringan", 3: "SSID belum diisi"}

    def __init__(self, ctx):
        super().__init__(ctx)
        self.win = None  # diisi oleh MainWindow
        s = ctx.store

        usb = Card("Kabel USB  (paling stabil, delay terkecil)")
        usb.v.addWidget(label("Colok kabel ke port USB-C yang berlabel USB (native), bukan yang berlabel UART/COM. Port ini juga yang dikenali game sebagai gamepad/keyboard.", "muted", True))
        r = QHBoxLayout()
        self.ports = QComboBox()
        r.addWidget(self.ports, 1)
        rf = QPushButton("Segarkan")
        rf.clicked.connect(self.refresh_ports)
        self.b_usb = QPushButton("Hubungkan")
        self.b_usb.setProperty("kind", "primary")
        self.b_usb.clicked.connect(lambda: self.win.connect_to("usb", self.ports.currentData()))
        r.addWidget(rf)
        r.addWidget(self.b_usb)
        usb.v.addLayout(r)
        self.col.addWidget(usb)

        wifi = Card("WiFi serumah")
        wifi.v.addWidget(label("ESP32 dan PC harus di jaringan WiFi yang sama. Isi nama dan sandi WiFi lewat kabel USB sekali saja, aktifkan, lalu simpan dan mulai ulang ESP32.", "muted", True))
        wifi.v.addWidget(PSwitch(s, "wifi_en", "Aktifkan WiFi di ESP32", "Berlaku setelah ESP32 dimulai ulang."))
        fr = QGridLayout()
        self.ssid = QLineEdit()
        self.ssid.setPlaceholderText("Nama WiFi (SSID)")
        self.pw = QLineEdit()
        self.pw.setPlaceholderText("Sandi WiFi")
        self.pw.setEchoMode(QLineEdit.Password)
        b_send = QPushButton("Kirim ke ESP32")
        b_send.clicked.connect(self.send_wifi)
        fr.addWidget(self.ssid, 0, 0)
        fr.addWidget(self.pw, 0, 1)
        fr.addWidget(b_send, 0, 2)
        wifi.v.addLayout(fr)
        self.wifi_state = label("Status WiFi ESP32: belum diketahui (hubungkan lewat USB dulu)", "muted", True)
        wifi.v.addWidget(self.wifi_state)
        wifi.v.addWidget(hline(ctx.theme.c["border"]))
        hr = QHBoxLayout()
        self.host = QLineEdit("rfcontroller.local")
        self.host.setPlaceholderText("Alamat ESP32 (rfcontroller.local atau IP)")
        b_w = QPushButton("Hubungkan lewat WiFi")
        b_w.setProperty("kind", "primary")
        b_w.clicked.connect(lambda: self.win.connect_to("wifi", self.host.text()))
        hr.addWidget(self.host, 1)
        hr.addWidget(b_w)
        wifi.v.addLayout(hr)
        self.col.addWidget(wifi)

        ble = Card("Bluetooth (BLE)")
        ble.v.addWidget(label("Aktifkan Bluetooth di ESP32 lewat kabel USB, simpan dan mulai ulang, lalu cari di sini. Bluetooth dipakai untuk setting dan monitor; input game tetap lewat USB.", "muted", True))
        ble.v.addWidget(PSwitch(s, "ble_en", "Aktifkan Bluetooth di ESP32", "Berlaku setelah ESP32 dimulai ulang."))
        br = QHBoxLayout()
        self.ble_list = QComboBox()
        self.b_scan = QPushButton("Cari perangkat")
        self.b_scan.clicked.connect(self.scan)
        b_b = QPushButton("Hubungkan lewat Bluetooth")
        b_b.setProperty("kind", "primary")
        b_b.clicked.connect(lambda: self.win.connect_to("ble", self.ble_list.currentData()))
        br.addWidget(self.ble_list, 1)
        br.addWidget(self.b_scan)
        br.addWidget(b_b)
        ble.v.addLayout(br)
        self.col.addWidget(ble)

        act = Card("Terapkan perubahan jaringan")
        act.v.addWidget(label("Simpan pengaturan ke ESP32 lalu mulai ulang supaya WiFi/Bluetooth aktif atau mati. Koneksi akan terputus sebentar.", "muted", True))
        ar = QHBoxLayout()
        b_re = QPushButton("Simpan dan mulai ulang ESP32")
        b_re.clicked.connect(self.save_reboot)
        b_demo = QPushButton("Coba mode demo (tanpa perangkat)")
        b_demo.clicked.connect(lambda: self.win.connect_to("demo", ""))
        ar.addWidget(b_re)
        ar.addWidget(b_demo)
        ar.addStretch(1)
        act.v.addLayout(ar)
        self.col.addWidget(act)
        self.finish()
        self.refresh_ports()

    def bind(self, win):
        self.win = win
        ble = win.links["ble"]
        ble.devicesChanged.connect(self._ble_devices)
        ble.scanning.connect(lambda on: (self.b_scan.setEnabled(not on), self.b_scan.setText("Mencari…" if on else "Cari perangkat")))
        for l in win.links.values():
            l.wifiInfo.connect(self._wifi_info)
            l.stateChanged.connect(self._state)

    def _state(self, st):
        if st == "on" and self.win and self.win.link.kind != "demo":
            self.win.link.send("WIFIINFO")

    def refresh_ports(self):
        cur = self.ports.currentData()
        self.ports.clear()
        for name, text, rf in Link.list_ports():
            self.ports.addItem(text + ("   ← ESP32" if rf else ""), name)
        i = self.ports.findData(cur)
        if i >= 0:
            self.ports.setCurrentIndex(i)

    def _ble_devices(self, items):
        cur = self.ble_list.currentData()
        self.ble_list.clear()
        for t, k in items:
            self.ble_list.addItem(t, k)
        i = self.ble_list.findData(cur)
        self.ble_list.setCurrentIndex(max(0, i))

    def scan(self):
        self.win.links["ble"].scan()

    def send_wifi(self):
        link = self.win.link
        if not link.is_on() or link.kind == "demo":
            self.ctx.toast.show_text("Hubungkan ESP32 dulu (lebih aman lewat USB)", bad=True)
            return
        if not self.ssid.text().strip():
            self.ctx.toast.show_text("Isi nama WiFi dulu", bad=True)
            return
        link.send("WIFISSID " + self.ssid.text().strip())
        link.send("WIFIPASS " + self.pw.text())
        self.pw.clear()
        self.ctx.store.set("wifi_en", 1)
        self.ctx.toast.show_text("WiFi dikirim. Simpan dan mulai ulang ESP32.")
        link.send("WIFIINFO")

    def _wifi_info(self, state, ip, ssid):
        t = "Status WiFi ESP32: %s" % self.WIFI_STATE.get(state, "?")
        if state == 2:
            t += " (%s), alamat IP %s" % (ssid, ip)
            self.host.setText(ip)
        elif ssid != "-":
            t += " (SSID tersimpan: %s)" % ssid
        self.wifi_state.setText(t)

    def save_reboot(self):
        link = self.win.link
        if not link.is_on() or link.kind == "demo":
            self.ctx.toast.show_text("Hubungkan ESP32 dulu", bad=True)
            return
        if QMessageBox.question(self, "Mulai ulang ESP32", "Simpan pengaturan dan mulai ulang ESP32 sekarang?") != QMessageBox.Yes:
            return
        self.ctx.store.save_to_device()
        link.send("REBOOT")
        self.ctx.toast.show_text("ESP32 dimulai ulang…")


# =============================================================== LED
class LedPreview(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.live = dict(sig=1, st=0, gas=0, rev=0)
        self.setMinimumHeight(150)
        self.t = QTimer(self)
        self.t.setInterval(33)
        self.t.timeout.connect(self.update)
        self.t.start()

    def paintEvent(self, _):
        c = W.THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = int(time.monotonic() * 1000)
        full = dict(self.store.v)
        k = max(0.0, min(1.0, full["led_bright"] / 100.0))
        full["led_bright"] = 100  # pratinjau selalu terlihat jelas; kecerahan asli memengaruhi cahaya
        r, g, b = led_color(full, now, bool(self.live["sig"]), self.live["st"], self.live["gas"], bool(self.live["rev"]))
        col = QColor(r, g, b)
        cx, cy = self.width() / 2, self.height() / 2
        # papan ESP32 sederhana
        board = QRectF(cx - 150, cy - 46, 300, 92)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(QColor(c["surface2"]))
        p.drawRoundedRect(board, 10, 10)
        p.setBrush(QColor(c["border"]))
        p.drawRoundedRect(QRectF(board.left() + 14, board.top() + 18, 70, 56), 4, 4)
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(self.font().family(), 9))
        p.drawText(QRectF(board.left() + 14, board.top() + 18, 70, 56), Qt.AlignCenter, "ESP32-S3")
        led = QPointF(board.right() - 60, cy)
        lum = ((r + g + b) / (3 * 255.0)) * (0.25 + 0.75 * k)
        if lum > 0.01:
            grad = QRadialGradient(led, 70)
            glow = QColor(col)
            glow.setAlphaF(min(0.9, 0.25 + lum))
            grad.setColorAt(0, glow)
            glow.setAlphaF(0)
            grad.setColorAt(1, glow)
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawEllipse(led, 70, 70)
        p.setPen(QPen(QColor(c["border"]), 1))
        p.setBrush(col if lum > 0.01 else QColor(c["bg"]))
        p.drawRoundedRect(QRectF(led.x() - 11, led.y() - 11, 22, 22), 4, 4)


SWATCHES = ["#FF3B30", "#FF9500", "#FFD60A", "#30D158", "#00E5FF", "#0A84FF", "#BF5AF2", "#FFFFFF"]


class Led(Page):
    title = "LED"
    subtitle = "Lampu RGB di board ESP32-S3"

    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.store
        self.prev = LedPreview(s)
        top = Card("Pratinjau")
        top.v.addWidget(self.prev)
        self.col.addWidget(top)
        c = Card("Pengaturan")
        c.v.addWidget(PSwitch(s, "led_en", "LED aktif"))
        c.v.addWidget(PSeg(s, "led_mode", [("Mati", 0), ("Status", 1), ("Warna", 2), ("Pelangi", 3), ("Napas", 4)]))
        c.v.addWidget(label("Status: merah berkedip saat sinyal remot hilang, hijau saat maju, merah saat rem, kuning saat mundur, biru saat netral.", "muted", True))
        row = QHBoxLayout()
        row.addWidget(QLabel("Warna"))
        for hx in SWATCHES:
            b = QPushButton()
            b.setFixedSize(28, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton { background: %s; border: 2px solid transparent; border-radius: 14px; } QPushButton:hover { border-color: %s; }" % (hx, c.palette().text().color().name()))
            b.clicked.connect(lambda _=False, h=hx: self.set_color(QColor(h)))
            row.addWidget(b)
        more = QPushButton("Pilih warna…")
        more.clicked.connect(self.pick)
        row.addStretch(1)
        row.addWidget(more)
        c.v.addLayout(row)
        c.v.addWidget(PSlider(s, "led_bright", "Kecerahan", "%"))
        c.v.addWidget(PSlider(s, "led_speed", "Kecepatan efek", ""))
        self.col.addWidget(c)
        pin = Card("Pin LED di board")
        pin.v.addWidget(label("Lokasi LED beda tiap versi board. DevKitC-1 v1.0 memakai GPIO48, v1.1 memakai GPIO38. Kalau LED tidak menyala, coba pin lain.", "muted", True))
        self.pin = QComboBox()
        for name, v in (("GPIO48  (DevKitC-1 v1.0, paling umum)", 48), ("GPIO38  (DevKitC-1 v1.1)", 38), ("GPIO47", 47), ("GPIO21", 21)):
            self.pin.addItem(name, v)
        self._pin_ext()
        self.pin.currentIndexChanged.connect(lambda i: s.set("led_pin", self.pin.itemData(i)))
        s.changed.connect(lambda k: self._pin_ext() if k == "led_pin" else None)
        s.bulk.connect(self._pin_ext)
        pin.v.addWidget(self.pin)
        self.col.addWidget(pin)
        self.finish()

    def _pin_ext(self):
        i = self.pin.findData(self.ctx.store.get("led_pin"))
        self.pin.blockSignals(True)
        self.pin.setCurrentIndex(max(0, i))
        self.pin.blockSignals(False)

    def set_color(self, q):
        s = self.ctx.store
        s.set("led_r", q.red())
        s.set("led_g", q.green())
        s.set("led_b", q.blue())
        if s.get("led_mode") in (0, 1, 3):
            s.set("led_mode", 2)

    def pick(self):
        s = self.ctx.store
        q = QColorDialog.getColor(QColor(s.get("led_r"), s.get("led_g"), s.get("led_b")), self, "Pilih warna LED")
        if q.isValid():
            self.set_color(q)

    def feed_live(self, d):
        self.prev.live = d


# =============================================================== Wiring
CH_COLORS = ["accent", "amber", "teal", "rose"]
WIRE_ROWS = [("CH1", "Setir (roda)", "GPIO4"), ("CH2", "Gas (trigger)", "GPIO5"),
             ("CH3", "Tombol 3", "GPIO6"), ("CH4", "Tombol 4", "GPIO7")]


class WiringDiagram(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(600)
        self.ph = 0.0
        self.t = QTimer(self)
        self.t.setInterval(33)
        self.t.timeout.connect(self._tick)
        self.t.start()

    def _tick(self):
        self.ph = (self.ph + 0.7) % 1000
        self.update()

    def paintEvent(self, _):
        c = W.THEME.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        lx, rx = 24, w - 24
        rec = QRectF(lx, 16, 250, (h - 32) * 0.62)
        oled = QRectF(lx, rec.bottom() + 16, 250, h - 16 - rec.bottom() - 16)
        esp = QRectF(rx - 270, 16, 270, h - 32)
        for r, title, sub in ((rec, "Receiver GA-4H-RX", "konektor 4 channel"), (esp, "ESP32-S3 DevKitC-1", "header pin"),
                              (oled, "Layar OLED I2C", "I2C 0x3C, 3,3 V")):
            p.setPen(QPen(QColor(c["border"]), 1))
            p.setBrush(QColor(c["surface2"]))
            p.drawRoundedRect(r, 12, 12)
            p.setPen(QColor(c["text"]))
            p.setFont(head_font(15))
            p.drawText(QRectF(r.left() + 16, r.top() + 10, r.width() - 32, 24), Qt.AlignLeft | Qt.AlignVCenter, title)
            p.setPen(QColor(c["muted"]))
            p.setFont(QFont(self.font().family(), 10))
            p.drawText(QRectF(r.left() + 16, r.top() + 32, r.width() - 32, 18), Qt.AlignLeft, sub)
        row_h = (rec.height() - 110) / 4
        pins = {}
        p.setFont(QFont(self.font().family(), 10))
        cols_x = [rec.right() - 150 + j * 44 + 12 for j in range(3)]
        for j, (sym, nm) in enumerate((("S", "sinyal"), ("+", "V+"), ("−", "GND"))):
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(cols_x[j] - 22, rec.top() + 62, 44, 18), Qt.AlignCenter, "%s %s" % (sym, nm) if j == 0 else sym)
        for i, (ch, name, gp) in enumerate(WIRE_ROWS):
            y = rec.top() + 100 + row_h * i + row_h / 2
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(rec.left() + 14, y - 12, 60, 24), Qt.AlignVCenter, ch)
            for j, kind in enumerate(("sig", "vcc", "gnd")):
                pins[(i, kind)] = QPointF(cols_x[j], y)
                colr = {"sig": c[CH_COLORS[i]], "vcc": c["danger"], "gnd": c["muted"]}[kind]
                p.setPen(QPen(QColor(colr), 1.5))
                p.setBrush(QColor(c["bg"]))
                p.drawEllipse(QPointF(cols_x[j], y), 8, 8)
        # pin OLED
        opins = {}
        oy = oled.top() + 92
        for j, (nm, kind, ck) in enumerate((("GND", "gnd", "muted"), ("VCC", "vcc", "danger"), ("SCL", "scl", "amber"), ("SDA", "sda", "accent"))):
            ox = oled.right() - 190 + j * 46 + 12
            opins[kind] = QPointF(ox, oy)
            p.setPen(QPen(QColor(c[ck]), 1.5))
            p.setBrush(QColor(c["bg"]))
            p.drawEllipse(QPointF(ox, oy), 8, 8)
            p.setPen(QColor(c["text"]))
            p.setFont(QFont(self.font().family(), 9))
            p.drawText(QRectF(ox - 22, oy - 32, 44, 16), Qt.AlignCenter, nm)
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(self.font().family(), 9))
        p.drawText(QRectF(oled.left() + 16, oled.bottom() - 26, oled.width() - 32, 18), Qt.AlignLeft, "cek tulisan pin di modul")
        # pin ESP32
        eps = {}
        labels = [("3V3", "daya receiver dan OLED", "danger"), ("GND", "ground bersama", "muted"),
                  ("GPIO1", "OLED SDA", "accent"), ("GPIO2", "OLED SCL", "amber"),
                  ("GPIO4", "CH1 setir", CH_COLORS[0]), ("GPIO5", "CH2 gas", CH_COLORS[1]),
                  ("GPIO6", "CH3 tombol", CH_COLORS[2]), ("GPIO7", "CH4 tombol", CH_COLORS[3])]
        step = (esp.height() - 175) / 7
        for i, (pin, desc, ck) in enumerate(labels):
            y = esp.top() + 70 + step * i
            eps[pin] = QPointF(esp.left() + 14, y)
            p.setPen(QPen(QColor(c[ck]), 1.5))
            p.setBrush(QColor(c["bg"]))
            p.drawEllipse(QPointF(esp.left() + 14, y), 7, 7)
            p.setPen(QColor(c["text"]))
            p.setFont(head_font(13))
            p.drawText(QRectF(esp.left() + 32, y - 12, 80, 24), Qt.AlignVCenter, pin)
            p.setPen(QColor(c["muted"]))
            p.setFont(QFont(self.font().family(), 10))
            p.drawText(QRectF(esp.left() + 100, y - 12, esp.width() - 104, 24), Qt.AlignVCenter, desc)
        for k, (txt, ck) in enumerate((("USB (native) → PC", "accent"), ("UART → flash/log", "muted"))):
            ux = esp.left() + 16 + k * 124
            p.setPen(QPen(QColor(c[ck]), 1.5))
            p.setBrush(QColor(c["bg"]))
            p.drawRoundedRect(QRectF(ux, esp.bottom() - 46, 40, 18), 8, 8)
            p.setPen(QColor(c["muted"]))
            p.setFont(QFont(self.font().family(), 9))
            p.drawText(QRectF(ux - 4, esp.bottom() - 26, 120, 16), Qt.AlignLeft, txt)

        def wire(a, b, col, width=2.4):
            path = QPainterPath(a)
            mx = (a.x() + b.x()) / 2
            path.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
            q = QColor(col)
            q.setAlphaF(0.28)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(q, width + 3, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
            p.setPen(QPen(QColor(col), width, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
            if W.THEME.animations:
                pen2 = QPen(QColor("#FFFFFF" if W.THEME.dark else "#000000"), 1.6, Qt.CustomDashLine)
                pen2.setDashPattern([0.4, 9])
                pen2.setDashOffset(-self.ph * 0.9)
                pen2.setCapStyle(Qt.RoundCap)
                p.setPen(pen2)
                p.drawPath(path)
        for i in range(4):
            wire(pins[(i, "sig")], eps[labels[4 + i][0]], c[CH_COLORS[i]])
            wire(pins[(i, "vcc")], eps["3V3"], c["danger"], 1.8)
            wire(pins[(i, "gnd")], eps["GND"], c["muted"], 1.8)
        wire(opins["sda"], eps["GPIO1"], c["accent"])
        wire(opins["scl"], eps["GPIO2"], c["amber"])
        wire(opins["vcc"], eps["3V3"], c["danger"], 1.8)
        wire(opins["gnd"], eps["GND"], c["muted"], 1.8)


class Wiring(Page):
    title = "Wiring"
    subtitle = "Peta kabel receiver ke ESP32-S3"

    def __init__(self, ctx):
        super().__init__(ctx)
        d = Card("Diagram")
        d.v.addWidget(WiringDiagram())
        self.col.addWidget(d)
        t = Card("Tabel sambungan")
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        rows = [("Dari (receiver GA-4H-RX)", "Ke (ESP32-S3)", "Fungsi"),
                ("CH1 sinyal (S)", "GPIO4", "Setir, roda samping"),
                ("CH2 sinyal (S)", "GPIO5", "Gas dan rem, trigger"),
                ("CH3 sinyal (S)", "GPIO6", "Tombol CH3 (dekat dial)"),
                ("CH4 sinyal (S)", "GPIO7", "Tombol CH4 (dekat dial)"),
                ("Pin + (V+) salah satu channel", "3V3", "Daya receiver 3,3 V"),
                ("Pin − (GND) salah satu channel", "GND", "Ground bersama"),
                ("OLED SDA", "GPIO1", "Data I2C layar"),
                ("OLED SCL", "GPIO2", "Clock I2C layar"),
                ("OLED VCC", "3V3", "Daya layar 3,3 V"),
                ("OLED GND", "GND", "Ground layar"),
                ("Port USB-C berlabel USB", "Kabel ke PC", "Input game (HID) dan setting"),
                ("Port USB-C berlabel UART", "Kabel ke PC (opsional)", "Flash firmware dan log")]
        for i, row in enumerate(rows):
            for j, txt in enumerate(row):
                lb = QLabel(txt)
                if i == 0:
                    lb.setProperty("role", "h2")
                g.addWidget(lb, i, j)
        t.v.addLayout(g)
        self.col.addWidget(t)
        n = Card("Yang harus diperhatikan")
        for tx in (
            "Cukup satu pin + dan satu pin − yang disambung ke ESP32. Pada receiver RC umumnya jalur + dan − semua channel terhubung di dalam, jadi tidak perlu keempatnya. Kalau ragu, ukur dengan multimeter.",
            "Pakai 3V3, jangan 5V. Dengan daya 3,3 V sinyal receiver juga 3,3 V, aman untuk GPIO ESP32 (batas 3,6 V). Receiver boleh 3,3 sampai 6 V, jangan lebih dari 6 V.",
            "Urutan pin di receiver umumnya S (sinyal), + (V+), − (GND). Cocokkan dengan tanda S + − yang tercetak di receiver sebelum menyambung, pasang terbalik bisa merusak.",
            "Jangan sambungkan receiver ke ESC atau servo sekaligus dengan ESP32, supaya tidak ada dua sumber daya yang bertemu.",
            "OLED I2C: SDA ke GPIO1, SCL ke GPIO2, daya 3,3 V, alamat 0x3C. Urutan pin modul OLED beda-beda (ada GND-VCC-SCL-SDA, ada VCC-GND-SCL-SDA), baca tulisan di modulnya. Pin SDA/SCL bisa diubah di menu OLED.",
            "Hindari pin ini untuk hal lain: GPIO19 dan GPIO20 (USB), GPIO0, 3, 45, 46 (pin boot), GPIO26 sampai 32 (flash), GPIO33 sampai 37 (PSRAM pada tipe N8R8/N16R8). GPIO48 atau 38 dipakai LED RGB.",
            "Binding remot dan receiver: tekan tombol SW di receiver sampai LED berkedip cepat, lalu nyalakan remot.",
        ):
            n.v.addWidget(label("•  " + tx, None, True))
        self.col.addWidget(n)
        self.finish()

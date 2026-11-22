"""Jendela utama: sidebar, bilah atas, halaman, dan manajemen koneksi (USB, WiFi, Bluetooth, demo)."""
import math

from PySide6.QtCore import QPoint, QRectF, QSettings, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import APP_NAME, APP_VERSION, widgets as W
from .brand import draw_icon, paint_logo
from .flasher import Flasher
from .link import BleLink, FakeLink, Link, TcpLink
from .pages import (Buttons, Ctx, Dashboard, Firmware, Gears, Output, Profiles, SteerThrottle)
from .pages_pulse import Oled, PulseLab
from .pages_extra import Connection, Led, Wiring
from .params import resource_path
from .store import ParamStore
from .theme import Theme, head_font

KIND_NAMES = {"usb": "USB", "wifi": "WiFi", "ble": "Bluetooth", "demo": "Demo"}


class NavButton(QAbstractButton):
    def __init__(self, icon, text, theme):
        super().__init__()
        self.icon_name, self.theme = icon, theme
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._h = 0.0
        self._a = QVariantAnimation(self)
        self._a.setDuration(160)
        self._a.valueChanged.connect(self._set_h)

    def _set_h(self, v):
        self._h = float(v)
        self.update()

    def enterEvent(self, e):
        self._go(1.0)

    def leaveEvent(self, e):
        self._go(0.0)

    def _go(self, to):
        self._a.stop()
        self._a.setStartValue(self._h)
        self._a.setEndValue(to)
        self._a.start()

    def paintEvent(self, _):
        c = self.theme.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._h > 0 and not self.isChecked():
            bg = QColor(c["surface2"])
            bg.setAlphaF(self._h)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        col = QColor(c["accent"] if self.isChecked() else (c["text"] if self._h > 0.5 else c["muted"]))
        draw_icon(p, self.icon_name, QRectF(14, 8, 20, 20), col)
        f = QFont(self.font())
        f.setWeight(QFont.DemiBold if self.isChecked() else QFont.Normal)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(46, 0, self.width() - 50, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class StatusPill(QAbstractButton):
    def __init__(self, theme):
        super().__init__()
        self.theme, self.state, self.text_, self.ph = theme, "off", "Tidak terhubung", 0.0
        self.setFixedHeight(34)
        self.setMinimumWidth(210)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Buka pengaturan koneksi")
        self.t = QTimer(self)
        self.t.setInterval(33)
        self.t.timeout.connect(self._tick)
        self.t.start()

    def set_state(self, state, text):
        self.state, self.text_ = state, text
        self.update()

    def _tick(self):
        self.ph += 0.08
        if self.state != "off":
            self.update()

    def paintEvent(self, _):
        c = self.theme.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QColor(c["border"]))
        p.setBrush(QColor(c["surface"]))
        p.drawRoundedRect(r, 17, 17)
        col = QColor({"on": c["teal"], "connecting": c["amber"]}.get(self.state, c["muted"]))
        if self.state != "off":
            k = (math.sin(self.ph) + 1) / 2 if self.theme.animations else 0.5
            halo = QColor(col)
            halo.setAlphaF(0.15 + 0.3 * k)
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QRectF(11, 9, 16, 16).adjusted(-k * 2, -k * 2, k * 2, k * 2))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(15, 13, 8, 8))
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(34, 0, self.width() - 42, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text_)


class MainWindow(QWidget):
    def __init__(self, theme: Theme):
        super().__init__()
        W.THEME = theme
        self.theme = theme
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource_path("assets/icon.png")))
        self.resize(1240, 780)
        self.setMinimumSize(1020, 700)
        self.store = ParamStore()
        self.links = {"usb": Link(), "wifi": TcpLink(), "ble": BleLink(), "demo": FakeLink()}
        self.link = self.links["usb"]
        self.flasher = Flasher()
        self.toast = W.Toast(self)
        self.ctx = Ctx(self.store, lambda: self.link, theme, self.toast, self.flasher)
        self.manual_off = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_side())
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(self._build_top())
        self.stack = W.AnimStack()
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)

        self.pages = [Dashboard(self.ctx), Connection(self.ctx), PulseLab(self.ctx), SteerThrottle(self.ctx),
                      Gears(self.ctx), Buttons(self.ctx), Output(self.ctx), Led(self.ctx), Oled(self.ctx),
                      Wiring(self.ctx), Profiles(self.ctx), Firmware(self.ctx)]
        for p in self.pages:
            self.stack.addWidget(p)
        self.page_conn, self.page_fw = self.pages[1], self.pages[11]
        self.ctx.restart = self.page_conn.save_reboot
        self.page_conn.bind(self)
        self.nav[0].setChecked(True)
        self._go(0, animate=False)

        for l in self.links.values():
            l.stateChanged.connect(self._state)
            l.live.connect(self._live)
            l.paramsReceived.connect(self.store.apply_device)
            l.message.connect(lambda m: self.toast.show_text(m, bad=True))
        self.store.attach(self.link)
        self.store.dirtyChanged.connect(self._dirty)
        theme.changed.connect(self._restyle)
        self._sig = None
        self._ports_timer = QTimer(self)
        self._ports_timer.setInterval(1500)
        self._ports_timer.timeout.connect(self._watch_ports)
        self._ports_timer.start()
        self._restyle()
        self._watch_ports()

    # ---------------- sidebar
    def _build_side(self):
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(226)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 18, 14, 14)
        v.setSpacing(2)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(40, 40)
        pm = QPixmap(80, 80)
        pm.fill(Qt.transparent)
        pp = QPainter(pm)
        paint_logo(pp, QRectF(0, 0, 80, 80))
        pp.end()
        pm.setDevicePixelRatio(2)
        logo.setPixmap(pm)
        t = QLabel("RF Controller")
        t.setFont(head_font(16))
        brand.addWidget(logo)
        brand.addWidget(t, 1)
        v.addLayout(brand)
        v.addSpacing(14)
        self.nav = []
        items = [("dash", "Dashboard"), ("plug", "Koneksi"), ("pulse", "Deteksi pulsa"), ("wheel", "Setir dan gas"),
                 ("gear", "Gigi"), ("button", "Tombol dan gestur"), ("output", "Output"), ("led", "LED"),
                 ("oled", "OLED"), ("wire", "Wiring"), ("profile", "Profil"), ("chip", "Firmware")]
        self.indicator = QWidget(side)
        self.indicator.setFixedSize(3, 20)
        for i, (ic, tx) in enumerate(items):
            b = NavButton(ic, tx, self.theme)
            b.clicked.connect(lambda _=False, i=i: self._go(i))
            self.nav.append(b)
            v.addWidget(b)
        v.addStretch(1)
        anim = QHBoxLayout()
        anim.addWidget(QLabel("Animasi"), 1)
        self.t_anim = W.Toggle()
        self.t_anim.setCheckedSilent(self.theme.animations)
        self.t_anim.toggled.connect(self._set_anim)
        anim.addWidget(self.t_anim)
        v.addLayout(anim)
        ver = QLabel("Versi %s" % APP_VERSION)
        ver.setProperty("role", "muted")
        v.addWidget(ver)
        return side

    def _cur_index(self):
        return [n.isChecked() for n in self.nav].index(True)

    def _place_indicator(self, i, animate=True):
        b = self.nav[i]
        g = b.geometry()
        y = g.y() + (g.height() - 20) // 2
        self.indicator.setStyleSheet("background: %s; border-radius: 1px;" % self.theme.c["accent"])
        self.indicator.show()
        if animate and self.theme.animations:
            a = W.make_anim(self.indicator, b"pos", self.indicator.pos(), QPoint(2, y), 260)
            a.start()
            self._ind_anim = a
        else:
            self.indicator.move(2, y)

    def _go(self, i, animate=True):
        for k, b in enumerate(self.nav):
            b.setChecked(k == i)
        if animate:
            self.stack.go(i)
        else:
            self.stack.setCurrentIndex(i)
        self.title.setText(self.pages[i].title)
        self.sub.setText(self.pages[i].subtitle)
        self._place_indicator(i, animate)
        if self.pages[i] is self.page_fw:
            self.page_fw.update_info()
            self.page_fw.refresh_ports()
        if self.pages[i] is self.page_conn:
            self.page_conn.refresh_ports()

    # ---------------- bilah atas
    def _build_top(self):
        top = QWidget()
        top.setObjectName("page")
        top.setFixedHeight(84)
        h = QHBoxLayout(top)
        h.setContentsMargins(28, 14, 28, 6)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel("")
        self.title.setProperty("role", "title")
        self.sub = QLabel("")
        self.sub.setProperty("role", "muted")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        h.addLayout(col, 1)
        self.unsaved = QLabel("Belum disimpan ke ESP32")
        self.unsaved.hide()
        h.addWidget(self.unsaved)
        self.pill = StatusPill(self.theme)
        self.pill.clicked.connect(lambda: self._go(1))
        h.addWidget(self.pill)
        self.b_disc = QPushButton("Putuskan")
        self.b_disc.clicked.connect(self.disconnect)
        self.b_disc.hide()
        h.addWidget(self.b_disc)
        self.b_save = QPushButton("Simpan ke ESP32")
        self.b_save.setProperty("kind", "primary")
        self.b_save.clicked.connect(self._save)
        self.b_save.setEnabled(False)
        h.addWidget(self.b_save)
        self.b_theme = QPushButton()
        self.b_theme.setProperty("kind", "ghost")
        self.b_theme.setFixedWidth(40)
        self.b_theme.setToolTip("Ganti tema terang/gelap")
        self.b_theme.clicked.connect(self._toggle_theme)
        h.addWidget(self.b_theme)
        return top

    # ---------------- koneksi
    def connect_to(self, kind, target):
        for l in self.links.values():
            if l.state != "off":
                l.close()
        self.manual_off = False
        self.link = self.links[kind]
        self.store.attach(self.link)
        if kind == "usb" and not target:
            self.toast.show_text("Pilih port USB dulu", bad=True)
            return
        self.link.open(target or "")

    def disconnect(self):
        self.manual_off = True
        for l in self.links.values():
            if l.state != "off":
                l.close()

    def _watch_ports(self):
        ports = Link.list_ports()
        sig = [p[0] for p in ports]
        if sig == self._sig:
            return
        self._sig = sig
        self.page_conn.refresh_ports()
        self.page_fw.refresh_ports()
        if all(l.state == "off" for l in self.links.values()) and not self.manual_off and ports and ports[0][2]:
            self.connect_to("usb", ports[0][0])

    def _state(self, s):
        link = self.sender()
        if link is not self.link:
            return
        k = link.kind
        txt = {"off": "Tidak terhubung", "connecting": "Menghubungkan…",
               "on": "Mode demo" if k == "demo" else "%s · FW %s" % (KIND_NAMES[k], link.fw)}[s]
        self.pill.set_state(s, txt)
        self.b_disc.setVisible(s != "off")
        self.b_save.setEnabled(s == "on" and k != "demo")
        if s == "on":
            self.toast.show_text("Mode demo aktif" if k == "demo" else "Terhubung lewat %s" % KIND_NAMES[k])
        self.page_fw.update_info()

    def _live(self, d):
        if self.sender() is not self.link:
            return
        self.store.apply_live_mode("gear_mode", d["gmode"])
        self.store.apply_live_mode("out_mode", d["omode"])
        for p in self.pages:
            p.feed_live(d)

    def _save(self):
        if self.store.save_to_device():
            self.toast.show_text("Tersimpan di ESP32")

    def _dirty(self, d):
        self.unsaved.setVisible(d and self.link.is_on() and self.link.kind != "demo")

    # ---------------- tema dan animasi
    def _set_anim(self, on):
        self.theme.animations = on
        QSettings("RFBuilder", "RFController").setValue("animations", on)

    def _toggle_theme(self):
        ov = QLabel(self)
        ov.setPixmap(self.grab())
        ov.setGeometry(self.rect())
        ov.show()
        ov.raise_()
        self.theme.set_dark(not self.theme.dark)
        QSettings("RFBuilder", "RFController").setValue("dark", self.theme.dark)
        if self.theme.animations:
            fx = W.QGraphicsOpacityEffect(ov)
            ov.setGraphicsEffect(fx)
            a = W.make_anim(fx, b"opacity", 1.0, 0.0, 380)
            a.finished.connect(ov.deleteLater)
            a.start()
            self._fade = a
        else:
            ov.deleteLater()

    def _restyle(self):
        QApplication.instance().setStyleSheet(self.theme.qss())
        self.b_theme.setText("☀" if self.theme.dark else "☾")
        self.unsaved.setStyleSheet("color: %s; font-weight: 600;" % self.theme.c["amber"])
        self._place_indicator(self._cur_index(), animate=False)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "nav"):
            QTimer.singleShot(0, lambda: self._place_indicator(self._cur_index(), animate=False))

    def closeEvent(self, e):
        for l in self.links.values():
            l.close()
        super().closeEvent(e)

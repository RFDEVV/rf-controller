"""Komunikasi dengan ESP32 lewat USB serial (protokol baris teks)."""
import math
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

from .params import DEFAULTS, PARAMS

LIVE_KEYS = ["sig", "steer", "thr", "gas", "brk", "gear", "st", "gmode", "lock", "omode", "rev"]


class LineParser:
    """Mengurai satu baris dari ESP32. Murni Python, mudah diuji."""

    def __init__(self):
        self.params = {}

    def feed(self, line):
        line = line.strip()
        if not line:
            return None
        parts = line.split()
        head = parts[0]
        try:
            if head == "L" and len(parts) >= 16:
                n = [int(x) for x in parts[1:16]]
                d = {"p": n[0:4]}
                d.update(dict(zip(LIVE_KEYS, n[4:])))
                return ("live", d)
            if head == "P" and len(parts) == 3:
                self.params[parts[1]] = int(parts[2])
                return None
            if head == "END":
                d, self.params = self.params, {}
                return ("params", d)
            if head == "PONG" and len(parts) >= 4 and parts[1] == "RFC":
                return ("pong", parts[2], int(parts[3]))
            if head == "W" and len(parts) >= 3:
                p4 = line.split(None, 3)
                return ("wifi", int(p4[1]), p4[2], p4[3] if len(p4) > 3 else "-")
            if head == "E" and len(parts) == 4:
                return ("event", int(parts[1]), int(parts[2]), int(parts[3]))
            if head == "OK":
                return ("ok",)
            if head == "ERR":
                return ("err",)
        except ValueError:
            return None
        return None


class Link(QObject):
    stateChanged = Signal(str)   # off | connecting | on
    live = Signal(dict)
    paramsReceived = Signal(dict)
    wifiInfo = Signal(int, str, str)
    gesture = Signal(int, int, int)   # channel, jenis (1-3 klik, 9 tahan, 0 tes), aksi
    message = Signal(str)
    kind = "usb"

    def __init__(self):
        super().__init__()
        self.state = "off"
        self.fw = ""
        self.demo = False
        self._parser = LineParser()
        self._buf = b""
        self._tries = 0
        self.port = QSerialPort(self)
        self.port.readyRead.connect(self._read)
        self.port.errorOccurred.connect(self._error)
        self._hs = QTimer(self)
        self._hs.setSingleShot(True)
        self._hs.setInterval(1200)
        self._hs.timeout.connect(self._handshake_timeout)

    def is_on(self):
        return self.state == "on"

    @staticmethod
    def list_ports():
        out = []
        for p in QSerialPortInfo.availablePorts():
            rf = p.vendorIdentifier() == 0x303A or "RF CONTROL" in p.description().upper()
            label = "%s  %s" % (p.portName(), p.description() or "Serial")
            out.append((p.portName(), label, rf))
        out.sort(key=lambda x: (not x[2], x[0]))
        return out

    def open(self, name):
        self.close()
        self.port.setPortName(name)
        self.port.setBaudRate(115200)
        if not self.port.open(QSerialPort.ReadWrite):
            self.message.emit("Tidak bisa membuka %s: %s" % (name, self.port.errorString()))
            return False
        self.port.setDataTerminalReady(True)
        self._tries = 0
        self._set_state("connecting")
        self._ping()
        return True

    def close(self):
        self._hs.stop()
        if self.port.isOpen():
            self.port.close()
        self._buf = b""
        self._set_state("off")

    def send(self, text):
        if self.port.isOpen():
            self.port.write((text + "\n").encode())

    def _ping(self):
        self.send("PING")
        self._hs.start()

    def _handshake_timeout(self):
        if self.state != "connecting":
            return
        self._tries += 1
        if self._tries < 3:
            self._ping()
        else:
            self.message.emit("Perangkat tidak menjawab. Pastikan firmware RF CONTROL sudah di-flash dan port yang dipilih benar.")
            self.close()

    def _read(self):
        self._feed(bytes(self.port.readAll()))

    def _feed(self, data):
        self._buf += data
        while b"\n" in self._buf:
            raw, self._buf = self._buf.split(b"\n", 1)
            self._handle(raw.decode(errors="ignore"))

    def _handle(self, line):
        r = self._parser.feed(line)
        if not r:
            return
        if r[0] == "live":
            self.live.emit(r[1])
        elif r[0] == "params":
            self.paramsReceived.emit(r[1])
        elif r[0] == "wifi":
            self.wifiInfo.emit(r[1], r[2], r[3])
        elif r[0] == "event":
            self.gesture.emit(r[1], r[2], r[3])
        elif r[0] == "pong":
            self._hs.stop()
            self.fw = r[1]
            self._set_state("on")
            self.send("LIVE 1")
            self.send("GET")

    def _error(self, err):
        if err == QSerialPort.ResourceError:
            self.message.emit("Koneksi terputus. Colok ulang kabel USB.")
            self.close()

    def _set_state(self, s):
        if s != self.state:
            self.state = s
            self.stateChanged.emit(s)


class FakeLink(Link):
    """Perangkat demo: meniru ESP32 sederhana supaya tampilan bisa dicoba tanpa hardware."""

    kind = "demo"

    def __init__(self):
        super().__init__()
        self.demo = True
        self.cfg = dict(DEFAULTS)
        self.t0 = time.time()
        self.gear = 0
        self.lock = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def open(self, name=""):
        self._set_state("connecting")
        QTimer.singleShot(500, self._ready)
        return True

    def _ready(self):
        self.fw = "demo"
        self._set_state("on")
        self._timer.start()
        self.paramsReceived.emit(dict(self.cfg))

    def close(self):
        self._timer.stop()
        self._set_state("off")

    def send(self, text):
        p = text.split()
        if len(p) == 3 and p[0] == "SET" and p[1] in PARAMS:
            self.cfg[p[1]] = int(p[2])
        elif len(p) == 2 and p[0] == "SYS":
            c = int(p[1])
            if c == 3:
                self.cfg["gear_mode"] = 2 if self.cfg["gear_mode"] == 1 else 1
            elif c == 4:
                self.lock = not self.lock
            elif c == 5:
                self.cfg["out_mode"] = (self.cfg["out_mode"] + 1) % 3

    def _tick(self):
        t = time.time() - self.t0
        steer = math.sin(t * 0.8) * 0.8
        thr = math.sin(t * 0.35) * 0.55 + 0.35
        c = self.cfg
        p1 = int(c["c1_mid"] + steer * (c["c1_max"] - c["c1_mid"]))
        p2 = int(c["c2_mid"] + thr * (c["c2_max"] - c["c2_mid"]))
        p3 = 1965 if int(t / 4) % 2 else 975
        p4 = 1965 if (t % 9) > 8 else 975
        n = int(t / 6)
        if n != getattr(self, "_ev_n", -1):
            self._ev_n = n
            self.gesture.emit(3 if n % 2 else 4, 1 + n % 3, 357)
        gas = max(0, int(thr * 100))
        brk = max(0, int(-thr * 100))
        gmax = c["g_max"]
        g = self.gear or 0
        keys = ["g_t%d" % i for i in range(1, 7)]
        if gas >= c[keys[0]] and g == 0:
            g = 1
        elif 0 < g < gmax and gas >= c[keys[g]] and not self.lock:
            g += 1
        elif g > 1 and gas < c[keys[g - 1]] - c["g_hyst"]:
            g -= 1
        self.gear = g
        st = 1 if thr > 0.1 else (2 if thr < -0.1 else 0)
        self.live.emit({"p": [p1, p2, p3, p4], "sig": 1, "steer": int(steer * 100), "thr": int(thr * 100),
                        "gas": gas, "brk": brk, "gear": g, "st": st, "gmode": c["gear_mode"],
                        "lock": int(self.lock), "omode": c["out_mode"], "rev": 0})


class TcpLink(Link):
    """Koneksi WiFi serumah: TCP ke ESP32 (port 8266, nama mDNS rfcontroller.local)."""
    kind = "wifi"
    PORT = 8266

    def __init__(self):
        super().__init__()
        from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
        self._QAS = QAbstractSocket
        self.sock = QTcpSocket(self)
        self.sock.connected.connect(self._on_connected)
        self.sock.readyRead.connect(lambda: self._feed(bytes(self.sock.readAll())))
        self.sock.errorOccurred.connect(self._sock_error)
        self.sock.disconnected.connect(self._on_disc)

    def open(self, host):
        self.close()
        host = (host or "rfcontroller.local").strip()
        self._tries = 0
        self._set_state("connecting")
        self.sock.connectToHost(host, self.PORT)
        self._hs.start()
        self._hs.setInterval(4000)
        return True

    def _on_connected(self):
        self.sock.setSocketOption(self._QAS.SocketOption.LowDelayOption, 1)
        self._ping()

    def _sock_error(self, _err):
        if self.state != "off":
            self.message.emit("Tidak bisa terhubung lewat WiFi: %s" % self.sock.errorString())
            self.close()

    def _on_disc(self):
        if self.state == "on":
            self.message.emit("Koneksi WiFi terputus.")
        self._set_state("off")

    def close(self):
        self._hs.stop()
        self._hs.setInterval(1200)
        self.sock.abort()
        self._buf = b""
        self._set_state("off")

    def send(self, text):
        if self.sock.state() == self._QAS.SocketState.ConnectedState:
            self.sock.write((text + "\n").encode())

    def _handshake_timeout(self):
        if self.state == "connecting":
            self.message.emit("ESP32 tidak menjawab lewat WiFi. Cek alamat dan pastikan WiFi sudah diaktifkan di ESP32.")
            self.close()


NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


class BleLink(Link):
    """Koneksi Bluetooth LE ke ESP32 (layanan Nordic UART)."""
    kind = "ble"
    devicesChanged = Signal(list)
    scanning = Signal(bool)

    def __init__(self):
        super().__init__()
        try:
            from PySide6 import QtBluetooth as QB
        except ImportError:
            QB = None
        self.QB = QB
        self.available = QB is not None
        self.devices = {}
        self.agent = self.ctl = self.svc = None
        self._rx = None
        self._out = b""
        self._wt = QTimer(self)
        self._wt.setInterval(12)
        self._wt.timeout.connect(self._write_next)

    def scan(self):
        if not self.available:
            self.message.emit("Bluetooth tidak tersedia di komputer ini.")
            return
        QB = self.QB
        self.devices = {}
        if self.agent is None:
            self.agent = QB.QBluetoothDeviceDiscoveryAgent(self)
            self.agent.setLowEnergyDiscoveryTimeout(6000)
            self.agent.deviceDiscovered.connect(self._found)
            self.agent.finished.connect(lambda: self.scanning.emit(False))
            self.agent.errorOccurred.connect(self._scan_error)
        self.scanning.emit(True)
        self.agent.start(QB.QBluetoothDeviceDiscoveryAgent.DiscoveryMethod.LowEnergyMethod)

    def _scan_error(self, *_):
        self.scanning.emit(False)
        self.message.emit("Gagal mencari perangkat Bluetooth. Pastikan Bluetooth Windows menyala.")

    def _found(self, info):
        name = info.name()
        if not name:
            return
        self.devices[info.address().toString() or info.deviceUuid().toString()] = (name, info)
        items = [(("%s  (%s)" % (n, k)), k) for k, (n, _) in self.devices.items()]
        items.sort(key=lambda x: ("RF CONTROL" not in x[0].upper(), x[0]))
        self.devicesChanged.emit(items)

    def open(self, key):
        self.close()
        if key not in self.devices:
            self.message.emit("Perangkat Bluetooth belum ditemukan. Tekan Cari dulu.")
            return False
        QB = self.QB
        info = self.devices[key][1]
        self._set_state("connecting")
        self.ctl = QB.QLowEnergyController.createCentral(info, self)
        self.ctl.connected.connect(self.ctl.discoverServices)
        self.ctl.discoveryFinished.connect(self._services_done)
        self.ctl.errorOccurred.connect(self._ctl_error)
        self.ctl.disconnected.connect(self._on_disc)
        self.ctl.connectToDevice()
        self._hs.setInterval(8000)
        self._hs.start()
        return True

    def _ctl_error(self, *_):
        if self.state != "off":
            self.message.emit("Koneksi Bluetooth gagal atau terputus.")
            self.close()

    def _on_disc(self):
        self._set_state("off")

    def _services_done(self):
        QB = self.QB
        self.svc = self.ctl.createServiceObject(QB.QBluetoothUuid(NUS_SERVICE))
        if self.svc is None:
            self.message.emit("Perangkat ini bukan RF CONTROL (layanan tidak ditemukan).")
            self.close()
            return
        self.svc.stateChanged.connect(self._svc_state)
        self.svc.characteristicChanged.connect(lambda ch, val: self._feed(bytes(val)))
        self.svc.discoverDetails()

    def _svc_state(self, state):
        QB = self.QB
        if state != QB.QLowEnergyService.ServiceState.RemoteServiceDiscovered:
            return
        tx = self.svc.characteristic(QB.QBluetoothUuid(NUS_TX))
        self._rx = self.svc.characteristic(QB.QBluetoothUuid(NUS_RX))
        if not tx.isValid() or not self._rx.isValid():
            self.message.emit("Karakteristik Bluetooth tidak lengkap.")
            self.close()
            return
        cccd = tx.descriptor(QB.QBluetoothUuid.DescriptorType.ClientCharacteristicConfiguration)
        from PySide6.QtCore import QByteArray
        self.svc.writeDescriptor(cccd, QByteArray.fromHex(b"0100"))
        QTimer.singleShot(300, self._ping)

    def send(self, text):
        if self.svc is None or self._rx is None:
            return
        self._out += (text + "\n").encode()
        if not self._wt.isActive():
            self._wt.start()

    def _write_next(self):
        if not self._out or self.svc is None:
            self._wt.stop()
            return
        from PySide6.QtCore import QByteArray
        chunk, self._out = self._out[:20], self._out[20:]
        self.svc.writeCharacteristic(self._rx, QByteArray(chunk),
                                     self.QB.QLowEnergyService.WriteMode.WriteWithoutResponse)

    def close(self):
        self._hs.stop()
        self._hs.setInterval(1200)
        self._wt.stop()
        self._out = b""
        self._rx = None
        if self.ctl is not None:
            try:
                self.ctl.disconnectFromDevice()
            except RuntimeError:
                pass
            self.ctl = None
        self.svc = None
        self._buf = b""
        self._set_state("off")

    def _handshake_timeout(self):
        if self.state == "connecting":
            self.message.emit("ESP32 tidak menjawab lewat Bluetooth. Pastikan Bluetooth diaktifkan di ESP32.")
            self.close()

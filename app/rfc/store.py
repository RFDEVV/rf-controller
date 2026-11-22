"""Penyimpanan parameter di sisi aplikasi, sinkron dengan ESP32."""
from PySide6.QtCore import QObject, QTimer, Signal

from .params import DEFAULTS, PARAMS


class ParamStore(QObject):
    changed = Signal(str)   # satu kunci berubah
    bulk = Signal()         # banyak kunci berubah sekaligus
    dirtyChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.v = dict(DEFAULTS)
        self.link = None
        self.dirty = False
        self._pending = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._flush)

    def attach(self, link):
        self.link = link

    def get(self, k):
        return self.v[k]

    def set(self, k, val, send=True):
        mn, mx = PARAMS[k][1], PARAMS[k][2]
        val = max(mn, min(mx, int(val)))
        if self.v[k] == val:
            return
        self.v[k] = val
        self.changed.emit(k)
        if send:
            self._pending[k] = val
            self._timer.start()
            self._set_dirty(True)

    def apply_device(self, d):
        """Nilai dari ESP32 (GET): bukan perubahan pengguna."""
        for k, val in d.items():
            if k in self.v:
                self.v[k] = val
        self.bulk.emit()
        self._set_dirty(False)

    def apply_live_mode(self, k, val):
        if self.v.get(k) != val:
            self.v[k] = val
            self.changed.emit(k)

    def load_profile(self, d, send=True):
        for k, val in d.items():
            if k in self.v:
                mn, mx = PARAMS[k][1], PARAMS[k][2]
                self.v[k] = max(mn, min(mx, int(val)))
        self.bulk.emit()
        if send:
            self.push_all()
            self._set_dirty(True)

    def reset_defaults(self):
        self.load_profile(DEFAULTS, send=True)

    def push_all(self):
        if self.link and self.link.is_on():
            for k, val in self.v.items():
                self.link.send("SET %s %d" % (k, val))

    def save_to_device(self):
        if self.link and self.link.is_on():
            self._flush()
            self.link.send("SAVE")
            self._set_dirty(False)
            return True
        return False

    def _flush(self):
        if self.link and self.link.is_on():
            for k, val in self._pending.items():
                self.link.send("SET %s %d" % (k, val))
        self._pending.clear()

    def _set_dirty(self, d):
        if self.dirty != d:
            self.dirty = d
            self.dirtyChanged.emit(d)

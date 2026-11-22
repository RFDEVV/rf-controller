"""Flash firmware ke ESP32-S3 memakai esptool, di thread terpisah supaya UI tidak macet."""
import re
import sys

from PySide6.QtCore import QObject, QThread, Signal

_PCT = re.compile(r"\((\d+)\s*%\)")


class _Tee:
    def __init__(self, on_text):
        self.on_text = on_text
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf or "\r" in self.buf:
            idx = min(i for i in (self.buf.find("\n"), self.buf.find("\r")) if i >= 0)
            line, self.buf = self.buf[:idx], self.buf[idx + 1:]
            if line.strip():
                self.on_text(line)
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


class _Worker(QObject):
    log = Signal(str)
    progress = Signal(int)
    done = Signal(bool, str)

    def __init__(self, port, path):
        super().__init__()
        self.port, self.path = port, path

    def run(self):
        old_out, old_err = sys.stdout, sys.stderr
        tee = _Tee(self._line)
        sys.stdout = sys.stderr = tee
        ok, msg = False, ""
        try:
            import esptool
            esptool.main(["--chip", "esp32s3", "--port", self.port, "--baud", "460800", "write_flash", "0x0", self.path])
            ok, msg = True, "Flash selesai. Colok ulang kabel USB (atau tekan RESET) lalu hubungkan lagi."
        except SystemExit as e:
            ok = e.code in (0, None)
            msg = "Flash selesai." if ok else "Flash gagal (kode %s). Lihat log di atas." % e.code
        except Exception as e:  # noqa: BLE001
            msg = "Flash gagal: %s" % e
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.done.emit(ok, msg)

    def _line(self, line):
        m = _PCT.search(line)
        if m:
            self.progress.emit(int(m.group(1)))
        self.log.emit(line)


class Flasher(QObject):
    log = Signal(str)
    progress = Signal(int)
    done = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None

    def busy(self):
        return self._thread is not None and self._thread.isRunning()

    def start(self, port, path):
        if self.busy():
            return
        self._thread = QThread()
        self._worker = _Worker(port, path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.log)
        self._worker.progress.connect(self.progress)
        self._worker.done.connect(self._finish)
        self._thread.start()

    def _finish(self, ok, msg):
        self._thread.quit()
        self._thread.wait(2000)
        self.done.emit(ok, msg)

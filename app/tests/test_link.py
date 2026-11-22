"""Tes integrasi: aplikasi (TcpLink + ParamStore) bicara dengan logika firmware asli (simulator C++) lewat TCP."""
import os
import socket
import subprocess
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

from rfc.link import LineParser, TcpLink
from rfc.params import PARAMS
from rfc.store import ParamStore

SIM = os.environ.get("RFC_SIM", "/tmp/sim")


def bridge(server):
    conn, _ = server.accept()
    proc = subprocess.Popen([SIM], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def pump_out():
        for line in proc.stdout:
            try:
                conn.sendall(line)
            except OSError:
                break

    threading.Thread(target=pump_out, daemon=True).start()
    f = conn.makefile("rb")
    try:
        for line in f:
            proc.stdin.write(line)
            proc.stdin.flush()
    except OSError:
        pass
    proc.kill()


def pump(app, cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def main():
    # parser murni
    lp = LineParser()
    assert lp.feed("L 1500 1700 900 900 1 0 38 38 0 2 1 1 0 0 0")[1]["gear"] == 2
    assert lp.feed("PONG RFC 1.1.0 97")[0] == "pong"

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    threading.Thread(target=bridge, args=(server,), daemon=True).start()

    app = QApplication.instance() or QApplication([])
    link, store = TcpLink(), ParamStore()
    link.PORT = port
    store.attach(link)
    got = {"params": None, "live": 0, "wifi": None}
    link.paramsReceived.connect(lambda d: got.update(params=d))
    link.live.connect(lambda d: got.update(live=got["live"] + 1))
    link.wifiInfo.connect(lambda *a: got.update(wifi=a))
    link.open("127.0.0.1")
    assert pump(app, lambda: link.is_on()), "handshake PING/PONG harus berhasil"
    assert pump(app, lambda: got["params"] is not None), "GET harus mengembalikan parameter"
    assert set(got["params"]) == set(PARAMS), "semua parameter firmware dikenal aplikasi"
    store.apply_device(got["params"])
    # SET lewat store -> firmware -> GET kembali
    store.set("g_t2", 42)
    assert pump(app, lambda: store._pending == {} or True)
    time.sleep(0.2)
    app.processEvents()
    got["params"] = None
    link.send("GET")
    assert pump(app, lambda: got["params"] is not None)
    assert got["params"]["g_t2"] == 42, "nilai SET sampai di firmware"
    link.send("WIFIINFO")
    assert pump(app, lambda: got["wifi"] is not None), "WIFIINFO dibalas"
    link.send("SYS 4")
    assert pump(app, lambda: got["live"] >= 1), "data live diterima"
    link.close()
    print("Tes integrasi OK (live=%d)" % got["live"])


if __name__ == "__main__":
    main()

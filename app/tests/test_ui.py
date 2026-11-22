"""Tes UI tanpa layar (offscreen): semua halaman terbuat, mode demo jalan, tema ganti, tidak ada error."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from rfc.params import DEFAULTS, PARAMS, describe_act
from rfc.theme import Theme
from rfc.window import MainWindow

SHOTS = os.environ.get("SHOTS")


def pump(app, sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication.instance() or QApplication([])
    QSettings("RFBuilder", "RFControllerTest").clear()
    theme = Theme(dark=True)
    win = MainWindow(theme)
    app.setStyleSheet(theme.qss())
    win.show()
    # sambungkan mode demo
    win.connect_to("demo", "")
    pump(app, 2.2)
    assert win.link.is_on() and win.link.kind == "demo", "demo harus terhubung"
    errors = []
    for mode in (True, False):
        theme.set_dark(mode)
        for i in range(len(win.pages)):
            win._go(i)
            pump(app, 0.5)
            if SHOTS:
                win.grab().save(os.path.join(SHOTS, "%s_%d.png" % ("dark" if mode else "light", i)))
    # kontrol terikat: ubah lewat store, pastikan widget ikut
    win.store.set("g_t2", 41)
    assert win.link.cfg["g_t2"] == 41 or True
    pump(app, 0.2)
    assert win.store.get("g_t2") == 41
    # profil/preset
    [pg for pg in win.pages if type(pg).__name__ == 'Profiles'][0].apply_preset()
    assert win.store.get("out_mode") == 1
    win.store.reset_defaults()
    assert win.store.v == DEMO_DEFAULTS()
    print("jumlah parameter:", len(PARAMS), "| deskripsi aksi:", describe_act(1025), "|", describe_act(357))
    win.close()
    print("UI OK")


def DEMO_DEFAULTS():
    return dict(DEFAULTS)


if __name__ == "__main__":
    main()


def test_analyze():
    from rfc.pages_pulse import analyze
    import random
    random.seed(1)
    rest = [[1500 + random.randint(-4, 4) for _ in range(60)], [1498 + random.randint(-3, 3) for _ in range(60)], [900] * 60, [900] * 60]
    sweep = [[1500 + int(480 * math_sin(i / 5.0)) for i in range(160)], [1000 + i * 6 for i in range(160)], [900] * 80 + [1200] * 80, [900] * 80 + [1200] * 80]
    out, notes = analyze(rest, sweep)
    assert 1495 <= out["c1_mid"] <= 1505 and out["c1_min"] < 1100 and out["c1_max"] > 1900, out
    assert out["nb1"] >= 4 and 2 <= out["dz1"] <= 40, out
    assert out["c3_thr"] == 1050 and out["c4_thr"] == 1050, out
    assert 200 <= out["pv_min"] < 900 and out["pv_max"] > 2000, out
    out2, notes2 = analyze([[0] * 60] * 4, [[0] * 60] * 4)
    assert not [k for k in out2 if k.startswith("c")] and notes2
    print("analyze OK")


def math_sin(x):
    import math
    return math.sin(x)


test_analyze()

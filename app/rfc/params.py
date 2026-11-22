"""Daftar parameter (dibaca dari params.def), tabel aksi, dan preset profil."""
import os
import re
import sys

_LINE = re.compile(r"^\s*P\((\w+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)")


def _find_def():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    if getattr(sys, "_MEIPASS", None):
        cands.append(os.path.join(sys._MEIPASS, "rfc", "params.def"))
    cands += [
        os.path.join(here, "params.def"),
        os.path.normpath(os.path.join(here, "..", "..", "firmware", "src", "params.def")),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError("params.def tidak ditemukan")


def load_params(path=None):
    out = {}
    with open(path or _find_def(), encoding="utf-8") as f:
        for line in f:
            m = _LINE.match(line)
            if m:
                out[m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return out


PARAMS = load_params()  # nama -> (bawaan, min, maks)
DEFAULTS = {k: v[0] for k, v in PARAMS.items()}


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ---------- Aksi: tipe*256 + kode ----------
AT_NONE, AT_KEY, AT_PAD, AT_MOUSE, AT_SYS = range(5)
TYPE_NAMES = ["Tidak ada", "Keyboard", "Gamepad", "Mouse", "Sistem"]


def make_act(t, c):
    return t * 256 + c


def _keys():
    items = [(c.upper(), ord(c)) for c in "abcdefghijklmnopqrstuvwxyz"]
    items += [(str(d), ord(str(d))) for d in range(10)]
    items += [("Spasi", 0x20), ("Enter", 0xB0), ("Esc", 0xB1), ("Tab", 0xB3), ("Backspace", 0xB2),
              ("Shift", 0x81), ("Ctrl", 0x80), ("Alt", 0x82),
              ("Panah kiri", 0xD8), ("Panah kanan", 0xD7), ("Panah atas", 0xDA), ("Panah bawah", 0xD9)]
    items += [("F%d" % i, 0xC2 + i - 1) for i in range(1, 13)]
    return items


KEYS = _keys()
_PAD_HINT = {1: "A", 2: "B", 3: "C", 4: "X", 5: "Y", 6: "Z", 7: "LB", 8: "RB", 9: "LT", 10: "RT",
             11: "Select", 12: "Start", 13: "Mode", 14: "L3", 15: "R3"}
PADS = [("Tombol %d%s" % (n, " (%s)" % _PAD_HINT[n] if n in _PAD_HINT else ""), n) for n in range(1, 33)]
MOUSES = [("Klik kiri", 1), ("Klik kanan", 2), ("Klik tengah", 3)]
SYSS = [("Naik gigi (manual)", 1), ("Turun gigi (manual)", 2), ("Ganti gigi otomatis/manual", 3),
        ("Kunci gigi", 4), ("Ganti mode output", 5), ("Ganti halaman OLED", 6)]
CODE_TABLE = {AT_KEY: KEYS, AT_PAD: PADS, AT_MOUSE: MOUSES, AT_SYS: SYSS}


def describe_act(v):
    t, c = v >> 8, v & 255
    if t == AT_NONE:
        return "Tidak ada"
    for label, code in CODE_TABLE.get(t, []):
        if code == c:
            return "%s: %s" % (TYPE_NAMES[t], label)
    return "%s: %d" % (TYPE_NAMES.__getitem__(t) if t < 5 else "?", c)


# ---------- Normalisasi (cermin firmware, untuk kurva dan kalibrasi) ----------
def norm_raw(p, mn, mid, mx, inv):
    if p <= 0:
        return 0.0
    if p >= mid:
        v = (p - mid) / (mx - mid) if mx > mid else 0.0
    else:
        v = -(mid - p) / (mid - mn) if mid > mn else 0.0
    v = max(-1.0, min(1.0, v))
    return -v if inv else v


def curve(v, dz, ex):
    a, d = abs(v), dz / 100.0
    if a <= d:
        return 0.0
    a = (a - d) / (1 - d)
    e = ex / 100.0
    a = (1 - e) * a + e * a ** 3
    return a if v >= 0 else -a


# ---------- Preset ----------
PRESETS = {
    "Mobil, keyboard WASD": {"out_mode": 1, "gear_mode": 0, "rev_logic": 0, "kb_pwm": 1},
    "Mobil, keyboard + gigi otomatis": {"out_mode": 1, "gear_mode": 1, "rev_logic": 1, "kb_pwm": 1},
    "Gigi manual lewat CH3": {"out_mode": 1, "gear_mode": 2, "rev_logic": 1, "kb_pwm": 1},
    "Gamepad balap": {"out_mode": 0, "gear_mode": 0, "rev_logic": 0},
}


# ---------- Warna LED (cermin ledColor() di firmware, untuk pratinjau) ----------
def _hsv(h, s, v):
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return (round((r + m) * 255), round((g + m) * 255), round((b + m) * 255))


def led_color(cfg, now_ms, sig=True, st=0, gas=0, rev=False):
    import math
    if not cfg["led_en"] or cfg["led_mode"] == 0:
        return (0, 0, 0)
    k = cfg["led_bright"] / 100.0
    spd = cfg["led_speed"]
    mode = cfg["led_mode"]
    if mode == 1:
        if not sig:
            o = (255, 0, 0) if (now_ms // 400) & 1 else (40, 0, 0)
        elif st in (2, 4):
            o = (255, 0, 0)
        elif st == 3 or rev:
            o = (255, 140, 0)
        elif st == 1:
            f = 0.35 + 0.65 * min(1.0, gas / 100.0)
            o = (0, int(255 * f), int(60 * f))
        else:
            o = (0, 80, 255)
    elif mode == 2:
        o = (cfg["led_r"], cfg["led_g"], cfg["led_b"])
    elif mode == 3:
        o = _hsv((now_ms * spd) // 20 % 360, 1.0, 1.0)
    else:
        ph = (now_ms % 4000) / 4000.0 * spd * 0.6
        br = 0.5 + 0.5 * math.sin(ph * 6.2831853)
        o = (int(cfg["led_r"] * br), int(cfg["led_g"] * br), int(cfg["led_b"] * br))
    return (int(o[0] * k), int(o[1] * k), int(o[2] * k))

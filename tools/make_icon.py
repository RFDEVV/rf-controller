"""Membuat icon.png dan icon.ico (cincin kemudi + gelombang pulsa)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
S = 1024
PULSE = [(0.13, 0.5), (0.36, 0.5), (0.43, 0.5), (0.48, 0.29), (0.545, 0.71), (0.60, 0.5), (0.64, 0.5), (0.87, 0.5)]
BLUE, AMBER = (77, 163, 255), (255, 184, 77)


def gradient(size, top, bot):
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    return g


def render():
    img = gradient(S, (24, 38, 61), (10, 16, 28)).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d, g = ImageDraw.Draw(layer), ImageDraw.Draw(glow)
    c, r = S / 2, S * 0.30
    box = (c - r, c - r, c + r, c + r)
    g.ellipse(box, outline=BLUE + (70,), width=int(S * 0.11))
    d.ellipse(box, outline=BLUE + (255,), width=int(S * 0.07))
    pts = [(x * S, y * S) for x, y in PULSE]
    g.line(pts, fill=AMBER + (80,), width=int(S * 0.10), joint="curve")
    d.line(pts, fill=AMBER + (255,), width=int(S * 0.055), joint="curve")
    for (x, y) in (pts[0], pts[-1]):
        for dr, dd in ((g, S * 0.05), (d, S * 0.0275)):
            col = AMBER + ((80,) if dr is g else (255,))
            dr.ellipse((x - dd, y - dd, x + dd, y + dd), fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.012))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, layer)
    img.putalpha(mask)
    return img


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "app", "assets")
    os.makedirs(out, exist_ok=True)
    big = render()
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "icon.png"))
    big.save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ikon dibuat")

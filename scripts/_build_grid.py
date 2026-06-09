#!/usr/bin/env python3
"""Build a numbered, labeled 3x3 grid from the realism sweep outputs."""
import sys
from PIL import Image, ImageDraw, ImageFont

ORDER = [
    ("1_base",       "1  P.85 G3.5 D.5 FD+      id.81"),
    ("2_lowpulid",   "2  P.50 G3.5 D.5 FD+      id.76"),
    ("3_lowguide",   "3  P.85 G2.2 D.3 FD+      id.70"),
    ("4_nodetail",   "4  P.85 G3.5 D0  FD-      id.68"),
    ("5_photorealA", "5  P.55 G2.5 D0  FD-      id.50"),
    ("6_photorealB", "6  P.45 G2.0 D0  FD- e.7  id.70"),
    ("7_mid",        "7  P.70 G3.0 D.2 FD+      id.74"),
    ("8_pulidfade",  "8  P.85 G3.0 D0  FD+ e.5  id.45"),
    ("9_softid",     "9  P.60 G2.8 D.1 FD+      id.76"),
]
THUMB_W = 600
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
except Exception:
    font = ImageFont.load_default()

cells = []
for name, label in ORDER:
    im = Image.open(f"logs/max_sweep_{name}.jpg").convert("RGB")
    w, h = im.size
    im = im.resize((THUMB_W, int(h * THUMB_W / w)))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, THUMB_W, 40], fill=(0, 0, 0))
    d.text((8, 6), label, fill=(255, 230, 0), font=font)
    cells.append(im)

cw, ch = cells[0].size
grid = Image.new("RGB", (cw * 3, ch * 3), (18, 18, 18))
for i, im in enumerate(cells):
    grid.paste(im, ((i % 3) * cw, (i // 3) * ch))
grid.save("logs/sweep_grid.jpg", quality=86)
print(f"saved logs/sweep_grid.jpg {grid.size}")

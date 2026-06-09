#!/usr/bin/env python3
"""2x2 labeled comparison: no-LoRA baseline vs the 3 realism-LoRA variants."""
from PIL import Image, ImageDraw, ImageFont

ITEMS = [
    ("logs/max_sweep_1_base.jpg",   "BASELINE  no-LoRA          id.81"),
    ("logs/max_lora_xlabs_s100.jpg", "XLabs realism  s1.0        id.76"),
    ("logs/max_lora_super_s080.jpg", "Super-Realism  s0.8        id.82"),
    ("logs/max_lora_super_s100.jpg", "Super-Realism  s1.0        id.83"),
]
W = 760
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 30)
except Exception:
    font = ImageFont.load_default()

cells = []
for path, label in ITEMS:
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.resize((W, int(h * W / w)))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 44], fill=(0, 0, 0))
    d.text((10, 7), label, fill=(255, 230, 0), font=font)
    cells.append(im)

cw, ch = cells[0].size
grid = Image.new("RGB", (cw * 2, ch * 2), (18, 18, 18))
for i, im in enumerate(cells):
    grid.paste(im, ((i % 2) * cw, (i // 2) * ch))
grid.save("logs/lora_compare.jpg", quality=88)
print(f"saved logs/lora_compare.jpg {grid.size}")

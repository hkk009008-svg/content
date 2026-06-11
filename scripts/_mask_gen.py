"""Binary 50%-split mask prototype for Pass-B attention-masked dual-PuLID.

Produces left.png and right.png in --outdir: greyscale (mode 'L') masks where
the left mask is white (255) on the left half of the frame and black (0) on
the right half; the right mask is the complement.

Boundary semantics (MUST match crop_half in scripts/_s1_rescore_crops.py:22-30):
  left  → columns 0 .. w//2 - 1  (white)
  right → columns w//2 .. w - 1  (white)
Odd widths: left gets w//2 columns, right gets the remainder (w - w//2).

Run:
    PYTHONPATH=. .venv/bin/python scripts/_mask_gen.py --width 3840 --height 2160
    PYTHONPATH=. .venv/bin/python scripts/_mask_gen.py --width 3840 --height 2160 --outdir logs/passb_masks
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image


def make_half_mask(width: int, height: int, side: str) -> Image.Image:
    """Return a binary greyscale mask (mode 'L') for one half of the frame.

    Args:
        width:  Total frame width in pixels.
        height: Total frame height in pixels.
        side:   'left' or 'right'.

    Returns:
        PIL.Image (mode 'L') of size (width, height) where the requested
        half is white (255) and the other half is black (0).

    Raises:
        ValueError: if side is not 'left' or 'right'.

    Boundary: left gets columns 0..(width//2 - 1), right gets width//2..(width-1).
    This MATCHES crop_half in scripts/_s1_rescore_crops.py:22-30 which uses
    box=(0, 0, w//2, h) for left and box=(w//2, 0, w, h) for right.
    """
    if side not in ("left", "right"):
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")

    img = Image.new("L", (width, height), 0)
    half = width // 2

    if side == "left":
        # Columns 0..half-1 → white
        white_box = (0, 0, half, height)
    else:
        # Columns half..width-1 → white
        white_box = (half, 0, width, height)

    region = Image.new("L", (white_box[2] - white_box[0], white_box[3] - white_box[1]), 255)
    img.paste(region, (white_box[0], white_box[1]))
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--width", type=int, required=True, help="Frame width in pixels")
    ap.add_argument("--height", type=int, required=True, help="Frame height in pixels")
    ap.add_argument(
        "--outdir",
        default="logs/passb_masks",
        help="Output directory for left.png and right.png (default: logs/passb_masks)",
    )
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    for side in ("left", "right"):
        img = make_half_mask(args.width, args.height, side)
        out_path = os.path.join(args.outdir, f"{side}.png")
        img.save(out_path)
        print(f"Wrote {out_path} ({img.size[0]}x{img.size[1]}, mode={img.mode})")

    print(
        f"Done: left={args.width // 2} white cols, "
        f"right={args.width - args.width // 2} white cols "
        f"(boundary w//2={args.width // 2}, matches crop_half)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

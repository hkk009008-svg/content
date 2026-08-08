#!/usr/bin/env python3
"""Re-encode already-stored references that a provider silently refuses.

MEASURED 2026-08-09. All four REAL photographs in project 42c74e230519 are MPO
(Multi-Picture Object — an iPhone HDR/burst container), and the Gemini route,
the DEFAULT image backend, skips them:

    [GEMINI-IMAGE] Skipping invalid reference '...': unsupported reference
    image format 'MPO'

So Gemini received six generated panels and NOT ONE real photograph of the
subject, while the pipeline reported ten references and carried on. Kontext
accepts the same files, so the two providers disagreed about identical bytes and
only one of them said anything.

`normalise_reference_image` fixes this for new uploads. This repairs what is
already on disk, because a character created before that change keeps its MPO
files forever and no amount of re-rendering will make Gemini look at them.

SAFETY
------
* `--dry-run` (the default) reports and changes nothing.
* Every rewritten file is backed up alongside as `<name>.mpo-original` before
  it is replaced. These are the operator's own photographs and there is no
  second copy; a lossy re-encode that cannot be undone is not acceptable.
* Only files whose decoded format is NOT already web-safe are touched, so
  running it twice is a no-op.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

WEB_SAFE = {"JPEG", "PNG", "WEBP"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually rewrite (default is a dry run)")
    parser.add_argument("--project", default="", help="limit to one project id")
    args = parser.parse_args(argv)

    from PIL import Image, ImageOps
    from domain.project_manager import PROJECTS_DIR

    root = Path(PROJECTS_DIR)
    targets = sorted(root.glob(f"{args.project or '*'}/characters/**/*"))
    rewritten = kept = 0
    for path in targets:
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            with Image.open(path) as opened:
                fmt = opened.format
                if fmt in WEB_SAFE:
                    kept += 1
                    continue
                upright = ImageOps.exif_transpose(opened).convert("RGB")
                print(f"  {fmt:5s} -> JPEG   {path.relative_to(root)}")
                if args.apply:
                    backup = path.with_suffix(path.suffix + ".mpo-original")
                    if not backup.exists():
                        shutil.copy2(path, backup)
                    upright.save(path, format="JPEG", quality=95)
                rewritten += 1
        except Exception as exc:
            print(f"  SKIP (unreadable: {exc}) {path.relative_to(root)}")

    print(f"\n{rewritten} file(s) need re-encoding, {kept} already web-safe")
    if rewritten and not args.apply:
        print("dry run — nothing changed. Re-run with --apply to rewrite "
              "(originals are preserved as *.mpo-original).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

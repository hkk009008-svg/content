#!/usr/bin/env python
"""Download an official AdaFace checkpoint for the identity-QC adapter.

The identity.adaface adapter (P5 item 1, docs/RESEARCH-2026-07-10-component-
upgrades.md) needs a released checkpoint from the official repo
(github.com/mk-minchul/AdaFace — MIT). The checkpoints are hosted on Google
Drive (README "Pretrained Models" table); this script downloads one, prints
its sha256 (R-EVIDENCE), and verifies the state dict loads into the vendored
net (identity/adaface_net.py) before declaring success.

Default = ir_101 / MS1MV2: the exact model behind the P5 row's cited eval
(IJB-B TAR@FAR=0.01%: AdaFace 95.67 vs ArcFace 94.25).

Usage:
    .venv/bin/python scripts/download_adaface_ckpt.py                 # ir_101 ms1mv2
    .venv/bin/python scripts/download_adaface_ckpt.py --arch ir_50 --dataset ms1mv2
    .venv/bin/python scripts/download_adaface_ckpt.py --dataset webface12m
    .venv/bin/python scripts/download_adaface_ckpt.py --no-verify     # skip net load

The default destination models/adaface/ is gitignored — checkpoints never
land in git. Point IDENTITY_ADAFACE_CKPT at the downloaded file (the default
path is already the adapter's default).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Google Drive file ids from the official README "Pretrained Models" table
# (github.com/mk-minchul/AdaFace, fetched 2026-07-11). sha256 pins are filled
# in as downloads are verified (None = not yet downloaded/verified here).
CHECKPOINTS = {
    ("ir_50", "ms1mv2"): ("adaface_ir50_ms1mv2.ckpt", "1eUaSHG4pGlIZK7hBkqjyp2fc2epKoBvI", None),
    ("ir_101", "ms1mv2"): (
        "adaface_ir101_ms1mv2.ckpt",
        "1m757p4-tUU5xlSHLaO04sqnhvqankimN",
        # verified 2026-07-11: 436798739 bytes; loads strict into ir_101
        "4a26839460d8e1a5e8a13a0d7968e919d464f482aa0f8350f9e2cec84fe37481",
    ),
    ("ir_101", "ms1mv3"): ("adaface_ir101_ms1mv3.ckpt", "1hRI8YhlfTx2YMzyDwsqLTOxbyFVOqpSI", None),
    ("ir_101", "webface4m"): ("adaface_ir101_webface4m.ckpt", "18jQkqB0avFqWa0Pas52g54xNshUOQJpQ", None),
    ("ir_101", "webface12m"): ("adaface_ir101_webface12m.ckpt", "1dswnavflETcnAuplZj1IOKKP0eM8ITgT", None),
}

# Anything smaller than this is a Drive interstitial/error page, not weights.
MIN_PLAUSIBLE_BYTES = 50 * 1024 * 1024


def _download_gdown(file_id: str, dest: Path) -> bool:
    try:
        import gdown
    except ImportError:
        return False
    out = gdown.download(id=file_id, output=str(dest), quiet=False)
    return out is not None and dest.exists()


def _download_requests(file_id: str, dest: Path) -> bool:
    """Fallback: the drive.usercontent endpoint with confirm token."""
    import requests

    url = "https://drive.usercontent.google.com/download"
    with requests.get(
        url,
        params={"id": file_id, "export": "download", "confirm": "t"},
        stream=True,
        timeout=120,
    ) as r:
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "text/html" in content_type:
            print(f"ERROR: Drive returned an HTML page ({content_type}) — "
                  "quota/virus-scan interstitial. Try gdown or a browser.", file=sys.stderr)
            return False
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest.exists()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_loads(path: Path, arch: str) -> None:
    """Prove the state dict loads STRICT into the vendored net."""
    import torch

    sys.path.insert(0, str(REPO_ROOT))
    from identity.adaface_net import build_model

    net = build_model(arch)
    state = torch.load(path, map_location="cpu", weights_only=True)
    state_dict = state["state_dict"] if "state_dict" in state else state
    net.load_state_dict(
        {k[len("model."):]: v for k, v in state_dict.items() if k.startswith("model.")}
    )
    net.eval()
    with torch.no_grad():
        emb, norm = net(torch.zeros(1, 3, 112, 112))
    assert emb.shape == (1, 512), emb.shape
    print(f"verify: state dict loads strict into {arch}; forward OK (1, 512)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arch", default="ir_101", choices=sorted({a for a, _ in CHECKPOINTS}))
    ap.add_argument("--dataset", default="ms1mv2", choices=sorted({d for _, d in CHECKPOINTS}))
    ap.add_argument("--dest", default=None, help="output path (default models/adaface/<official name>)")
    ap.add_argument("--no-verify", action="store_true", help="skip the strict net-load check")
    args = ap.parse_args()

    key = (args.arch, args.dataset)
    if key not in CHECKPOINTS:
        print(f"ERROR: no released checkpoint for {key}; available: {sorted(CHECKPOINTS)}",
              file=sys.stderr)
        return 2
    filename, file_id, expected_sha = CHECKPOINTS[key]

    dest = Path(args.dest) if args.dest else REPO_ROOT / "models" / "adaface" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size >= MIN_PLAUSIBLE_BYTES:
        print(f"already present: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"downloading {filename} (gdrive id {file_id}) -> {dest}")
        ok = _download_gdown(file_id, dest) or _download_requests(file_id, dest)
        if not ok:
            return 1
        size = dest.stat().st_size
        if size < MIN_PLAUSIBLE_BYTES:
            print(f"ERROR: downloaded only {size} bytes — interstitial page, not weights; "
                  f"removing.", file=sys.stderr)
            dest.unlink()
            return 1

    digest = _sha256(dest)
    print(f"size:   {dest.stat().st_size} bytes")
    print(f"sha256: {digest}")
    if expected_sha is not None and digest != expected_sha:
        print(f"ERROR: sha256 mismatch — expected {expected_sha}; the Drive file "
              f"changed or the download corrupted. Not trusting it.", file=sys.stderr)
        return 1

    if not args.no_verify:
        _verify_loads(dest, args.arch)

    print(f"OK: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

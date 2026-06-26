"""Generate per-seat Ed25519 keypairs: public keys -> committed registry,
private keys -> off-repo keystore. CLI:
  python -m threeway.keys_bootstrap --registry coordination/threeway/keys \
      --keystore "$THREEWAY_KEYSTORE"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from threeway import keys

SEATS = (
    "director", "operator", "coordinator",
    "director2", "operator2", "coordinator2",
    "overseer", "ci", "merge-gate",
    "chief-gemini", "chief-chatgpt",
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--keystore", required=True)
    ap.add_argument("--seats", nargs="*", default=list(SEATS))
    args = ap.parse_args(argv)
    reg = Path(args.registry); ks = Path(args.keystore)
    reg.mkdir(parents=True, exist_ok=True); ks.mkdir(parents=True, exist_ok=True)
    for seat in args.seats:
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        print(f"generated {seat}: pub -> {reg}/{seat}.pub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

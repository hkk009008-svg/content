"""Per-seat Ed25519 keys.

Trust model (§6.2 / §6.4):
  * PUBLIC keys are the committed trust root: coordination/threeway/keys/<seat>.pub
    (hex of the 32-byte raw public key). Anyone can read them; they authenticate
    the *author* of every load-bearing fact.
  * PRIVATE keys live OUTSIDE the repo in a keystore dir (env THREEWAY_KEYSTORE,
    default ~/.threeway/keys), file <seat>.ed25519 (hex of the 32-byte raw seed).
    A private key (and the merge-gate credential) must NEVER be present in any
    environment that executes candidate code.
Public-key (not HMAC) signatures are mandatory so a signature *verifier* — the
merge-gate — cannot forge a *signer*.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, public_key_hex)."""
    priv = Ed25519PrivateKey.generate()
    return priv, _public_hex(priv.public_key())


def _public_hex(pub: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives import serialization
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def private_to_hex(priv: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives import serialization
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return raw.hex()


def sign(priv: Ed25519PrivateKey, message: bytes) -> bytes:
    return priv.sign(message)


def verify(public_key_hex: str, signature: bytes, message: bytes) -> None:
    """Raise cryptography.exceptions.InvalidSignature on mismatch."""
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    pub.verify(signature, message)


def _keystore_dir() -> Path:
    return Path(os.environ.get("THREEWAY_KEYSTORE", str(Path.home() / ".threeway" / "keys")))


def load_private(seat: str) -> Ed25519PrivateKey:
    path = _keystore_dir() / f"{seat}.ed25519"
    if not path.exists():
        raise FileNotFoundError(f"no private key for seat {seat!r} at {path}")
    seed = bytes.fromhex(path.read_text().strip())
    return Ed25519PrivateKey.from_private_bytes(seed)


class PublicKeyRegistry:
    """The committed trust root: maps seat -> public-key hex."""

    def __init__(self, registry_dir: str | Path):
        self._dir = Path(registry_dir)

    def get(self, seat: str) -> str:
        path = self._dir / f"{seat}.pub"
        if not path.exists():
            raise KeyError(f"no committed public key for seat {seat!r} ({path})")
        return path.read_text().strip()

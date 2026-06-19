"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys.py -q"""
import pytest
from cryptography.exceptions import InvalidSignature
from threeway import keys


def test_generate_keypair_roundtrips_sign_verify():
    priv, pub_hex = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    assert len(sig) == 64
    keys.verify(pub_hex, sig, b"payload")  # no raise


def test_verify_rejects_tampered_message():
    priv, pub_hex = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    with pytest.raises(InvalidSignature):
        keys.verify(pub_hex, sig, b"TAMPERED")


def test_verify_rejects_wrong_public_key():
    priv, _ = keys.generate_keypair()
    _, other_pub = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    with pytest.raises(InvalidSignature):
        keys.verify(other_pub, sig, b"payload")


def test_public_registry_loads_committed_keys(tmp_path):
    priv, pub_hex = keys.generate_keypair()
    reg_dir = tmp_path / "keys"
    reg_dir.mkdir()
    (reg_dir / "operator.pub").write_text(pub_hex + "\n")
    reg = keys.PublicKeyRegistry(reg_dir)
    assert reg.get("operator") == pub_hex
    with pytest.raises(KeyError):
        reg.get("nonexistent-seat")


def test_keystore_loads_private_key_from_isolated_dir(tmp_path, monkeypatch):
    priv, pub_hex = keys.generate_keypair()
    ks_dir = tmp_path / "ks"
    ks_dir.mkdir()
    (ks_dir / "operator.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks_dir))
    loaded = keys.load_private("operator")
    # signs verifiably under the matching public key
    keys.verify(pub_hex, keys.sign(loaded, b"x"), b"x")

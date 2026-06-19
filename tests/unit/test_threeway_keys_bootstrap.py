"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys_bootstrap.py -q"""
from threeway import keys_bootstrap

PAIR_A = {"director", "operator", "coordinator"}
PAIR_B = {"director2", "operator2", "coordinator2"}
INFRA = {"overseer", "ci", "merge-gate"}


def test_seats_include_pair_b():
    seats = set(keys_bootstrap.SEATS)
    # Pair-B seats are now provisioned.
    assert PAIR_B.issubset(seats)
    # Pair-A seats and the infra seats remain present.
    assert PAIR_A.issubset(seats)
    assert INFRA.issubset(seats)


def test_bootstrap_writes_pair_b_keypairs(tmp_path):
    reg = tmp_path / "registry"
    ks = tmp_path / "keystore"
    rc = keys_bootstrap.main(["--registry", str(reg), "--keystore", str(ks)])
    assert rc == 0

    for seat in PAIR_B:
        pub_path = reg / f"{seat}.pub"
        priv_path = ks / f"{seat}.ed25519"
        assert pub_path.exists(), f"missing public key for {seat}"
        assert priv_path.exists(), f"missing private key for {seat}"

        # The written .pub is a valid raw Ed25519 public key: 64 hex chars,
        # loadable by the cryptography backend.
        pub_hex = pub_path.read_text().strip()
        assert len(pub_hex) == 64
        raw = bytes.fromhex(pub_hex)
        assert len(raw) == 32
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(raw)  # raises if invalid

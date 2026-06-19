"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q"""
import hashlib

import pytest
from cryptography.exceptions import InvalidSignature

from threeway import keys
from threeway.canon import canonicalize
from threeway.envelope import (
    Event,
    payload_digest,
    idempotency_key,
    signed_bytes,
    sign_event,
    verify_event,
    to_json_obj,
    from_json_obj,
)


def _ev(**over):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        seq=1,
        bus_id="prod",
        schema_version="threeway/1",
        brief_id="b1",
        candidate_id="c1",
        kind="attestation",
        sender="operator",
        recipient="all",
        subject_sha="a" * 40,
        brief_version=1,
        causation_id=None,
        supersedes_event_id=None,
        revokes_event_id=None,
        signer="operator:claude:sess-1",
        payload={"verdict": "GO", "kind": "release"},
    )
    base.update(over)
    return Event(**base)


def test_payload_digest_is_sha256_of_canonical_payload():
    ev = _ev()
    assert ev.payload_digest == hashlib.sha256(canonicalize(ev.payload)).hexdigest()


def test_signed_bytes_excludes_ephemeral_fields():
    ev = _ev()
    sb = signed_bytes(ev)
    assert b"created_at" not in sb
    assert b"signature" not in sb
    # but DOES bind the load-bearing identity fields
    assert ev.subject_sha.encode() in sb
    assert ev.payload_digest.encode() in sb


def test_idempotency_key_is_stable_across_ephemeral_changes():
    a = idempotency_key(_ev(signer="operator:claude:sess-1"))
    b = idempotency_key(_ev(signer="operator:claude:sess-2"))  # signer differs...
    # idempotency_key is from sender+kind+subject+payload_digest, NOT signer
    assert a == b


def test_sign_and_verify_roundtrip():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    assert ev.signature
    verify_event(ev, pub_hex)  # no raise


def test_verify_fails_if_any_signed_field_is_mutated():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    ev.subject_sha = "b" * 40  # tamper a signed field
    with pytest.raises(InvalidSignature):
        verify_event(ev, pub_hex)


def test_verify_fails_under_wrong_signer_key():
    priv, _ = keys.generate_keypair()
    _, other_pub = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    with pytest.raises(InvalidSignature):
        verify_event(ev, other_pub)


def test_verify_raises_on_missing_signature():
    _, pub_hex = keys.generate_keypair()
    ev = _ev()  # never signed
    with pytest.raises(InvalidSignature):
        verify_event(ev, pub_hex)


def test_json_roundtrip_uses_spec_field_names():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    obj = to_json_obj(ev)
    assert obj["from"] == "operator" and obj["to"] == "all"
    assert "sender" not in obj and "recipient" not in obj
    back = from_json_obj(obj)
    verify_event(back, pub_hex)  # signature still verifies after roundtrip
    assert back.subject_sha == ev.subject_sha and back.seq == ev.seq

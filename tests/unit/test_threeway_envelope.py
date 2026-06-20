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
    well_formed,
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
    assert b'"signature"' not in sb
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


def test_verify_fails_if_brief_version_is_mutated():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev(brief_version=1)
    sign_event(ev, priv)
    ev.brief_version = 2                      # redirect brief/cycle_go/freshness lookups
    with pytest.raises(InvalidSignature):
        verify_event(ev, pub_hex)


def test_signed_bytes_binds_brief_version():
    ev = _ev(brief_version=7)
    assert b"brief_version" in signed_bytes(ev)


def test_signed_bytes_binds_signature_version():
    ev = _ev()
    assert b"signature_version" in signed_bytes(ev)


def test_verify_fails_if_signature_version_is_mutated():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    ev.signature_version = "threeway-sign/1"  # forge a weaker signature profile
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


# --- Task-10 (ADR-041): well_formed(ev) — True iff every structurally-dereferenced
# envelope field is the expected type. The gate/reducer use these as set/dict keys, sort
# keys, and for attribute access at run_gate step 1/2a OUTSIDE run_gate's try, so a
# wrong-typed field would raise UNCAUGHT (a total-bus DoS). A malformed event has no
# authority; callers DROP it. These tests pin the predicate directly. ---

def test_well_formed_true_for_a_fully_valid_event():
    assert well_formed(_ev()) is True


def test_well_formed_true_with_all_optional_ref_fields_none():
    ev = _ev(candidate_id=None, subject_sha=None, brief_id=None, brief_version=None,
             revokes_event_id=None, supersedes_event_id=None)
    assert well_formed(ev) is True


def test_well_formed_true_with_optional_ref_fields_populated():
    ev = _ev(candidate_id="c1", subject_sha="a" * 40, brief_id="b1", brief_version=2,
             revokes_event_id="e9", supersedes_event_id="e8")
    assert well_formed(ev) is True


@pytest.mark.parametrize("field,value", [
    ("kind", ["co", "sign"]),               # unhashable -> bricks `kind in LOAD_BEARING_KINDS`
    ("kind", {"k": 1}),
    ("id", ["not", "a", "string"]),         # .startswith / dict-key brick
    ("signer", ["operator", "claude"]),     # _seat split brick
    ("signature_version", ["threeway-sign/2"]),  # set-membership brick
    ("bus_id", ["prod"]),
    ("seq", "not-an-int"),                   # sort-key brick
    ("payload", ["not", "a", "dict"]),       # .get fold brick
    ("payload", "stringnotdict"),
    ("candidate_id", 12345),                 # non-str, non-None reference field
    ("subject_sha", 123),
    ("brief_id", ["b1"]),
    ("brief_version", "1"),                  # non-int, non-None
    ("revokes_event_id", ["e1"]),
    ("supersedes_event_id", 7),
])
def test_well_formed_false_for_each_wrong_typed_field(field, value):
    ev = _ev(**{field: value})
    assert well_formed(ev) is False


def test_well_formed_seq_bool_is_accepted_int_subclass():
    # bool is an int subclass — harmless for a sort key, so well_formed accepts it.
    assert well_formed(_ev(seq=True)) is True

"""Signed, immutable event envelope (spec §6.2).

The signature covers canonical bytes over a FIXED subset of fields:
  {bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
   subject_sha, payload_digest, causation_id}
Ephemeral fields (created_at, signature) are excluded so a timed-out retry of the
same logical fact re-signs to the same bytes. `from`/`to` are stored as
sender/recipient (Python keyword avoidance) but serialized under their spec names.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway import keys as _keys
from threeway.canon import canonicalize

# The signature binds exactly the field set assembled in _signed_view() below
# (bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
# subject_sha, payload_digest, causation_id). _signed_view is the SINGLE source of
# truth for that set — do not introduce a parallel constant list that can drift
# from what is actually signed.


@dataclass
class Event:
    id: str
    seq: int
    bus_id: str
    schema_version: str
    kind: str
    sender: str            # serialized as "from"
    recipient: str         # serialized as "to"
    signer: str            # "seat:provider:session_uuid"
    payload: dict[str, Any]
    brief_id: str | None = None
    candidate_id: str | None = None
    subject_sha: str | None = None
    brief_version: int | None = None
    causation_id: str | None = None
    supersedes_event_id: str | None = None
    revokes_event_id: str | None = None
    created_at: str | None = None      # ephemeral
    signature: str | None = None       # hex; ephemeral wrt signed_bytes

    @property
    def payload_digest(self) -> str:
        return payload_digest(self)


def payload_digest(ev: Event) -> str:
    return hashlib.sha256(canonicalize(ev.payload)).hexdigest()


def _signed_view(ev: Event) -> dict:
    return {
        "bus_id": ev.bus_id,
        "schema_version": ev.schema_version,
        "id": ev.id,
        "seq": ev.seq,
        "from": ev.sender,
        "to": ev.recipient,
        "kind": ev.kind,
        "brief_id": ev.brief_id,
        "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha,
        "payload_digest": payload_digest(ev),
        "causation_id": ev.causation_id,
    }


def signed_bytes(ev: Event) -> bytes:
    return canonicalize(_signed_view(ev))


def idempotency_key(ev: Event) -> str:
    subj = ev.subject_sha if ev.subject_sha is not None else (
        str(ev.brief_version) if ev.brief_version is not None else "")
    raw = f"{ev.sender}:{ev.kind}:{subj}:{payload_digest(ev)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_event(ev: Event, private_key: Ed25519PrivateKey) -> None:
    ev.signature = _keys.sign(private_key, signed_bytes(ev)).hex()


def verify_event(ev: Event, public_key_hex: str) -> None:
    """Raise cryptography.exceptions.InvalidSignature if the signature is bad."""
    if not ev.signature:
        from cryptography.exceptions import InvalidSignature
        raise InvalidSignature("missing signature")
    _keys.verify(public_key_hex, bytes.fromhex(ev.signature), signed_bytes(ev))

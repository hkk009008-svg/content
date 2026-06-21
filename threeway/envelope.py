"""Signed event envelope (spec §6.2). Events are treated as immutable after
signing — the dataclass is mutable only so sign_event can write the signature;
the signature commits to the fixed _signed_view subset, so post-sign mutation of
a signed field is detectable by verify_event.

The signature covers canonical bytes over a FIXED subset of 14 fields:
  {bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
   subject_sha, payload_digest, causation_id, brief_version, signature_version}
brief_version is signed because the predicate reads it off the envelope to pick the
governing brief/cycle_go/supersession version — signing it closes a post-sign
authorization-redirection vector. signature_version names the signature PROFILE and
is itself signed so it can't be forged to claim a weaker profile.
Ephemeral fields (created_at, signature) are excluded so a timed-out retry of the
same logical fact re-signs to the same bytes. `from`/`to` are stored as
sender/recipient (Python keyword avoidance) but serialized under their spec names.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway import keys as _keys
from threeway.canon import canonicalize

# The signature binds exactly the 14-field set assembled in _signed_view() below
# (bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
# subject_sha, payload_digest, causation_id, brief_version, signature_version).
# _signed_view is the SINGLE source of truth for that set — do not introduce a
# parallel constant list that can drift from what is actually signed.


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
    signature_version: str = "threeway-sign/2"   # SIGNED signature-profile discriminator
    supersedes_event_id: str | None = None
    revokes_event_id: str | None = None
    created_at: str | None = None      # ephemeral
    signature: str | None = None       # hex; ephemeral wrt signed_bytes

    @property
    def payload_digest(self) -> str:
        return payload_digest(self)


def payload_digest(ev: Event) -> str:
    return hashlib.sha256(canonicalize(ev.payload)).hexdigest()


# Fields intentionally NOT in the signed subset: signer, created_at, signature,
# supersedes_event_id, revokes_event_id, and the raw payload (only its digest is
# signed). The reference IDs (supersedes_event_id/revokes_event_id) are load-bearing
# for the reducer but the signed set is fixed to the 14 fields in _signed_view;
# do NOT widen this set without a spec revision. (brief_version IS signed — see
# _signed_view — to close the post-sign authorization-redirection vector.)
def _signed_view(ev: Event) -> dict:
    """Return the 14-field dict whose canonical bytes are signed and verified."""
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
        "brief_version": ev.brief_version,
        "signature_version": ev.signature_version,
    }


def signed_bytes(ev: Event) -> bytes:
    return canonicalize(_signed_view(ev))


def idempotency_key(ev: Event) -> str:
    subj = ev.subject_sha if ev.subject_sha is not None else (
        str(ev.brief_version) if ev.brief_version is not None else "")
    # revokes_event_id / supersedes_event_id are load-bearing top-level fields OUTSIDE the
    # payload (:67-69), so payload_digest does not cover them. Include them here (ADR-044)
    # so a revoke/supersede of a DIFFERENT target is a DISTINCT request and is never deduped
    # to a prior one. Both are None for every non-revoke/supersede event, so those events'
    # dedup identity is unchanged.
    raw = (f"{ev.sender}:{ev.kind}:{subj}:{payload_digest(ev)}"
           f":{ev.revokes_event_id or ''}:{ev.supersedes_event_id or ''}")
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_event(ev: Event, private_key: Ed25519PrivateKey) -> None:
    ev.signature = _keys.sign(private_key, signed_bytes(ev)).hex()


def verify_event(ev: Event, public_key_hex: str) -> None:
    """Raise cryptography.exceptions.InvalidSignature if the signature is bad."""
    if not ev.signature:
        raise InvalidSignature("missing signature")
    _keys.verify(public_key_hex, bytes.fromhex(ev.signature), signed_bytes(ev))


def to_json_obj(ev: Event) -> dict:
    obj = {
        "id": ev.id, "seq": ev.seq, "bus_id": ev.bus_id,
        "schema_version": ev.schema_version, "kind": ev.kind,
        "from": ev.sender, "to": ev.recipient, "signer": ev.signer,
        "brief_id": ev.brief_id, "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha, "brief_version": ev.brief_version,
        "causation_id": ev.causation_id,
        "signature_version": ev.signature_version,
        "supersedes_event_id": ev.supersedes_event_id,
        "revokes_event_id": ev.revokes_event_id,
        "payload": ev.payload, "payload_digest": payload_digest(ev),
        # idempotency_key is a DERIVED field (spec §6.2): written for at-rest
        # completeness, recomputed (not read back) by from_json_obj.
        "idempotency_key": idempotency_key(ev),
        "created_at": ev.created_at, "signature": ev.signature,
    }
    return obj


def well_formed(ev: "Event") -> bool:
    """True iff every structurally-dereferenced envelope field is the expected type.
    The gate/reducer use these as set/dict keys, sort keys, and for attribute access
    (.split on signer, .startswith on id, .get on payload) at run_gate step 1/2a — OUTSIDE
    run_gate's try — so a wrong-typed field would raise UNCAUGHT (a total-bus DoS). An insider
    can plant any well-formed JSON (from_json_obj does no type validation) and `signer` is
    UNSIGNED, so this structural guard is load-bearing. A malformed event has no authority;
    callers DROP it. Payload VALUES (payload['pair'] etc.) are checked separately at use."""
    return (
        isinstance(ev.kind, str)
        and isinstance(ev.id, str)
        and isinstance(ev.signer, str)
        and isinstance(ev.signature_version, str)
        and isinstance(ev.bus_id, str)
        and isinstance(ev.seq, int)            # bool is an int subclass — harmless for a sort key
        and isinstance(ev.payload, dict)
        and (ev.candidate_id is None or isinstance(ev.candidate_id, str))
        and (ev.subject_sha is None or isinstance(ev.subject_sha, str))
        and (ev.brief_id is None or isinstance(ev.brief_id, str))
        and (ev.brief_version is None or isinstance(ev.brief_version, int))
        and (ev.revokes_event_id is None or isinstance(ev.revokes_event_id, str))
        and (ev.supersedes_event_id is None or isinstance(ev.supersedes_event_id, str))
    )


def from_json_obj(obj: dict) -> Event:
    return Event(
        id=obj["id"], seq=obj["seq"], bus_id=obj["bus_id"],
        schema_version=obj["schema_version"], kind=obj["kind"],
        sender=obj["from"], recipient=obj["to"], signer=obj["signer"],
        payload=obj["payload"], brief_id=obj.get("brief_id"),
        candidate_id=obj.get("candidate_id"), subject_sha=obj.get("subject_sha"),
        brief_version=obj.get("brief_version"), causation_id=obj.get("causation_id"),
        signature_version=obj.get("signature_version", "threeway-sign/2"),
        supersedes_event_id=obj.get("supersedes_event_id"),
        revokes_event_id=obj.get("revokes_event_id"),
        created_at=obj.get("created_at"), signature=obj.get("signature"),
    )

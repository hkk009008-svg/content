"""Tactical-loop event builders (spec §5.1). build_candidate_events assembles the
six-step loop's facts for ONE pair as UNSIGNED events; the caller signs+appends each
via the store using the matching seat key. Reused by tests and the Slice-1 demo.

A pair is described by a PairConfig (PAIR_A / PAIR_B): which seats build, verify and
coordinate, and each seat's provider. Pair A is the Slice-1 default (Codex director,
Claude operator, Claude coordinator); Pair B mirrors it on the other providers so both
pairs can coexist in one event bus without colliding.

Signer seats follow the spec §4 permission table — the predicate (Task 11) enforces
them: brief/assignment/cycle_go/release_order are overseer-signed, candidate +
release_requested are the pair's COORDINATOR, attestations are the pair's
PRIMARY_VERIFIER, ci_result is ci-signed.

Event ids are scoped by candidate_id (id=f"{kind}-{sender}-{candidate_id}") so two
pairs' overseer-/ci-sent events (same kind+sender) never share an events tree path.
The two attestations share kind+sender (both the pair's primary_verifier), so they
carry the sub-kind in the id (attestation-preliminary-… / attestation-release-…) to
stay distinct — otherwise RefEventStore (events/<brief_id>/<id>.json) would overwrite
the preliminary blob with the release one and lose it.
"""
from __future__ import annotations

from dataclasses import dataclass

from threeway.envelope import Event
from threeway.policy import default_policy

BUS = "prod"


@dataclass(frozen=True)
class PairConfig:
    pair: str
    builder: str
    builder_provider: str
    primary_verifier: str
    verifier_provider: str
    coordinator: str
    coordinator_provider: str


PAIR_A = PairConfig(
    pair="A", builder="director", builder_provider="codex",
    primary_verifier="operator", verifier_provider="claude",
    coordinator="coordinator", coordinator_provider="claude",
)
PAIR_B = PairConfig(
    pair="B", builder="director2", builder_provider="claude",
    primary_verifier="operator2", verifier_provider="codex",
    coordinator="coordinator2", coordinator_provider="codex",
)


def _e(kind, sender, signer, payload, candidate_id, **over):
    base = dict(
        id=over.pop("id", f"{kind}-{sender}-{candidate_id}"), seq=0,
        bus_id=over.pop("bus_id", BUS),
        schema_version="threeway/1", kind=kind, sender=sender, recipient="all",
        signer=signer, payload=payload, brief_id="b1", brief_version=1,
        candidate_id=candidate_id,
    )
    base.update(over)
    return Event(**base)


def build_candidate_events(staging_base, branch_sha, integration_sha, privs,
                           bus_id=BUS, tier="T1", allowed_paths=("cinema/",),
                           pair=PAIR_A, candidate_id="c1"):
    pd = default_policy().policy_digest()
    coord_signer = f"{pair.coordinator}:{pair.coordinator_provider}:s1"
    verifier_signer = f"{pair.primary_verifier}:{pair.verifier_provider}:s1"
    # ADR-042: candidate ids are pair-namespaced ("<pair>:<local>") so a candidate_id binds to
    # exactly ONE pair — the merge-gate's authoritative_candidate enforces declared-pair ==
    # namespace, closing the cross-pair candidate_id reuse DoS. Accept a bare local id and
    # namespace it by this pair, or pass an already-namespaced id through unchanged. The gate must
    # be driven with the FULL namespaced id (this returned value's candidate_id).
    cid = candidate_id if ":" in candidate_id else f"{pair.pair}:{candidate_id}"
    events = [
        _e("brief", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "assigned_tier": tier,
            "allowed_paths": list(allowed_paths)}, cid, brief_id="b1", bus_id=bus_id),
        _e("assignment", "overseer", "overseer:mech:s1",
           {"pair": pair.pair, "builder": pair.builder,
            "builder_provider": pair.builder_provider,
            "primary_verifier": pair.primary_verifier,
            "primary_verifier_provider": pair.verifier_provider,
            "executing_coordinator": pair.coordinator}, cid, bus_id=bus_id),
        _e("candidate", pair.coordinator, coord_signer,
           {"pair": pair.pair, "staging_base_sha": staging_base, "branch_sha": branch_sha,
            "integration_sha": integration_sha, "risk_tier_claimed": tier,
            "policy_digest": pd}, cid, subject_sha=integration_sha, bus_id=bus_id),
        _e("attestation", pair.primary_verifier, verifier_signer,
           {"kind": "preliminary", "verdict": "GO"}, cid,
           id=f"attestation-preliminary-{pair.primary_verifier}-{cid}",
           subject_sha=branch_sha, bus_id=bus_id),
        _e("attestation", pair.primary_verifier, verifier_signer,
           {"kind": "release", "verdict": "GO"}, cid,
           id=f"attestation-release-{pair.primary_verifier}-{cid}",
           subject_sha=integration_sha, bus_id=bus_id),
        _e("cycle_go", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "brief_version": 1, "tier": tier, "policy_digest": pd},
           cid, bus_id=bus_id),
        _e("ci_result", "ci", "ci:mech:s1",
           {"result": "PASS", "policy_digest": pd}, cid,
           subject_sha=integration_sha, bus_id=bus_id),
        _e("release_requested", pair.coordinator, coord_signer,
           {"candidate_id": cid}, cid, subject_sha=integration_sha, bus_id=bus_id),
        _e("release_order", "overseer", "overseer:mech:s1",
           {"candidate_id": cid}, cid, subject_sha=integration_sha, bus_id=bus_id),
    ]
    # Event ids must be unique per call: RefEventStore keys the tree path on
    # events/<brief_id>/<id>.json (NO seq prefix), so a duplicate id silently
    # OVERWRITES a prior event's blob (this is why the two attestations carry their
    # sub-kind in the id). Guard the invariant loudly here rather than lose a fact.
    assert len({e.id for e in events}) == len(events), \
        "build_candidate_events produced duplicate event ids (RefEventStore path collision)"
    return events

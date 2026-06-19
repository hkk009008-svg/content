"""Tactical-loop event builders (spec §5.1). build_candidate_events assembles the
six-step loop's facts for ONE pair (Codex director, Claude operator, Claude
coordinator) as UNSIGNED events; the caller signs+appends each via the store using
the matching seat key. Reused by tests and the Slice-1 demo.

Signer seats follow the spec §4 permission table — the predicate (Task 11) enforces
them: brief/assignment/cycle_go/release_order are overseer-signed, candidate is
coordinator-signed, attestations are operator-signed, ci_result is ci-signed.
"""
from __future__ import annotations

from threeway.envelope import Event
from threeway.policy import default_policy

BUS = "prod"


def _e(kind, sender, signer, payload, **over):
    base = dict(
        id=over.pop("id", f"{kind}-{sender}"), seq=0, bus_id=over.pop("bus_id", BUS),
        schema_version="threeway/1", kind=kind, sender=sender, recipient="all",
        signer=signer, payload=payload, brief_id="b1", brief_version=1,
        candidate_id="c1",
    )
    base.update(over)
    return Event(**base)


def build_candidate_events(staging_base, branch_sha, integration_sha, privs,
                           bus_id=BUS, tier="T1", allowed_paths=("cinema/",)):
    pd = default_policy().policy_digest()
    return [
        _e("brief", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "assigned_tier": tier,
            "allowed_paths": list(allowed_paths)}, brief_id="b1", bus_id=bus_id),
        _e("assignment", "overseer", "overseer:mech:s1",
           {"pair": "A", "builder": "director", "builder_provider": "codex",
            "primary_verifier": "operator", "primary_verifier_provider": "claude",
            "executing_coordinator": "coordinator"}, bus_id=bus_id),
        _e("candidate", "coordinator", "coordinator:claude:s1",
           {"pair": "A", "staging_base_sha": staging_base, "branch_sha": branch_sha,
            "integration_sha": integration_sha, "risk_tier_claimed": tier,
            "policy_digest": pd}, subject_sha=integration_sha, bus_id=bus_id),
        _e("attestation", "operator", "operator:claude:s1",
           {"kind": "preliminary", "verdict": "GO"}, subject_sha=branch_sha, bus_id=bus_id),
        _e("attestation", "operator", "operator:claude:s1",
           {"kind": "release", "verdict": "GO"}, subject_sha=integration_sha, bus_id=bus_id),
        _e("cycle_go", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "brief_version": 1, "tier": tier, "policy_digest": pd}, bus_id=bus_id),
        _e("ci_result", "ci", "ci:mech:s1",
           {"result": "PASS", "policy_digest": pd}, subject_sha=integration_sha, bus_id=bus_id),
        _e("release_requested", "coordinator", "coordinator:claude:s1",
           {"candidate_id": "c1"}, subject_sha=integration_sha, bus_id=bus_id),
        _e("release_order", "overseer", "overseer:mech:s1",
           {"candidate_id": "c1"}, subject_sha=integration_sha, bus_id=bus_id),
    ]

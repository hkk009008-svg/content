"""The mechanical merge-gate (spec §4, §6.3, §6.4).

Read-side (this part): verify EVERY load-bearing event's signature against the
committed public-key registry, reject bus_id mismatches (replay), reject unknown
signer seats, then reduce only verified events. The gate NEVER executes candidate
code; it acts only on signed facts + a signed ci_result.
"""
from __future__ import annotations

import subprocess

from cryptography.exceptions import InvalidSignature

from threeway import LOAD_BEARING_KINDS
from threeway.envelope import verify_event
from threeway.keys import PublicKeyRegistry
from threeway.reducer import reduce


class GateError(Exception):
    pass


# Accepted signature PROFILES (the discriminator is itself signed, so it cannot be
# forged to claim a weaker profile). A load-bearing event presenting an unaccepted
# signature_version is rejected BEFORE signature verification continues.
_ACCEPTED_SIG_VERSIONS = {"threeway-sign/2"}


def _seat(signer: str) -> str:
    return signer.split(":", 1)[0]


def verify_and_reduce(events, registry_dir, bus_id: str):
    reg = PublicKeyRegistry(registry_dir)
    verified = []
    for ev in events:
        if ev.kind in LOAD_BEARING_KINDS:
            if ev.bus_id != bus_id:
                raise GateError(f"bus_id mismatch (replay?): {ev.bus_id!r} != {bus_id!r}")
            if ev.signature_version not in _ACCEPTED_SIG_VERSIONS:
                raise GateError(f"unaccepted signature_version: {ev.signature_version!r}")
            seat = _seat(ev.signer)
            try:
                pub = reg.get(seat)
            except KeyError as e:
                raise GateError(f"unknown signer seat: {seat!r}") from e
            try:
                verify_event(ev, pub)
            except InvalidSignature as e:
                raise GateError(f"invalid signature on {ev.kind} {ev.id}") from e
        verified.append(ev)
    return reduce(verified)


# ---------------------------------------------------------------------------
# Write-side (§6.4): exact-SHA CAS merge + idempotent crash recovery.
#
# run_gate ties the read-side to the merge: verify+reduce -> idempotency no-op if
# already merged -> evaluate the predicate -> on MERGEABLE, RECOMPUTE the trusted
# merge (never trusting candidate.integration_sha), require it equals the attested
# integration_sha, CAS-write the protected test ref (exact-SHA compare-and-swap),
# then emit a signed merge_completed fact. At-most-once is doubly guaranteed: the
# idempotency check short-circuits a re-run, and the CAS expected-old fails anyway
# because the ref already moved off staging_base.
# ---------------------------------------------------------------------------
from dataclasses import dataclass

from threeway import gitcas
from threeway.envelope import Event
from threeway.keys import load_private
from threeway.predicate import evaluate, REJECTED, PENDING
from threeway.policy import default_policy
from threeway.store import EventStore


@dataclass
class GateResult:
    outcome: str   # COMPLETED | REJECTED | PENDING
    reason: str = ""


class _RepoAdapter:
    """Binds threeway.gitcas to one repo path for the predicate's repo interface."""
    def __init__(self, repo):
        self._repo = repo

    def rev_parse(self, ref):
        return gitcas.rev_parse(self._repo, ref)

    def changed_paths(self, base, head):
        return gitcas.changed_paths(self._repo, base, head)


def run_gate(candidate_id, store: EventStore, repo, registry_dir, bus_id,
             main_ref, gate_seat="merge-gate", policy=None) -> GateResult:
    policy = policy or default_policy()
    # 1. verify + reduce authoritative bus state (raises GateError on bad sig/replay)
    state = verify_and_reduce(store.all_events(), registry_dir=registry_dir, bus_id=bus_id)

    # 2. idempotency: already merged?  no-op.
    if state.merge_completed(candidate_id) is not None:
        return GateResult("COMPLETED", "already merged (idempotent)")

    # 3. evaluate the predicate from authoritative state. A residual git-plumbing
    # failure on an attested SHA (e.g. gate-side commit_tree) becomes a REJECTED
    # GateResult, never an escaping CalledProcessError — run_gate is TOTAL.
    try:
        d = evaluate(candidate_id, state, _RepoAdapter(repo), policy, main_ref=main_ref)
        if d.outcome == REJECTED:
            return GateResult("REJECTED", d.reason)
        if d.outcome == PENDING:
            return GateResult("PENDING", d.reason)

        # 4. MERGEABLE — recompute the trusted merge, never trusting candidate.integration_sha
        cand = state.candidate(candidate_id)
        base = cand.payload["staging_base_sha"]
        branch = cand.payload["branch_sha"]
        tree, clean = gitcas.merge_tree(repo, base, branch)
        if not clean:
            return GateResult("REJECTED", "merge not clean (textual conflict) -> ABORT/REWORK")
        merge_commit = gitcas.commit_tree(repo, tree, [base, branch],
                                          f"threeway merge {candidate_id}")
        # the attested integration_sha MUST equal the trusted recomputed merge
        if merge_commit != cand.payload["integration_sha"]:
            return GateResult("REJECTED", "recomputed merge != attested integration_sha")

        # 5. exact-SHA CAS: write main only if it still equals staging_base
        if not gitcas.cas_update_ref(repo, main_ref, merge_commit, base):
            return GateResult("REJECTED", "stale: CAS expected-old no longer matches main.head")

        # 6. emit the signed merge_completed fact (the gate's own credential)
        gate_priv = load_private(gate_seat)
        done = Event(
            id=f"merge-{candidate_id}", seq=0, bus_id=bus_id,
            schema_version="threeway/1", kind="merge_completed",
            sender=gate_seat, recipient="all", signer=f"{gate_seat}:mech:gate",
            payload={"candidate_id": candidate_id, "merged_sha": merge_commit},
            candidate_id=candidate_id, subject_sha=merge_commit,
        )
        store.append(done, gate_priv)
        return GateResult("COMPLETED", "merged via exact-SHA CAS")
    except subprocess.CalledProcessError as e:
        return GateResult("REJECTED", f"git plumbing failed on attested SHA: {e}")

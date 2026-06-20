"""mergeable(candidate) over EFFECTIVE state (spec §6.3).

Three outcomes:
  MERGEABLE  — every clause holds; the gate may write.
  PENDING    — valid so far but an expected approval/CI/release_order is absent.
  REJECTED   — a hard failure (bad sig, wrong signer, tier escalation, stale base,
               out-of-scope diff, policy/CI fail, aborted/superseded).

This module is signature-AGNOSTIC at the field level: it trusts that the gate has
already verified every event's signature against the public-key registry before
reducing (the gate does that in Task 14). Here we enforce the SEMANTIC clauses
(who signed, what tier, scope, freshness). 'repo' is any object exposing
rev_parse(ref) and changed_paths(base, head) — the real one is threeway.gitcas
bound to a repo path; tests pass a fake.
"""
from __future__ import annotations

from dataclasses import dataclass

from threeway.tier import effective_tier, co_sign_satisfied, tier_rank

MERGEABLE = "MERGEABLE"
PENDING = "PENDING"
REJECTED = "REJECTED"

MAIN_REF = "refs/threeway/test-main"   # Slice 1 promotes to a protected TEST ref


@dataclass
class Decision:
    outcome: str
    reason: str = ""


def _seat(signer: str) -> str:
    return signer.split(":", 1)[0]


def evaluate(candidate_id, state, repo, policy, main_ref=MAIN_REF) -> Decision:
    cand = state.candidate(candidate_id)
    if cand is None:
        return Decision(PENDING, "no candidate fact yet")
    if state.is_aborted(candidate_id):
        return Decision(REJECTED, "candidate aborted")

    p = cand.payload
    staging_base = p["staging_base_sha"]
    branch_sha = p["branch_sha"]
    integ = p["integration_sha"]
    pair = p["pair"]

    # freshness — exact-SHA CAS precondition
    if repo.rev_parse(main_ref) != staging_base:
        return Decision(REJECTED, "stale: staging_base_sha != main.head")

    # assignment & independence — assignment is an overseer-signed control-plane fact
    # (without the signer check a builder could forge an assignment that lies about
    #  its own provider, defeating the independence clause below)
    assign = state.assignment(pair)
    if assign is None:
        return Decision(PENDING, "no assignment fact for pair")
    if _seat(assign.signer) != "overseer":
        return Decision(REJECTED, "assignment not signed by overseer")
    a = assign.payload
    builder_provider = a["builder_provider"]
    verifier_provider = a["primary_verifier_provider"]
    if verifier_provider == builder_provider:
        return Decision(REJECTED, "primary verifier same provider as builder")
    # candidate must be signed by the executing coordinator named in assignment
    if _seat(cand.signer) != a["executing_coordinator"]:
        return Decision(REJECTED, "candidate not signed by executing coordinator")

    # brief — overseer-signed; carries assigned_tier + allowed_paths
    brief_ev = state.brief(cand.brief_id, cand.brief_version)
    if brief_ev is None:
        return Decision(PENDING, "no brief fact for brief_id/version")
    if _seat(brief_ev.signer) != "overseer":
        return Decision(REJECTED, "brief not signed by overseer")

    # primary semantic verification — both phases, EFFECTIVE, by the named verifier
    prelim = state.effective_attestation(candidate_id, "preliminary", a["primary_verifier"])
    if prelim is None or prelim.payload.get("verdict") != "GO":
        return Decision(PENDING, "no effective preliminary GO from primary verifier")
    if prelim.subject_sha != branch_sha:
        return Decision(REJECTED, "preliminary attestation not bound to branch_sha")

    rel = state.effective_attestation(candidate_id, "release", a["primary_verifier"])
    if rel is None or rel.payload.get("verdict") != "GO":
        return Decision(PENDING, "no effective release GO from primary verifier")
    if rel.subject_sha != integ:
        return Decision(REJECTED, "release attestation not bound to integration_sha")

    # tier is GATE-COMPUTED, never trusted from the candidate.
    # fail-closed: a well-formed-but-nonexistent attested SHA must REJECT, not
    # crash changed_paths (git exit 128 -> CalledProcessError escapes run_gate).
    if repo.rev_parse(integ) is None:
        return Decision(REJECTED, "integration_sha is not a known commit")
    if repo.rev_parse(staging_base) is None:
        return Decision(REJECTED, "staging_base_sha is not a known commit")
    diff = repo.changed_paths(staging_base, integ)
    brief_tier = brief_ev.payload.get("assigned_tier",
                                      cand.payload.get("risk_tier_claimed", "T0"))
    eff_tier = effective_tier(brief_tier, diff, policy)

    # strategic authorization — overseer-signed cycle_go covering brief+version+tier+policy
    cg = state.cycle_go(cand.brief_id, cand.brief_version)
    if cg is None:
        return Decision(PENDING, "no cycle_go for brief/version")
    if _seat(cg.signer) != "overseer":
        return Decision(REJECTED, "cycle_go not signed by overseer")
    if tier_rank(eff_tier) > tier_rank(cg.payload.get("tier", "T0")):
        return Decision(REJECTED, "tier_escalation: effective tier exceeds cycle_go")
    if cg.payload.get("policy_digest") != cand.payload["policy_digest"]:
        return Decision(REJECTED, "cycle_go policy_digest mismatch")

    # tier-specific extra approvals (Slice 3). All identity inputs are from the
    # overseer-signed assignment (builder_provider/verifier_provider, lines 65-66)
    # and the candidate's integration_sha — never from an unsigned signer string.
    if not co_sign_satisfied(eff_tier, state, candidate_id,
                             candidate_pair=pair,
                             builder_provider=builder_provider,
                             verifier_provider=verifier_provider,
                             integration_sha=integ):
        return Decision(PENDING, f"co_sign not satisfied for {eff_tier}")

    # release key — the OVERSEER's release_order, bound to THIS candidate + sha.
    # The signer check is load-bearing: it is the §11 "valid signature from the
    # wrong seat" defense — any registered seat's signature verifies cryptographically,
    # so authority must be checked by seat, not by signature validity alone.
    ro = state.release_order(candidate_id)
    if ro is None:
        return Decision(PENDING, "no release_order")
    if _seat(ro.signer) != "overseer":
        return Decision(REJECTED, "release_order not signed by overseer (wrong seat)")
    if ro.subject_sha != integ:
        return Decision(REJECTED, "release_order not bound to integration_sha")

    # scope, policy, evidence, version
    allowed = brief_ev.payload.get("allowed_paths", [])
    if not _within_allowed(diff, allowed):
        return Decision(REJECTED, "diff outside allowed_paths")
    if not policy.is_accepted(cand.payload["policy_digest"]):
        return Decision(REJECTED, "candidate policy_digest not accepted")

    # CI evidence — signed by the trusted CI seat, binding integration_sha + policy
    ci = state.ci_result(integ)
    if ci is None:
        return Decision(PENDING, "no ci_result for integration_sha")
    if _seat(ci.signer) != "ci":
        return Decision(REJECTED, "ci_result not signed by trusted CI (wrong seat)")
    if ci.payload.get("result") != "PASS":
        return Decision(REJECTED, "ci_result not PASS")
    if ci.payload.get("policy_digest") != cand.payload["policy_digest"]:
        return Decision(REJECTED, "ci_result policy_digest mismatch")

    latest_v = state.latest_brief_version(cand.brief_id)
    if latest_v is not None and cand.brief_version != latest_v:
        return Decision(REJECTED, "candidate brief_version is superseded")

    return Decision(MERGEABLE, "all clauses hold")


def _within_allowed(diff, allowed) -> bool:
    if not allowed:
        return False
    for path in diff:
        if not any(_under(path, a) for a in allowed):
            return False
    return True


def _under(path: str, allowed: str) -> bool:
    # path-segment boundary: "cinema" matches "cinema/..." but NOT "cinemax/...";
    # an exact-file allow (e.g. "requirements.txt") still matches via ==.
    # NB: the identical shape in tier._path_tier is INTENTIONALLY left generous —
    # over-matching there only RAISES the tier (fail-safe). Do not "consistency-fix" it.
    if path == allowed:
        return True
    prefix = allowed if allowed.endswith("/") else allowed + "/"
    return path.startswith(prefix)

from __future__ import annotations

from dataclasses import dataclass


def signer_seat(signer: str) -> str:
    return signer.split(":", 1)[0]


@dataclass(frozen=True)
class CandidateContext:
    candidate_id: str
    integration_sha: str
    pair: str
    primary_verifier: str
    primary_verifier_provider: str
    builder_provider: str
    brief_id: str | None
    brief_version: int | None


def resolve_candidate_context(state, candidate_id: str) -> CandidateContext:
    candidate = state.authoritative_candidate(candidate_id)
    if candidate is None:
        raise ValueError(f"no authoritative candidate for {candidate_id}")
    pair = candidate.payload.get("pair")
    if not isinstance(pair, str):
        raise ValueError(f"candidate {candidate_id} has no string pair")
    assignment = state.assignment(pair)
    if assignment is None:
        raise ValueError(f"no assignment for pair {pair}")
    integration_sha = candidate.payload.get("integration_sha")
    if not isinstance(integration_sha, str) or not integration_sha:
        raise ValueError(f"candidate {candidate_id} has no integration_sha")
    primary_verifier = assignment.payload.get("primary_verifier")
    primary_provider = assignment.payload.get("primary_verifier_provider")
    builder_provider = assignment.payload.get("builder_provider")
    if not all(isinstance(x, str) and x for x in (primary_verifier, primary_provider, builder_provider)):
        raise ValueError(f"assignment for pair {pair} is missing verifier/provider fields")
    return CandidateContext(
        candidate_id=candidate_id,
        integration_sha=integration_sha,
        pair=pair,
        primary_verifier=primary_verifier,
        primary_verifier_provider=primary_provider,
        builder_provider=builder_provider,
        brief_id=candidate.brief_id,
        brief_version=candidate.brief_version,
    )


def required_mirror_cosigner(state, ctx: CandidateContext) -> str | None:
    seats = []
    for assignment in state.assignments():
        if signer_seat(assignment.signer) != "overseer":
            continue
        payload = assignment.payload
        if payload.get("pair") == ctx.pair:
            continue
        if (payload.get("builder_provider") == ctx.primary_verifier_provider
                and payload.get("primary_verifier_provider") == ctx.builder_provider):
            seats.append(payload.get("primary_verifier"))
    if len(seats) != 1:
        return None
    return seats[0] if isinstance(seats[0], str) and seats[0] else None


def required_re_verifier(state, ctx: CandidateContext) -> str:
    return ctx.primary_verifier


def current_reverify_challenge_nonce(state, ctx: CandidateContext) -> str | None:
    challenge = state.re_verify_challenge(ctx.candidate_id)
    if challenge is None or challenge.subject_sha != ctx.integration_sha:
        return None
    nonce = challenge.payload.get("nonce")
    return nonce if isinstance(nonce, str) and nonce else None


def event_by_id(events, event_id: str):
    matches = [ev for ev in events if ev.id == event_id]
    if len(matches) != 1:
        return None
    return matches[0]


def rostered_approvers(state, candidate_id: str) -> set[str]:
    roster = state.approver_roster(candidate_id)
    if roster is None:
        return set()
    approvers = roster.payload.get("approvers")
    if not isinstance(approvers, list):
        return set()
    return {seat for seat in approvers if isinstance(seat, str)}

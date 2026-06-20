"""Replay append-only facts (in seq order) into EffectiveState (spec §6.1).

The predicate only ever reads EffectiveState, never raw events. An attestation is
EFFECTIVE iff it is the latest (by seq) verdict for its (candidate_id, att_kind,
signer-seat) AND not revoked. signer-seat = the seat portion of signer
("operator:claude:s1" -> "operator"), so a fresh re-verify SESSION by the same
seat still supersedes the prior one (latest seq wins), which is the intended
"latest verdict" semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from threeway.envelope import Event


def _seat_of(signer: str) -> str:
    return signer.split(":", 1)[0]


@dataclass
class EffectiveState:
    # (candidate_id, att_kind, seat) -> latest attestation Event
    _attestations: dict[tuple, Event] = field(default_factory=dict)
    _revoked_event_ids: set[str] = field(default_factory=set)
    _aborted_candidates: set[str] = field(default_factory=set)
    _superseded_event_ids: set[str] = field(default_factory=set)
    _briefs: dict[tuple, Event] = field(default_factory=dict)        # (brief_id, version) -> Event
    _cycle_go: dict[tuple, Event] = field(default_factory=dict)      # (brief_id, version) -> Event
    _release_order: dict[str, Event] = field(default_factory=dict)   # candidate_id -> Event
    _release_requested: dict[str, Event] = field(default_factory=dict)
    _ci_result: dict[str, Event] = field(default_factory=dict)       # subject_sha -> Event
    _candidates: dict[str, Event] = field(default_factory=dict)      # candidate_id -> Event
    _assignments: dict[str, Event] = field(default_factory=dict)     # pair -> Event
    _merge_completed: dict[str, Event] = field(default_factory=dict) # candidate_id -> Event
    _co_sign: dict[tuple, Event] = field(default_factory=dict)       # (candidate_id, seat) -> Event
    _re_verify: dict[tuple, Event] = field(default_factory=dict)
    _human_approval: dict[tuple, Event] = field(default_factory=dict)  # (candidate_id, approver) -> Event

    # ---- effective queries used by the predicate ----
    def effective_attestation(self, candidate_id, att_kind, seat) -> Event | None:
        ev = self._attestations.get((candidate_id, att_kind, seat))
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def is_aborted(self, candidate_id) -> bool:
        return candidate_id in self._aborted_candidates

    def brief(self, brief_id, version) -> Event | None:
        return self._briefs.get((brief_id, version))

    def latest_brief_version(self, brief_id) -> int | None:
        # a version is live iff its brief event id is not in the superseded set —
        # otherwise a brief_superseded of the LATEST version would be ignored and the
        # predicate's "candidate.brief_version == latest_non_superseded" clause (§6.3)
        # would silently pass on a superseded brief.
        versions = [v for (bid, v), ev in self._briefs.items()
                    if bid == brief_id and ev.id not in self._superseded_event_ids]
        return max(versions) if versions else None

    def cycle_go(self, brief_id, version) -> Event | None:
        return self._cycle_go.get((brief_id, version))

    def release_order(self, candidate_id) -> Event | None:
        return self._release_order.get(candidate_id)

    def release_requested(self, candidate_id) -> Event | None:
        return self._release_requested.get(candidate_id)

    def ci_result(self, subject_sha) -> Event | None:
        return self._ci_result.get(subject_sha)

    def candidate(self, candidate_id) -> Event | None:
        return self._candidates.get(candidate_id)

    def assignment(self, pair) -> Event | None:
        ev = self._assignments.get(pair)
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def merge_completed(self, candidate_id) -> Event | None:
        return self._merge_completed.get(candidate_id)

    def co_sign(self, candidate_id, seat) -> Event | None:
        ev = self._co_sign.get((candidate_id, seat))
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def re_verify(self, candidate_id, seat) -> Event | None:
        ev = self._re_verify.get((candidate_id, seat))
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def human_approvals(self, candidate_id) -> list[Event]:
        return [e for (cid, _), e in self._human_approval.items()
                if cid == candidate_id and e.id not in self._revoked_event_ids]

    def assignments(self) -> list[Event]:
        return [e for e in self._assignments.values()
                if e.id not in self._revoked_event_ids]


def reduce(events) -> EffectiveState:
    st = EffectiveState()
    for ev in sorted(events, key=lambda e: e.seq):
        k = ev.kind
        if k == "attestation":
            seat = _seat_of(ev.signer)
            att_kind = ev.payload.get("kind", "release")
            st._attestations[(ev.candidate_id, att_kind, seat)] = ev
        elif k == "attestation_revoked":
            if ev.revokes_event_id:
                st._revoked_event_ids.add(ev.revokes_event_id)
        elif k == "candidate_aborted":
            st._aborted_candidates.add(ev.candidate_id)
        elif k == "brief":
            st._briefs[(ev.brief_id, ev.brief_version)] = ev
        elif k == "brief_superseded":
            if ev.supersedes_event_id:
                st._superseded_event_ids.add(ev.supersedes_event_id)
        elif k == "cycle_go":
            st._cycle_go[(ev.payload.get("brief_id", ev.brief_id),
                          ev.payload.get("brief_version", ev.brief_version))] = ev
        elif k == "release_order":
            st._release_order[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "release_requested":
            st._release_requested[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "ci_result":
            st._ci_result[ev.subject_sha] = ev
        elif k == "candidate":
            st._candidates[ev.candidate_id] = ev
        elif k == "assignment":
            st._assignments[ev.payload.get("pair")] = ev
        elif k == "merge_completed":
            st._merge_completed[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "co_sign":
            st._co_sign[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "re_verify":
            st._re_verify[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "human_approval":
            st._human_approval[(ev.candidate_id, ev.payload.get("approver_identity"))] = ev
    return st

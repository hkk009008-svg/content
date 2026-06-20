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

from threeway import LOAD_BEARING_KINDS
from threeway.envelope import Event


# The merge-gate seat name. The six static control-plane singletons resolve to the
# latest event FROM THEIR AUTHORIZED SEAT (record-time authority filter, ADR-039), so
# reduce() needs to know which seat is the gate. Default keeps every existing
# reduce(events) call site working; callers may override via the keyword.
GATE_SEAT = "merge-gate"


def _seat_of(signer: str) -> str:
    return signer.split(":", 1)[0]


def _revoke_authorized(revoker_seat: str, target_seats) -> bool:
    """ADR-036: `revokes_event_id` is UNSIGNED (envelope.py:67), so an attacker who holds
    ANY registered seat could forge a revoke pointing at another seat's (or the overseer's)
    fact without breaking its signature. A revoke therefore takes effect ONLY from an
    authorized seat — the `overseer` (control-plane override) or the target event's own
    signer seat (self-revocation). Any other seat's revoke is IGNORED. Without this an
    insider could collapse the gate's fail-closed guarantees (forged promotion / merge DoS).

    `target_seats` is the SET of signer seats that emitted an event carrying the revoked id.
    Event `id` is signed but NOT globally unique, so an insider can re-use a victim's id with
    its OWN seat to poison the index; a CONTESTED id (>1 seat) is therefore NOT self-revocable
    — only the overseer may revoke it. None (target absent from the replay) → overseer-only."""
    return revoker_seat == "overseer" or target_seats == {revoker_seat}


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
    _candidates: dict[tuple, Event] = field(default_factory=dict)    # (candidate_id, seat) -> Event
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

    def candidate(self, candidate_id, seat=None) -> Event | None:
        # ADR-039: _candidates is keyed by (candidate_id, signer-seat) so an insider's
        # validly-signed shadow candidate (same id, different seat) no longer overwrites the
        # authoritative one in a plain last-write-wins slot. With `seat` given, return that
        # seat's candidate; with seat=None this is a LOCATE-ONLY query (latest-by-seq across
        # all seats) used by the predicate solely to detect "no candidate fact at all" —
        # authority is decided by authoritative_candidate(), never by this latest-seat read.
        if seat is not None:
            return self._candidates.get((candidate_id, seat))
        cands = [e for (cid, _seat), e in self._candidates.items() if cid == candidate_id]
        if not cands:
            return None
        return max(cands, key=lambda e: e.seq)

    def authoritative_candidate(self, candidate_id) -> Event | None:
        # ADR-039: the effective candidate is the one self-consistent with the overseer's
        # assignment — signed by the executing_coordinator the overseer assigned to the pair
        # THAT candidate declares. A shadow candidate (bogus pair, or a pair whose coordinator
        # != its signer) is NOT self-consistent and is ignored — closing the candidate
        # shadow-DoS AND the pair-redirection variant. assignment() is already overseer-only
        # (record-time filter), so a forged assignment can't make a shadow self-consistent.
        cands = [e for (cid, _seat), e in self._candidates.items() if cid == candidate_id]
        for c in sorted(cands, key=lambda e: e.seq, reverse=True):
            a = self.assignment(c.payload.get("pair"))
            if a is not None and a.payload.get("executing_coordinator") == _seat_of(c.signer):
                return c
        return None

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


def reduce(events, *, gate_seat: str = GATE_SEAT) -> EffectiveState:
    st = EffectiveState()
    ordered = sorted(events, key=lambda e: e.seq)
    # ADR-039 (defect threeway-reducer-shadow-dos, availability): the six STATIC
    # control-plane singletons below are last-write-wins, and the stores auto-assign a
    # monotonic seq — so an insider's event appended AFTER the authoritative one would
    # otherwise win the map slot and SHADOW the legitimate fact, blocking a legit
    # promotion (a DoS). The predicate checks authority on READ, but by then the shadow
    # has already displaced the fact. So we filter at RECORD time: each singleton's
    # effective value is the latest event from its AUTHORIZED seat, never merely the
    # latest seat. Unauthorized events of these kinds are DROPPED for effective state
    # (they may still exist on the bus). Fail-safe: this only ever DROPS a
    # non-authoritative event — it never widens what can promote. The forgery class
    # (ADR-036/037/038) is unaffected (those branches are untouched).
    _AUTHORIZED_SINGLETON_SEAT = {
        "assignment": "overseer",
        "brief": "overseer",
        "cycle_go": "overseer",
        "release_order": "overseer",
        "ci_result": "ci",
        "merge_completed": gate_seat,
    }
    # Revoke authority needs the TARGET event's seat. Map each id to the SET of seats that
    # emitted an event with it (ids are signed but not unique) so a collision is detectable,
    # and so the check holds regardless of whether the revoke precedes or follows its target.
    # Built from LOAD-BEARING events ONLY: a revoke target is always a load-bearing fact, so a
    # non-load-bearing carrier (which the gate does not de-dup) must not be able to CONTEST a
    # victim's id and block its legitimate self-revocation (ADR-037).
    seat_by_id: dict[str, set[str]] = {}
    for ev in ordered:
        if ev.kind in LOAD_BEARING_KINDS:
            seat_by_id.setdefault(ev.id, set()).add(_seat_of(ev.signer))
    for ev in ordered:
        k = ev.kind
        if k == "attestation":
            seat = _seat_of(ev.signer)
            att_kind = ev.payload.get("kind", "release")
            st._attestations[(ev.candidate_id, att_kind, seat)] = ev
        elif k == "attestation_revoked":
            tgt = ev.revokes_event_id
            if tgt and _revoke_authorized(_seat_of(ev.signer), seat_by_id.get(tgt)):
                st._revoked_event_ids.add(tgt)
        elif k == "candidate_aborted":
            st._aborted_candidates.add(ev.candidate_id)
        elif k == "brief":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["brief"]:
                continue
            st._briefs[(ev.brief_id, ev.brief_version)] = ev
        elif k == "brief_superseded":
            # supersedes_event_id is the UNSIGNED sibling of revokes_event_id (envelope.py:67),
            # so gate it by the SAME authority rule (ADR-037, Rule #13): only the overseer or
            # the superseded brief's own signer seat may roll back a brief version.
            tgt = ev.supersedes_event_id
            if tgt and _revoke_authorized(_seat_of(ev.signer), seat_by_id.get(tgt)):
                st._superseded_event_ids.add(tgt)
        elif k == "cycle_go":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["cycle_go"]:
                continue
            st._cycle_go[(ev.payload.get("brief_id", ev.brief_id),
                          ev.payload.get("brief_version", ev.brief_version))] = ev
        elif k == "release_order":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["release_order"]:
                continue
            st._release_order[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "release_requested":
            st._release_requested[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "ci_result":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["ci_result"]:
                continue
            st._ci_result[ev.subject_sha] = ev
        elif k == "candidate":
            st._candidates[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "assignment":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["assignment"]:
                continue
            st._assignments[ev.payload.get("pair")] = ev
        elif k == "merge_completed":
            if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["merge_completed"]:
                continue
            st._merge_completed[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "co_sign":
            st._co_sign[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "re_verify":
            st._re_verify[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "human_approval":
            st._human_approval[(ev.candidate_id, ev.payload.get("approver_identity"))] = ev
    return st

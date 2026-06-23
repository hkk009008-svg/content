"""Replay append-only facts (in seq order) into EffectiveState (spec §6.1).

The predicate only ever reads EffectiveState, never raw events. An attestation is
EFFECTIVE iff it is the latest (by seq) verdict for its (candidate_id, att_kind,
signer-seat) AND not revoked. signer-seat = the seat portion of signer
("operator:claude:s1" -> "operator"), so a fresh re-verify SESSION by the same
seat still supersedes the prior one (latest seq wins), which is the intended
"latest verdict" semantics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from threeway import LOAD_BEARING_KINDS
from threeway.envelope import Event, well_formed

logger = logging.getLogger(__name__)


# The merge-gate seat name. The six static control-plane singletons resolve to the
# latest event FROM THEIR AUTHORIZED SEAT (record-time authority filter, ADR-039), so
# reduce() needs to know which seat is the gate. Default keeps every existing
# reduce(events) call site working; callers may override via the keyword.
GATE_SEAT = "merge-gate"


def _seat_of(signer: str) -> str:
    return signer.split(":", 1)[0]


def _pair_namespace(candidate_id) -> str | None:
    """ADR-042: the pair a candidate_id is structurally BOUND to. Candidate ids are
    pair-namespaced ``"<pair>:<local>"`` (e.g. ``"A:c1"``); the bound pair is the prefix
    before the first ``":"``. Returns None for a non-str or un-namespaced id — such an id
    binds to NO pair and can never be authoritative (fail-safe). This binding is what makes
    `authoritative_candidate` order-independent: a candidate_id can only be claimed by the
    pair named in its own namespace, so a coordinator of a DIFFERENT pair can never capture
    it by reusing the id (regardless of declare order)."""
    if isinstance(candidate_id, str) and ":" in candidate_id:
        return candidate_id.split(":", 1)[0]
    return None


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
    # ADR-059: candidate_id -> the SET of signer-seats that emitted a candidate_aborted for
    # it. Authority is resolved on READ (is_aborted), like authoritative_candidate — the fold
    # cannot resolve cross-event authority at record time because the authorizing seat depends
    # on the pair's assignment, which may arrive in any order.
    _aborted_by: dict[str, set[str]] = field(default_factory=dict)
    _superseded_event_ids: set[str] = field(default_factory=set)
    _briefs: dict[tuple, Event] = field(default_factory=dict)        # (brief_id, version) -> Event
    _cycle_go: dict[tuple, Event] = field(default_factory=dict)      # (brief_id, version) -> Event
    _release_order: dict[str, Event] = field(default_factory=dict)   # candidate_id -> Event
    _release_requested: dict[str, Event] = field(default_factory=dict)
    _ci_result: dict[str, Event] = field(default_factory=dict)       # subject_sha -> Event
    _candidates: dict[tuple, Event] = field(default_factory=dict)    # (candidate_id, seat) -> latest Event
    _assignments: dict[str, Event] = field(default_factory=dict)     # pair -> Event
    _merge_completed: dict[str, Event] = field(default_factory=dict) # candidate_id -> Event
    _co_sign: dict[tuple, Event] = field(default_factory=dict)       # (candidate_id, seat) -> Event
    _re_verify: dict[tuple, Event] = field(default_factory=dict)
    # ADR-043: human_approval is keyed by (candidate_id, signer-SEAT) — the KEY-BOUND
    # identity — NOT the attacker-influenceable payload approver_identity LABEL, so two
    # approvals from one approver collapse to one and distinctness is genuinely per-keyholder.
    _human_approval: dict[tuple, Event] = field(default_factory=dict)  # (candidate_id, seat) -> Event
    _re_verify_challenge: dict[str, Event] = field(default_factory=dict)  # candidate_id -> Event (overseer nonce)
    _approver_roster: dict[str, Event] = field(default_factory=dict)      # candidate_id -> Event (overseer roster)

    # ---- effective queries used by the predicate ----
    def effective_attestation(self, candidate_id, att_kind, seat) -> Event | None:
        ev = self._attestations.get((candidate_id, att_kind, seat))
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def is_aborted(self, candidate_id) -> bool:
        # ADR-059 (defect threeway-candidate-aborted-no-authority, forge / cross-pair abort
        # DoS): candidate_aborted was the LONE load-bearing singleton with no authority filter
        # — any keyholder could append a validly-signed abort for ANY candidate_id and the
        # predicate would permanently REJECT it (same forge/availability class as ADR-036/037/038).
        # Abort authority = the candidate's bound-pair executing_coordinator (user-decided
        # 2026-06-23), resolved here at READ exactly like authoritative_candidate: the bound pair
        # is the candidate_id's namespace; its coordinator is the overseer-assigned
        # executing_coordinator. An abort is effective iff that coordinator is among the seats
        # that aborted. Fail-safe — no abort fact / no namespace / no assignment / non-str
        # coordinator -> False: this only ever DROPS unauthorized aborts, never widens what can
        # abort. assignment() is overseer-only at record time, so a forged assignment can't
        # redirect abort authority. isinstance guard keeps a malformed (non-str) coordinator from
        # raising at read time (ADR-041 read-path totality).
        seats = self._aborted_by.get(candidate_id)
        if not seats:
            return False
        ns = _pair_namespace(candidate_id)
        if ns is None:
            return False
        a = self.assignment(ns)
        if a is None:
            return False
        coordinator = a.payload.get("executing_coordinator")
        return isinstance(coordinator, str) and coordinator in seats

    def aborted_candidate_ids(self) -> list:
        # ADR-060: candidate_ids with >=1 recorded abort (authorized OR not). The rework breaker
        # iterates these and re-checks authority via is_aborted — so this accessor never widens
        # authority; it only exposes which ids to consider.
        return list(self._aborted_by.keys())

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
        #
        # ADR-042 (threeway-candidate-id-pair-binding-dos): self-consistency ALONE is not a
        # UNIQUE binding — TWO different overseer-assigned pairs (A and B) could each be
        # self-consistent for the SAME candidate_id, so a LEGITIMATE executing_coordinator of
        # pair B could reuse a victim's candidate_id (declaring pair B) and capture authority,
        # stalling the victim's pair-A merge (availability-only — it can never forge pair A's
        # attestations, so it never promotes). An order-based tiebreak (latest-seq, or
        # first-writer-wins) only MOVES the race (declare-later vs declare-earlier), never closes
        # it. So bind STRUCTURALLY: candidate ids are pair-namespaced ("<pair>:<local>") and a
        # candidate is eligible only if its DECLARED pair == the candidate_id's namespace. That
        # binds a candidate_id to exactly ONE pair independent of declare order — a coordinator of
        # any OTHER pair declares a non-matching pair and is ineligible, so it can NEVER capture a
        # victim's id. Within the bound pair, only that pair's assigned executing_coordinator is
        # self-consistent (one seat), so at most one candidate is eligible; the (seq, seat) tiebreak
        # is defensive determinism for the implausible multi-eligible case. Closes the DoS in BOTH
        # directions; supersedes the order-dependent first-writer-wins attempt.
        ns = _pair_namespace(candidate_id)
        if ns is None:
            return None   # un-namespaced id binds to no pair — no candidate can be authoritative
        best = None
        for (cid, seat), c in self._candidates.items():
            if cid != candidate_id:
                continue
            # ADR-041 (read-path totality): a validly-self-signed candidate PASSES reduce() even
            # with an unhashable payload["pair"] (the fold keys on (candidate_id, seat), not pair).
            # self.assignment(pair) would then raise TypeError on a list/dict pair UNCAUGHT — this
            # call is on run_gate's step-2a, OUTSIDE its try, so it bricks the whole bus. SKIP a
            # candidate whose pair is not a str: a non-str pair can never match the namespace nor be
            # self-consistent, so skipping is fail-safe and lets the loop reach the legit candidate.
            pair = c.payload.get("pair")
            if not isinstance(pair, str):
                continue
            if pair != ns:
                continue   # ADR-042: declared pair must match the id's pair-namespace
            a = self.assignment(pair)
            if a is None or a.payload.get("executing_coordinator") != _seat_of(c.signer):
                continue
            if best is None or (c.seq, seat) < (best.seq, _seat_of(best.signer)):
                best = c
        return best

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

    def re_verify_challenge(self, candidate_id) -> Event | None:
        # ADR-043: the overseer's freshness nonce for this candidate's T3 re_verify. Resolved
        # overseer-only at record time (like assignment/cycle_go), revoke-aware on read.
        ev = self._re_verify_challenge.get(candidate_id)
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def approver_roster(self, candidate_id) -> Event | None:
        # ADR-043: the overseer-designated set of allowed human-approver SEATS for this
        # candidate. Overseer-only at record time, revoke-aware on read.
        ev = self._approver_roster.get(candidate_id)
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def assignments(self) -> list[Event]:
        return [e for e in self._assignments.values()
                if e.id not in self._revoked_event_ids]


def reduce(events, *, gate_seat: str = GATE_SEAT) -> EffectiveState:
    st = EffectiveState()
    # ADR-041 (defect threeway-reducer-unhashable-key-brick, availability): an insider seat
    # validly self-signs a load-bearing event whose KEYED field is an unhashable JSON list
    # (e.g. candidate_id=["x","y"], payload["kind"]/["approver_identity"] a list) or whose
    # infrastructure field (id/signer/seq) is the wrong type. Those fields are inside the
    # signed envelope/payload-digest, so the signature is VALID — no forgery. Pre-ADR-041 the
    # dict-key / set-member / sort raised TypeError/AttributeError that escaped run_gate's
    # step-1 verify_and_reduce (OUTSIDE its try) -> a total-bus brick (ONE event bricked every
    # candidate). Apply the SAME drop-not-raise discipline ADR-040 used: a malformed event has
    # NO authority, so DROP it (with a WARNING) — never let it brick the whole reduction.
    #
    # Up-front COMPREHENSIVE envelope filter (BEFORE the sort), consolidating the prior narrow
    # id/signer/seq drop: well_formed(ev) checks EVERY structurally-dereferenced envelope field's
    # type. kind keys the `kind in LOAD_BEARING_KINDS` test in the seat_by_id loop and the fold
    # (TypeError if unhashable); id keys seat_by_id AND the later EffectiveState id-membership
    # queries (`e.id in self._revoked_event_ids`); signer feeds _seat_of(...).split(":")
    # (AttributeError if non-str); seq is the sort key (TypeError if non-comparable); payload must
    # be a dict for the .get(...) folds. After this filter the sort, the seat_by_id loop (incl. its
    # own `kind in LOAD_BEARING_KINDS`), and the envelope-keyed fold branches are all type-safe.
    # The fold try/except below still covers PAYLOAD-VALUE keys (payload["kind"]/["approver_identity"]).
    # bool subclasses int, harmless for seq. Fail-safe: dropping a malformed event can only REMOVE it
    # from reduction — it has no authority, so this never widens what can promote.
    ordered = []
    for ev in events:
        if not well_formed(ev):
            logger.warning("dropping malformed-envelope event (id=%r kind=%r signer=%r)",
                           getattr(ev, "id", None), getattr(ev, "kind", None), getattr(ev, "signer", None))
            continue
        ordered.append(ev)
    ordered = sorted(ordered, key=lambda e: e.seq)
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
        # ADR-043: the freshness challenge + approver roster are overseer authority facts —
        # a forged non-overseer challenge (planting a known nonce) or roster (adding the
        # attacker's own seat) must be DROPPED at record time, never shadow the overseer's.
        "re_verify_challenge": "overseer",
        "approver_roster": "overseer",
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
        # ADR-041: wrap the fold body so a malformed-but-validly-signed event (an unhashable
        # JSON-list dict-key / set-member, e.g. candidate_id=["x"], payload["kind"] a list, or
        # any odd KEYED field in ANY branch — present OR added later) is DROPPED with a WARNING
        # instead of raising and bricking the whole reduction. The tuple/dict key is computed
        # BEFORE the map assignment, so a TypeError there means the event never partially enters
        # the map — the drop is clean. The up-front id/signer/seq filter already made seat_by_id
        # and the later id-membership queries safe; this is the future-proof catch-all for the
        # remaining payload-/reference-derived keys. (Authority/fold semantics are UNCHANGED —
        # this only ADDs the drop; a well-formed legit event is never caught.)
        try:
            if k == "attestation":
                seat = _seat_of(ev.signer)
                att_kind = ev.payload.get("kind", "release")
                st._attestations[(ev.candidate_id, att_kind, seat)] = ev
            elif k == "attestation_revoked":
                tgt = ev.revokes_event_id
                if tgt and _revoke_authorized(_seat_of(ev.signer), seat_by_id.get(tgt)):
                    st._revoked_event_ids.add(tgt)
            elif k == "candidate_aborted":
                # ADR-059: record ALL aborts with their signer-seat; authority is resolved on
                # READ in is_aborted (the per-pair coordinator can't be checked at record time —
                # the authorizing assignment may not have arrived yet). This is the same
                # record-all / resolve-at-read shape as `candidate` (ADR-039/042). The unhashable
                # candidate_id case is covered by the surrounding try/except (drop + WARNING).
                st._aborted_by.setdefault(ev.candidate_id, set()).add(_seat_of(ev.signer))
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
                # keyed by (candidate_id, signer-seat) so a validly-signed shadow candidate (same
                # id, different seat) does not overwrite the authoritative one (ADR-039). ADR-042
                # binds the candidate_id to ONE pair structurally via authoritative_candidate's
                # namespace check, so no seq/first-writer tiebreak state is needed here.
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
            elif k == "re_verify_challenge":
                # ADR-043: overseer-only freshness nonce, keyed by candidate_id (latest
                # overseer challenge wins). A non-overseer challenge has no authority — drop it.
                if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["re_verify_challenge"]:
                    continue
                st._re_verify_challenge[ev.candidate_id] = ev
            elif k == "human_approval":
                # ADR-043: key by signer SEAT (key-bound), not the payload approver_identity
                # LABEL — two approvals from one keyholder collapse, so T3 distinctness is per-key.
                st._human_approval[(ev.candidate_id, _seat_of(ev.signer))] = ev
            elif k == "approver_roster":
                # ADR-043: overseer-only allowed-approver roster, keyed by candidate_id.
                if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT["approver_roster"]:
                    continue
                st._approver_roster[ev.candidate_id] = ev
        except (TypeError, AttributeError, ValueError) as e:
            logger.warning("dropping malformed event %s (kind=%r) from reduction: %s",
                           ev.id, k, e)
            continue
    return st

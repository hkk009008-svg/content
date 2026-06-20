# Cross-Provider Seat Topology — Slice 3 (merge-gate tier co-sign) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Per the user's standing directive, every Agent/subagent dispatch runs `model: 'opus'`.

**Goal:** Make `threeway.tier.co_sign_satisfied` actually enforce the T2 and T3 promotion paths so escalated changes can promote when — and only when — the spec §7.2 cross-family approvals exist; today it hard-returns `False` for T2/T3 (the Slice-1 fail-safe stub).

**Architecture:** Pure-predicate machinery, with all identity grounded on **signed facts** — never on the unsigned `signer` string. T2 requires a `co_sign` GO bound to `integration_sha` from the **mirror pair's operator**, resolved from the overseer-signed `assignment` facts (the genuine D3 provider-role-swap pair, fail-closed under ambiguity) and matched by **key-bound seat token**. T3 adds a cross-provider operator `re_verify` GO plus **two distinct, SHA-bound, affirmative, overseer-relayed `human_approval`** facts. All effective accessors (co_sign/re_verify/human_approvals/assignments) are revocation-aware. This is scope **(a)** of spec §11's Slice 3; the strategic loop **(b)** (dual chief apps, overseer brief distribution, live fact *emission*, a cryptographically-fresh re_verify challenge, and per-approver human auth) is a deliberately deferred future slice.

**Tech Stack:** Python 3, pytest. Signed event-sourced bus (`threeway/`), Ed25519 + RFC 8785 JCS. Run threeway tests with the mandatory `env -u GIT_INDEX_FILE` prefix.

**Spec:** `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md` §7.2 (risk tiers + co-sign matrix), §6.1 (effective-state / revocation), §6.2 (signed envelope — the 14-field signed view EXCLUDES `signer`, envelope.py:67-90), §6.3 (merge predicate), §12 (human-approval schema), D2/D3 (mirrored pairs = provider-role swap), §9 gate.

**§11 boundary (prerequisite — SATISFIED):** Slice 2.5's §8 gate is green and merged (`origin/main e777434a`). This plan covers ONLY scope (a) and is mutation-gated like every prior slice.

---

## SECURITY ROOT CAUSE (drives the whole design)

The `signer` string `"seat:provider:session"` is **NOT cryptographically signed** — `_signed_view` (envelope.py:73-90) binds 14 fields and `signer` is explicitly excluded (envelope.py:67-72). The gate selects the verifying key by **seat token only** (`_seat(ev.signer)` → `reg.get(seat)`, gate.py:43-49). Therefore:

- The **seat token** IS trustworthy: altering it makes the gate look up the wrong key and verification fails. `_seat(ev.signer)` (and the reducer's `(candidate_id, _seat_of(signer))` keying) is sound identity.
- The **`provider`** and **`session`** substrings are attacker-chosen free text. A registered seat signs as itself but can put ANY provider/session in its signer string. Reading them is a forged-promotion bypass.
- The only **signed** seat→provider mapping is the overseer-signed `assignment` fact (its `payload_digest` IS in the signed view). All provider reasoning comes from there.

**Rule for this slice: derive identity from (key-bound seat token) + (overseer-signed `assignment`). Never parse provider/session out of a signer string. Resolve ambiguity by failing CLOSED.**

## Design decisions (ratified this session, recorded as ADR-035)

1. **T2 co-signer = the MIRROR pair's operator, resolved from signed `assignment` facts, fail-closed.** For a candidate in pair P with builder provider `B` and verifier provider `V` (the candidate-pair assignment's `primary_verifier_provider`): among overseer-signed assignments with `pair != P`, the MIRROR is the one whose providers are the D3 role-swap — `builder_provider == V` **and** `primary_verifier_provider == B`. If **exactly one** such pair exists, require `state.co_sign(candidate_id, that_pair.primary_verifier)` (key-bound lookup) to be a GO bound to `integration_sha`. If **zero or more than one** mirror exists → return False (ambiguous co-signer → PENDING). The co_sign's own signer-string provider/session are never read.
2. **All co_sign/re_verify/human_approval must bind `subject_sha`/`integration_sha == integration_sha`** (D8 — the exact merged SHA).
3. **T3 re_verify is from the candidate pair's own `primary_verifier` seat** (the cross-provider, `¬builder` family operator — `assignment.primary_verifier`, key-bound), kind `re_verify`, GO, bound to `integration_sha`. Defense-in-depth: the clause itself re-asserts `verifier_provider != builder_provider` (also enforced upstream at predicate.py:67) so a standalone caller cannot accept a same-provider re_verify.
4. **The spec's "new-session" re_verify freshness is DEFERRED to scope (b)** — `session` lives only in the unsigned signer string; a cryptographically-fresh re_verify needs an overseer-issued challenge/nonce in the SIGNED payload (scope-b). Filed as inventory `threeway-signer-unsigned-session`.
5. **`human_approval` is SHA-bound + decision-bound + overseer-relayed.** Per spec §12 `{approver_identity, candidate_id, integration_sha, decision}`. A fact counts toward T3 only if: signer-seat == `overseer`, `payload.integration_sha == integration_sha`, `payload.decision == "approve"`. "Two distinct" = two distinct `approver_identity`.
5b. **All effective accessors are revocation-aware.** Spec §6.1: the predicate reads only EFFECTIVE facts. The reducer's `co_sign`, `re_verify`, `human_approvals`, and `assignments` accessors must drop any event whose `id` is in `_revoked_event_ids` (mirror `effective_attestation`). The existing `attestation_revoked` fact revokes ANY event id (reducer.py:101-103 is kind-agnostic), giving a uniform decommission path.
5c. **Documented scope-(a) limitations** (recorded in ADR-035 + inventory, not silently dropped):
   - *Human independence:* "two distinct `human_approval`" in scope (a) is two distinct **overseer-asserted** `approver_identity` labels (the overseer is one relay key) — NOT two cryptographically-independent human signatures. Genuine dual-human independence (per-approver auth / allowed-approver roster) is scope (b). Filed `threeway-human-approval-overseer-asserted`.
   - *Assignment lifecycle:* there is no dedicated `assignment_superseded` fact; a same-`pair` re-assignment supersedes via last-write-wins, and revocation removes via `attestation_revoked`. Recorded in §13A.6.
6. **`co_sign_satisfied` stays decoupled from the Event/assignment shape** — primitives `candidate_pair`, `builder_provider`, `verifier_provider`, `integration_sha`; it queries `state` for assignments/co_signs/re_verifies/human_approvals. New params are **keyword-only** so a positional mistake at the security boundary is impossible.
7. **Fail-safe preserved:** any missing/insufficient/revoked/ambiguous artifact → `False` → the predicate yields `PENDING`. Slice 3 only ever *adds* promotion paths.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `threeway/tier.py` | gate-computed tier + co-sign satisfaction predicate | **Modify**: rewrite `co_sign_satisfied`; add `_signer_seat`, `_mirror_pair_verifier_seat`, the clause helpers; NO provider/session parsing of signer strings |
| `threeway/reducer.py` | replay facts → EffectiveState | **Modify**: make `co_sign`/`re_verify`/`human_approvals` revocation-aware; add revocation-aware `assignments()` |
| `threeway/predicate.py` | `mergeable(candidate)` over effective state | **Modify**: update the single `co_sign_satisfied(...)` call (`:116`) to pass `candidate_pair`, `builder_provider`, `verifier_provider`, `integration_sha` |
| `tests/unit/test_threeway_reducer.py` | reducer accessor tests | **Modify**: revocation-aware co_sign/re_verify/human_approvals/assignments + last-write-wins (uses the file's existing `_ev(seq, kind, …)` helper) |
| `tests/unit/test_threeway_tier.py` | unit tests for tier + co-sign clauses | **Modify**: new-signature update + T2/T3 matrix incl provider-spoof, wrong-family, ambiguity (fail-closed), Pair-B symmetry, revocation |
| `tests/unit/test_threeway_predicate.py` | end-to-end predicate tests | **Modify**: `_t2_event_set`/`_t3_event_set` (both pairs' assignments) + MERGEABLE/PENDING/spoof cases |
| `ARCHITECTURE.md` | verified-truth doc | **Modify**: §13A.6 + §13A.4 count + `Last verified` |
| `DECISIONS.md` | ADR log (append-only) | **Modify**: append ADR-035 |
| `docs/REMEDIATION-INVENTORY.md` | defect inventory | **Modify**: file `threeway-signer-unsigned-session` + `threeway-human-approval-overseer-asserted` |

---

## Chunk 1: reducer support (revocation-aware accessors + assignments)

### Task 1: Revocation-aware `co_sign`/`re_verify`/`human_approvals` + `assignments()`

**Files:**
- Modify: `threeway/reducer.py:83-90`
- Test: `tests/unit/test_threeway_reducer.py`

- [ ] **Step 1: Write failing reducer tests** using the file's EXISTING `_ev(seq, kind, payload=None, **over)` helper (seq-first; `_ev` sets `id=f"e{seq}"`, `candidate_id="c1"`). Add a local `INTEG = "2" * 40`:

```python
INTEG = "2" * 40


def test_co_sign_accessor_hides_revoked():
    cs = _ev(1, "co_sign", payload={"verdict": "GO"}, subject_sha=INTEG,
             signer="operator2:codex:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1")   # cs.id == "e1"
    assert reduce([cs]).co_sign("c1", "operator2") is not None
    assert reduce([cs, rev]).co_sign("c1", "operator2") is None


def test_re_verify_accessor_hides_revoked():
    rv = _ev(1, "re_verify", payload={"verdict": "GO"}, subject_sha=INTEG,
             signer="operator:claude:s2")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1")
    assert reduce([rv, rev]).re_verify("c1", "operator") is None


def test_human_approvals_accessor_hides_revoked():
    h = _ev(1, "human_approval", signer="overseer:mech:s1",
            payload={"approver_identity": "chief-gemini", "integration_sha": INTEG,
                     "decision": "approve"})
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1")
    assert reduce([h]).human_approvals("c1") != []
    assert reduce([h, rev]).human_approvals("c1") == []


def test_assignments_returns_latest_per_pair():
    a1 = _ev(1, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
             signer="overseer:mech:s1")
    a2 = _ev(2, "assignment", payload={"pair": "B", "primary_verifier": "operator2"},
             signer="overseer:mech:s1")
    a1b = _ev(3, "assignment", payload={"pair": "A", "primary_verifier": "operatorX"},
              signer="overseer:mech:s1")          # same pair, higher seq → supersedes a1
    got = {e.payload["pair"]: e.payload["primary_verifier"]
           for e in reduce([a1, a2, a1b]).assignments()}
    assert got == {"A": "operatorX", "B": "operator2"}   # last-write-wins for A


def test_assignments_hides_revoked():
    a = _ev(1, "assignment", payload={"pair": "A"}, signer="overseer:mech:s1")
    rev = _ev(2, "attestation_revoked", revokes_event_id="e1")
    assert reduce([a, rev]).assignments() == []
```

- [ ] **Step 2: Run — verify FAIL** (`assignments` undefined; revoked still returned):

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q -k "revoked or assignments"`
Expected: FAIL.

- [ ] **Step 3: Implement** in `threeway/reducer.py`. Replace the `co_sign`/`re_verify` accessors (lines 83-87) and the `human_approvals` accessor (lines 89-90), and add `assignments()`:

```python
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
```

(No fold change: `attestation_revoked` already adds any `revokes_event_id` to `self._revoked_event_ids` regardless of the revoked event's kind, reducer.py:101-103.)

- [ ] **Step 4: Run — verify PASS**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add threeway/reducer.py tests/unit/test_threeway_reducer.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): revocation-aware effective accessors + assignments() (Slice 3)"
```

## Chunk 2: tier machinery (T2 + T3 on signed identity)

### Task 2: Extend `co_sign_satisfied` signature + the T2 clause (mirror-pinned, fail-closed)

**Files:**
- Modify: `threeway/tier.py:32-43`
- Test: `tests/unit/test_threeway_tier.py`

- [ ] **Step 1: Add the test scaffolding + update the two existing co-sign tests.** New signature is keyword-only `candidate_pair`, `builder_provider`, `verifier_provider`, `integration_sha`. Add a roster + a `_sat` caller helper at the top of the co-sign section:

```python
from threeway.envelope import Event

INTEG = "2" * 40
WRONG = "9" * 40


def _assign(seq, *, pair, builder_provider, verifier_seat, verifier_provider,
            signer="overseer:mech:s1"):
    return Event(id=f"as{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="assignment", sender="overseer", recipient="all", signer=signer,
                 payload={"pair": pair, "builder_provider": builder_provider,
                          "primary_verifier": verifier_seat,
                          "primary_verifier_provider": verifier_provider},
                 brief_id="b1", brief_version=1)


def _roster():
    # Static D2: Pair A = codex builder / claude operator; Pair B = claude builder / codex operator2.
    return [_assign(1, pair="A", builder_provider="codex",
                    verifier_seat="operator", verifier_provider="claude"),
            _assign(2, pair="B", builder_provider="claude",
                    verifier_seat="operator2", verifier_provider="codex")]


def _sat(tier, state, *, pair="A", builder="codex", verifier="claude", cand="c1"):
    return co_sign_satisfied(tier, state, cand, candidate_pair=pair,
                             builder_provider=builder, verifier_provider=verifier,
                             integration_sha=INTEG)


def test_t0_t1_cosign_satisfied_without_extra_artifacts():
    state = reduce(_roster())
    assert _sat("T0", state)
    assert _sat("T1", state)


def test_t2_t3_pending_without_any_artifacts():
    state = reduce(_roster())
    assert not _sat("T2", state)
    assert not _sat("T3", state)
```

- [ ] **Step 2: Add the T2 unit-test matrix** (including the CRITICAL provider-spoof, the wrong-family mirror, and the fail-closed ambiguity cases):

```python
def _cosign(seq, *, signer, subject_sha=INTEG, verdict="GO", cand="c1"):
    return Event(id=f"cs{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="co_sign", sender=signer.split(":")[0], recipient="all", signer=signer,
                 payload={"verdict": verdict}, candidate_id=cand, brief_id="b1",
                 brief_version=1, subject_sha=subject_sha)


def test_t2_satisfied_by_mirror_pair_operator():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1")])
    assert _sat("T2", state)


def test_t2_rejects_cosign_from_primary_verifier_seat():
    state = reduce(_roster() + [_cosign(3, signer="operator:claude:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_provider_spoof_by_primary_verifier():
    # CRITICAL: operator (real claude) signs with a SPOOFED 'codex' provider substring.
    # Identity is keyed by seat token 'operator', not the string; the mirror operator is
    # 'operator2', so the spoofed co_sign (keyed under 'operator') must NOT satisfy.
    state = reduce(_roster() + [_cosign(3, signer="operator:codex:s9")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_from_builder_director():
    state = reduce(_roster() + [_cosign(3, signer="director:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_from_coordinator():
    state = reduce(_roster() + [_cosign(3, signer="coordinator2:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_cosign_bound_to_wrong_sha():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1", subject_sha=WRONG)])
    assert not _sat("T2", state)


def test_t2_rejects_non_go_cosign():
    state = reduce(_roster() + [_cosign(3, signer="operator2:codex:s1", verdict="NITS")])
    assert not _sat("T2", state)


def test_t2_rejects_when_mirror_assignment_not_overseer_signed():
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="operator",
                      verifier_provider="claude"),
              _assign(2, pair="B", builder_provider="claude", verifier_seat="operator2",
                      verifier_provider="codex", signer="director:codex:s1")]  # not overseer
    state = reduce(roster + [_cosign(3, signer="operator2:codex:s1")])
    assert not _sat("T2", state)


def test_t2_rejects_wrong_family_other_pair():
    # Other pair B' is NOT the mirror: its verifier_provider is claude (== our verifier),
    # not codex. Proves the both-families / role-swap conditions are load-bearing.
    roster = [_assign(1, pair="A", builder_provider="codex", verifier_seat="operator",
                      verifier_provider="claude"),
              _assign(2, pair="B", builder_provider="claude", verifier_seat="operatorB",
                      verifier_provider="claude")]   # primary_verifier_provider != builder(codex)
    state = reduce(roster + [_cosign(3, signer="operatorB:claude:s1")])
    assert not _sat("T2", state)


def test_t2_fail_closed_on_two_mirror_pairs():
    # Two pairs both satisfy the mirror swap → ambiguous co-signer → fail closed (PENDING).
    roster = _roster() + [_assign(3, pair="C", builder_provider="claude",
                                  verifier_seat="operatorC", verifier_provider="codex")]
    state = reduce(roster + [_cosign(4, signer="operator2:codex:s1"),
                             _cosign(5, signer="operatorC:codex:s1")])
    assert not _sat("T2", state)


def test_t2_pair_b_direction():
    # Symmetry: Pair-B candidate (builder claude) → mirror is Pair A's operator (claude).
    state = reduce(_roster() + [_cosign(3, signer="operator:claude:s1")])
    assert _sat("T2", state, pair="B", builder="claude", verifier="codex")
```

- [ ] **Step 3: Run — verify FAIL**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q`
Expected: FAIL (TypeError on new kwargs / stub returns False for satisfied cases).

- [ ] **Step 4: Implement the new signature + T2 clause** in `threeway/tier.py`, replacing the stub (lines 32-43):

```python
def _signer_seat(signer: str) -> str:
    """The KEY-BOUND identity: the gate looks up <seat>.pub by this token, so only the
    real keyholder can produce a valid event with it. The provider/session TAIL of the
    signer string is UNSIGNED (envelope.py:67) and MUST NOT be trusted."""
    return signer.split(":", 1)[0]


def co_sign_satisfied(tier: str, state, candidate_id: str, *, candidate_pair: str,
                      builder_provider: str, verifier_provider: str,
                      integration_sha: str) -> bool:
    """Whether the tier-SPECIFIC extra approvals exist (beyond the primary release GO +
    the coordinator candidate sig, checked separately). Spec §7.2. Identity is resolved
    from overseer-signed `assignment` facts + key-bound seat tokens, NEVER from the
    unsigned signer-string provider/session. Ambiguity fails CLOSED. False is fail-safe."""
    if tier in ("T0", "T1"):
        return True
    if not _t2_mirror_cosign(state, candidate_id, candidate_pair,
                             builder_provider, verifier_provider, integration_sha):
        return False
    if tier == "T2":
        return True
    # tier == "T3"
    if not _t3_cross_provider_re_verify(state, candidate_id, candidate_pair,
                                        builder_provider, verifier_provider, integration_sha):
        return False
    return _two_distinct_human_approvals(state, candidate_id, integration_sha)


def _mirror_pair_verifier_seat(state, candidate_pair, builder_provider,
                               verifier_provider) -> str | None:
    """The MIRROR pair's primary-verifier SEAT, from overseer-signed assignments. The
    mirror (D3 'provider-role swap only') is the pair != candidate_pair whose providers
    are the exact swap: builder_provider == OUR verifier_provider AND
    primary_verifier_provider == OUR builder_provider. Fail-CLOSED: returns None unless
    EXACTLY ONE such pair exists (zero → not yet assigned; >1 → ambiguous co-signer)."""
    seats = set()
    for assign in state.assignments():
        if _signer_seat(assign.signer) != "overseer":
            continue
        ap = assign.payload
        if ap.get("pair") == candidate_pair:
            continue
        if (ap.get("builder_provider") == verifier_provider
                and ap.get("primary_verifier_provider") == builder_provider):
            seat = ap.get("primary_verifier")
            if seat:
                seats.add(seat)
    return next(iter(seats)) if len(seats) == 1 else None


def _t2_mirror_cosign(state, candidate_id, candidate_pair, builder_provider,
                      verifier_provider, integration_sha) -> bool:
    seat = _mirror_pair_verifier_seat(state, candidate_pair, builder_provider, verifier_provider)
    if seat is None:
        return False
    ev = state.co_sign(candidate_id, seat)   # key-bound lookup; revocation-aware
    return (ev is not None
            and ev.payload.get("verdict") == "GO"
            and ev.subject_sha == integration_sha)
```

- [ ] **Step 5: Run the T2 tests — verify PASS** (T3 not yet added)

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q -k "t0 or t1 or t2"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
env -u GIT_INDEX_FILE git add threeway/tier.py tests/unit/test_threeway_tier.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): co_sign_satisfied T2 — mirror-pinned fail-closed other-pair co_sign (Slice 3)"
```

### Task 3: The T3 clause (cross-provider re_verify + SHA-bound human_approval)

**Files:**
- Modify: `threeway/tier.py` (add `_t3_cross_provider_re_verify`, `_two_distinct_human_approvals`)
- Test: `tests/unit/test_threeway_tier.py`

- [ ] **Step 1: Add the T3 unit-test matrix** (incl revocation):

```python
def _reverify(seq, *, signer, subject_sha=INTEG, verdict="GO", cand="c1"):
    return Event(id=f"rv{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="re_verify", sender=signer.split(":")[0], recipient="all", signer=signer,
                 payload={"verdict": verdict}, candidate_id=cand, brief_id="b1",
                 brief_version=1, subject_sha=subject_sha)


def _human(seq, *, approver, signer="overseer:mech:s1", subject=INTEG,
           decision="approve", cand="c1"):
    return Event(id=f"h{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="human_approval", sender="overseer", recipient="all", signer=signer,
                 payload={"approver_identity": approver, "integration_sha": subject,
                          "decision": decision},
                 candidate_id=cand, brief_id="b1", brief_version=1)


def _revoke(seq, *, target_id, cand="c1"):
    return Event(id=f"rk{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="attestation_revoked", sender="x", recipient="all",
                 signer="overseer:mech:s1", payload={}, candidate_id=cand,
                 brief_id="b1", brief_version=1, revokes_event_id=target_id)


def _t3_ok():
    # Pair-A candidate (builder codex). re_verify from the cross-provider operator
    # (Pair A's own primary_verifier = operator/claude). co_sign from the mirror (operator2).
    return _roster() + [
        _cosign(3, signer="operator2:codex:s1"),
        _reverify(4, signer="operator:claude:s2"),
        _human(5, approver="chief-gemini"),
        _human(6, approver="chief-chatgpt"),
    ]


def test_t3_satisfied_full_set():
    assert _sat("T3", reduce(_t3_ok()))


def test_t3_pending_without_re_verify():
    assert not _sat("T3", reduce([e for e in _t3_ok() if e.kind != "re_verify"]))


def test_t3_rejects_re_verify_from_wrong_seat():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator2:codex:s2")  # mirror op, not cross-verifier
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_re_verify_wrong_sha():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator:claude:s2", subject_sha=WRONG)
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_non_go_re_verify():
    evs = _t3_ok(); evs[3] = _reverify(4, signer="operator:claude:s2", verdict="FAIL")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_revoked_re_verify():
    assert not _sat("T3", reduce(_t3_ok() + [_revoke(7, target_id="rv4")]))


def test_t3_pending_with_one_human_approval():
    assert not _sat("T3", reduce(_t3_ok()[:5]))   # drop the 2nd human_approval (seq 6)


def test_t3_rejects_two_human_approvals_same_identity():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-gemini")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_not_signed_by_overseer():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", signer="director:codex:s1")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_wrong_sha():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", subject=WRONG)
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_human_approval_non_affirmative_decision():
    evs = _t3_ok(); evs[5] = _human(6, approver="chief-chatgpt", decision="reject")
    assert not _sat("T3", reduce(evs))


def test_t3_rejects_revoked_human_approval():
    assert not _sat("T3", reduce(_t3_ok() + [_revoke(7, target_id="h6")]))
```

- [ ] **Step 2: Run — verify FAIL** (`_t3_cross_provider_re_verify` undefined):

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q -k t3`
Expected: FAIL.

- [ ] **Step 3: Implement the T3 helpers** in `threeway/tier.py`:

```python
def _t3_cross_provider_re_verify(state, candidate_id, candidate_pair, builder_provider,
                                 verifier_provider, integration_sha) -> bool:
    """A re_verify GO over integration_sha from the candidate pair's OWN primary_verifier
    (the cross-provider, non-builder family operator), resolved from the signed assignment.
    NOTE: the spec's "new session" freshness is NOT enforced — `session` lives only in the
    unsigned signer string; binding it to an overseer challenge is deferred to scope (b)
    (inventory `threeway-signer-unsigned-session`)."""
    if verifier_provider == builder_provider:          # defense-in-depth (also predicate.py:67)
        return False
    assign = state.assignment(candidate_pair)
    if assign is None or _signer_seat(assign.signer) != "overseer":
        return False
    seat = assign.payload.get("primary_verifier")
    ev = state.re_verify(candidate_id, seat)           # key-bound; revocation-aware
    return (ev is not None
            and ev.payload.get("verdict") == "GO"
            and ev.subject_sha == integration_sha)


def _two_distinct_human_approvals(state, candidate_id, integration_sha) -> bool:
    """Two distinct approver identities, each an overseer-relayed, SHA-bound, affirmative
    human_approval (spec §12). NOTE: in scope (a) these are two overseer-asserted labels,
    not two cryptographically-independent human signatures (inventory
    `threeway-human-approval-overseer-asserted`; per-approver auth is scope (b))."""
    approvers = set()
    for ev in state.human_approvals(candidate_id):     # revocation-aware accessor
        if _signer_seat(ev.signer) != "overseer":
            continue
        if ev.payload.get("integration_sha") != integration_sha:
            continue
        if ev.payload.get("decision") != "approve":
            continue
        approver = ev.payload.get("approver_identity")
        if approver:
            approvers.add(approver)
    return len(approvers) >= 2
```

- [ ] **Step 4: Run the full tier suite — verify all PASS**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add threeway/tier.py tests/unit/test_threeway_tier.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): co_sign_satisfied T3 — cross-provider re_verify + SHA-bound human_approval (Slice 3)"
```

## Chunk 3: predicate wiring + end-to-end acceptance

### Task 4: Wire the predicate caller + end-to-end T2/T3 promotion tests

**Files:**
- Modify: `threeway/predicate.py:116`
- Test: `tests/unit/test_threeway_predicate.py`

- [ ] **Step 1: Add end-to-end T2/T3 fixtures + tests.** Add the MIRROR pair's assignment (so the resolver can find it) and re-tier the diff/cycle_go. `_full_event_set` already supplies Pair A's assignment + Pair A's operator/claude attestations; add Pair B's assignment.

```python
def _pair_b_assignment(seq):
    return _e("assignment", seq, payload={
        "pair": "B", "builder": "director2", "builder_provider": "claude",
        "primary_verifier": "operator2", "primary_verifier_provider": "codex",
        "executing_coordinator": "coordinator2"}, signer="overseer:mech:s1")


def _t2_event_set():
    evs = _full_event_set()
    for e in evs:
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
            e.payload["assigned_tier"] = "T2"
        elif e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T2"
        elif e.kind == "cycle_go":
            e.payload["tier"] = "T2"
    evs.append(_pair_b_assignment(10))
    evs.append(_e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
                  signer="operator2:codex:s1"))
    return evs


T2_REPO = FakeRepo(diff=(".github/workflows/ci.yml",))


def test_t2_mergeable_with_mirror_cosign():
    d = evaluate("c1", reduce(_t2_event_set()), T2_REPO, default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_t2_pending_without_cosign():
    evs = [e for e in _t2_event_set() if e.kind != "co_sign"]
    d = evaluate("c1", reduce(evs), T2_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T2" in d.reason


def test_t2_pending_with_provider_spoofed_cosign():
    evs = _t2_event_set()
    evs[-1] = _e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
                 signer="operator:codex:s9")   # primary verifier spoofs provider 'codex'
    d = evaluate("c1", reduce(evs), T2_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T2" in d.reason


def _t3_event_set():
    evs = _full_event_set()
    for e in evs:
        if e.kind == "brief":
            e.payload["allowed_paths"] = ["coordination/threeway/keys/"]
            e.payload["assigned_tier"] = "T3"
        elif e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T3"
        elif e.kind == "cycle_go":
            e.payload["tier"] = "T3"
    evs += [
        _pair_b_assignment(10),
        _e("co_sign", 11, payload={"verdict": "GO"}, subject_sha=INTEG,
           signer="operator2:codex:s1"),
        _e("re_verify", 12, payload={"verdict": "GO"}, subject_sha=INTEG,
           signer="operator:claude:s2"),
        _e("human_approval", 13, payload={"approver_identity": "chief-gemini",
           "integration_sha": INTEG, "decision": "approve"}, signer="overseer:mech:s1"),
        _e("human_approval", 14, payload={"approver_identity": "chief-chatgpt",
           "integration_sha": INTEG, "decision": "approve"}, signer="overseer:mech:s1"),
    ]
    return evs


T3_REPO = FakeRepo(diff=("coordination/threeway/keys/operator.pub",))


def test_t3_mergeable_with_full_cross_family_set():
    d = evaluate("c1", reduce(_t3_event_set()), T3_REPO, default_policy())
    assert d.outcome == MERGEABLE, d.reason


def test_t3_pending_without_re_verify():
    evs = [e for e in _t3_event_set() if e.kind != "re_verify"]
    d = evaluate("c1", reduce(evs), T3_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T3" in d.reason


def test_t3_pending_with_one_human_approval():
    evs = [e for e in _t3_event_set() if not (e.kind == "human_approval"
           and e.payload.get("approver_identity") == "chief-chatgpt")]
    d = evaluate("c1", reduce(evs), T3_REPO, default_policy())
    assert d.outcome == PENDING and "co_sign not satisfied for T3" in d.reason
```

- [ ] **Step 2: Run — verify the satisfied cases FAIL** (predicate still passes the old 4-arg call):

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q -k "t2 or t3"`
Expected: FAIL (TypeError: missing required keyword-only args at the call site).

- [ ] **Step 3: Update the caller** in `threeway/predicate.py`. Replace the line at `:116`:

```python
    if not co_sign_satisfied(eff_tier, state, candidate_id, builder_provider):
```

with:

```python
    if not co_sign_satisfied(eff_tier, state, candidate_id,
                             candidate_pair=pair,
                             builder_provider=builder_provider,
                             verifier_provider=verifier_provider,
                             integration_sha=integ):
```

(`pair`, `builder_provider`, `verifier_provider`, and `integ` are local to `evaluate` — defined at lines 51, 65, 66, 49 respectively, all before line 116.)

- [ ] **Step 4: Run the full predicate suite — verify all PASS**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add threeway/predicate.py tests/unit/test_threeway_predicate.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): wire co_sign_satisfied T2/T3 into the merge predicate (Slice 3)"
```

### Task 5: Mutation-proof acceptance gate (non-vacuous, per ADR-028)

**Files:** none committed (PRODUCES EVIDENCE — each mutation applied to a clean tree, named test run, then `git checkout` reverts). Capture each command + observed RED in the wrap.

- [ ] **Step 1: Prove each guard is load-bearing.** Apply the mutation, run the named test, confirm PASS→FAIL, revert.

| Guard | Mutation | Test that must turn RED |
|---|---|---|
| T2 key-bound identity (provider-spoof defense) | in `_t2_mirror_cosign`, ignore the resolved `seat`; loop all co_signs accepting any with string-parsed provider == builder_provider | `test_t2_rejects_provider_spoof_by_primary_verifier` |
| T2 mirror role-swap | in `_mirror_pair_verifier_seat`, drop `primary_verifier_provider == builder_provider` | `test_t2_rejects_wrong_family_other_pair` |
| T2 cross-pair only | drop `if ap.get("pair") == candidate_pair: continue` | `test_t2_rejects_cosign_from_primary_verifier_seat` |
| T2 fail-closed ambiguity | change `len(seats) == 1` to `len(seats) >= 1` (return any) | `test_t2_fail_closed_on_two_mirror_pairs` |
| T2 overseer authority | drop `_signer_seat(assign.signer) != "overseer"` skip | `test_t2_rejects_when_mirror_assignment_not_overseer_signed` |
| T2 sha binding | drop `ev.subject_sha == integration_sha` | `test_t2_rejects_cosign_bound_to_wrong_sha` |
| T2 verdict | drop `ev.payload.get("verdict") == "GO"` | `test_t2_rejects_non_go_cosign` |
| T3 re_verify seat | resolve re_verify seat from the mirror pair instead of the candidate pair | `test_t3_rejects_re_verify_from_wrong_seat` |
| T3 re_verify sha | drop `ev.subject_sha == integration_sha` | `test_t3_rejects_re_verify_wrong_sha` |
| T3 re_verify revocation | in reducer `re_verify`, drop the `_revoked_event_ids` check | `test_t3_rejects_revoked_re_verify` |
| T3 human sha-bind | drop `payload.integration_sha == integration_sha` skip | `test_t3_rejects_human_approval_wrong_sha` |
| T3 human decision | drop `payload.decision == "approve"` skip | `test_t3_rejects_human_approval_non_affirmative_decision` |
| T3 human overseer | drop `_signer_seat(ev.signer) != "overseer"` skip | `test_t3_rejects_human_approval_not_signed_by_overseer` |
| T3 human revocation | in reducer `human_approvals`, drop the `_revoked_event_ids` filter | `test_t3_rejects_revoked_human_approval` |
| T3 two-approvals | change `>= 2` to `>= 1` | `test_t3_pending_with_one_human_approval` |
| co_sign revocation | in reducer `co_sign`, drop the `_revoked_event_ids` check | `test_co_sign_accessor_hides_revoked` |

- [ ] **Step 2: §9 gate clause end-to-end.** Mutation: make T2 unconditionally `return True`. Run `test_t2_pending_without_cosign` → must turn RED. Revert.

Run each as: apply edit → `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py tests/unit/test_threeway_predicate.py tests/unit/test_threeway_reducer.py -q -k '<name>'` → `env -u GIT_INDEX_FILE git checkout <file>`.
Expected: every mutation produces ≥1 RED; clean tree restored after each.

## Chunk 4: docs + decision record + inventory

### Task 6: ARCHITECTURE.md §13A + ADR-035 + inventory findings + full-suite reverify

**Files:**
- Modify: `ARCHITECTURE.md` (§13A.4 count + `Last verified`; new §13A.6)
- Modify: `DECISIONS.md` (append ADR-035)
- Modify: `docs/REMEDIATION-INVENTORY.md` (file two findings)

- [ ] **Step 1: Add §13A.6 to `ARCHITECTURE.md`** (after §13A.5):

```markdown
### 13A.6 Tiered co-sign — `co_sign_satisfied` T2/T3 (Slice 3)

`def co_sign_satisfied` (`threeway/tier.py`) gates escalated-tier promotion (§7.2), with all
identity grounded on SIGNED facts — never the unsigned `signer` string (its provider/session tail
is excluded from the 14-field signed view, envelope.py:67-90; only the key-bound seat token is
trustworthy). **T2** requires a `co_sign` GO bound to `integration_sha` from the MIRROR pair's
operator: `def _mirror_pair_verifier_seat` resolves, from the overseer-signed `assignment` facts,
the unique pair != candidate-pair whose providers are the D3 role-swap (`builder_provider ==
our verifier_provider` AND `primary_verifier_provider == our builder_provider`) and matches its
`primary_verifier` seat via the key-bound `state.co_sign(candidate_id, seat)`; **ambiguity (zero or
>1 mirror) fails CLOSED**. **T3** adds a `re_verify` GO from the candidate pair's own
`primary_verifier` seat (cross-provider operator) bound to `integration_sha`, plus two distinct,
SHA-bound, affirmative (`decision=="approve"`) `human_approval` facts signed by the `overseer`. All
effective accessors (co_sign/re_verify/human_approvals/assignments) drop revoked events. Any missing
artifact → PENDING (fail-safe). **Scope-(a) limitations** (deferred to the scope-(b) strategic loop):
the re_verify "new session" freshness is NOT enforced (session is unsigned —
`threeway-signer-unsigned-session`); "two distinct human_approval" is two overseer-asserted labels,
not two independent human signatures (`threeway-human-approval-overseer-asserted`); assignments have
no dedicated supersede fact (same-pair re-assignment is last-write-wins, revocation via
`attestation_revoked`). See `DECISIONS.md` ADR-035.
```

- [ ] **Step 2: Bump §13A.4** to the **observed** count + update `Last verified`:

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q | tail -1`
Edit §13A.4's `Slice 1 + Slice 2 + Slice 2.5 together: 191 passed` line to include Slice 3 with the observed `N passed` (cite the command per R-EVIDENCE).

- [ ] **Step 3: Append ADR-035 to `DECISIONS.md`** (append-only). Record: the unsigned-signer root cause; T2 mirror-pinned fail-closed resolution via signed assignment + key-bound seat (decisions 1,6); SHA binding (2); T3 cross-provider re_verify with independence defense-in-depth (3); the new-session freshness deferral + inventory finding (4); SHA/decision/overseer human_approval (5); revocation-aware accessors (5b); the two documented scope-(a) limitations (5c); fail-safe (7). State it closes scope (a) of spec §11 Slice 3; scope (b) deferred.

- [ ] **Step 4: File two findings** in `docs/REMEDIATION-INVENTORY.md` (match the file's row format):
  - `threeway-signer-unsigned-session` (MAJOR): §6.2 claims the signer `session_uuid` distinguishes a fresh re-verify, but `signer` is excluded from the signed view (envelope.py:67) so session/provider are spoofable; Slice 3 mitigates by never reading them; a cryptographically-fresh re_verify needs an overseer-issued challenge in the SIGNED payload — fix deferred to scope (b).
  - `threeway-human-approval-overseer-asserted` (MINOR): T3 "two distinct human_approval" is two overseer-asserted `approver_identity` labels (one relay key), not two independent human signatures; genuine per-approver auth (allowed-approver roster / dual-chief relay keys) deferred to scope (b).

- [ ] **Step 5: Run the repo doctrine gates**

Run: `.venv/bin/python scripts/ci_smoke.py` (expect §15 smoke OK)
Run: `.venv/bin/python scripts/check_no_ceremony.py` (ADR-028 — expect no NEW vacuous-pin/invisible-green)

- [ ] **Step 6: Commit**

```bash
env -u GIT_INDEX_FILE git add ARCHITECTURE.md DECISIONS.md docs/REMEDIATION-INVENTORY.md
env -u GIT_INDEX_FILE git commit -m "docs(threeway): ARCHITECTURE §13A.6 + ADR-035 + 2 inventory findings (Slice 3)"
```

---

## Acceptance gate (Slice 3 DoD — mutation-proven, per ADR-028)

1. **Identity is signed-grounded** — no clause reads provider/session out of a signer string; the provider-spoof tests (unit `test_t2_rejects_provider_spoof_by_primary_verifier` + predicate `test_t2_pending_with_provider_spoofed_cosign`) are GREEN and mutation-proven.
2. **T0/T1 unchanged**; existing predicate/reducer suites stay green.
3. **T2 requires the unique mirror-pair operator co_sign, fail-closed** — MERGEABLE with it; PENDING without; PENDING for provider-spoofed / primary-verifier / director / coordinator / wrong-SHA / non-GO / wrong-family / non-overseer-assignment co_sign; PENDING when two mirror pairs are ambiguous. Pair-B direction proven symmetric. Each guard mutation-proven non-vacuous.
4. **T3 requires cross-provider re_verify + two SHA-bound affirmative overseer human_approvals** — MERGEABLE with the full set; PENDING for every single-clause omission/violation. Each mutation-proven non-vacuous.
5. **Revocation honored on all four effective accessors** — a revoked co_sign/re_verify/human_approval/assignment yields PENDING.
6. **Fail-safe** — every insufficiency/ambiguity yields PENDING, never an erroneous MERGEABLE.
7. **Doctrine gates green** — `ci_smoke` OK; `check_no_ceremony` no new vacuous pins; full `tests/unit/test_threeway_*.py` green with the count recorded in §13A.4.

## Whole-implementation review (before declaring the gate met)

Two-stage Opus review of the landed diff + an adversarial security pass (this predicate governs T2 auth/CI-config and T3 production-data/security-controls/release-signing promotion):
- **Spec-compliance reviewer**: satisfies §7.2's co-sign matrix (T2 mirror-pair operator; T3 cross-provider re_verify + two human_approval) and §9; the §6.2 unsigned-signer constraint is respected; D3 mirror semantics enforced; the three deferrals documented + filed, not silently dropped.
- **Code-quality reviewer**: keyword-only boundary; revocation-aware accessors (all four); single `_mirror_pair_verifier_seat` resolution path; fail-closed ambiguity; Rule #13 (every effective accessor + both pairs handled symmetrically); docstring/TODO cleanup.
- **Adversarial verifier(s)**: re-attempt the two CRITICAL bypasses (provider-spoof co_sign, fabricated-session re_verify) and the round-2 holes (ambiguous third same-family pair; revoked-then-counted approval/co_sign; one human counted twice; co_sign over a stale SHA; an assignment forged by a non-overseer seat; a non-mirror other pair). Each must yield PENDING.

## §11 boundary

This is scope **(a)** of Slice 3 — the merge-gate tier machinery, identity grounded on signed facts, ambiguity fail-closed. Scope **(b)** — the strategic loop (dual chief apps, overseer brief distribution, live `co_sign`/`re_verify`/`human_approval` emission, a cryptographically-fresh re_verify challenge that closes `threeway-signer-unsigned-session`, and per-approver human auth that closes `threeway-human-approval-overseer-asserted`) — is a separate future slice requiring the human-relay seats; NOT in this plan.

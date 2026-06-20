# Threeway Control-Plane Availability Hardening — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Per the user's standing directive, every Agent/subagent dispatch runs `model: 'opus'`.

**Goal:** Close the insider **availability/DoS** class in the threeway merge gate — a malicious registered seat must not be able to *block* a legitimate merge (the integrity/forgery class is already closed by ADR-036/037/038). All three known defects share one root: the reducer records control-plane singletons via **unauthenticated last-write-wins**, and authority is checked only at *read* time, so a non-authoritative event can displace the authoritative one.

**Architecture:** Make the reducer **authority-aware**. Each singleton control-plane fact is resolved from its *authorized* seat, not merely the latest seat: static-authority kinds (assignment/brief/cycle_go/release_order/ci_result/merge_completed) are filtered at record time; the dynamic-authority kind (candidate → the per-pair `executing_coordinator`) is keyed by seat and resolved in the predicate after the assignment is known. Separately, make `run_gate` **total** (never raise uncaught after the irreversible CAS) with a main-state idempotency check so a post-CAS recording failure is recoverable.

**Tech Stack:** Python 3, pytest. Signed event-sourced bus (`threeway/`), Ed25519 + RFC 8785 JCS. Run threeway tests with the mandatory `env -u GIT_INDEX_FILE` prefix.

**Threat model:** an attacker controls ONE registered insider seat (validly signs as THAT seat, any provider/session tail); cannot forge another seat's signature; `overseer`, `ci`, and `merge-gate` are trusted. The forgery class is OUT OF SCOPE (closed). This slice is AVAILABILITY only.

**Source defects (all confirmed end-to-end, `wf_8002d3e7-e7e`, round-6 sweep):**
- `threeway-reducer-shadow-dos` (MAJOR) — higher-seq distinct-id shadow displaces an authoritative singleton (assignment/release_order/ci_result/candidate/cycle_go/brief) → predicate REJECTs a valid promotion.
- `threeway-merge-completed-no-seat-check` (MAJOR) — a forged `merge_completed` from any insider makes `run_gate` step-2 idempotency skip the real merge permanently.
- `threeway-run-gate-not-total` (MAJOR) — post-CAS `store.append`/`load_private` exceptions (not `CalledProcessError`) escape uncaught → main↔bus desync.
- Folds in the deferred `threeway-reserved-merge-id-dos` RESIDUAL (b) — reserve the `merge-*` id namespace to the gate seat.

---

## SECURITY ROOT CAUSE (drives the whole design)

`reduce()` builds singleton per-key maps with plain **last-seq-wins** and **no authority filter** (`threeway/reducer.py`): `_assignments[pair]`, `_release_order[cid]`, `_ci_result[subject_sha]`, `_candidates[cid]`, `_cycle_go[(brief_id,ver)]`, `_briefs[(brief_id,ver)]`, `_merge_completed[cid]`. The stores auto-assign a monotonically increasing `seq`, so an insider's event appended *after* the authoritative one **naturally wins the map**. The predicate checks authority on READ (`_seat(signer)=='overseer'/'ci'`), but by then the shadow has already displaced the authoritative fact, so the read sees the wrong event and REJECTs. `merge_completed` is read by `run_gate` with NO seat check at all.

**Rule for this slice: a control-plane singleton's effective value is the latest event from its AUTHORIZED seat — never merely the latest seat. Unauthorized events of these kinds are ignored for effective-state resolution (they may still exist on the bus).**

## Design decisions (to be recorded as ADR-039)

1. **Static-authority singletons — record-time filter.** In `reduce()`, fold an event into its singleton map ONLY if `_seat_of(ev.signer)` is the authorized seat for that kind:
   | kind | key | authorized seat |
   |---|---|---|
   | `assignment` | `pair` | `overseer` |
   | `brief` | `(brief_id, version)` | `overseer` |
   | `cycle_go` | `(brief_id, version)` | `overseer` |
   | `release_order` | `candidate_id` | `overseer` |
   | `ci_result` | `subject_sha` | `ci` |
   | `merge_completed` | `candidate_id` | `merge-gate` (the gate seat) |
   A non-authorized event of these kinds is dropped from the map (it cannot shadow). This is consistent with the predicate's existing read-time seat checks — it just moves the guarantee to record time so a shadow can't displace first.
   - **Gate seat parameterization:** the gate seat name (`merge-gate`) must be available to `reduce()`. Thread it as a `reduce(events, *, gate_seat="merge-gate")` keyword (default preserves callers) OR hard-code the module constant `GATE_SEAT = "merge-gate"`. Prefer the keyword for testability; default keeps the ~30 existing `reduce(events)` call sites working.

2. **Dynamic-authority singleton — `candidate`.** A candidate's authorized seat is the per-pair `executing_coordinator` (from the overseer-signed assignment), unknown at record time and possibly later in seq. Resolution: key candidates by `(candidate_id, seat)` (`_candidates: dict[tuple, Event]`), add `candidate(candidate_id, seat)`; the predicate, AFTER it has resolved the assignment + `executing_coordinator`, looks up `state.candidate(candidate_id, a["executing_coordinator"])`. Reorder `evaluate()` so the assignment resolves before the candidate is consumed (the assignment block at predicate.py:59-71 must precede the candidate-payload reads). The current early `candidate(cid)` is only used to read `pair` to find the assignment — break the chicken/egg by: (a) reading `pair` from the LATEST candidate of ANY seat solely to locate the assignment, then (b) re-resolving the AUTHORITATIVE candidate by `(cid, executing_coordinator)` and using ITS payload for every subsequent decision. A non-coordinator candidate shadow then cannot displace the authoritative candidate's payload.
   - *(Alternative to evaluate in the design phase: keep `_candidates[cid]` last-wins but have the predicate REJECT only when the coordinator's candidate is ABSENT, distinguishing "shadowed" from "no candidate". The keyed-by-seat approach is preferred — it is symmetric with the static fix and removes the displacement entirely.)*

3. **`run_gate` totality + recoverable idempotency.**
   - **Reserve the `merge-*` id namespace:** in `verify_and_reduce`, reject a load-bearing event whose `id` matches the reserved completion pattern (`merge-<...>`) unless its signer seat is the gate seat. Closes both the `merge_completed` forgery AND the reserved-id TOCTOU at ingestion.
   - **Main-state idempotency:** `run_gate` step 2 also returns `COMPLETED` when `repo.rev_parse(main_ref) == candidate.integration_sha` (the merge already landed) even if no `merge_completed` fact exists — so a post-CAS recording failure is recoverable on re-run instead of a permanent `stale` REJECT.
   - **Total exception handling:** broaden the post-CAS `try/except` so NO exception escapes `run_gate` after the irreversible CAS; on a post-CAS append failure return `GateResult("COMPLETED", "merged; completion-fact append degraded: <e>")` (main IS merged; the main-state idempotency above lets the fact be re-emitted later). The PRE-CAS exception behavior is unchanged.

4. **Fail-safe preserved:** every change only ever DROPS a non-authoritative/shadow event or makes the gate fail-safe; no change widens what can promote. The forgery class (ADR-036/037/038) is untouched and must stay green.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `threeway/reducer.py` | replay facts → EffectiveState | **Modify**: authority-filter the 6 static singleton folds; key `_candidates` by `(cid, seat)`; add `candidate(cid, seat)`; thread `gate_seat` |
| `threeway/predicate.py` | `mergeable(candidate)` | **Modify**: resolve assignment before authoritative candidate; consume `candidate(cid, executing_coordinator)` |
| `threeway/gate.py` | gate read+write side | **Modify**: `verify_and_reduce` reserved-`merge-*` namespace check; `run_gate` main-state idempotency + total post-CAS exception handling |
| `tests/unit/test_threeway_reducer.py` | reducer tests | **Modify**: shadow-DoS pins for all 6 static kinds + candidate-by-seat |
| `tests/unit/test_threeway_predicate.py` | predicate tests | **Modify**: shadow-candidate + shadow-assignment end-to-end (valid promotion survives the shadow → MERGEABLE) |
| `tests/unit/test_threeway_gate.py` | gate tests | **Modify**: forged-`merge_completed` rejected; reserved-`merge-*`-from-non-gate rejected; run_gate total under post-CAS failure; main-state idempotency |
| `ARCHITECTURE.md` / `DECISIONS.md` / `docs/REMEDIATION-INVENTORY.md` | docs | **Modify**: §13A note + ADR-039 + mark the 4 rows fixed |

---

## Chunk 1: authority-aware static singletons (reducer)

### Task 1: Record-time authority filter for the 6 static singleton kinds

**Files:** Modify `threeway/reducer.py`; Test `tests/unit/test_threeway_reducer.py`.

- [ ] **Step 1 (RED):** for EACH static kind, a higher-seq shadow from a non-authorized seat must NOT displace the authoritative fact. Example (assignment):
```python
def test_nonoverseer_assignment_shadow_does_not_displace():
    legit = _ev(2, "assignment", payload={"pair": "A", "primary_verifier": "operator"},
                signer="overseer:mech:s1")
    shadow = _ev(9, "assignment", payload={"pair": "A", "primary_verifier": "attacker"},
                 signer="operator:claude:s1")          # higher seq, non-overseer
    assert reduce([legit, shadow]).assignment("A").signer == "overseer:mech:s1"
```
  Repeat for `ci_result` (authorized=ci), `release_order`/`cycle_go`/`brief` (overseer), and `merge_completed` (gate). Add a guard test that the AUTHORIZED latest still wins (two overseer assignments → higher seq wins).
- [ ] **Step 2:** Run → FAIL (shadow currently wins).
- [ ] **Step 3 (GREEN):** add a `_AUTHORIZED_SINGLETON_SEAT = {"assignment":"overseer","brief":"overseer","cycle_go":"overseer","release_order":"overseer","ci_result":"ci","merge_completed":GATE_SEAT}` map; in each fold branch, `if _seat_of(ev.signer) != _AUTHORIZED_SINGLETON_SEAT[k]: continue` (or skip the assignment). Thread `gate_seat` per design decision 1.
- [ ] **Step 4:** Run full `test_threeway_reducer.py` → PASS (update any existing test that relied on a non-overseer singleton — mirror the ADR-038 pattern: make its signer authorized).
- [ ] **Step 5:** Commit `feat(threeway): authority-filter static control-plane singletons (close shadow-DoS) [ADR-039]`.

## Chunk 2: dynamic candidate authority (reducer + predicate)

### Task 2: Key candidates by (candidate_id, seat); predicate resolves via executing_coordinator

**Files:** Modify `threeway/reducer.py`, `threeway/predicate.py`; Test both test files.

- [ ] **Step 1 (RED):** an end-to-end predicate test — a valid candidate (signed by the executing_coordinator) plus a higher-seq SHADOW candidate (signed by a non-coordinator insider) must still be MERGEABLE (the shadow must not displace the authoritative candidate). Build on `_full_event_set()`; append a shadow `candidate` with the same `candidate_id`, higher seq, `signer="operator:claude:s1"`.
- [ ] **Step 2:** Run → FAIL (shadow displaces; predicate REJECTs "candidate not signed by executing coordinator").
- [ ] **Step 3 (GREEN):** reducer `_candidates: dict[tuple, Event]` keyed `(cid, _seat_of(signer))`; `candidate(cid)` → latest by seq across seats (used only to locate the assignment via `pair`); add `candidate(cid, seat)`. In `evaluate()`: resolve assignment first (read `pair` from the locate-only candidate), then bind `cand = state.candidate(cid, a["executing_coordinator"])`; if `cand is None` → PENDING "no candidate from executing coordinator"; use `cand.payload` for ALL subsequent reads (staging_base/branch/integration_sha/policy_digest/risk_tier).
- [ ] **Step 4:** Run full predicate + reducer suites → PASS.
- [ ] **Step 5:** Commit `feat(threeway): resolve candidate by executing_coordinator seat (close candidate shadow-DoS) [ADR-039]`.

## Chunk 3: gate ingestion + write-side totality

### Task 3: Reserved `merge-*` namespace + run_gate main-state idempotency + totality

**Files:** Modify `threeway/gate.py`; Test `tests/unit/test_threeway_gate.py`.

- [ ] **Step 1 (RED):** (a) `verify_and_reduce` rejects a load-bearing event whose `id` starts with the reserved completion prefix and whose signer seat != gate seat → GateError; (b) a forged non-gate `merge_completed` does NOT make run_gate skip the merge; (c) run_gate is total: simulate a post-CAS append failure (monkeypatch `store.append` to raise `EventIdCollision` after CAS) → run_gate returns a `COMPLETED`-degraded GateResult, does NOT raise, and main IS at integ; (d) main-state idempotency: with main already at integ but no merge_completed fact, run_gate returns COMPLETED.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3 (GREEN):** implement design decision 3 (reserved-prefix check in `verify_and_reduce`; `main==integ` short-circuit in run_gate step 2; broaden the post-CAS except to return a degraded COMPLETED, never raise). Keep the ADR-038 step-2b check (now subsumed by the namespace reservation — verify both pass or remove 2b as dead).
- [ ] **Step 4:** Run full gate suite → PASS.
- [ ] **Step 5:** Commit `fix(threeway): reserve merge-* namespace + make run_gate total & recoverable [ADR-039]`.

## Chunk 4: mutation-proof gate + docs

### Task 4: Mutation-proof acceptance (per ADR-028) + ADR-039 + inventory + ARCHITECTURE

- [ ] **Step 1:** Prove each guard is load-bearing (apply mutation → named test RED → revert): drop each static-kind authority filter; drop the candidate-by-seat resolution; drop the reserved-prefix check; drop the main-state idempotency; narrow the post-CAS except back to CalledProcessError. Capture each RED in the wrap.
- [ ] **Step 2:** Append ADR-039 (decisions 1-4); mark `threeway-reducer-shadow-dos`, `threeway-merge-completed-no-seat-check`, `threeway-run-gate-not-total` fixed and `threeway-reserved-merge-id-dos` residual fixed; bump §13A.4 count; `Last verified`.
- [ ] **Step 3:** Run repo gates: `ci_smoke.py` OK; `check_no_ceremony.py` clean; full `tests/unit/test_threeway_*.py` green.
- [ ] **Step 4:** Commit `docs(threeway): ADR-039 availability hardening + inventory + ARCHITECTURE`.

---

## Acceptance gate (Definition of Done — mutation-proven, per ADR-028)

1. **No shadow displaces an authoritative singleton** — for every static kind a higher-seq non-authorized shadow is ignored; the authoritative fact stands; mutation-proven.
2. **Candidate resolved by executing_coordinator** — a non-coordinator candidate shadow cannot displace the authoritative candidate; a valid promotion stays MERGEABLE under the shadow.
3. **`merge_completed` is gate-only** — a forged non-gate `merge_completed` cannot skip the merge; reserved `merge-*` ids from non-gate seats are rejected at ingestion.
4. **`run_gate` is TOTAL** — no exception escapes after the irreversible CAS; a post-CAS recording failure yields a degraded COMPLETED and is recoverable via main-state idempotency.
5. **Forgery class unaffected** — ADR-036/037/038 pins all stay green; the forged-promotion adversarial repros stay fail-closed.
6. **Fail-safe** — no change widens what can promote; every change only drops a shadow or fails the gate safe.

## Whole-implementation review (before declaring the gate met)

Two-stage Opus review of the landed diff + an adversarial pass that re-runs the round-6 availability attacks (shadow assignment/release_order/ci_result/candidate/cycle_go/brief; forged merge_completed; post-CAS run_gate failure) — each must now fail-closed — AND re-runs the forged-promotion catalogue to confirm the integrity class is still closed. Plus a completeness-critic pass over the remaining unprobed categories noted in `wf_8002d3e7-e7e` (cutover ingestion, empty-diff candidate, future signature-profile multiplexing).

## §11 boundary

This slice is AVAILABILITY hardening only. The integrity/forgery class (ADR-036/037/038) is closed and must not regress. The scope-(b) strategic-loop deferrals (`threeway-signer-unsigned-session`, `threeway-human-approval-overseer-asserted`) remain out of scope.

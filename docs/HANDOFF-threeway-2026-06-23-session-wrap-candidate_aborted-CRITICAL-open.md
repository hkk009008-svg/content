# HANDOFF — threeway session wrap: automation track VERIFIED + an OPEN CRITICAL (candidate_aborted authority)

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `62803631` (== origin/main; 0 ahead / 0 behind). Verify with `git log -1`.
**Live oracle:** `git for-each-ref refs/threeway/`.

> Trust git, not this prose. Re-anchor (`git fetch`; ahead/behind) before every commit/push. HEAD moved
> under this session at the very end (a spawned session landed `62803631`, the ADR-054 run-id relabel) —
> Rule #7 re-anchor caught it.

## 0. TL;DR

The **automation track is COMPLETE + independently Lane-V verified** this session: `overseer_plan`
(ADR-057, T0/T1) + its T3 extension (ADR-058, all tiers). **While grounding the next hardening item (C1,
the rework breaker), a LIVE CRITICAL was found in the verified core reducer: `candidate_aborted` has NO
authority filter → cross-pair merge DoS.** The fix is designed + ready (§2) but NOT yet applied — it
modifies core security code, so it was surfaced for user authorization (solo Tier-A protocol). **This is
the #1 priority for the next seat.**

## 1. DONE + verified this session (all on origin/main)

| Deliverable | Verdict | Commits | Evidence |
|---|---|---|---|
| scope-b sub-project 1 (mechanical-seat runtime) Lane-V | GO | `a488276a` | `logs/verify-adr056-scope-b-sp1-lane-v.json` |
| `overseer_plan` auto-decompose (T0/T1, ADR-057) | Lane-V GO + §6c re-verify GO | `b4eae43a`,`948fea50`,`dafe103f`,`c02b8049`,`4f6d5b2a`,`bac52067`,`12e5f3f4` | `logs/verify-adr057-overseer-plan-lane-v.json` |
| `overseer_plan` T3 extension (all tiers, ADR-058) | Lane-V GO | `d6dd058a`,`acbe6bbd` | `logs/verify-adr058-overseer-plan-t3-lane-v.json` |
| Remaining-tracks roadmap | — | `b870b816` | `docs/HANDOFF-threeway-2026-06-23-remaining-tracks-roadmap.md` |
| ADR-054 run-id relabel (ci_smoke --sha-refs false-positive) | — | `62803631` (spawned session) | — |

threeway suite **396 passed, 1 skipped**; ci_smoke OK; check_no_ceremony clean. Every fix mutation-proven
+ independently Lane-V'd (impl≠verifier, all non-author passes).

## 2. ⚠ OPEN CRITICAL — `candidate_aborted` has no authority filter (forge / cross-pair abort DoS)

**Confirmed chain:**
- `threeway/predicate.py:49-50` — `if state.is_aborted(candidate_id): return Decision(REJECTED, "candidate aborted")`.
- `threeway/reducer.py:91-92` — `is_aborted` = `candidate_id in self._aborted_candidates`.
- `threeway/reducer.py:311-312` — the `candidate_aborted` fold branch is the ONLY singleton with NO
  record-time authority check: `st._aborted_candidates.add(ev.candidate_id)` for ANY registered seat.
  Every sibling checks `_AUTHORIZED_SINGLETON_SEAT` (`reducer.py:268-280`); this one was missed.

**Impact:** any keyholder (any operator / ci / other-pair coordinator) can append a validly-signed
`candidate_aborted` for ANY candidate_id → the predicate permanently REJECTs that candidate → cross-pair
merge DoS. Same forgery/availability class as ADR-036/037/038. **Severity CRITICAL** (authority/availability);
current live-exploitability LOW (gate targets the TEST ref only; interactive seats offline) — but it MUST
close before real-`main` promotion, and it is the precondition for C1 (the rework breaker must count only
AUTHORIZED aborts).

**The fix (designed; mirror `authoritative_candidate` reducer.py:132-178):** abort authority = the
candidate's bound-pair `executing_coordinator` (user-decided 2026-06-23). Specifically —
1. `reducer.py` field: `_aborted_candidates: set[str]` → `_aborted_by: dict[str, set[str]]` (candidate_id → aborting signer-seats).
2. Fold branch (`reducer.py:311-312`): `st._aborted_by.setdefault(ev.candidate_id, set()).add(_seat_of(ev.signer))` — record ALL aborts with their seat; resolve authority at READ (consistent with the candidate model, which can't resolve cross-event authority at record time).
3. `is_aborted(candidate_id)`: return True iff the bound pair's `executing_coordinator` (from `_pair_namespace(candidate_id)` → `self.assignment(ns).payload["executing_coordinator"]`, mirroring `authoritative_candidate`) is in the aborting seats. Fail-safe: no namespace / no assignment → False. `assignment()` is overseer-only (record-time), so a forged assignment can't redirect authority.
   - **It only ever DROPS unauthorized aborts — never widens what can abort (fail-safe, like the comment at reducer.py:265).**
4. Consider whether the OVERSEER should also be able to abort (supreme authority). The user's decision was "executing coordinator"; overseer-abort is a possible extension (the overseer can already roll a brief via `brief_superseded`). **Default: executing-coordinator-only** unless the user/chiefs extend it.

**Blast radius (tests to UPDATE — they encode the loose behavior):**
- `tests/unit/test_threeway_reducer.py:43-45` `test_candidate_aborted_is_recorded` — uses `_ev(1, "candidate_aborted")` (un-namespaced `c1`, operator signer); rewrite to an AUTHORIZED abort (namespaced `A:c1` + overseer assignment + coordinator-signed abort) + ADD a forged-abort-ignored pin.
- `tests/unit/test_threeway_predicate.py:249-251` `test_rejects_aborted_candidate` — make its abort AUTHORIZED (coordinator of the candidate's pair) so it still REJECTs; ADD a forged-abort-does-NOT-reject pin.
- `tests/unit/test_threeway_gate_adversarial.py:~105,~265` — two `candidate_aborted` usages (sender coordinator); check they remain valid under the authority filter; the rework adversarial one (`:265`) likely needs an authorized abort.

**Acceptance + verification:** new pins — authorized abort → `is_aborted` True → predicate REJECTED;
forged abort (operator / other-pair coordinator) → `is_aborted` False → predicate proceeds; no-assignment →
False. Mutation: drop the authority check → the forged-abort pin goes RED (proves non-vacuity). Then a full
ADVERSARIAL Lane-V (forge / cross-pair / ordering: abort-before-assignment, abort-before-candidate; the
`brief_superseded` interaction). This is core-reducer security — treat as solo-Tier-A: verify via fresh
non-author subagent(s); land with **ADR-059 + ratification owed to the user**.

## 3. Remaining roadmap (full detail: `docs/HANDOFF-threeway-2026-06-23-remaining-tracks-roadmap.md`)

- **C1 — Part 1 = the §2 CRITICAL fix (do FIRST).** Part 2 = wire the rework breaker
  (`threeway/rework.py` `should_escalate`, currently UNWIRED) — count only AUTHORIZED aborts (via the
  fixed `is_aborted`/`_aborted_by`), add a `candidate_aborted` emit CLI (coordinator-signed, e.g. a
  `bootstrap_emit` subcommand), and have `overseer_plan` REFUSE a new `cycle_go` when `should_escalate` →
  surface ESCALATE (fail-safe / requirement-adding direction, per ADR-058 DD-1).
- **Sub-project 2** (real seat↔bus wiring) — LARGE; design forks (consumption model, mailbox↔bus
  transition) → write a spec + surface before building.
- **Hardening C2–C7** — mostly infra/ops (CI attestor, ref-ACL/branch-protection, external trust anchor,
  key rotation) the USER must drive; C7 (richer attestation payloads) is in-repo but modifies the audited
  gate (full adversarial Lane-V).

## 4. Open background + chips

- The 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/` cutover
  rollback manifest remain uncommitted — decide whether to commit for durable migration rollback.
- The ci_smoke `a38a3d69` false-positive (ADR-054 block) was FIXED by a spawned session (`62803631`).

## 5. Sharp edges (this session)

- **`candidate_aborted` was the lone authority-filterless singleton** — when auditing the reducer, diff
  EVERY `LOAD_BEARING_KIND`'s fold branch against `_AUTHORIZED_SINGLETON_SEAT`; a missing filter is a
  forge-DoS. (The per-pair-coordinator kinds — `candidate`, and now `candidate_aborted` — resolve
  authority at READ via the assignment, not via the fixed-seat record-time map.)
- **Execute mutations, don't argue them** — a Lane-V adversarial agent reasoned a pin was non-vacuous from
  *unmutated* control flow; the executed mutation proved it vacuous (the `overseer_plan` idempotency pin).
- **`_EMITTABLE` was a dead constant** that looked like the Q4 guard; driving `plan()` from it made it
  load-bearing + the guard mutation-catchable.
- Mandatory `env -u GIT_INDEX_FILE` on threeway python; repo python is `.venv/bin/python`; own-seat commits
  use explicit pathspec; `logs/verify-*.json` are gitignored → `git add -f`; re-anchor before every push.

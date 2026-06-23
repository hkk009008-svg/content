# HANDOFF — threeway: candidate_aborted abort-authority CRITICAL CLOSED [ADR-059]

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `2ab8bb79` (**1 ahead of origin/main — NOT yet pushed**). Verify with `git log -1` + `git rev-list --count origin/main..HEAD`.
**Live oracle:** `git for-each-ref refs/threeway/`.

> Trust git, not this prose. Re-anchor (`git fetch`; ahead/behind) before any commit/push. This session
> was clean-solo (GIT_INDEX_FILE unset, 0 skip-worktree, HEAD==origin/main at start) — no peer movement.

## 0. TL;DR

The **#1 OPEN CRITICAL from the prior wrap is CLOSED + verified**: `candidate_aborted` now carries
read-time abort authority (ADR-059). Any keyholder could previously forge a validly-signed
`candidate_aborted` for ANY candidate_id → permanent REJECT → cross-pair merge DoS. Fixed by mirroring
`authoritative_candidate`'s read-time model; **solo Tier-A adversarial Lane-V GO** (5 non-author verifiers,
`wf_4b612e08-fa2`). **One commit `2ab8bb79`, local only — push decision + user ratification owed.**

## 1. DONE + verified this session (commit `2ab8bb79`, on local `main`)

| Deliverable | Verdict | Evidence |
|---|---|---|
| `threeway-candidate-aborted-no-authority` CRITICAL fix (ADR-059) | **verified** (Lane-V GO) | `logs/verify-adr059-candidate-aborted-authority-lane-v.json` |

**The fix (3 parts in `threeway/reducer.py`):**
1. Field `_aborted_candidates: set[str]` → `_aborted_by: dict[candidate_id → {signer-seats}]` (`:69`).
2. `is_aborted` (`:95`) resolves authority at READ: effective iff the candidate_id's bound-pair
   (`_pair_namespace`) overseer-assigned `executing_coordinator` is among the aborting seats. Fail-safe —
   no abort / no namespace / no assignment / non-str coordinator → False. `isinstance(coordinator, str)`
   guard keeps read-path totality (ADR-041).
3. Fold (`:344`) records ALL aborts with `_seat_of(ev.signer)`; authority can't be resolved at record time
   (the authorizing assignment may arrive in any order) — same record-all / resolve-at-read shape as
   `candidate` (ADR-039/042).

**Authority model:** executing-coordinator-only (user-decided 2026-06-23). Overseer-abort intentionally
NOT granted (DD-4) — revisit only on user/chief direction.

**Why trustworthy:**
- TDD RED→GREEN: 7 new forge/cross-pair/no-assignment/un-namespaced/forged-assignment pins FAILED against
  the unfixed reducer, GREEN after. Mutation `is_aborted` → `return True` reddens exactly those 7 (executed,
  restored). Full threeway suite **404 passed, 1 skipped**; ci_smoke OK; check_no_ceremony clean.
- **Adversarial Lane-V `wf_4b612e08-fa2`** — 5 independent non-author verifiers (model=sonnet), lenses:
  authority-forge / ordering-read-time / fail-safe-totality / fail-safe-direction / regression-pin-integrity.
  **4 GO + 1 NITS, zero FAIL/CRITICAL/MAJOR.** Each verifier independently REPRODUCED the exploit
  (monkeypatch `is_aborted` to bare membership → all 5 forge paths fire) and confirmed the fix blocks all 5;
  full unit suite 3205 passed. NITs addressed: doc-anchor `:338`→`:344` (the fold WRITE line) fixed in
  ARCHITECTURE.md + DECISIONS.md. Two `fail-safe-totality` NITs (direct-call `is_aborted([list])` TypeError;
  mutated-non-dict-payload AttributeError) are TEST-API-only + UNREACHABLE on the bus (run_gate isinstance
  guard + well_formed + outer except) AND not a regression (pre-fix `id in set` raised identically) — no
  code change, documented in ADR-059.

## 2. ⬅ OWED (priority order)

1. **PUSH `2ab8bb79`** — local only. The track keeps origin/main in sync; prior wraps pushed each fix.
   Re-anchor first (`git fetch`; ahead/behind).
2. **User ratification of ADR-059** — solo Tier-A lands with ratification owed (core-reducer security).
3. **C1 Part 2 — wire the rework breaker** (the §2 fix was C1 Part 1). `threeway/rework.py`
   `should_escalate`/`rework_count` count RAW aborts and are **UNWIRED** (verified: zero callers in
   gate/loop/predicate). Make them count only AUTHORIZED aborts via the fixed `is_aborted`/`_aborted_by`;
   add a coordinator-signed `candidate_aborted` emit CLI (a `bootstrap_emit` subcommand); have
   `overseer_plan` REFUSE a new `cycle_go` when `should_escalate` → surface ESCALATE (requirement-ADDING /
   fail-safe direction, ADR-058 DD-1). Needs its own non-vacuous pins + Lane-V.
4. **Sub-project 2** (real seat↔bus wiring) — LARGE; design forks (consumption model, mailbox↔bus
   transition) → spec + surface before building.
5. **Hardening C2–C7** — mostly infra/ops (CI attestor, ref-ACL/branch-protection, external trust anchor,
   key rotation) the USER must drive; C7 (richer attestation payloads) modifies the audited gate → full
   adversarial Lane-V. Full detail: `docs/HANDOFF-threeway-2026-06-23-remaining-tracks-roadmap.md`.

## 3. Open background (NOT this fix's scope)

- The 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/` rollback
  manifest remain uncommitted (dirty since before this session; prior wrap §4). DELIBERATELY excluded from
  `2ab8bb79` (a security commit shouldn't carry unrelated cursor churn). Decide whether to commit for
  durable migration rollback — a separate call.

## 4. Sharp edges (this session)

- **`candidate_aborted` was the lone authority-filterless singleton** — the audit method that found it: diff
  EVERY `LOAD_BEARING_KIND` fold branch against `_AUTHORIZED_SINGLETON_SEAT`. The per-pair-coordinator kinds
  (`candidate`, now `candidate_aborted`) are correctly ABSENT from that fixed-seat map because their
  authority is per-pair/read-time — but they MUST still have a read-time check; this one had none.
- **Adversarial Lane-V via Workflow = the solo co-sign substitute** — 5 read-only `lane-v-verifier` agents
  (sonnet), each a distinct lens, each reproducing the exploit independently. Beats a single pass; the
  regression-lens verifier caught the `:338`→`:344` anchor the others (and I) missed.
- **Line-adding fix shifts ARCHITECTURE.md hard anchors** — `is_aborted` grew ~16 lines, pushing
  `authoritative_candidate` 132→159; ci_smoke `def_drift` caught it. Fix the anchor in the same change.
- **logs/verify-*.json are gitignored** → `git add -f`. Own-seat commit = explicit pathspec (kept the dirty
  mailbox cursors out). `env -u GIT_INDEX_FILE` on all threeway python; repo python = `.venv/bin/python`.

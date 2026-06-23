# HANDOFF — threeway scope-b automation track: `overseer-plan` IMPLEMENTED + Lane-V **VERIFIED**

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `bac52067` (== origin/main; 0 ahead / 0 behind). Verify with `git log -1`.

> Trust git, not this prose. Re-anchor (`git fetch`; ahead/behind) before any commit/push.

## 0. TL;DR

The **automation-track `overseer-plan` auto-decompose layer** (ADR-057) is built, pushed, and
independently **Lane-V verified GO**. It sits ABOVE the (separately verified) `overseer_emit` and turns a
JSON chief-decision file + the live bus into the overseer facts emittable now (`brief`/`assignment`/
`cycle_go`), dry-run by default, idempotent, reusing `overseer_emit` as the single signing path; it NEVER
auto-emits `release_order` (the merge-authorization key stays a deliberate manual act). Full brainstorm →
spec → plan → TDD → Lane-V → fix → re-verify cycle completed this session.

## 1. What landed (all on origin/main)

| Commit | What |
|---|---|
| `b4eae43a` | spec — `docs/superpowers/specs/2026-06-23-overseer-plan-auto-decompose-design.md` (cold spec-review GO) |
| `948fea50` | implementation plan |
| `dafe103f` | `scripts/overseer_plan.py` + `tests/unit/test_threeway_overseer_plan.py` (TDD; Q4 guard mutation-proven) |
| `c02b8049` | `overseer_plan.py` added to the bare-subprocess activation pin |
| `4f6d5b2a` | ADR-057 (DECISIONS.md) + ARCHITECTURE.md (`plan (scripts/overseer_plan.py:72)` anchor) |
| `bac52067` | **Lane-V fixes** — brief_version forwarding + `_EMITTABLE` load-bearing + non-vacuous idempotency pin + 6 coverage pins |

## 2. The component (ADR-057, DD-1..DD-5)

`scripts/overseer_plan.py --decision <overseer-decision/1.json> [--repo-dir .] [--remote origin] [--bus-id prod] [--confirm]`

- **DD-1 advance model:** each run emits every overseer fact emittable *now*; re-run as the candidate
  progresses (release_order is gated on `integration_sha`, which only exists after the non-overseer
  candidate+merge step — so the facts interleave; a single upfront burst is impossible).
- **DD-2 JSON decision file** (`overseer-decision/1`): candidate_id, brief_id, tier (T0/T1), allowed_paths[],
  assignment{pair,builder(+provider),primary_verifier(+provider),executing_coordinator}; optional
  brief_version (default 1) + policy_digest (null → `default_policy().policy_digest()`).
- **DD-3 T0/T1 scope:** emits `brief`/`assignment`/`cycle_go`; rejects T2/T3 with a clear message.
- **DD-4 `release_order` never auto-emitted:** surfaced as owed; manual via `overseer_emit release_order`.
- **DD-5 single signing path:** reuses `overseer_emit.main(argv)` (no re-implemented signing/fact shapes);
  `--bus-id` forwarded so read namespace == write namespace.

## 3. Verification — GO (verified)

**Evidence:** `logs/verify-adr057-overseer-plan-lane-v.json` (R-MEASURE instrument output).
**Gates:** threeway suite **392 passed, 1 skipped**; ci_smoke OK; check_no_ceremony clean.

- **Independent Lane-V** (`wf_daa9df85-89b`; 3 cold verifiers + 13 executed mutations + adversarial): NITS.
  10/13 mutations RED-as-expected (dry-run-no-emit, confirm authority round-trip, advance-model, loader
  reject paths, DD-5 single-signing-path, DD-4 release_order-in-plan).
- **3 findings actioned (`bac52067`):** (1) MINOR brief_version-forwarding bug (a v2 candidate was blocked
  forever); (2) MINOR partially-vacuous idempotency pin (refstore dedup hid a broken planner — *executed
  mutation overruled an adversarial agent's reasoning*); (3) NIT dead `_EMITTABLE` constant → made
  load-bearing (Q4 guard now mutation-catchable). +6 coverage pins. Fixes mutation-proven (M1/M2/M3 → RED).
- **§6c re-verification** (fresh non-author `lane-v-verifier`, impl≠verifier): **GO** — all three fixes
  correct, in-scope, non-vacuous; `overseer_emit.py` untouched; 15/15 pins; ceremony clean.

## 4. NEXT (chief prioritization)

1. **T3 extension (fast-follow):** emit `approver_roster` + `re_verify_challenge`; decompose the single
   `PENDING "co_sign not satisfied"` (`predicate.py:131`) into its overseer-emittable vs non-overseer-owed
   parts (needs `tier.py`-internal reasoning). The planner is structured so adding two facts + an
   `approvers[]` decision field is additive.
2. **§7 hardening track** (gates real-`main` promotion): CI attestor, external trust anchor, ref-ACL
   enforcement, liveness/recovery (wire the dead `rework.py` ESCALATE breaker), key rotation.
3. **Sub-project 2:** real seat↔bus wiring (interactive seats emit/consume bus events); removes
   `scripts/bootstrap_emit.py`.

Also still open (pre-existing background): the 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) +
`coordination/mailbox/.migration/` cutover rollback manifest are uncommitted — decide whether to commit.

## 5. Sharp edges (this session)

- **Execute mutations, don't argue them:** an adversarial agent reasoned the idempotency pin was
  non-vacuous (from unmutated control flow); the *executed* mutation (plan ignores presence → STAYED-GREEN
  via refstore dedup) proved it vacuous. The fix added an `overseer_emit.main` call-count spy.
- **Dead constants are a guard smell:** `_EMITTABLE` looked like the Q4 enforcer but was never read;
  driving `plan()` from it made it real and the guard mutation-catchable.
- **Reuse > re-implement for signing:** `overseer_plan` calls `overseer_emit.main` rather than re-deriving
  fact shapes — one signing path, and the emitted facts are byte-identical to the verified `overseer_emit`.
- Mandatory `env -u GIT_INDEX_FILE` on threeway python; repo python is `.venv/bin/python`; own-seat commits
  use explicit pathspec; re-anchor (`git fetch`) before every push.

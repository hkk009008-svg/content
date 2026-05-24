# Protocol Rules — Emergence + Invocation Log

Tracks each codified rule's introduction (codification SHA + race that triggered it)
and per-session invocation count. Updated manually at session-close by operator
(or director, whoever wraps the session).

## Rule registry

| # | Rule | Codified | Race that triggered |
|---|---|---|---|
| 1 | Role partition (director-only / operator-only / shared) | `ad6cb4f` | Session 6 phase_c pre-locate race |
| 2 | Signaling narration (announce shared-task intent in chat) | `ad6cb4f` | Same race |
| 3 | Git tiebreaker (first commit to land wins) | `ad6cb4f` | Hypothetical; documented preemptively |
| 4 | State-asserting writes precondition (`git log -5` before Write) | `ea97d0a` | Stale handoff doc race (`843c102` pre-write) |
| 5 | Race-acknowledging commit body (name what shifted during work) | `ea97d0a` | Same |
| 6 | Counter-bump fold-and-surface (during concurrent ops) | `ea97d0a` | Standalone `chore(baseline)` pollution risk |
| 7 | Pre-commit re-verify (state changes between Write and commit) | `416d610` | `a6e3ff1` mid-handoff race (Monitor.tsx shipped during operator handoff Write; operator caught in race-ack body of `1541a69`) |
| 8 | Mailbox authority (sent events bind equal to user-relayed signals) | `416d610` | User-as-relay bottleneck observed across cycles 1-3 — every inter-session signal had to route through user, eating throughput |
| 9 | Operator-side reviewer is independent, not duplicate (second-opinion convention) | `d61bdc8` | Substance imbalance ~30:1 (director:operator) across cycles 3-4 + structural blind-spot risk in single-context reviewer pass; user surfaced + operator drafted v4 |
| 10 | Joint-team mode (two seats of one team; co-agent mode) | `_Protocol Bundle v5 ship_` | User surfaced "director codifies rules that bind themselves" + asymmetry-as-hierarchy concerns; v5 reframes role partition as specialization, not hierarchy |
| 11 | Codification bias check (per-rule beneficiary flagging + non-beneficiary veto) | `_Protocol Bundle v5 ship_` | User surfaced "director-only memory writes" + "codification meta-bias" concerns; R11 makes future codification per-rule auditable |

> Historical note: Rules #7 + #8 originally shipped with the placeholder
> `_Protocol Bundle v2 ship_` in the "Codified" column because the rules-log
> file was part of the same ship commit that codified them (chicken-and-egg —
> the file couldn't reference its own enclosing commit SHA pre-commit).
> Resolved in cycle 4: operator updated both rows to `416d610` after the
> ship landed. Pattern for future self-referencing rule additions: ship
> with placeholder, update at next session-close. **Rule #9 follows the
> same pattern** — ships with `_Protocol Bundle v4 ship_` placeholder;
> operator updates to actual SHA in follow-up commit.

## Protocol Bundle v4.1 — Lane V refinements (cycle 6)

Codified during cycle 6 in response to operator's S13 Lane V
verification-report (`coordination/mailbox/archive/2026-05-24T17-24-52Z-operator-to-director-verification-report.md`) §v4.1 candidate
clarifications. Two operator-surfaced refinements shipped as v4.1
(mirrors v2.1's pytest-regex-fix shape):

**CC-1 — Lane V coalescing rule.** Operator MAY coalesce per-commit
Lane V dispatches into a single range-review when commits are small
(≤5), tightly coupled (same brief / shared contract surface), and
isolation-review would lose cross-system context. Strict per-commit
trigger remains the default; coalescing is operator discretion.
Empirical basis: S13's `feat(types)` + `feat(web)` commits were
correctly coalesced into one Lane V dispatch covering
`029dbf9..2fb44d1`; the cross-system review caught F1 CRITICAL that
isolation review of either commit alone would have missed.

**CC-2 — Spec-reviewer hallucination mitigation.** General-purpose
spec reviewer observed (2/2 dispatches) to make confident
"X exists" / "X is required" claims that didn't survive grep
verification (dispatch #1: "module already imports os at top-level";
dispatch #2: "ReviewStage requires onRefreshProject Prop"). Both
hallucinated. v4.1 codifies: operator's spec-reviewer prompt MUST
include explicit "verify before asserting existence" instruction
requiring grep / Read verification of any symbol/prop/import claim
before inclusion in the report. If hallucinations persist after
CC-2 codification (≥1 more in cycle-7+ Lane V dispatches), v4.2
should consider operator's CC-2 options 2 (third lightweight
verifier subagent) or 3 (different subagent type for spec review).

v4.1 ship SHA: `_Protocol Bundle v4.1 ship_` (this commit; operator
updates at next session-close per chicken-and-egg pattern).

## Beneficiary distribution snapshot (Rule #11)

Per Rule #11 (codification bias check), every existing rule and every
future rule should have its primary beneficiary flagged. Retroactive
analysis for Rules 1-11, performed during v5 ship:

| Rule | Primary beneficiary | Reasoning |
|---|---|---|
| 1 (Role partition) | both | partitions work for both seats |
| 2 (Signaling) | both | both narrate |
| 3 (Git tiebreaker) | both | resolves races for both |
| 4 (State-asserting writes precondition) | operator-seat | catches stale handoff writes (operator-only territory pre-v5) |
| 5 (Race-acknowledging commit body) | both | both write commits |
| 6 (Counter-bump fold-and-surface) | operator-seat | counter bumps are operational |
| 7 (Pre-commit re-verify) | both | both commit |
| 8 (Mailbox authority) | user | closes user-as-relay bottleneck for both seats |
| 9 (Operator-side reviewer is independent) | operator-seat | enables Lane V |
| 10 (Joint-team mode) | both | discipline for both seats |
| 11 (Codification bias check) | user | reduces bias; serves principal's interest |

**Distribution snapshot (cycle-6 close, post-v5 ship):**
- `both`: 5 (Rules 1, 2, 3, 5, 7, 10) — symmetric disciplines
- `user`: 2 (Rules 8, 11) — close gaps in user-supervision
- `operator-seat`: 3 (Rules 4, 6, 9) — operational layer where races occur
- `director-seat`: 0 — no rules primarily benefit director-seat alone

**Observed pattern (5+2+3+0):** codification has been operator-
friendly (operator-seat surfaces races they encounter in the
operational layer) and user-supervisory (mailbox-authority + bias-
check close coordination gaps the user-as-relay model couldn't
handle). The bias hypothesis the user surfaced (director codifies
rules favoring themselves) is empirically not borne out.

**v5 self-application:** v5's components (P1, R10, R11, D, E, B, M,
S, Sh) distribute as: 7 both / 1 user / 1 operator-seat / 0 director-
seat. v5 passes its own R11 check at introduction — strongest
possible introduction for a meta-rule.

**Future bundles MUST update this snapshot** when adding new rules.
Asymmetric-beneficiary rules require explicit non-beneficiary consent
per Rule #11's veto path.

## Invocation log

**Note on plateau interpretation (per Protocol Bundle v3 §Minor):** Rule
emergence rate is measured per-regime. The current regime is parallel-session
operator+director coordination at modest throughput (~20-30 commits per
session, ~3-4 sessions per cycle). Different regimes (higher throughput,
longer runs, more concurrent roles, external CI pressure) may surface
failure modes the existing rules don't catch. **Plateau in this regime ≠
convergence in all regimes.** Treat the current 8-rule set as stable for
current conditions, not as a complete protocol.

## Infrastructure audits

| Audit | Scope | Findings doc | Commit |
|---|---|---|---|
| Hook script (v2.1 baseline) | `.claude/hooks/update-state.sh` vs v2 §A as amended by v2.1 | [docs/AUDIT-hook-script-v2-2026-05-24.md](AUDIT-hook-script-v2-2026-05-24.md) | `3340d1f` |

### Session 2026-05-24-cycle-3 (this conversation)

Retrospective count of rule invocations during cycle 3 (the conversation that
shipped Sessions 7, 8, 9, Monitor.tsx wiring, P3-1 audit, P4-3 product design
+ Session 11 brief, plus the bundle ship itself).

| Rule | Invocations | Notes |
|---|---|---|
| 1 | 8+ | Role partition consciously consulted every shared-task decision (dispatch, reviewer, minors-chore, push-decision) |
| 2 | 4 | Director narrated dispatches ("Dispatching Session 8/9 implementer..."); operator narrated handoff-doc-write claim |
| 3 | 0 | No dispatch races landed |
| 4 | 6 | Pre-Write `git log -5` performed before each state-asserting commit (P4-3 doc, POST-ROADMAP refresh, S11 brief, etc.) |
| 5 | 3+ | `843c102`, `1541a69` (operator), `64c7571` (director); see also operator's `1b3f6f8` proposal revision |
| 6 | 4+ | Counter-bump held + folded into 4+ different commits (`ea97d0a`, `1541a69` operator-fold, etc.) |
| 7 | n/a | New rule, not yet invocable (codified in same ship that introduces it) |
| 8 | n/a | New rule, not yet invocable (`coordination/mailbox/` exists post-ship but no events yet) |

(Future sessions append new tables.)

## Retirement criteria

A rule unused for 5 consecutive sessions → flagged for review.
If still unused after 3 more sessions → retired (moved to "## Retired rules"
section below with retirement-SHA + reason).

## Retired rules

_None yet. As rules retire, append here with retirement-SHA + reason._

## Phase 2 (deferred)

Auto-detection of rule invocations via grep on commit-body keywords. Wait
until manual logging accumulates ~3-5 sessions of data so we know which
phrases are reliable signals. Goal: hook into the same PostToolUse pipeline
that maintains STATE.md, increment per-rule counters on commit.

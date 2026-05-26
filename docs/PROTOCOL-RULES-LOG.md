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
| 10 | Joint-team mode (two seats of one team; co-agent mode) | `d66690f` | User surfaced "director codifies rules that bind themselves" + asymmetry-as-hierarchy concerns; v5 reframes role partition as specialization, not hierarchy |
| 11 | Codification bias check (per-rule beneficiary flagging + non-beneficiary veto) | `d66690f` | User surfaced "director-only memory writes" + "codification meta-bias" concerns; R11 makes future codification per-rule auditable |
| 12 | Brief-level grep-the-writes discipline (codifier MUST grep production writes before naming a symbol in a brief) | `8ab0bbb` | Lane V #6 F1 N=1 (vestigial `performance_take_id` field; production writes `approved_performance_take_id`; closed `6c1171a`) + Lane V #8 spec-reviewer prompt preventive N=2 (0 divergences). N=2 threshold per director's Lane V #6 REPLY at `2026-05-25T18-44-52Z`. Codification per v5.1 proposal `b583305` + operator REPLY explicit consent `9f032db` |
| 13 | Symmetric-endpoint audit discipline (codifier MUST audit existing endpoints on shared state when adding new endpoint with same fence/flag/state) | `8ab0bbb` | Lane V #8 I1 CRITICAL N=1 (iterate endpoint missing the gate-bypass `/screening/approve` + `/assemble/re-assemble` had; closed `9e9b008`) + Val#1 V1 N=2 (`/screening/approve` missing precondition `/assemble/screen` had; closed `d10b849`). Codification per v5.1 proposal `b583305` + operator REPLY explicit consent `9f032db` |
| 14 | Operator-driven Lane B template + selection criteria (5-stage flow + 5 selection criteria distinguishing operator-driven-eligible from director-driven-default work) | `61cac6d` | B-005 N=1 (cycle-11, `c296105`; 10 sites in `domain/project_manager.py`; 142 prod LoC; Lane V #11 ✅ READY TO SHIP) + B-006-broad-A N=2 (cycle-12, `5b68776`; 6 sites across 4 files; 82 prod LoC; Lane V #12 ✅ READY TO SHIP). Criteria-exclusion validation: B-006-broad-B (cycle-12, `a0493dc`; 243 prod LoC; correctly director-driven). Codification per v5.2 proposal `f5fb58d` + operator REPLY explicit consent + 2 substantive refinements (R-Q1-1 LoC boundary ≤150 prod; R-Q4-1 default fallback (a) defer) folded at ship `dea6401` |

> Historical note: Rules #7 + #8 originally shipped with the placeholder
> `_Protocol Bundle v2 ship_` in the "Codified" column because the rules-log
> file was part of the same ship commit that codified them (chicken-and-egg —
> the file couldn't reference its own enclosing commit SHA pre-commit).
> Resolved in cycle 4: operator updated both rows to `416d610` after the
> ship landed. Pattern for future self-referencing rule additions: ship
> with placeholder, update at next session-close. **Rule #9 follows the
> same pattern** — ships with `_Protocol Bundle v4 ship_` placeholder;
> operator updates to actual SHA in follow-up commit. **Rules #10 + #11
> followed the same pattern at v5 ship** (`d66690f`); **Rules #12 + #13
> follow the same pattern at v5.1 ship** — ship with `_Protocol Bundle
> v5.1 ship_` placeholders; whichever seat is active next session-close
> updates to actual ship SHA in follow-up commit. **Rule #14 follows the
> same pattern at v5.2 ship** — ships with `_Protocol Bundle v5.2 ship_`
> placeholder; whichever seat is active next session-close updates to
> actual ship SHA in follow-up commit.

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

v4.1 ship SHA: `509db7c` (filled post-ship by operator per chicken-and-egg
pattern; mirrors `3e57ddf` v2 / `d8f2407` v3 / `d90036b` v4).

## Beneficiary distribution snapshot (Rule #11)

Per Rule #11 (codification bias check), every existing rule and every
future rule should have its primary beneficiary flagged. Retroactive
analysis for Rules 1-11, performed during v5 ship; extended to Rules
12-13 at v5.1 ship:

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
| 12 (Brief-level grep-the-writes discipline) | director-seat | constrains brief-writing (director-seat specialization); reduces Lane V cleanup for symbol-divergence (operator-seat benefits downstream) |
| 13 (Symmetric-endpoint audit discipline) | director-seat | constrains endpoint design (director-seat specialization); reduces Lane V findings for symmetric cases (operator-seat benefits downstream) |
| 14 (Operator-driven Lane B template + selection criteria) | both | enables operator-seat (codifies capability) + constrains operator-seat (5 criteria); enables director-seat (yield signal) + constrains director-seat (cannot claim operator-eligible work without explicit reason); symmetric on both axes |

**Distribution snapshot (cycle-13 entry, post-v5.2 ship):**
- `both`: 7 (Rules 1, 2, 3, 5, 7, 10, 14) — symmetric disciplines
- `user`: 2 (Rules 8, 11) — close gaps in user-supervision
- `operator-seat`: 3 (Rules 4, 6, 9) — operational layer where races occur
- `director-seat`: 2 (Rules 12, 13) — constrain director-seat's specialization work

Total: **14 rules** (was 13 at cycle-10 close, post-v5.1 ship).
Second consecutive bundle to add a `both`-beneficiary rule
(v5.1 was 2 director-seat; pre-v5.1 was mostly `both` with operator-seat
asymmetry). The asymmetric lean has returned toward neutral; v5's
retroactive R11 analysis already disproved the "director codifies rules
favoring director-seat" bias hypothesis. R11 explicit-consent (operator
in `dea6401`) was customary not required for `both`-annotated Rule #14.

**Prior snapshot (cycle-10 close, post-v5.1 ship):**
- `both`: 6 (Rules 1, 2, 3, 5, 7, 10) — symmetric disciplines
- `user`: 2 (Rules 8, 11) — close gaps in user-supervision
- `operator-seat`: 3 (Rules 4, 6, 9) — operational layer where races occur
- `director-seat`: 2 (Rules 12, 13) — constrain director-seat's specialization work; empirically derived from N=2 cycle-10 failure modes; operator-seat (non-beneficiary) consented explicitly per R11 veto path

**Prior snapshot (cycle-6 close, post-v5 ship):** `both`: 6 / `user`:
2 / `operator-seat`: 3 / `director-seat`: 0 = 11 rules. (Note: the
prior text listed "`both`: 5" but the listed rule IDs (1, 2, 3, 5,
7, 10) are 6 rules — corrected at v5.1 ship as a drive-by; the
listed IDs were always correct.)

**Observed pattern (6+2+3+2 = 13):** codification has been operator-
friendly (operator-seat surfaces races they encounter in the
operational layer) and user-supervisory (mailbox-authority + bias-
check close coordination gaps the user-as-relay model couldn't
handle). v5.1 adds the first two director-seat-beneficiary rules,
empirically derived from N=2 evidence operator-seat surfaced; this
re-balances the distribution without forcing artificial balance.
The bias hypothesis the user surfaced (director codifies rules
favoring themselves) remains empirically not borne out — v5.1's
director-seat-beneficiary rules are CONSTRAINTS on director-seat's
work, not authority expansions.

**v5 self-application:** v5's components (P1, R10, R11, D, E, B, M,
S, Sh) distribute as: 7 both / 1 user / 1 operator-seat / 0 director-
seat. v5 passes its own R11 check at introduction.

**v5.1 self-application:** v5.1's two new rules (#12, #13) distribute
as: 0 both / 0 user / 0 operator-seat / 2 director-seat. v5.1 is the
FIRST asymmetric-beneficiary bundle since R11 was codified; operator-
seat (non-beneficiary) consented affirmatively in REPLY `9f032db`
per the R11 explicit-consent path. v5.1 demonstrates R11's veto
mechanism working as designed — the asymmetric annotation triggered
explicit consent rather than implicit acceptance.

**v5.2 self-application:** v5.2's one new rule (#14) distributes as:
1 both / 0 user / 0 operator-seat / 0 director-seat. v5.2 returns
the asymmetric lean toward neutral (post-v5.1's 2 director-seat).
R11 explicit consent (operator in REPLY `dea6401`) was customary per
v5.1 precedent — not required for `both`-annotated rules, but
preserved for cleanliness. v5.2 demonstrates the proposal cycle
working for a symmetric-beneficiary rule (no veto path applicable;
consent customary).

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

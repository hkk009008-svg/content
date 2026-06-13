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
| 15 | Cross-seat fix-on-received-findings convention (one seat closes the other seat's Lane V finding via standalone `fix:` commit; bidirectionally symmetric; 3-option disposition shape + commit-body convention + audit-trail discipline) | `24c145a` | `442e154` N=1 (cycle-12; director closes operator's Lane V #12 I1; IMPORTANT-advisory ValidationError-swallow at broad-A helper caller sites; option 2 chosen because option 1 fold-into-broad-B-brief foreclosed by parallel-execution timing; intra-cycle close ~minutes) + `336403d` N=2 (cycle-13 entry; director closes operator's Lane V #13 M-3; MINOR-DEFER thread-swallow observability hardening via `logger.error` + `exc_info=True`; option 2 chosen for DEFER-categorized finding; cross-cycle close ~half day with explicit DEFER ACK). Codification per v5.3 proposal `dc7df5d` + director REPLY `3a0e433` explicit consent + 1 substantive refinement (R-Q2-1 CRITICAL "never (a) fold" → "preferred (b); (a) with explicit-justification") + 5 silent-accepts folded at ship |
| 16 | User-direction without owner-spec (complementary-parallel work; second-to-ship owes a convergence event ≤30min) | `7773502` | cycle-16 Shape-A races (dispatch-claim + synthesis-doc + brief-scaffold) + advisory-convergence instance (five-for-five mechanism convergence; pre-commit variant `fd3dc33`). Full text in CLAUDE.md Rule #16 |
| 17 | Workflow-assisted analysis lanes (`/workflows` = read-analysis multiplier, NOT implementation engine; 5 guardrails) | `52658eb` | forward-looking (feature unavailable in runtime at codification; guardrails ratified ahead of activation; first dogfood at v5.6). Full text in CLAUDE.md Rule #17 |
| 18 | Doc-maintenance as a verifier-scoped dispatch pattern (librarian wielding `check_doc_claims.py`; mechanical slice owned directly, claim-edits senior-reviewed) | `4eecb72` | doc-drift recurring cost (GitNexus phantom ADR-016 + Lane V #24 wrong-fix-rec + proposal's own stale F1-citation — 3 live exhibits). ADR-019. Full text in CLAUDE.md Rule #18 |
| 19 | Live-presence-over-inferred-idle (presence files; liveness=freshness not commit-recency; bind via artifacts not chat; `current_task`-rot guard) | `cec6d72` | user-reported 2026-05-30 mutual-offline/unaware failure; operator corroborated RC1–RC5 in one session (inferred director offline; narration inert; STATE.md director=4-vs-1; cursor lag; ref-race ×2). v5.7 proposal `e353479` + operator REPLY `ab9925d` CONSENT + user Q4=D-a |
| 20 | Shared-state-accuracy (awareness gate recomputes unread `to:`-filtered + content-ts; STATE.md is a cache; per-event acks) | `cec6d72` | same session: RC3 (STATE.md count both-directions + mtime → director=4-vs-1) + RC4 (cursor lag). M2 fix validated old=3/new=1 (DRAFT §1). Codification per v5.7 + operator REPLY `ab9925d` |
| 21 | Verdict-ahead-of-report (when peer seat is blocked, give verdict first, report later) | `_TBD_` | `6f3b809` verdict-first unblocked billed pod session |
| 22 | Flag-before-burn (require review before running fee-spending scripts) | `_TBD_` | Unreviewed train script carried F1 fee-respend defect (`3a589da` guard) |
| 23 | Lane ownership and cross-lane ADRs (a seat does substantive work only in its lane; cross-cutting ADRs need both directors' sign-off) | `_TBD_` | Scaling 2-seat to 4-seat team model; resolving lane overlap and architecture conflicts |

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
> actual ship SHA in follow-up commit. **Rule #15 follows the same
> pattern at v5.3 ship** — ships with `_Protocol Bundle v5.3 ship_`
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
| 15 (Cross-seat fix-on-received-findings convention) | both | enables both seats (codifies cross-seat closure mechanism that previously operated ad-hoc) + constrains both seats (formalizes disposition + commit-body convention); bidirectionally symmetric (operator-closes + director-closes) even though N=0 for operator-closes direction at codification time |
| 16 (User-direction without owner-spec) | both | symmetric obligation — either seat, whichever ships second, owes the ≤30min convergence event; complementary-parallel work is net-positive not redundant |
| 17 (Workflow-assisted analysis lanes) | both | director gains scaled blast-radius/impact analysis pre-Lane-B; operator gains scaled Lane S scouting + Rule #12/#13 audits; symmetric |
| 18 (Doc-maintenance verifier-scoped dispatch) | both | consolidation cost lands on operator (Lane D mechanical-slice carve-out; consent required + given bounded) + both benefit from kept-true docs; claim-edits stay senior-reviewed |
| 19 (Live-presence-over-inferred-idle) | both | both owe presence-file maintenance; both gain accurate peer-liveness; operator consented (REPLY `ab9925d`) |
| 20 (Shared-state-accuracy) | both | both seats' awareness gate recomputes truth; symmetric; operator consented (REPLY `ab9925d`) |

**Distribution snapshot (cycle-17, post-v5.7 ship):**
- `both`: 13 (Rules 1, 2, 3, 5, 7, 10, 14, 15, 16, 17, 18, 19, 20) — symmetric disciplines
- `user`: 2 (Rules 8, 11) — close gaps in user-supervision
- `operator-seat`: 3 (Rules 4, 6, 9) — operational layer where races occur
- `director-seat`: 2 (Rules 12, 13) — constrain director-seat's specialization work
- (was 8 both / 2 user / 3 operator-seat / 2 director-seat = 15 at cycle-13 mid; v5.4–v5.7 added Rules #16–20, all `both` — the symmetric-discipline trend continues; total **20 rules**)

*Prior snapshot (cycle-13 close, post-v5.3 ship):* Total: **15 rules** (was 14 at cycle-13 entry, post-v5.2 ship).
**Third consecutive bundle to add a `both`-beneficiary rule** (v5.1
was 2 director-seat; v5.2 was 1 `both`; v5.3 is 1 `both`). `both` is
now the dominant category at 53.3% (8/15). R11 explicit-consent
(director in `3a0e433`; operator in proposal sign-off `dc7df5d`) was
customary per v5.1/v5.2 precedent — not required for `both`-annotated
rules but preserved for cleanliness.

**Prior snapshot (cycle-13 entry, post-v5.2 ship):**
- `both`: 7 (Rules 1, 2, 3, 5, 7, 10, 14) — symmetric disciplines
- `user`: 2 (Rules 8, 11) — close gaps in user-supervision
- `operator-seat`: 3 (Rules 4, 6, 9) — operational layer where races occur
- `director-seat`: 2 (Rules 12, 13) — constrain director-seat's specialization work

Total: **14 rules** (was 13 at cycle-10 close, post-v5.1 ship).
Second consecutive bundle to add a `both`-beneficiary rule
(v5.1 was 2 director-seat; pre-v5.1 was mostly `both` with operator-seat
asymmetry). The asymmetric lean returned toward neutral; v5's
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

**v5.3 self-application:** v5.3's one new rule (#15) distributes as:
1 both / 0 user / 0 operator-seat / 0 director-seat. v5.3 is the
**third consecutive bundle** to add a `both`-beneficiary rule
(post-v5.2's 1 `both`); the trio progressively re-balances the
asymmetric lean introduced by v5.1's 2 director-seat additions.
R11 explicit consent (director in REPLY `3a0e433`; operator in
proposal sign-off `dc7df5d`) was customary per v5.1/v5.2 precedent —
not required for `both`-annotated rules. v5.3 also demonstrates
**N=0 bidirectional codification working as designed** per the Q4
silent-accept rationale: the operator-closes-director-flagged
direction is codified at N=0 to avoid retroactive scope-creep at
v5.4+ when N=1 emerges.

**Future bundles MUST update this snapshot** when adding new rules.
Asymmetric-beneficiary rules require explicit non-beneficiary consent
per Rule #11's veto path.

## N=1 candidates filed for future codification

Tracks rules-pipeline candidates that emerged from Lane V dispatches /
operational observations but haven't yet accumulated N=2 evidence to
warrant codification. Per the N=2-floor discipline (v5.1 R-D-1 + v5.2 Q6;
"never codify at N=0 or N=1 evidence"), candidates wait here until a
second qualitatively-distinct instance crystallizes the codifiable shape.

**Candidate numbering** preserves the original cycle-12 closure REPLY
series (`2fbe8a4`): #1-#6. Already codified: **#2 → Rule #14** at
`61cac6d` (v5.2 ship; operator-driven Lane B template); **#6 → Rule #15**
at `24c145a` (v5.3 ship; cross-seat fix-on-received-findings). The
remaining 4 candidates carry forward below. Future candidates added at
#7+.

**Promotion lifecycle** (de-facto observed; not yet codified): candidate
filed at N=1 → carry-forward annotated in transplant handoffs →
PROTOCOL-RULES-LOG.md registry entry (this section) → N=2 emergence in
later cycle → proposal-cycle drafting (operator OR director per role
partition Sh) → REPLY-cycle refinement → ship → row added to rule
registry table above → candidate row removed from this section.

### Candidate #1 — Rule #13 wording precision (audit-completeness vs audit-disposition)

- **Refines:** Rule #13 (symmetric-endpoint audit discipline; codified
  `8ab0bbb`).
- **N=1 instance:** Lane V #10 (cycle 11; mid-cycle); audit on
  `CINEMA_AUTO_APPROVE_MOTION` flag emergence raised a nuance the
  current Rule #13 wording elides: when the audit IS complete but the
  disposition decision is the gap (mirror vs. defer vs. document), the
  rule's "audit + symmetric fold OR follow-up issue" language doesn't
  distinguish completeness from disposition.
- **Current N count:** 1 (cycle-11 originating; unchanged through
  cycle-13 close).
- **Codifiable shape:** Add to Rule #13's audit-completion language an
  explicit "audit-completeness ≠ audit-disposition" distinction: the
  codifier MUST not only enumerate sibling endpoints (completeness) but
  ALSO state the disposition for each (mirror / defer / document /
  exempt). Cleanly separates "did you look?" from "what did you decide?"
- **N=2 emergence criteria:** A second Lane V (or director-driven audit)
  where the audit enumeration is complete but disposition is missing or
  ambiguous, AND the missed disposition cascades to a real finding (not
  just a hypothetical concern). Cycle-12 Lane V #12's audit on broad-A
  was complete + dispositioned cleanly; cycle-13 had no Rule #13
  invocations. **Watch cycle-14+ Lane V dispatches that cite Rule #13.**

### Candidate #3 — Pattern-doc cross-cycle uniformity pass mechanism

- **Refines:** F2 trigger codification (cycle-11+ workflow — when does
  the migration pattern doc trigger a uniformity pass?).
- **N=1 instance, with partial-close history:**
  - Cycle-11 originating: F2 trigger codified (initial threshold ~N=12).
  - Cycle-12 partial close: broad-B implementer's drive-by site listing
    advanced the doc but didn't lift older sites to uniform detail.
  - Cycle-13 partial close (`a3af770`): full enumeration pass at 32
    cumulative V1 production sites; per-site detail uniform.
- **Current N count:** 1.5 (per cycle-13 operator handoff). The full
  enumeration pass at `a3af770` is "third partial-close" rather than a
  discrete second N=2 instance because it's the same pattern (the docs
  uniformity is now caught up, not a new mechanism emerging).
- **Codifiable shape:** Trigger criteria for pattern-doc uniformity
  pass — e.g., "when cumulative sites cross 20 AND per-site detail
  drift exceeds X across more than Y prior pass-windows, the next
  operator-driven Lane A docs slice MUST include a uniformity pass."
  Or alternatively, fold uniformity passes into Lane B implementer
  briefs automatically (cycle-12 broad-B precedent).
- **N=2 emergence criteria:** A FUTURE migration-pattern doc (e.g., a
  new P2-X migration doc in cycle-14+) exhibits the same partial-close
  → drift → full-enumeration-pass pattern. The emergence would
  empirically show the mechanism is doc-class-general, not specific to
  the pydantic-caller pattern. **Watch cycle-14+ for new migration
  pattern docs OR cumulative-site-count thresholds crossed without
  uniformity.**

### Candidate #4 — Rule #12 brief-pattern reference verification

- **Refines:** Rule #12 (brief-level grep-the-writes discipline;
  codified `8ab0bbb`).
- **N=1 instance:** Cycle-12 Lane V #12 OBS-1 — operator's broad-A
  dispatch-claim cited `update_location` in `project_manager.py`
  (P1-3 part 10, `1bc9263`) as Mixed-shape canonical; spec reviewer
  verified the function doesn't exist + the commit is V2 not V1 Mixed-
  shape. Implementer adapted gracefully (no commit damage). Confirmed
  by director-side Lane V #12 dispatch.
- **Current N count:** 1 (cycle-12 originating; unchanged through
  cycle-13 close — operator-driven Lane B activity was zero cycle-13).
- **Codifiable shape:** Extend Rule #12's grep-the-writes requirement
  to brief-pattern REFERENCES (canonical pattern + canonical site SHA)
  in addition to brief-pattern WRITES. The codifier MUST grep-verify
  the named function/symbol exists AT the cited SHA, AND that the
  cited SHA exhibits the named sub-pattern (V1 strict vs. V2 wrap vs.
  Base vs. Mixed-shape). Closes the brief-vs-source divergence at the
  reference layer, not just at the write-site layer.
- **N=2 emergence criteria:** A second brief-vs-source divergence at
  the canonical-site reference layer (operator OR director-authored
  brief cites a function/SHA combination that doesn't exhibit the
  named pattern). **Watch cycle-14+ Rule #14 dispatch-claim events
  citing canonical-site SHAs; ALSO watch director-authored implementer
  prompts citing canonical patterns.**

### Candidate #5 — Rule #13 transitive caller-side audit scope-refinement

- **Refines:** Rule #13 (symmetric-endpoint audit discipline; codified
  `8ab0bbb`). Possible scope-refinement at codification time.
- **N=1 instance:** Cycle-12 Lane V #12 I1 — IMPORTANT-advisory
  ValidationError-swallow at 2 broad-A helper-function caller sites in
  `web_server.py` L2073/L2240. The audit on the helper-function
  migration surfaced caller-side transitive concerns. Operator's
  parallel Lane V #13 transitive audit on broad-B route-handler
  migration (14/15 clean) demonstrates the failure mode is
  STRUCTURALLY SCOPED to helper-function-encapsulated migrations, not
  route-handler-encapsulated ones.
- **Current N count:** 1 (cycle-12 originating; unchanged through
  cycle-13 close).
- **Codifiable shape:** Refine Rule #13 to distinguish "shared state
  touched by a helper function" (broader audit scope; transitive
  caller-side audit needed) from "shared state touched by a route
  handler" (narrower audit scope; the handler IS the audit boundary).
  This is a SCOPE REFINEMENT, not an extension — Rule #13's existing
  language conflates the two.
- **N=2 emergence criteria:** A second helper-function migration with
  transitive caller-side audit value (the broad-A pattern repeats on
  a different domain). ALTERNATIVELY, a route-handler migration where
  the transitive audit IS valuable (counter-example proving the scope
  distinction wrong). Either crystallizes the scope. **Watch cycle-14+
  for helper-function migrations + Rule #13 invocation patterns.**

### Candidate #7 — Carry-forward claim re-verification at handoff inheritance

- **Refines:** CLAUDE.md "Verification discipline for factual claims" §
  (Rule 1 / Rule 2 + ADR-013). Scope extension from "new claims" to
  "inherited claims older than 1 cycle."
- **N=1 instance:** Cycle-14 entry concurrency carry-forward retirement
  (`dbcde8b`). The "concurrency flake"
  `test_four_concurrent_generate_only_one_wins` was characterized in
  cycle-10 carry-forward as "environment-sensitive; not consistently
  reproducible." Handoffs at cycle-10, 11, 12, and 13 each inherited
  this framing without re-running the verifying command (run the test
  in isolation). At cycle-14 entry, isolation runs showed the test had
  been **deterministically failing 10/10** since origin commit
  `a97573e` (2026-05-24, cycle-9). The "flake" framing was false from
  the start; only full-suite execution warmth (prior tests warming
  Flask's request context) masked the timing-window bug. The cycle-13
  handoff even hypothesized "Possibly resolved by cycle-12's broader
  concurrency hardening + test-fixture leak fix" — extrapolating from
  full-suite passes to isolation-mode behavior, which is a Rule 2
  ("scoped output stays scoped") failure pattern applied to *inherited*
  rather than *newly-generated* claims.
- **Current N count:** 1 (cycle-14 entry; cycle-10 originating
  misframing).
- **Codifiable shape:** Extend the existing verification discipline so
  that carry-forward claims inherited from prior-cycle handoffs require
  re-verification at handoff-receipt time before re-assertion in the
  next handoff. Specifically: (a) the inheriting seat runs the
  verifying command before propagating the claim verbatim, OR (b)
  marks the claim "unverified-inherited" with the original handoff's
  SHA as provenance. Re-verification window: an originating handoff
  + the immediate next cycle's handoff are presumed authoritative
  (claim is "fresh"); ≥2 cycles after origin requires explicit
  re-verification at receipt time. Principle: authority and
  verification travel together (per CLAUDE.md §"When you cannot
  comply") — so *inherited* authority requires *fresh* verification or
  explicit demotion to unverified status.
- **N=2 emergence criteria:** A second carry-forward whose claim
  survives ≥2 cycle handoffs unverified, then is found materially
  false (not merely refined) at re-verification. Watch cycle-15+
  carry-forward chains; specifically watch for any current carry-forward
  (RunPod pod state, `web_server.py` LoC, `cinema_pipeline.py` LoC,
  `ScreeningStage.tsx` LoC) whose re-verification at handoff-receipt
  time produces a materially different answer than the inheriting
  handoff asserts. The 4 remaining N=1 candidates above (#1/#3/#4/#5)
  do NOT count as N=2 emergence for #7 — they have explicit re-audit
  cadence baked in (the "cycle-13 audit" section pattern), which
  arguably already satisfies the discipline this candidate would
  codify.
- **Beneficiary (per Rule #11):** `both` seats + `user` (cleaner
  handoff substrate; less wasted investigation time on misframed
  carry-forwards; faster carry-forward retirement when re-verification
  reveals "already-resolved" or "always-was-broken" states).

### Candidate #8 — Rule #4 RECENCY-window refinement (intra-session staleness)

- **Refines:** CLAUDE.md `## State-asserting writes: gate on \`git log --oneline -5\``
  (Rule #4). Scope extension from "pre-Write gate at session-start" to
  "pre-Write gate has a RECENCY-window — re-verify immediately before
  substantive Write if Write happens >30 min after the gate."
- **N=1 instance:** Cycle-14 mid-cycle parallel-draft collision
  (operator's `edae013` testplan + `fdd0094` escalation event +
  director's `68b92d2` decision event resolution; closed via OPTION B
  at brief v0.4 `2006217`). Operator's session started at ~T07:50Z;
  performed cold-start `ls coordination/mailbox/sent/ | tail -3` which
  truncated and missed director's `T05:00:00Z` dispatch-claim event;
  proceeded to draft ~768-line `docs/EXTENSIVE-TEST-PLAN-2026-05-27.md`
  from ~T08:15-08:25Z (substantive Write 25-35 min after cold-start
  `ls`). On finalizing the draft, operator re-`ls`'d mailbox for the
  dispatch-claim filename + **discovered director's T05 event**;
  halted publication; surfaced scope conflict to user; user adjudicated
  "escalate." A re-`ls` immediately before the Write would have caught
  T05 and prevented the parallel-draft.
- **Reinforcing N=1 instance (cycle-14 cursor-write gap):** director's
  `68b92d2` T09 decision event commit body asserted "Cursor advance:
  director `seen/director.txt` advances from `T03:00:00Z` →
  `T08:35:00Z` (consuming operator's escalation event)" but the actual
  filesystem write was missed at commit time. Closed at `ccdc420`
  cursor-fix follow-up commit on user's "check" state sweep
  discovering the discrepancy. Same shape as #1 above (state-assertion
  authored without filesystem-state verification at write-completion
  time) but at a smaller scale.
- **Current N count:** 1 (two cycle-14 instances reinforce the
  primary case but are arguably same-shape; counting as N=1 for
  N=2-floor discipline conservatism per v5.1 R-D-1).
- **Codifiable shape:** Extend Rule #4 with a RECENCY-window clause.
  Specifically: (a) the pre-Write gate (`git log -5` + mailbox `ls`)
  authoritative for ≤30 minutes; (b) substantive Writes happening
  >30 min after the gate MUST re-run the verifying command
  immediately before commit (per Rule #7 pre-commit re-verify), AND
  re-run the gate command immediately before substantive Write-start
  to capture mid-session drift; (c) "substantive Write" = any
  Write/Edit that asserts state about the repo (handoff content,
  cross-seat events, doc-claim with file paths or counts, brief
  content referring to other commits). Mechanical cursor-advance or
  doc-typo fixes are NOT substantive Writes (no re-gate needed).
  Principle: pre-Write gate is a snapshot, not a license — staleness
  accumulates as the session progresses.
- **Distinction from Candidate #7:** failure-mode shape, evidence
  base, remediation, and trigger window all differ — see operator's
  REPLY `a9b1c32` §"Ask #5" for the 5-row distinction table. Folding
  #8 into #7 would lose the distinct intra-session-vs-inter-session
  remediation discipline.
- **N=2 emergence criteria:** A second intra-session mailbox-state-
  staleness incident causing operational error (e.g., another
  parallel-draft collision in a different cycle; OR a director-side
  decision-event ship with cursor-write gap; OR a director-or-
  operator-side ship that asserts state about a recently-modified
  file the seat hasn't re-read). Watch cycle-15+ for similar shapes,
  particularly during high-velocity parallel work where both seats
  ship multiple commits per hour.
- **Beneficiary (per Rule #11):** `both` seats + `user` (prevents
  wasted parallel work; reduces escalation cycles; cleaner audit
  trail for state-asserting writes).

### Cycle-13 audit (cycle-14 entry watchpoint refresh)

Cycle 13 was the **first markdown-only protocol-substrate cycle** (no
new feat/refactor commits triggering Lane V dispatches; only `chore`,
`docs`, `test`, and the `336403d` `fix(web)` M-3 close which received
operator-judgment Lane V skip). **NO movement on any of the 4
candidates in cycle-13:**

- **#1:** 0 new Rule #13 invocations cycle-13. N=1 unchanged.
- **#3:** Cycle-13 `a3af770` added a partial-close but candidate stays
  at N=1.5; no new pattern-doc mechanism emergence.
- **#4:** 0 new operator-driven Lane B dispatch-claim events
  cycle-13 (cycle-13 was markdown-only). N=1 unchanged.
- **#5:** 0 new Rule #13 invocations cycle-13. N=1 unchanged.

**Next operator-seat OR director-seat session should re-audit at
cycle-14 close** when new Lane V dispatches OR new brief activity
crosses one of the N=2 emergence criteria above. Per Rule #14 +
Rule #15 codification cadence (v5.2 + v5.3 shipped same cycle once
N=2 accumulated), the v5.4 ship can happen quickly once the first
candidate crosses.

### Cycle-14 mid-cycle audit (substrate work per user direction "n=2")

Cycle 14 is in-progress at audit-write time. Mid-cycle re-audit
during director's substrate work covers: cycle-13's open candidates
(#1, #3, #4, #5) + cycle-14's new candidate (#7).

- **#1 (Rule #13 wording precision):** 0 new Rule #13 invocations
  cycle-14 mid-cycle (no Lane V dispatches; the cycle-14
  `dbcde8b` retirement was direct code work, not an audit-with-
  disposition). N=1 unchanged.
- **#3 (Pattern-doc uniformity pass mechanism):** 0 new migration
  pattern docs cycle-14. Only the pydantic-caller pattern doc
  exists; no P2-X migrations have started. N=1.5 unchanged.
- **#4 (Rule #12 brief-pattern reference verification):** 0 new
  operator-driven Lane B dispatch-claim events cycle-14 (mid-cycle;
  no operator Lane B activity). Director-side commit-body SHA
  citations during cycle-14 (cinema_pipeline.py LoC drift, cycle-13
  handoff misframing) reference commits accurately; no
  brief-pattern reference divergence. N=1 unchanged.
- **#5 (Rule #13 transitive caller-side audit scope-refinement):**
  0 new helper-function migrations cycle-14. N=1 unchanged.
  **Significant empirical inverse evidence already in hand from
  Lane V #13** (cycle 12, `7472d31..a0493dc`): operator's
  high-leverage transitive-audit on broad-B's 15 route-handler-
  direct sites returned 14/15 clean (the 1/15 was a brief-OOS
  thread-swallow site, not a transitive-audit miss). This inverse
  evidence is N=1 strength but empirically distinct from N=2
  same-shape evidence. **v5.4 codification could legitimately
  scope-refine to "helper-function-encapsulated migrations only"
  without a second helper-function-positive instance, if the
  next proposal-cycle director judges the inverse evidence
  load-bearing.** Director-discretion decision for v5.4+ proposal
  cycle.
- **#7 (Carry-forward claim re-verification at handoff
  inheritance) — NEW cycle-14:** Filed at `a76d881` during cycle-14
  substrate work. N=1 instance: concurrency flake operational
  carry-forward retired at `dbcde8b` (cycle-14 entry) after 4-cycle
  inheritance (cycle-10 → 14). **Scope clarification surfaced
  during cycle-14 POST-ROADMAP refresh (`69202da`):** state-of-
  affairs LoC claims (cinema_pipeline.py 1203 inherited 4 cycles
  in POST-ROADMAP doc cycle-9 → cycle-13 unchanged; web_server.py
  2406 inherited 1 cycle in cycle-13 handoff; ScreeningStage.tsx
  720 inherited 1 cycle in cycle-13 handoff) drifted from actual
  values (1238 / 2579 / 711). **These drifts are Rule #1 violations
  (claims without verification output), NOT Candidate #7 instances
  per scope clarification.** Candidate #7's scope is *operational
  carry-forwards* (open tasks / open decisions / open hypotheses
  about WORK), not state-snapshot claims about file contents. The
  fix-pattern differs: Rule #1 enforcement = "run the verifying
  command before stating the count"; Candidate #7 discipline =
  "re-investigate the underlying task before propagating its
  framing forward through handoffs." Different remediation =
  different scope. N=2 watch criterion for #7 stays "operational
  carry-forward whose claim survives ≥2 cycle handoffs unverified,
  found materially false at re-verification."

**Net N=2 status across all 5 candidates: NONE emerged cycle-14
mid-cycle. No v5.4 ship-candidate ready.** Substrate is stable;
codification discipline (N=2 floor) holds. **Director-discretion
opening:** Candidate #5's inverse-evidence pattern could justify
v5.4 ship at N=1+inverse if a future proposal-cycle director
judges the empirical strength load-bearing. Otherwise: continue
N=2 watch through cycle-15+.

**Next re-audit at cycle-14 close** (next director's handoff doc or
next operator's re-audit; whichever ships first). Re-audit cadence
mid-cycle is OPTIONAL — established cadence is at cycle-close, but
cycle-14 mid-cycle audit was triggered by user direction "n=2"
during ongoing substrate work and produced this subsection.

### Candidate #9 — Rule #19 mitigation (d): current_task describes ACTIVITY, not cached volatile shared-state

- **Refines:** Rule #19 (live-presence-over-inferred-idle; codified `cec6d72`).
  Rule #19's existing `current_task`-rot guard (CLAUDE.md ~:1873-1879) targets the
  OPPOSITE failure — `current_task` UNCHANGED / semantically stale. This candidate
  covers the inverse: a `current_task` that DID change (fresh file, fresh `updated`)
  yet embeds a STALE volatile value.
- **N=1 instance:** 2026-06-09 (post-portrait-arc; both seats live in parallel via
  user "continue as operator" / "continue as director"). `director.md current_task`
  — fresh (status:active, `updated` within seconds) — embedded TWO stale volatile
  claims: "director 0 unread (cursor 00:53:45Z)" (actually ≥1 unread; verified live
  via `status.py mailbox-unread director`) AND "operator 3 unread (offline)"
  (operator was LIVE at 0 unread — the exact inferred-idle error Rule #19 set out to
  kill, re-introduced by caching the PEER's liveness into one's OWN `current_task`).
  Surfaced by operator; ping `2026-06-09T04-42-44Z-operator-to-director-coordination.md`.
- **Current N count:** 1 (originating 2026-06-09).
- **REALIZED-HARM emergence criterion (the N=2 trigger):** a SECOND instance where a
  seat takes a **wrong action** off a peer-status or count value frozen into presence
  prose — NOT merely a stale value that caused no action (this session's harm was
  latent only: the operator caught it before any mis-action). Latent stale values
  alone do NOT advance N.
- **Codifiable shape (when N=2):** a single principle-clause as Rule #19 mitigation
  (d) — NOT an enumerated-list ban (which rots; the next volatile quantity not on the
  list slips through): *"current_task describes THIS seat's own ACTIVITY; never assert
  the peer's liveness or freeze any volatile shared-state value (unread N, ahead/behind)
  — recompute those live at read-time."* Actionable only once live-recompute is cheap;
  that prerequisite is now satisfied (`status.py mailbox-unread <seat>`, shipped `3fa29c9`).
- **Beneficiary (Rule #11):** both (symmetric — either seat can freeze a stale
  count / peer-status into its own `current_task`).
- **Provenance:** protocol-upgrade analysis workflow `wf_9c032336-468` (operator,
  2026-06-09); the adversarial-critique pass downgraded this from "codify-now" to
  N=1-file per the N=2 floor, explicitly resisting bundling it with the (distinct,
  computation-not-caching) instrument candidate to manufacture N. (The dated
  "across all 5 candidates" net-status note above is a cycle-14 snapshot, left as
  historical; this is candidate #9.)

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
| v5.8 per-seat index auto-refresh | `.claude/hooks/update-state.sh` `_sync_seat_index()` | [docs/PROPOSAL-protocol-bundle-v5.8-2026-06-08.md](PROPOSAL-protocol-bundle-v5.8-2026-06-08.md) | `454e770`+`a614f68` impl + _v5.8 text-ship_ |

### v5.8 — per-seat index auto-refresh (D-a hardening), 2026-06-08

**Mechanism:** `update-state.sh::_sync_seat_index()` fast-forwards a seat's
stale `GIT_INDEX_FILE` to HEAD on peer-commit staleness, called BEFORE the
shared skip-perf gate (the committing seat advances the shared `.last-state-head`
marker first, so gating behind it would skip the sync exactly when needed).
`git read-tree` fires in exactly one case (C1: index byte-equals the
last-synced commit's tree, no staged work) — staged-WIP loss excluded by
construction; the mixed case (C2: staged work + peer commit) stays manual
(`git read-tree -m`).

**Empirical basis:** D-a stale-index phantom-deletion storms ~4×/session on
2026-06-07 (peak 1015 status lines; one 600-file skip-worktree-bit variant;
director hit a 254-file storm independently). The manual `git read-tree HEAD`
workaround (memory `feedback_da_stale_index_refresh`) was failure-prone.

**Beneficiary (per Rule #11): `both`** — symmetric; both seats' indexes are
maintained, both lose the manual-resync chore. Operator drafted (PROPOSAL +
dispatch-claim `03fc21d`, Rule #14 operator-driven Lane B); director reviewed
the implementation independently (Rule #9 parallel pass — safety property
verified, 7 awk-extraction tests guarding the real function, suite 1723 green)
→ CONSENT; director ships the protocol text per Sh partition.

**SHAs:** impl `454e770` (+ Lane V minor-fold `a614f68`: atomic marker write
via tmp+`mv -f`, C2/D residual comment); operator Lane V ✅ READY / 0-blocking
at `31d5c96` (the one IMPORTANT was a false positive, disproven by branch
coverage). Text-ship _v5.8 (this commit; filled next session-close per
chicken-and-egg precedent)_. Working criteria C1-C4 in PROPOSAL §4 (dogfood at
v5.9/retro: zero storm reports in next 2 sessions; any staged-WIP-loss incident
= immediate revert).

**Process note (self-modification gate):** edits to
`.claude/hooks/update-state.sh` are an *agent-loaded hook* — the harness
auto-mode classifier treats them as self-modification and **gates them on USER
authorization per session** (peer-seat concurrence does NOT substitute).
Observed when the operator's Lane A fold to the hook was blocked until
user-authorized via AskUserQuestion. Future seats touching this hook should
expect the gate.

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

### R-SKILL — project-skill load triggers (2026-06-12, operator ship)

**Mechanism:** CLAUDE.md/AGENTS.md rule block — invoke `comfyui-mastery`
before authoring/reviewing/debugging ComfyUI graph code or JSON, and
`ai-video-gen` before pipeline-level video-generation design work; when a
skill prior shapes a verdict, name it in the work product.

**Empirical basis:** the 2026-06-11 S2 dual-PuLID GO/NO-GO verdicts were
shaped by comfyui-mastery priors (PuLID documented single-face → identity
blending is the expected dual-chain failure mode → the both-arcs>0.70
criterion; `ApplyPulidAdvanced.attn_mask` region mask became the recorded
Pass-B direction). The priors only entered the review because the operator
happened to have the skill loaded — the user asked whether both seats use it
(2026-06-11); operator offered codification; user approved 2026-06-12
("proceed with recommendation"). Shipped with the same commit: the skill's
integration section re-synced against live code (pulid.json 15→22 nodes incl.
PAG + RealESRGAN hires chain; RunPod RTX 4090 → Novita RTX 6000 Ada
host-agnostic; production parameter table re-snapshotted from
`WORKFLOW_TEMPLATES`; `pulid_max.json` max tier documented).

**Beneficiary (per Rule #11): `both` seats + user** — verdicts grounded in
documented node semantics rather than recall, on both authoring and reviewing
sides.

### Rules #21 + #22 + R-MEASURE + dispatch git-hygiene + SessionStart sweep (2026-06-12, operator ship, user-directed)

One user-directed hardening batch ("plan to apply these", 2026-06-12) of four
items surfaced by the 2026-06-11/12 sessions; plan
`docs/superpowers/plans/2026-06-12-two-seat-process-hardening.md`:

- **Rule #21 verdict-ahead-of-report** — basis: `6f3b809` verdict-first
  unblocked a billed pod session; report `3a13156` followed; nothing
  reversed. Beneficiary (Rule #11): both + user (billed-clock waste removed).
- **Rule #22 flag-before-burn** — basis: reviewed S3 sweep ran clean;
  unreviewed train script carried the F1 fee-respend defect (`3a589da`
  guard). Beneficiary: both + user (fee protection).
- **R-MEASURE** — basis: half-crop S2/S3 verdict numbers were REPL-only
  (operator Lane V `2026-06-11T18:49:37Z`, disposed `b91c6c9`; halves-mode
  scorer queued wave-2 is the instance). Beneficiary: both + user
  (reproducible records).
- **Dispatch git-hygiene (templates + CLAUDE/AGENTS clause)** — basis:
  index-operator corruption 2026-06-12 ("unable to read <blob>") during a
  31-agent workflow; per-invocation `env -u GIT_INDEX_FILE` (subagent shell
  state does not persist). Beneficiary: both (either seat's index).
- **SessionStart sweep registration** — closes the v5.9 post-last-hook-fire
  window (strike #2, 866 paths). Local registration documented in
  OPERATIONS.md. Beneficiary: both.

All five invocable from codification; invocation counts start at the next
session table.

## 2026-06-13 addendum — R-VERIFY-TIER (capacity audit `wf_6be2ee18-f4b`)

- **R-VERIFY-TIER** — caps verification DEPTH where R-EVIDENCE / Rule #9 only ever
  raised it. (A) doc-only deferred-defect notes converge at TWO independent seats
  (a Rule #23 co-sign counts as one); a 3rd pass requires a stated new question.
  (B) agent-confirmed unfixed defects ship a `pytest.mark.xfail(strict=True)` pin
  or a `test-infeasible` label in the same session. Empirical basis: the §8.5
  char-landscape note drew ~25–31 Sonnet agent-runs across 4 adversarial passes
  (`wf_73f95c8c` / `wf_e09bded6` / `wf_5d39bbe3` / `wf_ed13f2b4`) for one doc
  paragraph + 0 fix lines. Beneficiary: both (frees agent-cycles for the deliverable).
  Consent: principal-directed (capacity audit, 2026-06-13). Does NOT relax
  production-code verification — Lane V / Rule #9 per-commit checks unchanged.
  Note: this is the corpus's first depth-CAP rule; it reduces protocol work.

## 2026-06-14 addendum — Rule #23 async-split (Lever #7, capacity audit `wf_6be2ee18-f4b`)

- **Rule #23 co-sign classifier** — splits the single "both directors' sign-off"
  obligation into two tiers so an awareness heads-up no longer serializes behind a
  full session. Classifier: *would the co-signer's verification change which
  files/sites the implementation touches?* **Tier A** (yes, implementation-scope-
  determining): co-signer lands a mailbox `verification-report` BEFORE dispatch —
  async-fulfillable via workflow+mailbox, no session restart. **Tier B** (no,
  awareness-only): `-to-all-` heads-up, 48h proceed-if-no-objection. Empirical
  basis: the char-landscape co-sign was Tier A and caught a 4K-drop + silent-audio
  regression the brief's caller-grep missed; the determinism-siblings ACK was Tier B
  and round-tripped in <10min. Body in four-seat-extension.md §6. Beneficiary: both
  (unblocks cross-pair throughput without weakening scope-determining review).

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

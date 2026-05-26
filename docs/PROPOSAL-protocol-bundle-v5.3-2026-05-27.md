# Protocol Bundle v5.3 — Proposal (Operator Draft for Director REPLY-Cycle)

**Authored:** Operator session, 2026-05-27 — drafted at user direction
("2" referring to cycle-13 backlog item #2 "v5.3 proposal cycle for
candidate #6 now at N=2") at HEAD `a3af770` (cycle-13 F2 pattern-doc
uniformity pass).
**Authority basis:** v5 §"Strategic-seat-default" lane allows operator-
seat to draft codifications (director-seat ships); user direction
authorizes this draft cycle explicitly. Restores v2-v4 operator-drafts/
director-ships precedent after v5/v5.1/v5.2 director-drafts inversions.
R11 beneficiary annotation below resolves to `both` seats — no
asymmetric-veto path needed; explicit consent per v5.1/v5.2 precedent.
**Ship strategy:** Single commit, single rule. Race-ack body if state
moves during ship.
**Estimated implementation effort:** ~15-25 min (mirrors v5.2 scope;
narrow: 1 new rule + rule-registry update + beneficiary snapshot
update + 2 edit anchors in CLAUDE.md/AGENTS.md). Markdown only.
**Blocks:** None. v5.3 is additive over v5.2 — nothing currently
working breaks; existing 14 rules preserved.
**State at draft time:** HEAD `a3af770` (cycle-13 F2 uniformity pass).
Branch synced with `origin/main` (0 ahead / 0 behind). Working tree
clean (modulo this proposal pending add+commit); mailbox empty both
directions (director cursor `2026-05-27T03:00:00Z`; operator cursor
`2026-05-27T03:00:00Z` post-cycle-12 closure REPLY consumption).
pytest 866 / 3 skipped baseline preserved through cycle-13 entry.

---

## TL;DR (60 seconds)

**One new discipline rule promoted to codification at N=2 application.**
Cycle-12 produced N=1 evidence (`442e154` — director closes operator's
Lane V #12 I1); cycle-13 entry produced N=2 (`336403d` — director closes
operator's Lane V #13 M-3). Rule formalizes the cross-seat extension of
the long-standing fix-on-own-findings convention (N=9 cumulative
pre-cycle-12).

| # | Rule | Trigger evidence | Beneficiary (R11) |
|---|---|---|---|
| **15** | **Cross-seat fix-on-received-findings convention.** When one seat's Lane V verification surfaces a finding requiring code fix, the OTHER seat may close it via standalone `fix:` commit. Operator's `verification-report` event MAY include a structured 3-option disposition recommendation (fold / standalone fix / no action); receiving seat chooses based on timing + scope. Commit subject MUST reference the originating Lane V # + finding ID. | N=1: `442e154` (cycle-12) — director closes operator's Lane V #12 I1 (IMPORTANT-advisory severity; ValidationError-swallow at broad-A helper caller sites; option 2 chosen — operator's recommended option 1 (fold into broad-B brief) was foreclosed by parallel-execution timing). N=2: `336403d` (cycle-13 entry) — director closes operator's Lane V #13 M-3 (MINOR DEFER severity; thread-swallow observability hardening via `logger.error` + `exc_info=True`; option 2 chosen for the DEFER-categorized finding ~30min after v5.2 ship). | **both** seats |

**Beneficiary symmetry rationale:** Rule #15 enables both seats
(codifies the cross-seat closure mechanism that previously operated
ad-hoc) AND constrains both seats (formalizes the disposition + commit-
body convention). The mechanism is bidirectionally symmetric — operator
MAY close director-flagged findings via the same shape, even though
N=0 instances of that direction exist (operator-side dispatch of Lane
V on director-driven work is the documented Lane V #10 / #11 / #12 /
#13 dispatch shape; director-side dispatch of Lane V on operator-
driven work is cycle-12's dual Lane V #13 demonstration). Both seats
symmetric on both axes → `both`.

**No other rules codified in v5.3.** Four N=1 candidates from cycles
11-12 remain filed for v5.4+ codification when N=2 accumulates:
- #1 Rule #13 wording precision (audit-completeness vs audit-disposition; cycle-11 Lane V #10 nuance)
- #3 Pattern-doc cross-cycle uniformity pass mechanism (cycle-11 F2 trigger; partially closed cycle-12 via broad-B implementer drive-by + cycle-13 `a3af770` full enumeration pass)
- #4 Rule #12 brief-pattern reference verification (cycle-12 Lane V #12 OBS-1; operator's `update_location`/`1bc9263` mis-attribution)
- #5 Rule #13 transitive caller-side audit scope-refinement (cycle-12 Lane V #12 I1 + operator's broad-B audit demonstrating route-handler vs helper-function distinction)

Filing all 4 for v5.4+ codification when N=2 accumulates.

No new mechanisms / mailbox kinds / file additions. Pure rule
addition. Working criteria for measurability included.

---

## Why (motivation)

### The convention is already in practice

Cross-seat fix-on-received-findings has been the de-facto convention
since cycle-12; codifying makes the discipline auditable + observable.

**Pre-codification empirical history:**

| SHA | Date | Cycle | Who flagged | Who closed | Finding | Severity |
|---|---|---|---|---|---|---|
| `442e154` | 2026-05-27 | cycle-12 | operator (Lane V #12) | director | I1: ValidationError-swallow at broad-A helper caller sites | IMPORTANT-advisory |
| `336403d` | 2026-05-27 | cycle-13 entry | operator (Lane V #13) | director | M-3: L691 thread-swallow observability | MINOR DEFER |

**Different qualitative contexts:**

- **Severity range:** IMPORTANT (`442e154`) → MINOR DEFER (`336403d`).
  Spans the actionable severity spectrum.
- **Timing range:** mid-cycle close ~minutes after Lane V report
  (`442e154`) → cross-cycle close ~half day after Lane V report
  (`336403d`). Spans intra-cycle vs cross-cycle execution shapes.
- **Disposition route:** operator's 3-option recommendation respected
  in both cases; option 2 chosen in both (different reasoning —
  parallel-execution timing in N=1; explicit-DEFER categorization in
  N=2).
- **Finding lifecycle:** N=1 closes mid-cycle (DEFER never fully
  applied); N=2 closes post-cycle-close (DEFER explicitly accepted
  by operator, then closed by director ~half day later as "future
  hardening pass").

The two instances span the convention's full operational shape. N=2
codification is justified per the v5.1 R-D-1 + v5.2 R11 N=2-floor
discipline I myself argued for at v5.2 REPLY Q6 — and which director
folded affirmatively at v5.2 ship.

### Why this isn't just an extension of fix-on-own-findings

Fix-on-own-findings (N=9 cumulative pre-cycle-12) is one seat closing
their own surfacing — operator dispatches Lane V on operator's own
commit; finds something; folds the fix in a follow-up commit. The
finding's origin + closure are within one seat's context.

Cross-seat fix-on-received-findings introduces:

1. **Mailbox-routed disposition.** The finding travels via
   `verification-report` mailbox event from one seat to the other.
   Rule #8 mailbox authority applies — the event obligates the
   receiving seat to act per its content.

2. **3-option disposition recommendation shape.** Operator's
   `verification-report` includes a structured disposition with
   options (a) fold / (b) standalone fix / (c) no action. Director
   reads + chooses. This is new — fix-on-own-findings has no
   disposition mechanism because one seat owns both ends.

3. **Parallel-execution timing risk.** In parallel-execution cycles
   (cycle-12 was the first), operator's option (a) "fold into
   adjacent work" may be foreclosed by adjacent work landing during
   the disposition window. `442e154` body explicitly acknowledged:
   "Operator-recommended Option 1 (fold into broad-B's brief) was
   missed due to broad-B's implementer commit landing during Lane V
   #12 dispatch window." Operator MUST always provide option (b)
   "standalone fix" as fallback. This is new — fix-on-own-findings
   has no parallel-execution timing concern.

4. **Commit-body convention.** Cross-seat fix commits MUST reference
   the originating Lane V # in commit subject + cite the operator's
   disposition recommendation in commit body. This is new — fix-on-
   own-findings has weaker referential convention.

5. **Audit-trail discipline.** Cross-seat closures form a verifiable
   chain across the mailbox + git log: operator's Lane V report (in
   mailbox + verification-report event) → operator's disposition →
   director's option choice (in commit body) → director's fix commit
   (in git log). Anyone can reconstruct the chain post-hoc. Fix-on-
   own-findings has a simpler chain (own seat's report → own seat's
   fix commit).

These 5 differences are why fix-on-received-findings deserves its own
rule (rather than being a subsection of fix-on-own-findings or an
implicit-from-Rule-#9 extension).

### What changes if v5.3 ships

For operator-seat (closing-direction):
- A codified mechanism to close director-flagged findings via the
  same shape (operator dispatches own Lane V on director-driven work
  per Rule #9 §"Parallelism"; director surfaces a finding via
  director's `verification-report` event; operator closes via
  standalone `fix:` commit citing director's original finding).
- N=0 instances of this direction exist yet; codification establishes
  the bidirectional shape so it's available when needed.

For operator-seat (flagging-direction):
- A codified disposition shape for Lane V reports — 3-option (a) fold
  / (b) standalone fix / (c) no action. Operator may continue using
  this shape (matches cycles-12-13 practice).
- Working criteria for when option (a) is foreclosed by parallel-
  execution timing → must always offer option (b) fallback.

For director-seat (closing-direction):
- A codified mechanism for closing operator-flagged findings via
  standalone `fix:` commit when fold-into-adjacent-work is foreclosed.
- Commit subject convention: "close Lane V #N <finding-ID>"
  (mirrors cycle-12/13 commit subjects).

For director-seat (flagging-direction):
- Bidirectional symmetry available when director-seat dispatches own
  Lane V on operator-driven work + finds something.

For user-principal:
- Cleaner audit trail of cross-seat closures. The mailbox + git log
  chain is reconstructable; user can verify any cross-seat closure's
  full lifecycle.

For the substrate:
- Formalizes a convention that worked twice without it. Future cross-
  seat closures cite Rule #15 + use the structured disposition shape,
  making the convention self-documenting at invocation time.

---

## Rule #15 specification (proposed)

**Rule #15: Cross-seat fix-on-received-findings convention.**
*(Subtitle: when one seat closes the other seat's Lane V finding.)*

When one seat's Lane V verification surfaces a finding requiring code
fix, the OTHER seat MAY close it via standalone `fix:` commit. The
mechanism is bidirectionally symmetric (operator-closes-director-flagged
OR director-closes-operator-flagged), though only operator-flagged-
director-closes instances exist at codification time.

### Disposition recommendation shape (flagging seat)

When the flagging seat sends a `verification-report` event with a
finding requiring fix, the report MAY include a structured 3-option
disposition recommendation:

- **(a) Fold into adjacent in-flight work** (if applicable). The
  receiving seat folds the fix into the next-natural commit in their
  in-flight work.
- **(b) Standalone fix commit.** The receiving seat ships a separate
  `fix:` commit closing the finding.
- **(c) NO ACTION (informational only).** The finding is recorded for
  audit but doesn't require fix (e.g., cosmetic, doesn't affect
  correctness).

Recommendation: provide all 3 options when applicable. **Option (b)
MUST always be available as fallback** because (a) may be foreclosed
by parallel-execution timing (the receiving seat's adjacent work may
ship during the disposition window).

### Receiving seat's response (closing seat)

The receiving seat reads the disposition + chooses an option based on
timing + scope:

- **Timing.** If (a)'s adjacent work has already shipped, (b) is the
  fallback. If (a)'s adjacent work is in-flight + the fold-in is
  cheap, (a) is preferred. If (a) is not applicable, (b).
- **Scope.** If the fix is sub-2-LoC + literal mechanical change, (a)
  is preferred (less commit-churn). If the fix is structural OR
  spans multiple files, (b) is preferred (clean diff per concern).
- **Severity.** INFORMATIONAL-only findings → (c) is acceptable.
  Anything actionable → (a) or (b).

The receiving seat's option choice is binding once committed; rollback
requires another REPLY cycle (or escalation to user).

### Commit-body convention (closing commit)

Cross-seat fix-on-received-findings commits MUST follow these
conventions:

1. **Commit subject:** reference originating Lane V # + finding ID.
   - Format: `fix(<scope>): close Lane V #N <finding-ID> — <one-line summary>`
   - Examples: `fix(web): close Lane V #12 I1 — discriminate ValidationError from ValueError`; `fix(web): close M-3 — use logger.error with stack trace at api_train_lora::_runner exception handler`

2. **Commit body:** cite operator's disposition recommendation + note
   which option (a/b/c) was chosen + brief why.

3. **Race-ack body:** standard per Rule #5 + #7. Note any state shift
   during the close-loop window.

4. **Co-Authored-By trailer:** standard per system prompt.

### Audit-trail discipline

The full lifecycle of any cross-seat closure is reconstructable from:

- **Mailbox archive:** operator's `verification-report` event with
  the finding + disposition recommendation.
- **Git log:** receiving seat's `fix:` commit with subject + body
  referencing the originating Lane V + finding ID.
- **(Optional) Next operator Lane V:** if the flagging seat dispatches
  a follow-up Lane V on the closing commit, that report verifies
  closure quality (cycle-12 I1 was NOT re-Lane-V'd because broad-B
  was the next Lane V eligible commit which transitively audited the
  fix; cycle-13 M-3 was NOT re-Lane-V'd because mechanical scope +
  small).

Working criterion: the audit-trail must be reconstructable from
public artifacts (mailbox + git log) WITHOUT requiring the original
session's context.

### Working criteria (dogfood for v5.3)

Per v5.1's working-criteria precedent (R-D-1 refinement) + v5.2's per-
instance wall-clock measurable framing (R-Q5-1 refinement), v5.3
codifies working criteria for Rule #15 invocation:

- **C1: Cross-seat fix commit subject cites Lane V # + finding ID.**
  Measurable per-commit via grep: `git log --oneline --grep='close Lane V'`.
  N=2 instances ALREADY satisfy this (`442e154` + `336403d`).

- **C2: Operator's verification-report event includes 3-option
  disposition when fix is required.** Measurable per-event via
  mailbox-archive inspection. N=2 instances ALREADY satisfy this
  (Lane V #12 report at `coordination/mailbox/sent/2026-05-27T02-30-
  00Z-operator-to-director-verification-report.md` + Lane V #13 report
  at `2026-05-27T03-00-00Z-operator-to-director-verification-report.md`).

- **C3: Receiving seat's commit body cites disposition option choice.**
  Measurable per-commit via commit body grep. N=2 instances ALREADY
  satisfy this (`442e154` body acknowledges option 1 foreclosed →
  option 2 chosen; `336403d` body explicitly closes the DEFER M-3
  via standalone fix).

- **C4: Cross-seat closure completes within ~1 session OR explicit
  cross-cycle DEFER acknowledgment.** Per-instance wall-clock
  measurable. N=1: ~minutes (intra-cycle); N=2: ~half day (cross-
  cycle DEFER-acknowledged). Both within criterion.

Per the v5.2 R-Q5-1 precedent (concrete-measurable replaces "ZERO"/
"X%" framings), the criteria above are per-instance verifiable from
public artifacts; cumulative roll-up across instances becomes a
secondary v5.4+ retrospective metric.

### Beneficiary (per R11)

**Beneficiary: both** seats.

Rule #15 enables both seats (codifies a cross-seat closure mechanism
that previously operated ad-hoc) AND constrains both seats (formalizes
the disposition + commit-body convention). The mechanism is
bidirectionally symmetric — operator MAY close director-flagged
findings via the same shape, even though N=0 instances of that
direction exist (codification establishes the shape for when needed).

No asymmetric-beneficiary veto path needed per R11. Standard proposal
cycle: this proposal + director REPLY + ship (potentially folding
refinements).

**Cumulative R11 beneficiary distribution if v5.3 ships:**
- 8 both / 2 user / 3 operator-seat / 2 director-seat = **15 rules**
- (was 7/2/3/2 = 14 at cycle-12 close, post-v5.2 ship)
- Rule #15 raises `both` count to 8; third consecutive bundle to
  add a `both`-beneficiary rule (v5.1 was 2 director-seat; v5.2
  was 1 `both`; v5.3 is 1 `both`). Asymmetric lean returns toward
  neutral. The retroactive R11 analysis empirically disproving
  "director codifies rules favoring director-seat" bias hypothesis
  (v5 cycle-12 close: 6 both / 2 user / 3 operator-seat / 2 director-
  seat) is further reinforced by v5.3's `both` annotation.

---

## Advisory observations (no codification this bundle)

Four N=1 candidates surfaced at cycles 11-12 are NOT codified in v5.3.
Filed for v5.4+ when N=2 instances accumulate.

| # | Candidate | Source | Status |
|---|---|---|---|
| 1 | Rule #13 wording precision (audit-completeness vs audit-disposition) | Lane V #10 nuance on CINEMA_AUTO_APPROVE_MOTION | N=1; await N=2 |
| 3 | Pattern-doc cross-cycle uniformity pass mechanism | F2 trigger cycle-11; partially closed cycle-12 via broad-B implementer's pattern-doc append + M-cluster closure; cycle-13 `a3af770` full enumeration pass | N=1.5 (multiple partial-closes, not yet a discrete N=2 codifiable instance); await codifiable refinement instance |
| 4 | Rule #12 brief-pattern reference verification | Operator's `update_location`/`1bc9263` mis-attribution at Lane V #12 OBS-1 | N=1; await N=2 |
| 5 | Rule #13 transitive caller-side audit scope-refinement | Lane V #12 I1 (helper-function-encapsulated migration; failure mode reproduces) + operator's broad-B audit (route-handler-direct migration; failure mode does NOT reproduce) — empirically demonstrates scope-refinement direction | N=1 with scope-direction empirical signal; await N=2 codifiable refinement instance |

**Rationale for filing rather than codifying:**

- v5.1 + v5.2 precedent: single-rule codification at N=2 instance.
  Sparse-codification (4 refinements at N=1) creates a precedent
  that the N=2 threshold is squishy; v5.3 preserves the threshold's
  clarity by codifying ONLY the candidate that meets it.
- Candidate #3 is a borderline case (N=1.5 with multiple partial-close
  instances) — could be argued either way. Conservative call: defer
  until a single-instance codifiable refinement crystallizes.
- N=1 candidates may evolve before N=2 lands: candidate #5's scope-
  refinement direction is partial empirical signal that codification
  at N=2 will be better-informed by.

If multiple candidates reach N=2 in the same cycle (cycle-14+), those
can ship together as a multi-rule v5.4 bundle. Until then, single-
rule v5.3 is the cleaner shape.

---

## Open questions for director REPLY-cycle

**Q1 (disposition options shape):** Rule #15 currently says operator's
verification-report MAY include the 3-option disposition. Should this
be MUST (mandatory for actionable findings) OR continue as MAY
(operator discretion)? Empirical data: cycle-12/13's 2 instances both
INCLUDED the 3-option disposition; no counter-example exists.
**Recommendation:** keep as MAY for now; promote to MUST at v5.4+ if
counter-example emerges (an operator-flagged actionable finding without
disposition).

**Q2 (severity-vs-option matrix):** Should Rule #15 specify recommended
mappings between finding severity and option choice? E.g.,:
- CRITICAL → option (b) standalone fix; never option (a) fold (risk of
  burying the fix)
- IMPORTANT → option (a) preferred if fold-able; else (b)
- MINOR → either (a) or (b) per scope
- INFORMATIONAL → option (c) NO ACTION acceptable

**Recommendation:** add an advisory mapping as guidance, NOT as
binding rule. Receiving seat retains discretion.

**Q3 (commit subject format strictness):** Rule #15 currently mandates
"reference originating Lane V # + finding ID" in commit subject but
gives 2 example formats. Should one format be canonical (strict
adherence) OR are both example formats acceptable variants? E.g.:
- Strict: `fix(<scope>): close Lane V #N <finding-ID> — <summary>`
- Loose: any format that includes Lane V # + finding ID

**Recommendation:** loose format; the substantive requirement is
the reference exists. Strict format adds ceremony without significant
audit-trail improvement.

**Q4 (bidirectional symmetry codification at N=0 for one direction):**
The proposal codifies the operator-closes-director-flagged direction
even though N=0 instances exist. Should the rule explicitly cover
this direction OR defer the operator-closes direction to v5.4+ when
N=1 emerges? **Recommendation:** explicit bidirectional codification
NOW. Cycle-13's dual Lane V #13 demonstrated the structural shape;
director-side findings are equally possible. Codifying both directions
at the same time avoids retroactive scope-creep at v5.4+.

**Q5 (working-criteria C4 cross-cycle DEFER acknowledgment):**
Criterion C4 says "completes within ~1 session OR explicit cross-cycle
DEFER acknowledgment." `336403d` closed an explicit DEFER finding ~half
day after Lane V #13 report; the closure was the "future hardening
pass" promised by the DEFER. Is "explicit cross-cycle DEFER
acknowledgment" the right framing OR should there be an upper-bound
wall-clock (e.g., "≤3 cycles post-DEFER")? **Recommendation:** keep
as "explicit acknowledgment" framing — DEFER findings may legitimately
take many cycles (e.g., backlog items waiting on dependencies).
Upper-bound wall-clock would force premature closure.

**Q6 (telemetry tracking separation):** v4.1 cumulative telemetry
counts dispatches + tokens + findings + hallucinations. Should Rule
#15 instances be counted as a separate metric (cumulative fix-on-
received-findings count alongside cumulative fix-on-own-findings
N=9)? Or rolled into a single "fix-following-Lane-V" count?
**Recommendation:** separate tracking for ≥2-3 cycles, then merge
if no operationally-relevant difference emerges. Separate-tracking
costs ~zero overhead + preserves the distinction's audit value.

---

## v5.3 ship criteria

The v5.3 bundle is ready to ship when:

- Director REPLY received (per v5 disagreement protocol)
- All open questions addressed (director-side refinements OR explicit
  silent-accept)
- R11 beneficiary check: `both` confirmed by both seats (no veto path
  needed, but explicit consent is the v5.1/v5.2 precedent for
  cleanliness)
- Rule #15 specification + working criteria reviewed for internal
  consistency

Estimated ship-cycle: 1-2 cycles (this draft → director REPLY in
their next session → ship in cycle-13+ post-REPLY).

---

## Race-ack (Rule #5 + #7)

**State at write-start:** HEAD `a3af770` (my own F2 uniformity pass;
cleanest possible base for a v5.3 proposal since it's mid-cycle-13
post-cleanup). 0 ahead / 0 behind `origin/main`. WT clean. No
concurrent director activity expected (director's last commit was
`336403d` ~30min before my F2 pass; cross-cycle proposal cycle is
the natural next step).

**Pre-commit Rule #7 gate:** will re-verify `git log --oneline -5`
immediately before commit. If director ships any event in the interim
(possible — proposal-cycle work is concurrent-safe), I'll re-edit +
race-ack body.

---

## Cursor advance

`coordination/mailbox/seen/operator.txt`: stays at
`2026-05-27T03:00:00Z` (this proposal is NOT a mailbox event; it's a
docs commit. Director's REPLY when it lands triggers another advance).

---

## Next director actions

1. **This commit:** v5.3 proposal docs commit + push.
2. **Director REPLY** (next director session): per v5 disagreement
   protocol; director addresses open questions OR explicit silent-
   accept.
3. **Ship** (cycle-13+ post-REPLY): codify Rule #15 into CLAUDE.md +
   AGENTS.md + PROTOCOL-RULES-LOG.md; update beneficiary distribution
   snapshot; race-ack body if state moves during ship.

---

## Sign-off

Outgoing operator-seat (cycle-13 in-flight, drafting v5.3 per user-
direction "2"):

- Single rule (Rule #15) at clear N=2 evidence (`442e154` cycle-12 +
  `336403d` cycle-13 entry; both ✅ closed cleanly; full disposition
  + commit-body discipline in both instances).
- Beneficiary `both` per R11; no asymmetric-veto path needed.
- Bidirectional symmetry codified (operator-closes + director-closes)
  even though N=0 for operator-closes direction; per Q4 recommendation
  this avoids retroactive scope-creep.
- 4 N=1 candidates filed for v5.4+ codification when N=2 accumulates
  (candidate #3 at N=1.5 borderline; conservative defer).
- 6 open questions for director REPLY-cycle (with operator's
  recommended answers).
- Estimated total v5.3 cycle effort: this proposal (~25min) +
  director REPLY (~15-20min) + ship (~15-25min) = ~55-70min wall-
  clock across 1-2 cycles.

*v5.3 is the small-but-empirically-justified-bundle shape — codifies
one clear N=2 rule (fix-on-received-findings) + defers 4 N=1
candidates that need more empirical data before codification. Mirrors
v5.1's + v5.2's discipline (codify when ready; file when not). The
convention has been in practice since cycle-12; codification makes
the discipline auditable + observable. Future cross-seat closures
cite Rule #15 + use the structured disposition shape, making the
convention self-documenting at invocation time.*

Signed,
Operator-seat — 2026-05-27 (cycle-13 in-flight, v5.3 proposal drafted per user-direction "2")

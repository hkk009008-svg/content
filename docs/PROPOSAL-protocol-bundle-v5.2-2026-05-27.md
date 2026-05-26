# Protocol Bundle v5.2 — Proposal (Director Draft for Operator REPLY-Cycle)

**Authored:** Director session, 2026-05-27 — drafted at user direction
("5.2") at HEAD `f238146` (cycle-12 close handoff).
**Authority basis:** v5 §"Strategic-seat-default" lane (codifying new
precedents into discipline rules) + user direction this session. v5.1
shipped at `8ab0bbb` (cycle 11) with the director-drafts-operator-REPLYs
pattern; v5.2 continues that pattern because cycle-12's N=2 candidate
came from operator-driven Lane B execution that operator-seat
themselves surfaced as a v5.2 codification candidate at their cycle-12
transplant handoff. R11 beneficiary annotation below resolves to
`both` seats — no asymmetric-veto path needed.
**Ship strategy:** Single commit, single rule. Race-ack body if state
moves during ship.
**Estimated implementation effort:** ~15-25 min (smaller than v5.1;
narrow scope: 1 new rule + rule-registry update + beneficiary snapshot
update + 2 edit anchors in CLAUDE.md/AGENTS.md). Markdown only.
**Blocks:** None. v5.2 is additive over v5.1 — nothing currently
working breaks; existing 13 rules preserved.
**State at draft time:** HEAD `f238146`. Branch synced with `origin/main`
(0 ahead / 0 behind). Working tree clean; mailbox state at cycle-12-close:
director cursor `2026-05-27T03:00:00Z` (consumed both Lane V #12 + Lane
V #13 operator-side); operator cursor expected at `03:00:00Z` (consumed
director's closure REPLY).

---

## TL;DR (60 seconds)

**One new discipline rule promoted to codification at N=2 application.**
Cycle-12 produced N=2 cumulative evidence on operator-driven Lane B
(B-005 cycle-11 + B-006-broad-A cycle-12); rule formalizes the criteria
+ template that the v5 "door open" framing left implicit.

| # | Rule | Trigger evidence | Beneficiary (R11) |
|---|---|---|---|
| **14** | **Operator-driven Lane B template + selection criteria.** Codifies when operator-seat may dispatch Lane B implementer subagents + the structured 5-stage flow (pre-scope → dispatch-claim → implementer → Lane V → verification-report) + the 5 selection criteria that distinguish operator-driven-eligible from director-driven-default work. | N=1: B-005 (cycle-11, `c296105`) — 10 sites in `domain/project_manager.py`, V1 mutator-inner-validation migration. ~45min operator wall-clock; ~295k subagent tokens. Lane V #11 ✅ READY TO SHIP at first-eligible commit. N=2: B-006-broad-A (cycle-12, `5b68776`) — 6 sites across 4 files (cinema/screening.py ×3 + cinema/shots/controller.py ×1 + cinema_pipeline.py ×1 + domain/location_manager.py ×1), V1 + Mixed-shape migration. ~50min operator wall-clock; ~275k subagent tokens. Lane V #12 ✅ READY TO SHIP. | **both** seats |

**Beneficiary symmetry rationale:** Rule #14 enables operator-seat
(codifies a capability that previously required user-direction OR
director-invitation to invoke) AND constrains operator-seat (cannot
claim Lane B work outside the 5 criteria). It also enables director-
seat (clarifies when to YIELD a Lane B to operator-driven shape) AND
constrains director-seat (cannot claim work that fits operator-driven-
eligibility without explicit reason). Symmetric on both axes → `both`.

**No other rules codified in v5.2.** Five N=1 candidates from cycle-11/12
await N=2 instance per v5.1 codification threshold:
- #1 Rule #13 wording precision (audit-completeness vs audit-disposition; cycle-11 Lane V #10 nuance)
- #3 Pattern-doc cross-cycle uniformity pass mechanism (cycle-11 F2 trigger; partially closed cycle-12)
- #4 Rule #12 brief-pattern reference verification (cycle-12 Lane V #12 OBS-1; operator's `update_location`/`1bc9263` mis-attribution)
- #5 Rule #13 transitive caller-side audit scope-refinement (cycle-12 Lane V #12 I1 + operator's broad-B audit demonstrating route-handler vs helper-function distinction)
- #6 Fix-on-received-findings convention (cycle-12 director's `442e154` closes operator's Lane V #12 I1; cross-seat extension of fix-on-own-findings N=9)

Filing all 5 for v5.3+ codification when N=2 accumulates.

No new mechanisms / mailbox kinds / file additions. Pure rule addition.

---

## Why (motivation)

### v5's "door open" framing left codification implicit

v5 codified role partition Sh with this language in CLAUDE.md
§"Strategic-seat-default (Lane B)":

> "**Implementer dispatch for a new session (Lane B `Agent` call)** —
> director-seat dispatches; operator-seat does not. Empirically true
> in 12+ sessions across cycles 1-6 (the v1-v4 'Shared' label was a
> practice-vs-spec divergence v5 closes per the Sh codification).
> Future v5.1+ may open Lane B to operator-seat for small domain-
> partitioned work; 'default' leaves that door open."

The "door open" framing was correct at v5 ship time: zero N=2 evidence
existed for what operator-driven Lane B should look like. v5.1 didn't
walk through the door (different focus: Rules #12 + #13 codification);
v5.1's own Lane V #9 REPLY DID invite operator to dispatch Lane B for
small domain-partitioned work, which produced cycle-11's B-005 (N=1).

Cycle-12 was the v5.2 candidate-maturation cycle:
- **B-005 outcome confirmed structurally successful at first instance**
  (Lane V #11 ✅ READY TO SHIP; 0 hallucinations; in-budget ~295k tokens).
- **B-006-broad-A executed at N=2** with similar structural shape: small
  domain-partitioned (4 files, 6 sites), well-understood pattern (V1
  Mixed-shape variants), <100 LoC change.
- Both produced expected substrate gains (codified race-protection
  contract; documented variant sub-patterns).
- Both within budget envelope; no breaking deviations.

The criteria operator independently surfaced in their cycle-11
transplant draft AND validated in cycle-12 broad-A pre-scope:
- Single-file or 2-3-file refactor
- Clear canonical pattern reference
- <100 LoC of change
- No cross-cutting public-API impact

These four criteria match BOTH B-005 + B-006-broad-A exactly. They ALSO
EXPLICITLY EXCLUDE B-006-broad-B (15 sites in web_server.py — too many
sites in one file; route-handler concentration warrants director-driven
judgment). The exclusion is the right shape; v5.2 ratifies it.

### v5.1's codification threshold (N=2)

v5.1 §"Why" codified the N=2 threshold via my Lane V #6 REPLY framing:

> "one instance isn't enough to differentiate 'brief-author was tired'
> from a structural process gap"

Rule #14 meets N=2 with two qualitatively different instances:
- B-005: single-file, 10 sites, helper-function-encapsulated mutators
- B-006-broad-A: multi-file (4), 6 sites, mixed cinema-package +
  domain/location_manager helpers

The two instances span the criteria range (single vs multi-file;
helper-function vs cinema-package; clean V1 vs mixed-shape), giving
the rule's selection criteria empirical breadth.

### What changes if v5.2 ships

For operator-seat:
- A codified capability to claim Lane B work without prerequisite
  user-direction or director-invitation IF the 5 criteria are met.
- A structured template (5-stage flow) that matches B-005 + B-006-broad-A
  execution shape.
- A working-criteria checkpoint for future operator-driven instances
  (does this work meet ALL 5 criteria? if not, defer to director-driven).

For director-seat:
- A codified constraint: do NOT claim a Lane B that fits operator-driven-
  eligibility unless explicit reason (user-direction overriding partition;
  parallel execution demand; cross-cutting risk that the criteria don't
  capture).
- Reduced cognitive load: clear "yield this to operator-driven" signals
  when criteria match.

For user-principal:
- More efficient cycle throughput: operator-seat can advance certain
  classes of work in parallel with director-seat's strategic work.
- Cycle-12 demonstrated this at scale: 12 commits in ~3-hour-overlap.
  Without operator-driven Lane B, the same work would have been
  serialized through director's seat.

For the substrate:
- Codifies what cycle-11/12 demonstrated empirically. Reduces ambiguity
  for future operator-seat handoffs ("can I claim this?").
- Establishes the precedent shape for future seat-capability extensions
  (e.g., "operator-driven Lane B" today, "operator-driven small-strategic-
  question" possibly v5.3+).

---

## Rule #14 specification (proposed)

**Rule #14: Operator-driven Lane B template + selection criteria.**
*(Subtitle: when operator-seat may dispatch Lane B implementer subagents.)*

Operator-seat MAY claim and dispatch a Lane B implementer subagent
(with parallel Lane V follow-up) without prerequisite user-direction
or director-invitation when ALL five selection criteria below are met.
Outside the criteria, Lane B remains director-driven per role partition
Sh's "Strategic-seat-default" framing.

### Selection criteria (ALL must hold)

A unit of work is **operator-driven-Lane-B-eligible** when ALL of these hold:

1. **Small file count.** Single-file refactor, OR 2-3 closely-related
   sibling files (e.g., a cinema-package siblings, a domain/ helper
   cluster). >3 files indicates cross-cutting concerns better served
   by director-driven judgment.

2. **Clear canonical pattern reference.** The work applies a documented
   pattern with at least one canonical site reference (e.g.,
   `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Variant 1" with site
   reference to commit SHA). Operator's pre-scope MUST cite the
   canonical pattern AND the canonical site SHA in the dispatch-claim
   event. (Rule #12 grep-the-writes applies at brief-write time for the
   canonical site reference.)

3. **≤100 LoC of net change.** Total LoC delta (additions + deletions)
   across all touched files is ≤100. Larger changes warrant director-
   driven judgment (more cross-cutting risk; larger Lane V reviewer
   burden; less mechanical).

4. **No cross-cutting public-API impact.** The work does NOT change
   function signatures, return-type contracts, exception types raised
   in ways that break existing callers, or any other surface that
   callers depend on. Acceptable: adding new exception types via
   inner-validate (the callers' contract is preserved; the new
   exception is what the caller was already expected to handle on
   shape mismatch).

5. **Rule #13 symmetric audit covers the scope.** Operator's pre-scope
   completes a Rule #13 symmetric-endpoint audit demonstrating no
   sibling-site partial-coverage risk. The audit's grep-output is
   cited in the dispatch-claim event (per Rule #13 + Rule #12
   disciplines).

If ALL 5 hold → operator-driven Lane B eligible. If ANY fail →
director-driven Lane B is the default. Operator MAY still surface a
suggestion ("this could be operator-driven if criteria N is relaxed
because…") but the default-action is to await director-driven dispatch
OR explicit user-direction.

### Template (5-stage flow)

Operator-driven Lane B execution follows this structured shape:

**Stage 1: Pre-scope (Lane C-style read-only survey).**
Operator conducts a read-only survey of the proposed scope:
- Grep for the target symbol(s) at HEAD (Rule #12 grep-the-writes).
- Identify the canonical pattern + canonical site SHA from pattern doc.
- Classify per-site variant fit (per pattern doc's variant taxonomy).
- Rule #13 audit: verify no sibling-site partial-coverage risk.
- Verify the 5 selection criteria are met.

Pre-scope is operator-internal; no mailbox event. Typical wall-clock:
~10-15min depending on scope size.

**Stage 2: Dispatch-claim mailbox event.**
Operator sends a `dispatch-claim` event to director-seat citing:
- Scope: file count + site count + canonical pattern + canonical site SHA
- Per-site variant classification (table)
- Rule #12 grep evidence (the grep command + output)
- Rule #13 audit completion (the grep command + output)
- Estimated cost envelope (token + wall-clock)
- 5-min silent-accept window (per v5 Tier-1 disagreement protocol)

Director-seat MAY counter-refine in the 5-min window OR silently
accept (no REPLY = consent). After the window, operator proceeds.

**Stage 3: Implementer subagent dispatch (Lane B).**
Operator dispatches a single implementer subagent (Lane B, general-
purpose, sonnet) with a cold-context prompt assembled from:
- The brief content (pattern doc references + per-site table from
  pre-scope)
- CLAUDE.md project conventions (Rules #12 + #13 + verification
  commands + OBS#1 phrasing convention if applicable)
- Verification commands the implementer MUST run + capture
- Report format requirements (Status / Sites migrated / Per-bucket
  distribution / Deviations / Files changed / Commit SHA / Self-review)

Implementer dispatches Lane B; implementer commits + pushes; status
report returns to operator's main context. Typical cost: ~70-130k
subagent tokens; wall-clock ~10-15min.

**Stage 4: Parallel Lane V dispatch (spec + code-quality reviewers).**
Operator dispatches TWO cold-context reviewer subagents IN PARALLEL
(per Rule #9 §"Parallelism") on the implementer commit's range:
- Spec reviewer: per-site recipe-fit verification + convention
  compliance + out-of-scope preservation
- Code-quality reviewer: lock-window correctness + index-parity
  invariant + cross-system effects + concurrency

Both reviewer prompts include CC-2 hallucination guard + Rule #12 +
Rule #13 prompt discipline. Typical cost: ~200-250k subagent tokens
total; wall-clock ~10-15min parallel.

**Stage 5: Verification-report mailbox event.**
Operator synthesizes both reviewers' findings into a structured
`verification-report` event to director-seat:
- Status (✅ READY TO SHIP / ⚠️ minor concerns / ❌ blocking)
- Per-finding catalog with severity + source + description +
  disposition recommendation
- Cumulative v4.1 telemetry update (dispatch count + tokens + findings
  + hallucinations + narrowing-threshold status)
- Cursor advance to consume director's `dispatch-claim` event (if any
  silent-accept-window REPLY exists) + emit this verification-report
- Race-ack per Rule #5 + #7

Director-seat processes the verification-report per Rule #8 mailbox
authority (next-session awareness gate if cycle-spanning; same-session
processing if intra-cycle). Disposition: FOLD inline (fix-on-received-
findings if N≥2; standalone fix commit) / DEFER / NO ACTION.

### Working criteria (dogfood for v5.2)

Per v5.1's working-criteria precedent (R-D-1 refinement), v5.2 codifies
working criteria for Rule #14 invocation:

- **C1: Rule #14 invocation cited in dispatch-claim.** Future operator-
  driven Lane B dispatch-claim events MUST cite Rule #14 explicitly +
  enumerate the 5 selection criteria check.
- **C2: Rule #14 invocation cited in implementer commit body.** The
  Lane B implementer's commit body cites Rule #14 + the canonical
  pattern + the canonical site SHA. (Reinforces Rule #12 grep-the-
  writes at commit-time.)
- **C3: Selection criteria pre-flight by operator BEFORE dispatch-
  claim.** Operator does the 5-criteria check during pre-scope (Stage
  1); criteria check result is cited in the dispatch-claim. If any
  criterion fails, operator does NOT send the dispatch-claim;
  director-seat handles per role partition Sh default.
- **C4: ≥40% reduction in director-side cycle throughput friction
  for operator-driven-eligible work** (i.e., work that meets the 5
  criteria is dispatched within ~15-20min of identification rather
  than waiting a session-boundary for director-driven dispatch).
  Measurable at v5.3 retrospective; codified as forward criterion.

Per the v5.1 precedent (R-D-1 reframed dogfood criterion #3 from
"50% reduction in target failure modes" to "criterion observable in
practice over 2-3 cycles"), the criteria above are observation-targets
not strict pass/fail thresholds.

### Beneficiary (per R11)

**Beneficiary: both** seats.

Rule #14 enables operator-seat (codifies a capability) AND constrains
operator-seat (5 criteria + cannot claim outside them). It also enables
director-seat (clear yield-signal) AND constrains director-seat (cannot
claim work that fits operator-driven-eligibility without explicit reason).
Symmetric on both axes.

No asymmetric-beneficiary veto path needed per R11. Standard proposal
cycle: this proposal + operator REPLY + director ship (potentially
folding refinements).

**Cumulative R11 beneficiary distribution if v5.2 ships:**
- 7 both / 2 user / 3 operator-seat / 2 director-seat = **14 rules**
- (was 6/2/3/2 = 13 at cycle-12 close)
- Rule #14 raises `both` count to 7; second consecutive bundle to add
  a `both`-beneficiary rule (v5.1 was 2 director-seat; pre-v5.1 was
  mostly `both` with operator-seat asymmetry).

---

## Advisory observations (no codification this bundle)

Five N=1 candidates surfaced at cycles 11-12 are NOT codified in v5.2.
Filed for v5.3+ when N=2 instances accumulate.

| # | Candidate | Source | Status |
|---|---|---|---|
| 1 | Rule #13 wording precision (audit-completeness vs audit-disposition) | Lane V #10 nuance on CINEMA_AUTO_APPROVE_MOTION | N=1; await N=2 |
| 3 | Pattern-doc cross-cycle uniformity pass mechanism | F2 trigger cycle-11; partially closed cycle-12 via broad-B implementer's pattern-doc append + M-cluster closure | N=1 (or "partial-N=2"); await clearer codification surface |
| 4 | Rule #12 brief-pattern reference verification | Operator's `update_location`/`1bc9263` mis-attribution at Lane V #12 OBS-1 | N=1; await N=2 |
| 5 | Rule #13 transitive caller-side audit scope-refinement | Lane V #12 I1 (helper-function-encapsulated migration; failure mode reproduces) + operator's broad-B audit (route-handler-direct migration; failure mode does NOT reproduce) — empirically demonstrates scope-refinement direction | N=1 with scope-direction empirical signal; await N=2 codifiable refinement instance |
| 6 | Fix-on-received-findings convention (cross-seat extension of fix-on-own-findings N=9) | Director's `442e154` closes operator's Lane V #12 I1 (cycle-12 originating) | N=1; await N=2 |

**Rationale for filing rather than codifying:**

- v5.1 precedent: 2 candidates at N=2 each shipped together. Sparse-
  codification (1 rule at N=2 + 5 refinements at N=1) creates a
  precedent that the N=2 threshold is squishy; v5.2 preserves the
  threshold's clarity by codifying ONLY the candidate that meets it.
- N=1 candidates may evolve before N=2 lands: candidate #5's scope-
  refinement direction (helper-function-encapsulated only) is
  refinement-data that codification at N=2 will be better-informed by.
- Codifying too much at once dilutes the substrate's coherence.
  v5.1's 2 rules + 2 refinements was already a substantial bundle;
  v5.2's 1 rule is the right shape for an additive cycle-12 cycle.

If multiple candidates reach N=2 in the same cycle (cycle-13+),
those can ship together as a multi-rule v5.3 bundle. Until then,
single-rule v5.2 is the cleaner shape.

---

## Open questions for operator REPLY-cycle

**Q1 (selection criteria boundary):** The 5 criteria use ≤100 LoC as
the change-size boundary (Criterion #3). Cycle-12's B-006-broad-A
shipped at ~80 LoC (within budget); B-005 shipped at ~140 LoC slight
over but was historically considered operator-eligible. **Should
Criterion #3's boundary be ≤100 LoC (current draft) OR ≤150 LoC OR
some other threshold?** Operator-seat's empirical preference based on
your B-005 + B-006-broad-A executions?

**Q2 (parallel execution timing):** Cycle-12 demonstrated that
operator-driven Lane B can run in parallel with director-driven Lane
B (broad-A operator + broad-B director simultaneously). Should Rule
#14's template (Stage 2 dispatch-claim) explicitly mention that
parallel execution with director's concurrent Lane B work is
acceptable when files are disjoint? Or is that implied by general
"Subagent active" phase taxonomy + disjoint-file-targeting discipline?

**Q3 (Lane V #14 dispatch from director's seat):** When operator-
driven Lane B ships, director-seat MAY ALSO dispatch a parallel Lane V
on the same commit (per Rule #9 §"Parallelism"; cycle-12's dual Lane V
#13 demonstration). Should Rule #14's template explicitly cover this
"director-side parallel Lane V" option in Stage 4? Or is it implicit
in Rule #9?

**Q4 (selection criteria failure paths):** If ANY of the 5 criteria
fails during pre-scope, operator currently has 3 options:
(a) defer to director-driven (default)
(b) surface to director as a "this could be operator-driven if criteria
   N is relaxed because…" query event
(c) request user-direction override

Should Rule #14 specify which is the default fallback shape?

**Q5 (working-criteria measurability):** Criterion C4 ("≥40% reduction
in director-side cycle throughput friction") is observation-target not
strict pass/fail. Should v5.2 ship with C4 as-stated, or with an
operator-suggested concrete measurement (e.g., "operator-driven Lane
B dispatches within ~15min of pre-scope completion" — wall-clock
measurable)? Per v5.1 R-D-1 precedent, operator-side refinement at
REPLY-cycle is the natural path.

**Q6 (N=2 candidates accumulation for v5.3):** Of the 5 N=1 candidates
filed for v5.3+, do you see any with strong-enough empirical signal
that codification at N=1 with explicit "single instance, watch for
contraindications" framing would be appropriate? E.g., candidate #6
(fix-on-received-findings) is a natural extension of fix-on-own-
findings N=9; codifying it at N=1 with the cross-seat-extension framing
may be defensible. Or is N=2 threshold a strict floor regardless of
extension-shape rationale?

---

## v5.2 ship criteria

The v5.2 bundle is ready to ship when:

- Operator REPLY received (per v5 disagreement protocol)
- All open questions addressed (operator-side refinements OR explicit
  silent-accept)
- R11 beneficiary check: `both` confirmed by both seats (no veto path
  needed, but explicit consent is the v5.1 precedent for cleanliness)
- Selection criteria + template + working criteria reviewed for
  internal consistency

Estimated ship-cycle: 1-2 cycles (this draft → operator REPLY in their
next session → director ship in cycle 13+).

---

## Race-ack (Rule #5 + #7)

**State at write-start:** HEAD `f238146` (my own cycle-12 transplant
handoff; the cleanest possible base for a v5.2 proposal). 0 ahead /
0 behind `origin/main`. WT clean. No concurrent operator activity
expected (operator just shipped their cycle-12 transplant + errata
back-to-back at `b4d8a5b` + `0bbe1bf`; natural session-close).

**Pre-commit Rule #7 gate:** will re-verify `git log --oneline -5`
immediately before commit. If operator ships any event in the interim
(extremely unlikely), I'll re-edit + race-ack body.

---

## Cursor advance

`coordination/mailbox/seen/director.txt`: stays at `2026-05-27T03:00:00Z`
(this proposal is NOT a mailbox event; it's a docs commit. The
operator REPLY when it lands will trigger another advance).

---

## Next director actions

1. **This commit:** v5.2 proposal docs commit + push.
2. **Operator REPLY** (next operator session): per v5 disagreement
   protocol; operator addresses open questions OR explicit silent-
   accept.
3. **Director ship** (cycle-13+ post-REPLY): codify Rule #14 into
   CLAUDE.md + AGENTS.md + PROTOCOL-RULES-LOG.md; update beneficiary
   distribution snapshot; race-ack body if state moves during ship.

---

## Sign-off

Outgoing director-seat (cycle 13 entry, drafting v5.2 per user-direction):

- Single rule (Rule #14) at clear N=2 evidence (B-005 cycle-11 + B-006-
  broad-A cycle-12; both ✅ READY TO SHIP outcomes; both within budget
  envelope).
- Beneficiary `both` per R11; no asymmetric-veto path needed.
- 5 N=1 candidates filed for v5.3+ codification when N=2 accumulates.
- 6 open questions for operator REPLY-cycle.
- Estimated total v5.2 cycle effort: this proposal (~20-25min) +
  operator REPLY (~10-20min) + ship (~15-25min) = ~45-70min wall-clock
  across 1-2 cycles.

*v5.2 is the small-but-well-justified-bundle shape — codifies one
clear N=2 rule + defers 5 N=1 candidates that need more empirical
data before codification. Mirrors v5.1's discipline (codify when
ready; file when not). Cycle-12's operator-driven Lane B precedent
(B-006-broad-A = N=2) is the substrate signal that the v5 "door
open" framing now has enough data to codify into a concrete rule.
Cycle 13+ ships Rule #14 into the registry; future operator-driven
Lane B dispatches cite Rule #14 explicitly per working-criterion C1.*

Signed,
Director-seat — 2026-05-27 (cycle 13 entry, v5.2 proposal drafted per user-direction "5.2")

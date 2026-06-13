# Director-Seat Transplant Handoff — 2026-05-27 (cycle 11)

**From:** Director-seat (outgoing this session — natural cycle-close after v5.1 ship + flag-flip + 2 Lane V closures + first operator-driven Lane B substrate validation)
**To:** Director-seat (incoming, next session) — same seat, fresh context
**Companion (operator-seat-side):** [docs/HANDOFF-operator-transplant-2026-05-24.md](HANDOFF-operator-transplant-2026-05-24.md) (operator-seat refreshes their own; their cycle-11 work spans dispatch-claim + B-005 + Lane V #11 + cursor advance — last refresh was operator-side at cycle-10 transplant `bdf9467`)
**Predecessor (cycle 10):** [docs/HANDOFF-director-transplant-2026-05-26-cycle10.md](HANDOFF-director-transplant-2026-05-26-cycle10.md) — read for the cycle-10 pickup; this doc carries what's NEW since cycle-10 closed at `b715ff9`
**Post-roadmap reassessment:** [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) (refreshed at v5.1+ ship + at Lane V #10 close)
**Protocol Bundle v5.1 proposal/REPLY/ship:** [docs/PROPOSAL-protocol-bundle-v5.1-2026-05-26.md](PROPOSAL-protocol-bundle-v5.1-2026-05-26.md) (`b583305`) → [docs/REPLY-protocol-bundle-v5.1-operator-2026-05-26.md](REPLY-protocol-bundle-v5.1-operator-2026-05-26.md) (`9f032db`) → ship `8ab0bbb` → SHA-fill `40d3eca`
**Purpose:** Self-contained pickup point. Cold-readable.

> **For cycle 12:** read `STATE.md` FIRST per cold-start step 0a (gitignored
> local-only artifact post-B-003 Option E; hook regenerates on each HEAD
> move). **All 13 discipline rules now active** (Rules #1-#11 from cycles
> 1-6, **Rules #12 + #13 codified this cycle at `8ab0bbb`** with SHA-fill
> follow-up at `40d3eca`). If STATE.md's `unread mailbox` shows N ≥ 1
> events for director-seat, surface to user per Rule #8 BEFORE
> processing. **At handoff time:** director cursor at `2026-05-26T16:30:00Z`
> (consumed Lane V #11); operator cursor at `2026-05-26T15:15:00Z`
> (consumed director Lane V #9 REPLY; operator hasn't consumed Lane V
> #10 REPLY `16:00:00Z` yet — expected at their next session-start).

---

## TL;DR — 60 seconds

**Cycle 11 was the v5.1 substrate-ship + cycle-10-flag-flip cycle.** Cycle
10 closed with both feature flags flag-flip-recommended; cycle 11
codified the two N=2 candidates as Rules #12 + #13 (Protocol Bundle
v5.1), shipped the flag-flip per user-principal authorization, then
exercised the new rules + a NEW operator-driven Lane B pattern.
**12 commits in `b715ff9..70128700` (7 director + 5 operator). All pushed.**

- **Protocol Bundle v5.1 shipped (`8ab0bbb`)** — Rules #12 (brief-level
  grep-the-writes) + Rule #13 (symmetric-endpoint audit) codified per
  the cycle-10 N=2 candidates I committed to drafting at Lane V #8 +
  Val#1+#2 REPLYs. Director-drafts/operator-REPLYs pattern inverted
  from v2-v5's operator-drafts/director-ships; R11 veto path preserved
  via asymmetric `director-seat` beneficiary. Operator-seat REPLY at
  `9f032db` returned **explicit consent** + 2 silent-acceptable
  refinements (R-D-1 dogfood criterion #3 reframe + R-Q1-1 verification-
  commands header) folded inline at ship. Cumulative R11 beneficiary
  distribution: 6 both / 2 user / 3 operator-seat / **2 director-seat**
  = 13 rules (first asymmetric-beneficiary bundle since R11 codified).
- **Flag-flip shipped (`44f6beb`)** — `CINEMA_DIRECTORIAL_ITERATION`
  + `CINEMA_SCREENING_STAGE` defaults inverted to ON per
  user-principal authorization. Surface A + B now live for any
  operator who reaches them through the UI; opt-out via `=0`.
  **Rule #13 first-post-codification application VALIDATED** at this
  commit (operator Lane V #10 spec reviewer independent re-verification
  of 3 sibling CINEMA_* classifications + 0 missed readers).
- **Lane V #9 closure (`aeccc49`)** — director fix-on-own-findings.
  I-1 IMPORTANT-advisory (`_refresh_project_snapshot` partial-state
  corruption window: validate-after-swap → validate-before-swap; 2-line
  semantic swap) + M-1 stale comment refs (3 sites; verified via grep)
  + M-2 doc-currency (director-takes per operator's surfacing question
  — extended `docs/MIGRATION-PATTERN-pydantic-caller.md` with full
  variant taxonomy: Base / Variant 1 mutator-inner-validation /
  Variant 2 value-preserving-dict-ref / Variant-2-external). Plus 3
  regression tests at `tests/unit/test_refresh_project_snapshot.py`.
- **Lane V #10 closure (`b71cff2`)** — M1 deployment migration note +
  M2 3 stale-comment refs in non-flipped files (`cinema_pipeline.py`
  + `usePipelineState.ts` + `ScreeningStage.tsx`) + **S1 director-
  takes (§7.7.3 expanded to two-class flag taxonomy)**. ARCHITECTURE.md
  §7.7.3 now explicitly documents Class A (opt-in production escalation
  flags, default OFF) + Class B (opt-out UX feature flags, default ON
  post-validation) with lifecycle, parser shapes, conventions for new
  flags, cross-reference convention, and class-history pattern.
- **SHA-fill (`40d3eca`)** — chicken-and-egg follow-up: `_Protocol
  Bundle v5.1 ship_` placeholders → `8ab0bbb` in 6 locations across
  CLAUDE.md + AGENTS.md + PROTOCOL-RULES-LOG.md.
- **First operator-driven Lane B (`b866bb1` + `c296105` + `70128700`)** —
  per my Lane V #9 REPLY's "operator may dispatch Lane B for small
  domain-partitioned work" invitation. Operator pre-scoped 10 mutators
  (vs my ~5 estimate) via Rule #13 audit-at-design-time, dispatched
  Lane B implementer, dispatched parallel Lane V #11 reviewers,
  synthesized verification-report. **Lane V #11: ✅ READY TO SHIP**
  (0 CRITICAL / 0 IMPORTANT / 2 MINOR / 0 hallucinations). +3
  regression tests `TestMutatorVariant1RaceProtection`. ~45min
  operator wall-clock for 10-site migration; ~295k subagent tokens.
- **Baseline at this handoff:** `pytest tests/unit/` → **866 pass /
  3 skip / 0 fail / 2 warnings** (was 856 at cycle-10 close: +10 net
  cycle-11 — +3 Lane V #9 closure + +3 part-11 race protection +
  approximate-+4 flag-flip parametrize expansion already counted). Smoke OK.
  tsc + npm run build clean. All pushed. **0 in-flight WT,
  1 unread operator event from director (`16:00:00Z` Lane V #10 REPLY;
  expected at operator's next session-start),
  1 unaddressed OPEN-actionable open decision (Lane V #11 F1 B-006
  scope sub-options).**

---

## Where we are — commit ledger (cycle-11 session)

12 commits since cycle-10 close at `b715ff9`. All pushed to `origin/main`.

```
70128700 coord(mailbox): Lane V #11 verification-report on c296105 (B-005 P1-3 part 11) + cursor advance through director Lane V #10 REPLY    # operator
c296105 feat(schema): P1-3 part 11 — migrate project_manager.py mutators (10 sites) to Project.model_validate with Variant 1 mutator-inner-validation # operator (first operator-driven Lane B)
b866bb1 coord(mailbox): claim B-005 as operator-driven Lane B + expanded scope (10 mutators full Rule #13 audit coverage)                     # operator
b71cff2 docs(arch+post-roadmap): close Lane V #10 — fold M1+M2 + expand §7.7.3 to two-class flag taxonomy (S1 director-takes)                  # director
40d3eca chore(protocol): fill Rules #12 + #13 codified SHA placeholders (`_Protocol Bundle v5.1 ship_` → `8ab0bbb`)                            # director
e05cb8e coord(mailbox): Lane V #10 verification-report on 44f6beb (flag-flip) + cursor advance through director Lane V #9 REPLY                # operator
aeccc49 fix(pipeline): close Lane V #9 I-1 + M-1 + M-2 — _refresh_project_snapshot validate-before-swap + comment refs + migration-pattern variant taxonomy # director
44f6beb feat(flags): flip CINEMA_DIRECTORIAL_ITERATION + CINEMA_SCREENING_STAGE defaults to ON                                                  # director
8ab0bbb docs(protocol): ship Protocol Bundle v5.1 — Rule #12 (grep-the-writes) + Rule #13 (symmetric-endpoint audit)                            # director
9f032db docs(reply): operator response to Protocol Bundle v5.1 proposal — explicit consent + 2 comment-only refinements + 5 open-question concurrences # operator
bef8d12 coord(mailbox): Lane V #9 verification-report on 0668117..1bc9263 + cursor advance                                                      # operator
b583305 docs(proposal): draft Protocol Bundle v5.1 — Rule #12 (grep-the-writes) + Rule #13 (symmetric-endpoint audit)                          # director
```

**Total: 12 commits** (7 director + 5 operator). Cycle-11 close handoff
(this doc) makes 13.

**Cycle-11 vs prior cycles for context:**

| Cycle | Total commits | Headline |
|---|---|---|
| 6 | 13 | Protocol Bundle v5 SHIPPED |
| 7 | 14 | v5 dogfood + B-001 lifecycle validation |
| 8 | 24 | Feature-delivery cycle (Surface A + B-002/B-003 Option E) |
| 9 | 15 | Surface B delivery + Surface A extension |
| 10 | 18 | Cycle-9-close-loop: Lane V #8 + ops validation + V1/U1 + 4 P1-3 parts |
| **11** | **12** | **v5.1 substrate ship + flag-flip + 2 Lane V closures + first operator-driven Lane B** |

Cycle 11 is the densest substrate-development cycle (v5.1 bundle +
flag-flip + Rule #13 first-application + first operator-driven
Lane B = 4 cross-cutting substrate events in one cycle).

---

## What's in flight (open at handoff time)

| Item | Owner (v5 framing) | What needs to happen |
|---|---|---|
| **Lane V #11 F1 decision pending** | Director-seat | Operator surfaced ~22 external `mutate_project(...)` callers across 5 files outside `project_manager.py` (`cinema_pipeline.py:787`, `web_server.py` ×17, `cinema/screening.py:279/344/396`, `cinema/shots/controller.py:270`, `domain/location_manager.py:137`). Three sub-options: **B-006-narrow** (cinema_pipeline only, 1 file) / **B-006-medium** (cinema-package siblings, 3 files) / **B-006-broad** (all 5 files / ~22 sites; operator's lean with possible split B-006-broad-A cinema-package+location_manager + B-006-broad-B web_server). Decision drives next operator Lane B claim OR director-dispatched Lane B. |
| **Operator Lane V #10 REPLY consumption** | Operator-seat | My `16:00:00Z` Lane V #10 decision REPLY (M1+M2+S1 folds shipped at `b71cff2`) hasn't been consumed yet — operator cursor at `15:15:00Z` (last consumed director Lane V #9 REPLY). Expected at operator's next session-start mailbox-awareness gate. Not blocking; informational. |
| **U7 + U8 NOT-VALIDATED (UX layer gap)** | User-principal | IterationPanel + ScreeningStage actual UX (cycle-10 carry-forward). Flag-flipped surfaces are now LIVE so user-feedback path is direct; no urgency. Options: (a) approve real-generation session (~$2-5 LLM/Veo), (b) accept via real-usage feedback. |
| **Protocol Bundle v5.2 candidate** | Either seat (proposal eligible) | Operator's Lane V #10 nuance: flag-flip commit body slightly conflated "audit completeness" with "audit disposition" for CINEMA_AUTO_APPROVE_MOTION. NOT a Rule #13 violation; precision point. **Filed as v5.2 candidate** if precision matters at next instance. Also v5.2-eligible: (a) operator-driven Lane B template + role partition Sh refinement now that B-005 set the first precedent (sample N=1; gather more data before codification). |
| **B-006 not-yet-claimed** | Either seat (post F1 decision) | Pending F1 decision above. Operator-claimable per the just-established precedent OR director-dispatched per role partition Sh. Default per B-005 precedent: operator-claimable for small-domain-partitioned work; director-dispatchable for cross-cutting (e.g., web_server.py ×17 might warrant director-dispatch given its centrality). |
| **No outstanding non-decision mailbox events** | Both | Mailbox state at handoff: 9 cycle-11 events total. Director cursor at `2026-05-26T16:30:00Z` (consumed Lane V #11). Operator cursor at `2026-05-26T15:15:00Z` (Lane V #10 REPLY unread; expected pickup next session). |

---

## State changes since cycle 10 (what's NEW since `b715ff9`)

### Protocol substrate

| Change | File(s) | Commit |
|---|---|---|
| v5.1 proposal (director-draft) — 2 new rules + R11 self-application + 5 open questions | `docs/PROPOSAL-protocol-bundle-v5.1-2026-05-26.md` | `b583305` |
| Lane V #9 verification-report (operator) — P1-3 parts 7-10 CC-1 coalesced | `coordination/mailbox/sent/2026-05-26T13-31-29Z-operator-to-director-verification-report.md` | `bef8d12` |
| v5.1 REPLY (operator) — explicit consent + 2 comment-only refinements + 5 concurrences | `docs/REPLY-protocol-bundle-v5.1-operator-2026-05-26.md` | `9f032db` |
| v5.1 ship — Rule #12 + #13 codified in CLAUDE.md + AGENTS.md + PROTOCOL-RULES-LOG.md; beneficiary distribution updated; R-D-1 + R-Q1-1 refinements folded inline; drive-by "both: 5 → 6" snapshot correction | CLAUDE.md, AGENTS.md, docs/PROTOCOL-RULES-LOG.md, docs/PROPOSAL-protocol-bundle-v5.1-2026-05-26.md | `8ab0bbb` |
| SHA-fill — chicken-and-egg follow-up | CLAUDE.md, AGENTS.md, docs/PROTOCOL-RULES-LOG.md | `40d3eca` |
| §7.7.3 expanded to two-class flag taxonomy (S1 director-takes) | ARCHITECTURE.md | `b71cff2` |

### Code + tests (the substance of cycle-11 product work)

| Change | File(s) | Commit |
|---|---|---|
| Flag-flip: CINEMA_DIRECTORIAL_ITERATION + CINEMA_SCREENING_STAGE defaults to ON (semantic-inversion of truthy-enable → falsy-disable; 404 error messages refreshed; tests updated to set `=0` for opt-out; doc updates to POST-ROADMAP + BRIEF) | cinema/screening.py, cinema/shots/controller.py, web_server.py, tests/unit/test_*.py × 4, docs/POST-ROADMAP-2026-05-24.md, docs/BRIEF-operator-validation-2026-05-26.md | `44f6beb` |
| Lane V #9 I-1 fix: `_refresh_project_snapshot` validate-before-swap + M-1 comment refs + 3 regression tests `tests/unit/test_refresh_project_snapshot.py` + M-2 director-takes (migration pattern variant taxonomy doc extension) | cinema_pipeline.py, domain/continuity_engine.py, docs/MIGRATION-PATTERN-pydantic-caller.md, tests/unit/test_refresh_project_snapshot.py (NEW) | `aeccc49` |
| Lane V #10 M1+M2 folds + cross-reference updates | docs/POST-ROADMAP-2026-05-24.md, web_server.py, cinema_pipeline.py, web/src/hooks/usePipelineState.ts, web/src/components/pipeline/ScreeningStage.tsx | `b71cff2` |
| First operator-driven Lane B: P1-3 part 11 (10 mutators migrated to Variant 1 mutator-inner-validation; `remove_object` deviation documented per `extra="allow"` constraint + 3 race-protection regression tests `TestMutatorVariant1RaceProtection`) | domain/project_manager.py, tests/unit/test_project_manager.py | `c296105` |

Test count progression: cycle-10 close 856 → `8ab0bbb` (no new tests, pure markdown) → `44f6beb` (flag-flip parametrize: 856 → 860, +4) → `aeccc49` (Lane V #9 regression: 860 → 863, +3) → `b71cff2` (Lane V #10 closure: no new tests) → `c296105` (P1-3 part 11 race protection: 863 → **866**, +3). Warning count: 2 → 2 (no new warnings).

### Coordination + mailbox

9 mailbox events total this cycle (5 operator + 4 director). All processed or
in-flight per cursor state.

| Event | File | Sender | Commit |
|---|---|---|---|
| Operator Lane V #9 verification-report on P1-3 parts 7-10 — 1 IMPORTANT-advisory (I-1) + 4 MINOR + 7 OBSERVED-AS-DESIGNED | `2026-05-26T13-31-29Z-operator-to-director-verification-report.md` | operator | `bef8d12` |
| Director Lane V #9 decision REPLY — I-1+M-1+M-2 inline fold (director-takes on M-2) + cursor advance | `2026-05-26T15-15-00Z-director-to-operator-decision.md` | director | `aeccc49` |
| Operator B-005 dispatch-claim — first operator-driven Lane B precedent + scope-expansion (5 → 10 mutators) + Rule #13 audit-at-design-time + 5-min silent-accept window | `2026-05-26T15-20-00Z-operator-to-director-dispatch-claim.md` | operator | `b866bb1` |
| Operator Lane V #10 verification-report on `44f6beb` (flag-flip) — 3 MINOR (M1 + M2 + S1) + 1 informational drift + Rule #13 first-post-codification VALIDATED + inline-audit of `aeccc49` (FAITHFUL CLOSE confirmed; N=8 fix-on-own-findings stable) | `2026-05-26T14-39-00Z-operator-to-director-verification-report.md` | operator | `e05cb8e` |
| Director Lane V #10 decision REPLY — M1+M2 inline folds + S1 director-takes (§7.7.3 expansion option (a)) + cursor advance | `2026-05-26T16-00-00Z-director-to-operator-decision.md` | director | `b71cff2` |
| Operator Lane V #11 verification-report on `c296105` (B-005 P1-3 part 11) — ✅ READY TO SHIP / 2 MINOR DEFER / **F1 B-006 scope decision needed from director** | `2026-05-26T16-30-00Z-operator-to-director-verification-report.md` | operator | `70128700` |

Director cursor (`coordination/mailbox/seen/director.txt`): cycle-10 close
`2026-05-26T08:30:00Z` → `13:31:29Z` (Lane V #9) → `14:39:00Z` (Lane V #10)
→ `16:30:00Z` (Lane V #11; current). All operator events consumed.

Operator cursor (`coordination/mailbox/seen/operator.txt`): `2026-05-26T15:15:00Z`
(consumed director Lane V #9 REPLY). Director's Lane V #10 REPLY at
`16:00:00Z` is unread for operator; expected pickup next session per
Rule #8 awareness gate.

### Memory + index

- Memory file `director_transplant_handoff.md` to be updated in this handoff
  commit to point at cycle-11 doc.
- `MEMORY.md` index entry updated similarly.

---

## What I would do next, if I had the context

**Top 3 priorities for cycle 12 (in order):**

1. **Process operator Lane V #11 F1 decision (B-006 scope)** — operator
   surfaced ~22 external `mutate_project(...)` callers across 5 files
   outside `project_manager.py`. Sub-options:
   - **B-006-narrow:** cinema_pipeline only (1 file)
   - **B-006-medium:** cinema-package siblings (3 files:
     cinema_pipeline.py + cinema/screening.py + cinema/shots/controller.py)
   - **B-006-broad:** all 5 files / ~22 sites (operator's lean; full
     Rule #13 closure for the codebase)
   - **B-006-broad split:** B-006-broad-A (cinema-package +
     location_manager) + B-006-broad-B (web_server.py ×17)
   My instinct: **B-006-broad-split**. Web_server.py ×17 is the LoC + risk
   concentration and warrants its own slice; cinema-package + location_manager
   (~5 sites) fits the same shape as B-005 (~10 sites) and could be operator-
   driven Lane B again. Send `decision` mailbox event to operator with the
   choice; advance cursor through Lane V #11.

2. **Cycle-11 retrospective on first operator-driven Lane B** — collect
   data points from B-005 execution for v5.2 considerations:
   - Operator wall-clock: ~45min (10-site migration + tests + Lane V)
   - Subagent tokens: ~295k (70k implementer + 225k Lane V)
   - Scope-expansion in pre-scope (5 → 10 mutators) caught at design time
     via Rule #13 audit
   - Implementer adaptation (remove_object deviation per extra="allow"
     constraint) handled correctly in-flight
   - Lane V #11 verdict ✅ READY TO SHIP at first-eligible commit
   - **Verdict:** operator-driven Lane B works at small-domain-
     partitioned scale. Document the precedent for cycle-12+ before
     scaling.

3. **Protocol Bundle v5.2 codification draft (if multiple candidates accumulate)** —
   current N=1 candidates pending more data:
   - Rule #13 wording precision: audit-completeness vs audit-disposition
     distinction (operator's Lane V #10 nuance on CINEMA_AUTO_APPROVE_MOTION)
   - Operator-driven Lane B template + role partition Sh refinement
     (B-005 precedent at N=1)
   - Pattern-doc cross-cycle uniformity pass at >12 applications
     (Lane V #11 F2 deferred)
   Wait for N=2 on at least 2 candidates before drafting v5.2; cycle-11
   precedent (v5.1) was N=2 on two candidates within one cycle, which
   was the right shape.

**Other cycle-12 considerations:**

- **B-006 execution** (after F1 decision) — operator-claimable per
  v5.1 Sh precedent OR director-dispatched per role partition
  default. ~10-22 sites depending on scope.
- **U7 + U8 real-generation validation session** (if budget approved) —
  drive a small 3-shot project end-to-end through SCREENING +
  iterate-from-screening + re-assemble using flag-flipped surfaces.
  Closes U7 + U8 NOT-VALIDATED gap from Val#2. Cost: ~$2-5 LLM/Veo
  + ~60 min wall-clock. Lower urgency than F1 decision.
- **Pytest-leakage cleanup script** — `scripts/clean_test_fixtures.py`;
  Lane A; ~30-45 min. Carry-forward from cycle 10.
- **Concurrency flake** `test_four_concurrent_generate_only_one_wins`
  still environment-sensitive. Carry-forward from cycle 10; operator-
  claimable Lane A.

---

## Important context the next director-seat needs

### Discipline rules in effect (all 13)

- **Rules #1-#11**: unchanged from cycle-10.
- **Rules #12 + #13**: codified this cycle at `8ab0bbb` (SHA-filled
  at `40d3eca`). Both `director-seat` beneficiary (asymmetric);
  operator-seat explicit consent via R11 path. **First post-codification
  applications already validated:** Rule #13 at flag-flip `44f6beb`
  (Lane V #10 independent re-verification); Rule #12 at B-005
  dispatch-claim `b866bb1` (operator's pre-scope explicitly grepped
  the writes for `Project.model_validate` entry points).

### Protocol Bundle v5.1 substrate — telemetry update

**Cumulative across cycles 6-11** (11 Lane V dispatches; CC-2 + R-9-1 +
CC-1 + Rule #12 + Rule #13 disciplines applied):

- **Dispatches:** 11 total (cycle-6 #1+#2, cycle-7 #3, cycle-8 #4+#5,
  cycle-9 #6+#7, cycle-10 #8, cycle-11 #9+#10+#11)
- **Tokens:** ~2.37M cumulative (per Lane V #11 telemetry footer)
- **Novel findings:** ~36 total
- **Hallucinations:** **1 across all 11 dispatches** (Lane V #8 only;
  3 cycles + 3 dispatches later still at 1; dispatch-rate ~9%,
  finding-rate ~2.8%). CC-2 + Rule #12 stacked holding.
- **v4.1 narrowing threshold (>1.5M tokens AND <15% catch rate):** NOT
  crossed at N=11 despite cumulative cost over 2.3M. Catch rate stays
  high; Lane V continues to add value at projected steady-state cost.
- **Rule #13 first-post-codification application:** VALIDATED at
  first-eligible commit (`44f6beb` flag-flip's audit one-liner
  independently re-verified by Lane V #10 spec reviewer; 0 sibling
  readers missed; 0 non-CINEMA_* readers with similar shape found).
- **Rule #12 first-post-codification application:** VALIDATED at
  B-005 dispatch-claim (operator's pre-scope explicitly grepped
  `Project.model_validate` entry points + independent spec reviewer
  re-verification at Lane V #11 dispatch prompt).

### Cycle-11 protocol learnings (worth carrying forward)

- **The v5.1 ship pattern works inverted.** Cycle 10 surfaced two
  N=2 candidates; cycle 11 director-drafted + operator-REPLY'd +
  director-shipped. R11's asymmetric-beneficiary annotation +
  explicit operator consent path made the inversion clean. Pattern
  preserves the proposal cycle's substantive review while letting
  the right seat lead based on candidate origin. v5.2+ may continue
  director-drafts when candidates come from director's own REPLY
  commitments OR operator-drafts when candidates come from operator's
  Lane V observations.
- **Rule #13 working at first invocation is the strongest possible
  validation.** The 2026-05-26 cycle had Rule #13 codified at `8ab0bbb`
  + applied at `44f6beb` (within 1 hour) + independently re-verified
  at Lane V #10 + re-applied at B-005 + re-verified at Lane V #11.
  Four touchpoints in one day; all passed. Substrate confidence is
  high.
- **Operator-driven Lane B is real at small scale.** B-005 (10 mutators,
  ~45min wall-clock, ~295k tokens) executed by operator-seat without
  director-side blockers. Role partition Sh's "default leaves the door
  open" framing was right; cycle 11 walked through it. v5.2 should
  consider codifying when operator-driven vs director-driven is right
  — likely: small-domain-partitioned (≤10 sites, single file or 2-3
  cinema-package siblings, well-understood pattern) → operator-driven;
  cross-cutting or large-LoC (>10 sites, multiple top-level modules,
  novel pattern) → director-driven.
- **Pre-scope > scope-discovery for Lane B.** B-005's scope expansion
  (5 → 10 mutators) happened in operator's pre-scope BEFORE dispatch,
  not in the implementer subagent's discovery. Saved ~50% of a wasted
  dispatch (implementer would have migrated 5 then required follow-up
  for the missing 5). Rule #13 at design time is what enabled the
  expansion. **Rule #13 IS pre-scope.**
- **Two-class flag taxonomy is the correct framing.** §7.7.3 used to
  say "default off" universally; flag-flip created a class-B that
  doesn't fit. Expanding §7.7.3 to two classes (vs scope-bounding to
  Class A only) was a small edit (~80 LOC) with high-value clarity.
  Future feature flags fit one of the two classes cleanly; the
  framing prevents future "is this Class A or Class B" debate.
- **Director-takes-on-operator-question is sometimes the right move.**
  Lane V #9 M-2 (migration doc currency) and Lane V #10 S1 (§7.7.3
  framing) were both operator-surfaced "your call vs Lane D" questions.
  Director-takes-when-context-is-fresh saves a context-handoff cycle
  AND demonstrates that the asymmetric beneficiary doesn't mean
  "always defer to operator." Use when: director has fresh context +
  the artifact is director-influenceable (pattern-docs, architecture
  docs, ADRs).

### Known limitations the next director-seat should be aware of

- **U7 + U8 UX validation gap.** IterationPanel + ScreeningStage actual
  UX (verb selector layout, cost feedback, cancel mid-iterate, video
  player + markers + sidebar + Re-assemble dialog) NOT exercised since
  cycle 10. Flag-flipped surfaces are now LIVE; user-feedback path is
  direct. Real-gen validation session still on table (~$2-5).
- **Concurrency flake** `test_four_concurrent_generate_only_one_wins`
  still environment-sensitive (carry-forward from cycle 10).
- **`web_server.py` is ~2300 LoC + the B-006-broad target.** P1-2
  orchestrator extraction candidate; pending F1 decision.
- **`cinema_pipeline.py` is 1220 LoC + part of B-006 targets.** Same
  P1-2 candidate.
- **`ScreeningStage.tsx` is ~720 LoC** (unchanged cycle-11). Approaching
  sub-component extraction threshold.
- **No frontend test framework.** All UI verification via
  `tsc --noEmit` + manual smoke (carry-forward from cycle 10). M2
  doc-comment edits this cycle didn't add new UI tests.
- **1800+ pytest-leakage projects in `domain/projects/`** still
  present. U1 fix (cycle 10) makes the UX tolerable but cleanup
  script is the durable fix (Lane A candidate; carry-forward).
- **GitNexus `mutex_lock teardown` crash** continues (benign post-
  completion; carry-forward).
- **B-006 not yet scoped.** F1 decision pending. The ~22 sites are
  the full Rule #13 closure for the codebase's `mutate_project(...)`
  surface; until F1 lands they remain partial coverage.

### Verification before this handoff lands

```
$ git log --oneline b715ff9..HEAD | wc -l
12 (cycle-11 commits since cycle-10 close, all pushed; this handoff makes 13)

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
866 passed, 3 skipped, 2 warnings, 10 subtests passed
(was 856 at cycle-10 close: +10 net cycle-11; +4 from flag-flip parametrize
 expansion at 44f6beb + +3 from Lane V #9 regression at aeccc49 + +3 from
 part-11 race protection at c296105)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ (cd web && npx tsc --noEmit)
(clean; exit 0)

$ (cd web && npm run build)
✓ built in 711ms — 457.82 kB (121.24 kB gzipped)
(cycle-10 close was 457.74 kB / 121.16 kB; +0.08 kB raw / +0.08 kB gzipped
 for Lane V #10 M2 UX text edit at b71cff2)

$ ls coordination/mailbox/sent/ | grep -v gitkeep | wc -l
20 cumulative (all events processed except operator's pending pickup
 of director Lane V #10 REPLY 16:00:00Z; expected at operator's
 next session-start)

$ git rev-parse HEAD
70128700... (this handoff sits on top)

$ git rev-parse origin/main
70128700... (in-sync pre-handoff)
```

---

## Sign-off

Outgoing director-seat (cycle 11, prepared at natural session-close):
- Protocol Bundle v5.1 SHIPPED with Rules #12 + #13 codified +
  beneficiary distribution updated to 6/2/3/2 = 13 rules.
- User-principal flag-flip authorized + executed (Surface A + B
  default-ON; opt-out via `=0`).
- Lane V #9 closed at `aeccc49` (I-1 + M-1 + M-2 inline folds + 3
  regression tests; pattern-doc variant taxonomy extended).
- Lane V #10 closed at `b71cff2` (M1 + M2 inline folds + S1 §7.7.3
  expanded to two-class taxonomy).
- SHA-fill at `40d3eca` (chicken-and-egg follow-up).
- Cross-seat coord: 9 mailbox events processed (5 operator + 4
  director); 100% disposition adherence except 1 pending pickup
  (operator consumes Lane V #10 REPLY next session).
- 2 director-side IMPORTANT-or-advisory issues (Lane V #9 I-1 +
  Lane V #10 S1) closed in-cycle; 0 IMPORTANT+ issues shipped
  to origin without director-side review.
- **First operator-driven Lane B precedent established** under
  v5.1+ Sh codification. B-005 executed by operator-seat: 10
  mutators / ~45min wall-clock / ~295k tokens / Lane V #11 ✅
  READY TO SHIP at first-eligible commit.

Incoming director-seat (cycle 12): start with **STATE.md cold-read** (now a
gitignored local-only file post-Option E; hook regenerates it on each HEAD
move). Then this handoff. Then check mailbox for any operator events that
arrived since (none expected pre-session-start). Then run **cycle-12
priority scoping** — process Lane V #11 F1 decision (B-006 scope) + execute
or defer per the priorities below.

**Compound `git commit && git push` continues to work safely** as of B-003
Option E. Cycle-11 shipped 7 director compound commit+push cycles with
no stale-by-one.

*Cycle 11 was the substrate-cycle: v5.1 codified two new rules; the rules
were dogfooded successfully at first invocation; the flag-flip executed
the long-held user-principal authorization; the first operator-driven
Lane B walked through the door v5 Sh left open. **Protocol Bundle v5 + v5.1
substrate is now proven across 6 consecutive cycles (6, 7, 8, 9, 10, 11),
13 rules, 11 Lane V dispatches, ~2.37M cumulative tokens, 1 hallucination,
NO narrowing threshold crossed.** Cycle 12 inherits the cleanest substrate
state to date: 13 rules active, 2 director-seat-beneficiary rules
operating, first operator-driven Lane B precedent set, 0 unaddressed
OPEN-actionable IMPORTANT+ items, 1 pending operator-seat REPLY pickup,
1 pending director F1 decision. The substrate produces continuity, not
friction.*

Signed,
Director-seat — 2026-05-27 (cycle 11, end of session, post-v5.1-ship + flag-flip + Lane V #9/#10/#11 + first operator-driven Lane B)

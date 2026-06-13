# Director-Seat Transplant Handoff — 2026-05-26 (cycle 9)

**From:** Director-seat (outgoing this session — natural cycle-close after all 4 cycle-9 user-authorized slices shipped behind 2 feature flags + 1 IMPORTANT + 1 CRITICAL fix-on-own-findings folded + Lane V #6 + Lane V #7 both processed)
**To:** Director-seat (incoming, next session) — same seat, fresh context
**Companion (operator-seat-side):** [docs/HANDOFF-operator-transplant-2026-05-24.md](HANDOFF-operator-transplant-2026-05-24.md) (operator-seat refreshes their own; their last refresh was `48516ce` mid-cycle-9 pickup)
**Predecessor (cycle 8):** [docs/HANDOFF-director-transplant-2026-05-26-cycle8.md](HANDOFF-director-transplant-2026-05-26-cycle8.md) — read for the cycle-8 pickup; this doc carries what's NEW since cycle-8 closed at `4bf48cd`
**Post-roadmap reassessment:** [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) (last refreshed for cycle-6 P4-3 SHIPPED milestone; cycle-9 didn't trigger another rotation — cycle-9 work was on user-authorized Surface B features outside the P-priority spine)
**Purpose:** Self-contained pickup point. Cold-readable.

> **For cycle 10:** read `STATE.md` FIRST per cold-start step 0a (gitignored
> local-only artifact post-B-003 Option E; hook regenerates on each HEAD
> move). **All 11 discipline rules remain active.** If STATE.md's
> `unread mailbox` shows N ≥ 1 events for director-seat, surface to user
> per Rule #8 BEFORE processing.

---

## TL;DR — 60 seconds

**Cycle 9 is the Surface B delivery cycle.** Cycle 8 shipped Surface A
(S15-S17 + F1) behind `CINEMA_DIRECTORIAL_ITERATION`. Cycle 9 shipped
Surface B (S19-S21 — SCREENING stage + UI + re-assembly) behind
`CINEMA_SCREENING_STAGE` AND extended Surface A via S18 (PERFORMANCE_REVIEW
+ REVIEW gates + 3 structured verbs). **Both user-authorized cycle-8 product
features are now functionally complete end-to-end.** 14 commits in
`4bf48cd..e6932e3` (12 substantive + 2 cycle-8-tail docs commits). All
pushed.

- **S18 Surface A extension** (`8e11133`). Extended iterate to PERFORMANCE_REVIEW
  + REVIEW gates (was KEYFRAME_REVIEW only at S17). Added 3 structured verbs
  (`tighten_framing`, `match_shot`, `shift_emotion`) with per-call user-prompt
  prefix injection (preserves LLM cache hit rate for the dominant freeform
  case). F2 fold attempted on `approved_shots` filter (operator Lane V #6
  caught it as a no-op — see Lane V #6 fold below). 8 files, +665/-42.
- **S19 SCREENING scaffolding** (`1aca23d`). New `cinema/screening.py` module
  (~218 LoC) + 14th SCREENING stage in `cinema_pipeline.py` after ASSEMBLY +
  gate predicate (operator-signals-proceed via `lifecycle.wait_for_gate`) +
  `POST /api/projects/<pid>/assemble/screen` returning manifest +
  `POST /api/projects/<pid>/screening/approve`. Behind `CINEMA_SCREENING_STAGE`
  env flag. 5 files, +50 tests.
- **S20 ScreeningStage UI** (`fec58f7`). `web/src/components/pipeline/ScreeningStage.tsx`
  (~591 LoC) — HTML5 video + timeline markers + click-shot sidebar with take
  history + IterationPanel reuse + Approve Final Cut wired to /screening/approve.
  Re-assemble + Compare buttons stubbed for S21. 4 files, +665.
- **S21 re-assembly + Q5 spike** (`4075f8e`). `POST /api/projects/<pid>/assemble/re-assemble`
  with `only_if_changed: bool` + `needs_reassembly: list[str]` dirty-shot
  tracking + cost estimation + Re-assemble button wired with confirm dialog.
  Q5 measurement: synthetic 60-shot stitch+LUT+R128 ≈17s; real-world 60×5s
  projection ≈90s; **decision: full re-rerun for v1**. 11 files, +1200/+gates.
- **Lane V #6 IMPORTANT fold** (`6c1171a`). Operator's Lane V #6 caught
  F1 IMPORTANT: my S18 dispatch brief told the implementer to use
  `performance_take_id` per `domain/models.py:110` schema declaration, but
  production WRITES `approved_performance_take_id`. F2 fold was functionally
  a no-op. Folded F1 + F2 (double-tilde in tighten_framing prefix) + F3
  (unknown verb leaks to LLM payload) + F4 regression test that would have
  caught F1 pre-ship.
- **Lane V #7 CC-1 coalesced** (operator `fae8b5a`, decision `76e3ab0`).
  Operator's first 5-commit ceiling CC-1 dispatch on cycle-9 ship-batch
  range `10c8783..d217476`. ✅ CLEAN — 0 critical / 0 important / 7 minor
  advisories. Cross-system manifest contract verified 6/6 fields by name
  AND type. H3 + H6 folded inline with the S21 critical fix; H1/H2/H4/H5/H7
  deferred per cycle-8 pattern.
- **S19 quality fix + S21 CRITICAL fix** (`dffaed5` + `e6932e3`). MY OWN
  code-quality reviewers caught 2 IMPORTANT-class issues that operator's
  Lane V agreed with or amplified:
  - `dffaed5` — S19 manifest builder claimed to mirror `_build_scene_packages`
    but skipped `os.path.exists` check. Added opt-in `verify_files: bool=False`
    parameter — tests stay filesystem-free, endpoint enforces strict mirror.
  - `e6932e3` — S21 reassemble endpoint called `assemble_approved_takes()`
    which includes the SCREENING gate-wait when flag is on. Operator hasn't
    approved yet during iterate-then-reassemble, so Flask request would hang
    indefinitely. Extracted `_assemble_approved_takes_core()` helper for
    steps 1-5 (no gate, no cleanup, no cost summary). Added thread-bounded
    integration regression test (3s timeout) — verified by reverting + showing
    test fails at 5.19s, then reapplying + showing test passes at 1.95s.
- **Baseline at this handoff:** `pytest tests/unit/` → **841 pass / 3 skip /
  0 fail / 2 warnings** (was 737 at cycle-8 close: +104, but baseline shift
  to 742 at cycle-9 start via tail-end cycle-8 commits — net cycle-9
  delta is +99). Smoke OK. tsc + npm run build clean.

---

## Where we are — commit ledger (cycle-9 session)

14 commits since cycle-8 close at `4bf48cd`. All pushed to `origin/main`.

```
e6932e3 fix(reassemble): close S21 code-quality CRITICAL #1 — extract _assemble_approved_takes_core to avoid SCREENING gate-wait deadlock  # director
76e3ab0 coord(mailbox): decision REPLY to operator Lane V #7 — ship-as-is + H3+H6 fold deferred + cursor advance                            # director
4075f8e feat(reassemble): S21 — /assemble/re-assemble endpoint + dirty-shot tracking + ScreeningStage wiring                                 # director (Lane B subagent)
fae8b5a coord(mailbox): Lane V #7 CC-1 verification-report on 10c8783..d217476 + cursor advance                                              # operator
d217476 chore(screening-ui): fold S20 code-quality minors #2 + #5 — widen TakeRecord union + a11y on S21-stub buttons                       # director (Lane A inline fold)
fec58f7 feat(screening-ui): S20 — ScreeningStage with video player, timeline markers, take-history sidebar                                   # director (Lane B subagent)
dffaed5 fix(screening): close S19 code-quality reviewer IMPORTANT — strict manifest mirror via verify_files=True                            # director
be89189 coord(mailbox): decision REPLY to operator Lane V #6 — F1+F2+F3+F4 all folded in 6c1171a + cursor advance                          # director
6c1171a fix(iterate): close Lane V #6 F1 (vestigial-field F2 filter) + F2 + F3 + regression test                                            # director (Lane A inline)
1aca23d feat(screening): S19 — SCREENING stage scaffolding + /assemble/screen + gate predicate                                              # director (Lane B subagent)
10c8783 coord(mailbox): Lane V #6 verification-report on 8e11133 (S18) + cursor advance                                                     # operator
8e11133 feat(iterate): S18 — Surface A extension + 3 verbs + F2 fold                                                                        # director (Lane B subagent)
48516ce docs(handoff): operator-transplant cycle-8 close refresh — feature-delivery cycle, B-003 Option E, 2 Lane V dispatches              # operator (cycle-8-tail)
74f3f62 docs(backlog): seed B-004 — IterationPanel UX polish (m2 Escape-key + m3 non-JSON status context) from S17 reviewer-deferred items  # operator (cycle-8-tail)
```

**Total: 14 commits** (10 director-seat + 4 operator-seat — note: 2 of the
operator commits are cycle-8 tail that landed when operator picked up Lane V
#5 G4 + refreshed their handoff). Cycle-9 close handoff (this doc) makes 15.

**Cycle-9 vs prior cycles for context:**

| Cycle | Total commits | Headline |
|---|---|---|
| 6 | 13 | Protocol Bundle v5 SHIPPED |
| 7 | 14 | v5 dogfood + B-001 lifecycle validation |
| 8 | 24 | Feature-delivery cycle (Surface A + B-002/B-003 Option E) |
| **9** | **15** | **Surface B delivery + Surface A extension (densest USER-VISIBLE feature cycle)** |

Cycle 8 had more total commits but cycle 9 shipped 4 substantive slices
(S18, S19, S20, S21) vs cycle 8's 3 (S15, S16, S17 + F1). Cycle 9 is the
densest user-visible feature delivery to date.

---

## What's in flight (open at handoff time)

| Item | Owner (v5 framing) | What needs to happen |
|---|---|---|
| **Operator Lane V #8 expected on `4075f8e..e6932e3`** | Operator-seat | Per CC-1 disposition for fix-on-own-findings, `e6932e3` doesn't independently trigger Lane V. Operator may coalesce the whole range (S21 + decision REPLY + CRITICAL fix). Not landed at handoff time. |
| **Compare-with-previous-cut UI** | Director-seat (S22+ Lane B) | Stays stubbed in S20+S21. Per S21 reviewer Minor #4 fold (`e6932e3`), label updated from "Available in S21" → "Available in S22+". Needs a strategy: side-by-side video player? overlay diff? Requires keeping previous mp4 around. |
| **H1 — dead `approved_take_id` manifest field** | Director-seat (S22+ Lane A) | Lane V #7 H1: manifest entry declares `approved_take_id: string` but UI reads `shot.approved_final_take_id` from project state instead. Option (b) preferred — read manifest's value to align with manifest-as-assembled-truth semantics. Defer-or-fold call. |
| **H2 — walk-order divergence (`_build_timeline_manifest` vs `_find_take`)** | Either seat (S22+ helper extraction) | Lane V #7 H2: two helpers walk 4 take collections in opposite orders. Latent first-mover hazard. Extract shared `iter_takes(shot)` helper in `domain/take_lookup.py` or `domain/models.py`. |
| **H4 — test fixture direct `_running_pipelines` insertion** | Either seat (Lane A test-helper extraction) | Lane V #7 H4: tests bypass `_PIPELINE_PENDING` sentinel + `_pipelines_lock` discipline. Add `_test_inject_running_pipeline(pid, pipeline_obj)` helper. |
| **H5 — sync `os.path.exists` per shot at scale** | Telemetry watch | Lane V #7 H5: at N=500 shots, ~50ms per `/assemble/screen` call. Track in cycle-10+ telemetry; action gate: 95p shot count ≥ 100. |
| **H7 — inline `fontVariationSettings` style duplicates editorial-display** | Director-seat (S22+ style consolidation) | Lane V #7 H7: ≥2 components benefit threshold; defer until extraction is genuinely shared. |
| **B-004 — IterationPanel UX polish (m2 Escape + m3 non-JSON 502)** | Operator-seat (op claimable, ~5min Lane A) | Operator seeded at `74f3f62`. Still pending; not touched in cycle-9. |
| **Q5 follow-up measurement** | Cycle-10+ | S21 implementer's synthetic measurement at 60×1s clips gave ~17s. Real operator usage at 60×5s shots ≈ 90s projected. If real measurement diverges materially, S22+ may need delta-render OR background-job pattern. |
| **POST-ROADMAP refresh** | Director-seat (Lane A doc) | `docs/POST-ROADMAP-2026-05-24.md` last refreshed for cycle-6 P4-3 SHIPPED. Cycle-7/8/9 didn't trigger rotations (work was user-authorized features outside P-priority spine). Worth a freshness pass at cycle-10 start. |
| **No outstanding mailbox events** | Both | Mailbox state at handoff: 5 cycle-9 events all consumed by both seats. Director cursor at `2026-05-25T20:02:07Z` (consumed Lane V #7). Operator cursor expected to advance via their own next session activity. |

---

## State changes since cycle 8 (what's NEW since `4bf48cd`)

### Code + tests (the substance of cycle-9)

| Change | File(s) | Commit |
|---|---|---|
| S18 — Surface A verb DSL (3 verbs + per-call prefix injection) + PERFORMANCE_REVIEW/REVIEW gate wiring + F2 fold attempt (no-op, see Lane V #6 fold below) | `llm/director.py`, `cinema/shots/controller.py`, `web/src/components/pipeline/IterationPanel.tsx`, `ReviewStage.tsx`, `usePipelineState.ts`, `App.tsx`, `PipelineLayout.tsx`, `tests/unit/test_director.py` | `8e11133` |
| Lane V #6 F1 (vestigial-field) + F2 (double-tilde) + F3 (verb leak) + F4 (regression test) | `cinema/shots/controller.py`, `llm/director.py`, `tests/unit/test_director.py`, `tests/unit/test_iterate_endpoint.py` | `6c1171a` |
| S19 — SCREENING substrate: cinema/screening.py module (feature flag + manifest builder + gate accessor/mutator) + pipeline branch (cinema_pipeline.py:609-639) + 2 endpoints (/assemble/screen + /screening/approve) + frontend stage list (usePipelineState.ts) + 50 tests | `cinema/screening.py` (NEW), `cinema_pipeline.py`, `web_server.py`, `web/src/hooks/usePipelineState.ts`, `tests/unit/test_screening.py` (NEW), `tests/unit/test_screening_endpoint.py` (NEW) | `1aca23d` |
| S19 quality IMPORTANT — `verify_files: bool = False` opt-in for strict `_build_scene_packages` mirror | `cinema/screening.py`, `web_server.py`, `tests/unit/test_screening.py`, `tests/unit/test_screening_endpoint.py` | `dffaed5` |
| S20 — ScreeningStage.tsx (HTML5 video + timeline markers + sidebar + IterationPanel reuse + Approve Final Cut wired) + PipelineLayout SCREENING branch + usePipelineState.approveScreening + App handler | `web/src/components/pipeline/ScreeningStage.tsx` (NEW), `PipelineLayout.tsx`, `usePipelineState.ts`, `App.tsx` | `fec58f7` |
| S20 code-quality minors — TakeRecord union widening (`'performance'` added) + aria-label on S21-stub buttons | `web/src/types/project.ts`, `web/src/components/pipeline/ScreeningStage.tsx` | `d217476` |
| S21 — `/assemble/re-assemble` endpoint + `needs_reassembly: list[str]` dirty-tracking (in `regenerate_with_intent`) + cost estimation + ScreeningStage Re-assemble button wired + 42 tests | `cinema/screening.py`, `cinema/shots/controller.py`, `cinema_pipeline.py`, `web_server.py`, `web/src/components/pipeline/ScreeningStage.tsx`, `PipelineLayout.tsx`, `usePipelineState.ts`, `App.tsx`, `tests/unit/test_screening.py`, `tests/unit/test_screening_endpoint.py`, `tests/unit/test_iterate_endpoint.py`, `tests/unit/test_reassemble_endpoint.py` (NEW) | `4075f8e` |
| S21 CRITICAL fix — extract `_assemble_approved_takes_core()` helper (steps 1-5 without SCREENING gate / cleanup / cost summary). Reassemble endpoint calls helper directly. + integration regression test with 3s thread-bounded timeout + 6 minors fold (S21 reviewer #3/#4/#5/#6 + Lane V #7 H3/H6) | `cinema_pipeline.py`, `web_server.py`, `cinema/shots/controller.py`, `cinema/screening.py`, `web/src/components/pipeline/ScreeningStage.tsx`, `web/src/hooks/usePipelineState.ts`, `tests/unit/test_reassemble_endpoint.py` | `e6932e3` |

Test count progression: cycle-8 close 737 → cycle-9 start (after cycle-8-tail
operator commits) ≈ 742 → S18 (+5 verbs) → S19 (+50 screening) → S19 quality
fix (+5 verify_files) → Lane V #6 fix (+1 F4 regression) → S20 (+0 frontend)
→ S21 (+42) → S21 critical fix (+1 integration) → **841 total at cycle-9
close**. Warning count: 2 → 2 (no new warnings introduced).

### Docs + protocol

| Change | File(s) | Commit |
|---|---|---|
| B-004 BACKLOG seed (IterationPanel UX polish — m2 Escape + m3 non-JSON 502 context) | `docs/BACKLOG.md` | `74f3f62` (operator, cycle-8-tail) |

### Coordination + mailbox

5 mailbox events total this cycle (3 operator + 2 director). All processed.

| Event | File | Sender | Commit |
|---|---|---|---|
| Operator Lane V #6 verification-report on `8e11133` (S18) — F1 IMPORTANT (vestigial-field) + F2/F3/F4 minors | `2026-05-25T18-20-57Z-operator-to-director-verification-report.md` | operator | `10c8783` |
| Director Lane V #6 decision REPLY — all 4 folded in `6c1171a` + operational learning candidate logged | `2026-05-25T18-44-52Z-director-to-operator-decision.md` | director | `be89189` |
| Operator Lane V #7 CC-1 coalesced verification-report on `10c8783..d217476` (5-commit ceiling case) — 0 critical / 0 important / 7 minor (H1-H7) | `2026-05-25T20-02-07Z-operator-to-director-verification-report.md` | operator | `fae8b5a` |
| Director Lane V #7 decision REPLY — ship-as-is; H3+H6 fold deferred to S21 post-review; H1/H2/H4/H5/H7 deferred | `2026-05-25T20-13-11Z-director-to-operator-decision.md` | director | `76e3ab0` |

Director cursor (`coordination/mailbox/seen/director.txt`): cycle-8 close
`16:19:27Z` → `18:20:57Z` → `20:02:07Z` (current, post-Lane-V-#7). All
operator events consumed.

### Memory + index

- Memory file `director_transplant_handoff.md` to be updated in this handoff
  commit to point at cycle-9 doc.
- `MEMORY.md` index entry updated similarly.

---

## What I would do next, if I had the context

**Top 3 priorities for cycle 10 (in order):**

1. **POST-ROADMAP refresh + cycle-10 priority scoping** — Lane A doc work.
   `docs/POST-ROADMAP-2026-05-24.md` last refreshed for cycle-6 P4-3
   SHIPPED. Cycle-7/8/9 didn't trigger rotations because work was on
   user-authorized features (Surface A + B) outside the P-priority spine.
   With both surfaces now functionally complete, cycle 10 inherits a
   genuinely OPEN priority slate. Likely re-prioritization candidates:
   - **P1 (Pydantic migration)** — was the largest open backlog item.
     Parts 1-6 shipped; how many remain? Worth a candidate hunt at
     cycle-10 start.
   - **Surface A+B operator-facing validation** — both surfaces are
     feature-flagged + tsc-clean but NEVER manually tested in a browser
     by a real operator. Cycle 10 could include "ship the flag flip" if
     operator validation passes.
   - **S22+ Surface C/D ideas** — Compare-with-previous-cut, helper
     extractions (H2 walk-order, H4 test-helper, H7 style consolidation).
     User-authorized? If yes, draft proposal.

2. **Operator Lane V #8 processing** — when it lands. Cycle-9 ship-batch
   `4075f8e..e6932e3` is what Lane V #8 will cover (per CC-1 disposition,
   fix-on-own-findings `e6932e3` doesn't independently trigger, but
   operator may coalesce). If clean: acknowledge + cursor advance. If
   findings: fold per established pattern.

3. **Cycle-9 operational-learning codification decision** — TWO candidate
   learnings surfaced this cycle, both NOT yet codified as Rules:
   - **"Brief-level grep-the-writes discipline"** (cycle-9 Lane V #6 F1
     root cause) — my dispatch brief told the implementer to use a field
     name based on the schema DECLARATION (`domain/models.py:110`) without
     grepping for production WRITE sites. Cycle-8 had a similar
     reviewer-scoped learning ("verify ADJACENT-FILE-AREA siblings BEFORE
     generalizing"); this is the brief-level generalization. N=1 instance.
     Lane V #7 spec-reviewer prompt applied this discipline preventively
     and caught 0 new divergences — first PREVENTIVE application worked.
     One more instance (cycle-10 or later) justifies codifying as Rule
     #12.
   - **"Tests that mock the orchestrator level cannot catch deadlocks in
     the orchestrator itself"** (cycle-9 S21 CRITICAL #1 root cause) —
     all 13 S21 endpoint tests mocked `assemble_approved_takes` entirely;
     none exercised the real orchestrator code path. Mitigation pattern
     shipped in `e6932e3`: thread-bounded integration test with deliberate
     mock-too-low boundary. N=1. Not yet justified as a Rule (could be
     cycle-9 coincidence; needs another instance to differentiate from
     "the orchestrator happens to have a gate-wait shipped recently").
     If cycle-10+ surfaces another similar miss, codify.

**Other cycle-10 considerations:**

- **Surface A + B operator validation in a browser** — both feature flags
  flip behavior; both surfaces are tsc-clean + npm-build-clean. Real
  operator validation would surface UX issues (e.g., S20 sidebar layout
  on narrow viewports, S21 cost-estimate accuracy on real projects, Q5
  measurement drift, etc.). Could be operator-claimable or director-
  dispatch as a Lane B "playthrough + report" task.
- **ARCHITECTURE.md §16 doc-sync** — Section may need refresh after
  S19+S20+S21 added 3 new endpoints + new module + new pipeline stage.
  Operator-default per Lane D convention; check if their next session
  picks it up.
- **`memory-candidate` first-fire** — still pending. v5 §M defined but
  never dogfooded.
- **Lane S `scout-request` first-fire** — still pending. Cycle-8/9 dispatch
  briefs were rich enough that scout-request was discarded each time.
  May fire on a S22+ dispatch where the brief is genuinely uncertain.

---

## Important context the next director-seat needs

### Discipline rules in effect (all 11)

- **Rules #1-#11**: unchanged from cycle-8. No new rules cycle-9.
- **Cycle-9 added TWO operational learnings (NOT codified as Rules)** —
  see "What I would do next" #3 above for the codification-decision
  framing. Both are N=1 instances; cycle-10+ provides the data to
  decide.

### Protocol Bundle v5 substrate — telemetry update

**Cumulative across cycles 6-9** (7 Lane V dispatches; CC-2 + R-9-1 + CC-1
disciplines applied):

- **Dispatches:** 7 total (cycle-6 #1+#2, cycle-7 #3, cycle-8 #4+#5,
  cycle-9 #6+#7)
- **Tokens:** ~1.46M cumulative
- **Novel findings:** ~20 total (cycle-6 F1 critical + F2; cycle-7 F1/F2/F3
  minor; cycle-8 #4 F1-F5 minor + F0 resolved + cycle-8 #5 G1-G4 minor;
  cycle-9 #6 F1 IMPORTANT + F2-F4 minor + cycle-9 #7 H1-H7 minor)
- **Hallucinations:** **0 across all 7 dispatches.** CC-2 (verify-before-
  asserting) + R-9-1 (cold prompt construction) + CC-1 (5-commit-ceiling
  coalescing) all working as designed.
- **v4.1 narrowing threshold (>1.5M tokens AND <15% catch rate):** NOT
  crossed. Per-commit-trigger dispatch frequency remains correct per R-V1.
  Catch rate ~14% (20 findings / 144 reviewed commits) at the boundary;
  Lane V #6 IMPORTANT + S19/S21 director-side IMPORTANT both validate
  signal density still justifies cost.
- **CC-1 coalescing validated at 5-commit ceiling in cycle 9.** Operator's
  Lane V #7 first 5-commit-range dispatch on `10c8783..d217476` preserved
  cross-system manifest contract verification (6/6 fields verified by
  name AND type) that per-commit dispatch would have lost. **Endorsed
  recommendation:** when a multi-commit batch shares a contract surface
  (backend emit ↔ frontend consume), CC-1 is strictly better than
  per-commit dispatch even when commits land minutes apart.

### Cycle-9 protocol learnings (worth carrying forward)

- **Director-side reviewers caught BOTH cycle-9 IMPORTANT issues** (`dffaed5`
  manifest mirror gap + `e6932e3` SCREENING gate-wait deadlock). Pattern:
  my own reviewers + operator's Lane V converge on different angles.
  Director-side reviewers tend to catch architectural correctness; operator's
  Lane V tends to catch contract/integration. Both layers needed.
- **Iterative-internal-review-then-ship pattern works.** Lane V #7 explicit
  acknowledgment: "Director-seat's internal reviewers caught the only
  IMPORTANT (manifest mirror gap) in `dffaed5` before UI ship — the
  iterative-internal-review-then-ship pattern works." This is the strongest
  validation of the multi-task plan discipline to date.
- **Brief-level claims need the same grep-the-writes discipline reviewers
  apply.** Lane V #6 F1 root cause was MY brief over-trusting a schema
  declaration. Cycle-8 codified reviewer-scoped sibling-check; cycle-9
  is the brief-scoped generalization. PREVENTIVELY applied in Lane V #7
  spec prompt; 0 new divergences caught. One more PREVENTIVE application
  justifies codifying as Rule #12.
- **Mock-too-high tests can hide orchestrator bugs.** S21's 13 endpoint
  tests mocked `assemble_approved_takes` entirely; the new SCREENING
  gate-wait inside the orchestrator was never exercised. Mitigation
  shipped in `e6932e3`: integration test with deliberate mock-too-low
  boundary + thread-bounded timeout. Useful pattern when orchestrator
  changes shape mid-cycle.
- **Cross-seat mailbox loop scales to dense cycles.** Cycle 9's 5 events
  (3 operator + 2 director) handled without overhead. Both seats stayed
  in their lane; no scope conflicts. Equivalent density to cycle 8's 5
  events but with HIGHER signal value (Lane V #6 IMPORTANT vs cycle-8's
  all-minor advisories).

### Known limitations the next director-seat should be aware of

- **Surface A + B are flag-gated but never tested in a real operator's
  browser.** All UI verification is via `npx tsc --noEmit` + `npm run
  build` (project convention: no React unit test framework). Real
  operator playthrough is needed before flipping defaults.
- **Q5 measurement is synthetic.** Implementer measured 60×1s stub mp4s
  at 1920x1080@30fps. Real shots may be 5-10s at sometimes 4K. The
  "~90s for 60 real shots" projection is reasonable but not validated.
  Worth a real-project re-measurement when one exists.
- **`Compare with previous cut` button is permanently visible but disabled.**
  S20 stubbed it; S21 reviewer asked to update label "S21" → "S22+";
  done in `e6932e3`. No timeline for actually implementing — needs design
  thought (side-by-side video? overlay diff?).
- **`cinema/screening.py` is now ~470 LoC** with 7 public functions +
  constants. Likely the right boundary; if it grows past ~700 LoC, split
  into `cinema/screening/manifest.py` + `cinema/screening/gate.py` +
  `cinema/screening/reassemble.py`.
- **`web_server.py` is ~2100+ LoC** (post-S19+S21 endpoint additions).
- **`ScreeningStage.tsx` is ~720 LoC** (post-S21 button wiring + dirty
  badge + error banner + cache-bust). Approaching the unwieldy threshold;
  may benefit from extracting MarkerTrack + TakeCard + Sidebar
  sub-components in S22+.
- **No frontend test framework** (project convention: `tsc --noEmit` +
  manual smoke). Cycle-9 added significant UI surface (S20+S21); manual
  verification is the only correctness gate beyond type-checking.
- **GitNexus `mutex_lock teardown` crash** continues on every `analyze
  --embeddings` (benign post-completion).
- **P1-3 part 7+ candidate hunt deferred.** Cycle-9 didn't continue P1-3
  (focus was on user-authorized features). Cycle 10 may resume if
  candidates exist — grep targets: `project["scenes"]` / `project["characters"]`
  / `project["locations"]` in read-only consumer code NOT in `cinema/phases/*`,
  NOT in `domain/*`, NOT in write paths.

### Verification before this handoff lands

```
$ git log --oneline 4bf48cd..HEAD | wc -l
14 (cycle-9 commits since cycle-8 close, all pushed; this handoff makes 15)

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
841 passed, 3 skipped, 2 warnings, 10 subtests passed
(was 737 at cycle-8 close: +104 total; +99 net cycle-9 if we exclude the
 tail-end cycle-8 tests landed via operator's BACKLOG seed + transplant
 refresh; warnings unchanged at 2 — no new warnings introduced this cycle)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ cd web && npx tsc --noEmit
(clean)

$ cd web && npm run build
85 modules / built ~700ms / clean (456.37 kB / 120.76 kB gzipped)

$ ls coordination/mailbox/sent/ | grep -v gitkeep | wc -l
9 cumulative (all events processed; director cursor at 2026-05-25T20:02:07Z)

$ git rev-parse HEAD
e6932e3... (this handoff sits on top)

$ git rev-parse origin/main
e6932e3... (in-sync pre-handoff)
```

---

## Sign-off

Outgoing director-seat (cycle 9, prepared at natural session-close):
- All cycle-9 user-authorized work shipped: S18 (Surface A extension) +
  S19+S20+S21 (Surface B end-to-end) + Lane V #6 IMPORTANT fold + S19
  quality IMPORTANT + S21 CRITICAL fix.
- Both feature flags (`CINEMA_DIRECTORIAL_ITERATION` + `CINEMA_SCREENING_STAGE`)
  gate functionally-complete surfaces.
- Cycle-9 close commit-batch pushed to `origin/main` pre-handoff; this
  handoff makes 15 commits total.
- Cross-seat coord: operator's 2 Lane V verification-reports processed
  and acknowledged via decision REPLYs; 4 of 4 F-advisories closed
  (Lane V #6) + 2 of 7 H-advisories folded inline + 5 of 7 deferred
  with rationale (Lane V #7).
- 2 director-side IMPORTANT issues caught by my own reviewers and folded
  pre-push (`dffaed5` + `e6932e3`); 0 IMPORTANT-class issues shipped to
  origin without director-side review.

Incoming director-seat (cycle 10): start with **STATE.md cold-read** (now a
gitignored local-only file post-Option E; hook regenerates it on each HEAD
move). Then this handoff. Then check mailbox for any operator events that
arrived since (expected: Lane V #8 CC-1 on `4075f8e..e6932e3`; not landed
at handoff time). Then run **cycle-10 priority scoping** — POST-ROADMAP
refresh + operator-validation discussion + decide on cycle-10 picks.

**Compound `git commit && git push` continues to work safely** as of B-003
Option E. Cycle-9 shipped 6 compound commit+push cycles with no stale-by-one.

*Cycle 9 delivered the highest user-visible feature density of any cycle
to date: 4 substantive slices end-to-end across 2 feature flags. Surface
A + Surface B are now both functionally complete and ready for operator
validation before flag-flip. The substrate that enabled this — Protocol
Bundle v5, the cross-seat mailbox loop, Lane V/D/S, CC-2 + R-9-1 + CC-1,
the iterative-internal-review-then-ship pattern — is now proven across 4
consecutive cycles. Cycle-10 inherits the cleanest state in 9 cycles: 0
in-flight WT items, 0 unread mailbox, 1 expected-but-not-yet-landed Lane V
on the close range, 0 unaddressed IMPORTANT-class advisories. The substrate
produces continuity, not friction.*

Signed,
Director-seat — 2026-05-26 (cycle 9, end of session, post-Surface-B-ship)

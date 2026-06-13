# Director-Seat Transplant Handoff — 2026-05-26 (cycle 10)

**From:** Director-seat (outgoing this session — natural cycle-close after Lane V #8 fully closed + both Val#1+#2 actionable findings folded + all cycle-10 P1-3 candidates closed + operator-validation reports processed)
**To:** Director-seat (incoming, next session) — same seat, fresh context
**Companion (operator-seat-side):** [docs/HANDOFF-operator-transplant-2026-05-24.md](HANDOFF-operator-transplant-2026-05-24.md) (operator-seat refreshes their own; their last refresh was `29dc80f` cycle-9 in-flight, then Lane V #8 + 2 validation reports in cycle 10)
**Predecessor (cycle 9):** [docs/HANDOFF-director-transplant-2026-05-26-cycle9.md](HANDOFF-director-transplant-2026-05-26-cycle9.md) — read for the cycle-9 pickup; this doc carries what's NEW since cycle-9 closed at `17a06c1`
**Post-roadmap reassessment:** [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) (refreshed at cycle-10 open via `8f8190e`)
**Operator-validation brief:** [docs/BRIEF-operator-validation-2026-05-26.md](BRIEF-operator-validation-2026-05-26.md) (authored cycle-10 + refreshed twice post-fixes)
**Purpose:** Self-contained pickup point. Cold-readable.

> **For cycle 11:** read `STATE.md` FIRST per cold-start step 0a (gitignored
> local-only artifact post-B-003 Option E; hook regenerates on each HEAD
> move). **All 11 discipline rules remain active.** If STATE.md's
> `unread mailbox` shows N ≥ 1 events for director-seat, surface to user
> per Rule #8 BEFORE processing.

---

## TL;DR — 60 seconds

**Cycle 10 is the cycle-9-close-loop cycle.** Cycle 9 shipped Surface A
+ Surface B end-to-end behind feature flags but never exercised by a
real operator. Cycle 10 closed the loop: operator dispatched Lane V #8
(catching a CRITICAL ship-blocker pre-emptively) + ran the
operator-validation brief in two sessions (Val#1 backend contract +
Val#2 UX layer) + I shipped fixes for everything findable in 14
commits. **Both feature flags are now flag-flip-recommended** (Surface
A YES; Surface B YES with V1 fold complete at `d10b849`). 18 commits
in `17a06c1..dea4cc8` (14 director + 4 operator). All pushed.

- **Lane V #8 closure (`b6bb76c..0668117`)** — operator caught I1 CRITICAL
  (iterate-during-gate-wait busy-fenced; Surface B unreachable as
  shipped) + I2 IMPORTANT (SSE leak) + I3 IMPORTANT (dirty-tracking race
  unmasked by I1) + 3 MINOR + 1 hallucination. **Rule #9's strongest
  validation case to date** — cold-context reviewer caught a symmetric
  structural blind spot internal review missed. Director-seat shipped
  I1+I2+I3 fix-set at `9e9b008` (gate-aware bypass + SSE silence +
  set-diff clear); operator confirmed closure at `0668117`.
- **H4 inline fold (`b6bb76c`)** — Lane V #7 H4 advisory (test-fixture
  direct `_running_pipelines` insertion bypassing lock discipline)
  closed via shared `inject_pipeline` pytest fixture + 7-site migration.
  Lucky timing: the fixture became exactly the test-infrastructure
  needed for the I1 fix's regression tests.
- **P1-3 parts 7-10 (`9a88191..1bc9263`)** — 4 caller migrations
  closing ALL cycle-10 P1-3 audit candidates: `_get_used_voices`
  (character_manager) + `get_character` + `get_location`
  (project_manager) + `update_scene_shots` mutator (scene_decomposer, NEW
  pattern variant) + `CharacterContinuityTracker` + `LocationPersistence`
  inits + `cinema_pipeline._reload_project` external writer
  (continuity_engine multi-file). Pattern variants now validated across
  9 canonical applications (S10 + parts 3-10).
- **Operator validations #1 + #2 (`18beb92` + `8d5e2d4`)** — operator
  ran the brief I authored at `a116e0a`. 16 findings across 2 sessions,
  ~55% coverage. Backend contract layer fully validated (I1+I3 LIVE
  7/7 + 5/5 tests pass); UX layer partial (app shell + pipeline mode +
  PLAN_REVIEW + 14-stage rail confirmed; IterationPanel + ScreeningStage
  UX deferred per cost-bounded scope). Both surfaces recommended SAFE
  TO FLIP.
- **Val#1 V1 fix (`d10b849`)** — `/screening/approve` lacked precondition
  check (could permanently flip persistent gate-flag on never-screened
  project). Mirror of `/assemble/screen`'s `os.path.exists(final_cinema.mp4)`
  guard. **Second symmetric-endpoint-audit instance — N=2 codification
  candidate for v5.1 Rule #13** (paired with Lane V #8 I1 which was
  the first N=1 instance).
- **Val#2 U1 fix (`dea4cc8`)** — project landing page rendered all 1885
  projects (mostly pytest leakage) with no pagination/search/sort. Fixed
  via backend `list_projects` mtime-DESC sort + frontend search + show-
  top-20-with-toggle paginate.
- **Baseline at this handoff:** `pytest tests/unit/` → **856 pass / 3 skip
  / 0 fail / 2 warnings** (was 841 at cycle-9 close: +15 net cycle-10).
  Smoke OK. tsc + npm run build clean. All pushed. **0 in-flight WT,
  0 unread mailbox, 0 unaddressed OPEN-actionable advisories.**

---

## Where we are — commit ledger (cycle-10 session)

18 commits since cycle-9 close at `17a06c1`. All pushed to `origin/main`.

```
dea4cc8 fix(landing): close Val#2 U1 — list_projects mtime-DESC + ProjectSelector search + paginate     # director
4ac1bdf docs(brief): refresh operator-validation pre-flight per Val#1 + V1 fix                          # director
d10b849 fix(screening): close Val#1 V1 — /screening/approve precondition check                          # director
9f652a2 coord(mailbox): combined decision REPLY for Val#1 + Val#2                                       # director
1bc9263 feat(schema): P1-3 part 10 — CharacterContinuityTracker + LocationPersistence + cinema_pipeline # director (multi-file)
8d5e2d4 coord(mailbox): operator-validation #2 verification-report — UX layer partial                   # operator
18beb92 coord(mailbox): operator-validation #1 verification-report — backend contract validated          # operator
f8cd45f feat(schema): P1-3 part 9 — update_scene_shots mutator (NEW pattern variant)                    # director
0883201 feat(schema): P1-3 part 8 — get_character + get_location                                        # director
9a88191 feat(schema): P1-3 part 7 — _get_used_voices                                                    # director
0668117 coord(mailbox): cursor advance to 2026-05-26T07:20:00Z — Lane V #8 closed                       # operator
0aa1ae5 docs(brief): refresh operator-validation pre-flight — note I1 fix at 9e9b008                    # director
9e9b008 fix(iterate+reassemble): close Lane V #8 I1 CRITICAL + I2 + I3                                  # director
345c6e3 coord(mailbox): decision REPLY to operator Lane V #8                                            # director
b6bb76c test(conftest): close H4 from Lane V #7 — inject_pipeline fixture + migrate 7 sites             # director
6c0eefd coord(mailbox): Lane V #8 verification-report on 4075f8e..e6932e3                               # operator
a116e0a docs(brief): operator-validation protocol for Surface A + B                                     # director
8f8190e docs(roadmap): POST-ROADMAP cycle-10 banner refresh                                             # director
```

**Total: 18 commits** (14 director + 4 operator). Cycle-10 close handoff
(this doc) makes 19.

**Cycle-10 vs prior cycles for context:**

| Cycle | Total commits | Headline |
|---|---|---|
| 6 | 13 | Protocol Bundle v5 SHIPPED |
| 7 | 14 | v5 dogfood + B-001 lifecycle validation |
| 8 | 24 | Feature-delivery cycle (Surface A + B-002/B-003 Option E) |
| 9 | 15 | Surface B delivery + Surface A extension |
| **10** | **18** | **Cycle-9-close-loop: Lane V #8 + ops validation + V1/U1 + 4 P1-3 parts** |

Cycle 10 is the second-densest mailbox cycle (5 events) but the highest
operator-validation density to date (2 verification-reports running the
authored brief end-to-end).

---

## What's in flight (open at handoff time)

| Item | Owner (v5 framing) | What needs to happen |
|---|---|---|
| **Operator Lane V #9 expected on `0668117..1bc9263`** | Operator-seat | 4 P1-3 schema commits since Lane V #8 closed; CC-1 candidate (4 within 5-commit ceiling). Operator race-acked in Val#2 ("Lane V #9 trigger open per Rule #9 + R-V1"). Not landed at handoff time. |
| **Flag-flip authorization (Surfaces A + B)** | User-principal | Both surfaces recommended SAFE TO FLIP per BRIEF §1 (Surface A YES; Surface B YES with V1 fix already shipped). Decision is user's call. |
| **U7 + U8 NOT-VALIDATED (UX layer gap)** | User-principal | IterationPanel + ScreeningStage actual UX not exercised due to cost-bounded validation. Options per Val#1+#2 REPLY: (a) approve real-generation session (~$2-5 LLM/Veo), (b) flip flags + accept early-user feedback, (c) defer flip until real-operator drives end-to-end. |
| **Pytest-leakage cleanup** | Either seat (Lane A script) | Operator's "cheap mitigation" note from Val#2 U1 — 1800+ pytest-fixture projects in `domain/projects/` clutter the landing page. `scripts/clean_test_fixtures.py` would identify + remove (heuristic: name matches `Test Project|Guided Tool|ShotTest|CharTest|*Test*` + small project.json size). Lane A, ~30-45 min. Not blocking; durable UX fix shipped at `dea4cc8` makes this lower priority. |
| **Protocol bundle v5.1 — 2 codification candidates at N=2** | Director-seat (proposal draft) | (a) Brief-level grep-the-writes (Lane V #6 F1 N=1 + Lane V #8 spec-prompt preventive N=2) — Rule #12 candidate. (b) Symmetric-endpoint audit (Lane V #8 I1 iterate-bypass-missing N=1 + Val#1 V1 approve-precondition-missing N=2) — Rule #13 candidate. Both meet director's own "N=2 justifies codification" criterion from Lane V #6 REPLY. Draft as `docs/PROPOSAL-protocol-bundle-v5.1-2026-05-2X.md`. |
| **V2 + U2 MINOR deferred** | Either seat (Lane A opportunistic) | V2 (dangling colon in re-assemble error) + U2 (no observation-only pipeline-mode entry). Both deferrable; fold next time the affected code is in scope. |
| **No outstanding mailbox events** | Both | Mailbox state at handoff: 5 cycle-10 events all consumed by both seats. Director cursor at `2026-05-26T08:30:00Z` (consumed Val#2). Operator cursor expected to advance via their next Lane V #9 dispatch. |

---

## State changes since cycle 9 (what's NEW since `17a06c1`)

### Code + tests (the substance of cycle-10)

| Change | File(s) | Commit |
|---|---|---|
| H4 inject_pipeline fixture + migrate 7 test sites to canonical _pipelines_lock pattern | `tests/conftest.py`, `tests/unit/test_screening_endpoint.py`, `tests/unit/test_reassemble_endpoint.py`, `tests/unit/test_project_persistence.py` | `b6bb76c` |
| Lane V #8 I1 CRITICAL + I2 + I3 fix-set — gate-aware bypass (`_GATE_STAGES` + `_pipeline_at_gate_stage` + `_reject_if_project_busy_outside_gate`) + SSE silence (re-assemble progress_callback) + set-diff clear (`clear_needs_reassembly` only_shots) + 12 new tests | `web_server.py`, `cinema/screening.py`, `tests/unit/test_iterate_endpoint.py`, `tests/unit/test_screening.py`, `tests/unit/test_reassemble_endpoint.py` | `9e9b008` |
| P1-3 part 7 — `_get_used_voices` typed set-comp on `project_typed.characters` | `domain/character_manager.py` | `9a88191` |
| P1-3 part 8 — `get_character` + `get_location` typed iteration + index-back-to-raw-dict (caller identity preservation) | `domain/project_manager.py` | `0883201` |
| P1-3 part 9 — `update_scene_shots` mutator + NEW pattern variant (outer boundary validate + inner mutator typed-iterate + dict-write under mutate_project lock) | `domain/scene_decomposer.py` | `f8cd45f` |
| P1-3 part 10 — `CharacterContinuityTracker.__init__` + `LocationPersistence.__init__` + `cinema_pipeline._reload_project` external writer; value-preserving variant (dict reference preservation via index for downstream consumer compat) | `domain/continuity_engine.py`, `cinema_pipeline.py` | `1bc9263` |
| Val#1 V1 fix — `/screening/approve` precondition check (mirrors `/assemble/screen`); +1 regression test + 5 existing tests updated to tempdir-stub the assembled mp4 | `web_server.py`, `tests/unit/test_screening_endpoint.py` | `d10b849` |
| Val#2 U1 fix — `list_projects` mtime-DESC + malformed-json defensive skip; `ProjectSelector` search input + show-top-20-with-toggle paginate; +2 backend regression tests (sort-order + missing-json) | `domain/project_manager.py`, `tests/unit/test_project_manager.py`, `web/src/components/ProjectSelector.tsx` | `dea4cc8` |

Test count progression: cycle-9 close 841 → b6bb76c (H4: 0 new) → 9e9b008
(I1+I3: +12 = 853) → 9a88191/0883201/f8cd45f/1bc9263 (P1-3 parts 7-10:
0 new; semantic equivalence verified by full-suite passing) → d10b849
(V1: +1 = 854) → dea4cc8 (U1: +2 = **856** total at cycle-10 close).
Warning count: 2 → 2 (no new warnings introduced).

### Docs + protocol

| Change | File(s) | Commit |
|---|---|---|
| POST-ROADMAP cycle-10 banner refresh — open priority slate post-Surface-B + flake triage + filled cycles 7-9 ship history | `docs/POST-ROADMAP-2026-05-24.md` | `8f8190e` |
| BRIEF operator-validation protocol authored (~250 lines) + POST-ROADMAP cross-link from top-3 #1 | `docs/BRIEF-operator-validation-2026-05-26.md` (NEW), `docs/POST-ROADMAP-2026-05-24.md` | `a116e0a` |
| BRIEF refresh post-I1 fix — note I1 fix at 9e9b008 + bump expected pytest count | `docs/BRIEF-operator-validation-2026-05-26.md` | `0aa1ae5` |
| BRIEF refresh post-Val#1+#2 — port 5173→3000 + populated-project fallback + V1 commit references | `docs/BRIEF-operator-validation-2026-05-26.md` | `4ac1bdf` |

### Coordination + mailbox

5 mailbox events total this cycle (3 operator + 2 director). All processed.

| Event | File | Sender | Commit |
|---|---|---|---|
| Operator Lane V #8 verification-report on `4075f8e..e6932e3` (S21 substrate) — 1 CRITICAL + 2 IMPORTANT + 3 minor + 1 hallucination | `2026-05-26T05-15-00Z-operator-to-director-verification-report.md` | operator | `6c0eefd` |
| Director Lane V #8 decision REPLY — I1+I2+I3 fold-inline + cursor advance | `2026-05-26T07-20-00Z-director-to-operator-decision.md` | director | `345c6e3` |
| Operator Val#1 verification-report — backend contract validated; UX layer deferred (Chrome ext + populated project blockers) | `2026-05-26T08-00-00Z-operator-to-director-verification-report.md` | operator | `18beb92` |
| Operator Val#2 verification-report — UX layer partial (app shell + pipeline mode + PLAN_REVIEW + 14-stage rail confirmed) | `2026-05-26T08-30-00Z-operator-to-director-verification-report.md` | operator | `8d5e2d4` |
| Director combined Val#1+#2 decision REPLY — V1 FOLD + U1 DEFER + flag-flip recommendations + cursor advance | `2026-05-26T12-40-00Z-director-to-operator-decision.md` | director | `9f652a2` |

Director cursor (`coordination/mailbox/seen/director.txt`): cycle-9 close
`20:02:07Z` → `05:15:00Z` (Lane V #8) → `08:30:00Z` (current, post-Val#2).
All operator events consumed.

### Memory + index

- Memory file `director_transplant_handoff.md` to be updated in this handoff
  commit to point at cycle-10 doc.
- `MEMORY.md` index entry updated similarly.

---

## What I would do next, if I had the context

**Top 3 priorities for cycle 11 (in order):**

1. **Process operator Lane V #9 on P1-3 parts 7-10** — expected per CC-1
   (4 commits within 5-commit ceiling; tightly coupled same-template
   slice). When it lands: acknowledge + cursor advance if clean; fold
   per established pattern if findings. Per cumulative telemetry, 8 Lane
   V dispatches across cycles 6-10 have produced 1 CRITICAL (I1 cycle-10)
   + 0 IMPORTANT-from-spec-reviewer + 1 hallucination. Lane V's value
   proposition continues to compound.

2. **Flag-flip decision execution OR defer-with-rationale** — user-
   principal decided on the Val#1+#2 REPLY's question. If user approves
   flip:
   - Flip `CINEMA_DIRECTORIAL_ITERATION` to default-on (env-var → app
     default change; ~5 LoC + 1 test + docs)
   - Flip `CINEMA_SCREENING_STAGE` to default-on (same shape)
   - Optionally: real-generation validation session first if budget
     approved
   - Drop the env-var entirely OR keep as opt-out — design call
   If user defers: file the decision in DECISIONS.md as an ADR so the
   next cycle has clear context.

3. **Protocol bundle v5.1 codification draft** — both candidates at N=2
   per my own criterion:
   - **Rule #12 candidate** — brief-level grep-the-writes discipline
     (Lane V #6 F1 root cause N=1 + Lane V #8 spec-prompt preventive
     application N=2 with 0 new divergences)
   - **Rule #13 candidate** — symmetric-endpoint-audit discipline (Lane V
     #8 I1 iterate-bypass-missing N=1 + Val#1 V1 approve-precondition-
     missing N=2). Codifies "when adding a new gate-acting endpoint,
     audit existing endpoints for parallel checks."
   Draft as `docs/PROPOSAL-protocol-bundle-v5.1-2026-05-2X.md`.
   Operator-seat REPLY cycle per established v2-v5 pattern; ship if
   no major refinements.

**Other cycle-11 considerations:**

- **Pytest-leakage cleanup script** — `scripts/clean_test_fixtures.py`;
  Lane A; ~30-45 min. Heuristic on names + project.json size. Lower
  priority than the UX fix shipped at `dea4cc8` which is durable
  regardless of leak.
- **Real-generation validation session** (if budget approved) — drive a
  small 3-shot project end-to-end through SCREENING + iterate-from-
  screening + re-assemble. Closes U7 + U8 NOT-VALIDATED gap from Val#2.
  Cost: ~$2-5 LLM/Veo + ~60 min wall-clock.
- **V2 + U2 MINOR opportunistic folds** — re-assemble error empty-list
  branch + observation-only pipeline-mode entry. Wait for the affected
  code to be in scope for another reason.
- **`memory-candidate` mailbox first-fire** — still pending. v5 §M
  defined but never dogfooded.
- **Lane S `scout-request` first-fire** — still pending. Cycle-10
  dispatches all had rich-enough briefs; never fired. Will fire when a
  future dispatch brief is genuinely uncertain.

---

## Important context the next director-seat needs

### Discipline rules in effect (all 11)

- **Rules #1-#11**: unchanged from cycle-9. No new rules cycle-10.
- **Cycle-10 added/promoted TWO operational learnings to N=2** —
  see "Top 3 priorities #3" above. Both meet director's own
  N=2-justifies-codification criterion. Drafting Rule #12 + #13
  proposals is appropriate cycle-11 work.

### Protocol Bundle v5 substrate — telemetry update

**Cumulative across cycles 6-10** (8 Lane V dispatches; CC-2 + R-9-1 +
CC-1 disciplines applied):

- **Dispatches:** 8 total (cycle-6 #1+#2, cycle-7 #3, cycle-8 #4+#5,
  cycle-9 #6+#7, cycle-10 #8)
- **Tokens:** ~1.70M cumulative (per Lane V #8 telemetry footer)
- **Novel findings:** ~26 total (incremental Lane V #8: 1 CRITICAL +
  2 IMPORTANT + 3 MINOR + 1 hallucination = 7 findings)
- **Hallucinations:** **1 across all 8 dispatches** (first; I7 at Lane
  V #8 — code-quality reviewer falsely claimed dirty working tree).
  Cycle-10 telemetry per Lane V #8: 1/8 dispatches; ~3.8% finding-rate
  noise floor. Operator's lean (accepted) — within tolerable.
- **v4.1 narrowing threshold (>1.5M tokens AND <15% catch rate):** NOT
  crossed at N=8. Catch rate stays high — Lane V #8's I1 CRITICAL is
  the most material finding to date (release blocker neither director
  internal review nor cycle-9 dispatches caught).
- **Lane V #8 = strongest Rule #9 validation case** — cold-context
  reviewer caught a symmetric structural blind spot internal review
  missed. Director-seat's internal reviewers (running with full design-
  intent context, knowing the helper extraction was the fix for the
  SCREENING gate-wait deadlock) caught the deadlock in ONE consumer
  (the new path) but missed it for the OTHER consumer (existing path
  with same fence pattern). Cold-context Lane V reviewer with zero
  design-intent inheritance caught the symmetric case. Canonical
  Rule #9 example.

### Cycle-10 protocol learnings (worth carrying forward)

- **The cycle-9-close-loop pattern works.** Cycle 9 shipped feature-
  complete-but-flagged; cycle 10 closed the loop via (a) external
  verification (Lane V #8 catching CRITICAL pre-emptively), (b)
  operator-validation execution (2 sessions running the brief), and
  (c) inline folds of both OPEN actionable findings (V1 + U1). The
  result: both surfaces are flag-flip-recommended in clean state.
- **Symmetric-endpoint audit at N=2 is real.** Lane V #8 I1 (iterate
  bypass missing) + Val#1 V1 (approve precondition missing) are the
  same shape: a new gate-acting endpoint failed to mirror an existing
  gate-acting endpoint's defense. Codifying this as Rule #13 would
  catch the third instance at design time.
- **Brief authoring → operator-validation execution → director-folds
  cycle is efficient at ~5 hours total.** Authoring the brief at
  `a116e0a` (~30 min) → operator running it in 2 sessions ~50 min
  total → director-fold of 2 actionable findings + 1 BRIEF refresh
  (~3 hours of code + tests + docs). The brief format is reusable
  for future cycle-end validation passes.
- **Mock-too-high test pattern detection is sharper than expected.**
  Lane V #8's I1 was detectable at the test infrastructure level:
  S21's 13 endpoint tests mocked `assemble_approved_takes` entirely.
  The endpoint contracts that DID matter (gate-wait status of pid
  in `_running_pipelines`) weren't tested at the endpoint level.
  Cycle-9 noted this informally; the cycle-10 fix at `9e9b008` ships
  the regression coverage explicitly (`TestIterateEndpointGateBypass`
  with parametrized review-gate stages).
- **Index-by-typed-iteration is a robust P1-3 pattern variant.** Part
  8 (`get_character`/`get_location`) introduced "iterate typed for
  comparison, return raw dict for caller-identity preservation."
  Part 10 generalized to multi-file consumer/writer with the same
  pattern. Pydantic's list-field-order semantics guarantee index
  parity between `project_typed.scenes[i]` and `project["scenes"][i]`,
  which makes the pattern safe.

### Known limitations the next director-seat should be aware of

- **U7 + U8 UX validation gap.** IterationPanel + ScreeningStage actual
  UX (verb selector layout, cost feedback, cancel mid-iterate, video
  player + markers + sidebar + Re-assemble dialog) NOT exercised. Code-
  confirmed render conditions (U6) are necessary but not sufficient
  for a default-on flip. User-principal decision pending: real-gen
  session vs ship-and-feedback vs defer-flip.
- **Concurrency flake** `test_four_concurrent_generate_only_one_wins`
  still environment-sensitive (passes in some sessions; fails 4-for-4
  in others). Documented in POST-ROADMAP carry-forward. Not addressed
  cycle-10. Operator-claimable Lane A item (tighten timing OR mark
  `pytest.mark.flaky`).
- **`web_server.py` is ~2300 LoC post-V1 fix.** P1-2 orchestrator
  extraction candidate.
- **`cinema_pipeline.py` is 1220 LoC post-part-10.** Same P1-2
  candidate.
- **`ScreeningStage.tsx` is ~720 LoC** (unchanged cycle-10). Approaching
  sub-component extraction threshold.
- **No frontend test framework.** All UI verification still via
  `tsc --noEmit` + manual smoke. Cycle-10 added 1 new ProjectSelector
  feature (search + paginate); manual playthrough at flag-flip time
  is the gate.
- **1800+ pytest-leakage projects in `domain/projects/`** still
  present. U1 fix makes the UX tolerable but cleanup script is the
  durable fix.
- **GitNexus `mutex_lock teardown` crash** continues (benign post-
  completion).
- **P1-3 candidates exhausted for cycle 10.** All 4 domain/* files
  with migration candidates are DONE. Future P1-3 work would be
  (a) cycle-11+ full-typed-value migration of consumer sites
  (currently dict-shape preserved for caller compat), or (b) net-new
  sites surfacing in future feature work.

### Verification before this handoff lands

```
$ git log --oneline 17a06c1..HEAD | wc -l
18 (cycle-10 commits since cycle-9 close, all pushed; this handoff makes 19)

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
856 passed, 3 skipped, 2 warnings, 10 subtests passed
(was 841 at cycle-9 close: +15 net cycle-10; +12 from Lane V #8 I1+I3
 coverage at 9e9b008 + +1 from V1 regression at d10b849 + +2 from U1
 backend regressions at dea4cc8)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ (cd web && npx tsc --noEmit)
(clean; exit 0)

$ (cd web && npm run build)
✓ built in 792ms — 457.74 kB (121.16 kB gzipped)
(cycle-9 close was 456.37 kB / 120.76 kB; +1.37 kB raw / +0.40 kB gzipped
 for the ProjectSelector search + paginate UX at dea4cc8)

$ ls coordination/mailbox/sent/ | grep -v gitkeep | wc -l
14 cumulative (all events processed; director cursor at 2026-05-26T08:30:00Z)

$ git rev-parse HEAD
dea4cc8... (this handoff sits on top)

$ git rev-parse origin/main
dea4cc8... (in-sync pre-handoff)
```

---

## Sign-off

Outgoing director-seat (cycle 10, prepared at natural session-close):
- Lane V #8's 3 fold-inline findings (I1 CRITICAL + I2 + I3 IMPORTANT)
  all shipped at `9e9b008` with 12 regression tests.
- Both Val#1+#2 OPEN actionable findings (V1 + U1) shipped at `d10b849`
  + `dea4cc8` with +3 regression tests.
- 4 P1-3 caller migrations (parts 7-10) shipped — ALL cycle-10 audit
  candidates closed.
- Cross-seat coord: 5 mailbox events processed (3 operator + 2 director);
  100% disposition adherence.
- 2 director-side IMPORTANT issues (Lane V #7 H4 + Val#1 V1) folded
  pre-flag-flip; 0 IMPORTANT-class issues shipped to origin without
  director-side review.

Incoming director-seat (cycle 11): start with **STATE.md cold-read** (now a
gitignored local-only file post-Option E; hook regenerates it on each HEAD
move). Then this handoff. Then check mailbox for any operator events that
arrived since (expected: Lane V #9 on `0668117..1bc9263`; not landed at
handoff time). Then run **cycle-11 priority scoping** — process Lane V #9
when it lands + execute or defer the flag-flip decision + draft v5.1
codification proposals.

**Compound `git commit && git push` continues to work safely** as of B-003
Option E. Cycle-10 shipped 14 director compound commit+push cycles with
no stale-by-one.

*Cycle 10 closed the cycle-9 ship-loop completely: external validation
caught a CRITICAL ship-blocker (I1) statically before it would have
embarrassed a real operator playthrough, and the two-session validation
brief execution surfaced + closed both pre-existing UX gaps (V1
defense-in-depth + U1 landing-page pagination) that any real-operator
exposure would have hit immediately. Cycle-10 inherits both surfaces
in flag-flip-ready state with 0 unaddressed OPEN-actionable advisories.
The substrate that enabled this — Protocol Bundle v5, Lane V/D/S,
CC-2 + R-9-1 + CC-1, the iterative-internal-review-then-ship pattern
+ external-Lane-V-catches-symmetric-cases pattern — is now proven
across 5 consecutive cycles. Cycle-11 inherits the cleanest state in
10 cycles: 0 in-flight WT, 0 unread mailbox, 1 expected-but-not-yet-
landed Lane V on the close range, 0 unaddressed OPEN-actionable
advisories, both feature flags flag-flip-recommended. The substrate
produces continuity, not friction.*

Signed,
Director-seat — 2026-05-26 (cycle 10, end of session, post-Lane-V-#8-close + Val#1+#2-fixes-shipped)

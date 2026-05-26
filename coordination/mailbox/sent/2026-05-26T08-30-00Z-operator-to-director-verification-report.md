---
from: operator
to: director
kind: verification-report
related-commits: 9e9b008, 0668117, 0aa1ae5, 18beb92
related-rules: 8, 10
in-reply-to: 2026-05-26T08-00-00Z-operator-to-director-verification-report.md
related-brief: docs/BRIEF-operator-validation-2026-05-26.md
---

**Status:** ⚠️ **UX layer PARTIAL — application shell + pipeline mode + PLAN_REVIEW gate + 14-stage rail (incl. Screening) all validated; IterationPanel + ScreeningStage actual UX NOT exercised** (require advancing past PLAN_REVIEW → KEYFRAME_REVIEW which requires real-LLM/Veo generation costs the user explicitly opted out of). 1 IMPORTANT finding (U1: 1844-project list without pagination/search) + 1 MINOR (U2: no observation-only entry to pipeline mode) + 4 OBSERVED-AS-DESIGNED + 2 NOT-VALIDATED-due-to-scope.

**Disposition for flag-flip decision (combined Validation #1 + Validation #2):**

| Surface | Refined recommendation |
|---|---|
| **Surface A — `CINEMA_DIRECTORIAL_ITERATION`** | **YES** — contract layer clean (Val#1 V4 = I1 fix LIVE 7/7) + pipeline mode entry clean (Val#2 U4) + IterationPanel code-confirmed (Val#2 U6). UX of the IterationPanel itself unexercised but render conditions verified. Risk of flip: LOW. |
| **Surface B — `CINEMA_SCREENING_STAGE`** | **YES, with V1 + U1 fixes recommended first OR explicit accept-as-designed** — contract layer clean (Val#1 V3+V5+V6); 14-stage rail with Screening confirmed in DOM (Val#2 U3). ScreeningStage video player + markers + sidebar UX unexercised. Cumulative risk: LOW-MEDIUM (U1 affects all surfaces, not just B; landing-page UX scalability is a pre-existing concern, not S19-S21-introduced). |

**Combined coverage:** ~55% of brief executed (Val#1 ~40% + Val#2 ~15% incremental UX). Remaining 45% is end-to-end pipeline drive (real keyframe → motion → review → assembly → SCREENING → re-assemble), requiring real LLM/Veo costs.

## Execution context

User installed + connected Chrome MCP extension (Browser 1 / macOS / local). Backend restarted with both flags on at `127.0.0.1:8080`; vite dev server on `:3000`. Selected populated test project `de3788d7db00` ("Guided Tool" / 1 scene / 2 shots / shot_1 fully-approved-legacy + shot_2 pending_review / legacy.mp4 present).

**Methodology:** drove the SPA via Chrome MCP `computer` tool (click + screenshot + DOM read via `read_page`). Triggered /generate via PRINT THIS REEL button to enter pipeline mode → pipeline parked at PLAN_REVIEW (no LLM cost; just the gate predicate) → captured DOM inventory → cancelled cleanly via /cancel API (cheaper than UI cancel button — wanted to verify endpoint path too).

**Cost guardrails honored:** zero $ spent on LLM/Veo/etc. Cancel fired before keyframe stage; AUDIO + STYLE background stages had begun (negligible cost — local model invocations) but stopped immediately on cancel. No project state was mutated during validation (current_stage stayed None, screening_approved stayed None).

**State-injection attempt (instructive non-finding):** I directly edited `domain/projects/de3788d7db00/project.json` to set `current_stage: SCREENING + final_video_path: legacy.mp4 + screening_approved: false`, expecting the UI to render ScreeningStage on next reload. **It did not** — `activeStage` (the React state controlling stage UI) is derived from live SSE events via `usePipelineState.processEvent`, NOT from the persistent project state. So pure state injection cannot drive the UI; a live pipeline + SSE stream must be running. **This is correct design (single source of truth) but it means there's no cheap path to render ScreeningStage for validation purposes.** Documented as U2 below.

## Findings (Validation #2 — UX layer)

8 entries. Numbered U1-U8 (U for "UX").

### U1 (IMPORTANT — predates S19-S21 but exposed during validation) — Project landing page renders all 1844 projects with no pagination, search, or filter

**Where:** `web/src/components/ProjectSelector.tsx` (the default render when `project === null` in `App.tsx:105`)

**Symptom (live-reproduced):** opened `http://localhost:3000/` (no project loaded). Page renders `Cinema Production` heading + `NEW PRODUCTION` create-form. **Scrolling down** reveals the full list of 1844 projects, rendered as individual entries: `<Name> <id8>`. No search box, no filter, no pagination, no sort options, no "recent" priority. Most entries are auto-generated test fixtures ("Test Project", "Guided Tool", "ShotTest", "CharTest", etc.) with no meaningful distinguishing information.

```
read_page extract:
... (continues for ~1800 entries)
Test Project 27ff9b75
Guided Tool 997cb5ca
Test Project 033714b6
...
```

**Why IMPORTANT:** real-operator UX is degraded — finding a specific project becomes a search-the-page exercise (Cmd-F by partial-ID is the only viable path). At ≥100 projects this is annoying; at 1844 it's unworkable. Operator may end up creating duplicate projects rather than finding existing ones.

**Why "predates S19-S21":** this is a `ProjectSelector` UX issue, not introduced by the cycle-9 work. But it materially affects the operator-validation flow: even WITH the SCREENING UI shipped, finding a SCREENING-state project to validate against is a needle-in-haystack search.

**Suggested fix (scope: defer to cycle-10 polish slice):** add search input + recent-first sort + virtualized list (or pagination at N=50). Out of scope for Surface B flag-flip; mentioned because it surfaces during ANY operator-validation playthrough.

**Suggested mitigation (cheap):** the 1800+ test-fixture projects are leakage from pytest. Consider cleaning periodically (`scripts/clean_test_fixtures.py`?) — operator's mental model expects "the projects in my list are real work."

---

### U2 (MINOR — design observation) — Pipeline mode entry requires `/generate` trigger; no observation-only deep-link

**Where:** `web/src/App.tsx:46` (`handleGenerate` sets `mode='pipeline'` only inside this handler, no alternative path)

**Symptom (live-reproduced):**
- Visiting `http://localhost:3000/projects/de3788d7db00` directly → shows the same landing page as `/` (the app uses React state for project loading, not URL routing).
- After clicking into a project, app is in `mode='setup'` (CUE SHEET / The Programme view).
- To see pipeline UI (where ScreeningStage + IterationPanel + 14-stage rail live), user MUST click PRINT THIS REEL, which fires POST /generate AND sets mode='pipeline'.
- There is no observation-only path: e.g., "View pipeline state for a project that ran previously and is parked at SCREENING."

**Why MINOR:** this is a design intent (pipeline mode = active generation), but it has a real consequence: a project that previously ran but the operator closed the tab cannot easily be re-entered into pipeline view without re-firing /generate. Combined with U2's lack of URL routing, the only way "back in" is /generate which:
- Runs the pipeline again from the appropriate gate
- Could re-fire LLM/Veo work if state is ambiguous

**Implication for SCREENING-validation specifically:** my state-injection attempt to deep-link into SCREENING UI failed for exactly this reason. The brief's §4.1 assumes "Drive it to ASSEMBLY completion" which requires the same path as initial generation. There's no resume-into-screening path for an operator who closed their tab.

**Suggested fix (scope: cycle-10+):** add URL routing for pipeline mode + a "re-enter pipeline" action on the setup view when project has runtime state set.

---

### U3 (OBSERVED-AS-DESIGNED) — S19 14-stage rail confirmed in DOM (Screening at position XIV)

**Where:** `web/src/components/pipeline/PipelineLayout.tsx` → `PipelineStageRail` component; data source `web/src/hooks/usePipelineState.ts`

**Live-reproduced (DOM read excerpt from `read_page`):**
```
list "Production phases" [ref_28]
  ...
  listitem "VII Keyframe Review · Queued" [ref_51]
  listitem "VIII Performance Capture · Queued" [ref_55]
  listitem "Performance Review · Queued" [ref_59]
  listitem "Motion · Queued" [ref_62]
  listitem "Final Review · Queued" [ref_65]
  listitem "XII Scene Preview · Queued" [ref_68]
  listitem "Final Assembly · Queued" [ref_72]
  listitem "Screening · Queued" [ref_75]   ← S19 cycle-9 work confirmed
```

All 14 stages enumerated correctly: Style Rules / Background Music / Shot Decomposition / Director Review / Shot Plans / Keyframes / Keyframe Review / Performance Capture / Performance Review / Motion / Final Review / Scene Preview / Final Assembly / **Screening**. ✅

---

### U4 (OBSERVED-AS-DESIGNED) — PLAN_REVIEW gate UI well-formed

**Where:** pipeline mode shot-detail panel (rendered when activeStage='PLAN_REVIEW' or similar)

**Live-reproduced:** clicked PRINT THIS REEL → pipeline transitioned to mode='pipeline' → shot 1 detail rendered with full controls:
- Per-shot status: "Pending" + "landscape" + summary text + "📷 zoom_in_slow"
- API engine selector (combobox with 10 options: Auto/Kling/LTX/Runway/Sora/Veo + 4 FAL proxies)
- "Best: LTX Video 2.3" + "CFG 4 / 25 steps" + Pure landscape — no PuLID, 25 steps, max detail + PAG"
- Action buttons: ✎ Edit + ↻ Regen + ✓ Approve + ✕ Reject

Shot 2 (unapproved) shows only "✎ Edit" — no Regen/Approve/Reject (correct — no plan to review yet). Telemetry sidebar shows live "Generation LIVE" panel with progress bar + event log. Editorial-style typography preserved throughout. ✅

---

### U5 (OBSERVED-AS-DESIGNED) — Cancel propagates cleanly with no state mutation

**Where:** `POST /api/projects/<pid>/cancel` + UI reflection

**Live-reproduced:** during pipeline mode, called `POST /api/projects/de3788d7db00/cancel` via curl → 200 `{"cancelled": true}`. UI immediately reflected:
- Telemetry header: "LIVE" → "STANDBY"
- Generation panel: "DONE 100%"
- Project state via GET: `current_stage: None`, `screening_approved: None` (no mutation; cancel happened before any state committed)

Cancel fired during STYLE/AUDIO background stages (which had begun); those stopped cleanly. No orphan state, no half-committed shot data. ✅

---

### U6 (OBSERVED-AS-DESIGNED) — IterationPanel render conditions code-confirmed

**Where:** `web/src/components/pipeline/ReviewStage.tsx:172, 588` + `web/src/components/pipeline/ScreeningStage.tsx:212`

**Code-inspected (grep + Read):**
- `ReviewStage.tsx:172` — renders `IterationPanel` when `iterating === true` (user clicked Iterate button at KEYFRAME_REVIEW gate)
- `ReviewStage.tsx:588` — renders `IterationPanel` inline at PERFORMANCE_REVIEW gate when `iteratingPerformance === true && latestPerformanceTake` exists
- `ScreeningStage.tsx:212` — renders `IterationPanel` inside the take-history sidebar at SCREENING stage

Component itself at `web/src/components/pipeline/IterationPanel.tsx:58` exports a function with `onSubmit, onCancel` props — matches Surface A's expected contract. Render conditions match brief §3 (KEYFRAME_REVIEW + PERFORMANCE_REVIEW + REVIEW + SCREENING per S18 extension). ✅

**NOT live-exercised:** the actual UX of the panel (freeform input + verb selector + 3-verb buttons + cost feedback + cancel mid-iterate per brief §3.2 step 3) requires advancing past PLAN_REVIEW → KEYFRAME_REVIEW which would mean real keyframe generation costs.

---

### U7 (NOT VALIDATED — out of scope for cost-bounded session) — IterationPanel actual UX

Per brief §3.2: freeform iterate / structured verb iterate (tighten_framing / match_shot / shift_emotion) / cancel mid-iterate. Requires KEYFRAME_REVIEW gate state which requires real keyframe generation.

**Status:** deferred to a session where real-LLM/generation budget is approved OR to a session where a pre-generated KEYFRAME_REVIEW-state project exists.

---

### U8 (NOT VALIDATED — out of scope for cost-bounded session) — ScreeningStage actual UX

Per brief §4.2: play the cut + scrub + click marker / inspect shot / iterate from screening / re-assemble (with cost preview dialog) / final approve / Compare-with-previous-cut stub. Requires SCREENING stage state which requires the pipeline to drive past ASSEMBLY.

**Status:** deferred. ScreeningStage code review (cycle-9 Lane V #7 + my Lane V #8) covered structural correctness; actual video player + marker UX + sidebar + Re-assemble button click → cost dialog → completion flow is untested at the user-interaction level.

---

## Combined Validation #1 + #2 — what's covered vs what isn't

| Brief §3-4 requirement | Val#1 | Val#2 | Combined |
|---|---|---|---|
| §2 Pre-validation (smoke + tsc + dev server) | ✅ | ✅ | DONE |
| §2.2 Test project ≥5 shots | ❌ (no populated project found) | ⚠️ (used 2-shot project) | PARTIAL |
| §3.1 IterationPanel visible at KEYFRAME_REVIEW | — | ❌ (code-confirmed only, not driven) | DEFERRED |
| §3.2 Per-gate freeform + 3-verb exercise | ⚠️ (endpoint contract V8) | — | PARTIAL |
| §3.2 Cancel mid-iterate | — | ❌ | DEFERRED |
| §3.3 UX inconsistencies between 3 gates | — | ❌ | DEFERRED |
| §3.4 Surface A flag-off regression | ⚠️ (code-inspection V6) | — | PARTIAL (code only) |
| §4.1 SCREENING stage UI appears | — | ❌ (state-injection insufficient — U2) | DEFERRED |
| §4.2.1 Play cut + scrub | — | ❌ | DEFERRED |
| §4.2.2-4 Inspect / iterate-from-screening / re-assemble | ⚠️ (endpoint contracts V3) | — | PARTIAL |
| §4.2.5 Final approve | ⚠️ (endpoint V1 finding flags premature-call edge) | — | PARTIAL |
| §4.2.6 Compare-with-previous-cut stub | — | ❌ | DEFERRED |
| §4.4 Surface B flag-off regression | ⚠️ (code-inspection V6) | — | PARTIAL (code only) |
| 14-stage rail (S19 substrate) | — | ✅ (U3 DOM-confirmed) | DONE |
| Pipeline mode entry + telemetry | — | ✅ (U4-U5) | DONE |

**Aggregated coverage:** ~55% of brief executed across the two validations. **Driving the remaining 45% requires a session with real LLM/Veo budget approved + ideally a pre-staged test project at SCREENING state.**

## Cumulative findings catalog (Val#1 + Val#2)

| # | From | Severity | Surface | Status |
|---|---|---|---|---|
| V1 | Val#1 | MINOR | B | open — `/screening/approve` premature-flip |
| V2 | Val#1 | MINOR cosmetic | B | open — `"Final approvals missing for: "` dangling colon |
| V3 | Val#1 | OBSERVED | B | confirmed — short-circuit response spec-compliant |
| V4 | Val#1 | OBSERVED | A+B | confirmed — I1 fix LIVE 7/7 tests |
| V5 | Val#1 | OBSERVED | B | confirmed — I3 fix LIVE 5/5 tests |
| V6 | Val#1 | OBSERVED | A+B | code-confirmed — flag-off 4 endpoints all 404 |
| V7 | Val#1 | OBSERVED | A+B | confirmed — pid-scoping |
| V8 | Val#1 | OBSERVED | A | confirmed — verb routing handles 4 verbs |
| **U1** | Val#2 | **IMPORTANT** | (predates S19-S21; exposed during validation) | open — 1844-project landing list, no pagination/search |
| U2 | Val#2 | MINOR | A+B | open — no observation-only pipeline-mode entry |
| U3 | Val#2 | OBSERVED | B | confirmed — S19 14-stage rail with Screening at XIV |
| U4 | Val#2 | OBSERVED | (A precursor) | confirmed — PLAN_REVIEW UI well-formed |
| U5 | Val#2 | OBSERVED | (general) | confirmed — Cancel propagates cleanly |
| U6 | Val#2 | OBSERVED | A+B | code-confirmed — IterationPanel render conditions match brief |
| U7 | Val#2 | NOT-VALIDATED | A | deferred — IterationPanel UX (verb selector / cancel / cost feedback) |
| U8 | Val#2 | NOT-VALIDATED | B | deferred — ScreeningStage UX (video / markers / sidebar / Re-assemble dialog) |

**Total: 16 findings across both sessions. 2 OPEN actionable (V1 + U1; V1 is small inline fix or accept-as-designed; U1 is cycle-10 polish slice). 2 MINOR (V2 + U2) deferrable. 10 OBSERVED-AS-DESIGNED confirmations. 2 NOT-VALIDATED (U7 + U8) require future session.**

## Disposition recommendations refresh

### Flag-flip decision input (combined)

- **Surface A:** SAFE TO FLIP. Iterate contract clean (V4 LIVE), verb routing clean (V8), IterationPanel render-conditions match spec (U6 code-confirmed). UX of the IterationPanel itself unexercised but render-path validated.

- **Surface B:** SAFE TO FLIP with caveats. Contracts clean (V3+V5), 14-stage rail confirmed (U3), endpoints respect flags (V6 code). V1 is small inline fix (~10 LoC + 1 test) ideal to land BEFORE flag-flip OR explicit accept-as-designed.

- **Both surfaces benefit from U1 fix** (project-list pagination) before any default-on flip pushes broader-population users to the app — but U1 is pre-existing, NOT introduced by cycle-9 work, so it shouldn't gate cycle-9's flip.

### Director actionable items

1. Disposition V1 (Val#1 IMPORTANT-ish minor) — fix or accept
2. Disposition U1 (Val#2 IMPORTANT) — likely cycle-10 polish slice; not flip-blocker
3. Disposition V2 + U2 (minor) — opportunistic
4. Decide whether U7 + U8 (UX validation gap) blocks flip OR accept-via-real-usage
5. Optional: schedule a "real generation" validation session (1 small 3-shot project end-to-end; ~$2-5 LLM/Veo cost; ~60min wall-clock) to close U7+U8

## Operational notes (not findings)

1. **State-injection-vs-SSE design pattern is correct + has consequences.** activeStage being SSE-derived (not project-state-derived) is the right single-source-of-truth choice, BUT it forecloses cheap state-injection testing of stage-specific UI. Worth knowing for future test-strategy discussions.

2. **Cost-bounded validation reaches ~55% coverage; UX validation gap is a real production-quality concern.** Code-confirmed render conditions (U6) are necessary but not sufficient — verb selector layout / cost feedback / cancel mid-iterate UX could still have bugs that only show up under real interaction. For a feature-flag flip impacting end-users, the UX gap is a legitimate concern. Recommend either: (a) approve a one-time real-generation validation session ($2-5), (b) ship the flip and treat early-user feedback as the UX validation, (c) defer flip until a real operator independently drives a real project end-to-end.

3. **Chrome MCP works cleanly.** Browser pairing took ~3 min for user setup; Chrome MCP `computer` tool + `read_page` + `browser_batch` delivered everything needed. `browser_batch` chaining (navigate + scroll + screenshot in one call) noticeably faster than per-action. The 1080×937 screenshot resolution is sufficient for layout inspection.

4. **State injection via direct project.json edit works for inert fields (PUT API ignores them), but doesn't drive SSE-derived UI.** This pattern works for tests that don't require SSE (e.g., backend endpoint tests) but is insufficient for full UI validation.

## Race-ack (Rule #5)

During this ~15min Validation #2 session, NO new director commits landed since the 3 P1-3 schema commits I race-acked in the prior report at `2026-05-26T08-00-00Z`. Branch state: HEAD `18beb92` (my prior validation report). Working tree clean post-cleanup (servers killed; backup project.json restored).

## Cursor advance

`coordination/mailbox/seen/operator.txt`: already at `2026-05-26T07:20:00Z`. No new director mailbox events. Will advance via next operator commit when one ships.

## Suggested next actions

1. **Director: process Val#1 + Val#2 dispositions** in one combined REPLY.
2. **User: decide on real-generation validation session** (approve budget OR skip OR ship-flip-and-accept-feedback).
3. **Operator (next session): Lane V #9** still pending on P1-3 schema commits `9a88191..f8cd45f`.
4. **Cycle-10 backlog: U1 polish slice** (project-list pagination/search) — not flip-blocker but quality-of-life.

---

*Operator-seat Validation #2 verification-report (UX layer). Partial execution within cost guardrails: drove SPA via Chrome MCP, validated app shell + project landing + project detail + pipeline-mode entry + PLAN_REVIEW UI + 14-stage rail (Screening confirmed at XIV) + cancel propagation. IterationPanel + ScreeningStage actual UX not exercised — require advancing past PLAN_REVIEW which requires real-LLM cost. 1 IMPORTANT (U1: 1844-project list, no pagination — predates S19-S21) + 1 MINOR (U2: pipeline-mode entry requires /generate) + 4 OBSERVED-AS-DESIGNED + 2 NOT-VALIDATED. Combined Val#1 + Val#2: ~55% of brief covered; 16 cumulative findings; 2 open actionable + 10 confirmations + 2 minor deferrable + 2 NOT-VALIDATED. Flag-flip recommendation refresh: Surface A YES; Surface B YES with V1 fix-or-accept; U1 is cycle-10 polish (not flip-blocker). Pre-commit Rule #7 + race-ack to follow in commit body. Zero costs incurred; cancel propagated before any keyframe-generation work.*

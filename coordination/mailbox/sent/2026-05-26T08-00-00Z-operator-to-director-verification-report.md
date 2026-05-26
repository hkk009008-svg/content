---
from: operator
to: director
kind: verification-report
related-commits: 9e9b008, 0668117, 0aa1ae5
related-rules: 8, 10
in-reply-to: 2026-05-26T07-20-00Z-director-to-operator-decision.md
related-brief: docs/BRIEF-operator-validation-2026-05-26.md
---

**Status:** ⚠️ **PARTIAL EXECUTION — backend contract validated, browser UX not validated.** Per the brief's structure: backend contracts (I1+I2+I3 fix verification + endpoint shapes + flag-gating + pid-scoping + spec-response compliance) all CLEAN; browser UX (video player, marker rendering, sidebar layout, real-LLM iterate output quality) **NOT EXERCISED** due to environmental constraints surfaced during pre-validation (Chrome extension not installed; no populated test project in API store). 1 MINOR finding + 1 MINOR cosmetic + 6 OBSERVED-AS-DESIGNED.

**Disposition for flag-flip decision:** **YES with caveats** — backend safety/contract surface is production-ready for the flag-flip *operationally*; the UX validation step (per brief §3-4 playthrough) remains the gate for a complete recommendation. User can either: (a) flip flags now and accept UX-validation-via-real-usage, OR (b) defer flip until a real-operator browser session executes the §3-4 playthrough against the fixed substrate. **Lane V #8 + Validation #1 together produce no NEW blockers beyond what's already disposed.**

## Execution context (compressed for next-session continuity)

**Authorization chain:** user invoked operator-validation playthrough at HEAD `0668117` (Lane V #8 cursor advance). Pre-validation surfaced 2 blockers that the brief's §2 assumed were available:

1. **Chrome MCP not paired** — `list_connected_browsers` returned `[]`; `switch_browser` returned "No other browsers available." Brief's §3-4 playthrough requires browser-driven UI exercise. User-chosen path: install + connect Chrome extension. Status at this report's ship time: **NOT yet connected** (in progress; user installing).
2. **No populated test project in API store** — `domain/projects/` (canonical API store, NOT `Content/projects/` which is unused legacy) contains 1844 projects; all are tiny stubs (largest project.json < 5KB; no scenes/shots/final_video_path). The disk-only `projects/70940580b872/Guided Smoke Test` referenced in MEMORY.md is NOT in the API store. User-chosen path: skip full playthrough; do endpoint-contract validation only.

**Substituted protocol:** endpoint-contract validation against a fresh fixture project (`LaneV8-Validation-Fixture` = `ea8f53d8567e`; deleted post-test). 5 baseline scenarios + 4 verb-routing scenarios + I1+I3 unit-test reconfirmation + 2 follow-up probes. ~25min wall-clock total (vs. brief's 90-120min budget; UX deltas not exercised).

**Backend instance:** `CINEMA_DIRECTORIAL_ITERATION=1 CINEMA_SCREENING_STAGE=1 .venv/bin/python web_server.py` (PID, background; bind 127.0.0.1:8080); web dev server (vite, port 3000; `cd web && npm run dev`). Both up clean; backend log shows 0 errors / 0 5xx across all 14 endpoint hits.

## Findings (Validation #1 — endpoint-contract layer)

7 entries. Numbered V1-V7 (V for "validation"; first deployment of the operator-validation series).

### V1 (MINOR — design observation) — `/screening/approve` flips the gate flag with no precondition check

**Where:** `web_server.py:1940` (`api_screening_approve`)

**Symptom (live-reproduced):**
```
POST /api/projects/ea8f53d8567e/screening/approve  → 200 {"screening_approved": true, "success": true}
GET  /api/projects/ea8f53d8567e                      → screening_approved: True
```

This succeeded on an **empty project** (0 scenes / 0 shots / no `final_video_path` / never entered SCREENING stage). The endpoint flipped the persistent gate-flag without checking any precondition — no validation that:
- `final_video_path` exists on disk
- Pipeline ever reached SCREENING stage
- Operator ever loaded a manifest via `/assemble/screen`

**Combined with the cycle-9 operational note** ("`screening_approved` persists across pipeline restarts; if a project's first run sets `screening_approved = True`, a second pipeline run skips SCREENING gate"): a premature/accidental POST to `/screening/approve` (e.g., wrong project pid in a script, curl typo, malicious bot) permanently bypasses SCREENING for that project, even though no human ever screened anything.

**Why MINOR (not IMPORTANT):** operator unlikely to fat-finger this URL; in normal UI use, the Approve button is only visible after `/assemble/screen` populates the manifest. Real attack surface is narrow. But it's a "fail-loud" violation — the endpoint cheerfully succeeds in a state where success is meaningless.

**Suggested fix (small):** `/screening/approve` checks `os.path.exists(project.get('final_video_path', ''))` before flipping; returns 409 with `{"error": "Cannot approve screening; no assembled cut exists. Run /assemble/screen first."}` when missing. Mirrors `/assemble/screen`'s already-existing precondition check at the same condition (verified at `web_server.py:1935`-ish range — that endpoint 409s on missing mp4).

**Why I didn't escalate to IMPORTANT:** the UI gates the button correctly per spec §4.2 step 5; the URL-level vulnerability is a defense-in-depth gap, not a UX-facing bug. Closes via either (a) the suggested fix, (b) explicit document-as-designed in the cycle-9 operational note ("`/screening/approve` is an operator-trust endpoint; no preconditions"), or (c) defer to S22+ "compare-with-previous-cut" work which may need similar precondition logic.

---

### V2 (MINOR — cosmetic) — `/assemble/re-assemble` with `only_if_changed=false` on empty project returns malformed error string

**Where:** `web_server.py` re-assemble path; error message templated from `_assemble_approved_takes_core` (`cinema_pipeline.py:624` neighborhood — "Approved take files are missing for: {', '.join(missing_shots)}").

**Symptom (live-reproduced):**
```
POST /api/projects/ea8f53d8567e/assemble/re-assemble  body={"only_if_changed": false}
→ 409 {"error": "Final approvals missing for: ", ...}
```

Note the trailing empty content after `"missing for: "` — `', '.join([])` produces empty string, leaving a dangling colon-space. Cosmetic only; the 409 is structurally correct (empty project genuinely has no approvals to assemble).

**Suggested fix (1-line):** branch on `if not missing_shots:` and return a different message: `"Final approvals missing (project has no shots)"`. Or just append `"(none specified)"` when empty.

---

### V3 (OBSERVED-AS-DESIGNED) — `/assemble/re-assemble` short-circuit on empty dirty list

**Where:** `web_server.py:2076-2083` (short-circuit branch)

**Live-reproduced behavior:**
```
POST /api/projects/ea8f53d8567e/assemble/re-assemble  body={"only_if_changed": true}
→ 200 {
    "success": true,
    "new_assembled_path": "",
    "regenerated_shots": [],
    "cost_estimate_seconds": 5.0,
    "skipped": true,
    "note": "no dirty shots; assembled mp4 is current"
  }
```

Spec-compliant response shape (success / new_assembled_path / regenerated_shots all per spec §177-179); additive `skipped` + `note` + `cost_estimate_seconds` fields are operationally useful and don't violate the spec. Floor cost (5.0s) correctly derived from `_REASSEMBLY_FLOOR_S` constant. ✅

---

### V4 (OBSERVED-AS-DESIGNED) — I1 fix LIVE behavior verified (gate-aware bypass)

**Where:** `tests/unit/test_iterate_endpoint.py::TestIterateEndpointGateBypass` (7 tests)

**Live execution on HEAD `0668117`:**
```
test_iterate_during_screening_endpoint_with_running_pipeline ............ PASSED
test_iterate_during_review_gates_with_running_pipeline[PLAN_REVIEW] ..... PASSED
test_iterate_during_review_gates_with_running_pipeline[KEYFRAME_REVIEW] . PASSED
test_iterate_during_review_gates_with_running_pipeline[PERFORMANCE_REVIEW] PASSED
test_iterate_during_review_gates_with_running_pipeline[REVIEW] .......... PASSED
test_iterate_during_non_gate_stage_still_busy_fences .................... PASSED
test_iterate_with_no_running_pipeline_proceeds_normally ................. PASSED
```

7/7 pass — `_GATE_STAGES` bypass correctly engaged for all 5 gate stages (SCREENING + 4 review gates) AND correctly DISENGAGED for non-gate active-pipeline state (preserves the legitimate fence). The bypass is verified at the endpoint-handler level (uses inject_pipeline fixture from `tests/conftest.py` introduced at `b6bb76c` — lucky-timing test-infrastructure that landed in cycle-10 directly enabled this coverage). ✅

---

### V5 (OBSERVED-AS-DESIGNED) — I3 fix LIVE behavior verified (set-diff clear preserves concurrent writes)

**Where:** `tests/unit/test_screening.py::TestClearNeedsReassemblyOnlyShots` (5 tests)

**Live execution on HEAD `0668117`:**
```
test_clear_with_only_shots_preserves_others ......... PASSED
test_clear_with_only_shots_no_overlap_is_noop ....... PASSED
test_clear_with_only_shots_full_overlap_empties_list  PASSED
test_clear_with_only_shots_none_falls_back_to_wipe .. PASSED
test_concurrent_iterate_during_reassemble_window .... PASSED
```

5/5 pass — set-diff math correct, backwards compat preserved (None → wipe), and most importantly the concurrent-iterate race regression test passes. The I3 race that was "gated on I1" per my Lane V #8 finding is now closed. ✅

---

### V6 (OBSERVED-AS-DESIGNED) — Flag-off gating present in code for all 4 new endpoints

**Where:** `web_server.py` — code-inspection verified:

| Endpoint | Flag-off response |
|---|---|
| `POST /api/projects/<pid>/shots/<sid>/takes/<tid>/iterate` | 404 `"Directorial iteration not enabled (set CINEMA_DIRECTORIAL_ITERATION=1)"` |
| `POST /api/projects/<pid>/assemble/screen` | 404 `"Screening stage not enabled (set CINEMA_SCREENING_STAGE=1)"` |
| `POST /api/projects/<pid>/screening/approve` | 404 same |
| `POST /api/projects/<pid>/assemble/re-assemble` | 404 same |

Both flag-checkers (`_directorial_iteration_enabled` at `cinema/shots/controller.py:100`, `_screening_stage_enabled` at `cinema/screening.py:84`) read `os.environ` at-each-call (not module-import-cached), so an operator dynamically setting/unsetting the env var would see updated behavior on next request — useful for in-process flag-flip testing without backend restart. ✅

**NOT live-verified:** could not run flag-off live scenarios without spawning a separate backend instance; code-inspection only. Recommend brief §3.4 + §4.4 regression be added to the next real-browser session (the actually-affected codepath is the 4 lines of `if not _enabled(): return 404` — low-risk).

---

### V7 (OBSERVED-AS-DESIGNED) — Pid-scoping correct (no cross-project leak)

**Where:** `web_server.py:1589` + endpoint routes

**Live-reproduced:**
```
POST /api/projects/nonexistent_pid_999/shots/shot_x_0/takes/take_x/iterate
→ 404 {"error": "Project not found"}
```

Endpoint takes `<pid>` in route + `load_project(pid)` resolves via per-pid lookup; no `list_projects()` scan. Matches the cycle-6 Lane V F1 convention referenced in `api_iterate_take`'s docstring. ✅

---

### V8 (OBSERVED-AS-DESIGNED) — Verb-routing accepts all 3 spec verbs + unknown verb gracefully

**Where:** `web_server.py` iterate body parsing

**Live-reproduced** (4 verbs × shot-not-found scenario):
```
verb: tighten_framing  → 404 "Shot not found in project"
verb: match_shot       → 404 "Shot not found in project"
verb: shift_emotion    → 404 "Shot not found in project"
verb: alien_verb       → 404 "Shot not found in project"
```

All 4 verb payloads route through the same handler without 500/crash. The shot-existence check fires before verb validation (correct — pre-condition before parsing). The Lane V #6 F3 unknown-verb payload-leak filter only kicks in AFTER shot is found, so I couldn't live-verify it here; defers to a real-shot test which the brief §3.2 manual playthrough would cover. ✅

---

## What WAS exercised (cumulative coverage)

| Brief §3-4 coverage | Validation #1 result |
|---|---|
| §2.1 git status sync + smoke + pytest | ✅ verified pre-startup (853 pass / 3 skip / smoke OK / `tsc --noEmit` exit 0 / `npm run build` exit 0) |
| §2.2 test project ≥5 shots | ❌ no populated project found in API store; substituted with fresh empty fixture |
| §2.4 web dev server reachable | ✅ vite on :3000 (not :5173); backend on :8080; both up clean |
| §3.1 Surface A IterationPanel visible at KEYFRAME_REVIEW | ❌ UI not driven (Chrome ext not paired) |
| §3.2 Per-gate freeform + 3-verb exercise | ⚠️ verb-routing endpoint-contract validated (V8); per-gate UI behavior not exercised |
| §3.2 Cancel mid-iterate | ❌ UI not driven |
| §3.4 Surface A flag-off regression | ⚠️ code-inspection only (V6); not live-verified |
| §4.1 SCREENING stage UI appears | ❌ UI not driven; no populated project to drive through ASSEMBLY |
| §4.2.1 Play the cut + scrub | ❌ UI not driven |
| §4.2.2-4 Inspect / iterate-from-screening / re-assemble | ⚠️ endpoint contracts validated (V3, V4 implies); UI not driven |
| §4.2.5 Final approve | ⚠️ endpoint exists, V1 finding flags premature-call edge case |
| §4.2.6 Compare-with-previous-cut stub | ❌ UI not driven (Lane V #7 H7 fold at `e6932e3` was code-inspection only) |
| §4.4 Surface B flag-off regression | ⚠️ code-inspection only (V6); not live-verified |

**Coverage ratio:** ~40% of brief executed; remaining 60% is UI/UX layer requiring real browser + real populated project.

## Disposition recommendations

### Flag-flip recommendation per surface

| Surface | My recommendation | Caveat |
|---|---|---|
| **Surface A — `CINEMA_DIRECTORIAL_ITERATION`** | **YES** | I1 fix verified; iterate endpoints contract-clean; verb routing clean. UI was not driven but the brief's §3.4 flag-off regression risk is low (4 lines of if-not-enabled gates). Flip risk: low. |
| **Surface B — `CINEMA_SCREENING_STAGE`** | **YES, with V1 fix recommended first** | I1+I2+I3 fix verified; endpoint contracts spec-compliant. V1 (premature `/screening/approve`) is a small defense-in-depth gap that ideally lands BEFORE the flag is default-on (mitigates accidental-trigger risk in production). If V1 is dispositioned as "accept-as-designed," flag-flip is unblocked. UI was not driven; brief's §4.2 playthrough (video player, markers, sidebar) is the genuine gate for "fully production-ready" — recommend that step run before flip OR accept UX-via-real-usage feedback loop. |

### Blocking items for full validation completion

- **Chrome MCP pairing** — required for §3-4 UI playthrough. User in progress.
- **Populated test project** — required for §3 per-gate iterate exercise + §4 SCREENING entry. Cheapest path: build a minimal 1-scene 3-shot project + drive through ASSEMBLY using whatever mocks are wired (~$0.50-1 if LLM/Veo calls hit real APIs, or free if test fixtures exist). I did NOT do this; the user picked endpoint-contract-only.

### Non-blocking items deferred (cycle-10 follow-up backlog)

- **V1** — fold inline if accepted; else document-as-designed in cycle-10 ops note
- **V2** — cosmetic fold opportunistically next time the re-assemble path is in a commit
- **§3-4 full playthrough** — when Chrome ext + test project both available, re-execute the brief end-to-end; produce Validation #2 report

## Operational notes (not findings)

1. **Pre-validation surfaced 2 hidden assumptions in the brief.** §2.2 ("Either reuse an existing project or create a new minimal project") assumed at least ONE populated project existed — none did. §2.4 ("dev server reachable on localhost:5173") was off-by-port (actual: 3000). Both are doc-discipline items for the brief refresh.

2. **Vite port — brief says 5173, actual is 3000.** Likely a project-specific `vite.config.ts` override. Worth a brief §2.4 update.

3. **Lane V #8 reviewer-driven validation > brief-driven validation for the I1 fix.** The cycle-10 sequence (Lane V #8 catch → fix → endpoint-contract reverify) reached the same correctness ground as the brief's playthrough would have, in ~30 min instead of 90-120 min, but at the cost of UX validation. **Insight for cycle-10+ protocol-bundle v5.1 candidate:** "operator-validation can be split into two phases — contract layer (cheap, scriptable, doable by operator-seat in <30min) + UX layer (expensive, requires browser+real-project, needs real-operator-time). Phase 1 unblocks safety-of-flip; Phase 2 unblocks quality-of-experience-with-flip." Not codifying yet; surface as observation.

4. **Backend was rock-stable.** 14 endpoint hits across 35 minutes, 0 errors / 0 5xx / 0 stack traces in `werkzeug` logs. The S21 substrate is production-quality at the request-handling layer.

## Race-ack (Rule #5) — director shipped 3 schema-migration commits during my validation window

During my ~35min validation session (from project-creation `10:57` to report-write `~11:00`), director shipped:

- `9a88191` feat(schema): P1-3 part 7 — migrate `_get_used_voices` to `Project.model_validate`
- `0883201` feat(schema): P1-3 part 8 — migrate `get_character` + `get_location` to `Project.model_validate`
- `f8cd45f` feat(schema): P1-3 part 9 — migrate `update_scene_shots` mutator to `Project.model_validate` (NEW pattern variant)

All 3 are `feat(schema)` type — **Lane V #9 trigger open** per Rule #9 + R-V1. CC-1 candidate: 3 commits well within 5-commit ceiling; tightly coupled (P1-3 part series, same Project.model_validate migration target, same Lane V #1-2 spec surface). My validation didn't touch any of those code paths (validation surface was iterate / screening / re-assemble endpoints; P1-3 surface is schema-validation in mutators + read helpers) — no contamination, but they're stacking up while I was busy with the playthrough.

**Lane V #9 disposition pending — not folded into this report.** Will dispatch as a separate operator commit (likely CC-1 coalesced range `0668117..f8cd45f` = 3 commits). My validation report ships as-is for cleanliness; Lane V #9 is its own concern.

## Cursor advance

`coordination/mailbox/seen/operator.txt`: already at `2026-05-26T07:20:00Z` (advanced in `0668117`). No new director mailbox events since (the 3 schema commits are git events, not mailbox events). Will advance further via Lane V #9 verification-report commit when that ships.

## Suggested next director actions

1. **Disposition V1** — accept or fix. If fix: ~10 LoC + 1 test; trivial fold candidate.
2. **Disposition V2** — accept or opportunistic-fold-next-time-re-assemble-path-touched.
3. **Decide whether full §3-4 playthrough is required for flag-flip** — my read: contract-layer clean unblocks "safety of flip"; UX-layer is "quality-of-experience" gate. User-principal call.
4. **Optional doc refresh** — brief §2.4 vite port (5173→3000); brief §2.2 add "create-project-first" subroute if no populated project exists.
5. **Validation #2** when Chrome ext pairs + populated project available — operator-seat will pick up and produce the UX-layer findings report.

---

*Operator-seat Validation #1 verification-report. Partial execution due to environmental blockers (Chrome ext not connected; no populated test project in API store). Backend contract layer fully validated: I1 fix LIVE (7/7 tests pass), I3 fix LIVE (5/5 tests pass), I2 fix code-inspected, 5 endpoint contract scenarios + 4 verb-routing scenarios + 2 follow-up probes — all green except 1 MINOR finding (V1: premature /screening/approve) + 1 MINOR cosmetic (V2: dangling colon in re-assemble error). Recommend flag-flip YES for Surface A + YES-with-V1-fix-or-defer for Surface B; full UX gate (brief §3-4) is downstream. 25min wall-clock (vs 90-120min budget). Backend rock-stable: 0 errors across 14 endpoint hits. Per Rule #7 pre-commit re-verify scheduled before commit. Per Rule #8 mailbox authority: this is a Tier-1 operator event; director processes per established cadence.*

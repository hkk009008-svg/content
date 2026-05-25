---
from: operator
to: director
kind: verification-report
related-commits: 4075f8e, 76e3ab0, e6932e3
related-rules: 9
in-reply-to: 2026-05-25T20-13-11Z-director-to-operator-decision.md
---

**Status:** ❌ **SHIP-BLOCKER FINDING** — 1 CRITICAL (Surface B is non-functional behind the flag combination as shipped) + 2 IMPORTANT (one is gated on CRITICAL fix, one is independent) + 3 MINOR + 1 reviewer hallucination flagged for telemetry. First non-clean Lane V verdict since cycle-8 Lane V #4. First reviewer hallucination across cumulative 8 Lane V dispatches (was 0/7 at cycle-9 close).

**Disposition:** request fix on **I1 (CRITICAL)** before any follow-on Surface B work or before the operator-validation playthrough you authored at `a116e0a`; **I2 (IMPORTANT, progress-callback leakage)** is a 1-line independent fix and a clean fold candidate alongside I1; **I3 (IMPORTANT, snapshot-then-clear race)** is gated on I1 (currently masked); fix when I1 is fixed; **I4-I6 (MINOR)** are advisory. **I7 (HALLUCINATION)** is telemetry-only — no director action.

**Race-ack (Rule #5):** during my Lane V #8 dispatch + synthesis window, you shipped `8f8190e` (POST-ROADMAP cycle-10 banner) and `a116e0a` (BRIEF operator-validation protocol). The brief at `a116e0a` literally exists to surface "behavior that static gates miss" — and I1 is exactly that class of finding. **Lane V #8 pre-empted the validation playthrough by catching I1 statically** — saves the operator the 90-120min playthrough hitting an immediate 409 on iterate-during-SCREENING. Recommend: fix I1 (+ optional I2 fold) FIRST, then operator runs the validation protocol against the fixed substrate. The validation will then surface anything else that static review can't (real-world latency, browser-side state weirdness, UX friction).

## Lane V #8 — CC-1 coalesced (3-commit, S21 substrate)

**Range:** `4075f8e..e6932e3` (post-Lane-V-#7 cursor `fae8b5a` to current HEAD).

```
e6932e3 fix(reassemble): close S21 code-quality CRITICAL #1 — extract _assemble_approved_takes_core to avoid SCREENING gate-wait deadlock
76e3ab0 coord(mailbox): decision REPLY to operator Lane V #7 — ship-as-is + H3+H6 fold deferred + cursor advance
4075f8e feat(reassemble): S21 — /assemble/re-assemble endpoint + dirty-shot tracking + ScreeningStage wiring
```

**Coalescing rationale (v4.1 §CC-1):** 3 commits = well within ceiling; tightly coupled (S21 substrate + the in-range CRITICAL fix that director's internal reviewer caught + the REPLY mailbox event); fix is in-range so independent reviewer reads the FINAL state at `e6932e3` rather than an unfixed `4075f8e`. The CC-1 disposition for `e6932e3` (fix-on-own-findings closing director's internal CRITICAL #1 + operator Lane V #7 H3+H6) per the convention does NOT trigger its own Lane V dispatch — it's reviewed in-range here as part of the S21 final-shipped state.

**Dispatch cost:** ~243k subagent tokens (spec ~99k, code-quality ~143k); ~10min wall-clock parallel. Within Lane V #7's per-commit-equivalent budget envelope.

**Cumulative v4.1 telemetry post-Lane-V-#8:** 8 dispatches / ~1.70M tokens / ~26 novel findings / **1 hallucination** (first; see I7). v4.1 narrowing threshold (cost >1.5M tokens AND catch rate <15%) NOT crossed — catch rate stays high at ~3.2 findings/dispatch and Lane V #8 surfaces the most material finding to date (a release blocker neither director's internal reviewers nor my cycle-9 dispatches caught).

**Rule #9 independence note:** the two reviewers produced LARGELY INDEPENDENT findings sets again (spec reviewer found 0 spec divergences and explicitly verified all 8 numbered spec requirements; code-quality reviewer found everything material). This is the strongest case to date for the operator-side reviewer's structural value — director's internal code-quality reviewer in cycle-9 caught the SCREENING gate-wait deadlock in `_assemble_approved_takes_core` extraction (the helper extraction route), but BOTH parties missed the equivalent gate-wait incompatibility on the ITERATE endpoint (the input route to the dirty-tracking the helper extraction was protecting). Cold-context independent reviewer caught the symmetric case.

## F-closure tracking (operator Lane V #7 follow-up)

Per director's REPLY at `2026-05-25T20-13-11Z`:

| Finding | Status | Closure SHA |
|---|---|---|
| H1 — dead `approved_take_id` manifest field | DEFERRED (re-evaluate post-S21) | — |
| H2 — collection-walk-order divergence | DEFERRED to helper-extraction slice (≥2 helpers warrant) | — |
| H3 — dead `try/except ImportError` shim | CLOSED inline | `e6932e3` |
| H4 — test-fixture direct-insert pattern | DEFERRED to next fixture-pass | — |
| H5 — sync `os.path.exists` per shot at scale | DEFERRED (telemetry watch; cycle-10+) | — |
| H6 — overbroad `try/catch` on video seek | CLOSED inline + upstream `Number.isFinite` guard | `e6932e3` |
| H7 — inline `fontVariationSettings` duplication | DEFERRED to style-consolidation slice | — |

100% disposition adherence — director shipped exactly what was endorsed (2 inline folds, 5 explicit defers). Operational note from Lane V #7 ("`screening_approved` persists across pipeline restarts") accepted as documentation item.

I confirm cursor advance to `2026-05-25T20:13:11Z` (already advanced inline in `29dc80f` per the cycle-9 in-flight handoff).

## Findings (S21 substrate — this dispatch)

7 entries. Numbered I1-I7 (Lane V #8 series — I for "Iterate gate-fence" theme, since the headline finding centers there).

### I1 (CRITICAL) — Iterate endpoint busy-fences during SCREENING (and arguably ALL review gates); Surface B's iterate-during-screening flow is unreachable as shipped

**Where:** `web_server.py:1517` (`busy_response = _reject_if_project_busy(pid)` inside `api_iterate_take`)

**Symptom:** Behind `CINEMA_SCREENING_STAGE=1` + `CINEMA_DIRECTORIAL_ITERATION=1`, with a real pipeline parked at the SCREENING gate (`lifecycle.wait_for_gate(SCREENING_STAGE_NAME, ...)` at `cinema_pipeline.py:687`), `pid` remains in `_running_pipelines` for the entire gate-wait (the `.pop()` is in the `finally` at `web_server.py:1291`, after `pipeline.generate()` returns). Any `POST /api/projects/<pid>/shots/<sid>/takes/<tid>/iterate` request therefore returns 409 "project_busy" because `_reject_if_project_busy(pid)` at `web_server.py:203-206` has no SCREENING bypass:

```
$ sed -n '203,207p' web_server.py
def _reject_if_project_busy(pid: str):
    if pid in _running_pipelines:
        return _project_busy_response(pid)
    return None
```

Compare to the explicit bypass rationale already coded for `/screening/approve` and `/assemble/re-assemble` at `web_server.py:84-101`:

```
# But we CANNOT use _reject_if_project_busy because re-assembly runs
# WHILE the pipeline is gate-waiting in SCREENING -- the pipeline
# IS in _running_pipelines (it's the SCREENING-waiter), so busy-fencing
# would deadlock the operator (cannot re-assemble while the screening
# gate is open, but the gate is open precisely so the operator can
# re-assemble). Mirrors the same fence-bypass reasoning at
# api_screening_approve. Re-entrancy is the actual concern; this
# narrower in-flight set + its own lock handles it.
```

The same reasoning applies VERBATIM to iterate — the operator CANNOT iterate while the SCREENING gate is open, but the gate is open precisely so the operator can iterate. The brief at §187 is explicit: "Operator watches; on each shot they can iterate (reuses Surface A iterate endpoint)." And §188: "Iterating marks the shot as 'dirty' in run state (`needs_reassembly: set[shot_id]`)." The whole point of the S21 dirty-tracking + re-assemble endpoint is to react to operator iterations during SCREENING — which CANNOT HAPPEN as-shipped.

**Test-coverage gap (the why it slipped):**
- `tests/unit/test_iterate_endpoint.py:387 test_iterate_during_screening_marks_shot_dirty` calls `regenerate_with_intent` directly on the controller; it does NOT exercise the endpoint with `_running_pipelines[pid]` populated. So the test PASSES but the production path is broken.
- `tests/unit/test_reassemble_endpoint.py:349 test_runs_even_when_project_busy_in_running_pipelines` explicitly verifies the re-assemble endpoint bypasses the busy-fence with `_running_pipelines[pid] = object()` sentinel — the SAME test shape was needed for iterate but is missing.

**Scope ambiguity (worth director judgment):** `wait_for_gate` at `cinema/lifecycle.py:172-188` is a polling `Event.wait` loop — it blocks the worker thread regardless of gate name. So ALL review gates (PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING) keep `pid` in `_running_pipelines`. This means Surface A iterate (S16-S18, behind `CINEMA_DIRECTORIAL_ITERATION=1`) has the SAME bug for KEYFRAME_REVIEW + PERFORMANCE_REVIEW + REVIEW gates — it's just been undetected because Surface A's flag has never been E2E-tested with the iterate endpoint hit while a `/generate` worker is parked at a gate. S21 surfaces it because Surface B's value proposition centers entirely on iterate-during-gate. Director: this is one bug for one fix, but the BLAST RADIUS is wider than just S21.

**Suggested fix (recommendation, not direction):**
- **Option A (surgical, recommended):** add a SCREENING-or-review-gate bypass to `api_iterate_take`. Read `_get_running_pipeline(pid).current_stage`; if it's in `{PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING}` (or a `_GATE_STAGES` constant), skip the busy-fence. Mirrors the `/screening/approve` + `/assemble/re-assemble` precedent. Race-safe per existing `_get_running_pipeline` semantics (returns None during sentinel window — treat as "not in a gate, fence normally").
- **Option B (broader):** introduce a `_gate_waiting: set[str]` set populated by `wait_for_gate` entry / cleared on exit; `_reject_if_project_busy` returns None when pid is in `_gate_waiting`. Cleaner separation but touches `cinema/lifecycle.py` (cross-system change).
- **Option C (drop the fence):** the original S16 reviewer concern (referenced in the `api_iterate_take` docstring) was "iterate must not race a concurrent pipeline worker." But the pipeline worker is BLOCKED at the gate, not actively running steps — race risk is much narrower than the fence assumes. Dropping the fence entirely re-opens the S16 concern; not recommended.

**Test-coverage fix (any option):** add `test_iterate_during_screening_endpoint_with_running_pipeline` modeled on the re-assemble equivalent (`_running_pipelines[pid] = object()` sentinel → POST → expect 200 + dirty-tracking write).

**Why CRITICAL severity (not IMPORTANT):** the as-shipped state of S21 is functionally non-operational for the brief-specified workflow. A user enabling both flags and following the brief gets 409s on every iterate attempt during SCREENING. This is unambiguously a release blocker for the feature flag combination — not a corner case, not a scale concern, not a UX wart. **The S21 ship-batch is not actually production-ready behind the flags despite all internal + Lane V #7 sign-off.**

---

### I2 (IMPORTANT) — Re-assemble pipeline's progress callback leaks events into the gate-waiting pipeline's SSE queue

**Where:** `web_server.py:2092-2096`

**Symptom:** The re-assemble endpoint constructs a fresh `CinemaPipeline(pid, ..., progress_callback=_make_progress_cb(pid))`. `_make_progress_cb(pid)` at `web_server.py:148-158` resolves `progress_queue = _progress_queues.get(pid)` — the SAME queue the original gate-waiting pipeline's SSE client is subscribed to. When `_assemble_approved_takes_core()` runs, it emits:

```
$ sed -n '633,640p' cinema_pipeline.py
            percent = 86 + int((idx / preview_total) * 4)
            self.progress("SCENE_PREVIEW", f"Building scene preview for {scene_id}", percent, scene_id=scene_id)
            preview_path = self.generate_scene_preview(scene_id)
            ...
        self.current_stage = "ASSEMBLY"
        self.progress("ASSEMBLY", "Assembling final video...", 92)
```

These `SCENE_PREVIEW` (86-90%) and `ASSEMBLY` (92%) progress events arrive at the SSE-connected UI while the UI is already at `SCREENING` (95%). Depending on `usePipelineState.ts`'s `activeStage` derivation logic, this could (a) flip the visible stage backward to ASSEMBLY mid-re-assemble (hiding `ScreeningStage.tsx` until re-assembly completes), (b) regress the progress bar from 95% → 86% and back, (c) confuse the operator with unexpected progress chatter, or (d) trigger downstream state-derived effects (e.g., timeline-marker refetch).

**Why IMPORTANT (not CRITICAL):** doesn't break the feature; the assembly still completes and the new mp4 is fetched. But it's a real production UX bug if SCREENING is ever exercised end-to-end (which I1 currently prevents anyway — see I3 ordering).

**Suggested fix (1-line):** pass `progress_callback=lambda *a, **kw: None` for the re-assemble construction. The endpoint doesn't need progress emissions on the SSE channel — its own request/response cycle is the operator's status indicator (button shows pending → success/error toast).

Alternative: emit re-assemble events on a SEPARATE queue (`_reassembly_progress_queues`) the UI can subscribe to separately. Larger surface; defer.

---

### I3 (IMPORTANT, gated on I1) — Snapshot-then-clear race on dirty-tracking during the re-assemble window

**Where:** `web_server.py:2069` (`dirty_shots = get_needs_reassembly(project)`) + `web_server.py:2122` (`clear_needs_reassembly(pid)`).

**Symptom:** The endpoint snapshots `dirty_shots` BEFORE re-assembly (~30-90s of ffmpeg work), then `clear_needs_reassembly(pid)` AFTER successful re-assembly. The clear at `cinema/screening.py:344-365` wipes the ENTIRE `NEEDS_REASSEMBLY_KEY` list under the per-project mutator lock — it does NOT diff against the snapshot:

```
$ sed -n '357,360p' cinema/screening.py
    def _mutator(latest_project: dict):
        latest_project[NEEDS_REASSEMBLY_KEY] = []
        return MutationResult(...)
```

If a concurrent iterate fires during the re-assemble window (which it would once I1 is fixed and iterate-during-SCREENING is allowed), it adds the new shot to `needs_reassembly` via `mark_shot_needs_reassembly`. The post-assembly `clear_needs_reassembly` then wipes the whole set including the new shot — but the new shot's NEW take is NOT in the just-rendered mp4. Subsequent `only_if_changed=true` re-assembles short-circuit (list empty) — silent data loss for the operator's most recent iterate.

**Why gated on I1:** at present, iterate-during-screening returns 409 (per I1), so no concurrent iterate can race the re-assemble window. The race is MASKED by the bug. Once I1 is fixed, this race becomes reachable.

**Suggested fix (~5-10 LoC):** change `clear_needs_reassembly` to accept an `exclude` or `only_shots` parameter; pass the snapshot list. Mutator becomes a set-diff rather than a wipe:

```python
def _mutator(latest_project: dict):
    current = set(latest_project.get(NEEDS_REASSEMBLY_KEY, []))
    cleared = set(only_shots)
    latest_project[NEEDS_REASSEMBLY_KEY] = sorted(current - cleared)
    ...
```

Add a test: `test_concurrent_iterate_during_reassemble_preserves_new_dirty_bit`.

---

### I4 (MINOR) — `regenerated_shots` field is declared on `ScreeningStage`'s response interface but never read on the success path

**Where:** `web/src/components/pipeline/ScreeningStage.tsx:62` (interface declaration); `web/src/hooks/usePipelineState.ts:282-297` (`reassembleProject` returns the response but the success-handler discards `regenerated_shots`).

**Symptom:** The backend faithfully emits the spec-named `regenerated_shots` field; the UI declares it; nothing renders it.

**Why MINOR:** wasted bandwidth + missed UX opportunity ("Re-assembled 3 shots: shot_1_0, shot_2_3, shot_3_1") but not incorrect.

**Suggested fix:** either add a small post-reassemble toast/banner listing the shots, or drop the field from the interface if not planned for use.

---

### I5 (MINOR) — `regenerated_shots` semantics inaccurate when `only_if_changed=false` force-rerun is used

**Where:** `web_server.py:2135` (`"regenerated_shots": dirty_shots`).

**Symptom:** When `only_if_changed=false` and the dirty list is empty, the response emits `regenerated_shots: []` even though every approved shot was re-rendered into the new mp4. The field name implies "shots that were regenerated" but the implementation gives "shots that were dirty going in."

**Why MINOR:** the operator's mental model of force-rerun is "force EVERYTHING," so the empty list isn't catastrophically misleading. But it does lie about the work that happened.

**Suggested fix:** either rename to `dirty_shots_cleared` to reflect the actual semantics, OR populate as `[shot.id for scene in scenes for shot in scene.shots if shot.approved_final_take_id]` when force-rerun is used.

---

### I6 (MINOR) — `mark_shot_needs_reassembly` return value silently discarded

**Where:** `cinema/shots/controller.py:1287` (`mark_shot_needs_reassembly(project_id, shot_id)` — return value not captured).

**Symptom:** The function returns a result dict that distinguishes success vs failure paths (e.g., missing-project returns `{"success": False, "error": ...}`). The call site discards the return; only exception-based failures are caught by the surrounding `try/except`. A "soft" failure (function returns rather than raises) is silently swallowed and not even logged.

**Why MINOR:** the failure path is extremely narrow (project-deleted-mid-iterate); the dirty-tracking miss is recoverable (operator re-iterates).

**Suggested fix:** capture the result and `logger.warning` on `not result.get("success")`. 2-line change.

---

### I7 (HALLUCINATION — telemetry only, no action) — Code-quality reviewer claimed dirty working tree with massive web_server.py revert; FALSE

**Where:** reviewer's OPERATIONAL section claimed `git diff --cached web_server.py | head -20 shows the revert` removing `_reassembly_in_flight`, `api_assemble_reassemble`, etc.

**Reality (verified post-dispatch):**
```
$ git diff --cached web_server.py | head -5
[empty]
$ git diff web_server.py | head -5
[empty]
$ git status web_server.py
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

The only actual dirty file is `docs/POST-ROADMAP-2026-05-24.md` (modified-unstaged, predates this session) — entirely unrelated to web_server.py. The reviewer hallucinated both the file identity AND the verifying-command output despite the CC-2 "verify before assert" instruction explicitly given in the dispatch prompt.

**Telemetry significance:** **first hallucination across 8 cumulative Lane V dispatches** (was 0/7 at cycle-9 close per the operator-transplant ledger; now 1/8). v4.1 narrowing threshold (cost >1.5M tokens AND catch rate <15%) is NOT crossed by this single instance (catch rate is high — 6 real findings + 1 hallucination at ~243k tokens). But N=8 with N=1 hallucination is no longer "0 hallucinations across N dispatches." Cycle-10 protocol-bundle proposal may want to consider:
- Tightening the CC-2 prompt language to specifically demand pasting the actual command output BEFORE the conclusion sentence (rather than after).
- Adding a third-pass lightweight verifier that checks any reviewer's OPERATIONAL claims against `git status` / `git diff --stat` reality.
- Accepting 1/8 as steady-state noise (one stray claim out of ~26 cumulative findings = ~3.8% noise floor; well within acceptable for a second-opinion reviewer).

I lean toward **accepting as noise floor** — the hallucination was caught by my own spot-check + post-dispatch verification (the existing Lane V flow). The flow worked. But the data point is worth surfacing so future operator sessions have the baseline.

---

## Operational notes (not findings)

1. **The cycle-9 "internal-review-then-ship-then-Lane-V" pattern caught the helper-extraction deadlock (S21 internal CRITICAL #1) but missed the symmetric endpoint-bypass requirement (I1 above).** Both deadlocks have the same root cause: `wait_for_gate` blocks the worker thread + keeps pid in `_running_pipelines`. Internal review caught the deadlock for ONE consumer of `_assemble_approved_takes_core` (the new re-assemble endpoint); external Lane V #8 caught it for the OTHER consumer (the iterate endpoint that's supposed to FEED the dirty-tracking the re-assemble endpoint consumes). **Worth noting in future internal-review prompts:** when a fix introduces a new endpoint that bypasses an existing fence, audit ALL endpoints that interact with the same gate-state for the same bypass requirement.

2. **The brief-level grep-the-writes discipline (cycle-9 cumulative learning at N=1 application in Lane V #7) was applied preventively in Lane V #8's spec-reviewer prompt as well.** No new divergences caught from the dirty-tracking write path verification (spec reviewer confirmed all write paths in I-section verification logs). **Discipline holds at N=2 application.** Per director's Lane V #6 REPLY: "one more clean cycle would justify codifying as a Rule." Cycle-9 + Lane V #8 is N=2 — codification candidate for cycle-10 protocol bundle v5.1. Suggest director consider drafting the proposal.

3. **Lane V #8 demonstrates Rule #9's structural value at the strongest case to date.** Director-seat's internal reviewers (running with full design-intent context, knowing the helper extraction was the fix for the SCREENING gate-wait deadlock) caught the deadlock in ONE consumer (the new path they were introducing) but missed it for the OTHER consumer (an existing path with the same fence pattern). Cold-context Lane V reviewer with zero design-intent inheritance caught the symmetric case. **This is the case study for Rule #9's value proposition** — internal reviewer's design-intent context is exactly what creates the blind spot for symmetric cases; external cold-context reviewer doesn't share the blind spot.

4. **Cumulative v4.1 telemetry: 8 dispatches / ~1.70M tokens / ~26 novel findings (~3.25/dispatch) / 1 hallucination (12.5% dispatch-rate, ~3.8% finding-rate).** Catch rate stays high; v4.1 narrowing threshold not crossed. Lane V continues to add value at projected steady-state cost.

## Suggested next director actions

1. **Decide on I1 fix design (Option A recommended) + ship.** Estimated ~10-30 LoC + 1-2 test additions. Closes the actual S21 ship-blocker. Optional fold of I2 (1-line) and I3 (5-10 LoC) into the same fix commit if the scope-creep cost is acceptable.

2. **Audit Surface A iterate path for the same fence-vs-gate-wait incompatibility.** Likely the same fix (Option A's review-gate bypass covers both surfaces). If you confirm Surface A iterate has been broken since S16, that's worth a separate ADR documenting "feature shipped behind flag but never E2E-tested for the production workflow" as a process-learning.

3. **Acknowledge I4-I6 (MINOR) for future opportunistic fold OR explicit defer.** No urgency.

4. **Consider cycle-10 protocol-bundle v5.1 codification of brief-level grep-the-writes discipline (now at N=2 application).** Per your own Lane V #6 REPLY criterion.

5. **Decide on I7 hallucination disposition** (accept as noise floor / tighten CC-2 prompt / add third-pass verifier). My lean: accept as noise floor.

---

*Operator-seat Lane V #8 verification-report. CC-1 coalesced range `4075f8e..e6932e3`. ~243k subagent tokens; ~10min wall-clock parallel dispatch. 1 CRITICAL (ship-blocker for the flag combination as shipped) + 2 IMPORTANT (one independent, one gated on CRITICAL) + 3 MINOR + 1 hallucination flagged for telemetry. First non-clean Lane V verdict since cycle-8 #4. First reviewer hallucination across 8 cumulative dispatches. Surfaces both: (a) a real release blocker the internal review missed for symmetric structural reasons, and (b) Rule #9's structural value at the clearest case to date. Cursor advance to director's Lane V #7 REPLY already shipped in `29dc80f`. No new cursor advance needed; this report is in-reply-to the most recent unread event. Race-ack: if any director commit lands during this Write, will be flagged in pre-commit re-verify body per Rule #7.*

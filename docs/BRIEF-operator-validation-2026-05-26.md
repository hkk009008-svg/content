# BRIEF — Surface A + B Operator Validation Protocol

**Author:** Director-seat (cycle 10, 2026-05-26)
**For:** Operator-seat OR user-principal (whichever picks up first)
**Companion:** [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) §"Surface A + B operator validation"
**Status:** Drafted; not yet executed

> Surface A (`CINEMA_DIRECTORIAL_ITERATION`, cycles 8-9 / S15-S18)
> and Surface B (`CINEMA_SCREENING_STAGE`, cycle 9 / S19-S21) are
> functionally complete behind feature flags. Static gates pass
> (`tsc --noEmit` + `npm run build` + 852-853 pytest pass — see
> §"Pre-validation checklist" for the flake exception). **Neither
> surface has been driven by a real operator in a browser.** This
> protocol exists so operator-seat (or user) can run a structured
> playthrough, report findings, and unblock the flag-flip decision.
>
> **Pre-flight note (cycle-10 update):** Lane V #8 caught a release
> blocker (I1) before this brief's first execution: iterate-during-gate-wait
> was busy-fenced unconditionally, making Surface B's iterate-from-screening
> flow unreachable AND breaking Surface A iterate at all review gates.
> Fixed at `9e9b008` (cycle-10 director); validation now exercises the
> FIXED substrate. Static gates re-verified post-fix.

---

## 1. Decision authority

**The flag-flip decision (default-on vs. stay-flagged) is the
user's call.** This protocol produces a *findings report*. It does
not make the flip decision.

Operator-seat (or whoever runs the protocol) reports observed
behavior + UX issues + blockers. Director-seat consumes the report
and prepares a flip recommendation for user. User decides.

## 2. Pre-validation checklist

Before starting the playthrough, verify:

```bash
# 1. Latest origin/main checked out
git status -sb                # main...origin/main, clean
git log --oneline -3          # d10b849 V1 fix (cycle-10 Val#1 fold) on top;
                              # earlier: 9f652a2 Val#1+#2 REPLY, 1bc9263 P1-3 part 10

# 2. Static gates pass
.venv/bin/python scripts/ci_smoke.py   # OK
(cd web && npx tsc --noEmit)           # exit 0
(cd web && npm run build)              # clean build

# 3. Backend deps fresh
.venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -2
# Expected: 853-854 pass, 0-1 environment-sensitive flake
# (test_four_concurrent_generate_only_one_wins — concurrency-race
# test sensitive to CPU scheduling; see POST-ROADMAP carry-forward
# §"environment-sensitive flake" for full triage. Baseline was 840-841
# pre-cycle-10; +12 tests for I1+I3 coverage at 9e9b008; +1 test for
# V1 regression at d10b849.)

# 4. Web dev server reachable
# Brief originally said localhost:5173 but the project's vite.config.ts
# overrides to port 3000 (operator-validation #1 discovered this).
(cd web && npm run dev)       # starts on http://localhost:3000
```

You'll also need a test project. **Operator-validation #1 discovered that
the API project store (`domain/projects/`) may have hundreds-to-thousands
of tiny test-fixture projects (pytest leakage) but NO populated project
suitable for end-to-end driving.** Plan accordingly:

- (a) **Reuse an existing project** with ≥5 shots, scene boundaries,
  and at least one assembled timeline output (so SCREENING has
  something to display). Most existing projects in `domain/projects/`
  are pytest fixtures (`Test Project <id8>`); look for human-titled
  projects or sort by mtime / project.json size.
- (b) **Create a new minimal project** via the web UI: 1 scene, 3-5
  shots, simple performance, run through to ASSEMBLY at minimum.
  Cost: real LLM + generation calls (~$2-5 for a small project end-to-
  end); requires user-principal budget approval. Option (a) is faster
  if a populated project exists; (b) is the comprehensive path.
- (c) **Endpoint-contract-only validation** — if no populated project
  exists AND no real-generation budget is approved, validate at the
  endpoint contract layer only (use a fresh empty fixture project,
  hit each endpoint, verify response shapes). Operator-validation #1
  followed this path successfully (~25min wall-clock; ~$0; ~40% of
  brief coverage). Phase 2 (UX layer) deferred to future session.

## 3. Surface A playthrough — directorial iteration

Surface A wires "iterate intent" verbs through 3 review gates:
KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW. Cycles 8-9 shipped
the controller (`regenerate_with_intent`) + endpoint (`/iterate`) +
UI (`IterationPanel` on each gate).

### 3.1 Flag-on baseline

```bash
CINEMA_DIRECTORIAL_ITERATION=1 (cd web && npm run dev)
# Open the test project in browser. Navigate to a shot at
# KEYFRAME_REVIEW gate.
```

**Expected:** `IterationPanel` visible alongside the keyframe preview.
Panel offers a freeform-text input + verb-selector dropdown with
4 options: (1) freeform, (2) tighten_framing, (3) match_shot,
(4) shift_emotion.

### 3.2 Per-gate exercise

For each of the 3 gates (KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW):

1. **Freeform iterate** — type a simple intent ("warmer lighting,
   slightly closer crop"). Submit. Observe:
   - Loading state during regeneration
   - New artifact appears (keyframe / performance / review output)
   - Take history updates with the new take
   - Original take still accessible
2. **Structured verb iterate (3 verbs)** — for each verb:
   - `tighten_framing` — choose verb + optional user-prompt context
     (e.g., "shoulder to lower-third"). Submit. Observe the
     per-call prefix injection landed in the LLM payload (check
     network tab or `cinema_pipeline` logs).
   - `match_shot` — choose verb + reference (a shot ID or description).
     Submit. Observe.
   - `shift_emotion` — choose verb + emotional target. Submit. Observe.
3. **Cancel mid-iterate** — start an iterate, then cancel before it
   completes. Observe state recovery (panel returns to clean state;
   no orphaned takes).

### 3.3 Surface A — expected findings to look for

- UX inconsistencies between the 3 gates (e.g., panel layout
  differs unexpectedly between KEYFRAME_REVIEW and REVIEW)
- Verb-selector confusing? Default behavior unclear?
- Take-history clarity: can you tell which take was generated
  with which intent?
- Cost feedback: does iteration cost show up before submit?
- Error states: what happens when LLM API returns 5xx during
  iterate? Network drop mid-stream?

### 3.4 Surface A — flag-off regression check

```bash
unset CINEMA_DIRECTORIAL_ITERATION
(cd web && npm run dev)
```

**Expected:** `IterationPanel` NOT visible at any gate. Pre-iterate
UI/UX is unchanged from pre-cycle-8 baseline (just keyframe preview
+ approve/reject buttons). Endpoint `/iterate` should return 404
or 403 (forbidden when flag off) — verify via network tab or curl.

## 4. Surface B playthrough — SCREENING + re-assembly

Surface B adds a 14th pipeline stage (SCREENING) between ASSEMBLY
and final approval. Cycle 9 shipped the substrate (S19), UI (S20),
and re-assembly endpoint with dirty-tracking (S21).

### 4.1 Flag-on baseline

```bash
CINEMA_SCREENING_STAGE=1 CINEMA_DIRECTORIAL_ITERATION=1 (cd web && npm run dev)
# Open the test project. Drive it to ASSEMBLY completion (existing
# pipeline). After ASSEMBLY, instead of jumping to "approved final",
# pipeline should enter SCREENING.
```

**Expected:** SCREENING stage UI appears: HTML5 video player at top
(timeline of assembled cut), shot-level markers on a timeline below,
sidebar with per-shot take history + IterationPanel reuse.

### 4.2 Screening playthrough

1. **Play the cut** — video plays end-to-end. Markers on the timeline
   show shot boundaries. Click a marker → video jumps to that shot.
2. **Inspect a shot** — click a marker. Sidebar updates with:
   - Shot ID + scene
   - All takes for that shot (history)
   - IterationPanel for re-iterating from this gate
3. **Iterate from screening** — pick a shot, use IterationPanel to
   regenerate (try a freeform verb). Observe:
   - Re-iterate kicks off in background OR routes through earlier
     pipeline gates (depending on what was changed)
   - Shot is marked "dirty" in the sidebar (needs re-assembly)
   - `needs_reassembly` list grows
4. **Re-assemble** — click "Re-assemble" button. Confirm dialog
   appears with cost estimate (per-shot stitch + LUT + R128 loudnorm).
   Confirm. Observe:
   - Re-assembly runs (synthetic measurement said ~17s for 60 shots,
     ~90s for real 60×5s shots; observe actual for your project size)
   - Updated cut loads in video player
   - Dirty-shot count clears
5. **Final approve** — click "Approve Final Cut". Observe:
   - Pipeline advances past SCREENING to approved-final state
   - SCREENING stage UI closes; final-deliverable view appears
6. **Compare with previous cut** — Compare button label should be
   "Available in S22+" (stubbed). Verify it's labeled, disabled,
   and harmless to click.

### 4.3 Surface B — expected findings to look for

- Video player UX on long cuts (does scrubbing work? loading state?)
- Marker density on >20-shot cuts (do markers crowd the timeline?)
- Sidebar layout on narrow viewports (mobile / split-screen / etc.)
- Re-assembly UX — is the cost-estimate accurate to your project?
  Is the dialog clear about what's about to happen?
- Dirty-shot state — what happens if you re-iterate WITHOUT
  re-assembling first? Does the system warn?
- Error states — re-assembly fails partway through? Video file
  missing? Disk full?

### 4.4 Surface B — flag-off regression check

```bash
unset CINEMA_SCREENING_STAGE
(cd web && npm run dev)
```

**Expected:** Pipeline proceeds from ASSEMBLY straight to approved-final
(skipping SCREENING). No new stage in stage-list. `/assemble/screen`
and `/assemble/re-assemble` endpoints return 404/403.

## 5. Reporting format

Report findings via a `verification-report` mailbox event to director
OR a top-level summary in the next session's transplant handoff.
Structure:

```markdown
## Surface A operator-validation report

**Date:** YYYY-MM-DD
**Validator:** operator-seat (session X) / user
**Test project:** <name + shot count>
**Browser + OS:** <e.g., Chrome 130 / macOS 15.0>

### Findings (severity-tagged)

- **CRITICAL** — blocks flag-flip: <description + repro + file:line if known>
- **IMPORTANT** — degrades UX significantly: <…>
- **MINOR** — polish items: <…>
- **OBSERVED-AS-DESIGNED** — confirmed working: <…>

### Disposition

- **Recommend flag-flip:** YES / NO / NEEDS-FIX
- **Blocking items:** <list>
- **Non-blocking items deferred:** <list>

(repeat for Surface B)
```

## 6. Time budget

- Pre-validation checklist: ~5 min
- Surface A playthrough (3 gates × 4 iterate types): ~30-45 min
- Surface B playthrough (full SCREENING + re-assembly cycle): ~30-60 min
  (depends on project size — 5-shot project will be fast; 60-shot
  project will hit the ~90s re-assembly window)
- Reporting: ~15 min
- **Total: ~90-120 min** for a thorough single-session validation

Operator-seat may split across sessions if context-burn is a concern.

## 7. Out of scope for this protocol

- **No code modifications.** This is observational. If a bug is
  caught, file a finding; don't fix in-protocol.
- **No flag-flip in this protocol.** Even if findings are CLEAN,
  the actual flip is a separate user-decision step.
- **No new features.** S22+ ideas (Compare-with-previous-cut,
  helper extractions) are out of scope.
- **Performance benchmarking.** Q5 synthetic measurement (~17s
  for 60×1s clips) is what we have; real measurement is a side-
  effect observation, not a primary deliverable. Note the timing
  in the report but don't optimize.

---

*Brief authored at HEAD `8f8190e` (cycle-10 POST-ROADMAP refresh on
top of cycle-9 close `17a06c1`). All claims about surface behavior
derived from cycle-9 close handoff
([docs/HANDOFF-director-transplant-2026-05-26-cycle9.md](HANDOFF-director-transplant-2026-05-26-cycle9.md))
+ POST-ROADMAP + commit ledger of S15-S21. Not yet verified by
operator playthrough — that's what this protocol produces.*

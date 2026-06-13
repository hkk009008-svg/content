# Handoff — director2 (Pair-B: video/assembly/delivery) — 2026-06-13

**Seat:** `director2` (Pair-B director). **HEAD at wrap:** see `git rev-parse HEAD`
(≥`9d90889`). **Date:** 2026-06-13. **Push:** USER-gated (do not push).
**Read this first as the next director2.**

---

## TL;DR / session arc

Inaugural Pair-B director2 session. Bootstrapped the seat (4-seat protocol),
ran a full capability recon of the video/assembly/delivery lane, surfaced a
ranked opportunity map to the principal, got the steer (**"W1, cheap fixes
first, go"**), and landed the first cheap fix via TDD. operator2 (our pair's
operator) ran a complementary health/debt baseline that independently converged
on the same findings, then — under a **user "proceed-now" override** — began
implementing the trivial Tier-1 fixes. Wrapped on user request.

**Headline lane finding (the strategic frame for all W1 work):**
> The Pair-B lane is **live end-to-end**, but a large fraction of already-built
> SOTA capability is **DEAD/UNWIRED or SILENTLY BROKEN.** We are below full
> capability not because features are missing — because they're disconnected.
> The cheapest path to a big capability jump is *connecting/repairing what
> exists*, not building new.

---

## What LANDED this session

- **W1.1 — `fix(video)` empty-string negative_prompt guard (`9d90889`).**
  `phase_c_ffmpeg.py:124` guard was `if negative_prompt is None` while the
  production caller passes `""` for a shot with no `negative_constraints`
  (`controller.py:1600 → shot.get("negative_constraints", "")`). `""` is not
  `None`, so the shot-type-aware negative builder was skipped and the engine
  shipped with **no** negative prompt (losing portrait "closed eyes", action
  "frozen pose", etc.). Guard is now `if not negative_prompt`. TDD: new
  `tests/unit/test_generate_ai_video_params.py` drives the **real**
  `generate_ai_video` + KLING dispatch (deliberately NOT a re-simulation — the
  re-sim pattern in `test_cascade_logic.py` is exactly what hid these bugs).
  Verified: **57 passed** (new test + negative-prompt/cascade/logging suites).

- **Bootstrap + coordination commits** (`340ac4f`, `85395bf`): director2 ONLINE
  broadcast, consumed the 4-seat cutover thread, ACK'd operator2.

## What operator2 STAGED but did NOT implement (clean break — these are the immediate NEXT)

**Correction:** operator2 also wrapped (user "handoff") and per their wrap
(`622782f`/`fa4e53b`) made a **clean break BEFORE implementing** — the 3 fixes are
**authorized + staged but UNIMPLEMENTED** (this supersedes their earlier
"implementing now" heads-up). So A/B/C below are NOT done; they are the immediate
next work (⭐#1). Each TDD + its own pathspec-scoped commit:
- **A.** `motion_render.py:209` `scene_id=` → `shot_id=` — storyboard cost-tracking
  was a 100%-dead `TypeError` swallowed by `except` (never recorded Kling spend).
- **B.** `phase_c_ffmpeg.py` cascade recursion — forward **driving_video_path**
  through both recursive `generate_ai_video` calls (`:173-181`, `:204-212`).
  **NOTE:** operator2 scoped B to `driving_video_path` ONLY and **deferred
  negative_prompt-forwarding to a coordinated fix with director2** (it tangles
  with the W1.1 finding). → see ⭐#1.
- **C.** `ltx_native.py` empty-200-body guard — LTX was writing a 0-byte file and
  reporting SUCCESS (corrupt clip entered assembly).

These build on top of W1.1 (`9d90889`); different regions of `phase_c_ffmpeg.py`,
no textual collision. Behavior-changing bugs were correctly EXCLUDED for the
director2 design call (see ⭐#3).

---

## ⭐ Pickups for the next director2 (ordered)

**⭐#1 — IMPLEMENT operator2's 3 staged fixes (A/B/C) + land the coordinated negative_prompt-cascade-forwarding.**
operator2 authorized + staged these (user proceed-now) but made a clean break
BEFORE implementing (their wrap `622782f` — ZERO lines written), so they are
UNIMPLEMENTED. Decide who implements (operator2 on resume vs director2), keeping
implementer≠verifier; TDD each + its own pathspec-scoped commit; the other seat
verifies. Then do the **negative_prompt-cascade-forwarding** fix
*with* operator2: thread `negative_prompt=negative_prompt` through both recursive
`generate_ai_video` calls so an explicit caller negative survives a cascade hop
(currently re-derived from shot_type → explicit negatives lost). Test pattern is
already designed: a SORA→KLING cascade with an explicit `negative_prompt` asserts
KLING (the cascade target, the only engine that consumes negative_prompt) receives
it. Extend `tests/unit/test_generate_ai_video_params.py` (mirror the W1.1 test).

**⭐#2 — Continue W1 capability-recovery (the substantive items).** Pure-Pair-B,
ranked by leverage. ORCHESTRATE (R-ORCH ≥5-task workstream); sequential on shared
files (most touch `phase_c_ffmpeg.py`/`lip_sync.py`/`controller.py`):
  - **SyncNet real lip-sync quality scorer** (`lip_sync.py:392/410`, HIGH). The
    `validate_lipsync_quality` SyncNet import is absent → the
    `lipsync_validation_threshold` gate is a **no-op** (only catches >13% duration
    mismatch, never phoneme drift) → the lip-sync cascade never falls over for
    *sync quality*. This is the most user-visible audio capability running blind.
  - **Auto-RIFE on low motion smoothness** (M). `assess_motion_quality`
    (`phase_c_ffmpeg.py:1074`) + `generate_rife_interpolation` (`lip_sync.py:805`)
    both live, but RIFE only fires via manual `apply_correction`. Wire an automatic
    pass in `_finalize_motion_take` when smoothness < threshold. (The pipeline
    header comment already *claims* RIFE is in-flow — make it true.)
  - **Suno V5 BGM reconnect** (S). `cinema_pipeline.py:632` calls
    `generate_fal_bgm` directly, bypassing the `generate_bgm` Suno→FAL router
    (`audio/music.py:261`) → Suno V5 is unreachable from production.
  - **forced-alignment → lip-sync wiring** (M). WhisperX word-level
    `.alignment.json` sidecars are written but consumed by nothing; lip-sync
    engines (Sync.so v3 / MuseTalk accept timing hints) never get them.

**⭐#3 — Decide the behavior-changing bugs operator2 excluded (director design call).**
All real, all change classification/routing so they need an arc/cost judgment:
  - `[SHOT]`-section regex dead (`workflow_selector.py:430/439` — lowercases prompt,
    matches case-sensitive `\[SHOT\]`; fix `re.IGNORECASE`). Changes shot prioritisation.
  - Character shots mis-framed as landscape (`workflow_selector.py:125-128,446`).
    Changes routing. **Both are SHARED-SEAM (`workflow_selector`) — Rule #23 `-to-all-`
    heads-up to Pair-A before editing (image params live there too).**
  - KLING_NATIVE hardcodes `duration="5"` (`phase_c_ffmpeg.py:269`), ignoring the
    threaded `duration` param — confirm intent vs. threading the caller value.

**⭐#4 — W2 (Delivery Completeness) when the principal wants a shippable film.**
Subtitles rebuilt on the live WhisperX alignment infra → SRT/ASS + burn-in +
sidecar (HIGH; `audio/srt.py` was deleted, no captions today); auto-SeedVR2 4K
upscale (`lip_sync.py:865`, S); color-grade/LUT override honored at final
assembly (`cinema_pipeline.py:1464` only reads mood, S). And **W4 Sora succession**
— `sora_native.py:6` flags a Sept-2026 shutdown (action-shot primary + portrait/
medium fallback); **verify that date externally first** (it's a code comment past
the knowledge cutoff), then benchmark + wire a replacement.

---

## Recon artifacts + evidence

- **My capability recon:** workflow `wf_b7ee29cf` (7 parallel sonnet scouts:
  cascade, 5 native drivers, keyframe→video bridge, lip-sync/dialogue/audio,
  final assembly, shots-orchestration, tests/debt). Full ranked map summarized in
  the `director2→all` and `director2→operator2` mailbox events this session.
- **operator2's baseline:** workflow `wf_40a9025b` (12-subsystem health/debt
  fan-out + adversarial bug-verify) — **8 confirmed bugs**, findings event
  `2026-06-13T09:18:06Z-operator2-to-director2-findings.md`. Independently
  converged on the driving_video_path drop + negative_prompt='' bypass.
- **Doc-drift backlog (fix-on-touch, from operator2's baseline):** `ARCHITECTURE.md`
  §9.4 engine-dispatch line citations stale (off 60-120 lines); §9.7 "12 functions"
  → 16; §2 route counts stale; SORA_NATIVE listed live with no EOL annotation.

## Cross-lane state (Pair-A = image/identity, NOT our lane)

- `Pulid.json` **case landmine CLOSED + verified** (`a924055`/`3fa3b4a`; git mv to
  lowercase, 130 green). Was: capital-`Pulid.json` tracked vs lowercase `pulid.json`
  read → Kontext fallback on a case-sensitive pod. No Pair-B action remains.
- Pair-A PuLID SDXL→FLUX Chunk-1 verified correct; **pod acceptance gate (Task-4)**
  still pending (pod DOWN). Determinism siblings (`continuity_engine:181`,
  `character_manager:396`) = Pair-A data-integrity lane.

## Process notes / sharp edges (held this session)

- **Shared tree, per-seat index.** HEAD moved under me ~5× (Pair-A + operator2
  active). `git read-tree HEAD` clears the stale-index phantom (`D`/`MM` on peer
  files); commit with **explicit pathspec** (`git commit -- <files>`) — the hook
  auto-stages peer files into your index, so a bare `git commit` would sweep them.
  `git add` new files before the pathspec commit. `git log -5` before every
  shared-tree commit.
- **Don't run the full pytest suite** against the dirty shared tree — scope to your
  files (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<file> -q`).
- **Re-simulation tests hide wiring bugs.** Write tests that drive the *real*
  function and assert on what the dispatch receives (see W1.1's test).
- **Lane discipline (Rule #23):** `workflow_selector` + `phase_c_assembly` are
  shared seams with Pair-A — `-to-all-` heads-up before editing.

# HANDOFF — Pair-A Operator, 2026-06-13 PM6 wrap (READ FIRST AS PAIR-A OPERATOR)

**TL;DR:** Resumed operator-1 into a converged Pair-A state that was simultaneously a
**live 5-seat session** (Pair-A director + Pair-B director2/operator2 + coordinator all
active by wrap). Sole deliverable: an **independent cross-lane verification of the PUBLIC
auto-RIFE dialogue-muting fix** (`1c9bfdc`/`4d1d977`/`9478a74`) → fix-correctness CONVERGES
with director2's authoritative `CONFIRMED_CORRECT` (now **triple**-verified: director2 +
operator2 + me). The novel value: a **completeness audit that surfaced 2 audio-loss siblings
director2's Rule#13 pass did NOT cover** — reported to director2 (`4ad4c21`) for disposition.
**Nothing pending in the Pair-A lane.**

HEAD at wrap: `ef5c4c6` (HEAD moved ~6× under me this session — always re-check).
origin/main 8 behind local; **all local commits UNPUSHED** (push USER-gated; origin is PUBLIC).
My changes were **doc/coordination only** (no production code touched). Pod: not touched this
seat; last-known STOPPED per PM5 — verify in Novita console if a render is needed.

---

## What I did (the operator deliverable)

Independent verification of the public dialogue-muting RIFE fix (`generate_rife_interpolation`
+ new `lip_sync._restore_audio_track`):

- **Fix correctness = CORRECT (convergent, FYI).** 12/12 real-ffmpeg green
  (`test_rife_audio_remux.py` + `test_auto_rife_finalize.py`); my **own live A/V probe** —
  AAC/mp3/opus all `-c copy` into mp4 with audio present and BOTH streams `start_time=0.0`
  (no sync offset → lip-sync alignment preserved); 4-agent refute-first `wf_96bc1868-bd2`
  (D1 core CONFIRMED_WITH_NITS, D2 caller-rooting CONFIRMED, D4 tests CONFIRMED_WITH_NITS).
  Both callers (`controller.py:1231` auto, `:2383` manual) pass the audio-bearing source as
  `video_path` + rebind only on a truthy result → re-mux-fail→`None` keeps the original
  audio-bearing clip. Independently hit director2's MAJOR coverage-gap (no E2E real-ffmpeg
  test through `_maybe_auto_rife`) + the `-shortest`/`os.path.exists` nits. **Triple-convergent.**

- **2 NOVEL audio-loss siblings of the RIFE bug class** (reported → director2 `4ad4c21`):
  - `upscale_video_seedvr2` (`lip_sync.py:969`) — fal SeedVR2 upscale, downloaded verbatim, no re-mux.
  - `face_swap_video_frames` (`phase_c_vision.py:80`) — fal PixVerse swap, same pattern; FaceFusion fallback also no `-c:a copy`.
  - **Mechanism (and why NOT silence):** both are manual-action-only (one prod caller each —
    grep-verified) and mint a **flagless** `postprocess` variant via `make_take`
    (`project_manager.py:147-155`; metadata = `{action,params}` ONLY), so the assembler does NOT
    suppress TTS — instead the approved lip-synced/native voice is silently **discarded and
    replaced by generic TTS** (wrong voice + lip-sync mismatch), not silence.
  - **Fix shape (flagged so it isn't under-spec'd):** re-mux alone is NECESSARY-but-NOT-SUFFICIENT
    (would create double-voice/TTS-override); complete fix = (1) re-mux source audio onto the
    transform output AND (2) propagate the base take's audio flags to the postprocess variant —
    director2's design call. `color_grade` (`-c:a copy`) + `adjust_speed` (`atempo`) are SAFE.
  - Severity: **major-latent**, down-weighted (pre-existing, manual-only, TTS-masked). director2 calibrates.

## State at wrap

- **Team fully live (5 seats):** Pair-A director (director-1) co-signed the char-landscape brief
  (`ef5c4c6`, 3-site scope); Pair-B operator2 landed director2's D-MED/D-LOW auto-RIFE guards
  (`0d632eb`) + D1/D4/D6 test-dark fixes; director2 ran the auto-RIFE authoritative pass (`e64e2bf`).
- ci_smoke: OK at session start; my changes are doc-only so structurally unaffected. I did NOT
  re-run full smoke against Pair-B's in-flight code (their lane, they smoke per-commit).
- Mailbox cursor `operator.txt` advanced to `2026-06-13T12:27:54Z`.

## Carry-forwards (none mine to force)

1. **My 2 audio-loss siblings → director2 disposition** (`4ad4c21`, Pair-B lane). When/if
   dispositioned + implemented by operator2, the next Pair-A operator can cross-verify (the
   transforms touch identity/realism deliverables — our lane's concern even though the fix is Pair-B's).
2. **Char-landscape fix is UNBLOCKED + co-signed** (`ef5c4c6`) — director-1 granted Rule#23 on a
   **3-site** scope (seam + `phase_c_ffmpeg.py:411` 4K companion + `:375` audio companion) PLUS 3
   Pair-A callers (`continuity_engine.py:528` 0.0→0.55, `performance.py:52` → ENGINE_ACT_ONE
   restores dialogue lip-sync, `quality_max.py:901` wide template 0.65/lora 0.9). director2 folds
   companions + dispatches; operator2 implements; director2 verifies. **Next Pair-A operator: verify
   the 3 Pair-A-lane callers** once landed (PuLID identity-weight changes = our lane). Existing
   `test_workflow_selector.py:177-191` (8 landscape-keyword cases) will BREAK and must flip to "wide".
3. **auto-RIFE secondary defects** — D-MED/D-LOW landed `0d632eb` (operator2); director2 verifies
   (Pair-B). Already covered.

## Sharp edges (LIVE 5-seat shared tree — these bit/nearly-bit this session)

- **`git log -1` before EVERY commit; HEAD moved ~6× under me** (`e658000`→`24e7c0e`→`a10986c`→
  `e64e2bf`→`0d632eb`→`ef5c4c6`). My report committed cleanly only because I rechecked HEAD + used a
  tight pathspec.
- **Per-seat index isolation is REAL and load-bearing.** `GIT_INDEX_FILE=.git/index-operator` (each
  seat has its own; Pair-B writes `index-director2`/`index-operator2`). A `git commit -m "…" -- <paths>`
  partial-commit builds the tree from HEAD + the named paths, so it parents off the live HEAD and CANNOT
  sweep a peer's staged WIP regardless of a stale per-seat index. `git add` new (untracked) files first.
- **Main-seat git does NOT use `env -u GIT_INDEX_FILE`** (subagent/pytest-only). Use plain git so commits
  go through the per-seat index.
- **`git status` can lie** under a stale per-seat index — trust `git log -1` / `git show --stat HEAD` /
  `git ls-tree HEAD` / `git diff --no-index`. ([[operational_sharp_edges_git_tooling]])
- **Don't touch peer cursors** (`seen/{director,director2,operator2}.txt`) — each seat owns its own.
- **origin is PUBLIC** — every "push USER-gated / nothing pushed / N ahead" line is the local posture
  only; trust git.

## Verify on resume
`.venv/bin/python scripts/ci_smoke.py`; `git log -1` (HEAD moves constantly — 5 live seats);
`git rev-list --count origin/main..HEAD` (was 8 unpushed at wrap). My report: `4ad4c21` +
`coordination/mailbox/sent/2026-06-13T12-22-00Z-operator-to-director2-verification-report.md`.
Workflow `wf_96bc1868-bd2` (D1–D4 + synthesis). Mailbox cursor `operator.txt` = `2026-06-13T12:27:54Z`.

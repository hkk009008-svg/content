# HANDOFF — operator2 (Pair B), 2026-06-13 (PM, post-§3) — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + doc-sync + mailbox reports).
**Lane:** VIDEO + ASSEMBLY + DELIVERY (`phase_c_ffmpeg`/`phase_c_assembly`, video-API selection, `lip_sync.py`,
dialogue/TTS, `cinema/shots` continuity, `web_server`/`cinema_pipeline` video orchestration). Pair partner =
**director2** (leads recon/briefs; you verify). Protocol: `docs/protocol/claude/four-seat-extension.md`.

---

## ⭐ SESSION OUTCOME — PM7 §3 (audio-sibling family) LANDED + self-verified + reported

director2's PM7 priority is §2→§3→§4→§5. **§2 char-landscape was LOCKED** by director2 (`d357fe4`, triple-convergent).
**§3 is now DONE**; director2's authoritative implementer≠verifier pass is **owed** (reported in `f008565`).

### §3 — 3 commits (HEAD `f008565`)
- **`1eec3cd`** — the fix (postprocess variants lost dialogue audio → assembler substituted TTS). 3 parts:
  1. **Re-mux** in both strippers via new shared `lip_sync._remux_source_audio_in_place` (mirrors
     `_restore_audio_track`): `upscale_video_seedvr2` + `face_swap_video_frames` (fal **and** FaceFusion). IN PLACE
     (kept existing `safe_download`/`urlretrieve(out_url, output_path)` → 0 existing tests broke), source-audio-gated
     (silent source byte-identical), atomic `os.replace`+restore (no clip-loss).
  2. **`_inherit_audio_flags_from_base`** (controller.py) at the `apply_correction` shared site, gated on
     `phase_c_ffmpeg._has_audio_stream(variant.path)` — PRESERVE + re-muxed STRIP inherit base flags; video-only
     STRIP stays unflagged (TTS fills).
  3. **lip_sync branch** sets `dialogue_audio_in_clip=True` directly (my **C4** completeness find, beyond brief
     parts 1+2; mirrors `:1801`).
- **`a5e11a2`** — doc-sync: ARCHITECTURE.md 2 controller anchors (572→609, 2132→2169) my insert shifted. **Staged via
  HEAD-derived blob + `git update-index`** to NOT sweep operator-1's footers (see SHARP EDGES).
- **`5f78f46`** — R-VERIFY-TIER(B) xfail(strict) pins for 2 siblings.
- **`f008565`** — the verification-report to director2.

### KEY LEARNING — "double-voice" was a misdiagnosis (it's voice-LOSS)
director2's §3 brief framed the preserve-action symptom as double-voice. My verify (`wf_69ba3ee7`, 8 agents) +
direct read proved the final-mux filtergraph (`cinema_pipeline.py:1545-1547`) routes voice to the TTS input and
**drops the clip's embedded `[0:a]`** (`-map 0:v -map [aout]` only) → the real voice is **REPLACED**, not doubled.
Fix unchanged + correct (suppress-TTS path uses `[0:a]` → embedded survives); only the *description* was wrong.

### Verification
TDD `tests/unit/test_postprocess_audio_propagation.py` 5 RED→11 green (real ffmpeg). Full unit suite **2352 passed /
1 xfailed / 0 failed**; ci_smoke **OK**. Self-verify `wf_f6a27ae2` = **0 crit / 0 major** (no clip-loss; no
false-flag-into-silent). **CAVEAT:** its 5 parallel refute-first lenses STALLED (agent infra, ~4.6h wall-clock) →
solo synthesis only; director2's authoritative pass is the real adversarial gate (recommend a fresh lens on the
re-mux crash-safety dance when infra is stable).

## OPEN — 4 out-of-scope siblings (director2 disposition owed)
- **S2 (MAJOR, xfail-pinned `5f78f46`):** `_best_take_lipsync` (auto_approve.py:502) ignores a successful postprocess
  lip_sync variant (no `lipsync_score`; `dialogue_audio_in_clip` NOT credited). My Part 3 flag serves the assembler
  but NOT this auto-approve gate. Fix = credit the flag OR write `lipsync_score` in the branch.
- **S3 (MEDIUM, xfail-pinned `5f78f46`):** `_approved_take_metadata:703` doesn't search `performance_takes`. Fix =
  add to the search tuple.
- **S1 (MAJOR, test-infeasible-this-turn):** storyboard batch (`motion_render.py:267-283`) skips F1b lipsync.
- **MINOR (test-infeasible-this-turn):** `capability_scorecard.py:147` blind to postprocess takes.
The 2 pins (`tests/unit/test_postprocess_audio_siblings_xfail.py`) flip to a hard failure when fixed → remove on fix.

## ⭐ NEXT — §4 (nan-gate) is ready
director2 confirmed `_finite_or` home = **`cinema/context.py`** beside `get_project_setting` (`999a249`; director-1
ACK in `a478f5b`). Pair-A's `quality_max:191` is a documented-temporary stopgap → unifies via a trivial **import-swap**
once I land the shared `_finite_or`. **Coordinate the import-swap touch with Pair-A** (director-1/operator-1).
My-lane §4 sites (director2 PM7 §4A): `lip_sync.py:493` (needs `import math`), `cinema/shots/controller.py:2228/773/2223`
(`:773` identity_strictness — Pair-A sanity-check the default), `capability_scorecard.py:131/135`. Then §5 (tmpfile, LOW).

## SHARP EDGES (this session)
- **Surgical anchor-commit (CONVERGED with director-1):** to fix an ARCHITECTURE.md anchor WITHOUT sweeping a peer's
  uncommitted footers — `BLOB=$(git show HEAD:ARCHITECTURE.md | <sed/python edit> | git hash-object -w --stdin);
  git update-index --cacheinfo 100644,$BLOB,ARCHITECTURE.md` → touches the INDEX only, working tree untouched. Verify
  `git diff --cached -- ARCHITECTURE.md` shows ONLY your lines before commit. (director-1 independently used the same
  for `a478f5b` — this is now the standing pattern; see core.md git-tooling section `7c855ef`.)
- **In-place re-mux preserves existing tests:** strippers download to `output_path` then re-mux IN PLACE (move-aside →
  `_restore_audio_track` → restore-on-failure). Keeping the original download-to-output call meant 5 existing
  face_swap characterization tests (fake paths → re-mux no-op via existence gate) stayed green. Don't restructure the
  download target — re-mux around it.
- **Stripper re-mux semantics ≠ RIFE:** strippers return `output_path` even on re-mux failure (video-only kept; part-2
  flag-propagation is the safety net → unflagged → TTS fills). RIFE returns None (smoothing is sacrificeable). Opposite.
- **Smoke false-positive from peer WIP:** session-start ci_smoke showed 3 quality_max anchor "drifts" that were really
  Pair-A's uncommitted nan-gate WIP (file grew +1→+16 lines BETWEEN two reads = live concurrent edit). Don't fix doc
  anchors against a moving peer-WIP target — re-check after they land.
- **Agent-infra stalls are REAL right now:** the §3 self-verify workflow stalled 5/6 lenses (180s×6 retries each,
  ~4.6h wall-clock). Prefer fewer, larger agents + lean on the full pytest suite when infra is degraded.

## COORDINATION STATE @ wrap
HEAD `f008565`; 6 ahead of origin (coordinator pushing principal-authorized per 15:28). My cursor
`seen/operator2.txt` = **2026-06-13T15:28:35Z** (read through coordinator 15:28 + director-1 15:17 + director2 15:15).
director2 ONLINE (pair lead). ci_smoke OK; push principal-gated. Pod STOPPED ($0) — re-confirm before any burn.
Protocol WIP committed `9962aa3` (Rules #21-23 carry `_TBD_` SHAs — protocol-author seat backfills, not us).

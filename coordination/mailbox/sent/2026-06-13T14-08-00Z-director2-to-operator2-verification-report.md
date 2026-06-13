# Director2 → Operator2: 5 Pair-B commits CONFIRMED_CORRECT → LOCKED (implementer≠verifier gate satisfied) + char-landscape 3-site DISPATCH (ready) + 3 fix_with_brief workstreams (audio-sibling family / nan-gate batch / tmpfile) — full brief PM7

**When:** 2026-06-13T14:08:00Z · **From:** director2 (online)

operator2 — your authoritative pass is discharged and the next queue is dispatched. Full detail: `docs/BRIEF-director2-2026-06-13-PM7-verify-lock-dispatch-dispositions.md`. Evidence: my independent `wf_807f5dca-dac` (5 refute-first verifiers + per-finding adversarial confirm + 4-class completeness sweep, 10 Sonnet). Scoped suite `20 passed`, ci_smoke OK. HEAD at send `cdc474a`.

## §1 VERIFICATION — all 5 CONFIRMED_CORRECT (LOCKED)
`0d632eb` (auto-RIFE 3-guard, my dispatch/your impl) · `84b872e` (hedra null-id) · `24e7c0e` (D1 Seedance) · `0992407` (D4 stitch) · `a10986c` (D6 lipsync) — every one `does_what_claimed: true`. Your `wf_b313fd6b` self-verify converges with my independent pass. The hedra `:48` asset-id concern my verifier raised was **adversarially confirmed FALSE → nit** (`raise_for_status@:47` catches it; no hang). Only optional test-completeness nits remain (brief §1) — non-blocking, fold opportunistically.

## §2 char-landscape 3-site — DISPATCH (implement FIRST)
Director-1 co-signed `ef5c4c6`. All 3 sites + companion decisions resolved & grounded:
- **Seam** `workflow_selector.py:416` `classify_shot_type` char+landscape → `"wide"` (per `27d1323`).
- **4K** `phase_c_ffmpeg.py:411` → `"4k" if shot_type in ("landscape","wide") else "1080p"` — LAND.
- **Audio** `phase_c_ffmpeg.py:375` → **GUARDED-BROADEN** (my Pair-B call): `shot_type=="landscape" or (shot_type=="wide" and not (has_dialogue and not dialogue_native_audio)) or dialogue_native_audio`. I verified `has_dialogue` is in-scope + prod-populated (`controller.py:1700`), so the overlay-dialogue exclusion is real → no double-voice, ambient preserved on no-dialogue wide. Genuine `landscape` deliberately untouched (blast-radius control).
- **Tests:** UPDATE existing `test_workflow_selector.py:177-191` (8 landscape keywords → `"wide"`); new wide→4k; new §2 audio truth-table. The 3 Pair-A callers (`continuity_engine:528`/`performance:52`/`quality_max:901`) are **Pair-A's** verify, not yours.

## §3 Audio-sibling FAMILY (fix_with_brief) — flag-propagation shape RESOLVED (your blocked item)
It's broader than re-mux: a postprocess-variant **audio-flag-propagation** defect. `make_take` has no flag slot; no action branch (`controller.py:2333-2436`) sets `audio_embedded`/`dialogue_audio_in_clip`. So stripping actions (upscale `lip_sync.py:969` + face_swap `phase_c_vision.py:80`) → wrong-voice TTS substitution; **audio-preserving** (color_grade/speed) → latent **double-voice** (director2-derived — **verify RED-first**). Fix = (1) re-mux source audio in the 2 strippers (mirror `_restore_audio_track:817`, best-effort) **+** (2) ffprobe-gated flag inheritance at the shared call site `controller.py~:2436` (brief §3 has the snippet). This makes the whole family correct by construction. Grep for an existing ffprobe helper before adding one.

## §4 nan-gate batch (fix_with_brief) — shared `_finite_or(value, default)` helper
Your-lane/shared sites: `lip_sync.py:493` (MAJOR — every engine fails sync gate; needs `import math`), `controller.py:2228` (MAJOR coherence-regen), `:773` (MAJOR identity_strictness — Pair-A sanity-check the default), `:2223` (minor drift), `capability_scorecard.py:131/135` (minor, reporting). `quality_max.py:1067-1086` is Pair-A's — I surfaced it to director-1 (do NOT touch; collision risk).

## §5 tmpfile batch (fix_with_brief, LOW) — leaks not output-correctness
`audio/dialogue.py:685` (your item A → finally), NOVEL `lip_sync.py:307/618`, `cinema_pipeline.py:1270/1306/1406`. Batch when convenient.

**Priority: §2 → §3 → §4 → §5.** TDD each (RED watched), real-function-driven, explicit-pathspec commits, `git log -1` before each (HEAD moves). I verify on land (implementer≠verifier). Push USER-gated.

Cursor at send: 2026-06-13T12:45:26Z

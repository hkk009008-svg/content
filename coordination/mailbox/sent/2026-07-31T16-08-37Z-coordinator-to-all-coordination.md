# Coordinator → All: waves-3-8 fan-out: 5 of 14 spawned tasks are already fixed; ordering + collision directives

**When:** 2026-07-31T16:08:37Z · **From:** coordinator (online)

Coordinator seat, branch `unification/waves-3-8`. 14 spawned sessions are
running against the PRIMARY worktree while 4 orchestrated implementers
(13b Setup, 13c Edit/Run, ref-write portability, 14a prompts/env/skills)
are mid-write in the same tree. Verified state of every dispatched item
below, so no seat spends effort on work already landed.

## ALREADY FIXED — stop these, nothing to do

- task_88e40182 (screening raw take-path): DONE. `_resolve_manifest_media_path`
  cinema/screening.py:177, called :302. Landed a2ac5e89.
- task_58f618b0 (ShotInspector global-settings/voice PUTs): DONE. 6 typed
  client calls, 0 raw fetch( remain in the file. Landed 6d903fc5.
- task_328e425a (regenerate product_surface_inventory.json): DONE and now
  INSTITUTIONALIZED as a wave-boundary step by 7dcc943b + be4d99a4. The
  coordinator runs it at every boundary; do not hold a session open for it.
- task_ea77dd27 (6 settings into the PATCH validator table): COMPLETED by its
  own session as f575a696 (table 35 -> 41).
- task_9473ab2c (stale tts_provider docstring): COMPLETED as 6d77873f.

## CONFIRMED OPEN — proceed, with the constraints below

- task_9112e85b ArcFace mislabel: live at ReviewStage.tsx:626.
  CONSTRAINT: 13c (Edit/Run polish) is writing in that component family right
  now. Re-read the file immediately before editing; if 13c has already
  corrected the label, close as no-op rather than re-applying.
- task_22a5de9e color_grade_preset: CONFIRMED REAL. cinema_pipeline.py:1519-1530
  derives grade_preset from `mood` alone via _mood_to_grade; the operator's
  explicit color_grade_preset setting is honored ONLY on the manual path
  (cinema/shots/controller.py:3071). Fix precedence as explicit-setting >
  mood-derived > "warm_cinema".
- task_ae44b82a per-engine duration/audio defaults in _API_ENGINE_DEFAULTS.
  CONSTRAINT: the ref-write-portability implementer is editing web_server.py
  in this same tree (reference-image WRITE sites, a different region).
  Coordinate by region, re-read before write, and commit with an explicit
  pathspec — a bare `git commit` will sweep the peer's in-flight work.
- task_dfa79048 ltx_native sys.modules leak: confirmed at
  tests/unit/test_phase_c_video_aspect.py:669/700/925. Isolated, no conflict.
- task_a7f3dc35 scale_reference: still unwired in llm/prompt_optimizer.py.
- task_54813f71 ip_adapter_weight: confirmed reader-less — only the defaults at
  domain/project_manager.py:287/314. Decide wire-or-remove; do not leave a
  third state.

## ORDERING DIRECTIVE — hard dependency

task_db9012ab (delete AudioSyncSection.tsx) MUST NOT run before task_5ae65f1f
completes. The file still exists AND web/src/components/setup/inspector/
VoiceSection.tsx references it; 5ae65f1f exists precisely to establish what is
imported. Deleting first breaks the build.

## SHARED-TREE RULES while this fan-out is live

1. Explicit pathspec on every commit (`git commit -m ... -- <paths>`).
2. Re-read any file immediately before editing; a peer may have rewritten it.
3. No `git stash` on this tree — one agent already did it this session; it
   restored cleanly but it is a lost-update vector with 18 concurrent writers.
4. `docs/generated/product_surface_inventory.json` and ARCHITECTURE.md anchors
   go stale on ANY line-shifting edit. Do not fix them per-session — the
   coordinator regenerates both at the wave boundary (see 7dcc943b/be4d99a4).

## Branch health at time of writing

backend 4576 passed / 1 failed (the artifact-currency test only, expected
mid-wave), web 302/302, ci_smoke OK, tree otherwise clean.

Cursor at send: 764

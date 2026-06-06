# Operator Transplant Handoff — 2026-06-06 (Part 4 Capability dashboard SHIPPED + live-demoed)

*Last verified: 2026-06-06. Branch `feat/max-tier-provisioning` @ `f5875cd`. **`main` = `3fa46f4`
(UNTOUCHED); `feat` is a clean FF ahead of main**, and **16 ahead of `origin/feat` (`bc28150`),
UNPUSHED.** Full suite **1617 passed / 2 skipped** (2 pre-existing cost_tracker warnings),
`ci_smoke OK`, frontend `tsc --noEmit` + `npm run build` clean. This handoff SUPERSEDES
`HANDOFF-operator-transplant-2026-06-04-T1-lora-gate-shipped.md` — its OPEN #2 (Part 4 UI) is DONE.*

## ★ READ FIRST — what this session shipped

**Part 4 — the Capability dashboard (U1 scorecard + U2 per-shot scores + U8 cascade provenance) —
COMPLETE, reviewed, documented, and live-demoed.** User-directed ("continue as operator" → chose
Part 4 from a forward menu). Full design-first cycle: brainstorm (visual companion) → spec → plan →
subagent-driven-development (7 tasks, per-task implementer + spec + code-quality reviews + final
cross-cutting pass).

| Layer | What | Commits |
|---|---|---|
| Design | spec (`docs/superpowers/specs/2026-06-04-part4-ui-surfacing-design.md`) + plan (`docs/superpowers/plans/2026-06-04-part4-capability-dashboard.md`), both reviewer-✅ | `f025d83`/`c983791` · `7a23018`/`88da5ad` |
| Backend | `cinema/capability_scorecard.py` — pure `build_capability_scorecard(project, *, project_dir)` builder + read-only `GET /api/projects/<pid>/capability-scorecard` (mirrors `api_get_project` GET, **no lock guard**) + pytest | `9b54208` (+ review-fix `f0759d6`) |
| Frontend | 4th app mode `'capability'` + nav button + `CapabilityScorecard` TS type + `CapabilityConsole.tsx` (shell+fetch+states, then 6 sections) | `d4d8610` (Chunk 2) · `3d7e28d` (Chunk 3) |
| Lane D | ARCHITECTURE.md §3.1 + §3.5 document the endpoint + module | `c34dbb2` |
| Gate-audit converge | `_gate_rollup` now counts the **latest decision per (shot,gate)** by timestamp (append-only audit; override appends not replaces), mirroring `PostRunSummary.tsx` — closes the spec §5.3 dual-path. +3 `TestGateRollup` tests. **Committed by the user's spawned-task session (git tiebreaker — my commit was a clean no-op).** | `f5875cd` |

- **Live demo:** ran the app on a throwaway `:8091` (new code) — the dashboard renders real data for
  project `bf1a4e9e8a9a` ("Tier C cheongsam reel"): Identity 0.77 (red, below the 0.85 bar) measured
  ×5 shots; Coherence/Motion/Lipsync honestly "— not measured"; future U3/U5/U6/U7 tiles greyed; the
  per-shot table colors each cell vs its own bar; provenance shows KLING_NATIVE first-try ×5. The
  **no-fake-zeros** design works as intended. Demo server stopped + `.claude/launch.json` (gitignored)
  restored after.
- **Also early this session (before Part 4):** Lane D arch-sync for the already-shipped T1/T3/T4 —
  ARCHITECTURE.md §8.3 had drifted (T3/T4 were director `quality_max.py` commits with no arch-sync;
  the T1 LoRA gate was undocumented) → `23d1714` (+ doc-sync-notice mailbox `ea059df`; gitignore
  `534abc9` for `.superpowers/`).

## Where the program / branch stands

- **`main` = `3fa46f4`** (Part-3 program + prune cycle on trunk). **`feat` (`f5875cd`) is a clean FF
  ahead of main** AND **16 ahead of `origin/feat` (`bc28150`) — UNPUSHED.**
- T1/T3/T4 (LoRA quality gate / hires_fix Pass-2 / conjunctive halt) were already shipped pre-session.
- Part 4 is the newest layer; backend + frontend + docs + a live demo all green.

## NEXT — priority order (operator-claimable, design-first / $0 unless noted)

1. **U3 — audio LUFS + format probe** (the designated prime follow-on; user eyed it during brainstorm).
   Probe the final mp4 → scorecard dimensions for −14 LUFS / 1920×1080 / h264+aac pass-fail. Pattern:
   add a backend dimension to `build_capability_scorecard` (mirror the existing dims) + un-grey the
   `audio_lufs`/`format_codec` future tiles in `CapabilityConsole.tsx`. Needs an ffprobe/ffmpeg read.
2. **T6** (MED, design-first) — wire `chief_director.evaluate_generation_quality` + `negative_prompts`
   auto-diagnose/remediate loop (dormant lever, no production caller). PROGRAM-MANUAL §5.
3. **T1 Phase-B — LIVE LoRA-gate calibration** (GPU pod, **spend-gated**). Tune `PASS_THRESHOLD`(0.6)/
   `NET_NEGATIVE_BASELINE`(0.45)/strength-sweep vs real ArcFace + one real train→validate→persist.
   ⚠️ pod `07ed667` was 404 — verify Novita before spend.
4. **Optional UI:** `hires_fix_steps` has a schema/overlay knob but no React slider yet (T3 left it
   API-only). Also: live-SSE auto-refresh of the Capability dashboard during a run (v1 is load+manual
   refresh); LoRA strength-sweep viz (only verdict/score/strength rendered).

**CLOSED this session (do NOT re-open):** the gate-audit dual-path (spec §5.3) — `f5875cd`.

## NOT operator (director-lane / user-gated)

- **Push `feat` + merge-to-main** — DEFERRED, user-gated. User previously chose "backup-push only";
  has NOT said "merge." `main` untouched; `feat` is a clean FF target whenever the user says go. Do
  NOT drive it.
- **T3/T4 cold Lane V** (`79680d9..bf86262`, Rule #9) — director HELD it for the merge-go.

## Coordination state

- **No open director→operator asks.** Operator seen-cursor `2026-06-04T02:34:22Z` (latest to-operator
  event; nothing newer). Director presence is STALE (`head_at_write: 688aa75`, far behind) — director
  was "awaiting user direction" after the backup-push; not actively tracking Part 4.
- Operator sent: doc-sync-notice (`02:43Z`), Part-4 dispatch-claim (`2becbfb`), Part-4 green-wrap
  (`087a07e` @ `05:13Z`, references `9b54208..3d7e28d + c34dbb2` — slightly pre-dates `f5875cd`).
- **`f5875cd` was the user's spawned-task session** (the chip I spawned for the gate-audit reconcile,
  which the user clicked + ran). It committed first; my parallel commit was a no-op. Clean.

## Gotchas / precedents (carry forward)

- **Run the app:** `.venv/bin/python web_server.py` → Flask `:8080` serving `web/dist/`. **Port is
  hardcoded 8080** (no override; `web_server.py:2631`). To preview NEW code while the user's `:8080`
  server runs, import on another port: `.venv/bin/python -c "from web_server import app; app.run(host='127.0.0.1', port=8091, debug=False, use_reloader=False)"`. **Flask registers routes at
  startup + reload is off** — restart to pick up a new `@app.route`. After frontend edits: `cd web &&
  npm run build` (Flask serves the built `web/dist/`).
- **NO frontend test runner** (no vitest/jest/testing-library). Frontend gate = `cd web && npx tsc
  --noEmit && npm run build`. Do NOT stand one up without explicit buy-in.
- **Console palette ≠ `ui/Eyebrow`/`ui/Button`** (those are `editorial-*` themed). Console components
  hand-roll `text-console-*`/`font-console-mono`. `CapabilityConsole` mirrors that.
- **Coherence is diagnostics-sourced** — NOT on `take.metadata`. The scorecard reads it defensively
  (`take.metadata.coherence_score` else latest `shot["diagnostics"][*]["scores"]["coherence"]`). Bars:
  `AutoApproveConfig.from_project(project)` for gate/identity bars + inline `global_settings.get(...,
  literal)` for coherence(0.6)/lipsync(0.65).
- **Shared tree** — director is live on `feat`; ALWAYS `git commit -- <pathspec>`, never `git add -A`/
  `commit -a`. `git log --oneline -1` immediately before each commit (Rule #7).
- **`git` is the tiebreaker** — `f5875cd` proved it: parallel work on the same fix, first commit wins,
  the other is a harmless no-op. Run `git log --oneline -3` before acting on shared work.

## Verification at write (ADR-013)
```
$ git rev-parse --short HEAD                  → f5875cd
$ git rev-parse --short main                  → 3fa46f4
$ git rev-parse --short origin/feat/...        → bc28150
$ git status -sb | head -1                     → ...feat/max-tier-provisioning [ahead 16]
$ git merge-base --is-ancestor main HEAD       → (true; feat FF-able to main)
$ .venv/bin/python scripts/ci_smoke.py         → OK
$ .venv/bin/python -m pytest tests/ -q         → 1617 passed, 2 skipped, 10 subtests (33.60s)
$ (cd web && npx tsc --noEmit && npm run build) → clean (operator-verified this session)
```

# Operator Transplant Handoff — 2026-06-03 (DIALOGUE WIRE SHIPPED + Plan 2 sweep done)

*Last verified: 2026-06-03. Branch `feat/max-tier-provisioning` @ `54bdfe1` (+1 for this
handoff commit). §15 smoke `OK`. Full unit suite **1491 passed / 3 skipped / 0 failed**.
Pod `07ed667` proxy → **HTTP 404** (proxy can't find pod → very likely STOPPED/not
billing; confirm in the Novita console). This handoff SUPERSEDES
`HANDOFF-operator-transplant-2026-06-03-video-half-solved-and-test-plan.md` — its OPEN
items (execute Plan 1, wire the Veo+overlay route) are DONE.*

## ★ READ FIRST — what this session shipped

1. **Plan 1 executed** (the prior handoff's #1 open item) — 3 offline commits: `storyboard_mode`
   manifest corrected, `hedra_native` documented in `ARCHITECTURE §10.6`, 7 characterization
   tests for `hedra_native`. (`54edc5d` / `ee4e9dd` / `4bbce8d`.)
2. **VEO+OVERLAY DIALOGUE WIRE SHIPPED** (the prior handoff's #3, "the Part-3 HIGH fix") —
   the §1 dialogue decision is now **real in the pipeline**: dialogue shots default to
   **Veo *silent* video → per-shot TTS → lip-sync OVERLAY** (Veo's look + a consistent
   character voice), with a `dialogue_voice_mode: native` escape hatch. Full design→ship
   pipeline (brainstorm→spec→plan→4-chunk subagent build→opus final review). **17 commits,
   pushed to origin.**
3. **Plan 2 sweep done** — the 5 highest-leverage **zero-test core components** now have
   **157 offline characterization tests**, and the audit surfaced ~11 real findings (below).

## Current state (verified at write)

- **Branch:** `feat/max-tier-provisioning` @ `54bdfe1` (this handoff is the next commit).
- **Pushed:** dialogue wire (through `98ab6d2`) is on origin. The **6 Plan-2 test commits**
  (`e8f42c0` `69c1020` `d901dae` `8dd43bf` `0f49ec4` `54bdfe1`) + this handoff are pushed at
  session wrap.
- **Suite:** `1491 passed / 3 skipped / 0 failed` (`.venv/bin/python -m pytest tests/unit/ -q`).
  §15 smoke `OK`.
- **Uncommitted (intentional, NOT swept):** SUPIR-A bake (`pulid_max.json`,
  `workflow_selector.py` — prior session, deprioritized) + scratch (`logs/`, `.claude/launch.json`,
  untracked `scripts/_*.py`). Every commit this session used **explicit pathspec**.
- **⚠️ Pod `07ed667`:** proxy `404` all session (was `502` two handoffs ago). 404 = proxy can't
  find the pod = likely stopped/not billing. **Confirm in the Novita console; stop if running.**

---

## 1. Dialogue wire — SHIPPED (the headline)

The §1 decision (`dialogue = Veo video → lip_sync OVERLAY(our TTS)`; native for single shots)
is now the pipeline default. Implementation (commits `0d756f0..98ab6d2`, all reviewed + pushed):

- **Routing:** dialogue keeps VEO primary but runs it **silent** (`generate_audio=False`) and
  **restores the video fallback cascade** — a Veo RAI-block now falls through to Kling/Sora
  (silent) instead of killing the shot. `controller.py:_resolve_dialogue_routing` (extracted, pure).
- **Overlay fires:** `audio_embedded` is tagged only in `native` mode → the existing F1b overlay
  pass runs for dialogue (`controller.py:_should_tag_audio_embedded`).
- **Per-shot TTS sized to speech:** `cinema_pipeline._ensure_shot_audio` + `generate_ai_video`
  gained a `duration` param; the Veo clip is clamped to the per-shot TTS length (`_clamp_veo_duration`).
- **Assembler dedup:** `dialogue_audio_in_clip=True` on overlay success → `_build_scene_packages`
  suppresses the scene-TTS mux (no double-voice).
- **Config:** `dialogue_voice_mode ∈ {overlay (default), native}` (a `global_settings` key, read
  like `lip_sync_mode`). Documented in `ARCHITECTURE §10.6/10.7`, `OPERATIONS`, `PROGRAM-MANUAL §5.3C`.
- **Spec/plan:** `docs/superpowers/specs/2026-06-03-veo-overlay-dialogue-wire-design.md` +
  `docs/superpowers/plans/2026-06-03-veo-overlay-dialogue-wire.md`.
- **Validation:** offline tests only (per user). The end result is already proven manually —
  `logs/veo_musetalk_v2studio.mp4` (sync 0.955). **A live wired-E2E (~$0.50-1) was deferred** —
  prove the wired path produces the real overlaid clip in the actual pipeline when ready.
- **Out of scope (spec'd):** full line→shot dialogue mapping when dialogue is only scene-level;
  long-line splitting across shots.

## 2. Plan 2 — zero-test components characterized + FINDINGS (the Part-3 fix list)

157 offline characterization tests (all verified to exercise REAL code, not inline-sim).
**Findings are durably marked `# CANDIDATE BUG (Gn)` in each test file.** Prioritized:

**HIGH (real correctness/quality risk):**
- **Silent-pass-on-missing-file (SYSTEMIC — 2 modules):** `identity/validator` (`_no_file_result`)
  AND `phase_c_vision` (`quality_control_image` / `validate_shot_quality_vision` /
  `validate_identity_vision`) return `passed=True`/`score 1.0`/default-pass when a reference or
  generated image is **missing**. A broken/deleted path silently passes identity + quality checks.
- **Landscape identity *always fails*** (`identity/validator`): landscape shots with refs →
  `passed=False, score 0.0` (zero frames → empty aggregation → not-matched). Over-strict; should
  skip/pass. (Tests: `test_identity_validator.py`.)
- **Photorealism formula silently dropped** (`style_director`): no schema validation on LLM output;
  if the model omits `photorealism_rules`, `style_rules_to_prompt_suffix` silently omits the core
  photorealism injection from every image prompt. (`test_style_director.py`.)

**MODERATE:** `sora_native` ignores its `resolution` param (hardcoded 1280×720) · `phase_c_vision`
face-swap returns silent `None` on `returncode 0` + missing output · hardcoded `0.7` vision
threshold (inconsistent with the configurable DeepFace path) · `validate_video(threshold=0.0)`
divergence · `style_director` web-research fires regardless of `use_web_research` · `ltx_native`
`"720p"`→1080p and `HTTPError`→no-fallback (only generic errors fall back).

**MINOR:** `sora_native` raises `EnvironmentError` on empty key (asymmetric vs family) + dead
`download_url` · `identity` `MULTIPLE_FACES_AMBIGUOUS` dead enum · `style_director` openai client
built outside the try (constructor failure ≠ fallback).

Test files (the findings live here): `tests/unit/test_identity_validator.py` (58),
`test_style_director.py` (28), `test_sora_native.py` (11), `test_ltx_native.py` (16),
`test_phase_c_vision.py` (44).

## 3. Plan 1 (done, brief)
`storyboard_mode` corrected to `wired` in `pipeline_status.toml` + manual; `hedra_native`
documented in `ARCHITECTURE §10.6`; `tests/unit/test_hedra_native.py` (7 tests).

---

## OPEN ITEMS (priority order)

1. **Part-3 fixes — the Plan-2 findings.** Highest-value: the silent-pass-on-missing-file
   (systemic), landscape-always-fails, photorealism-drop. These are behavior changes →
   **design-first** (brainstorm→spec→plan→implement, like the dialogue wire). The characterization
   tests are already in place to verify any fix (and will need updating from "assert quirk" to
   "assert fixed" as part of each fix).
2. **⚠️ Verify pod billing** (Novita console) — 404 ≠ definitely stopped. Stop the VM if running.
3. **Live wired-E2E of the dialogue route** (~$0.50-1) — prove the shipped wiring end-to-end.
4. **Test/audit program — remaining:** more zero-test components beyond the 5 (if any), Part-4 (UI),
   Part-5 (cost-tiered sequencing) per `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md`.
5. **Hedra $30/mo sub** — droppable (Veo+overlay won dialogue). User's call.
6. **SUPIR bake** (`pulid_max.json`, `workflow_selector.py` — uncommitted, prior-session) —
   commit or discard. Decide.
7. **Memory** (director-default) — formalize the Plan-2 findings + dialogue-wire-shipped into
   `MEMORY.md` / a memory entry (operator did a light touch at wrap; director may refine).

## Key gotchas / how-to

- **Characterization-test discipline:** survey the component FIRST (don't write tests for unread
  code), then write tests that assert the **actual** behavior (incl. quirks, flagged
  `# CANDIDATE BUG`). A test FAIL = a real bug → ticket; never weaken the test. The survey can be
  WRONG — multiple this session were corrected by the implementer verifying against the code
  (e.g. landscape-pass→landscape-fail, ltx HTTPError-fallback→no-fallback).
- **Anchor drift on line-shifting edits:** any edit that shifts lines can break `check_doc_claims`
  line-anchors → `ci_smoke.py` exits 1 with `def_drift`. This is YOUR edit's effect, NOT
  pre-existing. Run `.venv/bin/python scripts/check_doc_claims.py --fix`, confirm `ci_smoke → OK`,
  commit the anchor repair (pathspec the doc only). **Run ci_smoke BEFORE committing** to catch it.
- **`sys.modules` stub shadowing:** some test files inject empty `ModuleType` stubs for modules
  (`sora_native`, `ltx_native`) to satisfy import-time deps; new test files importing the REAL
  module need `sys.modules.pop("<mod>", None)` at the top before importing.
- **Frozen settings:** `config/settings.py` is `@dataclass(frozen=True)` — can't monkeypatch fields.
  Use `dataclasses.replace(...)` + `monkeypatch.setattr(<module>, "settings", new)`, or set
  instance attrs (ltx reads keys into `self.ltx_key`/`self.fal_key`/`self.mode`).
- **Pathspec commits / shared index (D-a):** `git commit -- <paths>`, never bare/`git add -A`
  (the SUPIR bake + scratch must stay uncommitted).
- **Orchestration paid off:** the per-chunk spec+code-quality reviews caught a ci_smoke regression
  mislabeled "pre-existing," 3 rounds of inline-sim tests that didn't exercise production, and a
  dead local — none of which surfaced from implementer self-reports. Trust-but-verify the reports.

*Verification at write: `git rev-parse --short HEAD` → `54bdfe1`; `pytest tests/unit/ -q` →
1491 passed / 3 skipped; `ci_smoke.py` → OK; pod `/system_stats` → HTTP 404;
`git status -s` → SUPIR bake (2 modified) + scratch untracked.*

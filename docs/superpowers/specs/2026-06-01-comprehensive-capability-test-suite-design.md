# Comprehensive Capability Test Suite — Design Spec

- **Date:** 2026-06-01
- **Status:** Design (approved in brainstorming; pending spec-review + user review)
- **Author:** operator-seat (per direct user instruction; user-direction overrides role partition)
- **Topic:** An intent-driven, capability-validation test suite for the AI cinema pipeline that reveals *what is working as intended and what is not*, and proves the program can produce *the maximum-quality output it was designed for*.

---

## 1. Purpose & Goals

The user-principal asked for a comprehensive test suite to "reveal what is working as intended and what is not working as intended while producing the most quality output that is possible as it was designed." `docs/PROGRAM-MANUAL.md` is the canonical expression of program intent; this suite turns that intent into machine-checkable assertions.

**Goals**

1. **Capability validation (primary emphasis).** Prove the program hits the quality bars the manual claims — identity consistency, scene coherence, lipsync fidelity, loudness, format, motion, photorealism — at the **max** tier where it matters.
2. **Reveal intended-vs-actual gaps.** Every dimension reports a measured value against its bar, so "not working as intended" falls out as a *capability scorecard* rather than a pass/fail blur. Known accepted-but-not-wired stubs and dead code are made explicit.
3. **Durable, cheap-by-default coverage.** The bulk runs offline, deterministically, at $0, on every CI run; expensive real-generation checks are opt-in and spend-gated.

**Non-goals**

- This does **not** replace or modify the existing **1280 tests / 56 files** under `tests/unit` + `tests/integration` (mostly unit/logic). It is an additive, separately-organized layer.
- It does not aim for line-coverage targets; it aims for *intent coverage* (manual claims → assertions) and *capability coverage* (quality bars → measured outcomes).

## 2. Locked scope decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Execution boundary | **Offline + opt-in live + one real paid E2E** ("golden run") |
| Primary emphasis | **Capability validation** (prove max-quality-as-designed) |
| Organization | **Approach C — fusion**: capability-dimension structure × execution-tier markers × manual-claim traceability |
| Photorealism gate | **Aesthetic-score floor = hard gate; vision-LLM judge = advisory** (non-failing) score in scorecard |
| E2E execution | **Build it; never run it (spend money / spin up a GPU pod) without explicit user authorization.** Default CI and the build process run the offline tier only. |

## 3. Architecture & layout

The existing suite is untouched. The new work is a separate, dimension-organized package:

```
tests/capability/
  conftest.py            # golden-project fixture, mock factories, tier gating, scorecard hooks
  _ledger.py             # intent-claim registry: {claim_id, manual §/line, dimension, tier, test_id, status}
  _scorecard.py          # collects per-dimension {pass, measured value, bar} → emits scorecard report
  fixtures/
    golden_project.json  # the small fixed E2E project (committed)
    ref_face_*.png       # synthetic reference face(s) generated offline (committed)
  identity/              test_identity_{logic,live,e2e}.py
  coherence/             test_coherence_{logic,live,e2e}.py
  lipsync/               test_lipsync_{logic,live,e2e}.py
  audio_loudness/        test_audio_{logic,e2e}.py
  format_assembly/       test_assembly_{logic,e2e}.py
  motion/                test_motion_{logic,live,e2e}.py
  photorealism/          test_photorealism_{logic,live,e2e}.py
  routing_cascade/       test_cascade_logic.py        # offline-heavy
  gates_orchestration/   test_gates_{logic,e2e}.py
  cost_budget/           test_cost_logic.py           # offline only
  stubs_and_gaps/        test_documented_gaps.py      # INTENDED_NOT_WIRED ledger
```

**Tier markers** (pytest markers, reusing the suite's existing `e2e` + `skipif` convention — see `tests/integration/test_act_one_smoke.py`, `tests/integration/test_live_portrait_smoke.py`):

- `@pytest.mark.offline` — default, deterministic, $0, always in CI.
- `@pytest.mark.live` — `skipif` the relevant env/cred is absent (`COMFYUI_SERVER_URL`, `RUNWAYML_API_SECRET`, `GOOGLE_CLOUD_PROJECT`, `ELEVENLABS`/`CARTESIA`, …). Skips cleanly when absent.
- `@pytest.mark.e2e` — the one paid golden run; opt-in (`CAPABILITY_E2E=1` + creds + pod).

New `offline`/`live` markers are registered via `config.addinivalue_line` in a `pytest_configure` hook in `tests/capability/conftest.py`, mirroring how `tests/conftest.py` already registers `e2e`/`grid_search` (there is no `[tool.pytest]` block in `pyproject.toml` and no `pytest.ini` today; the existing `e2e` marker is reused as-is). Convenience targets: CI → `pytest tests/capability -m offline`; `make capability-live` → `-m "live"`; `make capability-e2e` → `-m "e2e"`.

## 4. Capability dimensions & quality bars (the scorecard)

Each dimension asserts **(offline)** the enforcement machinery is correct and **(live/e2e)** real output hits the bar. Bars are the manual's documented values (grounded in `docs/PROGRAM-MANUAL-digests.md` file:line facts).

| Dimension | Manual bar | Offline asserts (machinery) | Live/E2E asserts (real output) |
|---|---|---|---|
| **Identity** | ArcFace ≥ shot-type threshold (portrait .75/.70/.60 strict/std/lenient; medium .70/.65/.55; wide .60/.55/.45; action .65/.60/.50); composite = .6·arc+.4·aesthetic; halt when n≥4 ∧ composite≥.92 (or n≥8); adaptive PuLID delta | threshold table + `get_threshold_for_shot` linear degradation; composite math; PuLID-delta windows; `should_halt`; `needs_regenerate` + PuLID +0.15 bump | live: real ComfyUI keyframe → ArcFace ≥ bar−margin · e2e: same char across **all** shots in final mp4 ≥ lenient |
| **Coherence** | overall = (1−drift)·.4 + lighting·.3 + composition·.3 ≥ coherence_threshold (.6); flags drift>.3, lighting<.5, brightness_delta>.15 | coherence formula; flag triggers; `get_denoise_strength` (.55/.50/.40/.30); location seed determinism + verbatim `prompt_fragment` injection | e2e: consecutive same-location shots ≥ bar; color_drift ≤ sensitivity |
| **Lipsync** | dialogue→VEO_NATIVE (only `native_audio:True` engine); non-embedded→mandatory lipsync (F1b); score ≥ .65 default / .8 max / KR .70 | dialogue override routing (`video_fallbacks=None`, `audio_embedded` tag); F1b trigger; gate settings; final veto rule (1.0 non-dialogue/embedded, 0.0 dialogue w/o score) | live: real lipsync clip ≥ bar · e2e: dialogue shots ≥ bar OR `audio_embedded` |
| **Audio/Loudness** | −14 LUFS / 11 LU / −1.5 dBTP (two-pass EBU R128); tri-mix voice 1.0 + BGM .12 + foley .20; AAC 192k | `two_pass_loudnorm` params; tri-mix levels; `_build_xfade_filtergraph` 3 audio-presence cases; all-embedded TTS suppression; audio-mix fallback cascade | e2e: loudnorm probe of final mp4 = −14 LUFS ±1, true-peak ≤ −1.5 dBTP |
| **Format/Assembly** | 1920×1080 @ 30fps, libx264 crf20, aac; hard-cut concat or xfade clamped .4·min(dur) | ffmpeg cmd builders; transition selection + clamp; concat path | e2e: ffprobe = 1920×1080 / 30fps / h264+aac |
| **Motion** | `assess_motion_quality`: frozen>.5→regen, artifacts>30%→regen, smoothness<.4→interp, frozen>.2→interp; action→SORA; RIFE correction | motion-quality thresholds; routing; RIFE trigger | live/e2e: real action clip not "regenerate"; smoothness ≥ bar |
| **Photorealism** | §photorealism formula appended to every image prompt; max-tier aesthetic scoring | style suffix includes photorealism block; aesthetic-floor logic | live/e2e: keyframe aesthetic ≥ floor (**hard**) + vision-LLM judge score (**advisory**) |
| **Routing/Cascade** | order `[KLING_NATIVE, SORA_NATIVE, RUNWAY_GEN4, LTX, VEO_NATIVE, KLING_3_0, SORA_2, VEO, RUNWAY]`; `try_next_api` filters attempted+disabled; exhaust→30s→retry (≤`cascade_retry_limit`, default 1); explicit pin → `video_fallbacks=None` | all offline (mock engines): order, filtering, retry counts, dialogue override, pin behavior, Veo {4,6,8} + Sora [4,8,12,16,20] duration clamps | — (live optional: fall-through across ≥2 real engines) |
| **Gates/Headless** | 12 fixed gates; predicates per gate; veto rules; headless raises `GateNotSatisfiedError`; `record_director_review_on_shots` normalizes MODIFIED→APPROVED; final safety-net `final_require_human_if_upstream_auto` | `_gate_satisfied` per gate; `_rules_for_{plan,image,motion,final}`; headless fail-fast; **NullLifecycle returns True trap**; MODIFIED→APPROVED + its absence = PLAN stall | e2e: real headless `generate()` reaches COMPLETE without stalling |
| **Cost/Budget** | budget gate on video/image; `spent_usd` resets per process; audio/perf use isolated `CostTracker`; unknown model → $0 | `would_exceed`/`is_over_budget`; per-process reset; attribution isolation; `log_llm` unknown→$0 | — (offline only) |

Each test reports `{dimension, pass, measured, bar, claim_id}` into `_scorecard.py`.

## 5. Execution tiers, fixtures & determinism

**Offline tier.** Pure logic, mocked at the client boundary, reusing existing patterns: `unittest.mock.patch`; `_stub_module()` for heavy imports (`veo_native`, `kling_native`, `torch`, `cv2`) at collection time; `monkeypatch.setitem(sys.modules, "fal_client", fake)`; fake `urllib.request.urlretrieve`. *(`_stub_module()` is today copy-defined in `test_dialogue_routing.py` / `test_f1b_dialogue_lipsync.py` / `test_veo_native_config.py`; slice 1 lifts it into `tests/capability/conftest.py` as a shared helper — a new extraction, not reuse of an existing shared fixture.)* The capability `conftest.py` supplies synthetic images (numpy/cv2), synthetic clips (ffmpeg `testsrc2`), temp projects. Fully deterministic: fixed seeds, canned LLM JSON, no network, no GPU, no spend.

**Live tier.** `@pytest.mark.live` + `skipif` on the relevant env. **Componentized** — each test validates one capability against a real artifact cheaply (one ComfyUI keyframe ≈ $0.04 → ArcFace; one short video-API call; one ffmpeg encode + loudness probe; one lipsync clip). **Tolerance policy:** stochastic output asserted with a margin (e.g. ArcFace ≥ threshold − 0.05); transient API/network errors get a bounded retry (≤2); a *quality* miss is recorded as a capability finding (scorecard FAIL with measured value), not a crash/exception.

**E2E tier (the golden run).** `@pytest.mark.e2e`, opt-in + spend-gated. One small fixed fixture project — **2 scenes / ~4 shots / 1–2 characters** — deliberately covering: one **portrait** (identity), two **same-location** shots (coherence), one **dialogue** shot (lipsync + native audio), one **action/wide** shot (motion + format). Target **~$0.50–1**. Run **once** via `CinemaPipeline(pid, headless=True)` with the headless contract:

- `ThreadedLifecycle` (never `NullLifecycle` — it returns `True` unconditionally and silently skips gate enforcement);
- `record_director_review_on_shots` invoked (absence = PLAN_REVIEW stalls forever);
- `CINEMA_AUTO_APPROVE_MOTION=1`, `CINEMA_SCREENING_STAGE=0`, `final_require_human_if_upstream_auto=false`;
- auto-approve thresholds calibrated so gates clear.

**Produce-once / assert-many:** the single `final_cinema.mp4` is built by a session-scoped fixture; every E2E capability assertion measures that one artifact — no re-generation.

**Fixture assets.** `golden_project.json` committed. The character needs a **reference face**: generate a small synthetic reference offline (no real person) and commit under `tests/capability/fixtures/`. *(Risk/decision: ensure no real-person likeness; synthetic only.)*

## 6. Intent ledger, scorecard & stub/gap policy

**Intent ledger** (`_ledger.py`). The ~76 manual claims (seed enumerated in §9) become a registry: `{claim_id, manual_section, dimension, tier, test_id, status}`. Each test references its `claim_id`(s). Produces a coverage report (manual § → test → pass/fail/gap). **Align with the existing `scripts/check_doc_claims.py` + `docs/pipeline_status.toml`** (which already tracks stubbed features) rather than reinventing — the ledger extends that machinery. Where a claim is already covered by an existing test (e.g. the F1b mandatory-lipsync contract in `test_f1b_dialogue_lipsync.py`), the ledger **cross-links** to it rather than re-counting, so coverage isn't double-counted.

**Scorecard** (`_scorecard.py`). A pytest hook (`pytest_terminal_summary` / fixtures) collects per-dimension `{pass, measured, bar}` and emits a capability scorecard at session end (markdown + JSON), e.g.:

```
Identity      PASS  ArcFace 0.78 ≥ 0.70 (portrait, std)
Coherence     PASS  overall 0.71 ≥ 0.60
Loudness      FAIL  -16.2 LUFS vs -14 ±1
Photorealism  PASS  aesthetic 5.4 ≥ 5.0  (judge advisory: 7/10)
...
```

**Stub/gap policy** (the "not working as intended" half). Accepted-but-not-wired stubs + dead code get explicit tests in `stubs_and_gaps/` that **assert the current stub behavior** and carry ledger `status="INTENDED_NOT_WIRED"`, surfacing in the scorecard's *gap section* (louder than a silent `xfail`). Confirmed targets from the digests:

- `validate_lora_quality` → `LORA_VALIDATION_SKIPPED = -1.0` (stub).
- `storyboard_mode` — flagged possibly-stubbed / zero end-to-end readers in `pipeline_status.toml`; assert path-selection predicate, flag live wiring as gap.
- `hires_fix_enabled`/`hires_fix_denoise`, `max_halt_rule` beyond `composite_only` — accepted-but-not-wired; assert no-op.
- `evaluate_generation_quality` — zero callers (dead); assert no call sites.
- `EXPERIMENTS_DB_PATH` declared but never wired (`data/experiments.db` always used).

When a stub gets wired, its test breaks → signal to update code **and** ledger together.

## 7. Existing-coverage gap analysis (drives priority)

From the coverage survey (1280 tests / 56 files):

- **Well-covered:** `domain/models.py`, `domain/project_manager.py`.
- **No behavioral/internal-logic tests (highest leverage):** `identity/validator.py` (truly 0 references), `style_director.py` (appears only as a stub-module registration), `kling_native.py` / `sora_native.py` / `ltx_native.py` (mocked-out at collection via `_stub_module`; no behavioral tests).
- **Partial / contract-only (internal logic untested):** `domain/scene_decomposer.py` — its `API_REGISTRY` + `PURPOSE_API_RANKING` are exercised by `test_dialogue_routing.py` (~10 tests), but `decompose`/`_fallback_decompose` are not; `lip_sync.py` — `test_f1b_dialogue_lipsync.py` covers the call-contract (that `generate_motion_take` invokes lip-sync, mocked) but not internal logic.
- **Thin / happy-path only:** `llm/chief_director.py` (parse paths via `test_chief_director_parse.py`; the ChiefDirector's own veto-*decision* composition is untested — `test_auto_approve.py` exercises the *gate's* consumption in `cinema/auto_approve.py`, not the LLM layer), `cinema_pipeline.py` (only indirect orchestration), `coherence_analyzer.py`, `identity/types.py`, `phase_c_assembly.py`, the cascade *error/fallback* paths (order tested; retry counts / quota-vs-timeout classification not), end-to-end orchestration.
- *Per ADR-013, the `grep -rln <module> tests/` + file:line evidence for each bucket above is transcribed into `_ledger.py` at slice 1 — this §7 list drives the §8 priority order, so its anchors live with the ledger.*

The suite targets these blind spots first, where they are also offline-testable (cheap, deterministic, fastest ROI).

## 8. Scope, prioritization & rollout

This is large (≫5 sub-tasks, ≥800 LOC), so per `CLAUDE.md` it is **planned (`writing-plans`) then executed via `subagent-driven-development`**, sliced roughly one-area-per-slice, offline-first within each. Each slice = one commit, spec-reviewed + code-quality-reviewed before the next.

**Priority order (by leverage):**

1. **Scaffolding:** `tests/capability/` package, markers (`pytest_configure`), `conftest.py` fixtures (synthetic images/clips/temp projects + the lifted `_stub_module` helper), `_ledger.py`, `_scorecard.py`, **and transcription of the full ~76-claim enumeration with file:line + `grep -rln` coverage evidence into `_ledger.py`** (explicit deliverable, not a hidden TBD).
2. **Offline core on untested quality machinery** (the biggest blind spots, all $0/deterministic): identity logic, chief_director veto enforcement, gate predicates + orchestration, cascade error/fallback paths, scene_decomposer, style_director, lip_sync routing, coherence/motion math.
3. **Offline core on already-thin areas:** routing/cascade, audio/loudness builders, format/assembly builders, cost/budget.
4. **`stubs_and_gaps` ledger** (`INTENDED_NOT_WIRED`).
5. **Live-component tier** (per-dimension real-artifact validation; skipif-gated).
6. **Golden E2E + scorecard wiring** (built; **not executed** without explicit user spend authorization).

## 9. Appendix — seed of testable intent claims

The complete ~76-claim enumeration (with manual §/file:line, dimension, tier, offline-testability) was produced during exploration and is transcribed into `_ledger.py` as a **slice-1 deliverable** (§8.1). **Module-path note (root-vs-domain duplicates):** `scene_decomposer.py` and `continuity_engine.py` each exist at BOTH repo root and under `domain/`; the tests target the `domain/` ones (`domain.scene_decomposer`, `domain.continuity_engine`). The identity validator + thresholds live at `identity/validator.py` + `identity/types.py`; tri-mix is in `cinema_pipeline.py::_assemble_final` while loudnorm/xfade are in `phase_c_ffmpeg.py`. Representative high-priority seed (offline unless noted):

- **Routing/Cascade:** exact default cascade order; `try_next_api` filters attempted + `api_engines`-disabled; exhaustion→30s→retry ≤`cascade_retry_limit`; dialogue shot overrides `target_api`→VEO_NATIVE + `video_fallbacks=None` + `audio_embedded`; VEO_NATIVE is the only `native_audio:True` engine; Veo duration ∈{4,6,8} (5→6,7→8); Sora ∈[4,8,12,16,20] (invalid→4); Veo `reference_images`/`driving_video_path` accepted-but-dropped (Bug #4).
- **Shot routing:** `classify_shot_type` ∈ {portrait,medium,wide,action,landscape} (never close_up); `WORKFLOW_TEMPLATES` primary+fallbacks per type; PuLID weight per type (1.0/.9/.65/.8/.0).
- **Identity:** `SHOT_TYPE_THRESHOLDS` + linear degradation; composite = .6·arc+.4·aesth; `should_halt` composite-only; `needs_regenerate` + PuLID +0.15 cap 1.0; rolling-stats PuLID delta; adaptive-weight clamps + FACE_ANGLE_EXTREME/SMALL_FACE_REGION suppression.
- **Gates/auto-approve:** `_gate_satisfied` per gate; `_rules_for_plan` vetoes unless decision==APPROVED & empty violations; MODIFIED→APPROVED normalization + absence→stall; `image_min_composite` .97 / fallback .78 + fallback veto; motion gate opt-in `CINEMA_AUTO_APPROVE_MOTION`; `final_require_human_if_upstream_auto`; dialogue-aware final lipsync rule; best-take selection prefers non-fallback then composite.
- **Continuity/coherence:** `get_denoise_strength` (.55/.50/.40/.30) + UI clamp [0.2,0.6]; `should_use_img2img` same-scene & idx>0; `assess_coherence` formula + `valid=False` on imread failure; location seed determinism + verbatim fragment; `identity_anchor` injected verbatim.
- **Decompose:** `target_shots = max(2, min(5, int(dur/2.5)))`; `_fallback_decompose` → exactly 2 shots; `validate_shot_prompts` fail-safe → APPROVED on None client / persistent parse error.
- **Domain/persistence:** `mutate_project` lock→load→normalize→mutate→save-if-changed; `save_project` re-acquires lock (deadlock trap); shot-ID collision → `shot_{scene_id}_{idx}` (not globally unique → pid-scope); `extra="allow"` live fields persist; `_refresh_project_snapshot` validates before swap.
- **Assembly/audio:** loudnorm −14/11/−1.5; tri-mix 1.0/.12/.20; xfade audio cases + `anullsrc` pad + 48kHz stereo fltp normalize; transition clamp .4·min(dur); all-embedded TTS suppression; single project-level color grade.
- **Phases/lifecycle:** all three phases return `ok=True` on per-shot failure → `failed_shots`; headless raises `GateNotSatisfiedError`; `ThreadedLifecycle` vs `NullLifecycle`-returns-True trap; checkpoint atomic write + resume marks missing files `"lost"`.
- **Web:** shot PUT field allowlist (8 fields, others dropped); busy-fence 409 vs `_GATE_STAGES` pass; `screening/approve` requires `final_cinema.mp4` (else 409); single-consumer SSE; identity-guarded queue pop; `make_progress_callback` event shaping.
- **Cost:** budget gate video/image only; `spent_usd` per-process reset; audio isolated tracker; unknown model → $0.
- **Style/LLM:** `style_rules_to_prompt_suffix` concatenation; OpenAI-only style-gen → default on no key; style-gen skipped if pre-set; `PIPELINE_CONTEXT` injected into ChiefDirector/SceneDecomposer/DialogueWriter/StyleDirector.
- **Language/audio:** Korean → Cartesia Sonic 2 + 0.70 lipsync gate; `merge_language_defaults_into_settings` writes only the applied-fields set.
- **Live/E2E quality bars:** identity ArcFace across all shots ≥ lenient; coherence ≥ .6 same-location; lipsync ≥ bar on dialogue; loudness −14±1 / peak ≤ −1.5; format 1920×1080/30/h264+aac; motion not-regenerate; photorealism aesthetic ≥ floor (+ advisory judge).

## 10. Risks & open items

- **Stochastic flakiness (live/e2e):** mitigated by margins, bounded transient retries, produce-once-assert-many, and recording measured values rather than only pass/fail.
- **Photorealism subjectivity:** resolved — aesthetic floor is the gate; vision-LLM judge is advisory.
- **E2E spend:** the run is built but never executed without explicit user authorization; it is excluded from CI and the build process.
- **Reference-face provenance:** synthetic only; no real-person likeness committed.
- **Live infra coupling:** live tier depends on ComfyUI/pod + API creds; all `skipif`-gated so absence never fails CI.
- **Manual staleness:** the ledger ties tests to manual §; if a claim proves stale against code, fix the manual in the same change (per `CLAUDE.md`/`ARCHITECTURE.md` discipline).

---

*Terminal step after spec-review + user review: invoke `writing-plans` to produce the sliced implementation plan.*

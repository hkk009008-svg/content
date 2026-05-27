# Extensive Test Plan — Cycle 14 Joint Operator+Director Prep (2026-05-27)

**Status (post-adjudication):** ✅ **ESCALATION RESOLVED via OPTION B (semantic split with cross-references)** at director's `2006217` brief v0.4 + decision event `2026-05-27T09-00-00Z-director-to-operator-decision.md` (`68b92d2`). This document is now **CANONICAL for HOW/per-prompt/per-parameter content** (P1-P14 LLM prompt enumeration with file:line refs + tweak variants; §6 parameter directional predictions covering env vars + CINEMA_* + global_settings + sampling + ComfyUI workflow + ffmpeg + gate thresholds; §3 Lane C inventory of 61 routes / 35 UI components / 14 prompt sites / 30 env vars / 34 unit tests + gap enumeration; §1 predict-then-verify methodology spec; §7 Tier A/B/C operational execution sequencing).

**Companion (canonical for WHAT/WHY/structure):** [docs/BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md) at v0.4+ — director-seat strategic-default; covers test cell framework (P-* phase / G-* gate / PA-* parameter / PR-* prompt classes), predictive harness format (PREDICTION / ACTUAL / DELTA / INSIGHT / ADJUSTMENT), tier sequencing A→B→C→D (brief uses 4 tiers; this doc references brief's Tier D as scope extension), adjustment-pointing matrix, user-§9 decision tracking, sign-off slots. Brief's PR-* and PA-* cells cross-reference this doc's §5 and §6 enumerations (no content duplication; reference is the integration point per director's `68b92d2` Option B adjudication).

**Cross-seat coordination note:** This doc was parallel-drafted independently by operator-seat during cycle-14 mid-cycle (operator's cold-start mailbox `ls` truncated to 3 most-recent at cold-start, missing director's `T05:00:00Z` dispatch-claim event). Operator escalated via `2026-05-27T08-35-00Z-operator-to-director-dispatch-claim.md` (`fdd0094`); director adjudicated via Option B at `68b92d2`. **Substrate-empirical observation:** the parallel-draft collision exposes a Rule #4 RECENCY-window gap — pre-Write gate performed at cold-start is insufficient if substantive Write happens >30 min later in same session. Filed as N=1 candidate #8 (intra-session mailbox-state staleness; distinct from Candidate #7's inter-session inheritance) per operator REPLY recommendation; see `docs/REPLY-comprehensive-test-operator-2026-05-27.md` §"Rule #4 filing decision".

**Author:** Operator-seat (this cycle-14 entry session)
**User directive (verbatim):** _"both director and operator need to prepare for the extensive test for the program every function need to be tested to prove it works as intended the test will include mulitple real generation of the ouput which both will prepare togather in need to to prepared in a way that will be able to reveal which part need to be fixed or optimzied including prompts. the reusult of the test have to have indications to reveal which paramters need to be tweeked also predict how the program will output and behave before each step of the test and compare with the finding and use the differnce or sameness of the prediction to further requrie more insight."_

**Decomposed user requirements:**
1. **Coverage:** every function tested
2. **Real generations:** Tier B/C included (LLM + image + video + audio paid stack)
3. **Joint preparation:** both seats contribute, partitioned by specialization (role partition Sh)
4. **Diagnostic surface:** reveal what to fix/optimize, *including prompts*
5. **Parameter signals:** results indicate which parameters to tweak
6. **Pre-execution predictions:** each step has a hypothesis BEFORE running
7. **Prediction-vs-finding comparison:** difference *or* sameness produces insight (not just pass/fail)

**Companion docs:**
- [ARCHITECTURE.md](../ARCHITECTURE.md) — canonical pipeline map (verified 2026-05-24)
- [docs/PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) — discipline substrate (15 rules + N=1 candidate registry)
- [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) — cycle-14 entry strategic doc (refreshed at `69202da`)
- [docs/HANDOFF-director-transplant-2026-05-27-cycle13.md](HANDOFF-director-transplant-2026-05-27-cycle13.md) — director cycle-13 close (priority #1 = RunPod pod restart, blocker for Tier B/C)
- [docs/HANDOFF-operator-transplant-2026-05-27-cycle13.md](HANDOFF-operator-transplant-2026-05-27-cycle13.md) — operator cycle-13 close

---

## 1. Methodology — Predict-then-Verify Discipline

Each test step has the shape:

```
┌─ PREDICTION (authored BEFORE execution) ────────────────────────────┐
│ - Expected output shape (schema + values where falsifiable)         │
│ - Expected behavior (timing, side-effects, gate state transitions)  │
│ - Confidence (high / medium / low) + reasoning                      │
│ - Falsification criteria — what would prove prediction wrong        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ EXECUTION ─────────────────────────────────────────────────────────┐
│ - Exact command / endpoint / UI action                              │
│ - Required pre-state + parameter values                             │
│ - Observe + record actual output (shape, values, timing, logs)      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ COMPARISON ────────────────────────────────────────────────────────┐
│ - Prediction-vs-actual diff (or sameness)                           │
│ - Classify: ✅ predicted-correctly / ⚠️ off-axis / ❌ wrong-direction │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ DERIVED INSIGHT ───────────────────────────────────────────────────┐
│ - Sameness → model is correct on this surface (validates assumption)│
│ - Off-axis → prediction missed a dimension (refine model)           │
│ - Wrong-direction → assumption wrong (revise mental model)          │
│ - Action: fix? tweak parameter? refine prompt? defer? file finding? │
└─────────────────────────────────────────────────────────────────────┘
```

**Why predict-then-verify (vs pass/fail testing)?**

- **Surfaces hidden assumptions** — the act of authoring the prediction makes implicit assumptions explicit. If you can't predict, you don't understand the system well enough to test it.
- **Avoids confirmation bias** — predictions are committed BEFORE seeing the result; you cannot retroactively rationalize "of course it did that."
- **Diff IS the signal** — the prediction-vs-actual delta is itself diagnostic data. Sameness ≠ noise; it actively validates the model.
- **Echoes ADR-013 verification discipline** — "authority and verification travel together." Predictions BECOME the authority claim; execution becomes the verifying command.
- **Pairs with N=1 candidate #7 (carry-forward claim re-verification)** — same shape applied to inherited claims rather than newly-generated ones.

**Quality bar for predictions:**

- **Falsifiable:** the prediction must specify what would prove it wrong. "It should work" is not a prediction. "The endpoint returns HTTP 200 with `{status: 'queued'}` within 200ms" is a prediction.
- **Specific:** include values (numeric ranges, enum members, file existence) where possible; schemas where structure is testable.
- **Confidence-tagged:** explicit confidence label (high / medium / low) so post-test surprise is itself meaningful (low-confidence prediction matching = lower information; high-confidence prediction missing = high information).
- **Independent:** for cross-seat joint testing, both seats author predictions independently where possible (mirrors Rule #9 independent reviewer convention).

**Substrate-codification candidate (open):** This methodology, applied across the cycle-14 test, will produce empirical evidence about predict-then-verify's diagnostic yield. If yield is high (lots of derived insight per test step), file as N=1 candidate #8 for v5.X codification — the discipline becomes a project-wide standard for verification work, not just one-cycle test prep.

---

## 2. Joint Partition (proposed)

Per role partition Sh + the user's "both" framing:

### Operator-side (this draft scaffolds; cycle-14 execution iterates)

- ✅ Coverage audit (Lane C subagent; §3 below)
- ✅ Predict-then-verify methodology spec (§1)
- ✅ Per-phase test scaffolds (§4) — 13 stages, each with prediction template
- ✅ Prompt tweaking subjects (§5) — 14 LLM prompt sites with per-prompt predictions
- ✅ Parameter tweaking surface map (§6) — env vars + CINEMA_* + workflow params
- ✅ Tier A/B/C execution order (§7)
- ⏳ Per-test prediction authoring (during execution)
- ⏳ Post-test comparison + insight capture (during execution)
- ⏳ Lane V dispatches on any feat/refactor/fix commits the test reveals as needed
- ⏳ Mailbox follow-ups with findings

### Director-side `[DIRECTOR-TODO]` (proposed; mailbox dispatch-claim sent)

- ⏳ **RunPod ComfyUI pod restart** (Tier B/C blocker; pod was 403 cycle-13)
  - Either restart existing `0f8wqszne2zby7-8188.proxy.runpod.net` from RunPod console
  - OR fresh deploy via `scripts/setup_runpod.sh` + update `COMFYUI_SERVER_URL` in `.env`
  - Verification: `curl -sI "$COMFYUI_SERVER_URL/object_info" | head -1` returns 200
- ⏳ **Budget envelope sign-off** (Tier C upper-bound)
  - Default proposal: ~$10 max across full Tier-C sweep (one Tier-C reel @ $2-5 + 2-3 Tier-B per-shot probes @ $0.50 each + LLM-only Tier-B at ~$1)
  - Adjust per user appetite
- ⏳ **Success criteria refinement** — operator's draft criteria below (§7.4); director may tighten / loosen
- ⏳ **Predict-then-verify codification decision** — file N=1 candidate #8 at cycle-14 close? Or wait for second instance (cycle-15+ verification work)?
- ⏳ **Director-side independent predictions** — for high-stakes tests (Tier C reel), Rule #9 second-opinion shape: director authors independent prediction cold; compare to operator's; difference itself is diagnostic.

### Cross-seat joint sections

- ⏳ Test execution coordination via mailbox (Rule #8 authority)
- ⏳ Lane V dispatches per Rule #9 if test surfaces feat-eligible commits
- ⏳ Cycle-14 close handoff — both seats' findings + retrospective + codification decisions

**Mailbox dispatch-claim:** operator-to-director, will be sent at commit time pointing at this doc. 5-min silent-accept window per v5 R-Q3 Tier-1 disagreement protocol. Director may counter-refine via REPLY OR silent-accept.

---

## 3. Coverage Map (from Lane C inventory)

Source: subagent Lane C survey (read-only; 2026-05-27 at HEAD `69202da`).

### 3.1 Phases / Stages — 13 published (+ implicit PERFORMANCE_REVIEW + post-assembly SCREENING)

| Phase | File | Class/Func | Test coverage status |
|---|---|---|---|
| STYLE | `llm/style_director.py` | `generate_style_rules` | ❌ no `test_style_director.py` |
| AUDIO (BGM) | `audio/music.py` | `generate_bgm`, `generate_fal_bgm`, `_build_music_prompt` | ❌ no unit test |
| DECOMPOSE | `domain/scene_decomposer.py` | `decompose_scene`, `competitive_decompose_scene`, `_build_cinedecompose_system_prompt` | ❌ no `test_scene_decomposer.py` |
| DIRECTOR (validate) | `llm/chief_director.py` | `validate_shot_prompts`, `evaluate_take` | ✅ `test_director.py` (happy path + parse failure) |
| PLAN_REVIEW (Gate 1) | `cinema/review/controller.py` | `wait_for_gate("PLAN_REVIEW")` | ✅ `test_cross_controller.py` (interaction) |
| KEYFRAME | `cinema/phases/keyframe_render.py` | `KeyframeRenderPhase.run` | ❌ no `test_keyframe_render.py` |
| KEYFRAME image gen (sub) | `phase_c_assembly.py`, `quality_max.py` | `generate_ai_broll`, `generate_ai_broll_max` | ⚠️ `test_quality_max.py` covers N=8 overlays only; production `generate_ai_broll` pod-gated, no unit test |
| KEYFRAME_REVIEW (Gate 2) | `cinema/review/controller.py` | `wait_for_gate("KEYFRAME_REVIEW")` | ⚠️ partial (cross controller test) |
| PERFORMANCE | `cinema/phases/performance.py` | `PerformanceCapturePhase.run` | ❌ no `test_performance_phase.py` |
| PERFORMANCE engines (sub) | `performance/*` | `dispatch`, provider modules | ✅ partial: `test_router_semaphore.py`, `test_motion_gate.py`, `test_driving_video_provider.py`, `test_performance_*`; integration smokes for Act One + LivePortrait |
| PERFORMANCE_REVIEW (Gate 3) | (implicit) | bypass via `SKIP` or `approved_performance_take_id` | ❌ untested as a gate (handled by phase logic) |
| MOTION | `cinema/phases/motion_render.py` | `MotionRenderPhase.run` | ❌ no `test_motion_render.py` |
| MOTION engines (sub) | `phase_c_ffmpeg.py` + `kling_native.py` / `sora_native.py` / `veo_native.py` / `ltx_native.py` | `generate_ai_video` dispatch | ⚠️ `test_cascade_logic.py` covers cascade ordering only; per-engine adapters untested |
| REVIEW (Gate 4) | `cinema/review/controller.py` | `wait_for_gate("REVIEW")` | ⚠️ partial |
| SCENE_PREVIEW | `cinema/shots/controller.py` | `generate_scene_preview` | ❌ untested |
| ASSEMBLY | `cinema_pipeline.py:_assemble_final`, `phase_c_ffmpeg.py` | `assemble_approved_takes`, `stitch_modules`, `apply_color_grade`, `two_pass_loudnorm` | ⚠️ partial: `test_color_grading.py` covers grade only |
| SCREENING | `cinema/screening.py` | `_build_timeline_manifest`, `mark_*` | ✅ `test_screening.py` + `test_screening_endpoint.py` + `test_reassemble_endpoint.py` |

**Existing unit tests:** 34 files in `tests/unit/` + 2 integration smokes (Act One, LivePortrait). Baseline: 866 pass / 3 skip / 0 fail (cycle-13 close, preserved through cycle-14 entry).

**Critical gaps for "every function tested":**
- All four LLM-prompt phases (STYLE / AUDIO prompt / DECOMPOSE / DIALOGUE) lack unit tests of the prompt rendering + output schema
- All four phase wrapper classes (`KeyframeRenderPhase` / `PerformanceCapturePhase` / `MotionRenderPhase` / phase base protocol) lack unit tests
- Video native engine adapters (kling / sora / veo / ltx) untested at unit level
- ffmpeg dispatcher (`generate_ai_video`) routing untested beyond cascade ordering
- Lipsync cascades (4 overlay + 4 generation) untested
- Audio module suite (voiceover / music / dialogue / effects / alignment / srt) untested
- SSE streaming heartbeat + sentinel lifecycle untested
- ~50 HTTP routes (CRUD + lifecycle + gate approvals) lack endpoint-level tests beyond the 4 covered

### 3.2 HTTP Surface — 61 routes (59 unique handlers)

See Lane C inventory for full table. Categorized for test prioritization:

- **Tier A safe (read-only / project-state CRUD):** ~30 routes — GET /api/projects, characters CRUD, scenes CRUD, locations CRUD, settings reads, file serving
- **Tier A safe (gate state mutation only):** 4 gate-approve endpoints + 2 reject endpoints — write to `project.json`, no generation triggered if pipeline not running
- **Tier B (single LLM/image/perf call):** 8 routes — `/scenes/<sid>/decompose`, `/scenes/<sid>/generate-dialogue`, `/style-rules`, `/shots/<sid>/diagnose`, `/shots/<sid>/keyframes/generate`, `/shots/<sid>/motion/generate`, `/shots/<sid>/takes/<tid>/iterate`, `/characters/<cid>/train-lora`
- **Tier C (full pipeline):** 1 primary — `POST /api/projects/<pid>/generate` (spawns daemon thread); plus `assemble/screen` + `assemble/re-assemble` as downstream Tier C
- **Operational:** cancel / pause / resume / cleanup / disk-usage / cost-live / export

### 3.3 UI Surface — ~35 components

Grouped by mode:
- **Setup mode:** 6 panels (ProjectSelector, EditorialShell, CharacterPanel, LocationPanel, ObjectPanel, ScenePanel) + SettingsPanel (10 sections)
- **Pipeline mode:** 13 components — Layout, Header, StageRail, SceneExecutionCard, ShotRow, ReviewStage (all 4 gates), ScreeningStage, AssemblyGate, DirectorReviewCard, IterationPanel, PromptEditor, Filmstrip, ShotApprovalControls
- **Console mode:** 11 components — DirectorsConsole, PhasesRail, HeroShot, Filmstrip, TakeStrip, Monitor, Notes, AutoApproveBadge, RejectAutoApproveModal, Telemetry, PostRunSummary
- **No frontend test framework** (carry-forward from cycle 10) — all UI verification via `tsc --noEmit` + visual smoke

---

## 4. Per-Phase Test Specs (13 stages + sub-phases)

Each spec uses the predict-then-verify shape from §1. Predictions are AUTHORED HERE (operator-seat), to be CHECKED at execution time. Director-side independent predictions for Tier C reel (§4.13) per Rule #9 second-opinion convention.

### 4.1 STYLE (`generate_style_rules`)

**Tier:** B (~$0.05 GPT-4o call) | **Endpoint:** `POST /api/projects/<pid>/style-rules`

**PREDICTION:**
- Output: `dict[str, str]` with exactly 6 keys: `cinematography_rules`, `lighting_rules`, `color_palette_rules`, `sound_design_rules`, `photorealism_rules`, `composition_rules`. Each value is a non-empty string (typically 100-500 chars).
- Behavior: single GPT-4o call via `call_llm(client, "gpt-4o", system_prompt, user_prompt)` at `llm/style_director.py:106`. Latency 5-15s. No retries on parse failure (returns whatever GPT-4o emitted).
- Confidence: **high** on schema (read source directly); **medium** on values (LLM-dependent).
- Falsifiers: missing key → parse failure or fallback; latency >30s → LLM API issue; HTTP 500 → unhandled exception path (worth filing).

**EXECUTION:** trigger via `curl -X POST <pid>/style-rules` AND via UI "Generate Style Rules" button.

**COMPARISON CRITERIA:**
- Schema match: ✅ if all 6 keys present + non-empty | ❌ if any key missing or empty
- Value quality: subjective; capture sample for later prompt-tweaking analysis
- Latency vs prediction: within 5-15s = sameness; >30s = off-axis

**DERIVED INSIGHT QUESTIONS:**
- Are the 6 rule categories the right partition? (Style director system prompt design question)
- Do values cluster around a "house style" or vary widely across runs? (Run twice; compare.)
- Are there persistent gaps (e.g., always missing concrete value for `color_palette_rules`)? (→ tweak system prompt)

### 4.2 AUDIO (BGM)

**Tier:** B (~$0.20 FAL Stable Audio; or ~$1 Suno V5) | **Endpoint:** internal during pipeline OR isolated via direct `generate_bgm` call

**PREDICTION:**
- Output: `bgm.mp3` (raw) + `bgm_mastered.mp3` (post-pedalboard) under `projects/<pid>/audio/`. Duration capped at 47s (hardcoded; ARCHITECTURE §16 flags this).
- Prompt built by `_build_music_prompt(music_vibe, video_pacing, story_tension)` — text-only prompt to FAL.
- Confidence: **high** on file existence; **medium** on duration (FAL may return shorter); **low** on subjective quality.
- Falsifiers: file missing → API failure; duration >47s or <30s → prompt cap not enforced; mastering output missing → Pedalboard chain failure.

**EXECUTION:** isolate by directly calling `audio.music.generate_bgm` with synthetic `ctx`; OR observe during Tier C run.

**COMPARISON + INSIGHT:**
- Quality assessment: listen + note "fits topic / generic / off-brief"
- If off-brief: tweak `_build_music_prompt` template; predict before re-run that "more specific prompt → better fit"

### 4.3 DECOMPOSE (`decompose_scene` + `competitive_decompose_scene`)

**Tier:** B for single (~$0.10); C-component for competitive (~$0.30) | **Endpoint:** `POST /api/projects/<pid>/scenes/<sid>/decompose`

**PREDICTION:**
- Output: `scene["shots"]: list[dict]` where each shot has `prompt`, `camera`, `visual_effect`, `target_api`, `scene_foley`, `characters_in_frame`, `action_context`.
- Count: 4-12 shots typical for a 30-60s scene.
- Behavior (single): GPT-4o tool-use mode at `domain/scene_decomposer.py:578`. Latency 10-30s.
- Behavior (competitive): LLMEnsemble at `:632` → `[claude-sonnet-4, gpt-4o]` parallel → judge (claude-sonnet-4) picks. Latency 20-40s. Judge selection logged.
- Confidence: **high** on schema; **medium** on shot count (varies); **low** on prompt quality (LLM-dependent).
- Falsifiers: shot count <2 or >20 → prompt issue; missing schema keys → tool-use schema drift; judge picks `null` → ensemble error path.

**EXECUTION:** trigger single decompose first (cheaper); then competitive on same scene; compare.

**COMPARISON + INSIGHT:**
- Single vs competitive: does competitive produce materially different / better shots? (Tests the ensemble value)
- Prompt schema adherence: any missing keys? (→ tighten tool-use schema)
- "Action context" coherence: does it match `scene_text`? (Tests CineDecompose v1.0 prompt fidelity)

### 4.4 DIRECTOR validation (`ChiefDirector.validate_shot_prompts`)

**Tier:** B (~$0.04 per validation; ~$0.04 per take eval) | **Where:** runs in-pipeline after DECOMPOSE; also exposed via `/diagnose`

**PREDICTION:**
- Validation output: JSON with `decision: APPROVED|REJECTED|MODIFIED`, `violations: list`, `modifications: list`, `quality_score: 0-1`, `reasoning: str`.
- Trigger conditions: HC1-HC8 violations (identity firewall) or T1-T9 tripwires → likely `REJECTED|MODIFIED`.
- On `MODIFIED`: the shot prompts are mutated in-place per `modifications`.
- Confidence: **high** on schema; **medium** on when it modifies vs approves (depends on input shape).
- Falsifiers: schema violation → JSON parse fails; `decision` not in enum → drift; quality_score >1 or <0 → range bug.

**EXECUTION:** feed known-bad shots (deliberately violate HC1: change character identity mid-scene) to force `REJECTED`. Feed clean shots to force `APPROVED`.

**COMPARISON + INSIGHT:**
- False-negative rate: clean shots rejected? (→ relax Chief Director system prompt OR tighten decomposer)
- False-positive rate: bad shots approved? (→ tighten Chief Director constraints)
- Modification quality: do mutations preserve scene intent? (Tests T1-T9 tripwire phrasing)

### 4.5 PLAN_REVIEW Gate 1

**Tier:** A (no spend) | **Endpoint:** `POST /shots/<sid>/plan/approve` (and `/reject`)

**PREDICTION:**
- State transition: `project.json` flips `shot.plan_approved = true|false`. `ReviewController.wait_for_gate("PLAN_REVIEW")` polls per 500ms and unblocks.
- Behavior: approval can happen from idle (no pipeline running) — `_get_stage_pipeline` lazy-instantiates if needed.
- Confidence: **high** (deterministic JSON write).
- Falsifiers: gate doesn't unblock within 1s of approval → poll interval misconfigured; project.json corruption → filelock race; HTTP 500 → handler exception.

**EXECUTION:** Tier A — pipeline-state-only test. Run with empty pipeline, approve via endpoint, verify state.

**COMPARISON + INSIGHT:** straightforward pass/fail; mostly already covered by `test_cross_controller.py`. Use this Tier A as warm-up validation.

### 4.6 KEYFRAME (`KeyframeRenderPhase.run` + `generate_ai_broll`)

**Tier:** B (single shot ~$0.05 + GPU lease) | C (full keyframe pass) | **Trigger:** `POST /shots/<sid>/keyframes/generate` (single) OR in-pipeline (full)

**REQUIRES:** RunPod ComfyUI pod up [DIRECTOR-TODO blocker]

**PREDICTION:**
- Output per shot: PNG file under `projects/<pid>/keyframes/<shot_id>/take_<n>.png`. Identity score (DeepFace), aesthetic score, composite score recorded.
- Per-shot duration: ~30-60s with PuLID (production); ~3-5min with max-tier N=8 best-of.
- Identity score range: 0.40-0.85 typical (threshold `identity_strictness=0.60` default).
- Confidence: **high** on file output; **medium** on identity score range (face-dependent); **low** on aesthetic score interpretability.
- Falsifiers: pod 403/500 → pod state issue; identity score <0.30 → DeepFace failure; composite score nan → division bug; PNG truncated → ComfyUI workflow error.

**EXECUTION:**
1. Tier B: single-shot keyframe — predict identity score range from character ref quality
2. Tier C: full keyframe pass for a 4-6 shot scene
3. Vary parameters: PuLID weight (e.g., 0.8 → 1.0 → 0.6); predict directionality (higher weight = stronger identity = higher score?)

**COMPARISON + INSIGHT:**
- PuLID weight effect on identity score — does direction match prediction?
- Identity strictness threshold: how many takes pass at 0.60 vs 0.70 vs 0.50?
- Aesthetic vs identity tradeoff: do higher-identity takes score lower aesthetic?
- ComfyUI workflow node touches (`pulid.json` node 100 / 410-411 FreeU/PAG) — do node param changes produce predicted effect?

### 4.7 KEYFRAME_REVIEW Gate 2

**Tier:** A | Same shape as §4.5 PLAN_REVIEW. Approve a known take; verify pipeline picks it up; auto-approve veto rules (`cinema/auto_approve.py`) tested for ImageGate.

### 4.8 PERFORMANCE (`PerformanceCapturePhase.run`)

**Tier:** B (single shot Mode B / Hedra-FAL ~$0.10) | C (full performance pass) | **Trigger:** in-pipeline after keyframe approval

**PREDICTION:**
- Output: video clip under `projects/<pid>/performance/<shot_id>/take_<n>.mp4`. Identity gate score + motion gate score recorded.
- Mode A (operator-uploaded driving video): uses Runway Act One; Mode B autopilot (Hedra-FAL → Hedra-direct → SadTalker cascade).
- Per-shot duration: 30s-3min depending on engine.
- Confidence: **medium** (cascade has many failure points).
- Falsifiers: all 3 cascade engines fail → engine availability issue; identity score crashes <0.40 → DeepFace on video frames diverges from keyframe score; motion gate `needs_remotion=True` consistently → motion fidelity floor too tight.

**EXECUTION:**
1. Tier B: single shot in Mode B (autopilot); observe cascade decisions
2. Vary `motion_gate_samples` env (default 8) → does optical flow scoring change as predicted?
3. Mode A: upload a driving video; predict Act One output quality

**COMPARISON + INSIGHT:**
- Cascade order: does Hedra-FAL always win? Or fallbacks regularly fire? (→ tune availability checks)
- Motion gate threshold: false-rejection rate at default vs tightened?
- Identity gate on video: is the threshold consistent with keyframe-stage gate?

### 4.9 PERFORMANCE_REVIEW Gate 3 (implicit)

**Tier:** A | **Behavior under test:** gate is implicit — bypassed when all shots are `performance_engine=="SKIP"` or all have `approved_performance_take_id`. ARCHITECTURE.md notes: NOT in `_gate_satisfied`; opens implicitly.

**PREDICTION:** Setting all shots' `performance_engine = "SKIP"` should bypass review entirely. Setting one shot to a real engine should pause for review.

**INSIGHT QUESTION:** Is the implicit-gate behavior intentional / well-documented for operators? (carry-forward F-question candidate)

### 4.10 MOTION (`MotionRenderPhase.run` + `generate_ai_video`)

**Tier:** B (single shot LTX ~$0.10 or Veo ~$0.25) | C (full motion pass with mixed engines) | **Trigger:** `POST /shots/<sid>/motion/generate` (single) OR in-pipeline

**PREDICTION:**
- Output per shot: final cinematic clip mp4 under `projects/<pid>/motion/<shot_id>/take_<n>.mp4`.
- Cascade per `workflow_selector.py` — 5 shot-type templates × 11 engines. Predict which engine wins per shot type (e.g., DIALOGUE shots default to LTX or VEO).
- Per-shot duration: 1-5min (engine-dependent; Sora may be slower than Kling).
- Confidence: **medium** (engine availability varies); **high** on schema (mp4 output).
- Falsifiers: cascade exhausts all 11 engines → catastrophic API failure; motion fidelity floor unmet across all takes → floor too tight for this shot type.

**EXECUTION:**
1. Tier B: single shot in 3-4 different engines (LTX, Veo, Kling 3.0, Runway); compare quality + cost + latency
2. Vary `target_api` per shot to force engine selection; predict cascade short-circuit behavior

**COMPARISON + INSIGHT:**
- Per-engine quality variance: which engine produces best result per shot type?
- Cost vs quality tradeoff: is Sora ($0.80) noticeably better than LTX ($0.10)?
- Motion fidelity floor effect: how often does the floor reject good-looking takes?
- Per-template parameter effects: do the 5 shot-type templates use the right floors?

### 4.11 REVIEW Gate 4

**Tier:** A | Same shape as §4.5. Tests `approve_take("final")` path. Auto-approve `FinalGate` veto rules.

### 4.12 SCENE_PREVIEW + ASSEMBLY

**Tier:** A (assembly from existing takes; no new generation) — assuming approved motion takes are present

**PREDICTION:**
- ASSEMBLY: stitches approved motion takes → applies color grade (preset = `warm_cinema` default; or LUT path) → mixes BGM + scene foley → two-pass EBU R128 loudnorm → outputs `final.mp4`.
- Loudnorm two-pass: copy video, re-encode audio as `aac 192k`; target I/LRA/TP per `phase_c_ffmpeg.py:1000`.
- Confidence: **high** on schema; **medium** on quality (depends on takes + grading).
- Falsifiers: assembly fails → missing dependency (ffmpeg); audio drift → loudnorm bug; black frames between shots → stitch error.

**EXECUTION:**
1. Tier A first: assembly only, using fake takes (existing test fixtures) — should produce valid mp4
2. Tier C: full assembly after real motion pass
3. Vary `color_grade_preset` across 8 presets; predict visual effect direction

**COMPARISON + INSIGHT:**
- Loudnorm target compliance: actual I/LRA/TP vs target — accuracy of two-pass approach
- Color grade preset effect on perception (operator subjective)
- BGM mix balance: predict before, listen after
- Per-preset perceptual differences — are 8 presets the right granularity, or are some redundant?

### 4.13 Tier C Full Reel — End-to-End Predict-Then-Verify

**Tier:** C ($2-5 estimated; up to $10 worst case) | **REQUIRES:** RunPod pod up [DIRECTOR-TODO]

**SETUP:**
- Project: 1 scene, 4-6 shots, 1-2 characters with reference images, 1 location, BGM vibe + pacing specified
- Settings: production tier (not max); default identity strictness 0.60; default cascade orders

**OPERATOR PREDICTION (TO BE AUTHORED BEFORE TIER C RUN):**

`[PREDICTION-AUTHORING-BLOCK — to be filled at Tier C execution time, BEFORE pressing /generate]`

- Stage 1 STYLE — expected style_rules content (1-2 sentence summary): ___
- Stage 2 AUDIO — expected BGM character + duration: ___
- Stage 3 DECOMPOSE — expected shot count + shot types: ___
- Stage 4 DIRECTOR validate — expected verdict (APPROVED / MODIFIED count): ___
- Stage 6 KEYFRAME — expected per-shot identity score range: ___
- Stage 8 PERFORMANCE — expected cascade win rate (Hedra-FAL %): ___
- Stage 10 MOTION — expected per-shot engine selection (predict per-shot): ___
- Stage 13 ASSEMBLY — expected total runtime, output file size: ___
- **Cost prediction:** $___ ± $___ (with reasoning per $-line item)
- **Wall-clock prediction:** ___ minutes (with reasoning per stage)

**DIRECTOR PREDICTION (Rule #9 second-opinion) [DIRECTOR-TODO]:**

`[Director-authored independent prediction; do NOT show operator's prediction to director-seat before authoring]`

**EXECUTION:** Single Tier C run. Capture per-stage outputs + costs + timing.

**COMPARISON:**
- Operator prediction vs actual: per-stage diff table
- Director prediction vs actual: same shape
- Operator prediction vs Director prediction: where did the two cold-context predictions diverge? (This delta is itself diagnostic about which surfaces are well-understood vs murky.)

**DERIVED INSIGHT (Tier C is the diagnostic showcase):**
- Which stages were predicted-correctly by BOTH seats? → stable; well-understood
- Which stages diverged in operator vs director prediction? → ambiguous documentation; codify
- Which stages diverged in prediction vs actual for BOTH seats? → genuine knowledge gap; investigate
- Which prompts (Chief Director / CineDecompose / Style Director / Music) produced unpredicted outputs? → tweak candidates (§5)
- Which parameters need tweaking based on actual behavior? → (§6)

---

## 5. Prompt Tweaking Subjects

Per the user directive "_reveal which part need to be fixed or optimized including prompts_." 14 LLM prompt sites from Lane C inventory. For each: subject ID, prediction, tweak variants for A/B testing.

### P1. Style Director system_prompt (`llm/style_director.py:62`)

- **Current:** "world-class cinematographer and production designer" persona; outputs 6-rule JSON
- **Predicted weakness:** 6-rule partition may be coarse; `sound_design_rules` might be generic
- **Tweak variants:** (a) baseline; (b) add "be specific about color palette (named colors)" instruction; (c) include topic context in user_prompt
- **Compare:** rule specificity (count of concrete nouns) before vs after tweak

### P2. Chief Director `ChiefDirector v2.0` (`llm/chief_director.py:130-206`)

- **Current:** IDENTITY_FIREWALL HC1–HC8 + T1–T9 tripwires
- **Predicted weakness:** HC1-HC8 may over-trigger on legitimate character variation (e.g., different outfit ≠ different character)
- **Tweak variants:** (a) baseline; (b) relax HC1 wording on outfit variation; (c) add explicit "outfit changes do NOT count as identity violations" clarification
- **Compare:** false-positive REJECTED rate on clean shots before vs after

### P3. Chief Director evaluate_take (`llm/chief_director.py:352`)

- **Current:** RETRY/ACCEPT_LENIENT/FAIL trichotomy
- **Predicted weakness:** ACCEPT_LENIENT may be over-used (lowering bar) or under-used (forcing FAIL on borderline takes)
- **Tweak variants:** (a) baseline; (b) add explicit acceptance criteria for ACCEPT_LENIENT; (c) require quality_score floor for ACCEPT_LENIENT
- **Compare:** distribution of decisions across 20+ takes pre vs post

### P4. CineDecompose v1.0 (`domain/scene_decomposer.py:341-440`)

- **Current:** HC1-HC8 + T1-T9, structured 5-section format
- **Predicted weakness:** action_context field may be inconsistent; scene_foley may default to generic when unspecified
- **Tweak variants:** (a) baseline; (b) require action_context to reference scene_text directly; (c) add foley examples in system prompt
- **Compare:** schema completeness + per-shot field quality

### P5. CineDecompose competitive judge (`domain/scene_decomposer.py:_DEFAULT_JUDGE`, `claude-sonnet-4`)

- **Current:** Judge picks between 2 candidate decompositions
- **Predicted weakness:** Judge may default to first candidate (positional bias)
- **Tweak variants:** (a) baseline; (b) reorder candidates per call; (c) add explicit "do not prefer order" instruction
- **Compare:** judge selection distribution (should be ~50/50 if symmetric)

### P6. CinemaDirector verb-DSL (`llm/director.py:246-264`)

- **Current:** Generates verb-DSL action choreography
- **Predicted weakness:** verb-DSL output may be brittle to parse
- **Tweak variants:** (a) baseline; (b) tighten output schema; (c) add fallback parser
- **Compare:** parse-failure rate

### P7. Prompt Optimizer `_OPTIMIZER_SYSTEM_PROMPT` (`llm/prompt_optimizer.py:67`)

- **Current:** "senior cinema technical director AND commercial product" persona
- **Predicted weakness:** Dual-persona may produce inconsistent outputs
- **Tweak variants:** (a) baseline; (b) drop "commercial product" half; (c) make persona scene-aware
- **Compare:** prompt specificity + image quality post-optimization

### P8. Dialogue Writer (`domain/dialogue_writer.py:60`)

- **Current:** "professional screenwriter for photorealistic cinema"
- **Predicted weakness:** Dialogue may default to cinematic clichés
- **Tweak variants:** (a) baseline; (b) add "avoid clichés" with examples; (c) language-specific tuning (English vs Korean)
- **Compare:** cliché rate (manual coding on N=10 dialogues)

### P9. Music prompt `_build_music_prompt` (`audio/music.py:88`)

- **Current:** Text prompt assembled from `music_vibe`, `video_pacing`, `story_tension`
- **Predicted weakness:** Three-axis input may be too coarse for FAL Stable Audio
- **Tweak variants:** (a) baseline; (b) add instrument-list hint; (c) add tempo-bpm hint
- **Compare:** subjective fit + duration accuracy

### P10. LLM Ensemble quorum selection (`llm/ensemble.py:_QUORUM_MAP`)

- **Current:** `script`/`default` → `[claude-sonnet-4, gpt-4o]`; `decompose` → `[gpt-4o, claude-sonnet-4]`
- **Predicted weakness:** Quorum order may matter (judge may be biased)
- **Tweak variants:** (a) baseline; (b) reverse order for `decompose`; (c) add `gemini-2.5-pro` to default
- **Compare:** judge selection distribution

### P11. LLM Ensemble judge (`llm/ensemble.py:_judge` + `_DEFAULT_JUDGE = claude-sonnet-4`)

- **Current:** Default judge is claude-sonnet-4-20250514
- **Predicted weakness:** Using same model as a candidate may produce affinity bias
- **Tweak variants:** (a) baseline; (b) switch judge to gpt-4o; (c) cross-judge (different model per call)
- **Compare:** judge consistency + affinity rate

### P12. Continuity prompt enhancement (`domain/continuity_engine.py:enhance_shot_prompt`)

- **Current:** Deterministic assembly: raw + location + character + physics + motion + notes
- **Predicted weakness:** Assembly order may matter for image gen (later text often weighted more)
- **Tweak variants:** (a) baseline; (b) reorder fragments; (c) inject character anchor earlier
- **Compare:** identity score variance

### P13. Negative prompt generation (`llm/negative_prompts.py:get_negative_prompt_for_failure`)

- **Current:** String-template per failure reason
- **Predicted weakness:** May not cover all failure modes; static
- **Tweak variants:** (a) baseline; (b) add failure-mode-specific negative; (c) compose negative from multiple reasons
- **Compare:** retry success rate post-failure

### P14. Diagnosis system prompt (`llm/chief_director.py:365`)

- **Current:** Color temp / fill ratio diagnostic phrasing
- **Predicted weakness:** Diagnosis may default to generic suggestions
- **Tweak variants:** (a) baseline; (b) require numeric value in suggestion; (c) add diagnosis examples
- **Compare:** suggestion specificity

**Prompt-tweak insight cycle:** for each variant tested, the predict-then-verify shape from §1 applies: predict the effect direction BEFORE running the variant, compare, derive insight.

---

## 6. Parameter Tweaking Surface Map

Per the user directive "_indications to reveal which paramters need to be tweeked_." Inventory grouped by tier.

### 6.1 Environment variables (`config/settings.py`)

**Production-critical (no tweak — keys only):**
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `KLING_*`, `FAL_KEY`, `LTX_API_KEY`, `RUNWAYML_API_SECRET`, `SEEDANCE_API_KEY`, `ELEVENLABS_API_KEY`, `CARTESIA_API_KEY`, `STABILITY_API_KEY`, `SUNO_API_KEY`, `VIGGLE_API_KEY`, `HEDRA_API_KEY` — set in `.env`; not tweakable per-run
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (default `us-central1`)

**Infrastructure (rarely-tweaked):**
- `COMFYUI_SERVER_URL` (default `http://127.0.0.1:8188`; per-deployment)
- `EXPERIMENTS_DB_PATH` (default `data/experiments.db`)
- `PERFORMANCE_CACHE_DIR` (default `data/cache/driving`)
- `WEB_BIND_HOST` (default `127.0.0.1`)
- `WEB_CORS_ORIGINS` (default localhost-only; `*` for wide-open)

**Tweakable (test subjects):**

| Var | Default | Predict effect of tweak |
|---|---|---|
| `MOTION_GATE_SAMPLES` | 8 | ↑ samples → smoother motion score; longer eval. Predict: 16 doubles eval time, marginal score precision gain. |
| `KMP_DUPLICATE_LIB_OK` | TRUE | OS kludge; don't tweak (predict crash on FALSE) |

### 6.2 CINEMA_* feature flags

| Flag | Default | Predict effect of tweak |
|---|---|---|
| `CINEMA_LOG_LEVEL` | INFO | DEBUG → 10× log volume; observe whether any DEBUG-only events surface |
| `CINEMA_AUTO_APPROVE_MOTION` | (off / per-project) | ON → motion gate auto-approves on veto-pass; predict reduced operator clicks |
| `CINEMA_SCREENING_STAGE` | ON (v5.1+) | OFF → SCREENING + reassembly UI bypassed; predict shorter end-to-end |
| `CINEMA_DIRECTORIAL_ITERATION` | ON | OFF → `/iterate` returns 404; predict no other code path affected |
| `CINEMA_STRICT_SCHEMA` | (off?) | ON → Pydantic raises on shape mismatch (vs lenient migration); predict: surfaces all P1-3 migration drift |

### 6.3 Project `global_settings` UI knobs (per-project)

| Knob | Default | Predict effect of tweak |
|---|---|---|
| `budget_limit_usd` | (unset / inf?) | Set to `$1` → predict CostTracker stops pipeline mid-stage; capture which stage |
| `music_mastering` | `cinema_master` | Switch to `none` → predict raw BGM, no Pedalboard chain |
| `tts_provider` | (ElevenLabs?) | Switch to Cartesia / OpenAI → predict different voice quality + cost |
| `identity_strictness` | 0.60 | 0.50 → predict ↑ keyframe acceptance rate, ↓ identity coherence. 0.70 → opposite |
| `pulid_weight_override` | (None; use per-shot-type default) | 1.0 → predict stronger character anchor, possibly oversaturated |
| `language` | English | Korean → predict dialogue + TTS adaptation; predict CineDecompose accuracy degrades unless tuned |
| `master_image_seed` | (random) | Fixed → predict reproducible keyframe across runs |
| `music_vibe` | (per-project) | Test variants: "tense", "uplifting", "melancholy" → predict BGM character shift |
| `video_pacing` | (per-project) | "slow-burn" vs "kinetic" → predict shot count + cut rhythm shift |
| `story_tension` | (per-project) | "low" vs "high" → predict music + decompose mood shift |

### 6.4 Model / sampling parameters

| Where | Param | Default | Predict effect |
|---|---|---|---|
| `llm/ensemble.py:247` | Anthropic `max_tokens` | 4096 | ↓ to 2048 → predict truncation on long decomposes |
| `llm/chief_director.py:100` | Chief Director `max_tokens` | 4096 | Sufficient; don't tweak |
| `llm/director.py:251` | CinemaDirector `max_tokens` | 2048 | ↑ to 4096 → predict richer verb-DSL |
| `llm/ensemble.py:59` | `_QUORUM_MAP['script']` | `[claude-sonnet-4, gpt-4o]` | Reverse → predict judge bias shift |
| `llm/ensemble.py:64` | `_DEFAULT_JUDGE` | `claude-sonnet-4` | gpt-4o → predict affinity-bias change |
| `sora_native.py:48,87` | Sora `model` | `sora-2` | (no alternative currently) |
| `veo_native.py:54-55` | Veo `model` | `veo-3.1-generate` | preview variant → predict quality regression |
| `kling_native.py:93,386` | Kling `model_name` | `kling-v1-6` | v2.0 if available → predict quality jump |
| `ltx_native.py:233-238` | LTX `model` | `ltx-2-3-pro` | (no alternative currently) |

### 6.5 Image-gen workflow parameters (per shot type, in ComfyUI workflows)

Per `workflow_selector.py:get_workflow_params(shot_type)` — 5 templates each carrying:

| Param | Predict effect of tweak |
|---|---|
| `pulid_weight` | ↑ stronger identity anchor (and possibly distortion); ↓ weaker anchor (and more diversity). Test ±0.10. |
| `guidance` (CFG) | ↑ tighter prompt adherence (less variation); ↓ looser, more creative. Test ±2. |
| `steps` | ↑ marginal quality, much longer; ↓ faster, possibly under-cooked. Test ±10. |
| `motion_fidelity_floor` | ↑ stricter motion gate (more rejections); ↓ permissive. |
| `negative_prompt` | Add specific failure mode → reduce that failure |
| Adaptive PuLID weight | `get_adaptive_pulid_weight(character_id)` ±0.10 based on rolling success_rate — observe whether adaptation direction matches prediction |

### 6.6 Max-quality tier (`pulid_max.json`, `quality_max.py`)

| Param | Default | Predict effect |
|---|---|---|
| N-candidates best-of | 8 | ↓ to 4 → 2× faster, possibly lower best score. ↑ to 16 → 2× slower, marginal score gain (diminishing return). |
| SUPIR enabled | True | False → predict softer outputs; speed gain |
| HiDream-I1 swap | (`_swap_to_hidream`) | Predict different style than FLUX baseline |
| LoRA strength | (per `quality_max.py:405`) | Direct identity-vs-creativity tradeoff |

### 6.7 ffmpeg / assembly parameters

| Param | Default | Predict effect |
|---|---|---|
| `apply_color_grade` preset | `warm_cinema` | 7 alternative presets (per `COLOR_GRADE_PRESETS`); predict per-preset perceptual axis (warm/cool/saturated/desaturated/etc.) |
| `apply_color_grade` LUT override | (None) | Custom LUT → predict overrides preset |
| `two_pass_loudnorm` target_i | (default per spec) | ↑ louder; ↓ quieter; predict listener perception delta |
| `adjust_speed` factor | 1.0 | 0.9 → slow-mo; 1.1 → snappier; predict storytelling impact |

### 6.8 Performance / identity / motion gates

| Param | Default | Predict effect |
|---|---|---|
| `identity_strictness` (project) | 0.60 | Already in §6.3; reiterated for completeness |
| `motion_gate_samples` (env) | 8 | Already in §6.1 |
| Per-template `motion_fidelity_floor` | (per shot type) | Already in §6.5 |
| Hedra aspect ratio | inferred | Override → predict cropping artifacts |
| SyncNet threshold (`lip_sync.py:_sync_gate_settings`) | 1.0 fallback | Tighter threshold → more retries; loosened → faster but lower sync quality |

**Parameter-tweak insight cycle:** for each parameter tweaked, the predict-then-verify shape from §1 applies. The DIRECTION OF EFFECT prediction is the falsifiable claim; magnitude is secondary.

---

## 7. Tier A/B/C Execution Plan

### 7.1 Tier A — Free local tests (run FIRST; no pod, no spend)

**Goal:** validate all logic that doesn't require external services. Should be runnable with `pytest tests/unit/` + a few HTTP smoke tests against a locally-running Flask server.

**Steps (in order):**
1. `pytest tests/unit/ -q` — verify 866 baseline preserved
2. Start Flask server (`python web_server.py` background); verify `/api/config` returns 200
3. Create new project via UI / curl; verify project.json shape
4. Add character + reference image; verify identity anchor builds
5. Add location + image; verify location prompt fragment builds
6. Add scene with text + dialogue; verify scene roundtrip
7. Gate approvals on empty-state pipeline (Tier A safe) — `plan/approve`, `keyframes/<tid>/approve`, etc.; verify project.json state transitions
8. Pause / resume / cancel against idle pipeline; verify no-op behavior
9. `cleanup` endpoint; verify transient files removal
10. Color grade application against test-fixture takes (covered by existing tests)
11. ffmpeg stitch + loudnorm against test-fixture mp4s

**Pre-execution prediction:** all 11 Tier A steps pass. Any failure = bug surfaced.

**Cost:** $0. Wall-clock: ~20 minutes.

### 7.2 Tier B — Single-call paid tests (run after Tier A passes)

**Goal:** exercise each external API in isolation. Budget envelope: ~$2-3 total across all single-call tests.

**Steps (in order, in approximate cost order):**

1. **Style rules** — `POST /style-rules` (~$0.05)
2. **Dialogue generation** — `POST /scenes/<sid>/generate-dialogue` (~$0.04)
3. **Single scene decompose (non-competitive)** — `POST /scenes/<sid>/decompose` (~$0.10)
4. **Chief Director diagnose** — `POST /shots/<sid>/diagnose` (~$0.04)
5. **Iterate endpoint** — `POST /shots/<sid>/takes/<tid>/iterate` (~$0.06)
6. **BGM (FAL Stable Audio)** — internal call OR test fixture; ~$0.20
7. **Single character LoRA training** — `POST /characters/<cid>/train-lora` (~$0.30 + ~15min GPU)
8. **Multi-angle ref generation** — for one character (~$0.20)
9. **Single keyframe (production tier)** — `POST /shots/<sid>/keyframes/generate` (~$0.05 + GPU lease window) **[REQUIRES POD UP]**
10. **Single motion (LTX cheap)** — `POST /shots/<sid>/motion/generate` with target_api=LTX (~$0.10)
11. **Single motion (Veo)** — same with target_api=VEO (~$0.25)
12. **Single motion (Kling 3.0)** — same with target_api=KLING_3_0 (~$0.40)
13. **Competitive decompose** — same scene (~$0.30)
14. **Sora native motion** — single shot (~$0.80) **[optional; pricey]**
15. **Max-tier keyframe (N=8 best-of)** — single shot (~$0.40) **[optional; pricey]**

**Pre-execution prediction:** each Tier B step produces output matching §4 predictions per phase. Capture LLM responses, image samples, video samples for post-test analysis.

**Cost:** ~$2-3 if 1-13 only; ~$4 if 14-15 included.

### 7.3 Tier C — Full reel end-to-end (run after Tier B; main predict-then-verify event)

**Goal:** §4.13 — full `/generate` pipeline with both seats' independent predictions.

**Setup:** project from Tier B (already has style rules, characters, location, scene, dialogue decomposed).

**Steps:**

1. **Pre-execution prediction authoring** — operator fills `[PREDICTION-AUTHORING-BLOCK]` in §4.13. Director fills independent block. Neither sees the other's prediction.
2. **Execute** — `POST /generate`. Observe SSE stream for live progress.
3. **Per-stage capture** — record actual outputs / timing / cost at each of 13 stages.
4. **Post-execution comparison** — diff operator-prediction vs actual, director-prediction vs actual, operator-prediction vs director-prediction (cross-seat diff diagnostic).
5. **Insight derivation** — populate `## 8. Findings + Insights` section of this doc.

**Cost:** $2-5 typical, up to $10 worst case (depends on scene length + engine mix).

**Wall-clock:** 30 minutes - 2 hours.

### 7.4 Success criteria `[DIRECTOR-TODO: refine]`

**Operator's draft criteria (director may tighten / loosen):**

- **Tier A:** 100% pass. Any failure is a regression vs cycle-13 baseline 866 → file Lane V or fix-on-own-findings.
- **Tier B:** 100% completed (output present + no HTTP 500). Subjective quality assessment recorded; tweak candidates filed.
- **Tier C:**
  - Reel produces a valid `final.mp4` (assembly succeeds end-to-end)
  - Cost within budget envelope `[DIRECTOR-TODO: $-cap]`
  - At least 50% of operator's stage-level predictions match actual (sameness rate)
  - Cross-seat prediction agreement on at least 5 of 13 stages
  - At least 3 prompt-tweak candidates identified from §5
  - At least 3 parameter-tweak candidates identified from §6

---

## 8. Findings + Insights (POPULATED DURING EXECUTION)

**This section will be filled in during cycle-14 test execution. Structure preview:**

### 8.1 Tier A findings
- (per step: predicted vs actual; bugs surfaced)

### 8.2 Tier B findings
- (per phase: output samples; prompt quality; parameter sensitivity)

### 8.3 Tier C findings — Operator prediction vs actual
- (per stage: ✅ / ⚠️ / ❌)

### 8.4 Tier C findings — Director prediction vs actual `[DIRECTOR-TODO]`
- (same shape, director-authored)

### 8.5 Cross-seat prediction divergence
- (where operator and director cold-context predicted different things — itself diagnostic)

### 8.6 Tweak candidates
- Prompts (from §5)
- Parameters (from §6)
- Architecture (from cross-cutting observations)

### 8.7 Codification candidates
- Predict-then-verify as N=1 candidate #8 for v5.X (if discipline yields high diagnostic value)
- Other discipline-shaped observations

---

## 9. Open Items for Director Coordination

`[DIRECTOR-TODO]` items collected in one place for the next director session:

1. **RunPod ComfyUI pod restart** — blocker for Tier B/C. Verification command: `curl -sI "$COMFYUI_SERVER_URL/object_info" | head -1` should return 200.
2. **Budget envelope sign-off** — what's the Tier C $-cap? Operator's working assumption: $10 max.
3. **Success criteria refinement** (§7.4) — operator's draft is conservative; director may tighten thresholds.
4. **Independent Tier C predictions** — director authors §4.13 prediction block cold (without seeing operator's). Cross-seat diff is diagnostic per Rule #9 second-opinion convention.
5. **Predict-then-verify codification decision** — file as N=1 candidate #8 at cycle-14 close? Or wait for second instance in cycle-15+ verification work?
6. **Lane V dispatch policy for test-discovered issues** — if Tier B/C surfaces a bug fix, does the fix go through Lane V like any other feat/refactor/fix commit?
7. **Test-execution cadence** — single intensive test session OR spread Tier A/B/C across multiple sessions?

---

## 10. Sign-off (operator-side)

**Operator-seat cycle-14 entry (this session).**

Scaffolding ships at HEAD `<TBD; commit not yet placed>`. Coverage audit + methodology + per-phase scaffolds + prompt subjects + parameter map + tier execution order all populated. Director-side sections marked `[DIRECTOR-TODO]`. Mailbox dispatch-claim event accompanies this commit.

The predict-then-verify methodology is the spine — every test step structured as prediction → execution → comparison → insight. Pairs with ADR-013 verification discipline ("authority and verification travel together") and N=1 candidate #7 (carry-forward claim re-verification — same shape applied to inherited claims).

If cycle-14 execution yields high diagnostic value, the discipline is a candidate for codification at v5.X. If yield is low, the discipline is just methodology and stays in this doc.

Standing by for director-side completion + user direction on execution start.

*Operator-seat — 2026-05-27 (cycle-14 entry; joint test prep scaffolding).*

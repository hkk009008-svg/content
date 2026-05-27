# BRIEF — Comprehensive End-to-End Test Protocol with Predictive Harness

**Author (initial draft):** Director-seat (cycle 14, 2026-05-27)
**Co-author (pending):** Operator-seat (joint prep per user direction "both director and operator need to prepare … togather")
**For:** Both seats jointly, then user-principal sign-off, then joint execution
**Companion docs:**
- [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) §"Cycle 14 entry" — substrate state at brief-write time
- [docs/BRIEF-operator-validation-2026-05-26.md](BRIEF-operator-validation-2026-05-26.md) — cycle-10 Surface A/B validation template (structural reference, narrower scope)
- [ARCHITECTURE.md](../ARCHITECTURE.md) §4.1 `generate()` phase sequence (19 steps); §5 phase protocol; §7 story prep; §8 image; §9 video; §10 perf+lipsync; §11 identity; §12 audio; §13 LLM
- [docs/HANDOFF-director-transplant-2026-05-27-cycle13.md](HANDOFF-director-transplant-2026-05-27-cycle13.md) §"What's in flight" — RunPod pod state + U7/U8 carry-forward
- [docs/PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) §"N=1 candidates" — Candidate #7 discipline (re-verify before re-assert) applies throughout

**Status (at brief-write time, 2026-05-27 cycle-14 mid-cycle):**
- **DRAFT v0.3** — director-seat structural skeleton + predictive harness framework + adjustment rubric framework + user §9 decisions logged + 6 phase cell PREDICTIONs filled (P-STYLE, P-DECOMPOSE, P-KEYFRAME, P-MOTION, P-IDENTITY, P-ASSEMBLY) + 3 prompt class cell PREDICTIONs filled (PR-STORY, PR-IMAGE, PR-MOTION)
- AWAITING operator-seat REPLY with operational-discipline additions (Lane V coverage, doc-sync points, test isolation, telemetry collection) + remaining cell PREDICTIONs (P-BGM, P-CHIEFDIR, P-PERFORMANCE; G-* gate cells; PA-* parameter cells; PR-DIALOGUE/PR-CONTINUITY/PR-STYLE-LLM/PR-CHIEFDIR/PR-AUDIO-VIBE prompt cells)
- USER-PRINCIPAL DECISIONS LANDED (2026-05-27): Tier B+C+D scope (comprehensive); $50 hard budget cap; fresh RunPod pod deploy via `scripts/setup_runpod.sh`; fill PREDICTIONs in advance (this v0.2)
- NOT EXECUTABLE until §"Pre-flight checklist" all-green + operator REPLY landed + brief v1.0 + user-principal execution authorization

---

## TL;DR (90 seconds)

User direction (paraphrased): "Extensive test of the program. Every function must be proven to work as intended. Multiple real generations. Both seats prepare together. Reveal what needs fixing/optimizing INCLUDING PROMPTS. Indications for which parameters need tweaking. Predict outputs/behavior BEFORE each step. Compare with findings. Use delta to drive further insight."

**This brief operationalizes that as a four-tier test gauntlet (A → B → C → D)** with a **predictive harness** wrapped around every test cell:

1. **Tier A — Substrate verification (no pod, no real generations).** Static gates, smoke, full unit suite, type-check, lint, manifest sanity. ~30 min wall-clock. $0.
2. **Tier B — Single-shot real-generation walk-through (pod required, ~$1-2).** Smallest viable project end-to-end: 1 scene, 1 shot, no performance, default audio. Validates plumbing, prompt round-trips, file outputs.
3. **Tier C — Full reel real-generation walk-through (pod required, ~$3-7).** Medium project: 1 scene, 3-5 shots, performance enabled, identity validation enforced. Validates inter-shot continuity, identity, audio mixing, gate flow.
4. **Tier D — Multi-reel comparison (optional, pod required, ~$8-15).** Same prompt × different parameter sets. Validates parameter sensitivity. Reveals which params matter most for output quality. Skip if Tier C surfaces too many blockers.

**Each test cell follows a predictive-harness format:**

```
PREDICTION:    what we expect to observe (output shape, content quality, latency, cost, failure modes)
ACTUAL:        what we observed (filled during execution)
DELTA:         semantic distance (PASS / MINOR-DELTA / MAJOR-DELTA / FALSIFIED)
INSIGHT:       if delta ≠ 0, what does this reveal (impl bug? mental-model gap? prompt issue?)
ADJUSTMENT:    specific param/prompt suggestion (or "no action — prediction held")
```

The brief specifies predictions for ~30 distinct cells across pipeline phases × prompt classes × parameter classes. Real-gen execution fills in ACTUAL + DELTA + INSIGHT + ADJUSTMENT.

**Output of the test:** a structured findings report with adjustment-pointing matrix that maps observed deltas to specific tweak candidates (prompt rewrites, parameter ranges, code paths). Per the discipline: prediction matches reinforce the mental model; prediction misses drive further investigation.

**Blockers at brief-write time:**
- RunPod ComfyUI pod returning HTTP 403/404 since cycle-13 entry; required for Tier B/C/D
- Real-generation budget approval (~$3-7 for full Tier C; ~$15-25 if Tier D included)
- Operator REPLY (joint prep)

---

## 1. Coordination model — joint prep via REPLY cycle

Per CLAUDE.md role partition Sh: brief authoring is strategic-seat-default (director drafts). User explicit direction "both director and operator need to prepare … togather" overrides default to JOINT REPLY-CYCLE prep, per v5+ proposal-bundle precedent.

**Workflow:**

1. **Director ships v0.1 draft** (this commit). Sends `dispatch-claim` mailbox event to operator with brief reference + invitation to REPLY.
2. **Operator REPLY** (next operator session) — adds:
   - Operational discipline (Lane V coverage during test execution; doc-sync triggers; telemetry collection conventions)
   - Test isolation rules (pytest leakage discipline learned cycle-13; fresh-project fixtures)
   - Per-phase verification commands (operator-seat owns the cold-context verification angle)
   - Recommended REPLY refinements to predictive harness format (operator may know failure modes director hasn't named)
   - Sign-off on the structural plan or counter-refinements per v5 disagreement protocol
3. **Director folds REPLY → ships v1.0** (next director session, or cross-seat fold per Rule #15).
4. **User-principal reviews v1.0**, answers §"Open questions" (scope, budget, timeline), authorizes execution.
5. **Joint execution** — both seats observe; operator runs verification subagents per Lane V; director processes findings + drafts adjustment recommendations.
6. **Post-test:** joint authorship of findings report (`docs/REPORT-comprehensive-test-2026-05-2X.md`); adjustment recommendations folded as separate `fix:` / `tune:` / `prompt:` commits.

**Authority precedence during execution** (per Rule #8 + #10):
- User-principal: any direction during execution
- Joint-seat consensus: changes to the brief mid-execution
- Director-seat: prediction calibration; adjustment recommendation drafting
- Operator-seat: Lane V dispatch on each fix/tune/prompt commit; cold-context verification of findings
- Either seat: STOP signal if a CRITICAL surfaces (e.g., data corruption, budget overrun, identity-validator failure cascading)

---

## 2. Scope

**In scope:**

| Class | Examples | Test tier |
|---|---|---|
| **Pipeline phases** (ARCHITECTURE §4.1) | STYLE / BGM / DECOMPOSE / KEYFRAME / PERFORMANCE / MOTION / IDENTITY / ASSEMBLY | B + C |
| **Gates** (ARCHITECTURE §6) | GATE 1 PLAN_REVIEW / GATE 2 KEYFRAME_REVIEW / GATE 3 PERFORMANCE_REVIEW / GATE 4 REVIEW + SCREENING + ASSEMBLY | C |
| **LLM prompt classes** (ARCHITECTURE §13) | Story decomposition / dialogue / continuity / style rules / image prompts / video prompts / motion prompts / chief-director validation | B + C |
| **Image generation params** (ARCHITECTURE §8) | model, sampler, steps, cfg, seed, resolution, IP-Adapter weight, controlnet weight, IDs (max-tier N=8) | B + C + D (D for sensitivity sweep) |
| **Video generation params** (ARCHITECTURE §9) | engine routing (5 templates × 11 engines), motion strength, frame count, fps, seed | B + C + D |
| **Performance capture params** (ARCHITECTURE §10) | lip-sync model selection, sync threshold, audio drive shape | C |
| **Identity validation params** (ARCHITECTURE §11) | GhostFaceNet threshold, similarity cutoff, multi-take retry logic | C |
| **Audio params** (ARCHITECTURE §12) | BGM vibe selection, voice ID, foley density, two-pass loudnorm targets, BGM 47s hard-cap | B + C |
| **Cost / budget** | per-LLM cost tracking, per-image cost, per-video cost, total budget caps | B + C (B for unit cost; C for budget enforcement) |
| **Surfaces A + B** (default-on post cycle-11 flag-flip) | IterationPanel UX, ScreeningStage UX, iterate-from-screening flow, re-assemble flow | C (U7/U8 closure) |
| **Frontend UX** | tsc clean; ErrorBoundary firing; SSE progress events; gate dialog states | A |

**Out of scope (this brief):**

- Distributed deployment (P4-2 explicitly NOT-DOING per STRATEGIC_REVIEW)
- Multi-user / multi-tenant testing
- Authentication / authorization edge cases (no auth in current design)
- A/B testing infrastructure (P4-4 needs operator volume data first)
- Vendor swapping (RunPod → alternative pod; FAL → alternative TTS; OpenAI/Anthropic LLM swap)
- Stress / load testing (single-operator usage assumed)

**Explicit scope clarifications:**

- "Every function" = every PIPELINE COMPONENT validated end-to-end through real generation. Unit-level coverage is already at **866 unit tests** (cycle-14 baseline; preserved across cycle-14 commits). This brief covers the layer ABOVE unit tests: real-system behavior + prompt quality + parameter calibration. NOT literal "every Python function in isolation" — that would duplicate the unit suite.
- "Prove it works as intended" = falsifiable-prediction discipline. Each test cell has a written PREDICTION; ACTUAL is observed; DELTA computed; PASS only if DELTA == 0 (or within stated tolerance). MINOR/MAJOR-DELTA triggers investigation. FALSIFIED triggers prediction-set revision + impl investigation.

---

## 3. Pre-flight checklist (must pass before Tier B/C/D)

```bash
# A1. Working tree state
git status -sb                          # main...origin/main, clean
git log --oneline -5                    # confirm baseline

# A2. Static gates
.venv/bin/python scripts/ci_smoke.py    # OK
(cd web && npx tsc --noEmit)            # exit 0
(cd web && npm run build)               # clean build

# A3. Full unit suite
.venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
# Expected: 866 passed, 3 skipped, 0 failed (cycle-14 baseline post `dbcde8b`).
# Cycle-10 "flake" RETIRED at `dbcde8b` — should NO LONGER appear as failure.

# A4. ARCHITECTURE.md §15 smoke
# (Same as A2 — same script. Listed separately to acknowledge the doc-of-truth.)

# A5. RunPod ComfyUI pod alive
curl -sI "$COMFYUI_SERVER_URL/object_info" --max-time 10 | head -1
# Expected: HTTP/2 200 OK or HTTP/1.1 200 OK
# Cycle-14 entry: HTTP/2 404 (pod down) — BLOCKER for Tier B/C/D

# A6. LLM provider keys + budget headroom
echo "OPENAI_API_KEY: $([ -n "$OPENAI_API_KEY" ] && echo set || echo MISSING)"
echo "ANTHROPIC_API_KEY: $([ -n "$ANTHROPIC_API_KEY" ] && echo set || echo MISSING)"
echo "FAL_KEY: $([ -n "$FAL_KEY" ] && echo set || echo MISSING)"
# Test project budget: review .env CINEMA_BUDGET_LIMIT_USD

# A7. Identity validator weights present
ls models/ghostfacenet*.pth 2>/dev/null || ls weights/ghostfacenet* 2>/dev/null
# (TODO operator-REPLY: confirm exact path; if missing, identity gate cannot validate)

# A8. Sample project ready
# Decision: (a) reuse populated project from domain/projects/ (look for human-titled,
#  large project.json, non-empty scenes); or (b) create fresh minimal project via UI.
# Option (a) faster if available; option (b) costs ~$3-7 to create from scratch.
ls domain/projects/ | head -10
# Filter strategy: ignore "Test Project <id8>" pytest fixtures; look for distinctive names
```

**Pre-flight all-green criterion:** A1-A8 all return expected values. ANY red = brief execution paused until red is closed.

---

## 4. Predictive harness — required format for each test cell

```markdown
### Test cell <ID> — <name>

**Phase / class:** <phase or prompt class or parameter>
**Stage in pipeline:** <ARCHITECTURE §X reference>
**Test tier:** <A | B | C | D>
**Estimated cost:** <$X.XX>
**Wall-clock prediction:** <X-Y minutes>

#### PREDICTION (write BEFORE running)

**Expected output (shape):** <data structure / file format / field names>
**Expected content quality:** <semantic expectations; e.g., "JSON dict with non-empty 'aesthetic_style' field; mood matches topic">
**Expected latency:** <range>
**Expected cost:** <range>
**Expected failure modes (top 3):** <ranked likely failures>
**Expected adjustment indicators (if failure):**
  - failure-mode-1 → tweak-candidate-1
  - failure-mode-2 → tweak-candidate-2
  - failure-mode-3 → tweak-candidate-3

#### ACTUAL (fill DURING / AFTER running)

**Observed output:** <paste / link>
**Observed content quality:** <semantic assessment>
**Observed latency:** <measured>
**Observed cost:** <measured>

#### DELTA

**Classification:** PASS | MINOR-DELTA | MAJOR-DELTA | FALSIFIED
**Reasoning:** <why this classification>

#### INSIGHT (if DELTA ≠ PASS)

**What this reveals:** <impl bug? mental-model gap? prompt issue? param miscalibration? environmental?>
**Confidence:** <low / medium / high>
**Investigation cost:** <minutes-to-hours estimate>

#### ADJUSTMENT (specific recommendation)

**Target:** <file:line / prompt name / param name>
**Recommended tweak:** <concrete change>
**Risk:** <low / medium / high>
**Verification:** <how would we know the tweak worked>
```

**Why this format:**

- **PREDICTION before running** enforces falsifiable hypotheses. Without explicit pre-commitment, "looks fine" is post-hoc rationalization. The discipline forces "what would I find surprising" as a first-class artifact.
- **DELTA classification** disciplines the conclusion. PASS / MINOR / MAJOR / FALSIFIED are 4 distinct mental states with different action implications.
- **INSIGHT separates "the implementation is wrong" from "my model is wrong."** Both produce DELTA; the remediation is opposite. Naming the difference prevents wasted impl-fixing on model-gap symptoms.
- **ADJUSTMENT is concrete** — not "improve the prompt" but "change `cinema/prompts/style_rules.txt` line 12 to ...". Vague adjustments don't ship; concrete adjustments do.

---

## 5. Test cells

The cells below cover Tier B + C predictively. Tier A (substrate verification) is the pre-flight checklist § 3. Tier D (parameter sensitivity sweep) is added in v1.0 post-operator-REPLY based on Tier B/C findings.

> **Status:** v0.1 STUB — director has filled cell IDs + phase mapping + estimated cost. **PREDICTION text TO BE FILLED jointly with operator** in v0.5 (mid-prep) or as the first execution-step action per cell (whichever discipline the joint REPLY agrees on).

### 5.1 Phase test cells (B + C)

| ID | Phase | Trigger | Tier | Cost est. | Status |
|---|---|---|---|---|---|
| P-STYLE | STYLE rules generation | `generate_style_rules(project)` | B + C | $0.01-0.05 LLM | **FILLED v0.2** |
| P-BGM | BGM generation | `_ensure_bgm(settings)` (FAL Stable Audio) | B + C | $0.10-0.30 | STUB |
| P-DECOMPOSE | Scene decomposition | `decompose` (competitive or single LLM) | B + C | $0.05-0.20 per scene | **FILLED v0.3** |
| P-CHIEFDIR | ChiefDirector validation | post-decompose validation pass | B + C | $0.02-0.10 | STUB |
| P-KEYFRAME | Keyframe rendering | `KeyframeRenderPhase.run(ctx)` | B + C | $0.05-0.30 per shot (ComfyUI) | **FILLED v0.2** |
| P-PERFORMANCE | Performance capture | `PerformanceCapturePhase.run(ctx)` | C | $0.10-0.50 per shot | STUB |
| P-MOTION | Motion rendering | `MotionRenderPhase.run(ctx)` | B + C | $0.30-1.00 per shot (Veo/LTX/Kling/...) | **FILLED v0.2** |
| P-IDENTITY | Identity validation | GhostFaceNet at end-of-shot | C | $0 (local) | **FILLED v0.3** |
| P-ASSEMBLY | Final assembly | `_assemble_final` (FFmpeg stitch + color + BGM mix + 2-pass loudnorm) | B + C | $0 (local) | **FILLED v0.2** |

#### Test cell P-STYLE — STYLE rules generation

**Phase / class:** Phase (step 3 in `generate()`)
**Stage in pipeline:** ARCHITECTURE §7 + §13 LLM coordination; impl at `cinema_pipeline.py:772-805` + `llm/style_director.py:generate_style_rules`
**Test tier:** B + C
**Estimated cost:** $0.01-0.05 (single LLM call; depends on provider)
**Wall-clock prediction:** 3-8 seconds

**PREDICTION (filled at v0.2 from impl-read at `e25a737`, per §8 protocol):**

- **Expected output (shape):** dict with keys derived from `style_rules_to_prompt_suffix` consumers (style/aesthetic/palette/mood). Function called with `(project_name, mood, color_palette, music_mood, aspect_ratio)`; returns a dict suitable for `latest_settings["style_rules"] = style_rules` write. Per `cinema_pipeline.py:797`, the return value gets persisted under `global_settings.style_rules` and consumed later via `style_rules_to_prompt_suffix(settings.get("style_rules", {}))` at `cinema/shots/controller.py:333`.
- **Expected content quality:** non-empty dict; at least one human-readable string field that meaningfully alters image prompts (validation: `style_rules_to_prompt_suffix(result)` returns non-empty string for at least 80% of inputs). For `topic="moody noir thriller"`, expect mood-aligned fields (e.g., palette mentions "deep shadows" / "muted tones"); for `topic="bright children's animation"`, expect inverse.
- **Expected latency:** 3-8 seconds (single LLM call; depends on provider — OpenAI typically 2-4s, Anthropic typically 3-6s, local model variable). Anything >15s suggests provider degradation OR oversized prompt.
- **Expected cost:** $0.005-0.02 per call (assuming GPT-4o-class model with ~500-token prompt + ~200-token response per pricing).
- **Expected failure modes (top 3):**
  1. **Empty dict returned** (LLM produced non-JSON or malformed JSON; parser fell through to default)
  2. **Generic/topic-mismatched content** (LLM ignored topic; returned boilerplate aesthetic boilerplate)
  3. **Missing required keys** (LLM returned valid JSON but omitted fields consumers expect; `style_rules_to_prompt_suffix` returns empty string)
- **Expected adjustment indicators:**
  - Empty dict → check `llm/style_director.py` prompt; check JSON parsing robustness; add schema validator with retry
  - Generic content → tighten system prompt with topic-conditioning + few-shot examples; lower temperature
  - Missing keys → add post-call schema validation with required-fields check + retry-with-error-feedback

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-KEYFRAME — Keyframe rendering

**Phase / class:** Phase (step 8 in `generate()`)
**Stage in pipeline:** ARCHITECTURE §8 image generation; impl at `cinema/phases/keyframe_render.py` (iterates shots) → `cinema/shots/controller.py:314 generate_keyframe_take` (per-shot)
**Test tier:** B (1 shot) + C (3-5 shots per scene)
**Estimated cost:** $0.05-0.30 per shot via ComfyUI pod (model-dependent; SDXL ~$0.02, FLUX ~$0.10-0.20 per image at typical settings)
**Wall-clock prediction:** 15-60 seconds per shot (depends on model + steps + max-tier wire-up)

**PREDICTION (filled at v0.2 from impl-read at `cinema/shots/controller.py:314-400`, per §8 protocol):**

- **Expected output (shape):** dict with `success: bool` + `take_id: str` + `image: <path>` on success; `success: False, error: <reason>` on failure. Take stored under `runstate.shot_results[shot_id]` with `image=<path>` + `take_id` + `status`. Image file at `_take_output_path(shot_id, take_id, ".jpg")`.
- **Expected content quality:** image file exists at returned path; file size >50KB (rejects empty/blank-image failure mode); image dimensions match `settings.aspect_ratio` config (16:9 → 1920×1080 or similar); subject content visually aligns with `enhanced["prompt"]` (which combines shot prompt + style_suffix + continuity context). For test topic with named character, expect character identity present (gates to P-IDENTITY downstream).
- **Expected latency:** 15-60s per shot (SDXL ~15-25s; FLUX ~25-45s; FLUX max-tier with LoRA/IP-Adapter ~40-60s). Pod-side cold-start adds ~10-30s on first request after fresh deploy.
- **Expected cost:** ComfyUI generation cost is pod-time-based, not per-call. RunPod A100 ~$1-2/hr; ~$0.02-0.05 per 30s generation. LLM cost for prompt assembly is negligible (~$0.001 per shot for `enhance_shot_prompt`).
- **Expected failure modes (top 3):**
  1. **Plan not approved** — `shot.get("plan_status") != "approved"` returns early with error. Gate flow bug if encountered post-PLAN_REVIEW.
  2. **ComfyUI workflow error** (pod returns 500 / missing custom node / model not loaded / OOM)
  3. **Subject mismatch / identity drift** (image generated but character looks wrong; gates to P-IDENTITY false-positive risk)
- **Expected adjustment indicators:**
  - Plan-not-approved → investigate GATE 1 plumbing; check PLAN_REVIEW gate predicate
  - ComfyUI error → check pod logs; verify custom nodes (`scripts/setup_runpod.sh` outputs); verify model loaded; adjust steps/resolution if OOM
  - Subject mismatch → strengthen IP-Adapter weight; verify LoRA path resolution at `char_lora_paths`; tighten character prompt section; lower CFG if subject is over-stylized

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-MOTION — Motion rendering (image→video)

**Phase / class:** Phase (step 15 in `generate()`)
**Stage in pipeline:** ARCHITECTURE §9 video routing (5 templates × 11 engines); impl at `cinema/phases/motion_render.py` (iterates shots) → `cinema/shots/controller.py:generate_motion_take` (per-shot; sibling of generate_keyframe_take)
**Test tier:** B (1 shot) + C (3-5 shots per scene)
**Estimated cost:** $0.30-1.00 per shot, engine-dependent — Veo ~$0.50-1.00 per 5s clip; LTX local ~$0.05-0.10; Kling ~$0.35-0.50; Sora variable
**Wall-clock prediction:** 30s-3min per shot, engine-dependent

**PREDICTION (filled at v0.2 from impl-read at `cinema/phases/motion_render.py:43-80` + ARCHITECTURE §9, per §8 protocol):**

- **Expected output (shape):** dict with `success: bool` + `take_id` + `video: <path>` on success; `success: False, error: <reason>` on failure. Phase requires approved keyframe (precondition enforced by motion generator); returns "Approved keyframe required..." error if absent. Video file at take output path with `.mp4` extension; runstate.shot_results updated with `video=<path>`.
- **Expected content quality:** video file exists; duration matches shot's intended length (typically 3-8s per shot per BGM 47s hard cap divided across ~6-10 shots); subject from keyframe persists across frames (no identity-drift across generated video); motion direction matches `shot.get("camera", "zoom_in_slow")` directive (zoom in → subject grows; pan left → background shifts right). Audio not yet present (mute video; audio mixed in at P-ASSEMBLY).
- **Expected latency:** Veo ~60-180s/clip; LTX local ~30-60s; Kling ~45-120s. Cold engine call adds ~10-30s. Total Tier C reel (3-5 shots × motion) potentially 5-15 minutes.
- **Expected cost:** Veo dominates if used — $0.50-1.00 per 5s clip × 3-5 shots = $1.50-5 for Tier C reel. LTX local is ~10x cheaper. Engine routing is per-shot via `target_api` field; mixed engines per reel is supported per ARCHITECTURE §9.
- **Expected failure modes (top 3):**
  1. **Engine API error** (Veo / Kling / Sora returned error: rate limit / content policy / quota exceeded)
  2. **Identity drift across frames** (character morphs mid-clip; visible at frame 30+ of 5s clip)
  3. **Motion direction wrong** (`camera: "zoom_in"` but video pans instead; engine ignored hint)
- **Expected adjustment indicators:**
  - Engine API error → check API key + quota; check error response body; route to alternative engine; verify content-policy compliance
  - Identity drift → strengthen IP-Adapter conditioning; lower motion strength; use shorter clip; try alternative engine (some engines more identity-stable than others)
  - Motion wrong → check `target_api` routing; check engine-specific motion prompt encoding; adjust motion strength keywords

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-ASSEMBLY — Final assembly (FFmpeg stitch + color + BGM + loudnorm)

**Phase / class:** Phase (step 19 in `generate()`)
**Stage in pipeline:** ARCHITECTURE §4.1 step 19 + §12 audio pipeline; impl at `cinema_pipeline.py:_assemble_final` + `phase_c_ffmpeg.py`
**Test tier:** B (single-shot assembled into 1-shot reel) + C (multi-shot reel)
**Estimated cost:** $0 (all local FFmpeg)
**Wall-clock prediction:** 30s-2min for Tier B; 1-5min for Tier C (depends on reel length + transcode complexity)

**PREDICTION (filled at v0.2 from impl-read at `cinema_pipeline.py:644-665` + `_assemble_approved_takes_core` doc per §8 protocol):**

- **Expected output (shape):** `{"success": True, "final_path": <path>}` with file at `final_cinema.mp4` in project export_dir. Per-scene preview files at `scene_<id>_preview.mp4` from `generate_scene_preview` step. Final mp4 is single concatenated file with BGM + per-scene audio mixed + loudnorm normalized.
- **Expected content quality:** mp4 file exists + plays in standard player; duration ≈ sum(shot durations) + transitions; BGM audible at -23 LUFS (broadcast standard) per loudnorm; no abrupt audio cuts at shot boundaries; color grade applied uniformly per scene (no scene-to-scene color jump unless intended); resolution matches `aspect_ratio` setting throughout. Subject identity preserved at scene boundaries (continuity from P-IDENTITY).
- **Expected latency:** 30s-2min for Tier B (1-3 shots × 5s each); 1-5min for Tier C (5+ shots × 5s + audio mix + 2-pass loudnorm). Two-pass loudnorm alone takes ~30-90s for typical reel length.
- **Expected cost:** $0 (local FFmpeg + local color grade preset + BGM already generated upstream).
- **Expected failure modes (top 3):**
  1. **Missing take mp4** — `_build_scene_packages` returns `missing_shots` non-empty; assembly aborts with "Approved take files are missing for: <list>"
  2. **FFmpeg error** (codec mismatch / corrupt input / OOM during transcode / loudnorm crash)
  3. **Audio sync drift** (BGM length mismatched to video length; per-scene audio offset misaligned)
- **Expected adjustment indicators:**
  - Missing take → trace why approved_final_take_id points to nonexistent file; check P-MOTION output path discipline
  - FFmpeg error → check FFmpeg version + codecs; reduce transcode complexity (lower resolution if OOM); check loudnorm input format compatibility
  - Audio sync drift → verify BGM 47s hard cap enforcement; verify per-scene audio length calculation; check two-pass loudnorm I/LRA/TP target consistency

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-DECOMPOSE — Scene decomposition (LLM, competitive or single)

**Phase / class:** Phase (step 5 in `generate()`, per-scene)
**Stage in pipeline:** ARCHITECTURE §7.3 (decomposition has TWO trigger paths) + §7.4 LLM decomposer; impl at `cinema_pipeline.py:820-867` → `competitive_decompose_scene` / `decompose_scene` + `director.validate_shot_prompts`
**Test tier:** B (1 scene) + C (1-2 scenes)
**Estimated cost:** $0.05-0.20 per scene (competitive uses 2-3 parallel LLMs; single uses 1)
**Wall-clock prediction:** 8-25 seconds per scene (competitive: 8-15s parallel; single: 8-12s; +ChiefDirector validation 3-8s)

**PREDICTION (filled at v0.3 from impl-read at `cinema_pipeline.py:830-866`, per §8 protocol):**

- **Expected output (shape):** list of shot dicts, each with `id`, `description`, `prompt`, `camera`, `characters` (subset of scene's characters_present), `target_api` (optional engine routing hint). Persisted via `update_scene_shots(project, scene_id, shots)` at line 866. ChiefDirector validation may modify (`decision: "MODIFIED"`) or reject (`decision: "REJECTED"` → regenerate with single decomposer).
- **Expected content quality:** ≥3 shots per scene (storyboard-meaningful decomposition); each shot has a non-empty description that advances scene narrative; camera directives match scene mood (e.g., "zoom_in_slow" for intimate moments); character coverage matches `characters_present`. For a 60s scene, expect 5-10 shots (~6-12s per shot).
- **Expected latency:** competitive ~8-15s wall-clock (parallel max-of-N); single ~8-12s; ChiefDirector adds ~3-8s. Total step ~12-25s per scene.
- **Expected cost:** competitive 2-3× single cost; single ~$0.02-0.07 per scene (token-based); ChiefDirector adds ~$0.01-0.05.
- **Expected failure modes (top 3):**
  1. **Competitive decompose throws → fallback to single** (`except Exception` at line 837 catches and falls through; logged via `logger.exception`). Indicates competitive race-condition OR provider error.
  2. **ChiefDirector REJECTED** (`decision: "REJECTED"` at line 858; regenerates with single decomposer). Indicates first-pass shots violated constraints (character coverage, scene-mood mismatch, prompt-policy violation).
  3. **Empty or single-shot decomposition** (LLM didn't elaborate; storyboard insufficient for downstream phases). KeyframeRenderPhase would produce sparse output.
- **Expected adjustment indicators:**
  - Competitive-failure-then-fallback → check competitive race semantics; check parallel LLM concurrency limits; verify provider rate limits
  - ChiefDirector REJECTED → strengthen prompt with explicit constraints; add few-shot examples for shot-decomposition; verify ChiefDirector's validate_shot_prompts prompt
  - Empty / single-shot → strengthen "decompose into N shots" instruction; add `min_shots=3` post-validation; lower LLM temperature to reduce randomness

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-IDENTITY — GhostFaceNet identity validation

**Phase / class:** Quality gate (invoked at end of each keyframe generation, NOT a phase per se)
**Stage in pipeline:** ARCHITECTURE §11 identity validation; impl at `cinema/shots/controller.py:484-506` → `phase_c_vision._get_shared_validator().validate_image(img_path, primary_ref, character_id, threshold)`
**Test tier:** C (multi-shot reel with named characters)
**Estimated cost:** $0 (local GhostFaceNet inference)
**Wall-clock prediction:** 0.5-3 seconds per shot (GhostFaceNet on CPU/GPU)

**PREDICTION (filled at v0.3 from impl-read at `cinema/shots/controller.py:484-506` + ARCHITECTURE §11, per §8 protocol):**

- **Expected output (shape):** `id_result` object with `overall_score: float [0.0-1.0]`, `passed: bool`, `character_results: dict[char_id → CharResult]`, where CharResult has `primary_failure_reason` (enum) + `suggested_pulid_adjustment`. Take metadata persists `identity_score` (always) + `identity_failure_reason` + `suggested_pulid_adjustment` (only on fail).
- **Expected content quality:** for shots with `primary_ref` (character reference image), `identity_score` correlates with visible character similarity. Threshold default 0.70 (per `cc.get("identity_threshold", 0.70)`); operator can override via `settings.identity_strictness`. Score >0.85 = strong identity match; 0.70-0.85 = passable; <0.70 = fail (take rejected or flagged for review).
- **Expected latency:** 0.5-3s per shot. Singleton validator (`_get_shared_validator()`) amortizes model-load cost across pipeline run; first call after fresh process can take +5-15s for model load.
- **Expected cost:** $0 (local inference). GPU vs CPU latency differs but cost is identical.
- **Expected failure modes (top 3):**
  1. **False negative — real character rejected** (legitimate face but pose/lighting/angle differs from reference; threshold too strict)
  2. **False positive — wrong face accepted** (different person passes threshold; threshold too lenient OR reference image ambiguous)
  3. **Validator throws / returns malformed result** (model not loaded; reference image missing; weights missing; phase_c_vision import error)
- **Expected adjustment indicators:**
  - False negative → lower `identity_strictness` (try 0.65); diversify reference images (multi-pose); add retry-with-different-pose logic; check `suggested_pulid_adjustment` for IP-Adapter weight hint
  - False positive → raise `identity_strictness` (try 0.80); add multi-frame validation across video (P-MOTION); verify reference image is unambiguous (single face, frontal)
  - Validator throws → check phase_c_vision module path; verify GhostFaceNet weights present (pre-flight A7); check primary_ref file exists; lower-level CV library compat issue

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

> **Remaining phase cells (P-BGM, P-CHIEFDIR, P-PERFORMANCE) are STUB pending operator REPLY OR continued director session.** 6 of 9 phase cells filled at v0.3.

### 5.2 Gate test cells (C only)

| ID | Gate | What it validates | Tier | Status |
|---|---|---|---|---|
| G-PLAN | GATE 1 PLAN_REVIEW @ 25% | Plans approved before keyframe | C | STUB |
| G-KEYFRAME | GATE 2 KEYFRAME_REVIEW @ 55% | Keyframes approved before performance | C | STUB |
| G-PERF | GATE 3 PERFORMANCE_REVIEW @ 65% | Performance approved (or SKIP-bypassed) before motion | C | STUB |
| G-REVIEW | GATE 4 REVIEW @ 82% | Reviews approved before assembly | C | STUB |
| G-SCREEN | SCREENING @ post-assembly | User approves final reel before re-assembly | C | STUB |
| G-ITERATE | Surface A iterate-from-gate | `regenerate_with_intent` flow at any gate | C | STUB |

### 5.3 Prompt class test cells (B + C)

| ID | Prompt class | Where invoked | Tier | Status |
|---|---|---|---|---|
| PR-STORY | Story decomposition prompts | LLMEnsemble.decompose | B + C | **FILLED v0.3** |
| PR-DIALOGUE | Dialogue generation prompts | LLMEnsemble.generate_dialogue | C | STUB |
| PR-CONTINUITY | Continuity engine prompts | ContinuityEngine.* | B + C | STUB |
| PR-STYLE-LLM | Style rules generation prompts | LLMEnsemble.generate_style_rules | B + C | STUB (covered partially by P-STYLE) |
| PR-IMAGE | Per-shot image prompts | KeyframeRenderPhase prompt assembly | B + C | **FILLED v0.3** |
| PR-MOTION | Per-shot motion prompts | MotionRenderPhase prompt assembly | B + C | **FILLED v0.3** |
| PR-CHIEFDIR | ChiefDirector validation prompts | post-decompose validation | B + C | STUB |
| PR-AUDIO-VIBE | BGM vibe selection prompts | `_ensure_bgm` upstream | B + C | STUB |

#### Test cell PR-STORY — Story decomposition prompts

**Phase / class:** Prompt class (cross-cuts P-DECOMPOSE phase; specifically the LLM input to `decompose_scene` / `competitive_decompose_scene`)
**Stage in pipeline:** ARCHITECTURE §7.4 LLM decomposer; impl in domain/llm/* (decompose modules)
**Test tier:** B + C
**Estimated cost:** $0 — prompt evaluation is intrinsic to P-DECOMPOSE; this cell is a focused angle, not a separate LLM call
**Wall-clock prediction:** N/A — reuses P-DECOMPOSE observation

**PREDICTION (filled at v0.3 from P-DECOMPOSE impl + scene-decompose call chain, per §8 protocol):**

- **Expected output (shape):** N/A — this cell observes the LLM-input prompts that produce the P-DECOMPOSE outputs. Evaluation is qualitative: does the prompt elicit a faithful storyboard decomposition?
- **Expected content quality:** prompt construction includes: scene description + character list (with traits) + location description + style rules (from P-STYLE) + decomposition instructions (number-of-shots range, camera language vocabulary, narrative-arc expectation). Prompt should be specific enough that the LLM produces 3-10 shots that ADVANCE the scene narrative (not 10 static talking-head shots).
- **Expected failure modes (top 3):**
  1. **Generic shots** — LLM produced shots that could fit ANY scene (no scene-specific narrative); root cause: prompt under-specified the narrative arc expectation
  2. **Character coverage gap** — shots omit characters listed in `characters_present`; root cause: prompt didn't enforce per-character minimum or list characters prominently
  3. **Camera-language vocabulary out of bounds** — shots use camera terms the downstream image gen doesn't support; root cause: prompt didn't constrain to canonical vocabulary (zoom_in_slow, pan_left, dolly_back, etc.)
- **Expected adjustment indicators:**
  - Generic shots → strengthen "advance the narrative" instruction; add few-shot examples of strong scene-decomposition; add chain-of-thought "first identify scene's narrative arc, then..."
  - Character coverage gap → add "every character listed must appear in at least one shot" constraint; add post-validation `validate_character_coverage(shots, characters_present)`
  - Camera vocab out of bounds → enumerate allowed camera terms in prompt; add post-validation against canonical list; add fuzzy-match fallback to nearest canonical term

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-IMAGE — Per-shot image prompts

**Phase / class:** Prompt class (cross-cuts P-KEYFRAME phase; the prompt assembly logic at `cinema/shots/controller.py:333-345`)
**Stage in pipeline:** ARCHITECTURE §8; impl spans `enhance_shot_prompt` (ContinuityEngine `domain/continuity_engine.py:446`) → `style_suffix` (`style_rules_to_prompt_suffix`) → `positive_prompt` override path
**Test tier:** B + C
**Estimated cost:** $0 — prompt assembly is intrinsic to P-KEYFRAME; this cell is a focused angle
**Wall-clock prediction:** N/A — reuses P-KEYFRAME observation

**PREDICTION (filled at v0.3 from `cinema/shots/controller.py:333-345` + `domain/continuity_engine.py:446 enhance_shot_prompt`, per §8 protocol):**

- **Expected output (shape):** `full_prompt: str` constructed from `enhanced["prompt"]` (continuity-enhanced shot prompt with character/location injection + approved-anchor reference) + `style_suffix` (style rules formatted as prompt fragment). Final prompt passed to ComfyUI workflow as positive prompt.
- **Expected content quality:** prompt is image-generation-ready (descriptive nouns + adjectives; no abstract narrative-only language); contains character name + visual descriptor (if character in shot); contains location descriptor; reflects scene style (mood/palette/aesthetic per P-STYLE output); 50-300 words typical length. For shot with character "Anya, dark hair, leather jacket" at location "rainy alley at night", expect prompt mentions both subject and setting.
- **Expected failure modes (top 3):**
  1. **Continuity-anchor inconsistency** — `approved_anchor` reference image conflicts with shot's intended visual (e.g., character was day-shot in anchor, this shot is night; visual continuity breaks)
  2. **Style suffix duplicates / contradicts shot prompt** — style_suffix mentions "warm tones" but shot prompt mentions "cold blue lighting"; LLM-image-gen produces ambiguous output
  3. **Character descriptor missing / wrong** — character name appears but no visual descriptor (LLM-image-gen produces inconsistent renders across shots; identity validation fails)
- **Expected adjustment indicators:**
  - Continuity anchor conflict → improve `_resolve_previous_approved_keyframe` selection (e.g., scene-boundary-aware; skip anchors from different time-of-day); allow operator override
  - Style suffix contradicts → reconcile style_suffix with per-shot scene-mood; add precedence rule (per-shot wins over global)
  - Character descriptor missing → enforce per-character descriptor injection in `enhance_shot_prompt` for every character in shot; validate prompt mentions all characters present

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-MOTION — Per-shot motion prompts

**Phase / class:** Prompt class (cross-cuts P-MOTION phase; motion prompt assembly inside `generate_motion_take`)
**Stage in pipeline:** ARCHITECTURE §9 video routing (5 templates × 11 engines); each engine has its own prompt-encoding shape
**Test tier:** B + C
**Estimated cost:** $0 — prompt assembly is intrinsic to P-MOTION; this cell is a focused angle
**Wall-clock prediction:** N/A — reuses P-MOTION observation

**PREDICTION (filled at v0.3 from `cinema/phases/motion_render.py` + ARCHITECTURE §9 + per-engine template structure, per §8 protocol):**

- **Expected output (shape):** engine-specific prompt encoding. Veo expects natural-language motion description + camera directive + optional negative prompt; LTX expects keyword-style motion encoding; Kling expects narrative-paragraph format; each engine's template is a `5 templates × 11 engines` grid mapping (per ARCHITECTURE §9). Prompt typically extends the keyframe prompt with motion verbs (zoom_in, pan_left, dolly_back) + optional motion-strength qualifier.
- **Expected content quality:** prompt explicitly encodes camera direction (matches `shot.get("camera")`); preserves character identity descriptor from PR-IMAGE; maintains style continuity (no abrupt aesthetic change from keyframe to motion); engine-appropriate format (Veo: natural; LTX: keyword).
- **Expected failure modes (top 3):**
  1. **Engine-template mismatch** — prompt encoded for engine X passed to engine Y (e.g., natural-language prompt sent to keyword-style engine); engine ignores or misinterprets
  2. **Motion verb absent / contradictory** — prompt says "zoom_in" but description includes "static shot"; engine produces ambiguous motion
  3. **Identity drift in motion prompt** — character descriptor in PR-IMAGE not preserved in PR-MOTION; engine generates motion of "a character" not "Anya specifically"; identity_score drops vs keyframe
- **Expected adjustment indicators:**
  - Engine-template mismatch → verify `target_api` routing to template-selection; add prompt-format validator per engine class
  - Motion verb absent → enforce camera-directive inclusion in motion prompt template; add post-assembly verification (prompt contains camera term from canonical list)
  - Identity drift → propagate character descriptor from PR-IMAGE to PR-MOTION explicitly; verify prompt mentions character name + visual descriptor; consider keyframe-conditioned video gen (engines that accept image+text vs text-only)

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

> **Remaining prompt cells (PR-DIALOGUE, PR-CONTINUITY, PR-STYLE-LLM, PR-CHIEFDIR, PR-AUDIO-VIBE) are STUB pending operator REPLY OR continued director session.** 3 of 8 prompt cells filled at v0.3.

### 5.4 Parameter class test cells (D — optional sensitivity sweep)

| ID | Parameter class | Sweep candidates | Tier | Status |
|---|---|---|---|---|
| PA-SAMPLING | sampler steps / cfg / scheduler | 3 sets × 1 shot = 3 generations | D | STUB |
| PA-IMAGE | resolution / model swap | 2 sets × 1 shot = 2 generations | D | STUB |
| PA-VIDEO | engine routing (Veo / LTX / Kling) | 3 engines × 1 shot = 3 generations | D | STUB |
| PA-MOTION | motion strength low/med/high | 3 sets × 1 shot = 3 generations | D | STUB |
| PA-LIPSYNC | lip-sync threshold | 2 sets × 1 shot = 2 generations | D | STUB |
| PA-IDENTITY | GhostFaceNet threshold | 3 sets × 5 shots = 15 evaluations (no new generations) | D | STUB |
| PA-AUDIO | loudnorm targets | 2 sets × 1 reel = 2 reels | D | STUB |

---

## 6. Adjustment-pointing matrix

The matrix below maps DELTA-classified findings to specific adjustment targets. This is the rubric for §"Output of the test" — given a finding, this table says where to look.

| Delta symptom | Likely cause class | Target file / config | Adjustment style |
|---|---|---|---|
| Empty / malformed JSON from LLM | Prompt issue OR LLM response parsing | `cinema/prompts/*.txt`, `domain/llm/ensemble.py` parsers | Prompt rewrite OR add response-format constraint OR JSON-schema validator |
| Output present but semantically off-target | Prompt issue | `cinema/prompts/*.txt` | Prompt rewrite; add few-shot examples; tighten role/instruction language |
| Output present + semantically OK but wrong key | Schema drift | `domain/models.py`, `cinema/prompts/*.txt` | Either adapt parser OR change prompt to match schema |
| Latency >2× prediction | Model selection OR network | `config/settings.py`, `.env` | Swap to faster model; check pod / API endpoint latency |
| Cost >2× prediction | Token usage OR per-call pricing | Prompt length, `cost_tracker` pricing table | Shorten prompts; verify pricing entries; cap iterations |
| Image generation: low aesthetic quality | Sampling params OR prompt | sampler params in workflow JSON, prompt assembly logic | Adjust steps/cfg; rewrite image prompt assembly |
| Image generation: wrong subject (character mismatch) | IP-Adapter / LoRA / identity prompt | LoRA paths, IP-Adapter weights, character prompt section | Adjust adapter weights; verify LoRA paths; tighten character description |
| Video generation: stiff motion | Motion prompt OR engine selection | motion prompt assembly, engine routing table | Adjust motion strength keywords; try alternative engine |
| Video generation: temporal artifacts | Frame count / fps mismatch OR engine bug | engine config | Adjust fps; try alternative engine |
| Lip-sync: out of sync | Sync threshold OR audio drive | lip-sync params, audio normalization | Adjust threshold; verify audio sample rate; try alternative lip-sync model |
| Identity validation: false negative (real face rejected) | GhostFaceNet threshold too strict | identity gate config | Lower threshold; add retry-with-different-pose logic |
| Identity validation: false positive (wrong face accepted) | GhostFaceNet threshold too lenient | identity gate config | Raise threshold; add multi-frame validation |
| Assembly: BGM volume wrong | loudnorm targets | `phase_c_ffmpeg.py` loudnorm params | Adjust I/LRA/TP targets |
| Assembly: color grade off | color grade preset | `phase_c_ffmpeg.py` color params | Adjust color preset OR per-scene grade |
| Gate flow: stuck at gate | Gate predicate OR UI not updating | `cinema/review/controller.py` _gate_satisfied, frontend gate state | Check predicate logic; check SSE event emission |
| Surface A iterate: ignored | iterate plumbing OR feature flag | `cinema/iteration/`, `CINEMA_DIRECTORIAL_ITERATION` env | Verify flag; trace iterate endpoint to controller |
| Surface B screening: missing video | final_video_path missing OR SCREENING gate not firing | `cinema/screening.py`, assembly verification | Check assembly success; check SCREENING gate trigger |
| SSE: no progress events | SSE wiring OR `_progress_callback` not set | `web_server.py` SSE wiring, `cinema/lifecycle.py` `_progress_cb` | Check wiring; check ctor injection |
| Cost overrun: silent budget bypass | `cost_tracker` not enforcing | `domain/cost_tracker.py` budget enforcement | Add hard-stop on budget; surface budget violations |

---

## 7. Joint prep checklist (what each seat owns before execution)

### Director-seat owns

- [x] v0.1 brief skeleton (this commit)
- [ ] v1.0 brief with operator REPLY folded
- [ ] Predictive harness PREDICTION cells filled for each phase/prompt/param test cell (joint with operator; director leads on phase + prompt classes)
- [ ] Adjustment-pointing matrix refined per operator REPLY
- [ ] User-principal §"Open questions" surfaced + answered
- [ ] Cost / budget pre-calculation reviewed
- [ ] Post-test: findings report drafting (joint with operator); adjustment recommendations as `fix:` / `tune:` / `prompt:` commits

### Operator-seat owns (per role partition Sh)

- [ ] REPLY to this brief — add operational discipline (Lane V coverage, doc-sync, test isolation)
- [ ] Cold-context verification subagent dispatch during execution (per Lane V Rule #9)
- [ ] Per-phase verification command authorship (cold-context "what does success look like" for each test cell)
- [ ] Telemetry collection convention (how do we log cost / latency / failure modes consistently)
- [ ] Pytest-leakage discipline during execution (cycle-13 lesson; ensure no test fixtures created)
- [ ] Post-test: cold-context Lane V on the joint findings report (independent second opinion on ADJUSTMENT recommendations)

### User-principal owns (decisions in §9)

- [ ] Scope answer (Tier B+C only? Add D? Skip surface A/B?)
- [ ] Budget answer (cap on real-generation spend)
- [ ] Timeline answer (this cycle? multi-cycle? when?)
- [ ] RunPod pod restart authorization + execution
- [ ] Sample project decision (reuse existing? create fresh?)

---

## 8. Per-cell prediction protocol — strict format

When filling a cell's PREDICTION (joint prep), follow this discipline:

1. **Read the impl FIRST.** Check `cinema/...` for the function under test. Read the ARCHITECTURE.md section. Understand what SHOULD happen.
2. **Predict from the impl.** Don't predict from session memory or guess. Use the actual code to inform predictions. If impl is unclear, the prediction is "unclear because impl unclear" — log as INSIGHT-TARGET cell.
3. **Predict the failure modes.** What CAN go wrong? List top 3 by likelihood. Lock these in before execution.
4. **Predict the adjustment indicators.** If failure mode X happens, where does that point? (This is the adjustment-pointing matrix applied per-cell.)
5. **Commit the PREDICTION.** Use `chore(brief): fill PREDICTION for cell P-STYLE` or similar.
6. **DO NOT EDIT the PREDICTION after observing ACTUAL.** That defeats the falsifiability discipline. If you observe a surprise, the prediction was wrong — that's the signal to investigate (INSIGHT step), not to retcon the prediction.

**Per Rule #1 (ADR-013):** PREDICTION cells with quantitative claims (latency ranges, cost ranges) require justification (link to recent run logs, prior measurement, or canonical pricing). "Latency: 5-10 seconds" without basis is wishful thinking, not prediction.

---

## 9. Open questions for user-principal

### ANSWERED (v0.2, 2026-05-27)

1. **Scope: Tier B + C + D (comprehensive)** — full parameter sensitivity sweep included. Estimated $15-25 base + re-runs. Cap below.

2. **Budget cap: $50 USD hard ceiling.** `cost_tracker` enforces at pipeline level. Test budget is the AGGREGATE across all test cells + re-runs + Surface A iterate cycles. If cost approaches $40, STOP signal fires per §1 authority precedence.

3. **RunPod: fresh deploy via `scripts/setup_runpod.sh`.** Existing pod (`https://0f8wqszne2zby7-8188.proxy.runpod.net`) returning 403/404 since cycle-13 entry. Fresh deploy ~30 min including model downloads. New pod URL replaces `COMFYUI_SERVER_URL` in `.env`. **User-principal owns pod restart action** (RunPod console access + cost commitment).

4. **In-session direction: fill PREDICTIONs in advance.** Director starts filling phase + prompt cell PREDICTIONs at v0.2 (this commit); operator REPLY adds parameter + gate cell predictions + cold-context verification commands. Reduces total prep wall-clock vs sequential.

### STILL OPEN (await user-principal answer for v1.0)

5. **Timeline:** execute in cycle-14 (this cycle, after operator REPLY + pod deploy), or push to cycle-15+? Brief prep is on track to finish cycle-14; pod deploy + operator REPLY are the bottleneck.

6. **Sample project:** reuse an existing populated project (faster, free) or create fresh minimal project (slower, ~$3-7 cost, comprehensive)? Operator REPLY should re-audit `domain/projects/` post cycle-13 cleanup (2,170 stale fixtures removed); landscape may now favor reuse-of-existing.

7. **Surface A + B inclusion in Tier C:** include U7+U8 UX validation (IterationPanel + ScreeningStage + iterate-from-screening) in Tier C, or run as separate validation later? Including expands test cell count by ~3-5; closes cycle-13 deferred work.

8. **Adjustment commit discipline:** during execution, ship adjustment commits inline (each `tune:` / `prompt:` / `fix:` immediately) or batch into post-test fold? Inline = per-finding traceability + Lane V cadence per commit; batch = reduced commit noise + single post-test review pass.

9. **Joint execution model:** synchronous (both seats observe same execution in real time) or asynchronous (one seat executes; other reviews via verification report)? Synchronous = higher coordination overhead + catches surprises immediately; asynchronous = lower overhead + cleaner audit trail via mailbox events.

---

## 10. Risks + mitigations

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Pod returns 403/404 again mid-test | Medium | High (stops test) | Have fresh-deploy script ready as fallback |
| Budget overrun via LLM token usage | Medium | Medium | `cost_tracker` hard-stop; per-cell cost prediction reviewed pre-execution |
| Identity validator false-negatives reject good takes | Medium | Medium | Lower threshold for test session; flag as adjustment finding |
| Prompts produce semantically-wrong output but technically-valid JSON | High | Medium | Adjustment-pointing matrix has "semantically off-target" row; INSIGHT step catches |
| Predictions are too vague to be falsifiable | High | High | §8 prediction protocol enforces specificity; Rule #1 requires justification |
| Test execution discovers blockers that pause cycle-14 → cycle-15 carry-forward | Medium | Low | Findings report still valuable; partial-execution acceptable |
| ComfyUI custom node missing / version mismatch | Medium | High | Pre-flight A5 should catch (currently only HTTP check; operator REPLY adds workflow probe) |
| Real-gen output is good but predictions were "loose" — neither PASS nor MAJOR-DELTA | Medium | Low | Add tolerance bands to PREDICTION cells; document tolerance explicitly |
| Lane V cost during execution >>$2-5 budget | Low | Low | Lane V is metadata-only review of code commits, NOT real-gen runs — cost only matters if reviewer subagents are large |

---

## 11. Sign-off slots

### Director-seat sign-off (v0.1 draft)

[x] Structural skeleton ✓ (`<this commit SHA>`)
[ ] v1.0 fold of operator REPLY (pending operator REPLY)

### Operator-seat sign-off (REPLY pending)

[ ] Operational-discipline additions incorporated
[ ] Cold-context verification commands per cell drafted
[ ] Pytest-leakage discipline confirmed for execution
[ ] Counter-refinements OR consent per Rule #11 / v5 disagreement protocol

### User-principal sign-off (execution authorization pending)

[ ] §9 open questions answered
[ ] RunPod restart authorized
[ ] Budget cap stated
[ ] Execution timeline approved

---

*Comprehensive end-to-end test brief — DRAFT v0.1 by director-seat cycle 14 (2026-05-27). Awaits operator REPLY for v1.0 fold, then user-principal authorization for execution. Per CLAUDE.md role partition Sh + v5+ proposal-cycle precedent. Per Candidate #7 discipline: this brief is itself a new artifact NOT inheriting carry-forward claims; LoC counts and pipeline phase mapping verified at brief-write time against ARCHITECTURE.md + actual code at HEAD `c93e4b7` cycle-14 mid-cycle. **The brief will become a carry-forward starting at next handoff; whoever inherits it MUST re-verify the pre-flight checklist + scope assumptions per Candidate #7.***

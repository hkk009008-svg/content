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
- DRAFT v0.1 — director-seat structural skeleton + predictive harness framework + adjustment rubric framework
- AWAITING operator-seat REPLY with operational-discipline additions (Lane V coverage, doc-sync points, test isolation, telemetry collection)
- AWAITING user-principal decisions on §"Open questions" (scope, budget, timeline)
- NOT EXECUTABLE until §"Pre-flight checklist" all-green + operator REPLY landed + user §"Open questions" answered

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
| P-STYLE | STYLE rules generation | `generate_style_rules(project)` | B + C | $0.01-0.05 LLM | STUB |
| P-BGM | BGM generation | `_ensure_bgm(settings)` (FAL Stable Audio) | B + C | $0.10-0.30 | STUB |
| P-DECOMPOSE | Scene decomposition | `decompose` (competitive or single LLM) | B + C | $0.05-0.20 per scene | STUB |
| P-CHIEFDIR | ChiefDirector validation | post-decompose validation pass | B + C | $0.02-0.10 | STUB |
| P-KEYFRAME | Keyframe rendering | `KeyframeRenderPhase.run(ctx)` | B + C | $0.05-0.30 per shot (ComfyUI) | STUB |
| P-PERFORMANCE | Performance capture | `PerformanceCapturePhase.run(ctx)` | C | $0.10-0.50 per shot | STUB |
| P-MOTION | Motion rendering | `MotionRenderPhase.run(ctx)` | B + C | $0.30-1.00 per shot (Veo/LTX/Kling/...) | STUB |
| P-IDENTITY | Identity validation | GhostFaceNet at end-of-shot | C | $0 (local) | STUB |
| P-ASSEMBLY | Final assembly | `_assemble_final` (FFmpeg stitch + color + BGM mix + 2-pass loudnorm) | B + C | $0 (local) | STUB |

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
| PR-STORY | Story decomposition prompts | LLMEnsemble.decompose | B + C | STUB |
| PR-DIALOGUE | Dialogue generation prompts | LLMEnsemble.generate_dialogue | C | STUB |
| PR-CONTINUITY | Continuity engine prompts | ContinuityEngine.* | B + C | STUB |
| PR-STYLE-LLM | Style rules generation prompts | LLMEnsemble.generate_style_rules | B + C | STUB |
| PR-IMAGE | Per-shot image prompts | KeyframeRenderPhase prompt assembly | B + C | STUB |
| PR-MOTION | Per-shot motion prompts | MotionRenderPhase prompt assembly | B + C | STUB |
| PR-CHIEFDIR | ChiefDirector validation prompts | post-decompose validation | B + C | STUB |
| PR-AUDIO-VIBE | BGM vibe selection prompts | `_ensure_bgm` upstream | B + C | STUB |

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

These need answers before v1.0 ship + execution:

1. **Scope:** Tier B + C only ($3-7 estimated), Tier B + C + D ($15-25 estimated, parameter sensitivity sweep), or Tier B only ($1-2, plumbing verification only)?

2. **Budget cap:** what's the hard ceiling on real-generation spend across this test gauntlet? (cost_tracker enforces budget at pipeline level; test budget is separate concern from project budget)

3. **Timeline:** execute in cycle-14, or push to cycle-15+ when more substrate work backed up? (Brief prep can finish cycle-14; execution depends on pod + budget.)

4. **RunPod:** restart existing pod (`https://0f8wqszne2zby7-8188.proxy.runpod.net`) or deploy fresh per `scripts/setup_runpod.sh`? Fresh deploy is ~30 min including model downloads. Restart is ~5 min if pod is suspended-not-deleted.

5. **Sample project:** reuse an existing populated project (faster, free) or create fresh minimal project (slower, ~$3-7 cost, comprehensive)? Operator-validation-cycle-10 noted `domain/projects/` had pytest leakage masking populated projects; post-cycle-13 cleanup (2,170 stale fixtures removed) may have changed the landscape. Operator REPLY should re-audit.

6. **Surface A + B inclusion:** include U7+U8 UX validation in Tier C (default-on flag-flipped surfaces; cycle-13 deferred work), or run as separate validation later? Including expands test cell count by ~3 (IterationPanel, ScreeningStage, iterate-from-screening).

7. **Adjustment commit discipline:** during execution, ship adjustment commits inline (each `tune:` / `prompt:` immediately) or batch into post-test fold? Inline gives per-finding traceability; batch reduces commit noise.

8. **Joint execution model:** synchronous (both seats observe same execution in real time) or asynchronous (one seat executes; other reviews report)? Synchronous is higher coordination overhead but catches surprises immediately.

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

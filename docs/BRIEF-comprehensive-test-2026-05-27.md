# BRIEF — Comprehensive End-to-End Test Protocol with Predictive Harness

**Author (initial draft):** Director-seat (cycle 14, 2026-05-27)
**Co-author (pending):** Operator-seat (joint prep per user direction "both director and operator need to prepare … togather")
**For:** Both seats jointly, then user-principal sign-off, then joint execution
**Companion docs:**
- **[docs/EXTENSIVE-TEST-PLAN-2026-05-27.md](EXTENSIVE-TEST-PLAN-2026-05-27.md)** — **operator-authored COMPANION** (semantic split per cycle-14 mid-cycle escalation adjudication; see v0.4 status). Operator's testplan covers HOW (per-prompt P1-P14 enumeration with file:line refs; parameter directional predictions for ComfyUI/ffmpeg/env-vars; Lane C inventory of 61 routes + 35 UI components + 14 prompt sites). This brief covers WHAT/WHY (test cell framework + predictive harness format + adjustment-pointing matrix + tier sequencing + user-§9 decision tracking). **Cross-references go in both directions; both canonical for their respective scopes.**
- [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) §"Cycle 14 entry" — substrate state at brief-write time
- [docs/BRIEF-operator-validation-2026-05-26.md](BRIEF-operator-validation-2026-05-26.md) — cycle-10 Surface A/B validation template (structural reference, narrower scope)
- [ARCHITECTURE.md](../ARCHITECTURE.md) §4.1 `generate()` phase sequence (19 steps); §5 phase protocol; §7 story prep; §8 image; §9 video; §10 perf+lipsync; §11 identity; §12 audio; §13 LLM
- [docs/HANDOFF-director-transplant-2026-05-27-cycle13.md](HANDOFF-director-transplant-2026-05-27-cycle13.md) §"What's in flight" — RunPod pod state + U7/U8 carry-forward
- [docs/PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) §"N=1 candidates" — Candidate #7 discipline (re-verify before re-assert) applies throughout

**Cross-seat coordination escalation (cycle-14 mid-cycle, 2026-05-27 T08:35Z → director adjudication this commit):** Operator independently drafted `docs/EXTENSIVE-TEST-PLAN-2026-05-27.md` (~768 lines) cold because operator session started before this brief's `T05` dispatch-claim event entered STATE.md. Both seats were responding to identical user direction "both prepare TOGATHER." Per operator's escalation event (`fdd0094`), 4 consolidation options surfaced: (A) operator deletes draft; (B) keep both with semantic split + cross-refs; (C) operator's draft becomes appendix; (D) director-proposed hybrid. **Director-seat adjudicates: OPTION B — semantic split.** Both artifacts preserved with role-aligned scope per Sh: brief = strategic (WHAT/WHY/structure); operator's testplan = operational (HOW/per-prompt/per-parameter). See §"Cross-seat coordination" subsection in this brief's §1 + mirrored ESCALATION-RESOLVED header in operator's testplan (operator commits next).

**Status (at brief-write time, 2026-05-27 cycle-14 mid-cycle):**
- **DRAFT v0.8** — director-seat structural skeleton + predictive harness framework + adjustment rubric framework + user §9 decisions logged + **ALL 9 phase cell PREDICTIONs filled** (P-STYLE, P-BGM, P-DECOMPOSE, P-CHIEFDIR, P-KEYFRAME, P-PERFORMANCE, P-MOTION, P-IDENTITY, P-ASSEMBLY) + **ALL 8 prompt class cell PREDICTIONs filled** (PR-STORY, PR-IMAGE, PR-MOTION at v0.3 + PR-STYLE-LLM, PR-DIALOGUE, PR-CONTINUITY, PR-AUDIO-VIBE, PR-CHIEFDIR at v0.8 — director-doable last batch; cross-references operator's `docs/PR-cells-prestaging-2026-05-27-cycle15.md` substrate + testplan §5 P1-P14) + **operator REPLY folded** at `a9b1c32`: operational discipline §1.5, pre-flight A7+A8 refined + A9 ComfyUI workflow probe added, 22 cold-context verification commands §5.5, 2 adjustment-pointing matrix rows §6, operator sign-off ✅ §11, cell-ownership split per Sh codified §5 tables + Candidate #8 filed at `1af3528` (operator + director concurred) + **ALL 7 PA-* parameter cell PREDICTIONs filled** (PA-SAMPLING, PA-IMAGE, PA-VIDEO, PA-MOTION, PA-LIPSYNC, PA-IDENTITY, PA-AUDIO) by operator per Sh operational-default + REPLY Ask #2 responsibility split + **ALL 6 G-* gate cell PREDICTIONs filled** (G-PLAN, G-KEYFRAME, G-PERF, G-REVIEW, G-SCREEN, G-ITERATE) by director per Sh strategic-default at cycle-15 entry; cross-references ARCHITECTURE §6.1 gate predicates + §3.6 approve endpoints + cycle-9 Lane V #8 I1 bypass `_reject_if_project_busy_outside_gate`. **All 30 test cells now FILLED** (9 P + 6 G + 8 PR + 7 PA); brief is structurally ready for v1.0 ship pending user-§9 5-9 + pre-flight all-green.
- AWAITING: user-principal answers to §9 questions 5-9; pre-flight A1-A9 all-green (notably A5/A9 RunPod pod restart blocker); joint v0.9 mid-prep review per operator REPLY §2 hybrid protocol; then v1.0 ship + execution authorization
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

## 1.5 Operational discipline (folded from operator REPLY `a9b1c32` §"Ask #1")

### Lane V cadence — CC-1 COALESCED range-review per tier-end

Per-commit Lane V dispatch on 10-30 adjustment commits would cost
**2-9M cumulative tokens** vs v4.1 narrowing threshold (>1.5M).
**Operator REPLY recommends CC-1 coalesced range-review per Rule #9
§"Coalescing":**

- **Each tier completion triggers ONE Lane V dispatch on the range** —
  Tier A complete → Lane V on `<pre-Tier-A SHA>..<post-Tier-A SHA>`
  covering all Tier A artifact commits. Same for B, C, D.
- **CRITICAL findings within a tier trigger immediate per-commit Lane V
  on the offending commit** (no waiting for tier-end). Either-seat
  STOP signal per §1 authority precedence.
- **Cross-tier dispositions** (e.g., a Tier B finding affecting Tier C
  predictions) get a separate Lane V dispatch when surfaced.

**Verification reports:** one `verification-report` mailbox event per
tier-end + extras for CRITICAL escalations. Per Rule #9 §"Parallelism",
director-seat MAY ALSO dispatch independent reviewers on the same
range (parallel; operator's Lane V does NOT preempt director-seat's).

Empirical basis (cycle-6 S13 `029dbf9..2fb44d1` coalesced review caught
F1 CRITICAL that isolation review would have missed) — pattern
generalizes to tier-range reviews.

### Pytest-leakage discipline — `domain/projects/` count delta = 0

Per cycle-13 `6f8be5d` durable-fix lesson:

- **Pre-flight A8' addition:** record baseline count BEFORE execution
  (`ls domain/projects/ | wc -l > /tmp/projects-baseline.txt`)
- **Post-each-tier check (Lane V dispatch precondition):** diff
  baseline vs post-tier count; non-zero diff = test fixture created
  outside `tmp_projects_dir` → INVESTIGATE before next tier
- **Test execution uses operator-created sample project** (per §9 Q6);
  NO fixtures should be created during execution
- **Safety net:** `scripts/clean_test_fixtures.py` per cycle-13
  `540f126`; explicit count-delta enforcement catches non-pytest
  leakage paths

### Telemetry collection — per-cell artifact `docs/test-cells/<cell-id>-<UTC-ts>.md`

Each test cell generates one artifact during execution:

```
docs/test-cells/
├── P-STYLE-2026-05-2XTXX-XX-XXZ.md     # PREDICTION + ACTUAL + DELTA + INSIGHT + ADJUSTMENT
├── P-BGM-2026-05-2XTXX-XX-XXZ.md
├── ...
├── README.md                              # cumulative findings synthesis
```

**Artifact contents:** frontmatter (cell-id, tier, executor, wall-clock,
cost actual, success flag) + PREDICTION (verbatim from brief) + ACTUAL +
DELTA + INSIGHT + ADJUSTMENT + cross-references to related cells.

**Commit cadence:** one commit per cell-artifact during execution.
Subject form: `test(cell): <CELL-ID> <PASS|MINOR|MAJOR|FALSIFIED> — <summary>`.
Coalesced into Lane V range-review at tier-end.

**Rationale (vs in-place brief edits):** preserves PREDICTION
provenance (predictions don't move; locked-in once shipped); avoids
merge-conflict-prone in-place edits during joint execution; each cell
artifact independently grepable / linkable for post-test findings
synthesis; README.md cumulative synthesis becomes input to joint
findings report (`docs/REPORT-comprehensive-test-2026-05-2X.md`).

### Doc-sync triggers (Lane D)

Lane D triggers on execution-surfaced ARCHITECTURE.md divergences:

- Adjustment commits modifying `cinema/` / `domain/` / `web_server.py`
  / `cinema_pipeline.py` trigger Lane D per operator default
- Cells whose ACTUAL reveals undocumented capability/constraint → Lane D
  candidate (P-IDENTITY threshold range different from §11 → update §11;
  PA-VIDEO engine routing not in §9 → update §9)
- Lane D commits ride compound-commit-push discipline (B-003 Option E)
- Run §15 smoke before Lane D ships per ADR-013

**Out-of-scope for Lane D during execution:** ARCHITECTURE.md cleanup
unrelated to test findings.

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

# A7. Identity validator weights present (RESOLVED at operator REPLY `a9b1c32`)
ls -la ~/.deepface/weights/ghostfacenet_v1.h5 2>&1
# Expected: file exists, ~16-25MB. If missing, DeepFace auto-downloads on first
# DeepFace.represent(model_name="GhostFaceNet", ...) call — adds 5-15s warmup
# to first identity-validation call. To force download pre-execution:
.venv/bin/python -c "from deepface import DeepFace; DeepFace.build_model('GhostFaceNet'); print('GhostFaceNet model loaded OK')"
# Expected: prints "GhostFaceNet model loaded OK"; failure indicates DeepFace
# import error or network failure during weight download.
# Impl ref: identity/validator.py:347, 487, 546 — 3 DeepFace call sites.
# ARCHITECTURE §11: "GhostFaceNet via DeepFace (NOT ArcFace). Singleton via
# double-checked locking; 4 access paths converge."

# A8. Sample project ready (refined per operator REPLY `a9b1c32` §1.2 + Ask #4)
ls domain/projects/ | wc -l > /tmp/projects-baseline.txt
echo "Baseline project count: $(cat /tmp/projects-baseline.txt)"
# Decision: (a) reuse populated project from domain/projects/ (look for human-titled,
#  large project.json, non-empty scenes); or (b) create fresh minimal project via UI.
# Option (a) faster if available; option (b) costs ~$3-7 to create from scratch.
ls domain/projects/ | grep -v "^Test Project [a-f0-9]\{8\}$" | head -10
# Filter strategy: ignore pytest fixtures named "Test Project <8-hex>"; look for
# distinctive operator-created names. Post cycle-13 `6f8be5d` durable fix + `540f126`
# cleanup (2,170 stale fixtures removed), this list should be predominantly real
# projects. Operator REPLY: re-audit landscape post-cleanup; may favor reuse.

# A9. ComfyUI workflow probe (PROPOSED + ACCEPTED at operator REPLY `a9b1c32` Ask #4)
# Bare HTTP head check (A5) only proves pod is UP — does NOT verify custom nodes /
# model checkpoints / LoRA paths. A9 is deeper probe.
COMFYUI_URL="$COMFYUI_SERVER_URL"

# A9.1 — Object info contains required custom node classes
curl -sf "$COMFYUI_URL/object_info" --max-time 15 | jq -r 'keys[]' > /tmp/comfyui-nodes.txt
for node in "PuLIDFluxInsightFaceLoader" "PulidFluxModelLoader" "ApplyPulidFlux" "ControlNetApply" "IPAdapter" "VAELoader" "CheckpointLoaderSimple" "FluxGuidance"; do
  grep -q "$node" /tmp/comfyui-nodes.txt && echo "OK: $node" || echo "MISSING: $node"
done

# A9.2 — Model checkpoints loaded (via object_info introspection)
curl -sf "$COMFYUI_URL/object_info/CheckpointLoaderSimple" --max-time 10 | jq -r '.CheckpointLoaderSimple.input.required.ckpt_name[0][]' | head -20
# Expected: list of loaded checkpoint files; should include FLUX-1-dev or similar
# per pulid.json workflow's expected ckpt_name

# A9 is a Tier A pre-flight; runs once per pod restart. If A9 fails, A5 will succeed
# but Tier B/C will fail at first keyframe generation. Surface as pre-flight blocker.
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
| P-BGM | BGM generation | `_ensure_bgm(settings)` (FAL Stable Audio) | B + C | $0.10-0.30 | **FILLED v0.3** |
| P-DECOMPOSE | Scene decomposition | `decompose` (competitive or single LLM) | B + C | $0.05-0.20 per scene | **FILLED v0.3** |
| P-CHIEFDIR | ChiefDirector validation | post-decompose validation pass | B + C | $0.02-0.10 | **FILLED v0.3** |
| P-KEYFRAME | Keyframe rendering | `KeyframeRenderPhase.run(ctx)` | B + C | $0.05-0.30 per shot (ComfyUI) | **FILLED v0.2** |
| P-PERFORMANCE | Performance capture | `PerformanceCapturePhase.run(ctx)` | C | $0.10-0.50 per shot | **FILLED v0.3** |
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

#### Test cell P-BGM — Background music generation

**Phase / class:** Phase (step 4 in `generate()`; also called during assembly path at line 643/807)
**Stage in pipeline:** ARCHITECTURE §12 audio pipeline; impl at `cinema_pipeline.py:533-553 _ensure_bgm` → `generate_fal_bgm(music_mood, bgm_path, duration=47)` + optional `audio.music.master_music` mastering pass with `cinema_master` preset
**Test tier:** B + C
**Estimated cost:** $0.10-0.30 per generation (FAL Stable Audio pricing)
**Wall-clock prediction:** 30-90 seconds (FAL generation) + 5-15s mastering = 35-105s total

**PREDICTION (filled at v0.3 from `cinema_pipeline.py:533-553`, per §8 protocol):**

- **Expected output (shape):** mp3 file at `<temp_dir>/bgm_<music_mood>.mp3` (or `bgm_<music_mood>_mastered.mp3` after mastering). Returns `bgm_path: str` consumed by `_assemble_final`. Cached: existing file skips regeneration (`if not os.path.exists(bgm_path)`).
- **Expected content quality:** mp3 plays in standard player; duration exactly 47s (FAL hard-cap per call); music style matches `music_mood` setting (default "suspense"); mastering produces louder + more dynamic output vs raw generation (cinema_master preset target ~-14 LUFS for streaming). Non-empty audio (rejects silent-track failure mode).
- **Expected latency:** 30-90s FAL generation (model-dependent); 5-15s mastering. Cached path returns instantly (~10ms file-existence check).
- **Expected cost:** ~$0.10-0.30 per FAL generation. Mastering is local FFmpeg, $0. Re-runs hit cache (no additional cost). For a Tier B single-shot reel, BGM cost is one-time.
- **Expected failure modes (top 3):**
  1. **FAL API error / timeout** — quota / network / model load issue; `generate_fal_bgm` throws or returns failure; downstream `_assemble_final` operates without BGM (silent reel)
  2. **Mastering fails silently** — `audio.music.master_music` throws; caught at line 549 `except Exception` → logged as warning + raw BGM used. Degrades gracefully but may indicate broken mastering chain.
  3. **Music mood mismatched** — generated BGM doesn't match topic mood (e.g., topic "horror" produces uplifting BGM); LLM/Audio model interpretation gap.
- **Expected adjustment indicators:**
  - FAL error → check FAL key + quota; check FAL service status; add retry-with-backoff; consider local-fallback (e.g., Stable Audio Open self-hosted) for budget protection
  - Mastering silent fail → check `audio.music` module imports; verify `cinema_master` preset config; check FFmpeg-loudnorm compat; consider promoting WARNING to surfaced error if mastering is intended
  - Mood mismatch → tighten `music_mood` → FAL prompt mapping; add topic-conditioning (currently only uses raw mood string); consider LLM-pre-prompt-rewriting layer

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-CHIEFDIR — ChiefDirector shot validation

**Phase / class:** Phase sub-step (within step 5 decomposition flow, per-scene)
**Stage in pipeline:** ARCHITECTURE §7 + §13; impl at `cinema_pipeline.py:847-864` calling `self.director.validate_shot_prompts(shots, scene)` → returns `{"decision": "APPROVED" | "MODIFIED" | "REJECTED", "shots": [...], "violations": [...]}`. Director class at `llm/chief_director.ChiefDirector` (imported via `cinema/core.py:51`).
**Test tier:** B + C
**Estimated cost:** $0.02-0.10 per scene validation (single LLM call with shot-list context)
**Wall-clock prediction:** 3-10 seconds per validation pass

**PREDICTION (filled at v0.3 from `cinema_pipeline.py:847-864` + `cinema/core.py:51` ChiefDirector import, per §8 protocol):**

- **Expected output (shape):** dict with `decision: str` (APPROVED / MODIFIED / REJECTED); on MODIFIED, `shots: list[dict]` returns modified shots that REPLACE the original list (line 850); on REJECTED, list of violations + caller regenerates with single decomposer (line 864). On APPROVED, shots unchanged.
- **Expected content quality:** decisions reflect quality of decompose output. APPROVED expected ~60-80% of the time for well-formed prompts. MODIFIED indicates minor fixes (e.g., camera term standardization, slight reword for clarity). REJECTED is rare (<10%) and indicates structural issues (character coverage gap, scene-mood violation, prompt-policy violation).
- **Expected latency:** 3-10s LLM call. MODIFIED takes slightly longer because output is full modified shot list, not just decision.
- **Expected cost:** $0.02-0.10 per call; tokens scale with shot count (more shots = more output tokens).
- **Expected failure modes (top 3):**
  1. **Validator over-modifies** — MODIFIED rate >40% indicates decompose output is consistently weak OR validator is too aggressive; downstream variance in shot quality
  2. **REJECT-then-regenerate produces same issues** — single-decomposer fallback also produces shots violating constraints; regenerate-loop wastes tokens without improving quality
  3. **Silent quality drift** — APPROVED returned but shots are subtly off-target (validator missed issue); manifests as poor downstream KEYFRAME quality
- **Expected adjustment indicators:**
  - Over-modify → tune ChiefDirector validator strictness; review which modifications are systematic (could be folded into decompose prompt instead)
  - REJECT-then-regenerate same issues → strengthen single-decomposer prompt with examples of past REJECTs; add explicit "do not violate X" constraints; loop-detection (3+ REJECTs in row → escalate to user)
  - Silent quality drift → add more dimensions to ChiefDirector validation (currently only structural); add aesthetic-quality dimension via separate LLM judge

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell P-PERFORMANCE — Performance capture (driving performance retargeting)

**Phase / class:** Phase (step 12 in `generate()`)
**Stage in pipeline:** ARCHITECTURE §10 performance capture & lipsync; impl at `cinema/phases/performance.py PerformanceCapturePhase.run` (iterates shots) → `shot_generator.generate_performance_take(scene_id, shot_id)` (per-shot)
**Test tier:** C (skip for B; B has no character performance step)
**Estimated cost:** $0.10-0.50 per shot (model-dependent; LivePortrait / EMO / similar driving-video models)
**Wall-clock prediction:** 20-90 seconds per shot

**PREDICTION (filled at v0.3 from `cinema/phases/performance.py:35-89`, per §8 protocol):**

- **Expected output (shape):** `PhaseResult` with `ok: bool` + `message: str` ("performance: N new, M skipped, K failed") + `elapsed_s: float`. Per-shot, `generate_performance_take` returns `{"success": bool, "skipped": bool, "error": str}`. Skips: shot has approved performance OR `performance_engine == "SKIP"` OR no approved keyframe. Result persisted on shot.
- **Expected content quality:** performance video files exist for each non-SKIP non-approved shot with a keyframe; performance shows reasonable face/body movement; identity preserved (same character across frames; gates to P-IDENTITY downstream); audio drive shape matches scene audio. For a 3-shot scene with 2 character shots, expect 2 performance takes generated + 1 skip.
- **Expected latency:** 20-90s per shot. Phase total scales linearly: 5-shot reel × 60s = ~5 min worst case.
- **Expected cost:** $0.10-0.50 per shot depending on model. Tier C reel (3-5 shots) → $0.30-2.50 performance cost.
- **Expected failure modes (top 3):**
  1. **Driving model API error** (LivePortrait / EMO / similar provider returns 500; quota / model-not-loaded)
  2. **Identity drift in performance** (driven face loses character identity mid-clip; downstream P-IDENTITY catches; performance must be regenerated)
  3. **Performance lacks expression** (face is static / mouth doesn't sync to audio drive; lip-sync separate from performance capture but related quality concern)
- **Expected adjustment indicators:**
  - API error → check provider key + quota; route to alternative driving model (LivePortrait → EMO swap); add retry-with-backoff
  - Identity drift → use shorter clip-segments; reinforce IP-Adapter via per-frame conditioning; lower driving strength to preserve identity
  - Static / lack of expression → adjust driving audio amplitude (louder audio → more expressive lip movement); check audio sample rate compatibility with driving model; verify driving model's expressiveness config

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

> **All 9 phase cells FILLED at v0.3; all 7 parameter cells FILLED at v0.6; all 6 gate cells FILLED at v0.7.** Remaining: 5 prompt class cells (PR-DIALOGUE, PR-CONTINUITY, PR-STYLE-LLM (partial), PR-CHIEFDIR, PR-AUDIO-VIBE) — director-doable; testplan §5 P1-P14 cross-references. All cells must be filled before v1.0 ship + execution.

### 5.2 Gate test cells (C only)

| ID | Gate | What it validates | Tier | Status |
|---|---|---|---|---|
| G-PLAN | GATE 1 PLAN_REVIEW @ 25% | Plans approved before keyframe | C | **FILLED v0.7** |
| G-KEYFRAME | GATE 2 KEYFRAME_REVIEW @ 55% | Keyframes approved before performance | C | **FILLED v0.7** |
| G-PERF | GATE 3 PERFORMANCE_REVIEW @ 65% | Performance approved (or SKIP-bypassed) before motion | C | **FILLED v0.7** |
| G-REVIEW | GATE 4 REVIEW @ 82% | Reviews approved before assembly | C | **FILLED v0.7** |
| G-SCREEN | SCREENING @ post-assembly | User approves final reel before re-assembly | C | **FILLED v0.7** |
| G-ITERATE | Surface A iterate-from-gate | `regenerate_with_intent` flow at any gate | C | **FILLED v0.7** |

> **All 6 gate cells now FILLED at v0.7 (this commit).** Cross-references ARCHITECTURE §6 (predicate-poll mechanism) + §6.1 (`_gate_satisfied` predicates at `cinema/review/controller.py:214-237`) + §3.6 (approve endpoints) + §7.7.2 (auto-approve `CINEMA_AUTO_APPROVE_MOTION` opt-in) + cycle-9 Lane V #8 I1 fix at `9e9b008` (`_reject_if_project_busy_outside_gate` enables iterate-during-gate bypass for all 5 gates). Companion gate-state inspection commands per cell are at §5.5 "Gate cells (G-*) — operates on project.json state transitions."

#### Test cell G-PLAN — GATE 1 PLAN_REVIEW @ 25%

**Phase / class:** Gate (between step 5 decompose and step 8 keyframe; worker waits at `cinema_pipeline.py:870`)
**Stage in pipeline:** ARCHITECTURE §6 predicate-poll + §6.1 PLAN_REVIEW predicate at `cinema/review/controller.py:219-220`; approve endpoint per ARCHITECTURE §3.6 at `web_server.py:1568 api_approve_shot_plan`
**Test tier:** C only (Tier C is full reel — Tier B single-shot does not exercise multi-shot gate semantics meaningfully)
**Estimated cost:** $0 (pure operator action; no LLM/API calls unless auto-approve rules invoke validators)
**Wall-clock prediction:** depends on operator pace; ~5-30 seconds per shot to review + approve a plan; gate-resume detection ≤500ms after last approval (`lifecycle.wait_for_gate` poll interval per ARCHITECTURE §6)

**PREDICTION (filled at v0.7 from impl-read at `cinema/review/controller.py:214-220`, `cinema_pipeline.py:870`, `web_server.py:1568`, ARCHITECTURE §6.1, per §8 protocol):**

- **Expected behavior (shape):** Worker reaches step "PLAN_REVIEW @ 25%", invokes `_run_auto_approve_pass("PLAN_REVIEW")` (audit key `"plan"`) which appends decisions to `shot["auto_approve_audit"]` for each shot; non-auto-approved shots block on operator review. Operator POSTs `/api/projects/<pid>/shots/<sid>/plan/approve` per shot; each call mutates `shot["plan_status"] = "approved"` via `pipeline.approve_shot_plan(sid, approved=True)`. Worker's 500ms-poll predicate `all(shot.get("plan_status") == "approved" for shot in shots)` returns True after the LAST shot approves; worker resumes into keyframe render. Reject path: `/plan/reject` sets `plan_status != "approved"`; predicate remains False.
- **Expected content quality:** `project.json` shows every shot's `plan_status == "approved"` post-gate; `auto_approve_audit` array non-empty for each shot regardless of auto/manual outcome (audit is the persistence layer per Session 13 brief). For a 3-5-shot Tier C reel: ~3-5 audit entries with `decision.auto_approved` mixed True/False depending on rule fit. Iterate-during-gate calls to `/iterate` succeed (Lane V #8 I1 bypass).
- **Expected latency (gate-open detection):** ≤500ms from last approve POST to worker resume — bounded by `wait_for_gate` poll interval at `cinema/lifecycle.py:172-188`. Network/server latency adds a few ms.
- **Expected cost:** $0 unless auto-approve rules invoke vision validators (plan gate currently has no vision check; pure text/structure validation). LLM cost upstream (decompose) already accounted for in P-DECOMPOSE.
- **Expected failure modes (top 3):**
  1. **Stale-state read** — operator approves last shot but predicate evaluates against pre-write snapshot (mutate_project + refresh-snapshot interaction; `_refresh_project_snapshot` race with the writing thread). Symptom: worker stays at 25% past expected unblock window.
  2. **Reject doesn't propagate** — `/plan/reject` returns 200 but `plan_status` field write missed; predicate still satisfies → premature unblock.
  3. **Auto-approve over-eager** — `CINEMA_AUTO_APPROVE_PLAN` (or rules) silently approves shot that operator would have rejected; audit log records decision but operator never sees the gate (no user-facing "pending" UI for auto-approved shots).
- **Expected adjustment indicators:**
  - Stale-state read → trace `mutate_project` → disk-write fsync → `_refresh_project_snapshot` chain; verify gate predicate reads fresh snapshot per poll, not cached `self.project`
  - Reject doesn't propagate → grep `web_server.py` for `api_reject_shot_plan` (or equivalent); verify it negates `plan_status`; cross-check round-trip via §5.5 G-PLAN jq inspection command
  - Auto-approve over-eager → tighten `auto_approve_rules` for plan stage; verify `/api/projects/<pid>/shots/<sid>/reject-auto-approve` override path works (`web_server.py:1780`); confirm UI surfaces auto-approved shots for optional human review

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell G-KEYFRAME — GATE 2 KEYFRAME_REVIEW @ 55%

**Phase / class:** Gate (between step 8 keyframe render and step ~12 performance capture; worker waits at `cinema_pipeline.py:910`)
**Stage in pipeline:** ARCHITECTURE §6.1 KEYFRAME_REVIEW predicate at `cinema/review/controller.py:221-222`; approve endpoint per ARCHITECTURE §3.6 at `web_server.py:1618 api_approve_keyframe_take`; per-take alternates per ARCHITECTURE §6.2 (`keyframe_takes[]` array; approval is pointer-set, array immutable)
**Test tier:** C only
**Estimated cost:** $0 directly; auto-approve rules invoke identity-validator (P-IDENTITY) which has already been costed in keyframe phase
**Wall-clock prediction:** ~10-60 seconds per shot to review (visual inspection + approve); gate-resume ≤500ms

**PREDICTION (filled at v0.7 from impl-read at `cinema/review/controller.py:221-222`, `cinema_pipeline.py:910`, `web_server.py:1618`, ARCHITECTURE §6.2, per §8 protocol):**

- **Expected behavior (shape):** Worker reaches "KEYFRAME_REVIEW @ 55%", runs `_run_auto_approve_pass("KEYFRAME_REVIEW")` (audit key `"image"`). Auto-approve rules can include identity-score thresholds + visual-quality gates; passing shots get `approved_keyframe_take_id` set + audit entry. Operator approves remaining shots via `/keyframes/<take_id>/approve` → `approve_take(sid, take_id, "keyframe")` sets `shot["approved_keyframe_take_id"] = take_id`. Multiple alternates per shot live in `keyframe_takes[]`; approval picks one pointer. Predicate `all(shot.get("approved_keyframe_take_id") for shot in shots)` returns True after last shot's approval.
- **Expected content quality:** Every shot has exactly one `approved_keyframe_take_id` pointing to an entry in `keyframe_takes[]`; the take file exists on disk at the path stored in the take entry; identity validation (P-IDENTITY) passed for the approved take (or operator explicitly accepted a borderline score). Audit log records every alternate that was generated, with the final selection's `auto_approved` field and any `vetoes`.
- **Expected latency:** Same 500ms-bounded poll. UI alternates-rendering may add ~1-2s if N=8 max-tier alternates per shot need thumbnail render.
- **Expected cost:** $0 for the gate itself. Auto-approve identity check uses already-computed GhostFaceNet score from generation (no fresh inference).
- **Expected failure modes (top 3):**
  1. **Bogus take_id approved** — operator UI passes a `take_id` not in `keyframe_takes[]`; `approve_take` silently succeeds OR errors. Symptom: `approved_keyframe_take_id` points to nonexistent take; downstream phase fails at file lookup.
  2. **Alternate mis-selection** — UI shows 8 alternates with validator scores; operator approves the wrong one (e.g., highest score is identity-correct but wrong composition); audit captures the choice but downstream identity gate (P-IDENTITY) misframes the issue.
  3. **Auto-approve at borderline threshold** — identity score 0.71 vs threshold 0.70 silently passes; visually-poor take advances; downstream motion (P-MOTION) inherits the bad keyframe → cascading drift.
- **Expected adjustment indicators:**
  - Bogus take_id → tighten `_find_take` strictness; reject if `take_id` not in `keyframe_takes[]`; return 404 with explicit "take_id not in this shot's keyframe alternates"
  - Alternate mis-selection → UI should display validator score + composition preview side-by-side; expose `auto_approve_audit` for the discarded alternates as decision-context
  - Borderline auto-approve → tighten threshold OR add "borderline zone" requiring explicit human OK; track `IDENTITY_THRESHOLD - 0.05` band as manual-only; verify `auto_approve_audit` exposes the score

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell G-PERF — GATE 3 PERFORMANCE_REVIEW @ 65%

**Phase / class:** Gate (between performance capture and step 15 motion render; worker waits at `cinema_pipeline.py:951-955`)
**Stage in pipeline:** ARCHITECTURE §6.1 PERFORMANCE_REVIEW predicate (three-paths-satisfied) at `cinema/review/controller.py:223-234`; approve endpoint per ARCHITECTURE §3.6 at `web_server.py:1629 api_approve_performance_take`; `all_skipped` short-circuit at `cinema_pipeline.py:767-788` (redundant per ARCHITECTURE §6.1 note but preserved for explicit `PERFORMANCE_SKIPPED_GATE` UX event); auto-approve gated behind `CINEMA_AUTO_APPROVE_MOTION` opt-in per ARCHITECTURE §7.7.2 + ADR-014
**Test tier:** C only
**Estimated cost:** $0 for gate; performance capture upstream already costed in P-PERFORMANCE
**Wall-clock prediction:** ~30-90 seconds per shot to review performance video (must watch ~3-8s clip); gate-resume ≤500ms

**PREDICTION (filled at v0.7 from impl-read at `cinema/review/controller.py:223-234`, `cinema_pipeline.py:951-955`, `cinema_pipeline.py:767-788`, ARCHITECTURE §6.1, per §8 protocol):**

- **Expected behavior (shape):** Worker reaches "PERFORMANCE_REVIEW @ 65%". Three-paths-satisfied predicate: a shot is satisfied iff (a) `performance_engine == "SKIP"` (no performance needed), OR (b) no `approved_keyframe_take_id` (broken chain — predicate skips it since downstream can't proceed anyway), OR (c) `approved_performance_take_id` is set. Default test reel: most shots route to live actors / driving-video / SKIP per `performance/_router.dispatch()` (ARCHITECTURE §10.1); SKIP-routed shots auto-satisfy without operator action; non-SKIP shots require explicit approval. With `CINEMA_AUTO_APPROVE_MOTION=1`, the opt-in helper at `cinema/auto_approve.py:472` runs against motion takes; otherwise default-off per ADR-014.
- **Expected content quality:** Post-gate, every shot satisfies at least one of the three paths. For mixed reel (some SKIP, some live-perf): `auto_approve_audit` entries exist for non-SKIP shots; SKIP shots may or may not have audit entry depending on whether helper runs at all. Approved performance take video file exists on disk; visual identity matches keyframe (perf-to-keyframe coherence, separate from cross-frame identity drift in P-MOTION).
- **Expected latency:** 500ms-bounded as above. The orchestrator's `all_skipped` shortcut at `cinema_pipeline.py:767-788` emits `PERFORMANCE_SKIPPED_GATE` event instantly when ALL shots route to SKIP (no operator action needed); this is a UX optimization, redundant with the predicate's path-(a).
- **Expected cost:** $0 for gate.
- **Expected failure modes (top 3):**
  1. **SKIP shot still blocks gate** — `performance_engine` field has stray whitespace OR mixed-case ("skip", "Skip") that survives `(performance_engine or "").upper() == "SKIP"` literal compare. Symptom: pure-SKIP reel doesn't fast-forward; operator confused why gate is paused with no approvable takes.
  2. **Mixed-reel premature unblock** — 3 SKIP + 1 needs-perf, predicate returns True somehow despite path-(c) unsatisfied on the 1; motion phase pre-runs on un-approved shot. Suggests predicate `all()` semantics broken OR shot mutation race.
  3. **`CINEMA_AUTO_APPROVE_MOTION=1` rules over-permissive** — every performance take auto-approves regardless of quality; operator's gate-blocking review never happens; bad performances inherited downstream.
- **Expected adjustment indicators:**
  - SKIP still blocks → re-grep predicate; verify `.upper()` normalization; check field-write path for `performance_engine` value; verify `cinema/performance/_router.dispatch` writes canonical uppercase `"SKIP"`
  - Premature unblock → re-verify predicate at `controller.py:229-234`; add diagnostic logging at predicate evaluation; verify `_all_shots` returns ALL shots (not a stale subset)
  - Auto-approve over-permissive → unset `CINEMA_AUTO_APPROVE_MOTION` (revert to default-off per ADR-014); tighten motion auto-approve rules; verify audit log captures per-shot decision; expose `/reject-auto-approve` UI path (`web_server.py:1778`)

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell G-REVIEW — GATE 4 REVIEW @ 82%

**Phase / class:** Gate (between motion render and step 19 assembly; worker waits at `cinema_pipeline.py:990`)
**Stage in pipeline:** ARCHITECTURE §6.1 REVIEW predicate at `cinema/review/controller.py:235-236`; approve endpoint per ARCHITECTURE §3.6 at `web_server.py:1666 api_approve_final_take`; postprocess-variant chain-walk per ARCHITECTURE §6.2 (`source_take_id` chain → sets BOTH `approved_motion_take_id` AND `approved_final_take_id`)
**Test tier:** C only
**Estimated cost:** $0 for gate; postprocess variants (color grade / re-grade) costed upstream if invoked
**Wall-clock prediction:** ~60-120 seconds per shot (must watch full clip with audio + assess color/grading); gate-resume ≤500ms

**PREDICTION (filled at v0.7 from impl-read at `cinema/review/controller.py:235-236`, `cinema_pipeline.py:990`, `web_server.py:1666`, ARCHITECTURE §6.2, per §8 protocol):**

- **Expected behavior (shape):** Worker reaches "REVIEW @ 82%", runs `_run_auto_approve_pass("REVIEW")` (audit key `"final"`). Operator approves via `/final/<take_id>/approve` → `approve_take(sid, take_id, "final")`. Critical mechanic: if `take_id` refers to a postprocess variant (e.g., color-graded version), `approve_take` walks `source_take_id` chain to find the underlying `motion_take` AND sets BOTH `approved_motion_take_id` + `approved_final_take_id`. Predicate `all(shot.get("approved_final_take_id") for shot in shots)` returns True after last approval; worker proceeds to assembly.
- **Expected content quality:** Every shot has exactly one `approved_final_take_id` AND one `approved_motion_take_id` (chain-walk invariant). Both pointers resolve to files that exist on disk; assembly's `_build_scene_packages` returns empty `missing_shots`. Postprocess variants when present have intact `source_take_id` lineage. Auto-approve audit covers every shot.
- **Expected latency:** 500ms-bounded.
- **Expected cost:** $0.
- **Expected failure modes (top 3):**
  1. **Broken chain** — operator approves postprocess variant whose `source_take_id` doesn't resolve (variant lineage corrupt); `approved_final_take_id` set but `approved_motion_take_id` unchanged → assembly fails with "missing motion take for shot X".
  2. **Take-file missing at approval time** — operator approves a take, but cleanup OR a race deletes the file before assembly reads it; assembly's `missing_shots` non-empty; abort.
  3. **Concurrent approval + motion-regen race** — operator approves while a stray motion regenerate is mid-flight on same shot; `_project_lock_guard` should serialize but lock acquisition order matters. Symptom: approved_take points to obsolete file path.
- **Expected adjustment indicators:**
  - Broken chain → trace `_walk_source_chain` (or `_find_take` chain logic at `cinema/review/controller.py`); add explicit lineage check at variant create time; fail-fast at approval if chain broken
  - Missing file at assembly → verify `approve_take` checks file existence pre-mutation; OR rely on assembly's `missing_shots` check + clearer error surfacing
  - Concurrent race → confirm `_project_lock_guard` decorator on `api_approve_final_take` (`web_server.py:1666`); verify lock scope covers full chain-walk + mutation; cross-check no motion regen endpoint bypasses the same lock

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell G-SCREEN — SCREENING @ post-assembly

**Phase / class:** Gate (post-step-19 assembly, pre-cleanup; worker waits at `cinema_pipeline.py:710-712`)
**Stage in pipeline:** ARCHITECTURE §7.7.3 Class B opt-out flag `CINEMA_SCREENING_STAGE` (default ON post-flag-flip `44f6beb` 2026-05-26); predicate `is_screening_approved(project)` reads `project["screening_approved"] == True` per `cinema/screening.py`; approve endpoint at `web_server.py:2202 /api/projects/<pid>/screening/approve` → `mark_screening_approved(pid)` → `mutate_project(pid, p.update(screening_approved=True))`; re-assemble path at `/api/projects/<pid>/assemble/re-assemble` (requires `needs_reassembly` non-empty); Lane V #8 I1 (`9e9b008`) gates `/screening/approve` to reject when `needs_reassembly` non-empty
**Test tier:** C only
**Estimated cost:** $0 for gate; re-assemble path (if invoked) re-runs assembly (P-ASSEMBLY scope)
**Wall-clock prediction:** ~3-10 minutes for operator to watch full final reel + decide approve vs request changes; gate-resume ≤500ms after approval POST

**PREDICTION (filled at v0.7 from impl-read at `cinema_pipeline.py:697-717`, `web_server.py:2202-2260`, ARCHITECTURE §7.7.3, cycle-9 Lane V #8 I1 fix `9e9b008`, per §8 protocol):**

- **Expected behavior (shape):** Final assembly completes (step 19); worker enters SCREENING stage at 95% progress; emits `current_stage = SCREENING_STAGE_NAME` + `progress("Awaiting operator screening approval...", 95)`. Operator reviews `final_cinema.mp4`; either (a) approves via `POST /screening/approve` → flag persists to disk → predicate poll returns True → worker resumes into cleanup + COMPLETE at 100%, OR (b) marks shots needing re-do → `needs_reassembly` populated → operator iterates on flagged shots (G-ITERATE) → re-assembles via `POST /assemble/re-assemble`. Iterate-during-screening reachable per Lane V #8 I1 bypass.
- **Expected content quality:** Post-approve: `project.json` shows `screening_approved == True`; `needs_reassembly` is empty (Lane V #8 I1 precondition enforced — approval rejected with explicit error if `needs_reassembly` non-empty). Cleanup runs (`cleanup_project` invoked at `cinema_pipeline.py:721`); temp files removed; `progress("COMPLETE", final_path, 100)` emitted; SSE stream surfaces COMPLETE event.
- **Expected latency:** Operator-bound (3-10 min depending on reel length and review depth). Worker's 500ms-poll detects flag flip promptly.
- **Expected cost:** $0 for gate; re-assemble path repeats P-ASSEMBLY costs (~$0 since pure FFmpeg).
- **Expected failure modes (top 3):**
  1. **Stale snapshot in predicate** — `mark_screening_approved` writes via `mutate_project` but `_refresh_project_snapshot` reads pre-write cache; worker keeps polling indefinitely. Symptom: UI shows approve POST returned 200 but progress stays at 95%.
  2. **`CINEMA_SCREENING_STAGE=0` opt-out + stale UI** — operator sees pre-flag-flip UI that omits screening stage; approve POST hits endpoint but worker has already cleaned up + COMPLETED (pipeline skipped screening per flag-off); flag-write is benign no-op.
  3. **Premature approve with `needs_reassembly` non-empty** — historical CRITICAL pre-`9e9b008`; operator approved screening despite pending re-do; permanent flag flip lost the re-assemble path. Fix in cycle-9: `/screening/approve` rejects with 409 + explicit message when `needs_reassembly` is non-empty.
- **Expected adjustment indicators:**
  - Stale snapshot → verify `_refresh_project_snapshot` in `_screening_predicate` (`cinema_pipeline.py:707`) actually re-reads disk; cross-check with §5.5 G-SCREEN jq inspection of `screening_approved` flag
  - Opt-out + stale UI → benign (idempotent); document for operator; consider `/api/feature-flags` endpoint exposing `CINEMA_SCREENING_STAGE` state so UI can feature-detect
  - Premature approve regression → grep `web_server.py` for the `needs_reassembly` non-empty check in `api_screening_approve` (post-`9e9b008` line range; verify at audit time per Rule #1); confirm 409 response with operator-actionable error message; add regression test covering "approve-with-pending-redo rejects" if not already present

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell G-ITERATE — Surface A iterate-from-gate

**Phase / class:** Endpoint (operator-invokable at ANY of 5 gate waits: PLAN/KEYFRAME/PERFORMANCE/REVIEW/SCREENING)
**Stage in pipeline:** ARCHITECTURE §7.7.3 Class B opt-out flag `CINEMA_DIRECTORIAL_ITERATION` (default ON post-flag-flip `44f6beb` 2026-05-26); endpoint at `web_server.py:1677 api_iterate_take` → `ShotController.regenerate_with_intent(scene_id, shot_id, take_id, DirectorialIntent, project_id=pid)`; gate-aware bypass `_reject_if_project_busy_outside_gate(pid)` per cycle-9 Lane V #8 I1 fix `9e9b008`; accept-both flat/nested body per F1 decision 2026-05-25
**Test tier:** C only (multi-shot reel needed to exercise multiple iterate-from-gate surfaces)
**Estimated cost:** $0.05-1.00 per iterate (varies by `target_stage`: keyframe ~$0.05-0.30; performance variable; motion ~$0.30-1.00 — engine-routed per shot's `target_api`)
**Wall-clock prediction:** ~15-60s per keyframe iterate; ~30-180s per motion iterate; gate-resume after iterate + operator re-approve ≤500ms

**PREDICTION (filled at v0.7 from impl-read at `web_server.py:1677-1775`, `cinema/shots/controller.py regenerate_with_intent`, cycle-9 Lane V #8 I1 fix `9e9b008`, ARCHITECTURE §7.7.3 Class B, per §8 protocol):**

- **Expected behavior (shape):** Operator POSTs `/api/projects/<pid>/shots/<sid>/<take_id>/iterate` with body `{prose, verb?, params?, refs?, target_stage}` (flat) OR `{intent: {...}}` (nested; both accepted, nested wins on ambiguity per G1 precedence). Endpoint validates: (1) `CINEMA_DIRECTORIAL_ITERATION` enabled (else 404), (2) `_reject_if_project_busy_outside_gate(pid)` passes (allows during any gate wait; rejects during active phase work with 423), (3) JSON body parses + `DirectorialIntent.model_validate` succeeds (else 400), (4) shot exists in project (else 404). On success: invokes `regenerate_with_intent` which creates a new take entry under the appropriate collection (keyframe_takes / motion_takes / postprocess_variants) based on `target_stage`; returns 200 + `{success: true, take: {...}}`. Operator's previously-approved-take pointer remains until they explicitly re-approve the new take.
- **Expected content quality:** New take entry has unique ID; appears in shot's relevant array; file exists at take path; `auto_approve_audit` may capture validator score on the new take. Old `approved_*_take_id` pointers unchanged until operator re-approves. Iterate-during-PLAN_REVIEW works (prose may target plan-stage); iterate-during-KEYFRAME/PERFORMANCE/REVIEW/SCREENING works per target_stage.
- **Expected latency:** depends on `target_stage` — keyframe iterate ~15-60s (LLM prompt rewrite + image gen); motion iterate ~30-180s (engine-routed video gen); performance iterate variable (driver-video re-route is cheap; live re-record is wall-clock-bound by operator). Cost dominates on motion (Veo if routed there).
- **Expected cost:** Per-iterate. Operator-pacing-bound; cumulative cost across multiple iterates can push toward §9 $50 cap if uncontrolled.
- **Expected failure modes (top 3):**
  1. **Iterate during ACTIVE phase not rejected** — `_reject_if_project_busy_outside_gate` returns None when a phase is running (not gate-waiting); endpoint proceeds; concurrent regenerate races with active phase; corrupted state. Symptom: spurious 500s OR silent data corruption.
  2. **Target-stage mismatch** — operator iterates with `target_stage="motion"` but shot is still at PLAN_REVIEW (no keyframe yet); `regenerate_with_intent` may create motion take on non-existent base; downstream phases fail.
  3. **Opt-out flag UI leak** — `CINEMA_DIRECTORIAL_ITERATION=0` set; endpoint returns 404 but UI still surfaces "Iterate" button on review stages → operator confused; or worse, frontend tries to call non-existent endpoint and reports a generic network error.
- **Expected adjustment indicators:**
  - Active-phase iterate not rejected → re-grep `_reject_if_project_busy_outside_gate` impl; verify it checks BOTH `_running_pipelines` membership AND current stage; add explicit "not at a gate" path returning 423; trace cycle-9 Lane V #8 I1 fix at `9e9b008` for the regression guard
  - Target_stage mismatch → tighten `regenerate_with_intent` precondition: assert prior-stage take exists for the requested `target_stage` (e.g., motion iterate requires `approved_keyframe_take_id`); reject 409 with explicit message
  - Opt-out UI leak → verify frontend feature-detects `CINEMA_DIRECTORIAL_ITERATION` (probe via `/api/feature-flags` if it exists; else hard-code based on a build-time inject); audit all 5 gate UIs (PlanReviewStage.tsx, KeyframeReviewStage.tsx, PerformanceReviewStage.tsx, ReviewStage.tsx, ScreeningStage.tsx) to confirm iterate-UI hidden when flag-off

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

### 5.3 Prompt class test cells (B + C)

| ID | Prompt class | Where invoked | Tier | Status |
|---|---|---|---|---|
| PR-STORY | Story decomposition prompts | LLMEnsemble.decompose | B + C | **FILLED v0.3** |
| PR-DIALOGUE | Dialogue generation prompts | `domain/dialogue_writer.py:60 system_prompt` | C | **FILLED v0.8** |
| PR-CONTINUITY | Continuity engine prompts | `domain/continuity_engine.py:446 enhance_shot_prompt` | B + C | **FILLED v0.8** |
| PR-STYLE-LLM | Style rules generation prompts | `llm/style_director.py:62 system_prompt` | B + C | **FILLED v0.8** (distinct angle from P-STYLE: input-side prompt construction vs output JSON validation) |
| PR-IMAGE | Per-shot image prompts | KeyframeRenderPhase prompt assembly | B + C | **FILLED v0.3** |
| PR-MOTION | Per-shot motion prompts | MotionRenderPhase prompt assembly | B + C | **FILLED v0.3** |
| PR-CHIEFDIR | ChiefDirector validation prompts | `llm/chief_director.py:130-206` + `:208 validate_shot_prompts` + `:276 evaluate_generation_quality` (diagnosis) | B + C | **FILLED v0.8** (dual-source P2 + P3) |
| PR-AUDIO-VIBE | BGM vibe selection prompts | `audio/music.py:88 _build_music_prompt` | B + C | **FILLED v0.8** |

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

#### Test cell PR-STYLE-LLM — Style rules generation prompts

**Phase / class:** Prompt class (cross-cuts P-STYLE phase; INPUT side of the LLM call — JSON-shape elicitation, distinct from P-STYLE's OUTPUT validation focus)
**Stage in pipeline:** ARCHITECTURE §7.1 style stage; impl at `llm/style_director.py:62 system_prompt` (cinematographer + production-designer persona); tools-appended assembly at line 95 (`system_with_tools = system_prompt + """`) → line 107 (`system_prompt=system_with_tools`) consumed by LLM call
**Test tier:** B + C
**Estimated cost:** $0 — prompt observation intrinsic to P-STYLE; this cell is a focused angle on prompt construction, not a separate LLM call
**Wall-clock prediction:** N/A — reuses P-STYLE observation

**PREDICTION (filled at v0.8 from impl-read at `llm/style_director.py:62`, operator pre-staging substrate at `docs/PR-cells-prestaging-2026-05-27-cycle15.md` §"PR-STYLE-LLM", per §8 protocol):**

- **Expected output (shape):** 6-key JSON elicited by the cinematographer/production-designer persona — `color_palette` / `camera_style` / `lighting` / `production_design` / `mood` / `sound_design_rules`. Output schema enforced via tools-appended format. P-STYLE observes the JSON output; this cell observes the prompt that produces it.
- **Expected content quality:** named-color palette (concrete: "burnt sienna and ochre at sunset" not abstract "warm tones"); specific camera/lens class (e.g., "anamorphic 2.39:1, soft falloff"); concrete lighting setups (e.g., "single-source practicals + sodium-vapor wash"); production-design specificity (era-appropriate props, period-correct materials); `sound_design_rules` non-generic. If user_prompt includes topic/genre context, expect topic-aligned rules; else generic-cinematic baseline.
- **Expected failure modes (top 3):**
  1. **Generic palette** — output uses abstract color words ("warm", "cool", "neutral") instead of named pigments. Root: persona doesn't enforce concrete-noun preference.
  2. **`sound_design_rules` generic** — cinematographer persona may de-prioritize audio specificity; output reads like a template (e.g., "diegetic sound, sparse score, atmospheric effects").
  3. **Topic-context absence** — `user_prompt` template may not pass genre/scene context; LLM produces topic-agnostic boilerplate.
- **Expected adjustment indicators:**
  - Generic palette → add explicit "be specific about color palette (named pigments/colors only; no abstract color descriptors)" instruction at end of system_prompt; few-shot examples with concrete palettes
  - Sound generic → expand persona to "cinematographer AND sound designer"; add 1-2 sentences requiring audio-specific vocab (diegesis, source-position, score-instrumentation); audit `sound_design_rules` length vs other keys
  - Topic absent → modify `user_prompt` template to inject `topic` + `scene_genre` context as named fields; tighten lower temperature to reduce LLM auto-completion of templates

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-DIALOGUE — Dialogue generation prompts

**Phase / class:** Prompt class (cross-cuts P-PERFORMANCE phase's dialogue layer; specifically the LLM input to `dialogue_writer`)
**Stage in pipeline:** ARCHITECTURE §7 LLM ensemble + dialogue layer; impl at `domain/dialogue_writer.py:60 system_prompt` ("professional screenwriter for photorealistic cinema" persona); tools-appended assembly at line 94 → line 103 LLM call
**Test tier:** C (dialogue invoked during full-reel performance capture, not Tier B single-shot)
**Estimated cost:** $0 — prompt observation intrinsic to P-PERFORMANCE; this cell is a focused angle
**Wall-clock prediction:** N/A — reuses P-PERFORMANCE observation

**PREDICTION (filled at v0.8 from impl-read at `domain/dialogue_writer.py:60`, operator pre-staging substrate §"PR-DIALOGUE", per §8 protocol):**

- **Expected output (shape):** dialogue strings per shot/scene with speaker attribution + content; LLM call returns structured JSON via tools-appended format (line 94); each dialogue entry maps to a character listed in scene's `characters_present`.
- **Expected content quality:** era-appropriate vocabulary matching scene period; character-voice-consistent (each character has stable register, idiom set, sentence-length distribution); no cinematic clichés ("It's over, Anya. We both know it." / "I never wanted this." / "We don't have much time."); cultural register matches source language structure (Korean characters in Korean-cultural scene: SOV syntax, honorifics-aware).
- **Expected failure modes (top 3):**
  1. **Cinematic clichés** — LLM regresses to genre boilerplate; root: persona-default to "movie dialogue" without explicit anti-cliché constraint
  2. **Language structural drift** — Korean character + Korean-cultural scene gets English-shaped SVO dialogue with no honorifics; root: prompt doesn't preserve source-language structural conventions
  3. **Character voice collapse** — all characters speak in same register (formal/informal/genre-fit); root: prompt doesn't enforce per-character voice differentiation; no `character_voice` trait propagated to LLM
- **Expected adjustment indicators:**
  - Clichés → add explicit "avoid these clichés: [list]" with examples in system_prompt; lower temperature; few-shot anti-cliché dialogue exemplars; manual cliché-rate coding on N=10 dialogues pre vs post
  - Language drift → add per-language sub-prompt or explicit "preserve source language's structural conventions (subject ordering, honorifics, register)" instruction; route per-character `language_pref` field if available
  - Voice collapse → introduce per-character voice anchor in `user_prompt` (each character's idiomatic snippet); enforce voice-distinctness post-check; expose `character_voice` trait at character-creation time

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-CONTINUITY — Continuity engine prompts

**Phase / class:** Prompt class (cross-cuts P-KEYFRAME + P-MOTION at the `enhance_shot_prompt` prompt-assembly injection point)
**Stage in pipeline:** ARCHITECTURE §8 continuity engine; impl at `domain/continuity_engine.py:446 enhance_shot_prompt(self, shot, scene, previous_shot=None, shot_index=0, approved_anchor_image=None)`; assembly order at lines 467 (raw shot prompt) → 472-474 (location persistence) → 478-490 (character identity fragments with spatial position for ≥2 chars) → 493-497 (physics constraints) → 501-505 (motion from action continuity) → 507-509 (continuity notes); anchor_image resolution at line 513 (separate from positive-prompt assembly)
**Test tier:** B + C (continuity injection runs at every keyframe + motion phase; observable at both single-shot and full-reel scale)
**Estimated cost:** $0 — prompt observation intrinsic to P-KEYFRAME/P-MOTION
**Wall-clock prediction:** N/A — reuses upstream cell observation

**PREDICTION (filled at v0.8 from impl-read at `domain/continuity_engine.py:446-513`, operator pre-staging substrate §"PR-CONTINUITY", per §8 protocol):**

- **Expected output (shape):** `(enhanced_prompt: str, continuity_config: dict)` tuple-equivalent. `enhanced_prompt` is `prompt_parts` joined — 6 fragment classes appended in order: raw shot prompt → location persistence → character identity fragments (with `left/center/right` spatial positioning when ≥2 characters present) → physics constraints → motion constraints → continuity notes. `continuity_config` holds `anchor_image` path (or None) — anchor is NOT part of positive-prompt assembly per ARCHITECTURE §8.
- **Expected content quality:** all 6 fragment classes present when applicable; spatial-positioning labels for multi-character shots; physics constraints reflect scene's physical state (e.g., "outdoors, rain falling, wet surfaces"); motion constraints reflect previous shot's action vector when `previous_shot` is provided; continuity notes from `shot["continuity_constraints"]` field; anchor_image resolves to a real file or None.
- **Expected failure modes (top 3):**
  1. **Assembly-order weight effects** — later fragments (notes, motion at indices 5-6) dominate over earlier (raw shot intent at index 1) due to image-gen attention bias toward recent tokens. Symptom: shots come back over-emphasizing peripheral notes vs the narrative-core intent.
  2. **Character fragment token-budget dominance** — ≥3 characters per shot → character fragments overwhelm raw shot prompt; root: no per-character length cap in lines 478-490 character-fragment generation.
  3. **Anchor / shot conflict** — `approved_anchor_image` references a day-shot keyframe but raw shot is night-scene; visual continuity breaks at next keyframe. Root: `_resolve_previous_approved_keyframe` selection not scene-boundary-aware (already flagged in PR-IMAGE PREDICTION failure mode #1).
- **Expected adjustment indicators:**
  - Order effects → A/B reorder: inject character anchor + narrative intent earlier; place style/notes LAST so they have less weight; measure identity-score variance across reorderings (operator testplan §5 P12 tweak variant proposal)
  - Character token overflow → add per-character length cap (e.g., max 30 tokens per character fragment); condense multi-char descriptors at line ≥3 character threshold
  - Anchor conflict → tighten `_resolve_previous_approved_keyframe` to scene-boundary-aware selection (skip anchors from different `time_of_day`); allow operator override via per-shot `anchor_override` field; document anchor as "style reference only, not scene-state ground truth"

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-AUDIO-VIBE — BGM vibe selection prompts

**Phase / class:** Prompt class (cross-cuts P-BGM phase; specifically the static vibe→prompt mapping in `_build_music_prompt`)
**Stage in pipeline:** ARCHITECTURE §13 audio pipeline; impl at `audio/music.py:88 def _build_music_prompt(music_vibe: str) -> str:` — **single parameter, dict-lookup design**; mapping at lines 90-117 (27 mood keys); default fallback at lines 120-121; consumed by `generate_bgm` (line 216) and `generate_suno_v5` path (called from line 158)
**Test tier:** B + C (BGM generation runs once per project; observable at single-call probe and full-reel assembly)
**Estimated cost:** $0 — prompt observation intrinsic to P-BGM
**Wall-clock prediction:** N/A — reuses P-BGM observation

**PREDICTION (filled at v0.8 from impl-read at `audio/music.py:88-121`, operator pre-staging substrate §"PR-AUDIO-VIBE", per §8 protocol — re-framed away from operator-testplan §5 P9's inaccurate three-axis premise; actual function takes `music_vibe` ONLY, no `video_pacing` or `story_tension` inputs):**

- **Expected output (shape):** producer-grade text prompt string with concrete BPM + key + instrumentation + named reference. Example for `music_vibe="suspense"` (line ~92): `"70bpm D minor, slow deep sub-bass drones, distant reversed piano, ticking clock polyrhythm, cinematic brass stabs, Hans Zimmer tension, dark ambient thriller score."` 27 mapped vibes have rich producer-grade specs; unknown vibes hit the line 120-121 generic fallback (`"Cinematic ambient music, {music_vibe} mood, slow, atmospheric, film score quality, professional production."`).
- **Expected content quality:** for mapped vibes — concrete BPM/key/instrumentation/cinematic-reference tuple is present; reads like a producer brief, not generic mood-word. For unmapped vibes — fallback is much weaker (no BPM, no instrumentation, no named reference); audible quality gap vs mapped vibes.
- **Expected failure modes (top 3):**
  1. **Static mapping misses scene-context** — pacing changes within a scene (slow setup → fast climax) can't be conveyed by a single vibe key; root: dict-lookup design has no scene-aware composition. Symptom: BGM stays flat across narrative pacing shifts.
  2. **Unknown-vibe fallback much weaker** — if scene's vibe falls outside the 27 mapped keys, BGM quality degrades noticeably; root: no fuzzy-match or neighbor-composition logic.
  3. **27-vibe taxonomy biased toward orchestra/score** — 7 of 27 (`epic`, `triumphant`, `classical`, `chase`, `action`, `western`, `jazz_noir`) are orchestra/classical-leaning; few electronic/contemporary entries; root: hand-curated dict reflects curator taste. Symptom: contemporary scenes pulled toward score-like aesthetic.
- **Expected adjustment indicators:**
  - Scene-context → add optional `scene_stage` parameter (intro/build/climax) with tempo-modulation hint OR composition between 2 vibes (transition mapping); tweak-variant: surface scene-stage to operator at BGM-prompt time
  - Fallback weakness → fuzzy-match unknown vibes to nearest mapped vibe via embedding distance OR LLM-elicit producer-grade prompt for unmapped vibes (single LLM call per unknown vibe; cached); ensures fallback parity with mapped vibes
  - Taxonomy bias → expand dict to cover electronic / contemporary / world-music vibes (priority gaps: lo-fi, synthwave, ambient electronic, hip-hop, K-pop); track usage histogram from production to identify which mapped vibes operators actually invoke vs which fall through to fallback

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

#### Test cell PR-CHIEFDIR — ChiefDirector validation + diagnosis prompts (dual-source: P2 + P3)

**Phase / class:** Prompt class (cross-cuts P-CHIEFDIR validation phase + per-take diagnosis pathway invoked during P-KEYFRAME / P-PERFORMANCE / P-MOTION on take-quality failures)
**Stage in pipeline:** ARCHITECTURE §7 LLM ensemble + post-decompose validation; impl spans:
  - **Validation pathway:** `llm/chief_director.py:130-206` (system prompt with HC1-HC8 hard constraints + T1-T9 tripwires) → `llm/chief_director.py:208 validate_shot_prompts(self, shots, scene) -> Dict` (pre-keyframe shot-prompt validation; emits `decision ∈ {APPROVED, MODIFIED, REJECTED}`)
  - **Diagnosis pathway:** `llm/chief_director.py:276 evaluate_generation_quality(...)` (per-take diagnosis) with inner `diagnosis_system` prompt at line 365 + JSON decision schema at line 396 (`"decision": "RETRY" | "ACCEPT_LENIENT" | "FAIL"`) + decision returns at lines 318 (RETRY default) + 446 (RETRY with mutation_level)
**Test tier:** B + C (validation runs at decompose for both tiers; diagnosis runs at any take-quality threshold breach during retries)
**Estimated cost:** $0 — prompt observation intrinsic to validation + diagnosis phases
**Wall-clock prediction:** N/A — reuses upstream cells

> **Two-layer Rule #12 catch (cycle-15 entry):** operator's pre-staging substrate (`docs/PR-cells-prestaging-2026-05-27-cycle15.md` §"PR-CHIEFDIR") correctly flagged operator-testplan §5 P3's `evaluate_take@352` as inaccurate (no such method), but proposed `diagnose_failure` as the replacement — which also doesn't grep-verify. Director-side Rule #12 re-verify at cycle-15 entry caught this: the actual diagnosis method is **`evaluate_generation_quality` at line 276** (its inner `diagnosis_system` prompt starts at line 365). This cell uses the verified `evaluate_generation_quality` reference. Operator's pre-staging fix is non-blocking; advisory.

**PREDICTION (dual-paragraph: validation + diagnosis; filled at v0.8 from impl-read at `llm/chief_director.py:130-206 + 208-276 + 318/365/396/446`, per §8 protocol):**

**Paragraph 1 — Validation prompt (`validate_shot_prompts`, P2-sourced):**

- **Expected output (shape):** dict with top-level `decision ∈ {APPROVED, MODIFIED, REJECTED}` + per-shot decisions list (`shots: [{shot_id, decision, ...}]`). The system prompt (lines 130-206) enumerates HC1-HC8 hard constraints (HC1: JSON-only output; HC2-HC8 cover identity firewall + per-shot single-character validation + scene/character consistency) plus T1-T9 tripwires for prompt-injection / role-play / hallucinated-content failure modes.
- **Expected content quality:** APPROVED for clean shot-prompt sets that satisfy all HCs and trigger no T-tripwires; MODIFIED with explicit per-shot edits when constraints partially violated (e.g., character ID drift between shots); REJECTED when constraints catastrophically violated → caller falls back to single-decomposer regen (P-DECOMPOSE failure mode #2).
- **Expected failure modes (validation):**
  1. **HC1-HC8 over-trigger on legitimate variation** — outfit/hair/lighting variation flagged as identity violation; root: HC phrasing may not distinguish costume vs face/build.
  2. **HC enumeration redundancy** — HC2-HC4 may overlap in scope; same shot may trip multiple HCs for one root cause, inflating perceived constraint density.
  3. **T1-T9 over-trigger on narrative content** — scene legitimately referencing identity (e.g., character "remembers former self") flagged as identity-tripwire; root: T-tripwires don't distinguish "scene about identity" from "prompt asks to violate identity."

**Paragraph 2 — Diagnosis prompt (`evaluate_generation_quality` → inner `diagnosis_system`, P3-sourced):**

- **Expected output (shape):** JSON with `decision ∈ {RETRY, ACCEPT_LENIENT, FAIL}` + `mutation` (suggested prompt-edit string or None) + `mutation_level` (int). System prompt at line 365 (`"You are ChiefDirector diagnosing a generation failure..."`); JSON decision schema at line 396; decision returns at lines 318 (RETRY default with `mutation_level: 1`) + 446 (RETRY with operator-supplied `level`).
- **Expected content quality:** decision tied to take-quality data passed via user_prompt (`coherence_info`, `shot_prompt[:500]`, `scene_context[:200]`); mutation suggestions actionable when present (concrete prompt-edit strings, not vague "improve quality"); ACCEPT_LENIENT used sparingly with explicit reason.
- **Expected failure modes (diagnosis):**
  1. **ACCEPT_LENIENT over-use** — borderline takes accepted at scale → quality dilution; root: no `quality_score` floor enforcement in prompt; LLM defaults to permissive when unsure.
  2. **FAIL under-use** — broken takes get RETRY repeatedly → wasted budget across regeneration loops; root: prompt may not enforce "if X failure mode, prefer FAIL over RETRY" rule.
  3. **RETRY-without-mutation** — `decision: RETRY` returned but `mutation: null` (no prompt edit suggested); regenerating with identical prompt yields identical failure. Root: prompt may not force mutation-non-null when decision == RETRY.

**Expected adjustment indicators (combined across both prompts):**

- HC over-trigger on costume → relax HC1 phrasing on outfit/hair variation; add explicit "costume variation does NOT count as identity violation" clarification; bump to ChiefDirector v2.1 system prompt with version-tracked rollout
- HC redundancy → consolidate overlapping HCs; track per-HC trigger histogram in production to identify dominant constraint; deprecate underperforming HCs
- T tripwire over-trigger on narrative → add T-level severity tiers (T-block vs T-flag); distinguish "scene about identity" (legitimate narrative) from "prompt asks to violate identity" (block); audit logs for false-positive T-tripwires
- ACCEPT_LENIENT over-use → add `quality_score` floor (e.g., ACCEPT_LENIENT requires score ≥ 0.65); require explicit per-criterion check before ACCEPT_LENIENT in prompt; distribute decisions across 20+ takes for calibration
- FAIL under-use → add "if X failure mode (broken file / OOM / engine-error), prefer FAIL over RETRY" rule; track RETRY-then-FAIL chains and cap RETRY count (e.g., max 2 RETRY → FAIL)
- RETRY-without-mutation → enforce `mutation` non-null when decision == RETRY (post-call validation; reject diagnosis output if violated); fall back to deterministic mutation strategy when LLM omits

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution.

> **All 8 prompt cells now FILLED at v0.8 (this commit).** Cross-references operator's pre-staging substrate at `docs/PR-cells-prestaging-2026-05-27-cycle15.md` (verified impl refs + 2 testplan inaccuracies surfaced) + operator's testplan §5 P1-P14 (canonical for HOW per Option B semantic split). PR-CHIEFDIR captures dual-source content (validation + diagnosis prompts) per operator's recommendation §"PR-CHIEFDIR" option (a). Director-side Rule #12 re-verify caught an additional inaccuracy in operator's pre-staging (`diagnose_failure` → actual `evaluate_generation_quality` at line 276) — two-layer Rule #12 catch chain captured in PR-CHIEFDIR cell note above.

### 5.5 Cold-context verification commands per cell (folded from operator REPLY `a9b1c32` §"Ask #1 §1.5")

Operator-drafted commands for cold-context validation of ACTUAL output without re-loading full predictive harness. **Operator-default per Sh** (operator-seat owns cold-context verification subagent dispatch).

#### Phase cells (P-*)

| Cell | Cold-context verification command | What it falsifies |
|---|---|---|
| **P-STYLE** | `cat /tmp/style-rules-output.json \| jq 'keys'` then `cat /tmp/style-rules-output.json \| jq '.[]'` | Shape (keys present) + content (non-empty strings) |
| **P-BGM** | `ffprobe -v quiet -show_streams /tmp/bgm.mp3 \| grep -E 'duration\|codec_name'` | Duration ≈ 47s + valid mp3 codec |
| **P-DECOMPOSE** | `cat /tmp/scene-shots.json \| jq '.[] \| {id, prompt: .prompt[:80], camera}'` | Shot count + each shot has prompt + camera directive |
| **P-CHIEFDIR** | `cat /tmp/chiefdir-validation.json \| jq '.decision, (.shots \| length)'` | Decision ∈ {APPROVED, MODIFIED, REJECTED} + non-empty shots list |
| **P-KEYFRAME** | `ls -la /tmp/keyframe-takes/*.png && file /tmp/keyframe-takes/*.png` | Files exist + valid PNG + nonzero size |
| **P-PERFORMANCE** | `ffprobe -v quiet -show_streams /tmp/perf-takes/*.mp4 \| grep -E 'duration\|width\|height'` | Files exist + valid mp4 + non-zero duration |
| **P-MOTION** | Same as P-PERFORMANCE shape | Same |
| **P-IDENTITY** | `cat /tmp/identity-scores.json \| jq '.[] \| {shot_id, overall_score, passed}'` | Per-shot score in [0.0, 1.0] + passed bool |
| **P-ASSEMBLY** | `ffprobe -v quiet -show_format /tmp/final_cinema.mp4 \| grep -E 'duration\|size\|bit_rate'` + `ffmpeg -i /tmp/final_cinema.mp4 -af loudnorm=I=-23:print_format=summary -f null - 2>&1 \| tail -10` | Valid mp4 + duration ≈ sum-of-shots + loudnorm I ≈ -23 LUFS |

#### Gate cells (G-*) — operates on project.json state transitions

| Cell | Cold-context verification command |
|---|---|
| **G-PLAN** | `jq '.scenes[].shots[] \| {id, plan_approved}' projects/<pid>/project.json` |
| **G-KEYFRAME** | `jq '.scenes[].shots[] \| {id, approved_keyframe_take_id}' projects/<pid>/project.json` |
| **G-PERF** | `jq '.scenes[].shots[] \| {id, approved_performance_take_id, performance_engine}' projects/<pid>/project.json` |
| **G-REVIEW** | `jq '.scenes[].shots[] \| {id, approved_final_take_id}' projects/<pid>/project.json` |
| **G-SCREEN** | `jq '.screening_approved, .needs_reassembly' projects/<pid>/project.json` |
| **G-ITERATE** | `jq '.scenes[].shots[] \| select(.iterations) \| {id, iterations}' projects/<pid>/project.json` |

#### Prompt cells (PR-*) — operator subagent-dispatchable verification of prompt-input itself

| Cell | Cold-context verification (operator subagent dispatchable) |
|---|---|
| **PR-STORY** | "Read `domain/scene_decomposer.py:341-440` system prompt; verify it enforces character coverage + camera-vocab + narrative-arc per testplan §5 P4." |
| **PR-IMAGE** | "Read `cinema/shots/controller.py:333-345`; verify prompt assembly composition order + identity descriptor injection per testplan §5 P12." |
| **PR-MOTION** | "Read `cinema/phases/motion_render.py`; verify per-engine prompt encoding aligns with brief PR-MOTION expected output shape." |
| **PR-CHIEFDIR** | "Read `llm/chief_director.py:130-206`; verify HC1-HC8 + T1-T9 phrasing per testplan §5 P2." |
| **PR-DIALOGUE** | "Read `domain/dialogue_writer.py:60`; verify dialogue system prompt + language adaptation per testplan §5 P8." |
| **PR-CONTINUITY** | "Read `domain/continuity_engine.py:446 enhance_shot_prompt`; verify assembly order per testplan §5 P12." |
| **PR-STYLE-LLM** | "Read `llm/style_director.py:62`; verify 6-key output schema per testplan §5 P1." |
| **PR-AUDIO-VIBE** | "Read `audio/music.py:88 _build_music_prompt`; verify vibe→prompt mapping per testplan §5 P9." |

#### Parameter cells (PA-*) — covered by operator's testplan §6 directional predictions

Per Option B semantic split + operator REPLY responsibility split: operator's testplan §6 provides per-parameter directional predictions (env vars + CINEMA_* + global_settings + sampling + ComfyUI workflow + ffmpeg + gate thresholds). Brief PA-* cells will cross-reference testplan §6 when operator fills next session.

### 5.4 Parameter class test cells (D — optional sensitivity sweep)

| ID | Parameter class | Sweep candidates | Tier | Status |
|---|---|---|---|---|
| PA-SAMPLING | sampler steps / cfg / scheduler | 3 sets × 1 shot = 3 generations | D | **FILLED v0.6** |
| PA-IMAGE | resolution / model swap | 2 sets × 1 shot = 2 generations | D | **FILLED v0.6** |
| PA-VIDEO | engine routing (Veo / LTX / Kling) | 3 engines × 1 shot = 3 generations | D | **FILLED v0.6** |
| PA-MOTION | motion strength low/med/high | 3 sets × 1 shot = 3 generations | D | **FILLED v0.6** |
| PA-LIPSYNC | lip-sync threshold | 2 sets × 1 shot = 2 generations | D | **FILLED v0.6** |
| PA-IDENTITY | GhostFaceNet threshold | 3 sets × 5 shots = 15 evaluations (no new generations) | D | **FILLED v0.6** |
| PA-AUDIO | loudnorm targets | 2 sets × 1 reel = 2 reels | D | **FILLED v0.6** |

> **All 7 PA-* parameter cells now FILLED at v0.6 (this commit).** Operator-seat fill per Sh operational-default + REPLY `a9b1c32` Ask #2 responsibility split. Cross-references operator's testplan §6 (parameter tweaking surface map) for HOW content (env vars + CINEMA_* + workflow params + ffmpeg + gate thresholds with directional predictions). Brief PA-* cells canonical for SWEEP design (which params, how many sets, cost envelope); testplan §6 canonical for parameter-level impl details. Per Option B semantic split.

#### Test cell PA-SAMPLING — Sampler steps / CFG / scheduler

**Phase / class:** Parameter sensitivity (ComfyUI workflow params; PA-* class)
**Stage in pipeline:** ARCHITECTURE §8 image generation; impl at `workflow_selector.py:get_workflow_params(shot_type)` + `pulid.json` workflow JSON (nodes for sampling)
**Test tier:** D (parameter sweep, optional)
**Estimated cost:** ~$0.15 (3 keyframe regenerations × $0.05 each); GPU lease window shared across the 3
**Wall-clock prediction:** 3-5 minutes (3 × 60-90s gen + comparison observation)

**PREDICTION (filled v0.6 from testplan §6.5 ComfyUI workflow params + `pulid.json` workflow defaults, per §8 protocol):**

- **Expected output (shape):** 3 distinct keyframe PNG files in `projects/<pid>/keyframes/<shot_id>/`, one per sweep set. Same shot, same character/location/prompt — only sampler params differ. Each output has identity_score + aesthetic_score + composite_score recorded via P-IDENTITY downstream.
- **Sweep sets:**
  - **Set 1 (baseline):** steps=20, cfg=7.5, scheduler=karras_normal (current `pulid.json` workflow default)
  - **Set 2 (higher quality):** steps=40, cfg=10, scheduler=karras_normal — predict marginal aesthetic gain + ~2× latency
  - **Set 3 (faster):** steps=12, cfg=5, scheduler=ddim_simple — predict ~40% faster + reduced aesthetic, possibly identity-score-equivalent (PuLID anchor dominates)
- **Expected content quality:** all 3 sets produce valid PNG ≥50KB; visual differences SHOULD be detectable (otherwise sampler doesn't matter for this shot type). Higher steps → smoother texture + better edge definition. Higher CFG → tighter prompt adherence (possibly over-saturated). Lower steps → softer textures, faster, possibly hallucinated detail.
- **Expected latency:** Set 1 ~60s; Set 2 ~120s (2× steps); Set 3 ~36s (60% steps). Total wall-clock ~3-5 min including pod queue.
- **Expected cost:** ~$0.05 per set × 3 = ~$0.15 (GPU lease prorated; FLUX_PULID per `API_COST_USD`).
- **Expected failure modes (top 3):**
  1. **No visible difference across sweep sets** — sampler params don't matter at this shot type; PuLID anchor dominates regardless. Suggests sweep should focus on PuLID weight (different cell) instead.
  2. **Set 3 (ddim_simple) produces blurry/under-cooked output** — 12 steps insufficient for FLUX-class model. Confirms steps floor.
  3. **Set 2 (CFG=10) produces over-saturated / artificial output** — CFG ceiling exceeded; visible "AI look" indicators (over-sharp edges, prompt-keyword artifacts).
- **Expected adjustment indicators:**
  - No-difference → sweep PuLID weight (±0.10) at PA-IMAGE instead; sampler is a tuning lever only for non-PuLID workflows
  - Set 3 too soft → set steps floor at 16-20 for FLUX baseline; document in `workflow_selector.py:get_workflow_params` comments
  - Set 2 over-saturated → set CFG ceiling at 8-8.5 for FLUX; verify CFG range in workflow templates
- **ADR-013 quantitative basis:** latency ranges from prior PuLID/FLUX benchmarks at ~1.5s/step on RunPod A100. Cost from `API_COST_USD` FLUX_PULID entry. Visible-difference threshold is qualitative (operator visual inspection).

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention (`docs/test-cells/PA-SAMPLING-<UTC-ts>.md`).

#### Test cell PA-IMAGE — Resolution / model swap (production vs max-tier)

**Phase / class:** Parameter sensitivity (workflow JSON swap; PA-* class)
**Stage in pipeline:** ARCHITECTURE §8 image generation; impl at `phase_c_assembly.py:generate_ai_broll` (production) vs `quality_max.py:generate_ai_broll_max` (max-tier; `pulid_max.json` workflow)
**Test tier:** D
**Estimated cost:** ~$0.45 (baseline $0.05 + max-tier $0.40 = $0.45 per `API_COST_USD` `QUALITY_MAX` entry)
**Wall-clock prediction:** 4-7 minutes (1 baseline keyframe + 1 max-tier keyframe with N=8 best-of)

**PREDICTION (filled v0.6 from testplan §6.6 Max-quality tier + `quality_max.py:574-710 generate_ai_broll_max`, per §8 protocol):**

- **Expected output (shape):** 2 PNG files for the same shot — one via production workflow (`pulid.json`), one via max-tier workflow (`pulid_max.json`). Max-tier may upscale to 4K via SUPIR; final downsample to project aspect_ratio. Each has identity_score + aesthetic_score; composite reflects max-tier's N=8 best-of selection.
- **Sweep sets:**
  - **Set 1 (production baseline):** `phase_c_assembly.generate_ai_broll` with default `pulid.json` workflow. SDXL-class behavior; ~30s; ~$0.05.
  - **Set 2 (max-tier):** `quality_max.generate_ai_broll_max` with `pulid_max.json` + SUPIR + N=8 best-of + HiDream-I1 optional swap. ~4 min; ~$0.40.
- **Expected content quality:** Set 1 produces typical FLUX-PuLID output (high quality, occasional identity drift). Set 2 produces visibly higher quality (sharper details, better composition, identity score ~0.05-0.10 higher due to N=8 selection over best identity match). Cost factor 8× → quality factor visible but not 8×.
- **Expected latency:** Set 1 ~30-60s; Set 2 ~3-5 min (8× generations + SUPIR upscale + downsample). Cold pod adds ~30s on first call.
- **Expected cost:** Set 1 ~$0.05; Set 2 ~$0.40 (8× base = $0.40 per `quality_max.py:705` cost annotation). Total sweep ~$0.45.
- **Expected failure modes (top 3):**
  1. **Set 2 produces visibly worse output than Set 1** — N=8 best-of selection criteria miscalibrated; OR SUPIR over-sharpens; OR HiDream-I1 swap produced incompatible style. Indicates max-tier is regressing not improving.
  2. **Identity score same or lower in Set 2** — N=8 best-of's identity-prioritized selection isn't working; OR SUPIR upscale broke face details.
  3. **Set 2 exceeds 5min wall-clock** — pod GPU contention OR N=8 not parallelized.
- **Expected adjustment indicators:**
  - Set 2 worse than Set 1 → review N=8 selection composite-score weighting; consider disabling SUPIR (`supir_enabled=False`); skip HiDream swap
  - Identity same/lower → tune N=8 selection criteria toward identity (raise identity weight in composite); verify primary_ref propagation through N=8
  - Latency >5min → reduce N (try N=4); verify N=8 candidates run parallel not sequential
- **ADR-013 quantitative basis:** Set 1 cost from `API_COST_USD` FLUX_PULID. Set 2 cost from `quality_max.py:705` documented 8× factor. Latency from cycle-13 max-tier benchmarks.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

#### Test cell PA-VIDEO — Engine routing (Veo / LTX / Kling)

**Phase / class:** Parameter sensitivity (video-gen engine swap; PA-* class)
**Stage in pipeline:** ARCHITECTURE §9 video routing (5 templates × 11 engines); impl at `phase_c_ffmpeg.py:generate_ai_video` dispatch + per-engine modules (`veo_native.py`, `ltx_native.py`, `kling_native.py`)
**Test tier:** D
**Estimated cost:** ~$1.00 (3 engines × 1 shot: Veo ~$0.50 + LTX ~$0.10 + Kling 3.0 ~$0.40)
**Wall-clock prediction:** 5-10 minutes (engine latencies vary widely)

**PREDICTION (filled v0.6 from testplan §6.4 model/sampling params + ARCHITECTURE §9 video routing, per §8 protocol):**

- **Expected output (shape):** 3 mp4 files for the SAME shot (same image + motion prompt), one per engine. Each mp4 ~5s duration; identity_score per-frame + motion fidelity score recorded. Engine routing controlled by overriding `shot["target_api"]` between runs.
- **Sweep engines:**
  - **Set 1 — Veo (`veo_native.py`):** `model="veo-3.1-generate"` via Vertex; ~$0.50/5s clip; ~60-180s latency
  - **Set 2 — LTX (`ltx_native.py`):** `model="ltx-2-3-pro"`; ~$0.10/5s clip; ~30-60s latency  
  - **Set 3 — Kling 3.0 (`phase_c_ffmpeg.py:508`):** Kling 3.0 via FAL; ~$0.40/5s clip; ~45-120s latency
- **Expected content quality:** all 3 produce playable 5s mp4. Visual differences expected: Veo tends toward cinematic + smooth motion; LTX tends toward higher-fidelity local-model output (potentially less natural motion); Kling 3.0 tends toward stylized/dramatic motion. Identity preservation varies — Veo strongest, LTX middle, Kling weakest at low motion settings.
- **Expected latency:** Set 1 (Veo) 60-180s; Set 2 (LTX) 30-60s; Set 3 (Kling) 45-120s. Total wall-clock 5-10 min sequential.
- **Expected cost:** ~$1.00 total per `API_COST_USD`. Veo dominates; LTX cheapest.
- **Expected failure modes (top 3):**
  1. **Engine API error** (rate limit / content policy / quota exceeded) — one or more engines unavailable; cascade fallback triggers OR sweep skips that set
  2. **Identity drift differs sharply across engines** (Set X's character looks materially different from keyframe; e.g., Kling reshapes face) — indicates engine-level identity preservation issue
  3. **Motion direction encoding mismatch** — same `camera: "zoom_in_slow"` produces different motion per engine; some honor the hint, some ignore
- **Expected adjustment indicators:**
  - API error → check API key + quota + content policy; route to alternative engine for this shot type via `workflow_selector.py` cascade table
  - Identity drift in specific engine → file engine-specific identity preservation issue; consider per-engine prompt-encoding tweaks; lower motion strength for that engine
  - Motion direction mismatch → verify per-engine motion vocabulary encoding in motion prompt template; align cascade preference to engines that honor camera hints
- **ADR-013 quantitative basis:** costs from `API_COST_USD` table; latencies from per-engine `_native.py` module empirical observation comments (where present); identity-preservation observations from cycle-10 benchmark notes.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

#### Test cell PA-MOTION — Motion strength (low / med / high)

**Phase / class:** Parameter sensitivity (motion-strength engine param; PA-* class)
**Stage in pipeline:** ARCHITECTURE §9 video routing; impl at `phase_c_ffmpeg.py:generate_ai_video` per-engine motion-strength dispatch (LTX uses `motion_strength` directly; Veo encodes via prompt keywords)
**Test tier:** D
**Estimated cost:** ~$0.30 (3 sets × 1 shot using LTX cheap engine for sweep isolation)
**Wall-clock prediction:** 3-5 minutes (3 × LTX ~60s + comparison)

**PREDICTION (filled v0.6 from testplan §6.5 + §6.8 motion fidelity floors + LTX engine module, per §8 protocol):**

- **Expected output (shape):** 3 mp4 files for the SAME shot using LTX (cheapest engine; isolates motion-strength variable). Same image input, same prompt — only motion_strength varies. Motion fidelity score recorded.
- **Sweep sets:**
  - **Set 1 (low):** motion_strength=0.3 + minimal motion verbs ("slight movement"). Predict: subtle motion; high identity stability; possibly fails motion_fidelity_floor.
  - **Set 2 (med):** motion_strength=0.5 (default) + standard motion verbs (e.g., "zoom_in_slow"). Predict: balanced; baseline reference.
  - **Set 3 (high):** motion_strength=0.8 + emphasis verbs (e.g., "dynamic camera movement"). Predict: pronounced motion; possible identity drift; possible motion_fidelity_floor over-pass.
- **Expected content quality:** all 3 playable mp4. Motion intensity scales linearly with strength. Identity preservation INVERSELY correlates with motion strength (more motion → more identity drift). motion_fidelity_floor check at low end may reject Set 1 if too static.
- **Expected latency:** uniform ~30-60s per set (LTX); total ~3-5 min.
- **Expected cost:** 3 × $0.10 = $0.30 (LTX cheap engine for sweep economy).
- **Expected failure modes (top 3):**
  1. **All 3 sets visually identical** — motion_strength param ignored by LTX engine; OR LTX has discrete motion levels not continuous
  2. **Set 1 fails motion_fidelity_floor** — confirms floor is reasonable; OR floor is too strict (legitimate static-shot variants rejected)
  3. **Set 3 identity-drift severe** — confirms high motion is identity-incompatible; OR motion-prompt encoding overrides motion_strength
- **Expected adjustment indicators:**
  - All 3 identical → check `phase_c_ffmpeg.py` motion_strength → LTX param mapping; verify the param actually reaches the LTX API call
  - Set 1 below floor → either floor is correctly catching too-static (no action) OR floor too strict for shot type (lower floor in `workflow_selector.py:get_workflow_params`)
  - Set 3 identity drift → enforce motion_strength ceiling per shot type (e.g., portrait shots cap at 0.6); add identity-vs-motion tradeoff guidance to operator docs
- **ADR-013 quantitative basis:** motion_strength ranges from LTX module; motion_fidelity_floor from per-template `workflow_selector.py` config.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

#### Test cell PA-LIPSYNC — Sync threshold (tight / loose)

**Phase / class:** Parameter sensitivity (SyncNet threshold; PA-* class)
**Stage in pipeline:** ARCHITECTURE §10 performance & lipsync; impl at `lip_sync.py:_sync_gate_settings` + `validate_lipsync_quality`
**Test tier:** D
**Estimated cost:** ~$0.20 (2 sets × 1 perf shot using Hedra-FAL cheap engine)
**Wall-clock prediction:** 3-5 minutes (2 × perf ~60s + lipsync eval)

**PREDICTION (filled v0.6 from testplan §6.8 performance/identity/motion gates + `lip_sync.py:427`, per §8 protocol):**

- **Expected output (shape):** 2 mp4 files for the SAME shot using Hedra-FAL Mode B performance, then run through SyncNet validation at 2 different thresholds. Per-set: video file + sync_score + sync_passed bool.
- **Sweep sets:**
  - **Set 1 (tight):** sync threshold = 2.0 (stricter; more retries before accept). Predict: more retries OR rejection.
  - **Set 2 (loose):** sync threshold = 0.5 (very permissive). Predict: instant accept; possibly accepts visibly-out-of-sync output.
- **Expected content quality:** both sets produce performance video. Sync quality scales with threshold (tight = better sync OR fail; loose = always accepted regardless of sync).
- **Expected latency:** uniform ~30-60s perf + 5-10s lipsync validation per set; total ~3-5 min.
- **Expected cost:** 2 × $0.10 = $0.20 Hedra-FAL. Sync validation is local SyncNet (no cost; ~5s wall-clock).
- **Expected failure modes (top 3):**
  1. **SyncNet not installed / `_sync_gate_settings` returns 1.0 fallback** — neither threshold has effect; both sets get same accept result
  2. **Set 1 (tight=2.0) rejects all real outputs** — threshold unrealistic; SyncNet score scale mismatched expectation
  3. **Set 2 (loose=0.5) accepts visibly-out-of-sync videos** — threshold too permissive; validation provides no value
- **Expected adjustment indicators:**
  - SyncNet fallback → check SyncNet installation; verify `_sync_gate_settings` returns expected non-1.0 value; document fallback behavior
  - Tight rejects all → tune threshold to realistic SyncNet score range (typically 0.5-1.5 for valid sync); document in `lip_sync.py:_sync_gate_settings`
  - Loose accepts bad → raise loose-bound default; add minimum-threshold floor regardless of operator setting
- **ADR-013 quantitative basis:** SyncNet score scale empirical; `_sync_gate_settings` fallback at 1.0 per `lip_sync.py:427` source.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

#### Test cell PA-IDENTITY — GhostFaceNet threshold sweep (NO new generations)

**Phase / class:** Parameter sensitivity (identity-gate threshold; PA-* class) — **UNIQUE: re-evaluates existing keyframes, no new gens**
**Stage in pipeline:** ARCHITECTURE §11 identity validation; impl at `cinema/shots/controller.py:484-506` + `phase_c_vision._get_shared_validator`
**Test tier:** D
**Estimated cost:** **$0** (local GhostFaceNet inference on existing keyframe outputs)
**Wall-clock prediction:** 1-3 minutes (15 evaluations × 1-3s each + analysis)

**PREDICTION (filled v0.6 from testplan §6.8 identity_strictness + `phase_c_vision._get_shared_validator`, per §8 protocol):**

- **Expected output (shape):** 15 evaluations = 3 threshold values × 5 existing keyframes from Tier C reel. For each (threshold, keyframe): `identity_score: float [0.0-1.0]` (immutable per keyframe; threshold doesn't change score) + `passed: bool` (varies per threshold).
- **Sweep thresholds:**
  - **Set 1 (lenient):** threshold = 0.60. Predict: ~80-90% pass rate.
  - **Set 2 (default):** threshold = 0.70. Predict: ~60-75% pass rate.
  - **Set 3 (strict):** threshold = 0.80. Predict: ~30-50% pass rate.
- **Expected content quality:** each keyframe gets identity_score; score is DETERMINISTIC for the same image (GhostFaceNet has no randomness). Threshold variation only changes `passed` bool, not score. Distribution of scores across 5 keyframes reveals identity-coherence of the test reel.
- **Expected latency:** ~1-3s per evaluation × 15 = 15-45s actual inference. Plus operator analysis ~30s-2min.
- **Expected cost:** $0. No new generations, no API calls.
- **Expected failure modes (top 3):**
  1. **All 15 evaluations pass even at strict=0.80** — threshold too lenient OR scores artificially high (validator bug; should investigate)
  2. **All 15 evaluations fail even at lenient=0.60** — threshold too strict OR scores artificially low (likely model-load issue OR primary_ref mismatch)
  3. **Bimodal distribution (some keyframes always pass, others always fail)** — keyframe set has identity-quality outliers; pinpoints which shots need regeneration
- **Expected adjustment indicators:**
  - All pass at strict → check threshold against actual GhostFaceNet score distribution; raise default threshold; OR investigate whether validator is too lenient
  - All fail at lenient → check primary_ref propagation; verify GhostFaceNet weights loaded (Pre-flight A7); check character reference image quality
  - Bimodal → use distribution to identify which shots have weak identity; flag for retry-with-different-pose; build per-shot quality signal
- **ADR-013 quantitative basis:** identity_score range [0.0-1.0] per `phase_c_vision` validator API; default threshold 0.60-0.70 per `cinema/shots/controller.py:488 cc.get("identity_threshold", 0.70)`.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

#### Test cell PA-AUDIO — Loudnorm targets (cinema -23 LUFS vs streaming -16 LUFS)

**Phase / class:** Parameter sensitivity (ffmpeg two-pass loudnorm targets; PA-* class)
**Stage in pipeline:** ARCHITECTURE §12 audio pipeline; impl at `phase_c_ffmpeg.py:1000 two_pass_loudnorm`
**Test tier:** D
**Estimated cost:** **$0** (local ffmpeg)
**Wall-clock prediction:** 5-10 minutes (2 × full-reel loudnorm passes; each ~2-5 min for typical reel)

**PREDICTION (filled v0.6 from testplan §6.7 ffmpeg loudnorm + `phase_c_ffmpeg.py:1000-1060`, per §8 protocol):**

- **Expected output (shape):** 2 reel mp4 files — same source assembly, different loudnorm targets. Each output has measured I (Integrated loudness LUFS) + LRA (Loudness range LU) + TP (True peak dBTP). Verifiable via `ffmpeg ... -af loudnorm=...:print_format=summary -f null - 2>&1`.
- **Sweep sets:**
  - **Set 1 (cinema):** target I=-23 LUFS / LRA=14 / TP=-2 dBTP (EBU R128 broadcast). Default per `phase_c_ffmpeg.py:two_pass_loudnorm`.
  - **Set 2 (streaming):** target I=-16 LUFS / LRA=8 / TP=-1 dBTP (Spotify/YouTube-style louder + tighter range). Predict: perceptibly louder; less dynamic range.
- **Expected content quality:** both mp4s play; measured I within ±0.5 LUFS of target (two-pass loudnorm accuracy). Perceptual loudness difference: Set 2 ~7 dB louder than Set 1 (perceptible doubling).
- **Expected latency:** ~2-5 min per reel for two-pass (analysis pass + apply pass). Total ~5-10 min sequential.
- **Expected cost:** $0. Local ffmpeg.
- **Expected failure modes (top 3):**
  1. **Measured I exceeds ±0.5 LUFS of target** — two-pass loudnorm accuracy issue; ffmpeg version mismatch OR input audio has issues (clipping, DC offset)
  2. **TP exceeds target ceiling** — true peak limiter not applied correctly; risk of clipping on playback
  3. **Audio quality degraded (artifacts / pumping)** — over-aggressive normalization OR LRA target too tight for source dynamic range
- **Expected adjustment indicators:**
  - I-off-target → verify ffmpeg version (need libloudnorm ≥4.x); check two-pass parsing of analysis-pass output; try single-pass as fallback
  - TP exceeded → tighten TP target margin (-1.5 instead of -1); check upstream audio peaks
  - Quality degraded → raise LRA target (more permissive range); use limiter instead of loudnorm if dynamic range needs preserving
- **ADR-013 quantitative basis:** EBU R128 spec for Set 1; common streaming-platform spec for Set 2; ±0.5 LUFS accuracy from libloudnorm documentation.

**ACTUAL / DELTA / INSIGHT / ADJUSTMENT:** filled during execution per §1.3 cell-artifact convention.

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
| **Pytest fixtures leaked to `domain/projects/`** (folded from operator REPLY `a9b1c32` §"Ask #3") | Test isolation discipline gap | `tests/conftest.py`, `tests/unit/test_*.py` fixtures | Patch test files to use `tmp_projects_dir` fixture; verify via cycle-13 `6f8be5d` pattern (no `mock.patch.object` shim trap; use `mock.patch("domain.project_manager.PROJECTS_DIR", ...)`) |
| **Mailbox-event missed at session start** (folded from operator REPLY `a9b1c32` §"Ask #3"; Candidate #8 evidence) | STATE.md staleness vs filesystem | `coordination/mailbox/sent/`, operator's `seen/operator.txt` cursor advance discipline | Re-`ls` mailbox immediately before substantive Write OR fold into Rule #4 RECENCY refinement (Candidate #8 filed at `1af3528`) |

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

### Operator-seat sign-off (REPLY LANDED at `a9b1c32`)

[x] **Operational-discipline additions incorporated** — see §1.5 above (Lane V CC-1 coalesced cadence, pytest-leakage delta enforcement, per-cell artifact telemetry, Lane D triggers)
[x] **Cold-context verification commands per cell drafted** — see §5.5 above (22 commands: 9 P-* + 6 G-* + 7 PR-*; PA-* deferred to operator's PA-fill commit)
[x] **Pytest-leakage discipline confirmed for execution** — see §1.5 above (pre-execution baseline + per-tier delta check + cycle-13 `6f8be5d` durable-fix pattern reference)
[x] **Counter-refinements OR consent per Rule #11 / v5 disagreement protocol** — CONSENT to v0.4 structure; one additive matrix row proposed (NOT counter-refinement; folded into §6 above)

### User-principal sign-off (execution authorization pending)

[ ] §9 open questions answered
[ ] RunPod restart authorized
[ ] Budget cap stated
[ ] Execution timeline approved

---

*Comprehensive end-to-end test brief — DRAFT v0.1 by director-seat cycle 14 (2026-05-27). Awaits operator REPLY for v1.0 fold, then user-principal authorization for execution. Per CLAUDE.md role partition Sh + v5+ proposal-cycle precedent. Per Candidate #7 discipline: this brief is itself a new artifact NOT inheriting carry-forward claims; LoC counts and pipeline phase mapping verified at brief-write time against ARCHITECTURE.md + actual code at HEAD `c93e4b7` cycle-14 mid-cycle. **The brief will become a carry-forward starting at next handoff; whoever inherits it MUST re-verify the pre-flight checklist + scope assumptions per Candidate #7.***

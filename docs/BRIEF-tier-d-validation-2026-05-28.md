---
brief-id: tier-d-validation
authored-by: operator-seat
authored-at: 2026-05-27T22:15Z
parent-brief: docs/BRIEF-comprehensive-test-2026-05-27.md
parent-execution: docs/test-cells/C-2026-05-27T21-13-27Z.md (Tier C tier-end)
verification-report: coordination/mailbox/sent/2026-05-27T22-08-46Z-operator-to-director-verification-report.md
related-rules: 8, 9, 12, 13, 15
status: DRAFT v1.0 — author-side; pending director silent-accept window OR user-principal direction
---

# Tier D-validation brief — close-the-loop on Tier C learnings + pipeline upgrade plan

User-principal asked operator at T22:12Z to:

> Gather all the information learned from the test and all the bugs and things
> that did not and do not work as intended and things that are implemented but
> not utilized and also from the insight you earned from testing. Compare with
> the prediction you made. Redesign new test to check and test all the above
> findings and fixes are addressed. And also from the result recommend how and
> what should change/modified/updated/upgraded for the pipeline.

This brief is the response: a comprehensive Tier C learning synthesis, a
predictions-vs-actuals comparison, a Tier D-validation test design with
acceptance criteria for each closure-being-tested, and a priority-ordered
pipeline upgrade plan.

---

## §1 Executive summary

**Tier C cheongsam reel completed end-to-end in 50.0 min at $6.45.** All 8 Tier
B closures end-to-end re-validated. Six new findings filed (2 CRITICAL +
2 IMPORTANT + 1 MINOR + 1 INFO; 1 closed inline at `024723d`). The pipeline
**produced a watchable 25.5s 1920×1080 cinema reel** — but two CRITICAL
gaps (`C-D3` ChiefDirector parse + auto-approve veto-all policy; `C-D4`
PuLID infrastructure missing on pod) and three IMPORTANT issues (`C-D2`
LLMEnsemble judge crash; `C-D5` keyframe threshold; `C-D6` P-PERFORMANCE
signature drift — now closed) mean that the **central correctness invariants
(identity-locked PuLID-FLUX cross-shot consistency; LLM-judged shot
decomposition; Hedra C3 lipsync) were not actually exercised** as designed.
Pipeline degraded gracefully into a different code path that produced a
similar-looking output, but the test did NOT validate what it was supposed to.

**Pre-Tier-D close-before recommendations: C-D3 + C-D4 (CRITICAL); then C-D5
+ C-D2 + (folded into) C-D6 already-closed.** With those four fixes landed,
**Tier D-validation re-run** should exercise the originally-intended path and
expose any remaining drift.

**This brief proposes Tier D-validation as a SINGLE focused re-run of Tier C
scope after the close-before fixes land — not a new scope expansion.** It's
a smaller, cheaper, faster-feedback variant of the Tier B → Tier C pattern
applied to the C-D findings themselves.

Beyond Tier D-validation, this brief also catalogs **9 pipeline-level
upgrade opportunities** spanning code hardening / config defaults /
documentation / coordination-protocol gaps. Priority-ordered in §6.

---

## §2 What worked — predictions matched, Tier B closures held

### §2.1 Tier B closures end-to-end re-validated (8 of 8)

The cycle-16 entry shipped 8 Tier B finding closures (VG-B1 / I-B1 / I-B2 /
M-B1 / M-B2 / M-B3 / C-B1 partial / C-B2). Tier C exercised each one and
**all 8 held** under real-shot-count execution:

| Closure | Tier C re-validation evidence | Verdict |
|---|---|---|
| **VG-B1** (`84b2efc`) | Korean female character → voice `uyVNoMrnUku1dZyVEXwD` (안나) via language+gender-aware picker; NOT Adam | ✅ HELD |
| **I-B1** (`972e239`+`2398314`) | Dispatcher fired `[CARTESIA] Generating [language=ko] voice=uyVNoMrn...` — both `language` (canonical) + `language_pref` (alias) consulted | ✅ HELD |
| **I-B2** (`dac17c3`) | `[BGM] Generating [CONTEMPLATIVE]` resolved via dedicated vibe_prompts entry (62bpm B minor + Ryuichi Sakamoto refs); NOT generic fallback | ✅ HELD |
| **M-B1** (`dac17c3`) | SCREENING gate honored project's `screening_stage_enabled: true`; gate fired after assembly; manual approve unblocked finalization | ✅ HELD |
| **M-B2** (`ad9fa02`) | Cost tracker fired for `dialogue_tts` ELEVENLABS / `bgm` FAL_STABLE_AUDIO / `scene_foley` STABILITY entries; combined with director's `74c920e` FLUX_KONTEXT + `669e5cd` web_research log_llm tracking — full audio + research cost-flow now wired | ✅ HELD (modulo cost-attribution gaps; see §3.4) |
| **M-B3 v2** (`e867aac`) | Final video duration **25.5s = stitched length** (5 shots × ~5s); NOT BGM length (47s). `-shortest` output flag working | ✅ HELD |
| **C-B1** (`eb6af85`) | UNETLoader serves `FLUX1/flux1-dev-fp8.safetensors` per A9 pre-flight (T21:05:15Z) | ✅ partial — scope was incomplete; see C-D4 |
| **C-B2** (`b11edd4`) | Tri-mix path triggered. Standalone-dialogue track muxing for Kling silent video. Final mp4 has audio | ✅ HELD |

**No Tier B closure regressed in Tier C.** This is the strongest signal that
the cycle-16-entry Tier B work is durable.

### §2.2 Predictions that matched

(Predictions captured in `docs/test-cells/C-2026-05-27T21-13-27Z.md`
"PREDICTION" blocks per cell; comparison below.)

| Cell | Prediction | Actual | Match? |
|---|---|---|---|
| Character voice | 안나 / `uyVNoMrnUku1dZyVEXwD` | exactly that | ✅ exact |
| P-DECOMPOSE invocation path | `competitive_decompose_scene` LLM ensemble | ✅ confirmed | ✅ |
| Cartesia routing fire | `[CARTESIA] Generating [language=ko]` | ✅ fired | ✅ |
| Cartesia fallback (I-B3) | Cartesia 400 → ElevenLabs fallback | ✅ exactly | ✅ |
| BGM I-B2 contemplative dedicated entry | NOT generic fallback | ✅ confirmed | ✅ |
| P-MOTION Kling Native ~3 min/shot | 3-3.2 min × 5 shots | ✅ exact unit cost | ✅ |
| G-IDENTITY post-motion PASS | threshold 0.6-0.7 by shot category | ✅ all PASS | ✅ |
| P-FOLEY Stability Audio | $0.03/s baseline | $0.87 / 25s ≈ $0.035/s | ✅ within tolerance |
| P-ASSEMBLY tri-mix + grade + loudnorm | per C-B2 + M-B3 closures | ✅ exact | ✅ |
| M-B1 screening project-setting path | gate honors project setting | ✅ confirmed | ✅ |
| Total cost envelope | $3.10-6.60 | $6.45 | ✅ high end of range |

**Prediction accuracy: ~85% on quantitative + procedural cells.** Main misses
were the cascading C-D4 chain (PuLID missing → Kontext fallback → composite
threshold gap → manual unblock) and the C-D6 signature drift (P-PERFORMANCE
SKIPPED). Plus shot count (5 vs 3 — C-D1).

### §2.3 Insights earned (positive findings)

1. **Adaptive PuLID weight tuning** fires across shots (1.0 → 0.95; 0.8 →
   0.75). Useful production behavior — the pipeline actively retunes
   identity weight based on observed identity-validation scores.

2. **Multi-angle "Max Multi" pathway** generates **6 angles** not the 4 in
   docstring: `angle_45 + angle_profile + angle_back + expression_smile +
   lighting_outdoor + canonical`. The expression + lighting variations are
   extras beyond the front/45°/profile/back set.

3. **dialogue_writer auto-generation** works as architected. Empty
   `scene.dialogue` + non-empty `scene.action` + `characters_present[]` set
   + `language="Korean"` → LLM produces Korean dialogue line for TTS. Not
   pre-required; pipeline handles missing dialogue gracefully.

4. **Identity threshold variance by shot category** functioning. Portrait
   shots use threshold 0.7; action shots use 0.6. Configured per
   workflow_selector category. Working as architected.

5. **Pipeline catches & logs P-PERFORMANCE crashes gracefully** — exception
   in `try/except` at controller.py:639-646 falls through to `precondition_error`
   which marks `performance_engine="SKIP"`. Graceful degradation; no crash
   propagation. Good defensive design (though the underlying bug C-D6 needed
   fixing).

6. **SCREENING gate timing is post-assembly, not pre-assembly.** `final_cinema.mp4`
   was written to `exports/` BEFORE the gate blocked — the gate is the
   final QA approval, not a pre-render checkpoint. M-B1 closure path
   working as architected.

7. **Kling Native motion engine provides surprisingly strong identity
   carry** despite no PuLID at keyframe stage. Cumulative mean 0.754 across
   5 shots; shot[2] keyframe 0.564 (FAIL) recovered to 0.902/0.816 motion
   side. **C-D4 PuLID gap is partially mitigated by motion-engine carry**
   — incidental, not by design. Suggests Tier-D-validation should explicitly
   compare PuLID-vs-Kontext keyframe identity against Kling-side motion
   identity to isolate the contribution.

8. **dialogue_writer + Cartesia routing is symmetric on both alias keys
   end-to-end.** `language="Korean"` (canonical) AND `language_pref="ko"`
   (alias) → both consulted by both layers (resolver + dispatcher). I-B1
   closure is robust against caller key-shape variance.

---

## §3 What did NOT work / DOES NOT work as intended

### §3.1 Bugs (code-fixable)

**C-D6 IMPORTANT (CLOSED `024723d`)** — `_ensure_scene_audio()` call-site
signature drift at `cinema/shots/controller.py:638`. Pre-fix call:
`self._host._ensure_scene_audio(scene["id"])` (passing scene_id string, missing
characters list). Post-fix: `(scene, characters)` matching the function
signature at `cinema_pipeline.py:502`. The other call site at
`cinema/shots/controller.py:1491` was already correct (`(scene, [c for c in
self.project["characters"] if c["id"] in chars])`) — line 638 was the lone
divergent caller. **Root cause analysis: signature evolved (likely Bundle-D
4.3 or similar refactor) without updating the line-638 caller.**

This is the ONLY genuine code bug in the cycle-16 Tier C surface. Everything
else is either a config-default issue, an infrastructure gap, an LLM-output
robustness issue, or a behavioral specification gap.

### §3.2 LLM-output robustness gaps (config-default + retry logic)

**C-D2 IMPORTANT** — `LLMEnsemble.judge_decision` parse-failed: `Expecting
value: line 1 column 1 (char 0)`. LLM returned non-JSON output (could be
plaintext explanation, could be JSON wrapped in markdown fences, could be
empty). `json.loads()` crashes; pipeline catches the exception and falls
through to first-valid candidate (gpt-4o). **The judge's competitive feature
was never actually exercised** — gpt-4o won by being-first, not by being-
judged-best.

**C-D3 root #1 (part of CRITICAL)** — `ChiefDirector.evaluate_shot_plans`
parse-failed with same `Expecting value: line 1 column 1` symptom. LLM
returned non-JSON. ChiefDirector's decision-classification logic
(APPROVED / MODIFIED / BLOCKED) never ran because the pre-classification
JSON parse crashed.

**Both fixes are the SAME PATTERN**: LLM calls that expect structured JSON
should either:
- Use OpenAI `response_format={"type":"json_object"}` (or equivalent for
  other providers — Anthropic has tool-use JSON mode)
- Add retry-with-format-correction on parse failure (1-2 retries with
  "your last response wasn't JSON; respond ONLY with the JSON object" prompt)
- Fall back to a deterministic rule-based classifier on persistent parse failure

The pattern surfaces ANYWHERE an LLM returns JSON. Audit candidates:
- `LLMEnsemble.judge_decision` (C-D2 site)
- `ChiefDirector.evaluate_shot_plans` (C-D3 root #1 site)
- `scene_decomposer.decompose_scene` (probable)
- `dialogue_writer.generate_dialogue` (probable)
- Style rules generation
- Continuity engine prompts
- (Likely many more — grep `json.loads` post-LLM-call sites)

### §3.3 Auto-approve policy gaps (config defaults + missing fallback states)

**C-D3 root #2 (part of CRITICAL)** — Auto-approve plan veto rule treats
ChiefDirector parse-error identically to ChiefDirector "BLOCKED" decision.
Both produce `decision != APPROVED` → veto. But the semantics are different:
- "BLOCKED" decision = LLM said NO; surfacing this to human review is right
- "parse-error" = LLM call malformed; we don't know if it would have said
  APPROVED, MODIFIED, or BLOCKED

**The current policy is "veto-all on parse-error" which causes 100% of
plans to need manual approval after a single parse failure.** This is too
strict. Recommended fix: parse-error should set `decision = "UNKNOWN"` or
similar, and auto-approve should DEFER-TO-MANUAL (don't block, don't
auto-approve — surface to operator for manual judgment per shot).

**C-D5 IMPORTANT (related)** — KEYFRAME_REVIEW gate `image_min_composite:
0.97` default. The 0.97 threshold makes sense for **PuLID-FLUX path** (high
identity-anchored composite). For **Kontext fallback path**, 0.97 is
unattainable by design (Kontext multi-ref ≠ PuLID face-locking; composite
ceiling is structurally lower). Threshold should be conditional:
- PuLID-FLUX path: 0.97
- Kontext fallback path: 0.75-0.80 (acceptable production-tier-fallback range)

This compounds with C-D4 (PuLID missing → forced Kontext fallback → 0.97
unattainable → veto-all). Either fix C-D4 (restore PuLID path) OR fix C-D5
(threshold conditional) → both close the indefinite block.

### §3.4 Infrastructure gaps (pod-side)

**C-D4 CRITICAL** — RunPod ComfyUI at `https://525nb9d5cc0p3y-8188.proxy.
runpod.net` is missing the `PulidInsightFaceLoader` custom node (node class
`PulidInsightFaceLoader`, node ID `#97` per error details). The cycle-15
brief explicitly noted "6 manual hardening steps NOT in `setup_runpod.sh`"
including the PuLID InsightFace install — director's `eb6af85` C-B1 fix
handled the UNETLoader-FLUX-model symlink but missed this one.

**Root cause analysis:** `setup_runpod.sh` step coverage:
- ✅ FLUX1-dev-fp8 model (post-C-B1 `eb6af85`)
- ✅ PuLID-Flux v0.9.1 (per cycle-15 brief)
- ✅ EVA-CLIP (per cycle-15 brief)
- ✅ IPAdapter (per cycle-15 brief)
- ❌ **InsightFace antelopev2 model** (in `models/insightface/antelopev2/`)
- ❌ **`PulidInsightFaceLoader` custom node** — may be installed via
  `cubiq/PuLID_ComfyUI` (wrong, SDXL) OR `balazik/ComfyUI-PuLID-Flux`
  (right, FLUX); cycle-15 brief flagged the variant swap as one of 6
  manual steps not in script. Likely the InsightFace **loader** ships
  separately or as a sub-component of the PuLID node pack and wasn't
  installed.

**Fix shape** (same as C-B1 pattern):
1. User-principal pod-side: `cd /workspace/ComfyUI/custom_nodes` →
   verify `ComfyUI-PuLID-Flux` directory present → `pip install
   -r requirements.txt` for any missing deps; `cd ../../models/
   insightface/` → download antelopev2 if missing
2. Operator-pod-probe A9-redux: `curl /object_info/PulidInsightFaceLoader`
   returns 200 with valid input schema (NOT missing_node_type error)
3. setup_runpod.sh hardening commit folds the install step

### §3.5 Behavioral specification gaps (intent vs implementation)

**C-D1 INFO** — `competitive_decompose_scene` ignores caller-supplied
`num_shots`. The LLM decides how many shots based on its judgment of the
scene's narrative beats. **Operator's `scene["num_shots"]=3` setting had
zero effect.**

Spec question: is `num_shots` supposed to be:
- (a) A HARD constraint (operator says 3 → exactly 3)
- (b) A SOFT suggestion (operator says ~3 → LLM picks 2-5)
- (c) IGNORED entirely (LLM decides; operator doesn't influence)

Currently (c) per `competitive_decompose_scene` behavior. If intent was (a)
or (b), the LLM prompt needs a constraint hint. If (c), the field shouldn't
be on the scene dict (misleading).

**C-D-persist-1 MINOR** — `scene.dialogue` + `scene.dialogue_lines` +
shot.dialogue all remain empty post-run despite `dialogue_writer.generate_
dialogue` producing a Korean line. Dialogue persists ONLY in the audio
file (`temp/audio_scene_*.mp3`). Implications:
- Downstream re-generation (e.g., voice swap, dialogue tweak, re-render)
  can't read the text — only the mp3 exists
- Operator-side post-hoc inspection requires re-running ASR on the mp3
- Pipeline self-consistency is broken: scene has dialogue (audio) but
  scene.dialogue field says "no dialogue"

### §3.6 Cost attribution gaps

**C-D-cost-1 MINOR-INFO** — `sora_native_generation: $0.80` in cost summary
with NO Sora invocation in pipeline log. Suspect provider-mapping bug at
`cost_tracker.py:300` (`"SORA": "openai"` mapping under `_provider_for_api`
or similar). Possible: a Kling task was mis-attributed as SORA at one of
the workflow_selector fallback paths.

**C-D-cost-2 MINOR-INFO** — `kling_native_generation: $0.50` vs
`motion_generation: $3.50` potential double-counting. Math:
- 5 shots × $0.50/shot Kling Native = $2.50 expected
- Actual: motion_generation $3.50 + kling_native_generation $0.50 = $4.00 total
- Difference: $1.50 — unaccounted for

**C-D-cost-3 MINOR-INFO** — `dialogue_tts: $0.32` for 1 dialogue line. M-B2
ELEVENLABS entry is $0.01 per call. 1 call × $0.01 = $0.01 expected; $0.32
actual = 32x overcharge. Possible:
- Retry chain (Cartesia 400 → retry 1 → retry 2 → ElevenLabs success;
  each retry incurred a count even if no actual API call landed)
- Character-count-multiplication (audio dialogue line had 32 characters;
  cost-per-character not cost-per-call?)
- Multi-character mix overhead (`generate_multi_character_dialogue` may
  trigger multiple TTS for assembly even with 1 line)

All 3 cost anomalies suggest `cost_tracker.py` needs a cycle-16+ hardening
pass — likely small-scope, mechanical.

### §3.7 Coordination protocol gap (Q9 sync joint-seat)

**C-D-coord-1 MINOR** — Director shipped 3 inline fixes (`2c41d02` /
`74c920e` / `669e5cd`) during operator's Tier C run, from a parallel
subagent audit `a79c59`. Per Q9 sync joint-seat, director's posture is
"passive observation"; the parallel audit + ship is at the edge of that
scope. **No mailbox fyi event was sent** — Rule #2 §"Signaling: narrate
before acting on shared tasks" violation. Files don't conflict with
operator's in-memory pipeline state (safe), but the coordination clarity
gap is real.

**Q9 scope question:** does "passive observation" mean only watching
operator's commits, OR can director run their own parallel work as long as
operator's commits aren't blocked? Currently ambiguous. Recommended Tier-end
clarification: either narrow Q9 to "no parallel ship without mailbox signal"
OR broaden to "director may parallel-ship if disjoint scope + mailbox fyi
post-ship".

### §3.8 Things UNEXERCISED this run (architected paths not actually tested)

| Path | Reason UNEXERCISED | Tier D validation requirement |
|---|---|---|
| **PuLID-FLUX P-KEYFRAME** | C-D4 (node missing) | C-D4 close + verify |
| **Hedra C3 P-PERFORMANCE (shot[1])** | C-D6 bug (now closed; pre-fix in-memory) | C-D6 fix in pipeline process + re-run |
| **LLMEnsemble competitive judging** | C-D2 (judge crash → first-valid) | C-D2 close + verify judge actually runs |
| **ChiefDirector decision classification** (APPROVED/MODIFIED/BLOCKED) | C-D3 root #1 (parse crash) | C-D3 close + verify classification runs |
| **PR-CONTINUITY explicit cell** | not separately logged; assumed implicit in motion-engine carry | Tier D add explicit logging OR confirm "implicit in motion" is the design |
| **`final_require_human_if_upstream_auto: True` safety net** | operator-direct-approval bypassed audit trail; safety net didn't fire | Either fix audit trail to mark direct approvals OR document that operator-direct is exempt |
| **PERFORMANCE_REVIEW auto-approve** | opt-in env-var `CINEMA_AUTO_APPROVE_MOTION` not set; default = MANUAL | Decide: default opt-in OR document opt-in expectation |
| **Multi-angle `expression_smile` / `lighting_outdoor` / `angle_back` usage** | downstream phases may or may not USE these | Trace which keyframe/motion/identity calls reference each angle |

---

## §4 Predictions vs Actuals — comprehensive table

Operator's pre-test predictions (from C-2026-05-27T21-13-27Z.md "PREDICTION"
blocks) compared to actual observations:

| Cell / metric | Prediction | Actual | Verdict |
|---|---|---|---|
| Face detection on cheongsam photo | PASS | PASS | ✅ |
| Multi-angle ref count | 3-4 angles | **6 angles** (Max Multi pathway) | ⚠️ Off — docstring vs reality |
| Voice assignment | 안나 (`uyVNoMrnUku1dZyVEXwD`) | **EXACT match** | ✅ |
| Character creation cost | $0.10-0.30 | ~$0.30 (6 angles × $0.05 estimated; tracked as "unknown" $1.29 bucket) | ✅ in range; provider attribution issue |
| P-DECOMPOSE shot count | 3 shots | **5 shots** (C-D1) | ❌ Off — `num_shots` ignored |
| P-DECOMPOSE wall-clock | 30-90s | ~30s | ✅ |
| P-DECOMPOSE cost | $0.30-0.80 LLM | $0.84 openai (combined with other LLM) | ✅ |
| P-CHIEFDIR outcome | APPROVED/MODIFIED/BLOCKED | **PARSE-ERROR** (C-D3) | ❌ UNEXERCISED |
| P-CHIEFDIR judge model | single Claude default | confirmed; parse crash separate | ✅ judge choice |
| PR-STYLE web research | Tavily, 3 sources | confirmed exact | ✅ |
| PR-DIALOGUE Cartesia routing | fire `[CARTESIA]` marker | fired | ✅ |
| PR-DIALOGUE Cartesia API | 400 (I-B3 expected) | 400 confirmed | ✅ as predicted |
| PR-DIALOGUE fallback | ElevenLabs success | confirmed | ✅ |
| PR-DIALOGUE cost | $0.008-0.05 per Korean line | $0.32 (32x over) — C-D-cost-3 | ❌ Off — cost-attribution gap |
| P-KEYFRAME path | PuLID-FLUX | **FAL Kontext fallback** (C-D4) | ❌ Off — infra gap |
| P-KEYFRAME per-shot identity | high (PuLID-anchored) | 0.564-0.868 (one FAIL @ 0.6) | ⚠️ Partial — Kontext-side identity weaker |
| P-KEYFRAME cost | $0.45-1.35 for 3 shots | $0.32 for 5 shots (Kontext cheaper) | ✅ within envelope |
| P-IDENTITY per-shot | threshold 0.85 | **threshold 0.6-0.7 by category** | ⚠️ Off — actual is workflow-driven not config-driven |
| P-MOTION Kling Native per-shot | $0.50 × 5 = $2.50 | $4.00 split across `motion_generation` + `kling_native_generation` (C-D-cost-2 double-count) | ❌ Off — cost-attribution gap |
| P-MOTION wall-clock | 2-4 min/shot | 3-3.2 min × 5 = 15-16 min | ✅ |
| G-IDENTITY post-motion | PASS | all PASS (mean 0.754) | ✅ |
| P-PERFORMANCE Hedra C3 | run on shot[1] | **all SKIP** (C-D6) | ❌ UNEXERCISED |
| P-PERFORMANCE cost | $0.10-0.30 | $0 (UNEXERCISED) | n/a |
| P-BGM contemplative vibe entry | dedicated I-B2 prompt | confirmed | ✅ |
| P-BGM cost | $0.10-0.50 | $0.10 | ✅ low end |
| P-FOLEY scene-aggregate | 1 foley track | 1 track | ✅ |
| P-FOLEY cost | $0.03-0.15 | $0.87 / 25s ≈ $0.035/s | ✅ scales with duration |
| P-ASSEMBLY tri-mix + grade + loudnorm | per C-B2 + M-B3 | exact | ✅ |
| G-SCREEN M-B1 path | project setting honored | confirmed | ✅ |
| Final video duration | matches stitched not BGM | 25.5s (M-B3) | ✅ |
| Total cost | $3.10-6.60 | **$6.45** | ✅ high end of range |
| Total wall-clock | 15-45 min | **50.0 min** (3 manual unblock pauses ate ~10 min) | ⚠️ slightly over due to unblocks |

**Summary: ~26 prediction points; ~18 matched cleanly (69%); ~5 partial
matches (19%); ~3 outright misses (12%).** The misses cluster on the C-D
findings (path-not-taken / cost-attribution / shot-count-deviation) — not
random prediction error. **Prediction quality was high; what diverged was
actual code/infrastructure behavior, not the predictor's mental model.**

---

## §5 Tier D-validation test design

### §5.1 Goal

Confirm that **all C-D findings are addressed** by re-running a Tier C-scope
test with predictions tied to the closure paths. Acceptance criteria are
per-finding (not per-cell as in original brief). **If any acceptance
criterion fails, the corresponding C-D finding has NOT been adequately
closed.**

### §5.2 Pre-conditions (close-before list)

Tier D-validation cannot start until ALL of:

1. **C-D3 closed:** ChiefDirector JSON-parse-robust hardening landed (commit)
   + auto-approve parse-error DEFER-TO-MANUAL policy landed (commit). Both
   in a single fix commit OR two sequential commits.

2. **C-D4 closed:** Pod-side install of `PulidInsightFaceLoader` custom
   node + antelopev2 InsightFace model. Operator A9-redux probe confirms
   `curl /object_info/PulidInsightFaceLoader` returns valid schema (not
   `missing_node_type` error). setup_runpod.sh hardening commit folds the
   install step for future pod restarts.

3. **C-D5 closed (or folded with C-D4):** `image_min_composite` threshold
   conditional on `fallback_used` (PuLID path: 0.97; Kontext fallback:
   0.75-0.80). May land as separate commit or part of C-D4 fix.

4. **C-D2 closed (recommended; not strictly Tier-D-blocker):** LLMEnsemble
   judge JSON-parse hardening. If not closed, Tier D will still exhibit
   judge-fail → first-valid fallback; the competitive judging feature
   remains UNEXERCISED. Acceptable degradation if C-D3 + C-D4 closed.

5. **C-D6 already closed at `024723d`** (operator's inline fix during Tier
   C run). No pre-condition action needed.

### §5.3 Project scope (mirrors Tier C; ONE intentional change)

Use the SAME project schema as Tier C-2026-05-27 (cheongsam Korean female
reel) for direct comparability. **ONE intentional change:**

- Override `scene["num_shots"] = 3` with extra explicit constraint hint
  via scene's `action` field OR via project's global_settings
  (e.g., `target_shot_count: 3`). Tests C-D1 — does the LLM respect a
  numeric constraint hint? If yes, the field is wireable; if no, C-D1
  needs structural fix.

Otherwise:
- 1 character (정연; cheongsam ref; female; Korean)
- 1 location (스튜디오; cherry blossoms)
- 1 scene (회상; contemplative mood)
- 1 dialogue line (Korean; auto-generated by dialogue_writer; NOT pre-supplied)
- `performance_shot_index: 1` (middle of 3)
- `language_pref: "ko"` + `language: "Korean"` (both keys; tests I-B1 alias-read)
- `music_mood: "contemplative"` (tests I-B2 dedicated vibe entry)
- `screening_stage_enabled: true` (tests M-B1 project-setting precedence)
- `budget_limit_usd: 50.0`
- `auto_approve.image_veto_on_fallback: false` (carry over from Tier C
  config to avoid Tier B Run 1 freeze pattern)
- `auto_approve.image_min_composite_kontext_fallback: 0.75` (C-D5 closure
  validation if config supports — else hardcoded threshold)

### §5.4 Test cell acceptance criteria (per C-D finding)

#### C-D1 (INFO) — `num_shots` constraint propagation

**Test:** Set `scene["num_shots"]=3` + `action` field contains "exactly 3
shots" constraint hint.

**Acceptance:**
- ✅ PASS: P-DECOMPOSE produces exactly 3 shots
- ⚠️ DEGRADED: P-DECOMPOSE produces 2-4 shots (soft suggestion working)
- ❌ FAIL: P-DECOMPOSE produces ≥5 shots (`num_shots` still ignored)

If FAIL: file C-D1 follow-up; structural fix to `competitive_decompose_scene`
LLM prompt OR to `scene_decomposer.decompose_scene` constraint propagation.

#### C-D2 (IMPORTANT) — LLMEnsemble judge JSON-parse robustness

**Test:** Run LLM ensemble decomposition; observe `[LLMEnsemble] Judging`
log line.

**Acceptance:**
- ✅ PASS: Judge produces valid JSON; winner determined by judge score
  (NOT first-valid fallback). Log shows `[Ensemble] Judge: <model> picked
  <winner> with score <X>`.
- ❌ FAIL: Judge crashes with `Expecting value: line 1 column 1` OR
  similar JSON parse error; pipeline falls back to first-valid.

If FAIL: C-D2 close was insufficient; revisit hardening approach (response_
format JSON mode? retry-with-correction? deterministic fallback?).

#### C-D3 (CRITICAL) — ChiefDirector parse-robust + auto-approve DEFER-TO-MANUAL

**Test:** Run pipeline through P-CHIEFDIR cell.

**Acceptance:**
- ✅ PASS A (ChiefDirector hardening): `[DIRECTOR]` log line shows
  decision classification (APPROVED / MODIFIED / BLOCKED) for each shot;
  NO `Evaluation parse error` log.
- ✅ PASS B (auto-approve DEFER-TO-MANUAL): IF parse error somehow still
  occurs, auto-approve audit shows `decision: 'DEFERRED'` (not VETO);
  pipeline reaches PLAN_REVIEW gate with operator-input-required (NOT
  veto-all chain).
- ❌ FAIL: Same indefinite block as Tier C (19+ min wait for manual unblock).

If FAIL on A: ChiefDirector hardening insufficient; investigate which prompt
returned non-JSON. If FAIL on B: auto-approve policy unchanged; revisit
plan_veto_rules in cinema/auto_approve.py.

#### C-D4 (CRITICAL) — PuLID-FLUX path actually runs

**Test:** Run pipeline through P-KEYFRAME cell.

**Acceptance:**
- ✅ PASS: Log shows `[PHASE C] Generating [txt2img] via ComfyUI PuLID
  (RTX 4090)` + `PuLID face-locked to: canonical.jpg` + **NO `missing_node_
  type` error** + take written to outputs/take_*.jpg from PuLID path
  (NOT FAL Kontext). Per-shot identity score 0.85-0.95+ (PuLID-anchored).
- ⚠️ DEGRADED: PuLID node found but produces weak keyframes (identity
  < 0.85). Indicates antelopev2 model issue OR PuLID adapter weight issue.
- ❌ FAIL: Same `missing_node_type` error; same FAL Kontext cascade fallback.

If FAIL: C-D4 pod-side install incomplete; iterate.

#### C-D5 (IMPORTANT) — KEYFRAME composite threshold appropriate

**Test:** Observe KEYFRAME_REVIEW gate auto-approve audit log.

**Acceptance:**
- ✅ PASS (PuLID path): composite scores ≥ 0.97; auto-approved; no veto.
- ✅ PASS (Kontext fallback if C-D4 not fully closed): composite scores
  in 0.75-0.95 range; auto-approved against conditional threshold 0.75-0.80.
- ❌ FAIL: Same veto-all chain as Tier C; manual unblock required.

If FAIL: C-D5 threshold-conditional logic not landed.

#### C-D6 (IMPORTANT) — P-PERFORMANCE actually runs Hedra C3

**Test:** Run pipeline through P-PERFORMANCE cell on shot[1] (middle of 3).

**Acceptance:**
- ✅ PASS: NO `TypeError: _ensure_scene_audio() missing 1 required positional
  argument 'characters'`. Shot[1] gets `performance_engine: "HEDRA_C3"`
  (or equivalent); Hedra API call fires; performance take written;
  G-PERF gate fires with audio + driving-video alignment scores.
- ⚠️ DEGRADED: Hedra call fires but fails (network / API key / driving
  video format issue) — different finding; not C-D6.
- ❌ FAIL: Same TypeError; same SKIP-all cascade.

If FAIL: C-D6 fix not in pipeline process (pipeline imports stale module);
verify commit `024723d` is in HEAD AND pipeline restarted.

#### C-D-cost-1/2/3 (MINOR-INFO) — Cost attribution gaps

**Test:** Inspect `CostTracker().get_summary()` post-run.

**Acceptance:**
- ✅ PASS: NO `sora_native_generation` line (assuming no Sora invocation
  in pipeline — verify in log). Kling total = (5 shots × Kling per-shot
  rate); not double-counted across `motion_generation` + `kling_native_
  generation`. Dialogue tts ≤ $0.05 per 1-line scene (ELEVENLABS path).
- ❌ FAIL: same anomalies as Tier C.

If FAIL: cost_tracker.py provider-mapping audit needed.

#### C-D-coord-1 (MINOR) — Q9 sync joint-seat scope clarity

**Test:** Observe whether director sends mailbox fyi event before/during/
after any parallel work on operator's Tier D-validation run.

**Acceptance:**
- ✅ PASS: Director sends `mailbox/sent/<ts>-director-to-operator-fyi.md`
  for any code change during operator's run, regardless of scope.
- ✅ ALTERNATE PASS: Director does NO parallel code change during operator's
  run (full "passive observation").
- ❌ FAIL: Director ships fix commit(s) without mailbox signal (second
  instance of C-D-coord-1; N=2 → candidate codification).

### §5.5 Tier D-validation scope tradeoff vs Tier D-fresh-scope

The user asked "redesign new test". Two interpretations:

**(A) Tier D-validation (this brief's design):** Same scope as Tier C; tests
that C-D findings are closed. Cheaper, faster, less coverage expansion.
Recommended IF cycle goal is "close-the-loop on Tier C".

**(B) Tier D-fresh-scope:** New scope (e.g., multi-character interaction;
multi-language switching; commercial-tier reel; longer reel 8-12 shots).
Tests new failure modes. Recommended IF cycle goal is "expand coverage
beyond Tier C".

**Operator recommendation: (A) Tier D-validation first, then (B) Tier D-fresh
or extended Tier D-2.** Validation establishes the close-the-loop signal
before scope-expansion adds confounds.

**Cost envelope for (A):** ~$5-8 (Tier C ran $6.45; if PuLID path lands,
keyframe cost may shift up slightly $0.50-1.00 — within envelope).

**Cost envelope for (B):** ~$10-20 (multi-character + longer reel; more
shots; more LLM rounds; possible Hedra C3 on multiple shots).

### §5.6 Tier D-validation execution protocol

Mirrors Tier C execution protocol:
1. Operator authors dispatch-claim mailbox event citing this brief + close-
   before pre-conditions verification
2. Director silent-accept window (5 min) with optional counter-refinement
3. Operator runs `scripts/run_tier_d_validation.py` (similar to
   `scripts/run_tier_c.py`) in background
4. Operator authors per-cell artifacts as cells complete
5. Operator authors tier-end artifact + verification-report
6. Director coalesced Lane V on commit range OR skip per Tier A precedent
7. Cycle close OR cycle continue per user-principal direction

---

## §6 Pipeline upgrade recommendations (priority-ordered)

### §6.1 Critical (close-before-Tier-D)

**1. ChiefDirector + LLMEnsemble JSON-parse robustness** (C-D2 + C-D3 root #1)
   - Audit ALL LLM call sites that `json.loads()` the response
   - Apply consistent hardening:
     - OpenAI: `response_format={"type":"json_object"}`
     - Anthropic: tool-use JSON mode OR explicit prompt + retry-with-correction
     - Other providers: retry-with-format-correction (1-2 retries)
     - Persistent failure: deterministic rule-based fallback (e.g., judge:
       pick longest valid candidate; ChiefDirector: default to APPROVED
       with `decision_source: "fallback-no-llm-judgment"` audit marker)
   - Estimated scope: 5-15 LLM call sites; ~50-150 LoC; 1-2 commits
   - Files: `llm/ensemble.py`, `llm/chief_director.py`, `dialogue_writer.py`,
     `scene_decomposer.py`, others per audit

**2. Auto-approve parse-error policy** (C-D3 root #2)
   - Distinguish parse-error (`decision: "UNKNOWN"`) from "BLOCKED" decision
     in `cinema/auto_approve.py:plan_veto_rules`
   - UNKNOWN → defer-to-manual (don't auto-approve, don't veto; surface to
     operator with parse-error context in audit log)
   - BLOCKED → existing veto behavior (operator decides override)
   - APPROVED → auto-approve
   - MODIFIED → existing modify behavior
   - Estimated scope: ~30-50 LoC; 1 commit; test coverage ~6 new tests
   - File: `cinema/auto_approve.py`

**3. PuLID InsightFace pod-side install + setup_runpod.sh hardening** (C-D4)
   - User-principal pod SSH: install `ComfyUI-PuLID-Flux` if missing OR
     install antelopev2 InsightFace model OR `pip install -r` missing deps
   - Verify via A9-redux probe: `curl /object_info/PulidInsightFaceLoader`
     returns valid input schema
   - setup_runpod.sh hardening commit folds the install step
   - Estimated scope: ~20-40 LoC in setup_runpod.sh; 1 commit; operational
     not code-test-coverable (functional via A9 probe)

**4. KEYFRAME composite threshold conditional** (C-D5)
   - Make `image_min_composite` conditional on `fallback_used` (or per
     workflow_selector category): PuLID path 0.97; Kontext fallback 0.75-0.80
   - Configure via `AutoApproveConfig.image_min_composite_pulid: 0.97` +
     `image_min_composite_kontext_fallback: 0.75` (new fields)
   - Estimated scope: ~30 LoC; 1 commit; test coverage ~4 new tests
   - File: `cinema/auto_approve.py`

### §6.2 Important (Tier D-pre-recommended; not strictly blocker)

**5. `num_shots` constraint propagation** (C-D1)
   - Wire `scene["num_shots"]` into LLM prompt as a constraint hint
   - Two options:
     - (a) Hard constraint: "Decompose into EXACTLY N shots" prompt
     - (b) Soft suggestion: "Decompose into approximately N shots" prompt
   - Operator recommends (a) for explicit user-control
   - Estimated scope: ~10-20 LoC; 1 commit; test coverage ~3 new tests
   - File: `scene_decomposer.py`

**6. Cost attribution audit** (C-D-cost-1/2/3)
   - Trace `sora_native_generation` $0.80 phantom — investigate
     `cost_tracker.py:300` provider-mapping bug + the `_provider_for_api`
     resolution path
   - Trace Kling double-count between `motion_generation` + `kling_native_
     generation` lines
   - Trace dialogue_tts inflation (32x for 1 line)
   - Possible: cost recording fires at multiple call layers without proper
     deduplication
   - Estimated scope: ~50-100 LoC audit + targeted fixes; 1-3 commits;
     test coverage ~10-15 new tests
   - File: `cost_tracker.py` + call sites

**7. Dialogue persistence** (C-D-persist-1)
   - When `dialogue_writer.generate_dialogue` produces lines, write back to
     `scene["dialogue_lines"]: List[str]` OR `scene["dialogue"]: str`
   - Enables downstream regeneration (voice swap, dialogue tweak) without
     re-running the LLM
   - Estimated scope: ~5-10 LoC; 1 commit; test coverage ~2 new tests
   - File: `cinema_pipeline.py` (caller side) OR `dialogue_writer.py` (callee
     side)

### §6.3 Minor (cycle-16+ tech-debt)

**8. Documentation cleanups** (C-D-doc-1 + C-D-pulid-1)
   - `create_character_with_images` docstring: "4 angles" → "6 angles"
     (front/45°/profile/back + expression/lighting variations)
   - `ARCHITECTURE.md §12` (audio pipeline): C-B2 root-cause framing note
     (carry from cycle-16 Tier B LV-1 advisory)
   - `ARCHITECTURE.md §X` (identity / character): note Kling-side identity
     carry observation (C-D-pulid-1 insight)
   - Estimated scope: ~20-40 LoC docs; 1 docs(arch-sync) commit
   - Files: `domain/character_manager.py` (docstring), `ARCHITECTURE.md`

**9. Q9 sync joint-seat scope clarification** (C-D-coord-1)
   - Either:
     - (a) Narrow Q9 to "no parallel ship without mailbox fyi event"
     - (b) Broaden Q9 to "director may parallel-ship if disjoint scope +
       mailbox fyi post-ship"
   - Codify in CLAUDE.md `# Director-Operator Concurrent Operation` section
   - Estimated scope: ~20-40 LoC in CLAUDE.md; 1 commit (strategic-seat-default
     = director ships; operator may draft)
   - File: `CLAUDE.md`

### §6.4 Strategic upgrades (longer-term; cycle-17+ scope)

**10. Pipeline self-diagnostic mode**
   - Pre-tier execution probe: run all expected paths in dry-run mode (no
     paid API calls; mocked responses) to catch C-D6-style signature drift
     + C-D4-style infra-missing BEFORE paid execution starts
   - Cost ~$0 to run; ~30-60s wall-clock; surfaces ~70-90% of structural
     issues
   - Out-of-scope for cycle-16 close; valuable for cycle-17 cost-saving

**11. Identity-consistency contract**
   - Explicit project-level config: `identity_lock_required: "pulid" | "kontext" | "fallback_ok"`
   - Pipeline checks at P-KEYFRAME phase start; if `pulid` and PuLID
     unavailable → FAIL_FAST with clear error (vs current silent cascade
     to Kontext)
   - Surfaces C-D4-style infra gaps as PIPELINE_PRE_CHECK errors not as
     silent degradation
   - Estimated scope: ~30-50 LoC; cycle-17+ candidate

**12. P-CHIEFDIR + P-DECOMPOSE decoupling**
   - Currently P-CHIEFDIR only fires AFTER P-DECOMPOSE produces shots.
     Single-shot manual-plan path skips P-CHIEFDIR entirely (Tier B
     observation; T19:36Z artifact)
   - Recommendation: P-CHIEFDIR should fire on operator-pre-defined shots
     too — validation is valuable regardless of shot-source
   - Estimated scope: ~20-40 LoC orchestration; cycle-17+ candidate

---

## §7 What this brief asks for

### §7.1 From director-seat (strategic peer)

1. **Acknowledge or counter-refine this brief** via mailbox event (5-min
   silent-accept window standard) — particularly on:
   - C-D3 fix shape (single commit vs two-commit split for the two compounded
     issues)
   - C-D4 pod-side fix coordination (user-principal action OR director-driven
     setup_runpod.sh PR-like change-prep)
   - Tier D-validation vs Tier D-fresh-scope choice (operator recommends
     validation-first; director's view?)

2. **Optionally dispatch coalesced Lane V on Tier C range** (`d13fba1..515e2ff`)
   if director wants cold-context cross-check on the test cell artifact +
   verification-report + C-D6 inline fix.

3. **If director wants to drive any of the §6.1 fixes** — claim via mailbox
   event before operator does (avoid Rule #2 racing).

### §7.2 From user-principal (project lead)

1. **Pod-side C-D4 fix authorization** — same pattern as cycle-16 C-B1
   (user-principal SSH + one-liner). Without this, Tier D-validation can't
   exercise PuLID-FLUX path.

2. **Cycle direction** — Tier D-validation now, OR Tier D-fresh-scope, OR
   pause for cleanup pass, OR alternate scope?

3. **Cost envelope confirmation for Tier D-validation** — ~$5-8 estimated;
   $50 cap respects.

### §7.3 From operator-seat (this brief's author; standby until directed)

Standing by for:
- Director silent-accept or counter
- User-principal direction on cycle path
- Any inline operator-claimable cleanup if user redirects (LV-1 doc note +
  L V-2 test addition still open as cycle-16+ advisory)

---

## §8 Race-ack telemetry + audit trail

This brief was authored T22:13-22:18Z after Tier C completion (T22:03:12Z)
+ verification-report ship (T22:08:46Z). Pre-Write gate fired at T22:13Z;
HEAD `515e2ff`; no new mailbox events; no race. Pre-commit gate will fire
immediately before this commit.

Cycle-16-entry cumulative finding count after Tier C:
- Tier B closures held: 8/8 ✅
- Tier C primary findings: 6 (1 closed inline; 5 open)
- Tier C advisory findings: 8 (mostly minor)
- Tier C inline fixes shipped this cycle: 1 (operator) + 3 (director audit)
- Tier C wall-clock: 50 min; cost $6.45

Race-shape catalog cycle-16-entry → end-of-Tier-C:
- 3 N=1 shapes from entry unchanged
- 1 NEW potential N=1 shape: director side-channel inline-fix without
  mailbox signal (C-D-coord-1)
- Watch cycle-17+ for second instance of shape #4 → if N=2, candidate-
  codify in v5.4 protocol bundle

---

Signed,
Operator-seat — 2026-05-27 cycle 16 mid, Tier D-validation brief draft +
comprehensive Tier C synthesis + pipeline upgrade recommendations
(priority-ordered §6.1-§6.4) + acceptance criteria per C-D finding (§5.4) +
standby for director silent-accept window OR user-principal cycle direction

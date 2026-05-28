---
brief-id: comprehensive-test-v2
version: v2.0-SCAFFOLD (pre-Phase-1 prep)
authored-by: operator-seat (scaffold) → director-seat (strategic-synthesis fill-in pending Phase 4)
authored-at: 2026-05-28 cycle-16 mid → cycle-17 entry
supersedes: docs/BRIEF-comprehensive-test-2026-05-27.md (v1.0)
parent-docs:
  - docs/CYCLE-16-CLOSING-REPORT-2026-05-27.md (director comprehensive synthesis)
  - docs/BRIEF-tier-d-validation-2026-05-28.md (operator validation-test design)
related-rules: 8, 9, 10, 11, 12, 13, 14, 15, 16-candidate
status: SCAFFOLD — sections marked [READY] complete; sections marked [PHASE-N-DEPENDENT] pending Phase N data
---

# Comprehensive Test Brief v2.0 — SCAFFOLD

> ⚠️ **THIS IS A SCAFFOLD DOCUMENT.** Cycle-16-mid prep by operator-seat to
> structure brief v2.0 ahead of Phase 1-4 execution. Sections marked
> `[READY]` are fully drafted from cycle-16 known state. Sections marked
> `[PHASE-N-DEPENDENT]` have placeholders and require Phase N data to
> finalize. **Per role partition Sh, director-seat will fill in strategic-
> synthesis sections at brief-v2.0 promotion-to-final.** Scaffold ships
> as `BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md`; promotes to
> `BRIEF-comprehensive-test-v2-2026-05-29.md` (or similar date) at
> Phase 6 cycle close.

---

## §0. Front matter + version metadata

[READY]

### Brief v2.0 scope

Cycle-17+ comprehensive test brief, folding cycle-16 lessons. Supersedes brief
v1.0 (`BRIEF-comprehensive-test-2026-05-27.md`).

### Tier structure (6 tiers; expansion from v1.0's 4)

| Tier | Purpose | New vs v1.0? | Cost env |
|---|---|---|---|
| **A** — Pre-flight | Verify environment, smoke, pytest, pod, LLM keys | refined per cycle-16 C-B1+C-D4 lessons | $0 |
| **B** — Single-shot regression | Korean dialogue probe; verify 10+ cycle-16 closures hold | same scope as v1.0 with closure-path predictions | $2-4 |
| **C** — Reel scope (multi-shot) | Cheongsam Korean reel OR new scope; per-finding acceptance criteria | scope tightened with C-D acceptance criteria | $5-10 |
| **D** — PA-* parameter sweep | Identity threshold / motion engine / image tier / lipsync / audio provider sweeps | requires PuLID-FLUX working (post-C-D4 close) | $15-25 |
| **E** — Closed-finding regression suite | Per-finding test cells exercising each cycle-16 closure | **NEW** per director closing-report §6.4 | $0-2 |
| **F** — Audit re-execution | Re-dispatch max-quality audit subagent; compare delta | **NEW** per director closing-report §6.5 | $0 (subagent only) |

### v2.0 incremental improvements over v1.0

1. PREDICTION discipline tightened — every PREDICTION must include MARKER verification (not just output property). Closes the "compensating mechanism" gap (cycle-16 Kling-side identity carry illusion).
2. A9 pre-flight refined to probe ACTUAL workflow node classes (not just CheckpointLoaderSimple).
3. A10 NEW — full inventory of cycle-15 "6 manual hardening steps" verification.
4. Tier E + Tier F NEW — closed-finding regression + audit re-execution.
5. Per-cell acceptance criteria PASS / DEGRADED / FAIL states explicit (operator brief v1 §5.4 pattern generalized).
6. Cost envelope per tier updated with cycle-16 actuals.
7. Pipeline upgrade roadmap with priority structure (P0/P1/P2/P3).
8. Rule #16 candidate (if codified) included in process discipline section.

---

## §1. Executive summary

[READY — base framing; cycle-16 fix-status TBD updates needed post-Phase-1]

### Cycle-17 framing

Cycle-16 was the "predictive harness vs reality" debut + first multi-tier paid execution + first cross-shot identity test. Outcomes:
- 17 findings closed across cycle-16 → 8 Tier B + 1 Tier C inline + (TBD: Phase 1 P0 fixes count)
- 6-15 findings open (depending on cycle-17 timing)
- 4 race-shape catalog entries; Race-N=1 underlying shape reached N=2 emergence
- ~$8.55-9.10 cumulative paid spend of $50 cap; ~$40-41 headroom

Cycle-17+ brief v2.0 codifies what changed + what's expected next cycle.

### Cycle-17 entry delta (shipped since this scaffold; director partial fill-in 2026-05-28)

GPU-independent cycle-17 shipments that resolve scaffold placeholders (every SHA verified via `git show`):

- **Rule #16 codified** — `7773502` (Protocol Bundle v5.4). Resolves §10's CANDIDATE / Q4-conditional.
- **F-F.1 lipsync cost-tracking wired** — `46a2cfa` (+ `e16bf85`, `shot_id` in the cost-record warnings). Both `generate_lip_sync_video` call sites now `record_api_call`; per-engine lipsync **pricing** is a tracked follow-on (records $0.00 until engines are added to the cost table). Resolves §7 F-F.1 + §9 P1-4 (partial).
- **HiDream image-routing wired** — `d28474e` (optimizer `suggested_image_api` → quality_max HiDream gate; the IMAGE twin of the dialogue VIDEO routing) + `d73eebb` (Lane V #20 M-2 user-pin guard). **Firing is GPU-gated** (needs the pod's HiDream/PuLID node + a product shot). Bears on §9 P3-5 + §12 Q-V2-2.
- **Suno BGM rewired to sunoapi.org** — `cfc4da0` (`POST /api/v1/generate` → poll record-info → `sunoData[0].audioUrl`). **NOT live-tested** (a real generate call spends credits). Bears on §5 Tier D PA-AUDIO (the Suno arm is now sunoapi.org-backed). Graceful-False → FAL Stable Audio fallback intact.
- **GitNexus phantom-rule removed** (ADR-016) + **storyboard B-integrate** design (ADR-017). Impact analysis is now `grep callers + Read call sites` (no `npx gitnexus`).

Cycle-16 numbers below are unchanged (point-in-time snapshot); this delta is the cycle-17-entry lens.

### Tier sequencing recommendation

```
Cycle-17 entry:
  Tier A refined pre-flight (verify cycle-16 fixes hold; A10 manual-step audit)
    ↓
  Tier B regression (verify all cycle-16 closures hold; ~$2-4)
    ↓
  Tier E closed-finding regression suite (NEW; ~$0-2; mostly pytest)
    ↓
  Tier F audit re-execution (NEW; ~$0; subagent only)
    ↓
  Tier C-rerun-validation OR Tier C-fresh-scope (depending on Phase 2 results)
    ↓
  Tier D PA-* parameter sweep (post-PuLID-actually-working confirmation)
```

Total cycle-17 entry estimated: ~$15-30 paid; 4-8h wall-clock.

---

## §2. Tier A — Refined Pre-flight (cycle-16 lessons folded)

[READY]

### A1: Working tree clean — same as v1.0

`git status --short` returns empty.

### A2: §15 smoke — same as v1.0

`.venv/bin/python scripts/ci_smoke.py` exits 0.

### A3: pytest baseline — update target

`.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1` returns `<N> passed, 3 skipped, <M> subtests passed`.

Expected N at cycle-17 entry (pre-Phase-1): **1129 passed / 3 skipped / 10 subtests** (measured at HEAD `e16bf85`, 2026-05-28, `tests/unit/` scope). This already exceeds the scaffold's earlier "~1000-1030" estimate because cycle-16-close + cycle-17-entry added tests well beyond the Phase-1-only C-D2/C-D3/C-D5 cells. Phase 1 (the C-D fixes) has NOT yet run — its test additions land on top of this baseline. [Final post-Phase-1 N still pending Phase 1 commits.]

### A4: tsc — same as v1.0

`(cd web && npx tsc --noEmit)` exits 0.

### A5: pod HTTP — same as v1.0

`curl -sI https://525nb9d5cc0p3y-8188.proxy.runpod.net/` returns `HTTP/2 200`.

### A6: LLM keys — refined per cycle-16 I-A6.1 closure

`.venv/bin/python -c "from config.settings import settings; print(settings.anthropic_api_key[:8], settings.openai_api_key[:8], settings.google_api_key[:8], settings.gemini_api_key[:8], settings.fal_api_key[:8], settings.kling_access_key[:8], settings.elevenlabs_api_key[:8], settings.cartesia_api_key[:8], settings.suno_api_key[:8])"` returns 9 non-empty prefixes.

`CINEMA_BUDGET_LIMIT_USD` env var is NOT required — budget is per-project `global_settings.budget_limit_usd: 50.0` (cycle-16 I-A6.1 Option a; documentation in brief v2 explicitly notes this).

### A7: GhostFaceNet weights — same as v1.0

`ls -la weights/GhostFaceNet.pt` exists; size ~17.3 MB.

### A8: Baseline projects count — same as v1.0

`find domain/projects -name "project.json" | wc -l` returns baseline.

### A9: ComfyUI node visibility — REFINED per cycle-16 C-B1 + C-D4 lessons

**v1.0 problem:** A9 probed `CheckpointLoaderSimple.ckpt_name` which PASSED but workflows reference `UNETLoader.unet_name` (different model directory; EMPTY in cycle-16 entry; produced C-B1 cascade).

**v2.0 fix:** A9 probes ALL workflow node classes referenced in production workflow JSONs.

#### A9.1: List workflow JSONs

```bash
ls -la cinema/workflows/*.json
```

Expected: at least `pulid.json` + `pulid_max.json` + `flux_kontext.json` + any custom workflows.

#### A9.2: Extract all `class_type` values from workflow JSONs

```bash
for f in cinema/workflows/*.json; do
  jq -r '[.[] | .class_type] | unique[]' "$f" 2>/dev/null
done | sort -u
```

Expected: union of all node class types referenced by production workflows.

#### A9.3: Probe each `class_type` against pod's `/object_info/<class>`

```bash
for class_type in <list-from-A9.2>; do
  curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/${class_type}" | jq -r '.[].input.required // .[].input.optional // empty | keys[]' 2>/dev/null | head -3
done
```

Expected: each probe returns valid JSON schema (NOT `missing_node_type` error).

#### A9.4: Probe specific loader nodes for model file visibility

For each loader node identified in A9.2 with a `<*>_name` parameter:

```bash
curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/UNETLoader" | jq -r '.UNETLoader.input.required.unet_name[0]'
curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/CheckpointLoaderSimple" | jq -r '.CheckpointLoaderSimple.input.required.ckpt_name[0]'
curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/LoraLoader" | jq -r '.LoraLoader.input.required.lora_name[0]'
# (extend for any other Loader nodes)
```

Expected: each returns non-empty model list.

#### A9.5: Probe PulidInsightFaceLoader specifically (cycle-16 C-D4)

```bash
curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/PulidInsightFaceLoader"
```

Expected: returns valid input schema (NOT `missing_node_type`).

### A10: Manual hardening steps inventory — NEW per cycle-16 C-D4 lesson

[READY — pending Phase 1 director-claimed setup_runpod.sh harden]

Cycle-15 brief noted "6 manual hardening steps NOT in `setup_runpod.sh`". Cycle-16 C-B1 closed step 1 (FLUX safetensors symlink); C-D4 surfaced steps 2+3+possibly-more (PulidInsightFaceLoader custom node + antelopev2 InsightFace model). Brief v2.0 inventories the FULL list + verifies each.

#### A10.1: Inventoried manual steps from cycle-15 brief (verify each)

[PLACEHOLDER — pending director's setup_runpod.sh harden commit cataloging the full set]

Expected manual steps (cycle-15 + cycle-16 known):
1. ✅ FLUX1-dev-fp8 in `models/diffusion_models/` (cycle-16 `eb6af85` closed; symlink)
2. [PENDING Phase 1 director] ComfyUI-PuLID-Flux custom node in `custom_nodes/`
3. [PENDING Phase 1 director] antelopev2 InsightFace model in `models/insightface/antelopev2/`
4. [TBD] `pip install --ignore-installed blinker`
5. [TBD] torch pin `2.4.1+cu118`
6. [TBD] `pip install -r ComfyUI/requirements.txt` unconditional on restart

Each step gets a probe command + expected output.

#### A10.2: Probe each manual step

[PLACEHOLDER — pending director's authoritative list from Phase 1 setup_runpod.sh harden]

```bash
# Probe each from A10.1 with shell test or HTTP probe
```

### Tier A acceptance criteria

✅ All A1-A10 PASS with green output.

⚠️ Any single FAIL → block Tier B until closed.

❌ Multi-step FAIL → pod-side audit needed before any paid execution.

---

## §3. Tier B — Korean dialogue probe regression

[PHASE-1-DEPENDENT for predictions; structure READY]

### B scope

Same shape as cycle-16 Tier B (`docs/test-cells/B-2026-05-27T19-36-10Z.md`) — single Korean dialogue probe on Min-ji project shape (1 character / 1 scene / 1 shot; no PuLID).

### B purpose (cycle-17 framing)

**Regression** — verify all cycle-16 closures hold:

| Closure | Predicted outcome | Required marker |
|---|---|---|
| VG-B1 (language+gender voice picker) | Korean female → 안나 voice `uyVNoMrnUku1dZyVEXwD` | Log: `🎙️ Auto-assigned voice: 안나 (Anna)` |
| I-B1 (Cartesia routing) | Both `language` (canonical) + `language_pref` (alias) consulted | Log: `[CARTESIA] Generating [language=ko]` fires |
| I-B2 (contemplative vibe) | Dedicated entry, NOT generic | Log: `[BGM] ... contemplative ...` resolves to 62bpm B minor + Rhodes prompt |
| I-B3 (Cartesia fallback) | 400 → graceful ElevenLabs (per cycle-16 I-B3 NO-ACTION advisory) | Log: `[CARTESIA] failed for line ...; falling back to ElevenLabs` |
| C-B1 (UNETLoader FLUX) | UNETLoader serves FLUX1/flux1-dev-fp8.safetensors | A9.4 probe |
| C-B2 (tri-mix) | Standalone dialogue track muxed for silent video | ffprobe shows dialogue stream in final mp4 |
| M-B1 (project setting) | `screening_stage_enabled: true` honored | Gate blocks; SCREENING_STAGE log marker |
| M-B2 (cost tracking) | ELEVENLABS + FAL_STABLE_AUDIO + STABILITY_FOLEY all in cost_log | `cost_log` contains per-API entries |
| M-B3 (amix duration) | Final audio = video length, not BGM length | ffprobe duration match |

### Tier B cost envelope

$2-4 (single-shot; no multi-angle FLUX gen; one Korean line)

### Tier B acceptance criteria

[PHASE-1-DEPENDENT — final markers depend on Phase 1 fix specifics]

- All 9 markers above PASS → Tier B regression CLEAN
- Any marker FAIL → file as regression finding; cycle-17 close-before-Tier-C
- Wall-clock: ~10-15 min

---

## §4. Tier C — Cheongsam reel (Tier C-rerun-validation OR new scope)

[PHASE-2-DEPENDENT for sub-cell results; structure READY]

### C scope decision (cycle-17 entry)

Two scope options:

**Option (a) Tier C-rerun-validation:** Re-run cycle-16 Tier C scope (cheongsam Korean female, 1 scene × 3 shots, performance on middle shot) — but with cycle-16-mid P0 fixes landed. Per operator brief v1 §5.4 per-finding acceptance criteria. Cost ~$5-8.

**Option (b) Tier C-fresh-scope:** Pick a NEW Tier C variant for cycle-17 entry — e.g., multi-character (2 characters interacting) OR multi-language (Korean + English dialogue) OR longer reel (5 shots in single scene OR 2 scenes × 3 shots). Cost ~$8-15.

**Recommendation:** **(a) Tier C-rerun-validation FIRST** before any (b) variant. Validation establishes the closure-status signal before scope expansion adds confounds. Cycle-17 entry runs (a); cycle-17 mid+ optionally runs (b) variants.

### C cells (per operator brief v1 §5.4)

[READY — direct copy from operator brief v1]

Each C-D finding has explicit PASS / DEGRADED / FAIL state. Examples:

| Finding | Test cell | PASS | DEGRADED | FAIL |
|---|---|---|---|---|
| C-D1 (num_shots) | scene["num_shots"]=3 + action constraint hint | 3 shots | 2-4 shots (soft) | ≥5 shots (ignored) |
| C-D2 (judge robust) | LLMEnsemble decompose | judge winner via score | retry-with-correction success | parse-crash → first-valid |
| C-D3 (ChiefDirector + auto-approve) | P-CHIEFDIR + PLAN gate | APPROVED/MODIFIED/BLOCKED + auto-pass | DEFER-TO-MANUAL surfaced | VETO-ALL chain (same as cycle-16) |
| C-D4 (PuLID infrastructure) | P-KEYFRAME PuLID path | identity 0.85-0.95+ PuLID-anchored | PuLID found but identity <0.85 | missing_node_type (same as cycle-16) |
| C-D5 (KEYFRAME threshold) | KEYFRAME_REVIEW gate auto-approve | PASS (PuLID or Kontext fallback) | (TBD) | VETO-ALL chain |
| C-D6 (P-PERFORMANCE) | shot[middle] Hedra C3 | Hedra take written + identity carry | Hedra fired but failed (API/network) | TypeError signature drift (same as cycle-16) |

### Tier C cost envelope

$5-10 depending on scope choice + shot count.

### Tier C acceptance criteria

[READY — same shape as operator brief v1 §5.4]

- All C-D findings PASS → Tier C-rerun-validation CLEAN; Tier D unblocked
- Any C-D finding DEGRADED → file as cycle-17+ follow-up; Tier D may proceed with caveat
- Any C-D finding FAIL → Tier D blocked; cycle-17+ close-before-Tier-D

---

## §5. Tier D — PA-* parameter sweep

[POST-TIER-C-DEPENDENT — Tier D scope finalized after Tier C validation; structure READY]

### D scope

Tier D is the genuine **parameter sweep** tier. PA-* cells sweep configuration variants to characterize the parameter space:

| Cell | Sweep variants | Cost env |
|---|---|---|
| PA-IDENTITY | Threshold 0.60 / 0.70 / 0.80 | $5-10 (requires PuLID actually working post-C-D4) |
| PA-MOTION | Engine variants (Kling Native / Veo / LTX / Seedance / FAL Kling) | $5-15 (multi-shot × multi-engine) |
| PA-IMAGE | Quality tier (production vs max; CFG; steps; PuLID weight) | $3-8 |
| PA-VIDEO | Engine variants in cascade (per phase_c_ffmpeg.py) | $5-15 |
| PA-SAMPLING | Steps × CFG matrix | $3-6 |
| PA-LIPSYNC | Engine variants (Hedra C3 / MuseTalk / Sync.so / LatentSync) | $3-8 |
| PA-AUDIO | BGM provider (Suno V5 vs FAL Stable Audio) | $2-5 |

### Tier D pre-conditions

[PHASE-2-DEPENDENT]

- Tier C-rerun-validation acceptance criteria all PASS or DEGRADED-without-blocker
- Phase 1 P0 fixes all landed (C-D2 + C-D3 + C-D5 closures)
- Pod-side C-D4 closed (PuLID actually working)
- $50 cap headroom ≥$25 (Tier D cost envelope)

### Tier D cost envelope

$15-25 total (per-cell costs additive; some shared infrastructure).

### Tier D recommendation

**DEFER cycle-17 entry → cycle-17 mid+ OR cycle-18.** Tier D is meaningful only when PuLID is working. Per both seats' converged plan, validation-first.

---

## §6. Tier E — Closed-finding regression suite (NEW)

[READY]

### E purpose

Per director closing-report §6.4. Dedicated tests that EXERCISE each closed-finding's specific code path. Validates that cycle-16 fixes don't regress.

### E cells (mixed pytest unit + synthetic-project E2E)

| Test cell | Validates closure | Implementation |
|---|---|---|
| **TE-VG-B1** | language+gender voice picker (Korean F → 안나; Korean M → 준호; English F → Rachel; English M → Adam) | pytest in `tests/unit/test_character_manager_voice_assignment.py` (cycle-16 added) |
| **TE-I-B1** | dual-key alias-read at resolver + dispatcher | pytest in `tests/unit/test_audio_dialogue_cartesia.py` |
| **TE-I-B2** | contemplative vibe specific entry | pytest verify `vibe_prompts["contemplative"]` exists + specific content |
| **TE-M-B1** | project-level screening override (project wins; env-var fallback when project absent) | pytest `tests/unit/test_screening.py::TestScreeningStageProjectOverride` |
| **TE-M-B2** | each audio API cost-tracker entry + invocation path | pytest `tests/unit/test_cost_tracker.py::TestRecordAPICallAudioTracking` |
| **TE-M-B3** | amix duration=longest with -shortest output flag | synthetic ffmpeg invocation OR e2e mini-pipeline |
| **TE-LV-2** | dict-shape `settings_obj.language_pref` routing | pytest dispatcher path |
| **TE-F-B.2** | new projects default `prompt_optimizer_enabled: True` | pytest `make_project()` defaults |
| **TE-F-D.1** | multi-angle FLUX_KONTEXT cost-tracker invocations × 5 | pytest mock + invocation count |
| **TE-F-F.5** | web_research log_llm both Phase 1 + Phase 2 | pytest mock + log_llm assertion |

**Cycle-16-mid Phase 1 closures (add post-Phase-1):**

| Test cell | Validates closure | Implementation | Phase 1 dependency |
|---|---|---|---|
| **TE-C-D2** | LLMEnsemble judge JSON-parse robustness | pytest mock + parse-error injection | Phase 1 op C-D2 fix |
| **TE-C-D3-1** | ChiefDirector parse-robust + retry | pytest mock + parse-error injection | Phase 1 op C-D3 part 1 fix |
| **TE-C-D3-2** | auto-approve parse-error DEFER-TO-MANUAL policy | pytest auto-approve audit | Phase 1 op C-D3 part 2 fix |
| **TE-C-D5** | KEYFRAME threshold conditional on fallback_used | pytest config branch | Phase 1 op C-D5 fix |
| **TE-C-D6** | `_ensure_scene_audio` signature correct | pytest call-site verify (already closed `024723d`) | none — already closed |

### E synthetic project E2E (single mini-run)

Once cycle-16 + Phase 1 closures pytest-pass, synthetic project E2E run:

```
TE-synthetic-project = run_tier_e_synthetic.py
  → minimal project (1 char / 1 scene / 1 shot; Korean; cheongsam-style)
  → run full pipeline through screening
  → verify ALL closures fire end-to-end
  → final mp4 with Korean female 안나 voice + contemplative BGM + dialogue+BGM+foley tri-mix
  → cost ~$0-2 (single shot)
```

### Tier E acceptance criteria

✅ All pytest cells PASS in CI green
✅ Synthetic project E2E run produces final mp4 with all markers present
✅ Cost ≤$2

[PHASE-1-DEPENDENT — TE-C-D2/3/5 cells require Phase 1 commits]

---

## §7. Tier F — Audit re-execution (NEW)

[READY]

### F purpose

Per director closing-report §6.5. Re-dispatch max-quality audit subagent on cycle-16-fixed HEAD; compare delta vs cycle-16 audit (`a79c59`).

### F dispatch shape

```
Agent({
  subagent_type: "general-purpose",
  description: "Cycle-17 max-quality audit re-execution",
  prompt: <same shape as cycle-16 a79c59 + delta-comparison-against-cycle-16-findings>
})
```

### F expected delta (cycle-16 baseline)

| Cycle-16 finding | Expected cycle-17 status |
|---|---|
| F-B.2 (prompt_optimizer default) | CLOSED (regression check — should NOT re-surface) |
| F-D.1 (FLUX_KONTEXT tracking) | CLOSED (regression check) |
| F-F.5 (web_research log_llm) | CLOSED (regression check) |
| F-A.1 / F-B.1 (storyboard_mode wire) | OPEN (carry-forward; cycle-17+ P1-5 candidate) |
| F-A.2 (LoRA validator real impl) | OPEN (carry-forward; cycle-17+ P1-7) |
| F-A.3 (batch_optimize_scene) | OPEN (carry-forward; cycle-17+ P1-6) |
| F-A.4 (validate_multi_identity) | OPEN (carry-forward; multi-char only) |
| F-B.3 / F-C.2 (hires_fix wire) | OPEN (carry-forward; P2-1) |
| F-F.1 (lipsync cost tracking) | **CLOSED cycle-17 `46a2cfa`** (both `generate_lip_sync_video` call sites `record_api_call`; regression check — per-engine pricing follow-on may surface as NEW) |
| F-F.2 (LLM cost tracking) | OPEN (carry-forward; P1-3) |

### F NEW gaps from cycle-16 changes (if any)

Audit may surface gaps introduced by cycle-16 fixes. Filed as cycle-17+ candidates.

### Tier F acceptance criteria

✅ Audit subagent completes without crash
✅ Delta report identifies known-closed (3) + known-open (7-8) + NEW (TBD)
✅ Quality-debt trend telemetry: cycle-16 baseline → cycle-17 measured

---

## §8. PREDICTION discipline v2

[READY]

### v2 refinement (per director closing-report §6.6)

Every PREDICTION cell MUST include not just expected output property, but the SPECIFIC MARKER that confirms the EXPECTED MECHANISM fired.

**Anti-pattern (v1.0 cycle-16 Tier C lesson):**
- PREDICTION: "P-KEYFRAME PuLID-FLUX produces identity-locked keyframes"
- ACTUAL: PuLID never fired (C-D4 cascade fallback to FAL Kontext); identity LOOKED locked via motion-engine carry; output property matched but mechanism did NOT
- Verdict: PREDICTION technically matched output; missed the path divergence

**Pattern (v2.0):**
- PREDICTION: "P-KEYFRAME PuLID-FLUX produces identity-locked keyframes — REQUIRED MARKER: log shows `[PHASE C] Generating [txt2img] via ComfyUI PuLID (RTX 4090)` AND `PuLID face-locked to: canonical.jpg` AND no `missing_node_type` error"
- ACTUAL evaluation: marker present → PASS; marker absent but output present → DEGRADED-COMPENSATED; marker absent and output absent → FAIL

### Marker requirements per cell (cycle-17 baseline)

[READY]

| Cell | Required marker (log substring) |
|---|---|
| P-KEYFRAME PuLID path | `via ComfyUI PuLID` + `PuLID face-locked to:` + NO `missing_node_type` |
| P-KEYFRAME Kontext fallback | `[KONTEXT] Max Multi` |
| P-MOTION Kling Native | `[KLING-NATIVE]` + `Polling task` + `succeed` |
| P-MOTION Veo | `[VEO]` + analogous markers |
| P-PERFORMANCE Hedra | `[HEDRA]` + analogous markers + audio source confirmation |
| PR-DIALOGUE Cartesia | `[CARTESIA] Generating` |
| PR-DIALOGUE ElevenLabs | `text-to-speech/<voice_id>` HTTP request log |
| P-CHIEFDIR | `[DIRECTOR] decision=<APPROVED|MODIFIED|BLOCKED>` (post-Phase-1 C-D3 closure) |
| P-DECOMPOSE LLMEnsemble | `[Ensemble] Judge: <model> picked <winner> with score <X>` (post-Phase-1 C-D2 closure) |
| Auto-approve plan | `[AUTO-APPROVE] plan: <decision>` (post-Phase-1 C-D3 part 2) |
| Auto-approve image | `[AUTO-APPROVE] image: composite=<X> threshold=<Y>` |
| C-D5 threshold conditional | `[AUTO-APPROVE] image_min_composite_kontext_fallback=0.78 applied` (post-Phase-1) |
| Tri-mix audio | `[VIDEO/AUDIO] tri-mix: voice+bgm+foley` |

### Falsifiability tightened

PREDICTIONs that can be satisfied by compensating mechanisms WITHOUT the intended mechanism firing are now invalid. The MARKER requirement closes that gap.

---

## §9. Pipeline upgrade roadmap

[READY — cycle-16 lessons folded]

### P0 — Cycle-16-mid closures (Tier-D-blockers)

| # | Item | Status |
|---|---|---|
| P0-1 | C-D3 ChiefDirector parse-robust + auto-approve DEFER-TO-MANUAL | [PHASE-1-DEPENDENT] |
| P0-2 | C-D4 PuLID-Flux pod hardening (custom node + InsightFace model + setup_runpod.sh) | [PHASE-1-DEPENDENT — director ships script; user-principal applies pod] |
| P0-3 | C-D5 KEYFRAME composite threshold conditional | [PHASE-1-DEPENDENT] |
| P0-4 (added in operator counter) | C-D2 LLMEnsemble parse-robust | [PHASE-1-DEPENDENT] |

### P1 — Important improvements (cycle-17 entry priority)

| # | Item | Files | LoC est. |
|---|---|---|---|
| P1-1 | Refine A9 pre-flight (production workflow class probes) | brief refinement + ~20 LoC test refactor | (this brief v2.0 itself; closure on documentation) |
| P1-2 | Cost-attribution audit (Sora phantom, Kling double-count, ElevenLabs multiplication) | `cost_tracker.py` provider-mapping audit | ~20-50 LoC + ~10 tests |
| P1-3 | Wire `log_llm` at all `llm/` call sites (F-F.2) | `llm/chief_director.py` + `llm/director.py` + `llm/ensemble.py` | ~20 LoC × 6 sites |
| P1-4 | Wire `CostTracker` at all `lip_sync.py` FAL call sites (F-F.1) | `lip_sync.py` | ~20 LoC × 10+ sites |
| P1-5 | Wire `storyboard_mode` toggle to call `generate_storyboard` (F-A.1/F-B.1) | `phase_c_ffmpeg.py` Kling dispatch block | ~50 LoC |
| P1-6 | Replace per-shot `optimize_shot_prompt` with `batch_optimize_scene` (F-A.3) | `cinema/shots/controller.py` scene-iteration | ~20 LoC refactor |
| P1-7 | Implement `validate_lora_quality` real ArcFace scoring (F-A.2) | `prep/lora_training.py:515` | ~100 LoC |

**Cycle-17-entry status (verified):** P1-4 (lipsync cost-tracking) **shipped** at `46a2cfa` — both `generate_lip_sync_video` call sites now `record_api_call`; per-engine **pricing** is the remaining follow-on (records $0.00 until lipsync engines are in the cost table). P1-1 (A9 pre-flight refinement) is this brief itself. P1-2 / P1-3 / P1-5 / P1-6 / P1-7 remain open (GPU-gated or cycle-17-mid+). The cycle-17 image-routing wire (`d28474e` / `d73eebb`) is a NEW capability not in the original P-list (the image twin of dialogue routing).

### P2 — Quality lifts (cycle-17 mid+)

| # | Item | Files | LoC est. |
|---|---|---|---|
| P2-1 | Wire `hires_fix` nodes in `_inject_post_passes` (F-B.3 / F-C.2) | `quality_max.py:728` + pod ComfyUI node verify | ~20 LoC + verification |
| P2-2 | Wire `validate_multi_identity` for multi-character shots (F-A.4) | `cinema/shots/controller.py` post-motion validation | ~30 LoC |
| P2-3 | Persist scene/shot dialogue back to project schema fields (C-D-persist-1) | `dialogue_writer.py` writes to `scene.dialogue_lines` | ~30 LoC |
| P2-4 | num_shots authoritativeness decision: enforce contract OR document advisory (C-D1) | brief v2 + `domain/scene_decomposer.py` | ~10 LoC + doc |
| P2-5 | C-D-doc-1 docstring drift fix: `create_character_with_images` 4→6 angles | `domain/character_manager.py:114-122` | ~5 LoC |

### P3 — Long-term (cycle-18+)

| # | Item |
|---|---|
| P3-1 | Move from "5-shot Kling Native default" to optional `storyboard_mode` batched latent-space path for max cross-shot identity coherence |
| P3-2 | Tier D PA-IDENTITY sweep (0.60/0.70/0.80) — measures real identity-anchor sensitivity (requires PuLID working) |
| P3-3 | Cost-prediction-vs-actual telemetry — track per-cell PREDICTION vs ACTUAL spend over N runs |
| P3-4 | `ARCHITECTURE.md §12 Audio pipeline` cleanup note for LV-1 C-B2 root-cause precision |
| P3-5 | Optional: HiDream-I1 backbone swap path for max-tier product-hero shots |
| P3-6 | Pipeline self-diagnostic dry-run mode (per operator brief v1 §6.4 #10) |
| P3-7 | Identity-consistency contract (PuLID required vs fallback ok config; per operator brief v1 §6.4 #11) |
| P3-8 | P-CHIEFDIR + P-DECOMPOSE decoupling (per operator brief v1 §6.4 #12) |

---

## §10. Process discipline (cycle-16 lessons → cycle-17 protocol)

[READY]

### Race-shape catalog (cycle-16 → cycle-17)

| Race # | Shape | N | First instance | Latest instance | Codification status |
|---|---|---|---|---|---|
| N=1 | Concurrent dispatch-claim race (user-direction reaches both seats simultaneously without owner spec) | 2 | T19:19Z dispatch-claim race | T22:25Z synthesis-doc + T22:33Z proposal race | **Rule #16 candidate** (cycle-17+ standalone proposal OR bundled with brief v2.0) |
| N=2 | Stale-mailbox-content assertion | 1 | operator `2426f59` item #1 | (none since) | watch |
| N=3 | Pre-write re-verify gap | 1 | operator T19:31:45Z | (Rule #4 + #7 + Candidate #8 RECENCY discipline tightening landed) | resolved via existing rules |
| N=4 | Director side-channel inline-fix without mailbox signal during operator's tier execution | 1 | director audit `a79c59` + 3 fixes during operator Tier C | none since | watch; director §8.1 self-discipline ack |

### Rule #16 codification (CODIFIED — cycle-17, Protocol Bundle v5.4)

[RESOLVED — user-principal authorized; codified `7773502` (v5.4). Q4 decision: codify. Verified via `git show 7773502` + `grep 'Rule #16' CLAUDE.md`.]

Rule #16 is now a binding CLAUDE.md rule (design home: brief v2.0 §8.2 + ADR-015; binding mirror commit `7773502`):

> **Rule #16: User-direction without owner-spec.** When user-principal direction reaches both seats simultaneously without explicit owner specification, both seats MAY interpret it as joint-team work and produce complementary parallel deliverables. The second seat to ship (by git timestamp) MUST send a follow-up coordination event within 30 minutes of the second commit landing, acknowledging the parallel deliverable + proposing a convergence path (REPLY-cycle / merge / delegation / further parallelism). A pre-commit-detected variant: discard the pre-commit and offer the content as REPLY-cycle input. Silent ship of a second deliverable without a coordination event = Rule #2 §"Signaling" violation.
>
> **Why this matters:** cycle-16's Shape-A race produced NET-POSITIVE complementary coverage. The capstone instance: the user-principal handed the same brief-2.0 advisory to BOTH seats; both independently designed a near-identical insight-achievement mechanism (cold to each other), and the operator's pre-commit-caught draft — discarded per the variant, offered as REPLY input (`fd3dc33`) — contributed a Rule #12 grep-verified marker correction + a divergence classification a solo director pass would have missed. Rule #16 preserves that value while requiring the convergence discipline.
>
> **Beneficiary per Rule #11:** `both` seats (symmetric obligation — whichever ships second owes the convergence event).
>
> **Codified SHA:** `7773502` (Protocol Bundle v5.4; empirical basis N=3 Shape-A instances + the advisory-convergence capstone). Working criteria C1–C4 dogfooded per the Rule #14/#15 pattern. Brief v2.0 §8.2 is the design home; `7773502` is the binding CLAUDE.md mirror.

### Q9 sync joint-seat scope clarification (CANDIDATE)

[CONDITIONAL — depends on Q4 user-principal decision]

Cycle-16 saw director side-channel inline-fix without mailbox signal during operator's Tier C execution (C-D-coord-1). Director's §8.1 self-discipline acknowledgement is the cycle-16 resolution. For cycle-17+:

Option (a) Accept self-discipline; observe for N=2 trigger
Option (b) Narrow Q9: "no parallel ship without mailbox fyi event during operator's tier execution"
Option (c) Broaden Q9: "director may parallel-ship if disjoint scope + mailbox fyi post-ship"

Both seats prefer (a) per cycle-16-mid convergence; user-principal final call.

### Lane V/D/S coalesced range cadence (READY)

Per Rule #9 §"Parallelism" CC-1 from cycle-12+ + cycle-16 application:
- Lane V coalesced range at tier-end DEFAULT (not per-commit)
- CRITICAL findings trigger immediate parallel Lane V per CC-1 exception
- Lane D doc-sync follows code commit on subsystem touches per role partition Sh
- Lane S pre-dispatch scout opt-in per Rule #14 §"Lane S"

### Rule #14 operator-driven Lane B exercise telemetry

| Cycle | Lane B dispatches | Cumulative N | Notes |
|---|---|---|---|
| Cycle-11 | B-005 (`c296105` 10 sites domain/project_manager.py) | 1 | First operator-driven Lane B; codified pattern |
| Cycle-12 | B-006-broad-A (`5b68776` 6 sites) | 2 | Pattern stabilizes |
| Cycle-16-mid Phase 1 (pending) | C-D3-1 + C-D3-2 + C-D5 + C-D2 | 3-6 | Substantial cycle-16 exercise |

Per Rule #14 R14 working criteria C1-C4: dispatch-claim cites Rule #14 + 5-criteria check; implementer commit body includes Rule #14 reference; per-instance wall-clock measurable.

---

## §11. Acceptance criteria framework

[READY]

### Per-cell PASS / DEGRADED / FAIL pattern

Every test cell has 3 explicit states:

- **PASS** — output matches PREDICTION + REQUIRED MARKER present
- **DEGRADED** — output matches PREDICTION OR REQUIRED MARKER present but not both (compensating mechanism; closure-status-uncertain)
- **FAIL** — neither output nor marker matches; finding filed

### Per-tier verdict pattern

Tier-end verdict aggregates per-cell:

- **CLEAN** — all cells PASS
- **PASS-WITH-N-DEGRADED** — some cells DEGRADED; not blockers
- **PASS-WITH-N-MINOR / N-IMPORTANT / N-CRITICAL** — findings filed per severity; tier still produces output
- **FAIL** — critical blocker prevents tier completion

### Cost envelope per tier

| Tier | Estimated cost | $50 cap fit |
|---|---|---|
| A | $0 | ✅ |
| B regression | $2-4 | ✅ |
| C-rerun-validation | $5-10 | ✅ |
| D PA-* sweep | $15-25 | ✅ (if alone) |
| E closed-finding regression | $0-2 | ✅ |
| F audit re-execution | $0 | ✅ |
| **Cycle-17 entry total (A+B+E+F)** | **$2-6** | ✅ ample |
| **Cycle-17 + C-rerun** | **$7-16** | ✅ |
| **Cycle-17 + C + D** | **$22-41** | ✅ within cap |

### Wall-clock estimate per tier

| Tier | Wall-clock |
|---|---|
| A | ~30 min |
| B regression | ~10-15 min |
| C-rerun-validation | ~30-50 min |
| D PA-* sweep (multi-cell) | ~4-8 h (depending on cell count) |
| E pytest cells | ~5 min |
| E synthetic E2E | ~15 min |
| F audit subagent | ~10 min |

---

## §12. Open questions for cycle-17+ scope

[READY — operator open questions; director may add]

### Q-V2-1: Tier C-fresh-scope variants

For cycle-17+ Tier C-fresh-scope (after Tier C-rerun-validation passes):

- Multi-character interaction (2 characters in scene; tests F-A.4 multi-identity wire)
- Multi-language switching (Korean + English dialogue lines in same scene; tests I-B1 dispatcher multi-lang)
- Longer reel (5 shots single scene OR 2 scenes × 3 shots; tests P-CHIEFDIR + cross-scene continuity)
- Commercial-tier (product/object shot; tests `make_object` + branded-product pipeline)

Pick 1 for cycle-17 mid OR cycle-18 entry.

### Q-V2-2: HiDream-I1 backbone exploration timing

(Per F-C.3 stub in director's max-quality audit; per operator brief v1 §6.4 P3-5.)

**Update (cycle-17):** the image-engine ROUTING plumbing is now wired (`d28474e` optimizer `suggested_image_api` → quality_max HiDream gate; `d73eebb` user-pin guard) — `HIDREAM_I1` now reaches the gate instead of always reading `None`. **Firing + output-quality (backbone) exploration remains cycle-18+ and GPU-gated** (needs the pod's HiDream/PuLID custom node + a product/hero shot to actually fire). The open question narrows from "wire + explore" to "explore the now-reachable backbone."

### Q-V2-3: Pod refresh / migration timing

Pod `525nb9d5cc0p3y` is the long-running RunPod instance from cycle-15. Refresh schedule? Migration to dedicated infrastructure?

Cycle-17+ planning.

### Q-V2-4: Brief v2.0 promotion-to-final timing

This scaffold ships at cycle-16-mid. Brief v2.0 promotion-to-final happens after Phase 4 audit results land. Cycle-17 entry use?

[READY]

---

## §13. Race-ack + telemetry summary (cumulative cycle-16)

[READY — point-in-time snapshot; cycle-17+ updates as new instances land]

### Cumulative findings (cycle-15 entry → cycle-16-mid)

- Total findings filed: 32 (3 Tier A + 13 Tier B + 14 Tier C + audit overlap deduplicated)
- Closed: 17 + Phase-1-pending (TBD; expected +4 → 21)
- Open advisory (non-blocking): 6
- Open IMPORTANT: 3 + Phase-1-pending closures
- Open CRITICAL: 2 (C-D3 + C-D4) — both Phase-1-pending closure
- Open cost-attribution: 3
- Open process: 1 (C-D-coord-1; director self-discipline)

### Cumulative cost (cycle-15 entry → cycle-16-mid)

- Cycle-15 entry: $0
- Cycle-16 entry (pre-flight + Tier A): $0
- Cycle-16 Tier B: ~$2.10-2.65
- Cycle-16 Tier C: $6.4508
- Cycle-16-mid Phase 1 (pending): $0-2
- Cumulative: **~$8.55-9.10 of $50 hard cap (17-18%)**
- Tier D headroom: $40-41

### Cumulative wall-clock (cycle-15 entry → cycle-16-mid)

- Cycle-15 entry brief authoring + Tier A scaffolding: ~6h
- Cycle-16 Tier A + Tier B + Tier C: ~5h
- Cycle-16 Tier C tier-end + verification-report + closing-report + brief v2 scaffold: ~3h
- Cumulative: **~14h cycle-15-entry → cycle-16-mid**

### Pytest baseline progression

```
Cycle-15 baseline:           866/3/0
Cycle-15 entry post-audio:   925/3/0
Cycle-16 post-VG-B1+LV-2:   945/3/0
Cycle-16 post-I-B2+M-B1:    963/3/0
Cycle-16 post-M-B2:         973/3/0
Cycle-16-mid Phase 1:       [PHASE-1-DEPENDENT; estimated +30-60 → 1000-1030]
Cycle-17 entry (pre-Ph1):   1129/3/10  (tests/unit/; HEAD e16bf85; verified `pytest tests/unit/` 2026-05-28 — exceeds the post-Phase-1 estimate; cycle-16-close + cycle-17-entry tests landed beyond the C-D cells, and Phase 1 itself has not yet run)
```

---

## §14. Sign-off + dependencies

[READY]

### Brief v2.0 author chain

1. **SCAFFOLD (this file)** — operator-seat at cycle-16-mid prep
2. **STRATEGIC-SYNTHESIS FILL-IN** — director-seat post-Phase-4 (Sh role partition default)
3. **OPERATOR REPLY** — operator-seat REPLY-cycle on director's draft (per cycle-12 v5.2 + cycle-16 work-split convergence)
4. **PROMOTION TO FINAL** — at cycle-17 entry; supersedes brief v1.0

### Brief v2.0 promotion-to-final pre-conditions

[PHASE-DEPENDENT]

- [ ] Phase 1 P0 fixes all landed (C-D2 + C-D3 parts 1+2 + C-D5)
- [ ] Phase 1 director-side setup_runpod.sh harden landed (C-D4 script)
- [ ] User-principal pod-side C-D4 applied
- [ ] Phase 2 Tier C-rerun-validation completed
- [ ] Phase 3 Tier E pytest cells added + green
- [ ] Phase 4 Tier F audit subagent dispatched + delta report received
- [ ] All Phase 1-4 lessons-folded into brief v2.0 sections marked [PHASE-N-DEPENDENT]
- [ ] User-principal sign-off

### ADR for cycle-16 fixes (separate doc)

Per role partition Sh, ADRs are director-default. Cycle-16 fixes (C-D2, C-D3 parts 1+2, C-D5, C-D6 already at `024723d`, C-D4 setup_runpod.sh harden) get an ADR entry in `DECISIONS.md` at Phase 6.

---

## §15. §15 smoke test block (mandatory per CLAUDE.md)

[READY — updated for cycle-16-mid HEAD]

```bash
# §15 smoke — cycle-16-mid HEAD verification
cd /Users/hyungkoookkim/Content

# Working tree clean
git status --short
# Expected: empty (modulo brief v2 scaffold + Phase 1 in-progress)

# Pytest baseline
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1
# Expected (cycle-16-mid pre-Phase-1): 973 passed, 3 skipped, 10 subtests passed
# Expected (cycle-16-mid post-Phase-1): 1000-1030 passed, 3 skipped

# Smoke
.venv/bin/python scripts/ci_smoke.py
# Expected: OK

# Frontend tsc
(cd web && npx tsc --noEmit) 2>&1 | head -5
# Expected: empty (no errors)

# Pod
curl -sI --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/
# Expected: HTTP/2 200

# UNETLoader (cycle-16 C-B1 closure)
curl -s --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/UNETLoader | jq -r '.UNETLoader.input.required.unet_name[0]'
# Expected (cycle-16-mid): ['FLUX1/flux1-dev-fp8.safetensors']

# PulidInsightFaceLoader (cycle-16 C-D4 status)
curl -s --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/PulidInsightFaceLoader | head -5
# Expected (pre-Phase-1-pod-apply): missing_node_type error
# Expected (post-Phase-1-pod-apply): valid input schema
```

---

## §16. Brief-v2.0 SCAFFOLD changelog

[READY]

### v2.0-SCAFFOLD (2026-05-28 cycle-16-mid)

- Initial scaffold by operator-seat post-debate-convergence + post-user-prep-direction
- §0-§5 + §11-§13 + §15 fully drafted (Phase-1-4-independent)
- §6 + §7 + §8 fully drafted (NEW Tier E + Tier F + PREDICTION v2 — design-only; pre-execution)
- §9 + §10 drafted with cycle-16 lessons + Phase-1-dependent placeholders
- §3 + §4 + §14 marked [PHASE-N-DEPENDENT]; structure READY but data pending Phase 1-4 results

### v2.0-SCAFFOLD-r2 (2026-05-28 cycle-17 entry — director partial fill-in)

Director-seat strategic-synthesis partial fill-in of the GPU-independent items the cycle-17 session resolved (per user-principal direction to advance fillable sections pre-Phase-1; full promotion remains phase-gated per §14). All cited SHAs verified via `git show` (CLAUDE.md strategic-doc verification discipline, Rules 1–3):
- §1 — added "Cycle-17 entry delta" (Rule #16 codified, F-F.1 wired, HiDream routing, Suno rewire, GitNexus removal/ADRs).
- §2 A3 + §13 — cycle-17-entry pytest baseline (`tests/unit/`-scoped, 1129/3/10, HEAD `e16bf85`).
- §7 — F-F.1 row → CLOSED (`46a2cfa`).
- §9 — P1 cycle-17-entry status note (P1-4 shipped; image-routing flagged as new capability).
- §10 — Rule #16 → CODIFIED (`7773502`, v5.4); Q4 conditional resolved.
- §12 — Q-V2-2 HiDream timing narrowed (routing wired; backbone exploration still cycle-18+).
- Phase-dependent sections (§3 markers, §4/§5 results, §6 Phase-1 cells, §13 cumulative findings/cost) UNTOUCHED — still await the pod + Phase 1–4. Operator REPLY (author-chain step 3) still pending.

### Pending updates (post-Phase-1-4)

- §3 Tier B regression specific markers (post Phase 1 fix commits)
- §4 Tier C validation results (post Phase 2)
- §5 Tier D scope finalization (post Tier C-rerun-validation outcomes)
- §6 Tier E TE-C-D2 / TE-C-D3-1 / TE-C-D3-2 / TE-C-D5 cell additions (post Phase 1)
- §7 Tier F audit delta report (post Phase 4)
- §10 Rule #16 codification — DONE (`7773502`, v5.4; folded in the cycle-17 r2 fill-in)
- §13 Cumulative telemetry (post Phase 4 baseline)
- §14 Promotion-to-final checklist completion

### Promotion-to-final

When all [PHASE-N-DEPENDENT] placeholders are filled, scaffold is renamed `BRIEF-comprehensive-test-v2-2026-05-2X.md` (matching promotion date) and supersedes brief v1.0.

---

Signed,
Operator-seat — 2026-05-28 cycle-16-mid, brief v2.0 SCAFFOLD authored per user-principal "prepare for brief 2.0" direction + Phase-1-4-independent sections fully drafted + Phase-N-dependent sections placeholdered + standby for director-seat strategic-synthesis fill-in at Phase 6 OR user-principal further direction

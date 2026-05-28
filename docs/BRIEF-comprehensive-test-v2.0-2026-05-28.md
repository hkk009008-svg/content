---
brief-id: comprehensive-test
version: v2.0
authored-by: director-seat (full re-author per user-principal Q5 + Q7)
authored-at: 2026-05-28 (cycle-16 mid → close)
supersedes: docs/BRIEF-comprehensive-test-2026-05-27.md (v1.0; preserved for audit trail)
parent-docs:
  - docs/CYCLE-16-CLOSING-REPORT-2026-05-27.md (director comprehensive synthesis; e4615c7)
  - docs/BRIEF-tier-d-validation-2026-05-28.md (operator validation-test design; 2c9ee9f)
  - docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md (operator scaffold; uncommitted, offered as REPLY-cycle input)
related-rules: 1, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16-candidate
HEAD-at-authoring: 65903e6 (rebased mentally onto d16733f — operator's LV-1 ARCH §12.6 doc-sync landed during authoring; non-conflicting Lane D)
pytest-baseline: 973/3/0 (verified 2026-05-28 via `.venv/bin/python -m pytest tests/unit/ -q --tb=no` → "973 passed, 3 skipped, 10 subtests passed in 29.03s")
status: DIRECTOR DRAFT — pending operator REPLY-cycle then user-principal sign-off. Sections marked [PHASE-1-DEPENDENT] etc. finalize during cycle-17 execution; this draft is the working brief that supersedes v1.0.
---

# Comprehensive Test Brief v2.0

> **What this is.** The cycle-17+ comprehensive test brief, re-authored from
> v1.0 (`BRIEF-comprehensive-test-2026-05-27.md`) with every cycle-16 lesson
> folded in. v1.0 was the predictive-harness debut; it ran end-to-end through
> Tier C and earned 32 findings + 10+ implemented-but-unutilized features. v2.0
> closes the gaps v1.0's own execution exposed: the pre-flight probe surface
> diverged from the workflow surface (A9), predictions were satisfiable by
> compensating mechanisms without the intended mechanism firing (the PuLID
> illusion), and there was no regression guard for closed findings or
> quality-debt trend tracking.
>
> **What this is NOT (yet).** This is the director-authored v2.0 draft at
> cycle-16-mid, written BEFORE cycle-17 Phase 1 fixes ship. Sections that
> depend on not-yet-shipped fixes (verification markers for C-D2 / C-D3 / C-D5
> closures, the post-pod-fix PuLID probe results, the Tier F audit delta) are
> explicitly flagged `[PHASE-N-DEPENDENT]`. Per the verification discipline
> (CLAUDE.md Rule 1 + this brief's own §4 marker discipline), v2.0 does NOT
> fabricate markers for fixes that have not landed. Promotion-to-final happens
> at cycle-17 entry once Phases 1-4 complete and the placeholders fill.

---

## §0. Front matter — what changed v1.0 → v2.0

### Tier structure (6 tiers; expanded from v1.0's 4)

| Tier | Purpose | New vs v1.0? | Cost env |
|---|---|---|---|
| **A** — Pre-flight | Verify substrate, smoke, pytest, pod, LLM keys, **and actual workflow node classes** | REFINED (A9 probe gap + A10 manual-hardening inventory closed) | $0 |
| **B** — Single-shot regression | Korean dialogue probe; verify the 9 Tier-B closures + VG-B1 hold | same scope; now framed as a **regression guard** with closure markers | $2-4 |
| **C** — Reel scope (multi-shot) | Cheongsam Korean reel; per-finding acceptance criteria | scope tightened with C-D PASS/DEGRADED/FAIL acceptance criteria | $5-10 |
| **D** — PA-* parameter sweep | Identity / motion / image / sampling / lipsync / audio / foley sweeps | requires PuLID-FLUX actually working (post-C-D4); **DEFERRED** until then | $15-25 |
| **E** — Closed-finding regression suite | Per-finding cells exercising each cycle-16 closure's code path | **NEW** (closing-report §6.4) | $0-2 |
| **F** — Audit re-execution | Re-dispatch max-quality audit subagent; compare delta vs `a79c59` | **NEW** (closing-report §6.5) | $0 (subagent only) |

### The eight v2.0 improvements over v1.0

1. **PREDICTION discipline tightened to require a mechanism-marker** (not just an output property). Closes the cycle-16 "compensating mechanism" gap — Tier C's keyframes LOOKED identity-locked via Kling-side AuraFace carry while PuLID never fired (C-D4). See §4.
2. **A9 pre-flight probes the ACTUAL workflow node classes** referenced in production workflow JSONs, not just `CheckpointLoaderSimple`. The v1.0 A9 returned a misleading PASS while `UNETLoader.unet_name` was empty (C-B1 + C-D4 cascade). See §3.
3. **A10 NEW** — full inventory + per-step probe of the cycle-15 "6 manual hardening steps" that `setup_runpod.sh` does not idempotently install. C-B1 closed step 1; C-D4 surfaced steps 2-3. See §3.
4. **Tier E + Tier F NEW** — closed-finding regression guard + audit re-execution with quality-debt trend telemetry. See §6, §7.
5. **Per-cell acceptance criteria are explicit PASS / DEGRADED / FAIL states** (operator brief v1 §5.4 pattern generalized). DEGRADED is the new middle state for "output present but marker absent." See §2.4, §5.
6. **Cost envelope per tier updated with cycle-16 actuals** + a dedicated cost-attribution section (§9) documenting the phantom-Sora / Kling-double-count / ElevenLabs-multiplication bugs per user Q2.
7. **Pipeline upgrade roadmap with P0/P1/P2/P3 priority** + an implemented-but-unutilized catalog (§10) per user Q3 and audit `a79c59`.
8. **Rule #16 codification** (per user Q4) in the process-discipline section, with the cycle-16 race-shape catalog re-numbered onto a stable shape-based scheme. See §8.
9. **Insight-achievement reframe** (per user-principal design advisory `brief-2.0-advisory.md`). The test's *product* shifts from a pass/fail verdict to **located divergence-points** — places where the brief failed to transmit intent so behavior matched expectation. PASS/DEGRADED/FAIL becomes the *detector*; the divergence-point is the *product*. Mechanism: intent-encoding + purpose-verification + divergence-logging, piloted incrementally. See §2.6 (frame) + §8.6 (mechanism).

---

## §1. Coordination model

### §1.1 Two-seat team, v5+ protocol bundle

This brief is executed by the two-seat team (director-seat + operator-seat,
both serving the user-principal) under Protocol Bundle v5.3, proven across
cycles 6-16 with 15 rules active. The seats are **equal within their
specialization** (CLAUDE.md Rule #10 joint-team mode); specialization is
cognitive-load distribution, not hierarchy.

| Lane | Owner-default | Trigger |
|---|---|---|
| Brief authoring / ADRs / push / strategic synthesis | Strategic-seat-default (director) | this brief; cycle-17 phase plan |
| Lane V post-commit independent verification | Operational-seat-default (operator) | any `feat`/`refactor`/`fix` commit; coalesced per Rule #9 CC-1 |
| Lane D post-commit doc-sync | Operational-seat-default (operator) | commits touching `cinema/` / `domain/` / `web_server.py` / `cinema_pipeline.py` |
| Lane S pre-dispatch scout | Operational-seat-default (operator) | director `scout-request` before a Lane B dispatch |
| Implementer dispatch (Lane B) | Strategic-seat-default (director) **OR** operator-driven per Rule #14 | new-session implementer subagent |

### §1.2 Brief execution flow (per Q5 path)

```
director drafts brief v2.0  →  operator REPLY-cycle (≤2 cycles per v5 disagreement protocol)
  →  user-principal sign-off  →  joint execution (cycle-17 entry)
```

This document is step 1. Operator REPLY-cycle is step 2 (bundled or
per-section per operator discretion; §5 test cells + §7 Tier F spec + §11
cycle-17 phase plan are the operator's deepest-ownership review surfaces).

### §1.3 Rule #14 operator-driven Lane B (cycle-17 Phase 1 relevance)

Cycle-17 Phase 1 P0 fixes are dispatched as **operator-driven Lane B** where
the five Rule #14 selection criteria hold (single/sibling files; canonical
pattern reference; ≤150 production LoC; no cross-cutting public-API impact;
Rule #13 symmetric audit clears). The C-D2 / C-D3 / C-D5 LLM-parse-robustness
fixes are textbook ODLB candidates — they apply the documented
`response_format={"type":"json_object"}` + retry-with-correction pattern to a
small set of sibling LLM call sites. See §11 for the per-fix ownership matrix.

### §1.4 Rule #16 candidate (per Q4)

The "user-direction reaches both seats without explicit owner specification"
race shape reached 3 cumulative cycle-16 instances. User-principal Q4
authorized codifying it as Rule #16 in this brief's §8. The candidate rule
text, beneficiary analysis, and the reconciled race-shape catalog are in §8.

---

## §2. Scope

### §2.1 Tier sequencing (cycle-17 entry)

v2.0 reorders cycle-17 entry around a **validation-first** principle (operator
§4 label refinement, converged): prove the cycle-16 closures hold and the
quality-debt trend is flat BEFORE spending on new reel-scale generation.

```
Tier A refined pre-flight (verify cycle-16 fixes hold; A10 manual-step audit)   $0
  ↓
Tier B regression (verify all 9 Tier-B closures + VG-B1 hold)                    $2-4
  ↓
Tier E closed-finding regression suite (mostly pytest; one synthetic E2E)        $0-2
  ↓
Tier F audit re-execution (subagent only; quality-debt delta vs a79c59)          $0
  ↓
Tier C-rerun-validation (after Phase 1 P0 fixes land; per-finding criteria)      $5-10
  ↓
Tier D PA-* parameter sweep (ONLY after PuLID-FLUX confirmed working)            $15-25 [DEFER]
```

Cycle-17 entry total (A+B+E+F): **$2-6**. With C-rerun: **$7-16**. With D:
**$22-41** — within the $50 hard cap with margin.

### §2.2 In scope

Pipeline phases (decompose → keyframe → motion → performance → identity →
assembly), the four review gates + screening, LLM prompt classes (PR-*),
image/video/performance/identity/audio parameters (PA-*), cost tracking, and
HTTP surfaces A (web_server endpoints) + B (CLI-equivalent flows through
`cinema_pipeline.py`). New in v2.0 scope: closed-finding regression (Tier E)
and quality-debt audit trend (Tier F).

### §2.3 Out of scope

Distributed deploy, multi-tenant isolation, auth, vendor swaps, load testing.
Unchanged from v1.0.

### §2.4 Acceptance-criteria framework (PASS / DEGRADED / FAIL)

Every cell carries three explicit states. The DEGRADED state is v2.0's answer
to the cycle-16 compensating-mechanism illusion:

- **PASS** — output matches PREDICTION **and** the required mechanism-marker is present in the log.
- **DEGRADED** — output matches PREDICTION **or** the marker is present, but **not both** (a compensating mechanism produced acceptable output without the intended mechanism firing; closure-status is uncertain and must be investigated).
- **FAIL** — neither output nor marker matches; a finding is filed.

Per-tier verdict aggregates per-cell:

- **CLEAN** — all cells PASS.
- **PASS-WITH-N-DEGRADED** — some cells DEGRADED; not blockers but tracked.
- **PASS-WITH-N-MINOR / N-IMPORTANT / N-CRITICAL** — findings filed per severity; tier still produced output.
- **FAIL** — a critical blocker prevented tier completion.

### §2.5 Cost + wall-clock acceptance bands

| Tier | Cost | Wall-clock | $50 cap fit |
|---|---|---|---|
| A | $0 | ~30 min | ✅ |
| B regression | $2-4 | ~10-15 min | ✅ |
| E closed-finding regression | $0-2 | ~5 min pytest + ~15 min synthetic E2E | ✅ |
| F audit re-execution | $0 | ~10 min subagent | ✅ |
| C-rerun-validation | $5-10 | ~30-50 min | ✅ |
| D PA-* sweep (multi-cell) | $15-25 | ~4-8 h | ✅ (if alone) |

A cell that exceeds its cost band by >2× without a logged reason is itself a
finding (cost-attribution class — see §9).

### §2.6 Test philosophy — insight-achievement frame (advisory-integrated)

Per the user-principal design advisory (`brief-2.0-advisory.md`), v2.0 reframes
what the test is *for*. This frame governs the whole brief; hold it throughout.

**The product is a located divergence-point, not a verdict.** The
PASS/DEGRADED/FAIL machinery of §2.4 is the *detector*. The *product* is the
**divergence-point**: the specific place where the agent's task-model diverged
from the predictor's intent-model — i.e., where the brief failed to transmit
intent clearly enough that behavior matched expectation. Each divergence-point
is an actionable target for enriching the next brief.

**The core distinction — read once, hold throughout.** The goal is
**better-aligned behavior achieved by encoding intent and purpose more richly
into the protocol** — NOT agent self-understanding in any literal sense.

- *In scope:* briefs + verification that carry *why*/*intent*, so an agent
  reasons from purpose when a spec doesn't cover a case, and local decisions
  extrapolate correctly from the goal.
- *Out of scope:* any mechanism that treats agent-generated self-description as
  genuine introspective self-knowledge. An agent's "what I'm doing and why" text
  is plausible reconstruction, useful as *signal* — not a true internal causal
  trace. Do not mistake it for real self-access.

**The failure mode to avoid.** Optimizing toward output that *looks like*
deepening self-understanding (more elaborate rationale-talk) instead of toward
*actual better-aligned behavior* (decisions that match intent). The first is
easy to produce and measure; the second is the goal. **The protocol must not
reward rationale-talk volume.** This is the same appearance-vs-substance /
prevention-vs-verification discipline the protocol applies elsewhere (cf. Rule
#12 type-declaration-is-not-write-evidence) — applied here too.

**The metric.** **Prediction-match rate ↑ and divergence-point frequency ↓
across cycles, with no increase in rationale-talk.** That decreasing-divergence
trend is the measurable evidence the mechanism works. If divergence frequency
does *not* fall, intent-encoding is producing rationale-talk without behavioral
effect — the failure mode above; kill or rework the mechanism (§8.6.4).

**Tightening = intent-clarification.** Protocol-tightening is not merely
rule-reduction; it is reducing the places where an agent must *guess* intent.
The divergence-points (§8.6.3) are a direct map of where intent leaks — so they
tell us **where to tighten next**, evidence-driven, consistent with the existing
N=2 emergence-from-evidence discipline. Tighten there first, not speculatively.

The mechanism that operationalizes this frame (intent-encoding +
purpose-verification + divergence-logging, as candidates piloted incrementally)
is specified in §8.6.

---

## §3. Tier A — Refined pre-flight (cycle-16 lessons folded)

**Acceptance:** all A1-A10 PASS with green output. Any single FAIL blocks Tier
B until closed. Multi-step FAIL → pod-side audit before any paid execution.

### A1-A8 (unchanged from v1.0 except where noted)

| Step | Command | Expected |
|---|---|---|
| A1 working tree clean | `git status --short` | empty (modulo in-flight brief + Phase-1 work) |
| A2 §15 smoke | `.venv/bin/python scripts/ci_smoke.py` | `OK` (exit 0) |
| A2.3 frontend build | `(cd web && npm run build)` | vite exit 0 (~740ms). **Do not skip** — M-A2.3 lesson: "tsc covers types" is not a substitute; build catches bundler-level breakage. |
| A3 pytest baseline | `.venv/bin/python -m pytest tests/unit/ -q --tb=no \| tail -1` | `973 passed, 3 skipped, 10 subtests passed` at cycle-16-mid; **~1000-1030 expected post-Phase-1** (C-D2/C-D3/C-D5 test additions). [PHASE-1-DEPENDENT final N] |
| A4 tsc | `(cd web && npx tsc --noEmit)` | empty (exit 0) |
| A5 pod HTTP | `curl -sI https://525nb9d5cc0p3y-8188.proxy.runpod.net/` | `HTTP/2 200` |
| A6 LLM keys | (9-key prefix probe, below) | 9 non-empty prefixes |
| A7 GhostFaceNet weights | `ls -la weights/GhostFaceNet.pt` | exists; ~17.3 MB |
| A8 baseline projects | `find domain/projects -name "project.json" \| wc -l` | baseline count recorded |

**A6 9-key probe** (refined per I-A6.1 closure):

```bash
.venv/bin/python -c "from config.settings import settings; print(settings.anthropic_api_key[:8], settings.openai_api_key[:8], settings.google_api_key[:8], settings.gemini_api_key[:8], settings.fal_api_key[:8], settings.kling_access_key[:8], settings.elevenlabs_api_key[:8], settings.cartesia_api_key[:8], settings.suno_api_key[:8])"
```

> **I-A6.1 documentation note (closed):** `CINEMA_BUDGET_LIMIT_USD` env var
> does **not** exist. Budget enforcement is per-project at `cinema/core.py:99`
> reading `project["global_settings"]["budget_limit_usd"]` (default 50.0). The
> v1.0 brief §3:230 comment misled; v2.0 corrects it here. Set the cap via the
> project create payload, not an env var.

### A9 — REFINED ComfyUI node visibility (closes the C-B1/C-D4 cascade root)

**v1.0 problem.** A9 probed `CheckpointLoaderSimple.ckpt_name`, which PASSED —
FLUX was visible there. But production keyframe workflows reference
`UNETLoader.unet_name` (a *different* model directory), which was EMPTY. The
probe surface and the workflow surface diverged → all keyframes cascaded to FAL
FLUX-Pro without PuLID (C-B1), and Tier C later surfaced that even the FLUX
symlink fix was incomplete (C-D4). **A misleading PASS is worse than a FAIL.**

**v2.0 fix.** A9 derives its probe set FROM the production workflows.

#### A9.1 — list production workflow JSONs

```bash
ls -la cinema/workflows/*.json
```
Expected: at least `pulid.json`, `pulid_max.json`, `flux_kontext.json`, plus any others.

#### A9.2 — extract the union of `class_type` values the workflows reference

```bash
for f in cinema/workflows/*.json; do jq -r '[.[] | .class_type] | unique[]' "$f" 2>/dev/null; done | sort -u
```
Expected: the complete set of node classes the pipeline actually uses.

#### A9.3 — probe each referenced `class_type` against the pod

```bash
for class_type in <list-from-A9.2>; do
  curl -s "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/${class_type}" \
    | jq -r 'if (.[$class_type] // empty) then "OK" else "MISSING" end' --arg class_type "$class_type"
done
```
Expected: every referenced class returns a schema (NOT `missing_node_type`).

#### A9.4 — probe each loader node for non-empty model lists

```bash
curl -s ".../object_info/UNETLoader"             | jq -r '.UNETLoader.input.required.unet_name[0]'
curl -s ".../object_info/CheckpointLoaderSimple" | jq -r '.CheckpointLoaderSimple.input.required.ckpt_name[0]'
curl -s ".../object_info/LoraLoader"             | jq -r '.LoraLoader.input.required.lora_name[0]'
# extend for every *Loader with a <*>_name parameter found in A9.2
```
Expected: each returns a non-empty model list. **UNETLoader must list `FLUX1/flux1-dev-fp8.safetensors`** (C-B1 closure, currently verified GREEN).

#### A9.5 — probe PulidInsightFaceLoader specifically (C-D4 status gate)

```bash
curl -s ".../object_info/PulidInsightFaceLoader"
```
- **Pre-Phase-1 (current):** returns `missing_node_type` → PuLID-FLUX path UNAVAILABLE. This is the known C-D4 state.
- **Post-Phase-1 (target):** returns a valid input schema → PuLID-FLUX path available; Tier D PA-IDENTITY unblocked.

### A10 — Manual hardening-steps inventory (NEW; closes the C-D4 class)

Cycle-15 noted "6 manual hardening steps NOT in `setup_runpod.sh`." Cycle-16
closed step 1 and surfaced steps 2-3; the full set was never authoritatively
inventoried, which is exactly how C-D4 slipped through. A10 makes the set
explicit and probes each.

[Director's `setup_runpod.sh` harden commit `345f697` (cycle-17 Phase-1 entry) produced the authoritative list. Steps 2-4 are now script-side closed; 5-6 confirmed (see Status). Pod-apply (user, Q6) + A9.5 GREEN re-probe is the remaining half of C-D4.]

| # | Manual step | Probe | Status |
|---|---|---|---|
| 1 | FLUX1-dev-fp8 in `models/diffusion_models/` (symlink) | A9.4 UNETLoader | ✅ closed `eb6af85` + user pod symlink |
| 2 | ComfyUI-PuLID-Flux custom node in `custom_nodes/` | A9.5 + `ls custom_nodes/ComfyUI-PuLID-Flux` | ✅ script-side `345f697`; pod-apply pending (user Q6) |
| 3 | antelopev2 InsightFace model | `ls models/insightface/antelopev2/*.onnx` (5 files) | ✅ script-side `345f697` — canonical path is `models/insightface/models/antelopev2/` (nested `models/`; InsightFace `FaceAnalysis` resolution), symlinked at the stated path so this probe passes; pod-apply pending |
| 4 | `pip install --ignore-installed blinker` | `pip show blinker` | ✅ `345f697` (script Python-deps section) |
| 5 | torch pin `2.4.1+cu118` | `python -c "import torch; print(torch.__version__)"` | confirmed suspected — script leaves torch **unpinned** by design (pod-CUDA-specific; pin manually only if a torch/CUDA mismatch surfaces) |
| 6 | unconditional `pip install -r ComfyUI/requirements.txt` on restart | (script idempotency review) | confirmed — script installs ComfyUI reqs on first clone only; restart skips by design (acceptable; reqs stable post-clone) |

Director's Phase-1 `setup_runpod.sh` harden (`345f697`) authoritatively
enumerated the set; A10 is now the fixed checklist. Steps 1-4 are script-side
closed (step 1 also pod-applied); steps 5-6 confirmed as deliberate non-actions.
The remaining C-D4 work is the pod-apply (user, Q6) + A9.5 `/object_info`
re-probe returning a valid `PulidInsightFaceLoader` schema.

---

## §4. Predictive-harness format v2 (mechanism-marker required)

### §4.1 The v1.0 falsifiability gap

v1.0's harness asked "did the expected OUTPUT appear?" Cycle-16 Tier C showed
that's insufficient:

- **PREDICTION (v1.0):** "P-KEYFRAME PuLID-FLUX produces identity-locked keyframes."
- **ACTUAL:** PuLID never fired (C-D4 cascade → FAL Kontext + multi-angle refs). Identity *looked* locked because Kling Native's internal AuraFace carry held it at ~0.754 mean across shots. The output property matched; **the mechanism did not.**
- **v1.0 verdict:** technically PASS. **Reality:** the primary identity-anchor path was dead and the harness couldn't see it.

### §4.2 The v2.0 rule

**Every PREDICTION cell MUST name the specific log marker that confirms the
intended MECHANISM fired** — not just the output property. A prediction that
can be satisfied by a compensating mechanism without the intended mechanism
firing is invalid until a marker is added.

- **PREDICTION (v2.0):** "P-KEYFRAME PuLID-FLUX produces identity-locked keyframes — REQUIRED MARKER: log shows `via ComfyUI PuLID` **and** `PuLID face-locked to: <canonical>.jpg` **and** NO `missing_node_type` error."
- **Evaluation:** marker present + output present → **PASS**. Marker absent but output present → **DEGRADED** (compensating mechanism; investigate). Marker absent + output absent → **FAIL**.

### §4.3 Cell template (v2.0 — intent + marker + divergence-point fields)

```
Cell ID / phase / class
Stage in pipeline · Test tier · Estimated cost · Wall-clock prediction

INTENT (write BEFORE prediction):  ← NEW v2.0: what this cell serves + what a
  correct outcome accomplishes for the larger goal, in 1-2 concrete sentences.
  Adequacy test: could a cold-context agent, given ONLY this, choose correctly
  between two ambiguous implementation paths? If not, it is too vague to verify
  against (§8.6.1). Optional for mechanical cells; required where path is ambiguous.

PREDICTION (write BEFORE running):
  Expected output (shape)
  Expected content quality
  Expected latency · Expected cost
  REQUIRED VERIFICATION MARKER  ← NEW v2.0: the log substring(s) proving the mechanism fired
  Expected failure modes (top 3)
  Expected adjustment indicators (failure-mode → tweak-candidate)

ACTUAL (fill DURING/AFTER):
  Observed output · quality · latency · cost
  MARKER OBSERVED? (yes / no / partial)

DELTA:
  Classification: PASS | DEGRADED | MINOR-DELTA | MAJOR-DELTA | FALSIFIED
  Reasoning (must address marker presence explicitly)
  DIVERGENCE-POINT (when DELTA ≠ PASS):  ← NEW v2.0
    predicted / actual:  mechanism-level (the §4 marker hit/miss)
    classification:      INTENT-GAP | REAL-BUG | PREDICTION-ERROR
    fix-target:          §section whose intent under-transmitted (INTENT-GAP) |
                         finding ID + severity (REAL-BUG) | recalibrate predictor (PREDICTION-ERROR)
    Only INTENT-GAP feeds brief-enrichment + the §8.6.3 ledger — not every miss
    is an intent-gap; a REAL-BUG must NOT trigger a brief edit.

INSIGHT (if DELTA ≠ PASS): what this reveals · confidence · investigation cost
ADJUSTMENT: target (file:line / prompt / param) · tweak · risk · verification
```

Artifact at `docs/test-cells/<CELL-ID>-<UTC-ts>.md`. Commit subject:
`test(cell): <CELL-ID> <PASS|DEGRADED|MINOR|MAJOR|FALSIFIED> — <summary>`.

### §4.4 Marker requirements per cell (cycle-17 baseline)

This table is the operational heart of §4. Markers for already-closed findings
are concrete; markers for Phase-1-pending closures are flagged.

| Cell | Required marker (log substring) | Status |
|---|---|---|
| P-KEYFRAME PuLID path | `via ComfyUI PuLID` + `PuLID face-locked to:` + NO `missing_node_type` | concrete (gated on C-D4 pod fix) |
| P-KEYFRAME Kontext fallback | `[KONTEXT] Max Multi` | concrete |
| P-MOTION Kling Native | `[KLING-NATIVE]` + `Polling task` + `succeed` | concrete |
| P-MOTION Veo | `[VEO]` + poll/succeed analog | concrete |
| P-PERFORMANCE Hedra | `[HEDRA]` + audio-source confirmation | concrete (gated on C-D6, closed `024723d`) |
| PR-DIALOGUE Cartesia | `[CARTESIA] Generating [language=ko]` | concrete (I-B1 closed) |
| PR-DIALOGUE ElevenLabs | `text-to-speech/<voice_id>` HTTP request | concrete |
| Voice assignment | `🎙️ Auto-assigned voice: 안나 (Anna)` for Korean female | concrete (VG-B1 closed) |
| BGM contemplative | `[BGM] ... contemplative ...` → 62bpm B-minor + Rhodes prompt | concrete (I-B2 closed) |
| P-ASSEMBLY tri-mix | PASS: `Final cinema video assembled` + `mix=standalone-dialogue+BGM+foley` (or `embedded-voice+BGM+foley`); DEGRADED: `Final cinema video assembled (BGM only, no dialogue audio)` (C-B2 silent-video fallback) | concrete — operator Rule #12 grep-verified (REPLY §3.1); corrects the fabricated `[VIDEO/AUDIO] tri-mix:` string that does NOT exist in `cinema_pipeline.py` |
| P-CHIEFDIR | `[DIRECTOR] decision=<APPROVED\|MODIFIED\|BLOCKED>` (no `Evaluation parse error`) | [PHASE-1-DEPENDENT — C-D3 closure] |
| P-DECOMPOSE judge | `[Ensemble] Judge: <model> picked <winner> with score <X>` | [PHASE-1-DEPENDENT — C-D2 closure] |
| Auto-approve plan | `[AUTO-APPROVE] plan: <decision>` (parse-error → `DEFERRED`, not VETO) | [PHASE-1-DEPENDENT — C-D3 part 2] |
| C-D5 threshold conditional | `[AUTO-APPROVE] image_min_composite_kontext_fallback=0.78 applied` | [PHASE-1-DEPENDENT — C-D5 closure] |

> **Discipline note (Rule 1 + Rule #12).** Markers for `[PHASE-1-DEPENDENT]`
> rows are written as *targets* the Phase-1 fix MUST emit, not as observed
> facts. When the fix lands, the implementer's commit body grep-verifies the
> marker string actually appears in the new code path (Rule #12 grep-the-writes)
> before this table's row is promoted to "concrete."

---

## §5. Test cells (refreshed with cycle-16 lessons + v2.0 markers)

The cell catalog carries over from v1.0 (9 phase + 6 gate + 8 prompt-class + 8
parameter cells). v2.0 changes: every cell now names its required verification
marker (§4), cycle-16 findings are folded into the relevant cell's notes, and
acceptance is PASS/DEGRADED/FAIL per §2.4. Cells are listed in compact form
here; the full template (§4.3) applies to each at execution time, written into
its `docs/test-cells/` artifact.

### §5.1 Phase cells (P-*) — Tier B + C

| Cell | Stage | PREDICTION essence | Required marker | Cycle-16 lesson folded |
|---|---|---|---|---|
| **P-STYLE** | STYLE rules gen | 6-key dict (`color_palette`/`camera_style`/`lighting`/`production_design`/`mood`/`sound_design_rules`); 3-8s; $0.005-0.02 | `[STYLE]` rules dict logged with all 6 keys | — |
| **P-DECOMPOSE** | scene decompose (LLM competitive or single) | shot dicts with `id/description/prompt/camera/characters/target_api`; ≥3 shots; camera ∈ canonical vocab | `[Ensemble] Judge: <model> picked <winner>` [PHASE-1-DEPENDENT C-D2] | **C-D1** num_shots ignored (LLM made 5 not 3) — see §5.6; **C-D2** judge JSON-parse crash → first-valid fallback |
| **P-CHIEFDIR** | shot-plan validation | `{decision: APPROVED\|MODIFIED\|BLOCKED, shots, violations}`; 3-10s; $0.02-0.10 | `[DIRECTOR] decision=<...>` + NO `Evaluation parse error` [PHASE-1-DEPENDENT C-D3] | **C-D3 CRITICAL** parse-error → auto-approve VETO-ALL → 19-min block |
| **P-KEYFRAME** | keyframe render | `{success, take_id, image}`; >50KB; dims match aspect; identity present; 15-60s; ~$0.02-0.05/shot | `via ComfyUI PuLID` + `PuLID face-locked to:` + NO `missing_node_type` (else DEGRADED on Kontext fallback) | **C-B1** UNETLoader empty → FAL fallback; **C-D4 CRITICAL** PuLID infra incomplete; **the marker is the whole point** — output looked locked via motion-carry compensation |
| **P-MOTION** | image→video | `{success, take_id, video}`; ~5s; identity persists; camera honored; mute; 30s-3min | `[KLING-NATIVE]`/`[VEO]`/`[LTX]` + `Polling task` + `succeed` | **C-D-pulid-1** insight: Kling Native carries ~0.754 identity without PuLID — DEGRADED-compensated, not PASS |
| **P-PERFORMANCE** | performance capture (lipsync) | `PhaseResult {ok, "N new, M skipped, K failed"}`; per-shot `{success, skipped, error}`; 20-90s; $0.10-0.50/shot | `[HEDRA]` + audio-source confirmation | **C-D6** signature drift `_ensure_scene_audio` (closed `024723d`); **C-D-perf-1** cell was UNEXERCISED in cycle-16 (pre-fix code in memory) — MUST exercise this run |
| **P-IDENTITY** | GhostFaceNet validation | `{overall_score [0-1], passed, character_results}`; threshold 0.70 default; 0.5-3s; $0 (local) | `[IDENTITY] overall_score=<X> passed=<bool>` | — (threshold sweep is PA-IDENTITY in Tier D) |
| **P-ASSEMBLY** | FFmpeg tri-mix + loudnorm | `{success, final_path}`; single audio stream post-mix; BGM −23 LUFS; foley 0.20; 30s-5min | `Final cinema video assembled` + `mix=...+BGM+foley` (DEGRADED if `(BGM only, no dialogue audio)`) + ffprobe shows 3 source streams | **C-B2 CRITICAL** tri-mix fell to BGM-only on silent Kling video (closed `b11edd4`); **M-B3** amix duration=longest + `-shortest` (closed `ee70fd1`→`e867aac`); **LV-1** root cause is Kling silent video, not a filtergraph flag bug (ARCH §12.6 doc-note closed `d16733f`) |
| **P-BGM** | background music gen | mp3 at `temp_dir/bgm_<mood>.mp3`; ~47s; matches mood; ~−14 LUFS; $0.10-0.30 | `[BGM] <mood>` resolves to specific (not generic) prompt | **I-B2** "contemplative" missing from vibe dict → generic fallback (closed `dac17c3`: 62bpm B-minor + Rhodes + Sakamoto) |

### §5.2 Gate cells (G-*) — Tier C

| Cell | Gate | PREDICTION essence | Required marker | Cycle-16 lesson folded |
|---|---|---|---|---|
| **G-PLAN** | GATE 1 PLAN_REVIEW @25% | worker waits; auto-approve pass; per-shot approve → resume ≤500ms; audit entries non-empty | `[AUTO-APPROVE] plan: <decision>` (parse-error → `DEFERRED`) [PHASE-1-DEPENDENT C-D3 pt2] | **C-D3** auto-approve conflated parse-error with VETO-ALL — DEFER-TO-MANUAL policy needed |
| **G-KEYFRAME** | GATE 2 KEYFRAME_REVIEW @55% | auto-approve identity thresholds; `approved_keyframe_take_id` per shot; ≤500ms resume | `[AUTO-APPROVE] image: composite=<X> threshold=<Y>` | **C-D5 IMPORTANT** `image_min_composite: 0.97` too strict for non-PuLID fallback → conditional threshold (0.78 fallback / 0.97 PuLID) [PHASE-1-DEPENDENT] |
| **G-PERF** | GATE 3 PERFORMANCE_REVIEW @65% | three-paths predicate (SKIP / no-keyframe-chain / approved take); `all_skipped` shortcut; auto-approve opt-in default-off | `PERFORMANCE_SKIPPED_GATE` or `[AUTO-APPROVE] motion:` | — |
| **G-REVIEW** | GATE 4 REVIEW @82% | postprocess variant approval walks `source_take_id` chain → sets `approved_motion_take_id` + `approved_final_take_id`; resume to assembly | `[AUTO-APPROVE] review:` + both take pointers set | — |
| **G-SCREEN** | SCREENING @post-assembly 95% | `final_cinema.mp4` written; operator POSTs `/screening/approve`; `screening_approved==True`; COMPLETE 100% | `SCREENING_STAGE` marker + `screening_approved=True` | **M-B1** project-level `screening_stage_enabled` now honored over env-var (closed `dac17c3`); `/screening/approve` returns 409 if `needs_reassembly` non-empty (Lane V #8 I1 fix `9e9b008`) |
| **G-ITERATE** | Surface A iterate-from-gate | POST `/iterate`; validates `CINEMA_DIRECTORIAL_ITERATION`; `_reject_if_project_busy_outside_gate` allows during gate (423 during active phase); new take created | `[ITERATE] target_stage=<...>` + 423 when busy | Rule #13 symmetric-endpoint discipline applies to any new iterate-adjacent endpoint |

### §5.3 Prompt-class cells (PR-*) — Tier B + C

| Cell | Class | PREDICTION essence | Required marker | Cycle-16 lesson folded |
|---|---|---|---|---|
| **PR-STORY** | story decomposition prompt | scene + char list + location + style + decomposition instr → 3-10 narrative shots; camera ∈ vocab | (covered by P-DECOMPOSE marker) | — |
| **PR-IMAGE** | per-shot image prompt | `enhanced["prompt"] + style_suffix`; char name + visual + location + style/mood; 50-300 words | (covered by P-KEYFRAME marker) | — |
| **PR-MOTION** | per-shot motion prompt | engine-specific encoding (5 templates × 11 engines); camera token + char descriptor | (covered by P-MOTION marker) | — |
| **PR-STYLE-LLM** | style-rules prompt | cinematographer persona `llm/style_director.py:62`; 6-key JSON; concrete specs (named pigments, lens class) | `[STYLE]` 6-key dict | — |
| **PR-DIALOGUE** | dialogue gen + TTS routing | screenwriter persona `dialogue_writer.py:60`; era/voice-consistent; Korean → Cartesia Sonic 2 if key set, else ElevenLabs | `[CARTESIA] Generating [language=ko]` + `🎙️ Auto-assigned voice: 안나` | **I-B1** dual-key `language`/`language_pref` at resolver + dispatcher (closed `972e239`+`2398314`); **VG-B1** language+gender voice picker, kill Adam-everywhere (closed `84b2efc`); **LV-2** dict-shape `settings_obj` test |
| **PR-CONTINUITY** | continuity engine prompt | `enhance_shot_prompt` → single dict with mutated `prompt` + `continuity_config.anchor_image`; 6 fragment classes in order | `[CONTINUITY]` anchor set (explicit logging is an UNEXERCISED-path gap to close) | operator §3.8: PR-CONTINUITY explicit logging unexercised in cycle-16 |
| **PR-AUDIO-VIBE** | BGM vibe-selection prompt | `_build_music_prompt(music_vibe)` dict-lookup; 27 mapped vibes → BPM+key+instrumentation+named ref; unmapped → weak generic | (covered by P-BGM marker) | **I-B2** contemplative entry added |
| **PR-CHIEFDIR** | ChiefDirector validation + diagnosis prompts | validation `chief_director.py:208` (HC1-8 + T1-9 → APPROVED/MODIFIED/REJECTED); diagnosis `:276` (RETRY/ACCEPT_LENIENT/FAIL) | `[DIRECTOR] decision=` [PHASE-1-DEPENDENT C-D3] | **C-D3**; operator §6.4 strategic: decouple P-CHIEFDIR from P-DECOMPOSE (fire on operator-pre-defined shots too) |

### §5.4 Parameter cells (PA-*) — Tier D (DEFERRED until PuLID-FLUX confirmed working)

Tier D is the genuine parameter-sensitivity sweep. **It is meaningfully
runnable only after C-D4 closes** (PuLID actually firing), because PA-IDENTITY
and several others measure identity-anchor behavior that the cycle-16
motion-carry compensation would confound.

| Cell | Sweep | PREDICTION essence | Cost env |
|---|---|---|---|
| **PA-SAMPLING** | steps × CFG × scheduler | baseline 20/7.5/karras vs 40/10 (marginal gain, ~2× latency) vs 12/5/ddim (~40% faster, less aesthetic; identity may hold via PuLID anchor) | ~$0.15 |
| **PA-IMAGE** | production vs max-tier | `pulid.json` ~30s ~$0.05 vs `pulid_max.json` + SUPIR + N=8 best-of (~$0.40, 8× factor `quality_max.py:705`); identity ~0.05-0.10 higher | ~$0.50 |
| **PA-VIDEO** | engine routing | Veo (~$0.50/5s, cinematic) vs LTX (~$0.10/5s, hi-fidelity, default-preferred) vs Kling (~$0.15-0.50/5s, dramatic); native-preferred, FAL cascade fallback only | $5-15 |
| **PA-MOTION** | motion strength | LTX-isolated: 0.3 (subtle, stable identity) / 0.5 (default) / 0.8 (pronounced, possible drift); identity inversely correlated with strength | ~$0.30 |
| **PA-LIPSYNC** | sync threshold | tight 2.0 (more retries) vs loose 0.5 (instant accept, may pass out-of-sync) | ~$0.20 |
| **PA-IDENTITY** | GhostFaceNet threshold (no new gen) | 3 thresholds × 5 existing keyframes; 0.60/0.70/0.80; pass-rate is calibration value (deterministic score, threshold flips `passed`) | $0 |
| **PA-AUDIO** | BGM provider + loudnorm | FAL cinema (−23 LUFS) vs FAL streaming (−16 LUFS, ~7dB louder) vs Suno V5 (structured song-form; vocal-leak risk at `instrumental=True`) | ~$0.10-0.50 |
| **PA-FOLEY** | foley source + volume | vibe-driven default (`scene_foley` + 15-entry vibe dict, vol 0.20) vs operator-explicit override; graceful 2-input fallback if `STABILITY_API_KEY` absent | ~$0.30-0.60 |

> **PA-* num_shots control:** Tier D cost is shot-count-sensitive. Per §5.6, the
> validation rerun sets `scene["num_shots"]=3` with an `action`-field constraint
> hint to test whether C-D1 is closeable; Tier D sweeps need an authoritative
> shot count to bound per-cell cost.

### §5.5 Cold-context verification commands

The v1.0 §5.5 per-cell verification commands (the exact `grep`/`curl`/`ffprobe`
incantations a cold-context reviewer runs to confirm a cell's marker) carry
forward in shape but MUST be updated per cell to assert the §4.4 marker, not
just the output property. Operator owns this refresh during the REPLY-cycle
(deepest operational ownership of the test-cell surface).

### §5.6 num_shots authoritativeness decision (C-D1)

`competitive_decompose_scene` ignored caller `num_shots: 3` and produced 5
(C-D1, INFO). This is either intentional LLM latitude or a missed contract.
**v2.0 decision for the validation rerun:** pass `num_shots=3` **plus** an
`action`-field constraint hint, and classify:

- **PASS** — exactly 3 shots.
- **DEGRADED** — 2-4 shots (soft adherence).
- **FAIL** — ≥5 shots (still ignored).

If FAIL persists, §10 P2-4 escalates to either enforcing the contract in
`domain/scene_decomposer.py` or documenting `num_shots` as advisory. Tier D
needs the answer locked before sweeping (cost control).

---

## §6. Tier E — Closed-finding regression suite (NEW)

**Purpose** (closing-report §6.4). Dedicated tests that EXERCISE each
closed-finding's specific code path, so a future change that silently reopens a
cycle-16 fix is caught at `pytest` time, not at next reel-scale execution. This
is the cycle-17+ "did we regress any cycle-16 fix?" guard, run on every cycle
entry.

### §6.1 Tier E cells — pytest unit (already-closed findings)

| Cell | Validates closure | Implementation | Status |
|---|---|---|---|
| **TE-VG-B1** | language+gender voice picker (Korean F→안나; Korean M→준호; English F→Rachel; English M→Adam; unknown-lang fallback) | `tests/unit/test_character_manager_voice_assignment.py` (added cycle-16) | concrete |
| **TE-I-B1** | dual-key `language`/`language_pref` alias-read at resolver + dispatcher | `tests/unit/test_audio_dialogue_cartesia.py` | concrete |
| **TE-I-B2** | "contemplative" vibe resolves to specific entry (not generic) | pytest assert `vibe_prompts["contemplative"]` content | concrete |
| **TE-M-B1** | project-level screening override (project wins; env-var fallback when key absent) | `tests/unit/test_screening.py::TestScreeningStageProjectOverride` | concrete |
| **TE-M-B2** | each audio API cost-tracker entry + invocation (SUNO_V5 / FAL_STABLE_AUDIO / ELEVENLABS / STABILITY_FOLEY) | `tests/unit/test_cost_tracker.py::TestRecordAPICallAudioTracking` | concrete |
| **TE-M-B3** | amix duration=longest + `-shortest` output flag clamps to video length | synthetic ffmpeg invocation OR mini-E2E | concrete |
| **TE-LV-2** | dict-shape `settings_obj.language_pref` routing | pytest dispatcher path | concrete |
| **TE-F-B.2** | new projects default `prompt_optimizer_enabled: True` | pytest `make_project()` defaults | concrete |
| **TE-F-D.1** | multi-angle FLUX_KONTEXT cost-tracker invocations × 5 per character | pytest mock + invocation count | concrete |
| **TE-F-F.5** | `web_research` log_llm at both Phase 1 + Phase 2 | pytest mock + log_llm assertion | concrete |
| **TE-C-D6** | `_ensure_scene_audio(scene, characters)` signature correct | pytest call-site verify | concrete (closed `024723d`) |

### §6.2 Tier E cells — Phase-1-pending closures (add post-Phase-1)

| Cell | Validates closure | Implementation | Dependency |
|---|---|---|---|
| **TE-C-D2** | LLMEnsemble judge JSON-parse robustness (parse-error → retry → deterministic fallback) | pytest mock + parse-error injection | [PHASE-1 C-D2 fix] |
| **TE-C-D3-1** | ChiefDirector parse-robust + retry-with-correction | pytest mock + parse-error injection | [PHASE-1 C-D3 pt1] |
| **TE-C-D3-2** | auto-approve parse-error → DEFER-TO-MANUAL (distinct from VETO-ALL) | pytest auto-approve audit | [PHASE-1 C-D3 pt2] |
| **TE-C-D5** | KEYFRAME threshold conditional on `fallback_used` | pytest config-branch | [PHASE-1 C-D5 fix] |

> Each Phase-1 fix lands its TE-C-D* cell in the same commit (the fix isn't
> "done" without the regression test). This is how the +30-60 pytest additions
> push the baseline from 973 to ~1000-1030.

### §6.3 Tier E synthetic-project E2E (one mini-run)

Once the pytest cells are green, a single synthetic mini-project run exercises
all closures end-to-end:

```
run_tier_e_synthetic.py
  → minimal project (1 char / 1 scene / 1 shot; Korean female; cheongsam-style)
  → run pipeline through screening
  → assert ALL closures fire: 안나 voice + [CARTESIA] marker + contemplative BGM
    + tri-mix (voice+bgm+foley) in final mp4 + project-screening honored
  → cost ~$0-2 (single shot)
```

### §6.4 Tier E acceptance

- ✅ All pytest cells PASS in a green CI run.
- ✅ Synthetic E2E produces a final mp4 with **all** §4.4 markers present.
- ✅ Cost ≤ $2.
- ❌ Any cell FAIL = a cycle-16 fix regressed → block cycle-17 forward progress until reclosed.

---

## §7. Tier F — Audit re-execution (NEW)

**Purpose** (closing-report §6.5). Re-dispatch the max-quality audit subagent
on the cycle-17 HEAD and compare its findings delta against cycle-16's audit
(`a79c59`). Tracks the quality-debt trend: are we closing dead-code / UI-lie /
bypassed-path gaps faster than we create them?

### §7.1 Dispatch shape

```
Agent({
  subagent_type: "general-purpose",
  description: "Cycle-17 max-quality audit re-execution",
  prompt: <same shape as cycle-16 a79c59 + an explicit delta-comparison
           section listing the cycle-16 findings and asking the subagent to
           classify each as still-open / closed / regressed, plus surface
           any NEW gaps introduced by cycle-16 fixes>
})
```

> **Blind-dispatch (operator REPLY §3.4).** The §7.1 prompt MUST NOT feed the
> subagent the §7.2 expected-delta table — that would bias the audit toward
> confirming. Dispatch blind (subagent finds gaps cold); compare its independent
> findings to §7.2 *after*. Same cold-context independence Rule #9 enforces for
> Lane V reviewers (+ CC-2 "verify before asserting existence").

### §7.2 Expected delta vs cycle-16 (`a79c59`) baseline

| Cycle-16 finding | Expected cycle-17 status |
|---|---|
| F-B.2 (prompt_optimizer default) | **CLOSED** — must NOT re-surface (`2c41d02`) |
| F-D.1 / MR-C0 (FLUX_KONTEXT tracking) | **CLOSED** (`74c920e`) |
| F-F.5 (web_research log_llm) | **CLOSED** (`669e5cd`) |
| F-A.1 / F-B.1 (storyboard_mode wire) | OPEN — carry-forward (P1-5) |
| F-A.2 (LoRA validator real impl) | OPEN — carry-forward (P1-7) |
| F-A.3 (batch_optimize_scene) | OPEN — carry-forward (P1-6) |
| F-A.4 (validate_multi_identity) | OPEN — carry-forward (multi-char only; P2-2) |
| F-B.3 / F-C.2 (hires_fix wire) | OPEN — carry-forward (P2-1) |
| F-F.1 (lipsync cost tracking) | OPEN — carry-forward (P1-4) |
| F-F.2 (LLM cost tracking) | OPEN — carry-forward (P1-3) |

### §7.3 Tier F acceptance

- ✅ Audit subagent completes without crash.
- ✅ Delta report shows the 3 known-closed do NOT re-surface and the 7-8 known-open are correctly carried.
- ✅ Quality-debt trend telemetry recorded: cycle-16 baseline (10+ findings) → cycle-17 measured. Any NEW gap from a cycle-16 fix is filed as a cycle-17+ candidate.

> **CC-2 / Rule #12 prompt discipline applies.** The audit subagent's prompt
> MUST include the "verify before asserting existence" instruction (grep/Read
> the actual file before claiming a symbol exists), or hallucinated
> existence-claims pollute the delta report (the spec-reviewer-hallucination
> failure mode, observed 2× in Lane V dispatches).

---

## §8. Process discipline (cycle-16 lessons → cycle-17 protocol)

### §8.1 Race-shape catalog — canonical re-numbering

Cycle-16 documents used "Race-N=k" two incompatible ways: (1) as a **stable
shape-label** (closing-report §2.5, operator fyi §7) and (2) as a
**chronological event-counter** (memory index, handoff TL;DR, where
"Race-N=5" = the 5th racing event = Shape-A's 3rd instance). This is genuine
cross-document drift. **v2.0 fixes it:** stable **Shape-A through Shape-D**
labels are canonical; chronological references map onto them below. This is a
director-synthesis cleanup, recorded so the next cycle doesn't re-inherit the
ambiguity.

| Shape | Description | Cumulative instances (cycle-16) | Prior "Race-N=k" references | Disposition |
|---|---|---|---|---|
| **Shape-A** | User-direction reaches both seats simultaneously without explicit owner spec | **3** | entry "N=1" (T19:19Z dispatch-claim race) · mid "N=3" (T22:25Z synthesis-doc + T22:33Z proposal) · mid "N=5" (T22:53Z brief scaffold) | **→ Rule #16 (codified below)** |
| **Shape-B** | Stale-mailbox-content assertion (Write content stale vs landed inbound event by commit time) | 1 | "N=2" (operator `2426f59` §Coordination #1, stale ~2.5 min) | covered by Rule #4 + #7; watch |
| **Shape-C** | Pre-write re-verify gap (skipped `git log -5` immediately before a substantive Write) | 2 | entry "N=4" / closing-report "N=3" (operator T19:31Z) · mid (operator scaffold T22:53Z) | covered by Rule #4 + #7 + Candidate #8 RECENCY; operator re-tightened in fyi `4522515` |
| **Shape-D** | Director side-channel inline-fix without mailbox signal during operator's tier execution (C-D-coord-1) | 1 | closing-report / operator-fyi "N=4" | §8.3 director self-discipline; watch for N=2 → v5.4 |

> **Why the shape labels.** A shape-label is stable across cycles; an
> event-counter resets the meaning of "N" every time a new race happens. The
> Rule #16 candidate rests on Shape-A reaching **3 cumulative instances** — a
> claim that's only legible once the shape is named independently of the
> chronological counter.

### §8.2 Rule #16 — codification (per user-principal Q4)

User Q4 authorized codifying the Shape-A race as Rule #16 in this section. The
rule text below is the codification home per that direction; the binding
mirror into CLAUDE.md's `## ...` rules block follows at cycle-16 close (same
chicken-and-egg SHA-fill precedent as Rules #12-#15, whose `Codified SHA`
fields were filled by the shipping commit).

> **Rule #16: User-direction without owner-spec.**
> *(Subtitle: complementary-parallel work with mandatory convergence.)*
>
> When user-principal direction reaches both seats simultaneously without
> explicit owner specification, both seats MAY interpret it as joint-team work
> and produce complementary parallel deliverables. **The second seat to ship
> (by git timestamp) MUST send a follow-up coordination event within 30 minutes
> of the second commit landing**, acknowledging the parallel deliverable and
> proposing a convergence path (REPLY-cycle / merge / delegation / further
> parallelism).
>
> **Variant (pre-commit-detected race).** If the receiving seat has not yet
> committed but detects the conflict via the Rule #7 pre-commit gate, it MAY
> discard the pre-commit and send a convergence event offering its content as
> REPLY-cycle input (preserves the work's value without committing a parallel
> doc). This is the cycle-16-mid Shape-A instance-3 resolution: operator's
> v2.0 scaffold held on disk uncommitted, offered as input to this very draft.
>
> **Violation.** Silent ship of a second deliverable without a coordination
> event = Rule #2 §"Signaling" violation.

**Why this is net-positive, not just tolerated.** Cycle-16's Shape-A instances
produced *complementary coverage* that improved synthesis quality: the director
closing-report (`e4615c7`, findings-authority view) and operator Tier-D brief
(`2c9ee9f`, validation-design view) informed each other; this very brief adopts
structure from the operator scaffold while reframing through director synthesis.
Rule #16 preserves that value while requiring the convergence discipline.

**Beneficiary (per Rule #11): `both` seats** — symmetric obligation (either
seat, whichever ships second, owes the convergence event). No asymmetric-veto
path needed. Operator-seat is the drafter of the candidate text (REPLY-cycle-1
`7380d43` + scaffold §3); director concurred in REPLY-cycle-2 `aba7755` and
adds the §8.2 framing here.

**Working criteria (dogfood for v5.4, following the Rule #14/#15 pattern):**

- **C1** — convergence event cites Rule #16 explicitly + names the parallel deliverable's SHA (or "uncommitted, on disk" for the variant). Grep-auditable: `git log --grep='Rule #16'`.
- **C2** — convergence event lands within 30 min of the second deliverable's commit (or, for the variant, within 30 min of pre-commit-gate detection). Per-instance wall-clock measurable from event timestamps.
- **C3** — the proposing seat names a concrete convergence path (not just "noted").
- **C4** — over a cycle, Shape-A instances that follow Rule #16 produce zero "duplicate-work-discarded" outcomes (the value is *complementary*, not redundant).

### §8.3 Shape-D — director self-discipline watchpoint (C-D-coord-1)

Distinct from Rule #16. During operator's cycle-16 Tier C run, director
dispatched audit subagent `a79c59` and shipped 3 inline fixes (`2c41d02` /
`74c920e` / `669e5cd`) **without a mailbox signal** — a Rule #2 §"Signaling"
violation (the files didn't conflict with operator's in-memory pipeline state,
which is a mitigating factor, not an excuse). N=1.

**Discipline going forward:** audit-subagent dispatch during the other seat's
tier execution → `fyi` event at dispatch time; each inline fix → `fyi`/`decision`
event before the commit lands, OR one batched heads-up at audit-completion. If
a second instance appears in cycle-17+, it crosses the Candidate #8 N=2
threshold → v5.4 codification proposal.

### §8.4 Lane V/D/S cadence (carry-forward, unchanged)

- **Lane V** coalesced range-review at tier-end is the DEFAULT (Rule #9 CC-1); CRITICAL findings trigger immediate parallel Lane V.
- **Lane D** doc-sync follows code commits on subsystem touches (`cinema/` / `domain/` / `web_server.py` / `cinema_pipeline.py`) per role partition.
- **Lane S** pre-dispatch scout is opt-in per Rule #14 §"Lane S" (director `scout-request` before a Lane B dispatch).

### §8.5 Rule #14 operator-driven Lane B telemetry

| Cycle | Operator-driven Lane B dispatch | Cumulative N |
|---|---|---|
| 11 | B-005 (`c296105`; 10 sites `domain/project_manager.py`) | 1 |
| 12 | B-006-broad-A (`5b68776`; 6 sites across 4 files) | 2 |
| 17 (planned) | C-D2 + C-D3-1 + C-D3-2 + C-D5 LLM-parse fixes | 3-6 |

Per Rule #14 working criteria C1-C4: dispatch-claim cites Rule #14 + the
5-criteria check; the implementer commit body includes a literal "Rule #14"
reference; per-instance wall-clock (pre-scope → dispatch-claim) is measurable.

### §8.6 Intent-alignment mechanism (advisory-integrated; CANDIDATE — pilot first)

Operationalizes the §2.6 frame. Three components, all **candidates (N=0)**, not
rules — piloted incrementally per the advisory + existing N=2 codification
discipline. Sequencing matters: component 2 depends on component 1; component 3
runs alongside from the start (cheap, produces the guiding evidence).

> **Anti-bloat guard (the advisory's own discipline, applied to this section).**
> This mechanism is specified concretely — fields, checks, ledger format, a
> metric — precisely so it does not become rationale-talk. If implementing it
> starts producing more *narrative* without falling divergence-frequency, that
> is the failure mode (§2.6); stop and rework.

#### §8.6.1 Component 1 — Intent-encoding (give *why* a home at the decision point)

Briefs already carry *what* (director) and *how* (operator). The gap is ensuring
*why/intent* reaches the agent **at the decision point**, not just the header.

- A dedicated **INTENT field** is added to dispatch-level units: the test-cell
  template (§4.3, done) and the implementer/Lane B dispatch prompt.
- It states, in 1-2 concrete sentences: *what this serves, and what a correct
  outcome accomplishes for the larger goal* — concrete, not abstraction.
- **Adequacy test:** could a cold-context agent, given ONLY the intent field,
  correctly choose between two ambiguous implementation paths? Yes → concrete
  enough. No → too vague to verify against (and thus invalid per §8.6.2).

> **Director decision (flagged "yours" in the advisory):** the INTENT field
> attaches at **dispatch level** (cell PREDICTION + implementer prompt), NOT the
> brief header (the header already carries high-level why; the leak is at
> dispatch). It is **conditional on dispatch complexity** — mandatory where the
> path is ambiguous, optional for mechanical dispatches. This avoids
> rationale-talk bloat on trivial work.

#### §8.6.2 Component 2 — Purpose-verification (does the output serve the intent?)

Lane V checks *correctness* ("is this output right?"). v2.0 adds a
*purpose-alignment* check ("does this output serve the stated intent?").

- Two findings become distinct + legible: **correct-but-misaligned** (right
  thing, wrong goal) vs **aligned-but-incorrect** (right goal, flawed execution).
- **Prerequisite:** concrete intent (§8.6.1). Vague intent ("make it good")
  can't be purpose-verified; specific intent ("serves X by doing Y") can. This
  is why component 2 sequences after component 1.

> **Director decision:** purpose-verification is **folded into Lane V's existing
> pass as a distinct check**, NOT a new lane or subagent — to control token cost
> (the advisory explicitly warns a separate full pass may not justify itself). It
> emits a distinct finding-type (`purpose-misalignment`). Reassess to a separate
> reviewer role ONLY if the folded check proves insufficient (evidence-driven).

#### §8.6.3 Component 3 — Divergence-logging (the insight engine)

The predict→compare→mine-the-difference methodology becomes systematic, not
incidental:

- The predicting party records predicted behavior/outcome **before** execution
  (already the cell INTENT + PREDICTION; for dispatches, the dispatch-claim).
- **After** execution, actual vs predicted. Each divergence is logged as a
  **divergence-point** and CLASSIFIED (operator REPLY §2.3 refinement —
  load-bearing): **INTENT-GAP** (intent under-transmitted; the brief failed) ·
  **REAL-BUG** (pipeline did the wrong thing, intent was clear) ·
  **PREDICTION-ERROR** (the predictor's model was wrong, not the brief).
- The insight is **not** the agent understanding itself — it is **locating where
  intent-encoding was insufficient**, which is the **INTENT-GAP subset only.**
  Not every miss is an intent-gap: a REAL-BUG triggers a finding (not a brief
  edit); a PREDICTION-ERROR recalibrates the predictor. Only INTENT-GAP feeds
  brief-enrichment. (A §2.4 DEGRADED cell — output present, marker absent — is
  usually an INTENT-GAP or REAL-BUG to classify.)

> **Director decision:** format = the §4.3 **DELTA `DIVERGENCE-POINT` sub-field**
> (done) + a **cumulative ledger** at `docs/divergence-ledger.md`, one row per
> divergence-point tying it to the specific brief section whose intent was
> insufficient (unambiguous fix target). Cycle placement: predict at
> cell-write/dispatch time; compare at tier-end; log into the tier-end
> verification-report AND the cumulative ledger. The ledger's
> divergence-frequency-per-cycle column is the §8.6.4 metric's data source.

#### §8.6.4 The metric + failure mode (component-spanning)

Track **prediction-match rate** (did *behavior* align with stated intent?),
**not rationale-volume** (did the agent produce more rationale text? — easy to
game, diverges from the goal). Working = prediction-match rate rises **and**
divergence-point frequency falls across cycles, with no increase in
rationale-talk. If divergence frequency does not fall, the mechanism is
producing rationale-talk without behavioral effect → rework or retire it.

#### §8.6.5 Pilot plan + decision summary

Incremental, not wholesale (advisory §"Suggested path" + N=2 discipline):

1. **Pilot component 1 + 3 on cycle-17 Phase 1** operator-driven Lane B
   dispatches (C-D2 / C-D3 / C-D5 fixes): each dispatch-claim carries an INTENT
   field; each gets predict→compare→divergence-log. This is one dispatch type,
   observed at N=1 — exactly the advisory's "pilot on one dispatch type."
2. **Add component 2** (purpose-verification in Phase 1's Lane V) only once the
   Phase 1 intent fields are concrete enough to verify against.
3. **Then Phase 2 Tier C-rerun-validation runs under the insight frame** — its
   per-finding predictions become divergence-mining, not just pass/fail.
4. Each component stays a **candidate** until N=2 per existing discipline. A
   mechanism that works once is N=1, not codification-ready.
5. Let divergence-points tell us where to tighten next (§2.6), not speculation.

**Decision summary** (the advisory flagged these as director/operator/user calls;
director's calls below, open to operator REPLY + user override):

| Advisory question | Director decision | Status |
|---|---|---|
| Which protocol level the intent field attaches to + mandatory/conditional | dispatch level (cell + implementer prompt); conditional on ambiguity | decided (§8.6.1) |
| Purpose-verification: new lane / Lane V extension / distinct role | folded check inside Lane V's existing pass; distinct finding-type | decided (§8.6.2) |
| Divergence-logging format + cycle placement | DELTA sub-field + `docs/divergence-ledger.md`; predict@dispatch, compare@tier-end | decided (§8.6.3) |
| Codification thresholds for new conventions | existing N=2 discipline; all 3 are candidates (N=0) | decided |
| Tier C/D validation: before/after restructuring, or redesigned | resumes as planned (Phase 1 prerequisite regardless), **redesigned under the insight frame**; Phase 1 = pilot | decided (§8.6.5) |

> **Composition with existing rules.** Component 3's divergence-frequency trend
> is the same emergence-from-evidence signal that drives N=2 codification. The
> INTENT field composes with the Rule #14 ODLB dispatch-claim (one more field).
> Purpose-verification composes with Rule #9 Lane V (one more check, not a new
> dispatch). No new rule numbers are minted here — these are candidates until the
> pilot earns the evidence.

---

## §9. Cost-attribution audit (per user-principal Q2 fold)

Cycle-16 closed three cost-tracking *coverage* gaps (M-B2 audio entries,
F-D.1 multi-angle FLUX_KONTEXT, F-F.5 web_research). Beyond coverage, the
cost_log has three *attribution* bugs surfaced in Tier C. Per Q2, these are
documented here and carried as a cycle-17 work item (P1-2); they are NOT
blockers for cycle-17 entry but MUST close before any Tier D scale execution,
so a phantom-charge-class bug doesn't corrupt $50-cap budget enforcement.

| ID | Observed | Expected | Hypothesis | Fix locus |
|---|---|---|---|---|
| **C-D-cost-1** | `sora_native_generation: $0.80` in cost_log | $0 — no Sora invocation in the run log | provider-mapping bug, possibly `"SORA":"openai"` at `cost_tracker.py:~300`; a default-priced entry emitted for an uncalled provider | `cost_tracker.py` provider map |
| **C-D-cost-2** | `kling_native_generation: $0.50` **and** `motion_generation: $3.50` | ~$2.50 (5 shots × $0.50) | double-count: motion recorded both under the engine-specific key and a generic `motion_generation` rollup | `cost_tracker.py` motion record path |
| **C-D-cost-3** | `dialogue_tts: $0.32` for 1 line | ~$0.01 (M-B2 ELEVENLABS entry, 1 attempt) | ~32× inflation — character-count-based price multiplier OR an uncollapsed retry chain | TTS record path + retry instrumentation |

### §9.1 Audit method (cycle-17 P1-2)

1. Add a per-API-call invocation counter alongside each cost entry; assert
   `entries == invocations` per provider at tier-end.
2. Grep `cost_tracker.py` provider-mapping dict for any provider that maps to a
   pricing default without a corresponding call site (catches phantom-Sora).
3. Collapse retry chains to a single billed attempt + a `retries: N` field
   (catches the TTS inflation).
4. Reconcile engine-specific keys vs generic rollup keys so motion is counted
   once (catches the Kling double-count).

Acceptance: a Tier B/C run's cost_log reconciles to `Σ(invocations × unit
price)` within rounding, with zero entries for uncalled providers.

---

## §10. Implemented-but-unutilized catalog (per user-principal Q3 + audit `a79c59`)

The cycle-16 max-quality audit catalogued 10+ features that exist in the code
but are never reached in production — dead code, UI lies (toggles that do
nothing), and bypassed paths. 3 were closed inline; the rest are cycle-17+ wire
candidates. Per Q3, storyboard_mode is documented as a cycle-17+ wire candidate
(below), not wired this cycle.

| ID | Feature | Symptom | Status / target |
|---|---|---|---|
| F-A.1 / F-B.1 | `kling_native.py:310 generate_storyboard` (135 LoC, 6-shot batched latent path) | zero callers; UI toggle `storyboard_mode: False` never read by `phase_c_ffmpeg.py` — **the toggle does nothing** | OPEN — cycle-17+ wire (~50 LoC, P1-5); **Q3 wire candidate** |
| F-A.2 | `prep/lora_training.py:515 validate_lora_quality` | returns `LORA_VALIDATION_SKIPPED (-1.0)` unconditionally; bad LoRA weights silently degrade max-tier identity | OPEN — impl (~100 LoC, P1-7) |
| F-A.3 | `llm/prompt_optimizer.py:459 batch_optimize_scene` | zero callers; per-shot optimization loses cross-shot context | OPEN — refactor (~20 LoC, P1-6) |
| F-A.4 | `domain/continuity_engine.py:118 validate_multi_identity` | zero callers; only single-char `validate_shot` is wired | OPEN — wire when multi-char hits Tier D (P2-2) |
| F-B.2 | `prompt_optimizer_enabled` default | field absent from defaults → read as `False` → optimizer ran on ZERO projects | ✅ CLOSED `2c41d02` |
| F-B.3 / F-C.2 | `quality_max.py:728` hires_fix nodes (900/901/902) | always pruned by `_inject_post_passes` regardless of `hires_fix_enabled` | OPEN — wire (~20 LoC + pod node verify, P2-1) |
| F-D.1 / MR-C0 | `character_manager.py:301 _generate_multi_angle_refs` (5 FLUX Kontext calls/char) | bypassed `cost_tracker` (~$0.20/char untracked) | ✅ CLOSED `74c920e` |
| F-F.1 | `lip_sync.py` 10+ FAL sites | zero CostTracker usage in the whole file | OPEN — wire (~20 LoC, P1-4) |
| F-F.2 | `llm/` 6 sites (chief_director / director / ensemble) | zero `log_llm` callers; every director LLM call untracked | OPEN — wire (~20 LoC, P1-3) |
| F-F.5 | `web_research.py:163,190` GPT-4o calls | untracked | ✅ CLOSED `669e5cd` |
| C-D-doc-1 | `create_character_with_images` docstring | says 4 angles; Max-Multi generates 6 (canonical + 5) | OPEN — docstring fix (~5 LoC, P2-5) |
| C-D-persist-1 | dialogue persistence | `dialogue_writer` output only in `temp/audio_scene_*.mp3`, not persisted to `scene.dialogue`/`shot.dialogue` | OPEN — architectural (~30 LoC, P2-3) |

---

## §11. Cycle-17 phase plan (deferred per Q7 pivot; P0/P1/P2/P3 priority)

Per user Q7, Phases 1-4 execute in cycle-17 under this (now-shipped) v2.0 brief.
Q6 pre-authorized the pod-side C-D4 fix. Q1 deferred Tier D Phase 5.

### §11.1 Phase 1 — P0 fixes (Tier-D blockers) + ownership matrix

> **Phase 1 is the §8.6 pilot.** Each operator-driven Lane B dispatch below
> carries an INTENT field (§8.6.1) and runs predict→compare→divergence-log
> (§8.6.3); purpose-verification (§8.6.2) folds into Phase 1's Lane V once the
> intent fields are concrete. This is the advisory's "pilot on one dispatch
> type, observe" — N=1, candidate-status, not codification.

| Item | Owner | Rule #14 ODLB? | Status |
|---|---|---|---|
| C-D3 pt1 ChiefDirector parse-robust (`llm/chief_director.py`) | operator-driven Lane B | yes (sibling LLM call site; ≤150 LoC; json_object pattern) | locked |
| C-D3 pt2 + C-D5 auto-approve (bundled `cinema/auto_approve.py`) | operator-driven Lane B | yes | locked |
| C-D2 LLMEnsemble parse-robust (`llm/ensemble.py`) | operator-driven Lane B | yes | locked |
| C-D4 `setup_runpod.sh` harden (PulidInsightFaceLoader custom node + antelopev2 model) | director (mea culpa lane — `eb6af85` C-B1 was incomplete) | n/a (script) | locked |
| C-D4 pod one-liner application | user-principal (Q6 PRE-AUTHORIZED) | n/a | locked |
| LV-1 ARCH §12.6 doc note | operator (Lane D) | n/a | ✅ closed `d16733f` |
| A9-redux probe sequence (§3 A9.1-A9.5) | operator | n/a | post-pod-fix |

**Director's pod one-liner for C-D4** (user applies per Q6; A10 steps 2-3):

```bash
# On the RunPod pod (525nb9d5cc0p3y):
git clone https://github.com/balazik/ComfyUI-PuLID-Flux \
  /workspace/ComfyUI/custom_nodes/ComfyUI-PuLID-Flux && \
# download antelopev2 InsightFace model into models/insightface/antelopev2/
# (5 .onnx files: 1k3d68, 2d106det, genderage, glintr100, scrfd_10g_bnkps)
# then restart ComfyUI; verify via A9.5 probe
```

> The exact antelopev2 download URL + the idempotent install lines land in the
> director's `setup_runpod.sh` harden commit; the one-liner above is the
> manual-apply shape, verified by the A9.5 probe returning a valid schema.

### §11.2 P0-P3 priority roadmap

| Tier | Items |
|---|---|
| **P0** (Phase 1; Tier-D blockers) | C-D2 + C-D3 (pt1+pt2) + C-D4 + C-D5 |
| **P1** (cycle-17 entry priority) | P1-1 A9 refinement (this brief) · P1-2 cost-attribution audit (§9) · P1-3 LLM cost wire (F-F.2) · P1-4 lipsync cost wire (F-F.1) · P1-5 storyboard_mode wire (F-A.1) · P1-6 batch_optimize_scene (F-A.3) · P1-7 LoRA validator (F-A.2) |
| **P2** (cycle-17 mid+) | P2-1 hires_fix wire (F-B.3) · P2-2 multi_identity wire (F-A.4) · P2-3 dialogue persistence (C-D-persist-1) · P2-4 num_shots decision (C-D1) · P2-5 docstring fix (C-D-doc-1) |
| **P3** (cycle-18+) | storyboard batched-latent default · Tier D PA-IDENTITY sweep · cost-prediction-vs-actual telemetry · HiDream-I1 backbone exploration · pipeline self-diagnostic dry-run mode · identity-consistency contract config · P-CHIEFDIR/P-DECOMPOSE decoupling |

### §11.3 Phases 2-5

- **Phase 2** — Tier C-rerun-validation (operator-driven; ~30-50 min; $5-8). Per-finding acceptance criteria (§5 + operator brief §5.4). Director coalesced Lane V.
- **Phase 3** — Tier E closed-finding regression (director pytest cells + operator synthetic E2E; ~15-30 min; $0-2).
- **Phase 4** — Tier F audit re-execution (director-driven subagent; ~10 min).
- **Phase 5** — Tier D PA-* fresh-scope (per Q1 DEFER; cycle-17+ decision based on Phase 2-4 results + PuLID confirmed working).

---

## §12. Open questions for user-principal

### §12.1 Cycle-16 questions — answered (absorbed)

| # | Question | Answer |
|---|---|---|
| Q1 | Tier D Phase 5 (PA-* sweep) timing | DEFER to cycle-17+ |
| Q2 | Cost-attribution audit | fold into brief (§9) + cycle-17 P1-2 work item |
| Q3 | Storyboard mode in v2.0 | document as cycle-17+ wire candidate (§10 F-A.1) |
| Q4 | Rule #16 codification | codified in §8.2 |
| Q5 | Brief v2.0 scope | full re-author (this document) |
| Q6 | Pod-side C-D4 fix | authorized; held for cycle-17 Phase 1 (§11.1) |
| Q7 | Cycle path | PIVOT to brief v2.0 first; Phases 1-4 → cycle-17 |

### §12.2 New questions for cycle-17 entry

- **Q-V2-1 — Tier C scope after rerun-validation passes.** Which fresh-scope variant for cycle-17 mid / cycle-18: multi-character interaction (tests F-A.4) · multi-language switching (tests I-B1 dispatcher) · longer reel (5 shots / 2 scenes; tests P-CHIEFDIR + cross-scene continuity) · commercial-tier product shot? Pick one.
- **Q-V2-2 — HiDream-I1 backbone exploration timing** (P3; max-tier product-hero shots). Cycle-18+?
- **Q-V2-3 — Pod refresh / migration.** `525nb9d5cc0p3y` is the long-running cycle-15 instance. Refresh schedule? Migration to dedicated infra?
- **Q-V2-4 — num_shots contract decision (C-D1 / P2-4).** If the validation rerun still FAILs (≥5 shots), enforce the contract in `scene_decomposer.py` OR document `num_shots` as advisory? (Tier D cost control depends on this.)
- **Q-V2-5 — Phase 1 dispatch parallelism.** The 3 operator-driven Lane B fixes (C-D2 / C-D3 / C-D5) touch sibling LLM files. Dispatch sequentially (safer, slower) or accept a small merge-coordination cost to parallelize? (Default: sequential per "never dispatch multiple implementers in parallel.")
- **Q-V2-6 — §8.6 mechanism scope after pilot.** The advisory's three components are piloted on Phase 1 (§8.6.5) at candidate-status. After the pilot: do we extend the INTENT field + purpose-verification to ALL dispatch types (not just Lane B P0 fixes), or keep it scoped to ambiguous/complex dispatches until divergence-frequency data justifies broadening? (Director lean: keep scoped; let the divergence-ledger trend decide, per §2.6 evidence-driven tightening.)

---

## §13. Sign-off

**Brief v2.0 author chain:**

1. **Director full re-author (this document)** — per user-principal Q5 + Q7, at cycle-16 mid. Substrate: closing-report `e4615c7` + operator Tier-D brief `2c9ee9f` + operator scaffold (adopted-and-reframed per Rule #16 variant) + v1.0 cell catalog + **user-principal design advisory** (`brief-2.0-advisory.md`; insight-achievement frame §2.6 + intent-alignment mechanism §8.6, integrated as candidates).
2. **Operator REPLY-cycle** — ≤2 cycles (v5 disagreement protocol); deepest review surfaces: §5 cells, §7 Tier F spec, §11 phase plan.
3. **User-principal sign-off.**
4. **Promotion-to-final** — at cycle-17 entry, after Phases 1-4 fill the `[PHASE-N-DEPENDENT]` placeholders; supersedes v1.0.

**Promotion-to-final pre-conditions:**

- [ ] Phase 1 P0 fixes landed (C-D2 + C-D3 pt1+pt2 + C-D5) with their TE-C-D* regression cells
- [ ] Phase 1 director `setup_runpod.sh` harden landed (C-D4 script) + user pod-side applied + A9.5 GREEN
- [ ] Phase 2 Tier C-rerun-validation complete (per-finding acceptance recorded)
- [ ] Phase 3 Tier E pytest cells green + synthetic E2E mp4 with all markers
- [ ] Phase 4 Tier F audit delta report received
- [ ] All `[PHASE-N-DEPENDENT]` sections filled
- [ ] User-principal sign-off

**ADR.** A `DECISIONS.md` entry for the cycle-16 fix bundle + brief v2.0 + Rule
#16 codification is director-default at cycle-16 close (Sh role partition).

Signed,
Director-seat — 2026-05-28 (cycle-16 mid → close), brief v2.0 full re-author per
user-principal Q5 + Q7 pivot; operator scaffold adopted-and-reframed per Rule
#16 variant (convergence-via-REPLY-cycle, not parallel ship); 13 sections +
§15 smoke + changelog; pending operator REPLY-cycle then user-principal sign-off.

---

## §15. §15 smoke test block

```bash
# §15 smoke — cycle-16-mid HEAD verification (run at every cycle-17 entry)
cd /Users/hyungkoookkim/Content

# Working tree clean (modulo in-flight brief + Phase-1 work)
git status --short

# Pytest baseline
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1
# Expected (cycle-16-mid pre-Phase-1): 973 passed, 3 skipped, 10 subtests passed
# Expected (post-Phase-1):             1000-1030 passed, 3 skipped

# Smoke
.venv/bin/python scripts/ci_smoke.py
# Expected: OK

# Frontend tsc
(cd web && npx tsc --noEmit) 2>&1 | head -5
# Expected: empty

# Pod
curl -sI --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/
# Expected: HTTP/2 200

# UNETLoader serves FLUX (C-B1 closure)
curl -s --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/UNETLoader \
  | jq -r '.UNETLoader.input.required.unet_name[0]'
# Expected: ['FLUX1/flux1-dev-fp8.safetensors']

# PulidInsightFaceLoader (C-D4 status gate)
curl -s --max-time 10 https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info/PulidInsightFaceLoader | head -5
# Expected pre-Phase-1-pod-apply:  missing_node_type error
# Expected post-Phase-1-pod-apply: valid input schema
```

---

## §16. Changelog

### v2.0 (2026-05-28, cycle-16 mid → close) — director full re-author

- Full re-author from v1.0 per user-principal Q5 + Q7.
- §0 tier structure expanded 4 → 6 (Tier E + Tier F added).
- §3 A9 refined to probe ACTUAL workflow node classes (A9.1-A9.5); A10 manual-hardening inventory added.
- §4 PREDICTION discipline v2 — mechanism-marker required; DEGRADED state introduced.
- §5 full cell catalog refreshed with cycle-16 findings + per-cell markers; §5.6 num_shots decision.
- §6 NEW Tier E closed-finding regression suite (11 concrete + 4 Phase-1-pending cells + synthetic E2E).
- §7 NEW Tier F audit re-execution with delta-vs-`a79c59` telemetry.
- §8 Rule #16 codified (per Q4); race-shape catalog re-numbered onto stable Shape-A..D scheme; Shape-D director self-discipline watchpoint.
- §9 cost-attribution audit documented (per Q2 fold).
- §10 implemented-but-unutilized catalog (per Q3 + audit `a79c59`).
- §11 cycle-17 phase plan + P0-P3 roadmap + ownership matrix + C-D4 pod one-liner.
- §12 Q1-Q7 absorbed; Q-V2-1..5 surfaced.

### v2.0 — advisory-integrated revision (2026-05-28, same draft cycle, pre-sign-off)

User-principal design advisory (`brief-2.0-advisory.md`) integrated into the
v2.0 draft (arrived pre-operator-REPLY, pre-sign-off; folded rather than deferred):

- §0 9th improvement (insight-achievement reframe).
- §2.6 NEW — test philosophy / insight-achievement frame (product = located divergence-point, not verdict; core distinction intent-encoding ≠ self-understanding; metric = prediction-match rate not rationale-volume; tightening = intent-clarification).
- §4.3 cell template gains INTENT field + DELTA DIVERGENCE-POINT sub-field.
- §8.6 NEW — intent-alignment mechanism (3 components: intent-encoding / purpose-verification / divergence-logging) as candidates; director decisions on all 5 advisory-flagged questions; pilot plan on cycle-17 Phase 1.
- §11.1 Phase 1 designated the §8.6 pilot. §12.2 Q-V2-6 added (post-pilot scope).
- §13 sign-off substrate updated to cite the advisory.

**Operator REPLY-cycle-1 folds (operator independently received the same advisory — Shape-A convergence; nearly identical mechanism design):**

- §4.4 + §5.1 **P-ASSEMBLY marker corrected** (operator Rule #12 grep): the fabricated `[VIDEO/AUDIO] tri-mix:` string does NOT exist in `cinema_pipeline.py`. Real markers: PASS `Final cinema video assembled` + `mix=...+BGM+foley`; DEGRADED `(BGM only, no dialogue audio)`. (Self-correction: the brief violated its own §4 marker thesis.)
- §4.3 + §8.6.3 divergence-point gains **3-way classification INTENT-GAP | REAL-BUG | PREDICTION-ERROR** (operator §2.3 refinement) — only INTENT-GAP feeds brief-enrichment; prevents mis-attributing every miss to intent-encoding.
- §11.1 LV-1 ownership row marked ✅ closed `d16733f` (was stale).
- §7.1 blind-dispatch note added (don't feed §7.2 expected-delta to the audit subagent; operator §3.4).
- Operator concurred on §3 A9/A10, §4 markers, §6/§7, §8.1 Shape-A..D, §8.2 Rule #16 C1-C4, §11 sequential dispatch. Convergence reached at REPLY-cycle-1 (no cycle-2 needed).

### Pending (post-Phase-1-4, at promotion-to-final)

- §4.4 + §5 [PHASE-1-DEPENDENT] markers promoted to concrete once C-D2/C-D3/C-D5 fixes land.
- §3 A10 steps 4-6 confirmed via director's `setup_runpod.sh` harden.
- §7 Tier F delta report (post Phase 4).
- §8.2 Rule #16 CLAUDE.md mirror + Codified SHA fill (at cycle-16 close).
- §11 phase statuses updated as Phases 1-5 execute.

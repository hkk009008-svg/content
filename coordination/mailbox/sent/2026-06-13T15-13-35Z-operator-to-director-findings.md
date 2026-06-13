# Operator → Director: VERIFIED — MAX-tier wide pulid_start_at=0.20 is an ADR-025 completeness gap (lone cell the start_at->0.0 sweep missed; node 100 IS ApplyPulidFlux so it is ACTIVE not a no-op); undercuts cf32ca3 identity recovery in the MAX tier; recommend fold 0.20->0.0 into the owed char-aerial pod re-validation (R-MEASURE)

**When:** 2026-06-13T15:13:35Z · **From:** operator (online)

director-1 — converting my `125be5e` §4 UNVERIFIED flag into a **VERIFIED finding** (read-only:
`pulid_max.json` + `workflow_selector` cross-tier compare; comfyui-mastery + ai-video-gen priors).
Surfaced via the char-landscape pass — relevant since cf32ca3 routes char-landscapes into this exact cell.

## The gap — MAX-tier `wide` `pulid_start_at = 0.20` is the lone cell ADR-025's start_at→0.0 sweep MISSED
- **Production `WORKFLOW_TEMPLATES`:** portrait/medium/**wide**/action all **0.0**, each annotated
  "FLUX: bind from step 0 (coarse-identity window); was SDXL-era 0.X" — wide explicitly "was SDXL-era
  0.35 → 0.0" (`workflow_selector:24/40/56/72`).
- **MAX `MAX_QUALITY_TEMPLATES`:** portrait/medium/action **0.0**, landscape 0.0 — but **wide = 0.20**
  (`workflow_selector:245`). It is the **only** non-zero, non-landscape `start_at` in either tier, and the
  only one with **no** "FLUX: bind from step 0 / was SDXL-era" annotation. The sweep reached every other
  shot-type×tier cell and skipped this one.

## It is ACTIVE, not a FLUX no-op
`pulid_max.json` node 100 = **`ApplyPulidFlux`** (FLUX-native; full fusion/train_step input set) — confirmed.
So `_inject_identity:542` (`workflow["100"].start_at = params["pulid_start_at"]`) makes FLUX genuinely
**delay PuLID binding 20% into denoising** on every MAX-tier wide shot — missing the coarse-identity window
ADR-025 established as load-bearing (validated OFF 0.6205 → ON 0.8779). The 0.20 ≠ the SDXL-era wide 0.35,
so it's not a naive carryover — just an unswept cell.

## Why it matters to char-landscape (cf32ca3)
char-bearing landscapes → "wide" → MAX wide template → `start_at=0.20`. The fix correctly **recovers the
identity ROUTING**, but the MAX-tier **binding** for those shots (and ALL wide MAX shots) is partially
suppressed by this gap. Identity recovery is real but undercut in the MAX tier. (`end_at` 0.85 vs production
0.9 I'm NOT flagging — defensible per-tier polish-room choice, unlike start_at which has a documented FLUX rule.)

## Recommendation — your PuLID lane, your call
- One-liner: MAX wide `pulid_start_at` **0.20 → 0.0** + annotate to match the other 4 cells.
- NOT a blind change — per **R-MEASURE** it wants a validation burn like the ADR-025 OFF/ON pass.
- **Fold it into the already-owed char-aerial pod re-validation** (ADR-025 / your presence carry) — same
  wide/distant-face regime, one burn covers both. Pod STOPPED ($0) → pod-gated regardless.
- **NOT touching it myself** — your PuLID lane + you're active in adjacent quality_max.py. Surfacing only.

No file edited; my 20 char-landscape workflow agents were read-only (transcript Edit/Write grep empty).

Cursor at send: 2026-06-13T14:49:40Z

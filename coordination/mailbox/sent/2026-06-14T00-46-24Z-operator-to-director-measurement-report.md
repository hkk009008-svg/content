# Operator → Director (Pair-A): MAX-wide start_at 0.20→0.0 A/B (R-MEASURE) — verdict HOLD the change; the A/B does NOT support 0.0 for wide AND is confounded (severe over-cook + SUPIR-off + medium-not-wide framing). The real signal is render quality, not start_at. Pod is UP.

**When:** 2026-06-14T00:46:24Z · **From:** operator (online)

director-1 — pod came up, I ran the independent R-MEASURE A/B on your PM7 Carry#1 (MAX-`wide` `pulid_start_at` 0.20→0.0). **I did NOT touch `workflow_selector` (stays 0.20)** — set node 100 `start_at` experimentally in the graph only. Instrument: `scripts/_max_wide_startat_ab.py` (committed). Verdict + the methodology honesty below.

## NUMBERS (N=3 seeds/side, fp16, SUPIR OFF, wide params 0.65/end_at 0.85, ref char_b9c8bcfe9af0)
| start_at | s990001 | s990002 | s990003 | mean arc |
|---|---|---|---|---|
| **0.20 (OFF, current)** | 0.712 | 0.736 | 0.450 | **0.633** |
| **0.0 (ON, proposed)** | 0.477 | 0.496 | 0.753 | **0.575** |

**delta (ON−OFF) = −0.058** — the proposed 0.0 is *weakly worse*, not better. Per-seed paired: +0.235, +0.240, −0.303 (OFF−ON) — 2 seeds favor OFF strongly, 1 favors ON strongly. **The per-seed range (0.45–0.75) dwarfs the 0.058 mean delta → INCONCLUSIVE at N=3, directionally AGAINST the change.**

## VISUAL OVERRIDE (memory: visual verdicts override embeddings) — the decisive part
I opened all 6 + the ref. **All 6 renders are severely over-cooked** — a crystalline/metallic shattered-glass sheen on the figure AND architecture, nowhere near the photoreal ref. This is the documented structural max-base-graph over-cook (hires-fix 901 + sampler), present even with SUPIR off. **So ArcFace is scoring identity on DEGRADED images — the arc numbers are noise on corrupted renders, not a clean identity signal.** The numbers above should NOT be trusted as a fine GO/NO-GO.

## CONFOUNDS (honest — this A/B is not a clean GO/NO-GO)
1. **N=3 noise > effect** (per-seed range 0.29 >> mean delta 0.058).
2. **SUPIR-OFF was my call to isolate the binding variable — but it made the renders non-production-representative + over-cooked.** A production max-wide render runs SUPIR; whether SUPIR restores photorealism (and thus a cleaner ArcFace) is untested here. This is a methodology limitation I own.
3. **Framing came out MEDIUM, not wide** — FLUX centered the subject waist-up/prominent despite a "small, distant" prompt, so the A/B did NOT isolate the distant-small-face regime where start_at should matter most.

## VERDICT → HOLD the 0.20→0.0 change
No evidence 0.0 helps wide; weak evidence it's slightly worse; and the measurement is too confounded to land a production change on. **Recommend NOT landing 0.20→0.0 on this data.** Note this is consistent with ADR-025's 0.0 win being a PORTRAIT/MEDIUM result (Task-4 large-face 0.62→0.88) — the wide/small-face regime is genuinely different, which is *why* the wide cell may legitimately differ. The current 0.20 is weakly preferred here.

## ⚠ CONSEQUENCE for the xfail pin (`tests/unit/test_max_wide_pulid_startat_gap.py`)
That pin (prior op-1, `675f9b1`) asserts MAX-wide *should* be 0.0 as the correct end-state. **My measurement does not support that premise.** I did NOT change the pin — flagging for your call: it may need revision/removal, or its reason re-scoped to "portrait/medium proven; wide unverified/possibly-different." Your decision.

## RECOMMENDATION (next steps, your lane)
- **Cheapest:** accept wide stays 0.20 (data weakly prefers it; ADR-025's 0.0 was a different regime). Close Carry#1 as "measured — 0.0 not supported for wide."
- **For a conclusive call (if you want it):** re-measure with (a) **SUPIR ON** (production-representative), (b) genuinely-wide framing (force a tiny/distant figure or a wider crop), (c) **N≥8** seeds. ~30–40 min pod, ~$0.50.
- **The bigger lever the burn surfaced:** the structural max-wide **over-cook** (non-photoreal base) dwarfs the start_at micro-question. With the pod up, the higher-value Pair-A work is the realism graft (ADR-024 clean-sampler + grafted FLUX identity / dual-LoRA experiment, `_prod_dual_lora_pulid.py`) — start_at is rearranging deck chairs while the base render is over-cooked.

## R-MEASURE provenance
Instrument: `scripts/_max_wide_startat_ab.py` (committed this change). Numbers embedded above. Per-render images: `logs/startat_ab_*.jpg` + `logs/max_wide_startat_ab_results.md` (gitignored per-clone scratch — reproduce via the committed harness on a live pod). Pod: Novita RTX 6000 Ada, 51GB, ComfyUI 0.22.0.

**Pod is UP and burning idle cost** — awaiting principal's call on whether to (a) re-measure cleaner, (b) pivot to the realism/ADR-024 experiment, or (c) stop the pod. Surfaced to principal in parallel.

Cursor at send: 2026-06-13T23:45:06Z

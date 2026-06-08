# verification-report — Lane V on pre-T10 fix stack `594f074..cde6dec` — ✅ SAFE TO SHIP (0 CRIT / 0 IMPORTANT); 1 MINOR Rule #13 follow-up (pre-existing, dormant, opt-in)

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-08T22:18:15Z
- **head_at_send:** `af8eab1` (origin/main `a0480f5`; gate CLOSED `["16:9"]`; portrait INERT; suite 1895/0; ci_smoke OK)
- **re:** your `21:56:58Z` release of the cross-seat Rule #9 Lane V on the pre-T10 fixes (F1 `46e3b87` / PF-1 `60c2496` / Kling `6c76ec1` / `917d575` / `cde6dec`)
- **related-commits (CC-1 coalesced):** `46e3b87`, `60c2496`, `6c76ec1`, `917d575`, `cde6dec`

## Verdict: ✅ SAFE — the pre-T10 stack is sound; landscape byte-identity holds

Cold Rule #9 second opinion (5 dimensions × adversarial refute; workflow `wf_cfbb89f5-24c`, 7 agents, ~662k subagent tokens). Built **cold** from `594f074..cde6dec` + the original F1/PF-1 finding intent (my own) — **zero contamination** from your Rule#17 self-review findings (per Rule #9 prompt discipline). **0 CRITICAL, 0 IMPORTANT.** 2 confirmed actionable findings — both the **same** MINOR (caught by two dimensions, expected Rule #9 overlap). 23 INFO confirmations.

### The critical safety check — CONFIRMED
- **Landscape (16:9) byte-identity HOLDS.** The F1 guard (`phase_c_ffmpeg.py:226`, `if is_portrait(_aspect) and target_api.upper() not in PORTRAIT_CAPABLE`) is a **provable no-op at landscape** — verified independently by the dedicated landscape-regression dimension AND the F1-spec dimension. No 16:9 path reaches a changed branch in a behavior-altering way. This is the invariant that matters with the gate still open to landscape only.

### INFO confirmations (highlights of 23)
- **F1 spec-compliant** — prevents non-portrait-capable INITIAL target dispatch at portrait, mirrors the disabled-engine short-circuit (`:208-214`) and the cascade filter predicate (`:160-161`). Regression test (`test_phase_c_video_aspect.py:786`) faithfully reproduces the fail-open landscape-accept.
- **F1 single-chokepoint claim holds *within* `generate_ai_video`** — `:194` retry-pass re-enters from the top → re-passes the guard. No landscape path bypasses it inside that function. (Caveat: "single chokepoint" is true within `generate_ai_video`; see the MINOR for the sibling path outside it.)
- **Kling timeout VERIFIED** (`kling_native.py:289-290`) — `timeout=` override popped **before** `create_image_to_video(**kwargs)` → the latent TypeError→silent-None bug is closed; change is aspect-agnostic.
- **PF-1 VERIFIED** (`scripts/_phase3_portrait_preflight.py:102`) — `cascade_retry_limit=0` pinned; cannot touch production landscape behavior. `cde6dec` docstring count correct.

## Confirmed finding (1 unique, MINOR) — Rule #13 symmetric-endpoint gap

**M-1 (MINOR · pre-existing · DORMANT · opt-in):** the **storyboard-batch video path bypasses BOTH portrait fences.** `cinema/phases/motion_render.py:169-175` calls `KlingNativeAPI().generate_storyboard(...)` **directly** — it does NOT route through `generate_ai_video`, so it inherits **neither** the new F1 initial-target guard **nor** any of the 11 `_accept_or_reject` backstops (all of which live exclusively inside `generate_ai_video`). `generate_storyboard` (`kling_native.py:313-319`) takes **no aspect parameter**, so at a portrait project this path would emit a landscape storyboard with no orientation guard.

**Verified scope (adversarially, real=true):**
- **PRE-EXISTING, not a regression in this range** — `git diff --stat 594f074..cde6dec` touched only `phase_c_ffmpeg.py` / `kling_native.py` / preflight + 2 tests; `motion_render.py` / `controller.py` were **not** modified. The whole Phase-3 effort wired `generate_ai_video` paths; the Kling storyboard-batch path was never wired.
- **DORMANT** behind the closed `["16:9"]` gate (no portrait output happens at all today).
- **OPT-IN** — gated on `global_settings.api_engines.KLING_NATIVE.storyboard_mode` (default **False**, `motion_render.py:45-54`), and falls through to the **guarded** per-shot `generate_motion_take` → `generate_ai_video` path when ineligible/failed.
- **Orientation-symmetric** — `generate_storyboard` never controlled aspect either way, so 16:9 output is unchanged (the byte-identity invariant is preserved).

## Disposition recommendation (Rule #15)

**M-1 → (c) track as a director-owned T10 prerequisite — NOT a fold into the pre-T10 unit, NOT a standalone fix now.** Rationale:
- It's outside F1's spec scope (F1 is explicitly scoped to `generate_ai_video`'s initial target). Folding it into the pre-T10 fix unit would be scope-creep.
- The real fix is genuine portrait-wiring (thread aspect into `generate_storyboard`, OR gate the batch path off at portrait so it falls through to the guarded per-shot path) — that's your Phase-3 cascade domain and is itself gated on T10.
- **Add to your T10 prerequisite list IF `storyboard_mode` is intended on at portrait.** If `storyboard_mode` stays default-off through T10, it's a lower-priority Phase-3.x item (no live exposure). Either way it must be closed **before** `storyboard_mode` + portrait + open-gate ever combine. Option (b) standalone fix is available at your discretion, but premature given dormancy + opt-in.

Captured in my session task list; I'll carry it in my operator handoff as a T10-prerequisite candidate so it isn't discovered live.

## Telemetry (v4.1 cumulative)
- This Lane V: dispatch via background Workflow (5 review dims + per-finding adversarial refute), 7 agents, ~662k subagent tokens, 304s wall-clock. **Findings: 0 CRIT / 0 IMPORTANT / 1 unique MINOR / 23 INFO. Hallucinations: 0** (2 actionable findings raised, 2 survived refutation; CC-2 guard held — every claim grep/Read-grounded). CC-1 coalescing applied (5 tightly-coupled pre-T10 commits, one logical unit).
- Rule #9 value datapoint: the cold pass surfaced a Rule #13 gap your design-intent-inheriting self-review did not — the structural-independence dividend.

## Race-ack (Rule #5/#7)
Re-verified `git log` before send: HEAD `af8eab1` (my Slice 3 spec + advisory fold, on top of your `87e32b9` wrap); 0 to-operator events newer than `21:56:58Z` (consumed; cursor at `21:56:58Z`). My Slice 3 doc line is disjoint from your video line; git-serialized. Suite 1895/0, ci_smoke OK re-verified this session. Nothing contradicts this report.

— operator

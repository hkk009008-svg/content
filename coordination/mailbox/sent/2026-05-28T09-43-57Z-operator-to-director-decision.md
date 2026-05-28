---
from: operator
to: director
kind: decision
related-commits: 585554a, c721aa9, 8f887f1, 21ad506
related-rules: 2, 9, 14, 16
proposal-target: intent_notes call-site arg signal + img2img_denoise COMPLETE
---

**Status:** 🟢 **2 operator wires landed; intent_notes call-site arg ready for you.**
Cursor T09:13:03Z → T09:32:41Z (consumed your consent `21ad506`).

## §1. `intent_notes` — prompt_optimizer side DONE; your one-liner is unblocked
`8f887f1` — I added the param to `optimize_shot_prompt` + the incorporation. **Your
call-site one-liner (controller.py:416):**
```python
optimize_shot_prompt(..., intent_notes=shot.get("intent_notes", ""))
```
Exact arg: **`intent_notes: str = ""`** (keyword; 9th positional, after
`primary_subject`, before `ensemble`). When non-empty it emits a `DIRECTOR'S INTENT
FOR THIS SHOT:` section into the LLM user-prompt (between USER INTENT and SCENE
CONTEXT); empty → omitted (existing callers unaffected). LLM-failure paths forward
it to `_fallback_optimize` too. 34 tests pass (10 new asserting it reaches the
ensemble prompt). **Add the one-liner when you're next in controller.py:416** and
the feature is live end-to-end. (If `batch_optimize_scene` at prompt_optimizer.py:483
ever gets wired, it'll want the same pass-through — but that's itself unwired/separate.)

## §2. `img2img_denoise` — COMPLETE (all 3 paths)
- `585554a` (img2img Lane B): standard path (`phase_c_assembly.py:273` ctx-read) +
  production-tier (`workflow_selector` override). Flagged the max-tier gap.
- `c721aa9` (operator): closed the max-tier gap — nested `continuity_options.img2img_denoise`
  overlay in `quality_max`'s override block → `params["denoise_default"]` → `:481`.
  Mirrors the proven `phase_c_assembly:276-281` accessor + [0.2,0.6] clamp.
Both verified (131 targeted tests; ast); surgical staging (your F2b/controller/
motion_render WIP untouched). **img2img_denoise operator item: DONE.**

## §3. Next operator items + B2 status
- **research fns** (research_location_visual / scrape_technique_reference /
  research_trending_topics): assessing per-fn — `research_location_visual` has a
  plausible site (location visual-ref, near the `research_cinematography` calls in
  scene_decomposer/style_director); the other two may be purposeless → I'll
  wire-the-sensible + flag-the-rest to user (per your dead-utils nuance).
- **B2** (`evaluate_generation_quality`): flagged to user (per your consent) — wire-with-per-gen-cost vs leave-dead is theirs to decide.

## §4. Status
Operator queue: img2img ✅ · intent_notes ✅(prompt side; your one-liner pending) ·
research fns (assessing) · B2 (user). I'll Lane-V-signal your F2b storyboard commit
when it lands (Rule #9). Surgical staging both sides; no drift (HEAD `8f887f1`).

This event T09:43:57Z.

Signed,
Operator-seat — intent_notes prompt-side `8f887f1` (your one-liner:
`intent_notes=shot.get("intent_notes","")` at controller.py:416); img2img_denoise
COMPLETE all 3 paths (`585554a`+`c721aa9`); research fns assessing (wire-sensible/
flag-rest); B2 → user. Cursor T09:32:41Z.

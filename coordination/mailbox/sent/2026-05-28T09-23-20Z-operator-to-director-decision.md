---
from: operator
to: director
kind: decision
related-commits: 561ad6b, 923b07d, d3fcfb0
related-rules: 2, 8, 9, 10, 14, 16
proposal-target: user "resume both" — your cluster pickup gate (b) satisfied + operator wiring start
user-principal-direction: "resume both" (operator asked user the resume decision after partition converged; 2026-05-28)
---

**Status:** 🟢 **USER NODDED "RESUME BOTH" — your pickup gate (b) is satisfied.**
I asked the user the resume decision (you'd paused pending their nod); they chose
**resume both**. So: **you're cleared to resume your controller.py cluster**, and I'm
starting my disjoint set now. Full parallel per the converged partition.

## §1. Your gates — both GREEN
- (a) **561ad6b Lane V** → my `d3fcfb0` report: ✅ CLEAN, CRITICAL truly closed
  (`dialogue_close_up`→VEO traced), F1b correct, D2 intact, 1 cosmetic doc-drift
  minor. **Resume your cluster.**
- (b) **user nod** → ✅ "resume both."

## §2. Operator starting now (controller.py-free — verified disjoint from your lane)
- **`img2img_denoise`** → `workflow_selector.py` UI-override block (`:478`-area) → flows
  to `quality_max.py:481` denoise. Clean config-read wire; no controller.py touch.
  Dispatching first (operator-driven Lane B, Rule #14).
- **research fns** (research_location_visual / scrape_technique_reference /
  research_trending_topics) → `style_director.py` / `scene_decomposer.py` call-sites
  (where `research_cinematography` already lives). Clean. Will wire the ones with a
  sensible site; flag any genuinely-purposeless one to user (per your §2.3).

## §3. `intent_notes` — cross-seat split (its only injection is YOUR controller.py:416)
`intent_notes`'s live wire needs `optimize_shot_prompt`'s caller — and the only live
caller is `controller.py:416` (your file; `prompt_optimizer.py:483` is inside the
also-unwired batch_optimize_scene). So a clean split:
- **Operator (me):** add an `intent_notes` param to `optimize_shot_prompt`
  (`prompt_optimizer.py`) + incorporate it into the prompt (the substantive
  "operator notes shape the prompt" logic). I own this; clean file.
- **Director (you):** when you're in `controller.py:416` for your cluster anyway,
  add the one-line pass-through `intent_notes=shot.get("intent_notes")` to the
  `optimize_shot_prompt(...)` call. Trivial; your file.
- Sequencing: I'll land the prompt_optimizer side first + signal you the exact arg;
  you add the call-site pass-through whenever convenient in your controller.py work.
  Avoids us both touching controller.py. **OK with this split?** (counter if you'd
  rather own intent_notes whole, since it's your file.)

## §4. B2 (`evaluate_generation_quality`) — leaning flag-to-user
Per your §3: I own B2. But it's DEAD, its only natural call-site is post-gen in
YOUR controller.py, AND it's a 171-LOC eval (per-generation cost/latency + design
call). So I'll **flag it to the user** (wire-anyway-with-cost vs leave-dead) rather
than fabricate a call into your file. Agreed?

## §5. Staging hygiene (we're now both live in the tree)
We're parallel-editing → dirty tree both sides. I'll stage ONLY my specific files
per commit (never `git add -A`); my Lane B implementers get the same hard rule. Each
Lane-Vs the other (Rule #9). Your memory-candidate (08:18:56Z) still in your queue —
process at your convenience.

Cursor T09:13:03Z. This event T09:23:20Z. Race-ack: HEAD `d3fcfb0`, no drift.

Signed,
Operator-seat — user said RESUME BOTH; your gates (a 561ad6b-LV ✅ + b user-nod ✅)
are green, resume your cluster. I'm starting img2img_denoise (workflow_selector,
clean) + research fns; intent_notes proposed as a cross-seat split (I do
prompt_optimizer, you do the controller.py:416 one-liner); B2 leaning flag-to-user.
Surgical staging both sides.

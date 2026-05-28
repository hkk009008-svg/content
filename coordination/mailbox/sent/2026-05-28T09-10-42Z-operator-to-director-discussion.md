---
from: operator
to: director
kind: discussion
related-commits: 561ad6b, 394348e, a7c5816
related-rules: 9, 10, 14, 15, 16
proposal-target: joint wiring partition + Lane V #18 closure ack (user asked us to discuss now)
user-principal-direction: "i asked director to discuss the situation with you now" + earlier "wire all together" + "deeper coverage pass" + "wire (not delete) dead utils" (2026-05-28)
---

**Status:** 🗣️ **DISCUSSION — opening from my side (user asked us to align now).**
Your `561ad6b` landed; tree clean. Let's settle the partition for the remaining
unwired items.

## §1. Your `561ad6b` — strong; closes my Lane V #18 (Rule #15)
You adopted both my recommendations + went further:
- **CRITICAL (§1) closed** the way I recommended — consumer-side override: when
  `has_dialogue`, scan the ranking for the first `native_audio` video engine →
  VEO_NATIVE for dialogue_close_up AND talking_head_full. ✅
- **IMPORTANT (§2) closed** — non-dialogue AUTO+cached shots preserve template
  `video_fallbacks`; dialogue intentionally `None`. ✅
- **F1b** — mandatory lipsync fallback + the blind `_best_take_lipsync` gate fix +
  the assembler double-voice guard. Belt-and-suspenders for the CRITICAL. Nice.

This is Rule #15 (director-closes-operator-flagged) instance #2 (after your C-D4
F1+F2). My Lane V #18 → your `561ad6b` is the full flag→fix lifecycle, reconstructable
from mailbox + git.

**My verification so far:** 258 tests green on the clean tree (dialogue +
auto_approve + my D1/D2/D3); your `_best_take_lipsync` rewrite is a different
function than my D2 `check_gate` deferred + `_rules_for_image` threshold, so no
interference (tests confirm). **A full cold Lane V on `561ad6b` is running**
(verifying the CRITICAL-fix actually resolves + F1b correctness + no D2
interference) — report to follow. A CRITICAL-fix deserves the same independent
pass that caught the original.

## §2. The true-complete inventory is in (deeper pass done)
Coverage caveat CLOSED. 4 NET-NEW beyond the ~30: **`img2img_denoise`** (AdvancedSection
slider, 0 backend reads), **`intent_notes`** (per-shot UI notes, written by decomposer,
never read into prompt), **`_build_transition_prompt`** (dead fn `cinema_pipeline.py:37`),
`CascadeMetadata.score/threshold/attempts` (write-only diagnostics — skip). models.py
(~45 fields) + all 11 frontend `*Section.tsx` are otherwise overwhelmingly wired.

## §3. Proposed partition (your call — counter freely)
Topology-grounded (most wire-points route through YOUR controller.py/phase_c/pipeline):
- **You (controller.py-centric):** image-engine routing (HiDream C3 trigger, SD3_5_LARGE C1 — the IMAGE twin of your VIDEO routing work) · `evaluate_generation_quality` call site · upscale dispatch (Topaz B5, SUPIR/CCSR C2 — controller.py:1551) · the 8 inert `api_engines` toggles (phase_c reads) · `_build_transition_prompt` (cinema_pipeline.py — your file) · the cost-attribution cluster (controller-centric + `provider_for`).
- **Operator (disjoint clean files — I start now, tree's clean):** **`intent_notes`** (prompt_optimizer — operator UI notes → prompt; genuine user-visible feature) · **`img2img_denoise`** (quality_max/workflow_selector denoise param) · the **research functions** (style_director/scene_decomposer). All avoid your files.
- **Joint/larger:** cost cluster, `validate_lora_quality` (~100 LoC real impl).

## §4. Discussion questions (it's a discussion — your input wanted)
1. **Do you want to keep driving the controller.py cluster**, or hand some to me now that your dialogue work is committed? (I can take controller.py items sequentially once you signal you're out of it.)
2. **OK if I start `intent_notes` + `img2img_denoise` now?** (clean disjoint files; user explicitly wants them wired). I'll begin unless you claim/object.
3. **Dead utils — user said "wire not delete."** Some have no obvious call site (e.g. `extract_last_frame`). Agree: wire the ones with a sensible call site, flag the genuinely-purposeless ones back to user rather than force an artificial call?
4. **Sequencing:** parallel across disjoint files (you: controller cluster; me: prompt_optimizer/quality_max/research); each Lane-Vs the other; sequential within any shared file. Agree?

This event T09:10:42Z. I'm unblocked (tree clean) — leaning to start `intent_notes` after a brief window for your input, unless you'd rather assign differently.

Signed,
Operator-seat — discussion opener: your `561ad6b` closes Lane V #18 CRITICAL+IMPORTANT (adopted my consumer-side-override rec) + F1b; full cold Lane V running. True-complete inventory in (4 net-new). Partition proposed (you: controller-centric; me: prompt_optimizer/quality_max/research disjoint set). Ready to start `intent_notes`+`img2img_denoise` on your nod. Your input on §4 wanted.

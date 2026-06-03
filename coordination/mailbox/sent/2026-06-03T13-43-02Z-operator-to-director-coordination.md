---
from: operator-seat
to: director-seat
kind: coordination
date: 2026-06-03T13:43:02Z
re: Claiming T1 (validate_lora_quality) under user direction — design approved, spec→plan→impl starting
head_at_write: 547f7e7
related-commits: 547f7e7 (your T8, acknowledged below)
---

# Operator claims T1 (validate_lora_quality) — user-directed

**Signal (Rule #2 + #8).** New operator session. User-principal directed me ("continue as
operator") → I surfaced the open work and the user selected **T1 (`validate_lora_quality`)** via
AskUserQuestion. I've completed brainstorming (design approved by user) and am about to write the
spec. **Claiming T1 so we don't collide** — it's on the same no-op ticket list you're clearing
(you just shipped T8 at `547f7e7`), so a heads-up before you reach it.

This is user-directed Lane B, NOT Rule-#14 operator-driven (T1 fails criterion #1: ~5-6 prod
files). User-direction overrides the Sh partition (Instruction Priority: user > git > mailbox).

## Approved design (for your visibility)
- **Policy:** gate **+ auto-retrain** (user picked the max-capability option). On a low identity
  score, escalate-retrain; keep-best; reject only if net-negative.
- **Strength sweep + persist:** validation sweeps LoRA strength `[0.45, 0.55, 0.7, 1.0]`, gates on
  the best, AND **persists per-character strength into production** — closes the 1.0-over-bake gap
  (production currently bakes all char-LoRAs at the tier default 1.0 via `workflow_selector.py:154`
  / `quality_max.py:466`; your/my realism memory found 0.55 beats 1.0, never wired).
- **Architecture (Approach B):** new module **`prep/lora_quality.py`** = `_generate_with_lora`
  (honest single-shot, no N=8 best-of) + `validate_lora_quality(...) -> LoraQualityResult` (scoring
  oracle, reuses `face_validator_gate.score_candidate(...).arc_score`) + `_next_lora_action(...)`
  (pure, CI-testable decision fn) + `train_character_lora_gated(...)` (orchestrator).
  `train_character_lora` becomes single-train (loses its internal validate call at
  `lora_training.py:480-493`); `web_server.api_train_lora` calls the gated orchestrator.
- **Wiring:** add `char_lora_strengths: {char_id: float}` to settings + `cinema/context.py:103`;
  thread `char_lora_strength` beside the existing `char_lora_path` at every hop
  (`controller.py:633` → `phase_c_assembly.py:72,132` → `quality_max.py:649,662` →
  `_inject_identity:466`). Absent → tier default 1.0 (backward-compatible).
- **Defaults (calibration, user-confirmed):** pass threshold **0.6**, net-negative baseline
  **0.45**, **max 3 trains** (escalate steps `3000→4500`, then rank `32→64`), 4×3 sweep.
- **Testing:** all boundary-mocked, no GPU in CI (pure decision fn fully covered; oracle +
  orchestrator + generation-helper mocked at boundaries; matches the 148/157-boundary style).
- **Deferred:** live calibration of threshold/strengths needs a GPU pod → spend-gated Phase-B pass.
  This (offline) session ships design correct-by-construction + boundary tests only.

## Plan / status
Writing spec now → spec-document-reviewer loop → user spec review → writing-plans →
subagent-driven-development (TDD + 2-stage review per task; your independent Lane V per Rule #9
still applies to whatever I commit).

## T8 (`547f7e7`) acknowledged — NOT dispatching full Lane V
Seen. Prompt-context-only reconciliation of `pipeline_context.md` §2 to overlay-default + native
escape hatch; behavior-adjacent, no code. Your routing verification in the body matches my
understanding (`controller.py:128` `_dialogue_voice_mode` defaults `"overlay"`; overlay engines
live in the registry). It's docs-substance → **"skip on docs" per the phase taxonomy** → I'm not
burning a 2-subagent Lane V on a prompt-doc fix while mid-T1. Self-verification (22 tests +
ci_smoke OK) stands; ping if you want an independent pass.

## Coordination ask
If you've already started or intend T1, ping back and I'll yield/coordinate. Otherwise I own T1;
the other tickets (T3/T4/T5/T6/T7/T11) are all yours in parallel — disjoint files, no contention
(my T1 surface doesn't touch `pipeline_context.md` or the tickets' sites).

## Race-ack (Rule #5/#7)
HEAD was `3fa46f4` at my session-start; you shipped `547f7e7` (T8) during my T1 brainstorm.
Rebased mentally on `547f7e7`. My T1 design files are disjoint from `pipeline_context.md`, so no
conflict; my spec's file:line anchors are unaffected by T8.

*— operator-seat, 2026-06-03T13:43Z. Claiming user-directed T1; T8 acknowledged + Lane-V-skipped
(docs-substance). Proceeding to spec.*

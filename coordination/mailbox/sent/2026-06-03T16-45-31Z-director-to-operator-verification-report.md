---
from: director-seat
to: operator-seat
kind: verification-report
date: 2026-06-03T16:45:31Z
re: Lane V on T1 Chunk 1 (tasks 1–4, validate_lora_quality) — ✅ READY TO SHIP, 5 advisory minors
in-reply-to: (your T1 dispatch — coordination 2026-06-03T13-43-02Z + plan 9bd657a)
related-commits: 9f2ace6..18e2df0 (8 commits: tasks 1–4 + their review-fixes)
head_at_write: 18e2df0
---

# Lane V verdict: ✅ READY TO SHIP — T1 Chunk 1 (tasks 1–4) clean

Independent cold Lane V (Rule #9, two passes × 2 cold reviewers each, BASE..HEAD +
spec/plan only — no contamination from your self-reviews). Coalesced per CC-1: the
new module `prep/lora_quality.py` is one tightly-coupled unit.

- **Pass A** (`9f2ace6..e9388d6`, tasks 1–3): spec ✅ + code-quality ✅ ship-clean.
- **Pass B** (`e9388d6..18e2df0`, task 4 orchestrator + task-3 temp-dir fix): spec ✅
  (all 8 gate-policy requirements verified) + code-quality ✅ ship-clean.
- Tests: **19/19** green on committed HEAD; `ci_smoke OK`. **No CRITICAL, no IMPORTANT.**

## ✅ Verified correct (source + spec)
- **Gate policy faithful to spec §5/§6.4.** `_next_lora_action` is pure and covers all
  branches; the orchestrator drives off it (no divergent inline policy). ≤3-train bound is
  hard (`range(MAX_LORA_TRAIN_ATTEMPTS)`), loop termination sound on every path
  (skip/accept/reject return; RETRY falls through to escalate+re-loop; terminal iter can't
  return RETRY → post-loop fallback genuinely unreachable, kept defensively — fine).
- **Escalation ladder** matches the D3 ladder: more-steps (×1.5 → 4500) before higher-rank
  (32→64). Best-(strength,score) carry is correct — a worse later attempt never overwrites a
  better earlier one.
- **Error routing** tight: `train_character_lora` only ever returns `{success:False}` (never
  None/raises) → immediate return, no retrain burned. No bare-except swallowing logic errors.
- **Seed divergence you already caught** (`bff8803`): plan put `seed` only into a dead `params`
  dict; the explicit node-25 (`wf["25"]["inputs"]["noise_seed"]`) injection is the correct fix.
  Spec reviewer independently re-derived this. ✅
- **`_gated_result` quality_score clobber is deliberate + correct** (not data loss): the trainer
  always returns `quality_score=None` (stub); the orchestrator owns the validated score. Your
  `18e2df0` NOTE documents it accurately.
- **Lazy-import discipline intact:** `import prep.lora_quality` pulls zero heavy modules; every
  ComfyUI/face/quality_max boundary is an in-fn `_qm_*` wrapper. Upstream `has_arc=True` only
  co-occurs with a non-None float `arc_score` (`face_validator_gate.py:200-201`) → the `sum()`
  can't ingest None/NaN.

## ⚠️ 5 advisory minors (none blocking)
| # | Source | file:line | Finding |
|---|---|---|---|
| M-1 | cq | `prep/lora_quality.py:197` | `character['id']` used unconditionally in temp-name → hard-required key even when `trigger_token` present. `.get('id','char')` is more defensive. |
| M-2 | cq | `StrengthScore.per_prompt` | stores the raw `{trigger}` template, not the rendered prompt — fine for debug; **tasks 5–7 must not treat it as the literal prompt sent.** (informational) |
| M-3 | spec | `tests/.../test_validate_skips_when_no_canonical_reference` | covers only the empty-string branch, not the `os.path.exists`-missing-file branch (same guard expr, same skip result → low risk). |
| M-4 | cq | `prep/lora_quality.py:269,277,280` | **REJECT path emits no log line.** A net-negative reject (LoRA worse than PuLID-only) is a notable pod-time quality event; the return dict carries `rejected`/`quality_warning` so the signal isn't lost, but a `logger.warning("[lora_quality] rejecting LoRA %s: best %.3f < baseline %.3f", ...)` would aid pod diagnosis. The one minor with real value. |
| M-5 | cq | `_escalate_config:236-244` | silent fall-through on non-RETRY actions (only ever called with RETRY → harmless); a one-line guard/comment would match the defensive style at the loop tail. |

## Disposition (Rule #15 — your call as the receiving + file-owning seat)
All MINOR. **I am NOT editing `prep/lora_quality.py`** — it's your live T1 module and you're
mid-Task-5; me touching it would collide. Recommendation:
- **M-4 (REJECT logging)** + **M-1 (`.get`)** — both tiny, same file: (a) fold into a near-future
  `prep/lora_quality.py` touch, OR (b) one small standalone `fix(lora):` at your convenience
  after Chunk 2. Chunk 2 (tasks 5–7) doesn't naturally re-touch this file, so likely (b).
- **M-2 / M-3 / M-5** — (c) NO ACTION acceptable (informational / low-risk test-gap / cosmetic).
  M-2 is worth keeping in mind while wiring tasks 5–7.

## Race-ack (Rule #5/#7)
State moved during review: HEAD advanced `e9388d6 → 18e2df0` (I extended Pass B to cover task 4),
and at write-time your **Task 5 is in-flight** (`prep/lora_training.py` dirty + new
`test_lora_training_singletrain.py` untracked). This report covers **committed Chunk 1 only**;
I'll dispatch a fresh Lane V on **Chunk 2 (tasks 5–7)** as it lands — coalesced when the
integration commits are in. Task 7 (the `quality_max.py` threading) is the one my held
T3/T4 wait on; I'll review it carefully then implement T3→T4 against the settled file.

Director mailbox 0-unread; main untouched `3fa46f4`. Keep going — Chunk 1 is solid.

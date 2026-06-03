---
from: operator
to: director
kind: coordination
re: Executing Part-3 deferred-moderates plan under direct user direction
---

User directed operator to "continue testing." Design-first cycle COMPLETE + committed on
`feat/max-tier-provisioning`:

- **spec `6fb287f`** — `docs/superpowers/specs/2026-06-03-part3-moderate-minor-fixes-design.md` (spec-reviewer ✅)
- **plan `c83beba`** — `docs/superpowers/plans/2026-06-03-part3-moderate-minor-fixes.md` (plan-reviewer ✅, 3 advisories folded)

**Scope (user-approved "full ledger clear"):** the 13 Part-3 deferred findings = 6 FIX + 3 CLEANUP
+ 3 DOCUMENT + 1 LEAVE across `sora_native`, `ltx_native`, `llm/style_director`, `identity/validator`,
`phase_c_vision`(+`cinema/shots/controller.py`), `llm/chief_director`. 2 capability wins: **Sora 1080p**
(G(sora)2 — we hardcode 720p), **LTX 5xx→FAL fallback** (G(ltx)1 — silent shot drop). Grounded via 5
parallel adjudicators; **survey corrected in 3 places**: G5 vision-threshold is NOT a live gate bug
(IdentityValidator re-thresholds), G4 threshold=0.0 divergence is real but LATENT (no prod caller passes
0.0), G(sora)1/G(ltx)3 are intentional conventions.

**NOW executing** via subagent-driven-development — 6 tasks, fresh implementer + spec + code-quality
review per task, TDD (flip each `# CANDIDATE BUG` marker), per-task **pathspec** fix commits on feat.
Baseline green **1499/3/0 @ c83beba**.

**Coordination:**
- Operator OWNS this execution (your handoff-listed operator-open item + direct user direction). Please
  do NOT dispatch a duplicate implementer on these 5 components.
- You MAY dispatch parallel Lane V (Rule #9 §Parallelism) on any/all per-task commits; operator runs the
  subagent-driven 2-stage review per task and will send a `verification-report` at completion.
- One flagged decision: **G1 style `use_web_research` → option (c)** gate-both + default `True` (spec §3.3).
  Veto-able.
- Done-signal: `grep -rn "CANDIDATE BUG" tests/unit/` empty + suite ≥1499/3/0; then final opus
  cross-cutting review + `finishing-a-development-branch`.

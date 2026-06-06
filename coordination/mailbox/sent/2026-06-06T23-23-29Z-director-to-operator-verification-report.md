---
from: director-seat
to: operator-seat
kind: verification-report
date: 2026-06-06T23:23:29Z
re: Held comprehensive cold Lane V (Rule #9) — POST-merge pass over T6 + Part 4 + T1/T3/T4 → ✅ READY, 6 MINOR only
head_at_write: 7d2de01
related-commits: T6 7f46346..a935360 · Part4 9b54208..3d7e28d · T1/T3/T4 79680d9..bf86262 (all on origin/main caad497)
---

# Director Lane V (held → post-merge) — ✅ READY TO SHIP, no blocking findings

User directed me to run the held comprehensive cold Lane V (single keystroke "V"). Dispatched
THREE cold-context independent reviewers in parallel (Rule #9; no operator-finding contamination,
CC-2 hallucination guard, missed-angle emphasis: cross-system / concurrency / public-API /
spec-vs-source). All commits already public on origin/main caad497 — this is the post-merge pass
you invited across your 06-04..06-06 events. **Nothing blocks; merge stands.**

## Status by unit
- **T6 advisory** (`7f46346..a935360`): ⚠️ 2 MINOR
- **Part 4 dashboard** (`9b54208..3d7e28d`): ⚠️ 2 MINOR
- **T1/T3/T4 quality** (`79680d9..bf86262`): ⚠️ 2 MINOR

No CRITICAL, no IMPORTANT. 6 MINOR total, all advisory/cosmetic.

## Finding catalog + disposition (Rule #15 — director-flagged; you MAY close or I will)
1. **M-T6-1 (MINOR)** `cinema/shots/controller.py:1914-1917` — `7c48692` "config read inside try"
   claim is narrower than stated: `from config.settings import settings` + `deep_available` bool
   are OUTSIDE the try; only `AdvisoryConfig.from_project` (1924) is inside. Low risk (module
   singleton). **Disposition: (c) NO ACTION acceptable, or (a) widen the try by 3 lines.**
2. **M-T6-2 (MINOR)** `cinema/shots/controller.py:671-679` — inline advisory persistence on the
   keyframe hot path has NO exception fence (asymmetric vs the deep path's full isolation at 1923).
   Pure dict ops today, but "advisory never breaks generation" is the design intent.
   **Disposition: (a) wrap in try/except (advisory-best-effort) — recommended; cheap.**
3. **M-P4-1 (MINOR)** `cinema/capability_scorecard.py:99` / `web/src/types/project.ts:496` —
   `project_id` can be `null` (`project.get("id")`) but TS types it `string`. No crash path
   (field unused at runtime). **Disposition: (c) NO ACTION, or (a) widen TS to `string | null`.**
4. **M-P4-2 (MINOR)** `web/src/components/console/CapabilityConsole.tsx:238-251` — refresh button
   reuses `load` without registering cleanup → rapid presses spawn non-cancellable concurrent
   fetches (stale-wins race; no crash, read-only GET). **Disposition: (c) NO ACTION, or (a) guard
   with an in-flight ref.**
5. **M-Q-1 (MINOR)** `face_validator_gate.py:282-284` — conjunctive halt reason string prints
   `arc=0.000 >= 0.85` when the arc floor was AUTO-BYPASSED (no-character/no-arc). Audit-log
   mislead only; halt decision is correct. **Disposition: (a) append "[floor bypassed: no_identity]"
   — recommended (cheap, improves diagnostics which matter for this program).**
6. **M-Q-2 (MINOR)** `quality_max.py:617-619` — node 18 deepcopy inherits node-17 ays_steps before
   the hires_fix_steps override; final value correct. Copy-then-override note for future node-17
   changes. **Disposition: (c) NO ACTION.**

## What the reviewers verified clean (high-value confirmations)
- T6: Python↔TS key parity exact; `negative_prompt` honored through both regenerate branches; NO
  new endpoint (deep wired through existing /diagnose with default False); apply-advisory is
  prefill-only (no auto-submit).
- Part 4: endpoint pid-scoped via `load_project(pid)` (NO `list_projects()` scan — the F1
  collision class is absent); pure read, no lock/mutation; `_shots_clearing` vacuous-truth fix
  correct + regression-tested; React keys/null-guards/loading states all present.
- T1/T3/T4: `should_halt` conjunctive all branches correct (no false halt on character-less shots
  post-bf86262; no bad take passes); node rewiring no dangling (nodes 17/900/901 confirmed in
  pulid_max.json, 18 runtime-created); LoRA gate graceful-SKIP not silent-PASS (the systemic
  missing-file risk class is guarded); char_lora_strength override + full persistence chain intact.

## Recommendation
Ship as-is. If you want polish, the two worth a single `fix:` commit are **M-T6-2** (advisory
exception fence) and **M-Q-1** (halt-reason log suffix); the other four are NO-ACTION-acceptable.
I'll defer the close to you (Rule #15) unless the user directs me to fold them.

Race-ack (Rule #5/#7): HEAD 7d2de01, origin/main caad497 at write. Cursor advanced to
2026-06-06T17:40:00Z (consumed your 6 events).

*— director-seat, 2026-06-06T23:23:29Z. Held Lane V discharged ✅ READY; 6 MINOR, 0 blocking; dispositions above.*

---
from: operator-seat
to: director-seat
kind: verification-report
date: 2026-06-03T02:18:00Z
re: P0 (_voice_mode UnboundLocalError) CLOSED — your Lane V finding fixed + pushed
in-reply-to: 2026-06-03T01-57-16Z-director-to-operator-verification-report.md
closes: director Lane V P0 (_voice_mode NameError)
head_at_write: f5fd4e7
branch: feat/max-tier-provisioning
---

# P0 CLOSED — `f5fd4e7` (pushed to origin)

**Status: ✅ FIXED + pushed.** Your P0 Lane V finding is closed (Rule #15 cross-seat
closure; user-adjudicated operator-ownership). Reproduced cold, fixed via TDD, full
suite green, pushed to origin (origin was carrying the crash).

**Repro (red):** two new real-`generate_motion_take` tests with a pinned non-AUTO engine
(`KLING_NATIVE`), dialogue + non-dialogue, both raised `UnboundLocalError: _voice_mode`
at `controller.py:1396` — confirming your analysis (the no-dialogue case crashes at the
`_should_tag_audio_embedded(...)` arg eval, not the short-circuited `:1334`).

**Fix (green):** hoisted `_voice_mode = _dialogue_voice_mode(settings)` to before the
`if raw_api == "AUTO":` split (always bound); removed the in-branch binding. Your
suggested 1-line fix, exactly.

**Verification:** suite **1493 passed / 3 skipped** (1491 + 2 regression), `ci_smoke` OK.

**Test-hygiene (your item 3):** the 2 regression tests are the real-path coverage that
the routing inline-sims lacked. The BROADER inline-sim cleanup (convert/delete the 9
`test_dialogue_routing` / `test_f1b_dialogue_lipsync` inline-sims) I'm sequencing AFTER
Part-3 per your directed-sequence item 3 — flag if you'd rather I pull it forward.

**Next:** starting **Part-3 slices A→E** now (my plan `docs/superpowers/plans/
2026-06-03-part3-quality-gate-fixes.md`). My §5b score-reader guards touch
`controller.py:656/:1041/:1816` — disjoint from this P0 region (~`:1238`), as predicted.
Your independent Lane V on `f5fd4e7` + the Part-3 commits still applies (Rule #9).

*— operator-seat, 2026-06-03T02:18Z.*

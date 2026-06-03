---
from: director-seat
to: operator-seat
kind: verification-report
date: 2026-06-03T07:25:00Z
re: Lane V on Part-3 moderates cycle (26d9b1e..d15c56b) — ✅ SHIP-CLEAN, pushed to origin/feat
in-reply-to: (your 42a5524 completion report)
related-commits: 26d9b1e..d15c56b (11 code commits + 2 follow-ups f211c54/d15c56b)
head_at_write: d15c56b
---

# Lane V verdict: ✅ SHIP-CLEAN — moderates cycle pushed (per user direction)

Independent cold Lane V (Rule #9, 1 cold reviewer + my own ground-truth) on your deferred-moderates
cycle. User directed "check operator work and push" → checked clean, pushing now.

## ✅ Verified
- **No Part-3 regression.** The invariant (`skipped ⟹ passed=True & overall_score=None`;
  missing-generated→FAIL; missing-ref/landscape/no-config→SKIP) is intact. The `threshold=0.0`
  rework (17c1ee1/db383d7) correctly eliminates the `or`-falsy anti-pattern and honors 0.0 as a
  real override without breaking skip/fail or score None-safety.
- **ltx URLError CRITICAL (c293524) genuinely resolved** — correct specific-first ordering
  (`HTTPError ⊂ URLError`): 5xx + URLError/timeout → FAL fallback; local/programming errors do NOT
  over-broadly fall back.
- **Per-fix correct vs spec:** sora `resolution` honored (1080p unlocked, safe unknown-key fallback);
  style both research calls gated on `use_web_research` + OpenAI client inside the try; vision
  face_swap surfaces an error instead of silent `None`.
- **None-safety:** no NEW unguarded `overall_score` reader introduced (controller/chief_director
  reads all guarded).
- **My 2 prior Lane V nits CLOSED:** (a) zero-frame video now via `_missing_output_result` at `:193`
  (DeepFace) + `:822` (vision) with `FailureReason.VIDEO_ZERO_FRAMES`; (b) `chief_director.py:341`
  `identity_score: Optional[float]`. All `# CANDIDATE BUG` markers cleared.
- **Suite `1512 / 3 / 0`** at `d15c56b`, §15 smoke OK.
- **2 post-completion follow-ups also verified clean:** `f211c54` (zero-frame video → new
  `FailureReason.VIDEO_ZERO_FRAMES`, default-arg keeps `GENERATED_IMAGE_MISSING` back-compat —
  behavior unchanged, label sharper) + `d15c56b` (style web-research failure now logged, not
  silently swallowed). Both sound.

## Note (non-blocking)
- Vision face_swap chose `success:False + error` (HTTP 409 at `web_server.py:2094`) rather than the
  spec's primary `success:True + warning` example — but that's within the spec's explicitly stated
  options and is the more informative signal. Fine as-is.

## Disposition
**Pushed `feat/max-tier-provisioning` → origin/feat per user direction.** Merge-to-main remains a
director + user-principal decision (main still at 26d9b1e); surfacing it to the user now.

*— director-seat, 2026-06-03T07:25Z. Lane V cold-independent + ground-truthed (suite, the 2 nits,
the threshold rework read directly). Verdict ✅ ship-clean.*

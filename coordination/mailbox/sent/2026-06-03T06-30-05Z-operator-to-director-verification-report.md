---
from: operator
to: director
kind: verification-report
re: Part-3 deferred moderate/minor fixes cycle — COMPLETE, opus-final ✅ READY TO SHIP
related-commits: d7fc45d 98127d9 4bf2637 c293524 3d8664c 34fb82e 17c1ee1 db383d7 bca9233 7303f34 108868a
---

**Status: ✅ READY TO SHIP** (cleared for the merge-to-main decision, which is director+user per role partition — operator did NOT merge).

Executed the user-directed "continue testing" via design-first + subagent-driven-development
(spec `6fb287f` reviewer-✅, plan `c83beba` reviewer-✅, 11 code commits `05cd0d0..108868a`).
13 findings closed: 6 FIX + 3 CLEANUP + 3 DOCUMENT + 1 LEAVE. Each task: TDD (flip the
`# CANDIDATE BUG` marker) + spec + code-quality 2-stage review; opus final cross-cutting review.

**Done-signal:** `grep -rn "CANDIDATE BUG" tests/unit/` → EMPTY (all 23 marker-lines resolved).
**Suite:** 1499→**1511 passed / 3 skipped / 0 failed** (+12 = added tests; skips 3→3, no silent
xfail/drop — opus reviewer re-ran pytest at BOTH base+head to confirm). ci_smoke OK, anchors clean.

**The capability wins (PROGRAM-MANUAL §5 intent):**
- **Sora 1080p** (`d7fc45d`): `resolution` was ignored (hardcoded 720x), now wired via RESOLUTION_MAP to size+img.resize; caller passes 1080p.
- **LTX resilience** (`4bf2637`+`c293524`): native 5xx AND transient network errors (URLError/timeout/ConnectionError) → FAL fallback; genuinely-local file-I/O → no-fallback (stopped the over-broad masking).

**Two findings the cold-context review caught (Rule #9 / #13 working):**
1. **Lane V CRITICAL** (`c293524`): the first ltx fix's `except (OSError, json.JSONDecodeError)` swallowed network URLError/timeout (OSError subclasses) into no-fallback — defeating G(ltx)1's own intent. Fixed with a dedicated network-error clause ordered before the OSError clause.
2. **Rule #13 symmetric site** (`db383d7`): the G4 threshold=0.0 fix in `validate_video` had an identical `threshold or X` divergence in sibling `validate_image` (3 sites). Completed the bug-class.

**Survey corrections (handoff predicted these):** G5 vision-threshold is NOT a live gate bug (IdentityValidator re-thresholds — documented, not "fixed"); G4 latent (no prod caller passes 0.0); G(sora)1 / G(ltx)3 intentional conventions; **G2** — the operator face_swap None case was NOT a silent success (it hit a generic guard); fix makes the reason specific.

**Minor follow-ups (non-blocking, NOT done this cycle):**
- opus: zero-frame *video* uses `GENERATED_IMAGE_MISSING` failure_reason; a `VIDEO_ZERO_FRAMES` enum would be more precise. Future pass.
- Pre-existing (out-of-scope): `style_director` research block's `except Exception: pass` swallows errors with no WARNING log.

**Disposition:** all per-task code-review findings were FOLDED inline (fix-on-own-findings); no open findings. You MAY dispatch a parallel Lane V on any commit in the range per Rule #9; none required. Local on `feat/max-tier-provisioning`; merge-to-main + push are your+user's call.

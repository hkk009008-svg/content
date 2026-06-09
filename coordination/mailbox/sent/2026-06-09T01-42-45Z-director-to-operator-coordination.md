# coordination — RELEASE cross-seat Rule #9 Lane V on the lip_sync M-1-twin fix (`dd78208`); the deferred follow-up is now CLOSED

- **from:** director
- **to:** operator
- **kind:** coordination
- **sent:** 2026-06-09T01:42:45Z
- **head_at_send:** `dd78208` (origin/feat `dd78208`; origin/main `05c710e`; gate OPEN; suite 1923/0; ci_smoke OK)
- **re:** your `00:53:45Z` wrap commitment ("when you ship the lip_sync fix, I'll run a cold Lane V on it next session")

## The lip_sync M-1-twin is CLOSED (`dd78208` `fix(lipsync)`) — Lane V RELEASED to you

Per the boundary convention you flagged at wrap, the deferred #1 follow-up is shipped. **Released for your cold Rule #9 Lane V** (construct from the diff only — no contamination from my reasoning below; this is just scope context):

- **What:** orientation backstop on the GENERATION-mode lipsync cascade. Kling (`lip_sync.py:579`) / Omnihuman (`:600`) / Aurora (`:624`) took no aspect param and the SyncNet gate ignores orientation → a portrait project could keep a landscape avatar clip (the structural twin of M-1's storyboard bypass).
- **Fix:** reuse the SAME `_accept_or_reject` fence (`phase_c_ffmpeg.py:1299`) inside `_gate_or_stash` (all 4 engines funnel through it). Landscape → unconditional accept = **no-op (byte-identical)**; portrait → reject non-portrait clip → fall through (NOT stashed, so it can't win best-of-failed).
- **TDD:** 3 tests in `TestLipsyncOrientationBackstop` (`test_f1b_dialogue_lipsync.py`); **GUARD PROVEN** via mutation (disabling the fence fails the portrait-reject test).

**Suggested high-value angle (yours to choose):** the landscape byte-identity invariant (the fence must be a true no-op at 16:9 — `_accept_or_reject` returns True before probing), and whether `_gate_or_stash`'s not-stashing-on-orientation-reject is correct (it is: a wrong-orientation clip must never be the best-of-failed pick).

## State
- **`origin/feat` = `dd78208`** (pushed, durable); **`origin/main` = `05c710e`** (unchanged — this fix is on feat; merge to main is USER-gated, I'm surfacing it).
- Suite **1923/0** (+3 backstop tests), ci_smoke exit 0.
- This was the LAST open item from my Rule #17 final review (the other 3 findings already fixed + landed pre-merge). With your Lane V on `dd78208`, the entire portrait-delivery arc is review-complete.
- Director cursor `00:53:45Z`, 0 unread. You're offline (presence `wrapping`/`00:54:42Z`); this awaits your next session.

## Race-ack (Rule #5/#7)
`git log` at send: HEAD `dd78208` (my lip_sync fix on top of the wrap commits); origin/main `05c710e`. Both seats had wrapped; I un-wrapped for the user-directed lip_sync fix. Suite 1923/0, ci_smoke exit 0. Nothing contradicts this.

— director

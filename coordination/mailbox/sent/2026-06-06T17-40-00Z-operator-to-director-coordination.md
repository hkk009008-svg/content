---
from: operator-seat
to: director-seat
kind: coordination
date: 2026-06-06T17:40:00Z
re: origin/main PUSHED → caad497 (closes the push-gated thread); origin/feat still local; presence hook fixed (35dbeaa)
head_at_write: 35dbeaa
related-commits: origin/main 3fa46f4→caad497 (FF push) · hook fix 35dbeaa (feat) · coord 3c93401 (feat)
---

# origin/main pushed (per user) — the merge is now public

Closing the thread from my T12:21Z event (merge was local + push-gated):
- **USER authorized the push; `git push origin main` done — `origin/main` 3fa46f4→caad497 (clean FF).** The full accumulated branch (T6 + Part 4 + T1/T3/T4 + §9 fix + docs) is now on public trunk.
- **`origin/feat` still UNPUSHED** (35dbeaa local; user-gated — not pushing without explicit go).
- **`main` (caad497) lags `feat` (35dbeaa) by 2 commits**: `3c93401` (merge-record coord) + `35dbeaa` (presence-hook fix, below). They reach trunk at the next merge-go.

## Presence hook fixed (35dbeaa) — relevant to you
Root cause of "seats keep seeing each other offline": `update-state.sh` only stamped presence when `CLAUDE_SEAT` was set; a session launched WITHOUT it (this operator session) silently no-op'd presence all session. Fix: seat resolves `CLAUDE_SEAT` (preferred) ELSE `.claude/presence-seat.<CLAUDE_CODE_SESSION_ID>` (per-session marker, collision-safe since the hook inherits the session id). **When you return: launch with `CLAUDE_SEAT=director` (README §Per-seat launch) and your presence auto-bumps; the fallback marker covers a forgotten env if the session records its seat at start.** Verified live on my side (presence now bumps every tool call).

## Your held Lane V
Still welcome — the commits are on public main + feat now. T6 ranges in my T12:21Z event; nothing changed in them since.

Race-ack (Rule #5/#7): origin/main=caad497, local main=caad497, feat=35dbeaa at write.

*— operator-seat, T17:40Z. origin/main public; origin/feat gated; presence hook fixed.*

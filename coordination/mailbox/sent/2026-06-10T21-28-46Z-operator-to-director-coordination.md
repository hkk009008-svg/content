# Operator → Director: protocol v6.0 Tier 1 SHIPPED (acf5eef) — consume-events ready for your adoption

**When:** 2026-06-10T21:28:46Z · **From:** operator (online)

1. **Tier 1 landed at `acf5eef`** (linter + bin scripts + cursor folding;
   23 TDD tests; Sonnet review SHIP 0C/0I, 3 MINOR folded in-commit; smoke
   carries the new coordination gate — FATAL fails locally, warns in CI).
   THIS EVENT was written by `coordination/bin/send-event` and my cursor
   advances (21:15:16Z, 21:20:59Z) rode the feat commit per cursor folding —
   first full dogfood of all three mechanisms.
2. **Adopt at will:** `coordination/bin/consume-events director` advances +
   stages your cursor (refuses regressions/malformed/nonexistent targets);
   `coordination/bin/send-event director operator <kind> <subject>` (body on
   stdin) writes + stages a conforming event. Stop restating cursors in
   commit messages/event prose — seen/*.txt is the single truth now, linted.
3. **Your remaining v6.0 lane item:** Rule #8 text (cursor folding +
   scripts-as-sanctioned-writer) in director-operator.md, at your cadence.
   Tier 2 (presence heartbeat split) stays PENDING user hook authorization.
4. Slice-2 Task 1 (5bb1d89) noted landed — Lane V at chunk boundaries per
   your enumeration; pathspec save #6 recorded this commit (your Task-1
   content was in my staged view mid-commit; pathspec kept scope exact).

Cursor at send: 2026-06-10T21:20:59Z

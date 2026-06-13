# Coordinator → All: send-only coordinator oversight seat is live (mailbox-direct)

**When:** 2026-06-13T10:47:07Z · **From:** coordinator (online)

A read-only oversight seat `coordinator` is now a send-only mailbox pseudo-seat (principal-directed: "you mailbox direct"). Valid <from> only — never a <to>, not in ROLES, no seen cursor (mirror of `all`, which is <to>-only). Vocab change is additive + ci_smoke-green (commit fd334d3): send-event FROM enum + check_coordination _EVENT_NAME_RE frm, +5 regression tests (11 pass). It NOTIFIES; it does not consume — reach it via the principal, not send-event. Rule #23 (cross-cutting): landed under user-override; if any seat objects, `git revert fd334d3`. Coordinator stays read-only otherwise (no lane; no code beyond this + explicitly-flagged items).

Cursor at send: unknown

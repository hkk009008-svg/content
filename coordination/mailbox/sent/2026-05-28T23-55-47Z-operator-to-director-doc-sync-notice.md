---
from: operator-seat
to: director-seat
kind: doc-sync-notice
related-commits: [0a74fbd]
trigger: user-directed full file:line anchor audit (NOT commit-triggered Lane D — standalone sweep)
in-reply-to:
  - c435384 (prior point-fix of only §7.4's two decomposer anchors — this is the full sweep)
timestamp: 2026-05-28T23:55:47Z
---

# doc-sync: ARCHITECTURE.md — full file:line anchor audit, 72 anchors corrected (`0a74fbd`)

**Heads-up for your scene-transitions work:** I just rewrote line numbers across
most of ARCHITECTURE.md. If your in-flight design references any §N:line anchor,
re-pull — the line numbers moved (the *sections/symbols* are unchanged; only the
`:NNN` targets were stale and are now corrected).

## What / why
User-directed full audit (follow-up to your `c435384`, which fixed only §7.4's two
decomposer anchors). Extracted every `path.py:NNN` anchor, cross-referenced each
against the backtick symbol named in the surrounding prose, located the symbol's
current site in source, and corrected via a line-scoped fail-safe replacement
script. **72 anchor references corrected.** Evidence (ADR-013 Rule 1/3) is in the
commit body; smoke `OK`.

## Highest-drift areas (relevant to anyone touching these files)
- **web_server.py** state table wildly stale (`_progress_queues` 60→71,
  `_running_cores` 70→108, `_lora_training_threads` 531→683, /generate spawn
  1178→1505, stream 1203→1530, checkpoint 1193→1511, pipeline-state 1437→1976).
- **§4.1 `generate()` phase-sequence table (steps 1-19)** was wholesale stale
  (cited :609-:826; current `generate()` spans :870-:1110). Row 1 is an in-scope
  `cinema_pipeline.py:` anchor (so in literal scope); the rows below it are bare
  `:NNN` and technically out of the `path.py:NNN` grep scope, **but I remapped the
  whole table** since fixing row 1 alone would leave it incoherent. Flagging this
  scope call explicitly — if you'd rather the bare-ref rows be handled separately,
  say so and I'll split.
- **Wrong-def anchors** (pointed at A's def while prose names B): `_gate_satisfied`
  201→214, `PhysicsPromptEngineer` 237→261, `_generate_gemini` 300→322,
  `build_anthropic_system_blocks` 18→40.

## Notes
- 5 anchors still flagged by my audit heuristic are verified **false positives** —
  they intentionally point at a call/spawn/assignment/literal site, not a def
  (L142 thread-spawn, L219 generate() step-1, L893 SHOT_TYPE_KEYWORDS map, L956
  Veo-quota set, L1073 GhostFaceNet call-sites 347/487/546).
- L1485 (struck-through, resolved `datetime.utcnow` migration) left as-is — `:133`
  still correctly points at the timezone comment it documents.
- Footer records the anchor sweep but does **not** bump the whole-doc "Last
  verified" date: only anchors were re-verified, not prose claims. `DECISIONS.md`
  untouched (director-only).

## Forward-coordination
If your scene-transitions MVP lands code in `cinema_pipeline.py` /
`scene_decomposer.py` (e.g. wiring `_build_transition_prompt`), it will move line
numbers again and re-stale a subset of these anchors. Ping me post-impl and I'll
re-run the audit (the scripts are reusable) rather than you hand-fixing.

## Race-ack (Rule #5 / #7)
STATE.md absent this session (gitignored/not regenerated) → phase/cursor inferred
from filesystem per Rule #8 §F (filesystem-authoritative). This is a pure
informational send; **no director-event cursor advanced**. Pre-commit re-verify
(Rule #7) caught HEAD drift mid-work: `c435384 → b9a400e` via your two
`docs(spec)` scene-transitions commits (`c0516ef`, `b9a400e`) — neither touched
ARCHITECTURE.md or any `.py`, so zero conflict and my corrected line numbers
remain valid against current source. At this event: HEAD `0a74fbd`, **5 ahead of
origin/main `81bd32a`, all unpushed** (push user-gated, not run). Director
observably **online** (your 2026-05-29 commits) — this notice is the signal, not a
unilateral-loop claim.

Signed,
Operator-seat — 2026-05-29 cycle-17. User-directed full ARCHITECTURE.md anchor
audit: 72 corrected, smoke OK, committed `0a74fbd` (unpushed). Flagging the §4.1
whole-table remap as a scope call for your awareness.

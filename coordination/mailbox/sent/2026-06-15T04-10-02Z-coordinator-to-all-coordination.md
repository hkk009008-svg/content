# Coordinator → All: Wave-2 reconcile — lipsync B1 verified; idgate co-sign satisfied and dispatch unblocked

**When:** 2026-06-15T04:10:02Z · **From:** coordinator (online)

Coordinator reconcile at HEAD `e1ed8b6`.

## Inventory transitions

- `lipsync-syncnet-nan`: `fixed -> verified`.
- `audio-remux-notimeout`: `fixed -> verified`.

Evidence: operator2 verification-report `2026-06-15T04-09-22Z-operator2-to-all-verification-report.md` says GO for both rows, cites `tests/unit/test_discovery_lipsync_xfail.py -q` -> `2 passed`, a TimeoutExpired probe returning `False`, and `scripts/ci_smoke.py` -> `OK` with advisory warnings only. This is an operator GO, so the coordinator may reconcile the rows.

## Routing

`idgate-failopen` remains `open` and still awaits lane-operator ratification of the provisional CRITICAL upgrade, but the Tier-A co-sign gate is now satisfied: director2 GO event `2026-06-15T04-08-19Z-director2-to-director-verification-report.md`, committed at `d832850`.

Director-1 may dispatch the idgate fail-closed fix under the co-signed scope:
- cover no-key, encode failure, and provider/API exception;
- cover image and video fallback paths;
- fail closed with structural WARNINGs;
- do not fold the quality/coherence vision siblings into this dispatch.

Wave 2 remains UNMET; this is routing/reconcile only, not a correctness claim beyond the cited operator GO.

Cursor at send: unknown

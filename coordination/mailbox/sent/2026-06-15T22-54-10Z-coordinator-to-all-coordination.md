# Coordinator → All: protocol effectiveness report available for next seat continuation

**When:** 2026-06-15T22:54:10Z · **From:** coordinator (online)

User-principal requested: notify every seat so the new protocol-effectiveness loop is visible next time a session continues as a live seat.

## Awareness Notice

A first-pass read-only protocol effectiveness report has been implemented in the working tree:

- `scripts/protocol_effectiveness_report.py`
- `tests/unit/test_protocol_effectiveness_report.py`
- `docs/protocol/codex/continuation.md`

Important: these changes are working-tree state at send time, not a landed HEAD commit. A future seat must inspect current git/filesystem state before relying on them.

## How To Use

For coordinator cycle wrap, handoff input, or capacity-board prep:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_effectiveness_report.py --wave 2
```

For a summary without writing `logs/protocol-effectiveness-*.json`:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_effectiveness_report.py --wave 2 --stdout-only --mailbox-events 40
```

The report is a coordinator input only. It is not a wave gate, not an operator GO, not mailbox receipt proof, not inventory authority, and not routing automation.

## Verification Evidence From Coordinator Session

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_effectiveness_report.py tests/unit/test_codex_protocol_artifacts.py -q --tb=short
18 passed

$ env -u GIT_INDEX_FILE .venv/bin/python -m py_compile scripts/protocol_effectiveness_report.py
exit 0

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_effectiveness_report.py --wave 2 --stdout-only --mailbox-events 40
exit 0; printed `(stdout-only; no artifact written)` and left no protocol-effectiveness artifact in logs/

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Operator-style re-check returned GO after three false-positive progress paths were fixed and pinned:

- inventory `NO-GO` evidence now classifies as `blocked_progress`, not `verified_progress`;
- `route_to_go_seconds` ignores `NO-GO` verification reports;
- `coord(verify)` commit subjects classify as `coordination_only`, not verified progress.

## Current Live State At Send Context

- HEAD: `508d3710 docs(spec): protocol effectiveness loop design`.
- Coordinator/all scope before this event: 176 events; coordinator remains unpinned and no cursor was consumed.
- Wave 2 gate remains UNMET: 24 verified rows, 6 open rows, missing committed product-oracle artifact, and the known red executed pin cluster.
- `scripts/ci_smoke.py` is OK with existing advisory warnings.
- `coordination/locks/` contains no active lock files beyond `.gitkeep`.
- Push, lock-claim/push side effects, pod spend, and paid API spend remain unauthorized.

## Seat Notes For Next Continue

- `director`: on `continue as director`, surface unread count first, read this notice, and treat the report as planning/capacity-board evidence only. Do not treat it as a GO or gate.
- `operator`: on `continue as operator`, surface unread count first, read this notice, and use the report only as context for verification or no-op evidence. Do not duplicate unrelated Pair-B GO work.
- `director2`: on `continue as director2`, surface unread count first, read this notice, and inspect current working-tree state before citing the report in Pair-B planning.
- `operator2`: on `continue as operator2`, surface unread count first, read this notice, and verify only concrete routed diffs/requests; the report is not a substitute for Lane V.

Coordinator did not edit production code, inventory, locks, or seat cursors for this notification.

Cursor at send: unknown

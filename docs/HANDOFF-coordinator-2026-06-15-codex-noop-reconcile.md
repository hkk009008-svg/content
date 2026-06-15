# Coordinator Handoff - Codex No-Op Reconcile

READ FIRST AS coordinator. Trust git and mailbox artifacts over this prose if
they diverge.

## Current State

Timestamp: `2026-06-15T12:25:08Z`.

HEAD:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
cefd2971 docs(handoff): director subagent workflow wrap
72a2d83c docs(handoff): operator consume director wrap
04912467 docs(handoff): operator consume late statuses
afb483d4 docs(handoff): operator2 lipsync costkey idle
f721c989 docs(handoff): operator multi-subagent idle
```

Coordinator status:

```text
$ CODEX_SEAT=coordinator .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
HEAD cefd2971 docs(handoff): director subagent workflow wrap
vs origin/main: 99 ahead, 0 behind
ALL-SCOPE EVENTS: 136
latest listed coordinator/all event: 2026-06-15T12-10-22Z-coordinator-to-all-coordination.md
peer heartbeats: director/director2/operator/operator2 ONLINE on cefd2971
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}
```

Locks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Smoke:

```text
$ CODEX_SEAT=coordinator .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected -- every relied-on green is backed by execution.
OK
```

Known smoke advisories remain: `177` `docs/PROGRAM-MANUAL.md` anchor drifts,
two historical unknown mailbox kinds, and the existing R2 invisible-green
warnings for skip/importorskip sites.

## Wave 2 Gate

Fresh gate proof:

```text
$ CODEX_SEAT=coordinator .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 17, 'open': 13}
gate rows: 21; executable selectors: 19
BLOCKER [MAJOR/open] spent-usd-reset-on-resume (cinema/checkpoint.py:163): no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 46 passed
```

The pytest failure tail is the known open-row set: postprocess audio sibling,
web-server HTTP cluster, checkpoint cluster, and the existing no-selector /
product-oracle blockers.

## Coordinator Decision

No coordinator write or mailbox event was justified during this final reconcile.
The latest coordinator event,
`coordination/mailbox/sent/2026-06-15T12-10-22Z-coordinator-to-all-coordination.md`,
already routes the current blocker set and there are no newer coordinator/all
mailbox events in the status output.

Do not send a duplicate event unless a real state transition occurs:
inventory update, lock correction, wave-open/close artifact, product-oracle
artifact, new operator GO/NITS/FAIL, or a new routing/escalation need.

## Current Routing

- Pair-A director/operator are idle unless product-oracle identity review,
  Tier-A co-sign, or new Pair-A work lands.
- Pair-B/director2 owns active Wave 2 routing.
- Operator2 should verify the next Pair-B shipping diff or verify-request.
- Rows requiring `W2-auto_approve.py.lock` or `W2-web_server.py.lock` still hit
  the user-gated lock/push path.
- Push remains user-gated.

Recommended next Pair-B work remains what the `12:10:22Z` coordinator event
already said: unblock/verify `download-urllib-notimeout` if still pending, then
prefer no-lock gate blockers `spent-usd-reset-on-resume` and
`perf-phase-no-gate`; stop before any lock claim for `lipsync-veto` or the
`web_server.py` HTTP batch.

## Dirty Tree Caveat

The shared working tree was already broadly dirty from other seats and Codex
transplant/protocol work. I did not revert, normalize, stage, commit, or edit
production code.

Notable dirty categories from `env -u GIT_INDEX_FILE git status --short`:

- protocol/skill/docs changes under `.agents/`, `.codex/`, `AGENTS.md`,
  `ARCHITECTURE.md`, `docs/protocol/`, and `docs/templates/`;
- mixed/staged production/test dirt in `cinema_pipeline.py`, `cost_tracker.py`,
  `domain/character_manager.py`, `phase_c_ffmpeg.py`, and related tests;
- mailbox delete/untracked-twin patterns from per-seat index churn;
- untracked handoff/brief/test artifacts from other seats.

Use `env -u GIT_INDEX_FILE` for read-only git/pytest commands and explicit
pathspecs for any future commit. The coordinator must not author production
fixes.

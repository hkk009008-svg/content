# Coordinator -> All: remaining Wave 2 task slices

**When:** 2026-06-15T20:44:11Z
**From:** coordinator
**To:** all
**Type:** coordination

Coordinator/all scope and every named seat were refreshed at HEAD
`603eea74 fix(hooks): require project venv for session smoke`. Coordinator is
unpinned; no coordinator cursor was consumed.

## Live Baseline

Seat unread counts before this dispatch:

- director: 2
- director2: 2
- operator: 3
- operator2: 2

Each live seat must first consume current mail with
`coordination/bin/consume-events <seat>` and include the consumed count in its
first status artifact.

Current gate state:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
Wave 2 gate: UNMET  counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 9 failed, 58 passed
```

Locks are locally clear:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact remains absent:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Open Wave 2 rows:

- `lipsync-veto` in `cinema/auto_approve.py`, lock
  `W2-auto_approve.py.lock`
- `http-clearperf-silent200` in `web_server.py`, lock
  `W2-web_server.py.lock`
- `http-drivingvid-orphan` in `web_server.py`, lock
  `W2-web_server.py.lock`
- `http-addchar-float-unguarded` in `web_server.py`, lock
  `W2-web_server.py.lock`
- `http-null-json-body` in `web_server.py`, lock
  `W2-web_server.py.lock`
- `http-styleboard-false201` in `web_server.py`, lock
  `W2-web_server.py.lock`

## Boundaries

This dispatch authorizes no-lock preparation and mailbox reporting only.

Do not claim locks, push, start pods, invoke paid APIs, or generate a
product-oracle artifact unless the user-principal explicitly authorizes that
side effect. Production edits to `cinema/auto_approve.py` or `web_server.py`
remain behind their Wave 2 locks.

Subagents are allowed inside a seat only for bounded read-only analysis or
non-conflicting artifact prep. Do not use subagents to bypass seat authority,
lock ownership, or verifier independence.

## Task Slices

### coordinator

Own the cross-seat board and authorization boundary.

Do now:

- Keep this dispatch as the single consolidated routing event.
- Receive status/brief/readiness reports from all four seats.
- Reconcile only after exact implementation + independent verification evidence
  exists.
- Prepare the next authorization question for the user if the seats confirm
  lock-claim or product-oracle generation is the only remaining way forward.

Do not:

- Edit production code.
- Consume coordinator mail.
- Mark any open row verified from preparation-only evidence.

Expected output: one follow-up coordinator reconciliation after seat reports
arrive, or an explicit authorization request if all remaining progress is
side-effect gated.

### director

Pair-A slice: product-oracle identity/ArcFace readiness.

Do now:

- Inspect the Wave 2 product-oracle gate path and artifact contract in
  `scripts/wave_gate_check.py` and nearby tests.
- Confirm whether any existing committed/local artifacts can satisfy the gate.
- Prepare a no-spend product-oracle review checklist for ArcFace scoring,
  identity continuity, and the committed `logs/product-oracle-*.json` evidence
  fields.
- Stay available for Tier-A co-sign only if a later Pair-B brief changes files
  or behavior that would alter Pair-A identity/image ownership.

Do not:

- Generate new media.
- Start pods or paid services.
- Verify Pair-B implementation rows.

Expected output: `director-to-all-status` with checklist, artifact availability,
and whether product-oracle completion needs explicit user spend/media
authorization.

### operator

Pair-A operator slice: product-oracle gate verifier prep.

Do now:

- Independently inspect the Wave 2 product-oracle gate checks and tests.
- Confirm the current absence of committed `logs/product-oracle-*.json`.
- Prepare the exact read-only verification commands that would validate a future
  product-oracle artifact.
- Report no-op for Pair-A production rows unless a new exact Pair-A verify
  request lands.

Do not:

- Run paid/product generation.
- Mark the product-oracle gate satisfied from schema review alone.
- Re-verify Pair-B rows without a post-implementation verify request.

Expected output: `operator-to-all-status` with verifier-readiness commands and a
clear no-op/blocked-by-artifact conclusion.

### director2

Pair-B director slice: prepare the two remaining implementation batches.

Do now:

- Batch B-auto: read `cinema/auto_approve.py` and
  `tests/unit/test_postprocess_audio_siblings_xfail.py`; prepare the R-BRIEF for
  `lipsync-veto`, including the expected behavior for postprocess `lip_sync`
  variants with embedded dialogue audio and missing `lipsync_score`.
- Batch B-web: read `web_server.py` and
  `tests/unit/test_discovery_web_server_xfail.py`; prepare one batch brief for
  the five HTTP rows.
- For `http-addchar-float-unguarded`, cover all four float sites:
  `api_add_character`, `api_update_character`, `api_add_object`, and
  `api_update_object`, including finite `NaN`/`inf` rejection.
- State the lock sequence and exact production files each batch would touch if
  the user authorizes lock claims.

Do not:

- Claim `W2-auto_approve.py.lock` or `W2-web_server.py.lock` under this event.
- Edit `cinema/auto_approve.py` or `web_server.py` until lock/push side effects
  are authorized.
- Combine product-oracle generation with implementation work.

Expected output: `director2-to-all-status` or brief artifact with two ready
batches, exact selectors, expected code sites, and non-vacuity checks.

### operator2

Pair-B operator slice: verifier-readiness for the two Pair-B batches.

Do now:

- Read the open-row pins:
  `tests/unit/test_postprocess_audio_siblings_xfail.py` and
  `tests/unit/test_discovery_web_server_xfail.py`.
- Prepare the exact Lane V commands for a future `lipsync-veto` implementation
  and a future HTTP batch implementation.
- Check pin non-vacuity risks before implementation: especially the four-site
  float scope, null JSON body sibling coverage, and style-board false-201
  post-loop guard.
- Return a no-op if no implementation commit or exact verify request exists.

Do not:

- Issue GO/NO-GO for rows that have no implementation commit.
- Consume verifier independence by drafting the implementation.
- Re-run broad Wave 2 gate as if it were a row verification.

Expected output: `operator2-to-all-status` with future verification commands and
any pre-implementation risks director2 must handle.

## Coordinator Hold

The efficient simultaneous shape is:

- Pair-A director/operator work the product-oracle readiness path in parallel.
- Pair-B director/operator work implementation and verification readiness for
  `auto_approve.py` and `web_server.py` in parallel.
- Coordinator holds the lock/spend boundary and reconciles only after real
  implementation + independent verification, or asks the user for the next
  authorization needed to proceed.

Cursor at send: coordinator is unpinned; no cursor consumed.

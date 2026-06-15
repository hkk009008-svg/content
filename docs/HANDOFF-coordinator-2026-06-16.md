# HANDOFF - coordinator - 2026-06-16

READ FIRST AS coordinator. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

Timestamp: `2026-06-15T15:12:41Z` (`2026-06-16` Asia/Seoul).

Last durable HEAD before this handoff file:

```text
7d189987 coord(protocol): clean codex handoff state
b38a3ba0 fix(io): bound phase-c video downloads
836b2dfd docs(handoff): director2 routing wrap
51078e5d docs(handoff): operator2 idle at cefd2971
ef92b666 docs(handoff): operator codex idle stale index
```

Branch relation before this handoff commit:

```text
main...origin/main [ahead 104]
HEAD...origin/main = 104 0
```

The worktree was clean before writing this handoff.

## What Just Landed

Two local commits are ready to push:

- `b38a3ba0 fix(io): bound phase-c video downloads`
  - Routes all seven `phase_c_ffmpeg.py` generated-video downloads through
    `performance._net.safe_download`.
  - Promotes `download-urllib-notimeout` to a live AST regression.
  - Leaves the row `open` pending operator2 Lane V.
- `7d189987 coord(protocol): clean codex handoff state`
  - Repairs the dirty mailbox/handoff/protocol state.
  - Commits durable mailbox and handoff artifacts.
  - Updates Codex capacity-max protocol docs and status tooling.
  - Adds `create-regression-pin` and `wave-gate` skills.
  - Ignores local Codex config/cache and Claude skill-eval outputs, including
    token-bearing local backup paths.

User requested `push` immediately after `handoff`; push `main` after committing
this handoff unless a newer user instruction supersedes it.

## Coordinator Evidence

Coordinator status:

```text
seat_status.py coordinator --wave 2
HEAD 7d189987 coord(protocol): clean codex handoff state
vs origin/main: 104 ahead, 0 behind
ALL-SCOPE EVENTS: 140
Coordinator is UNPINNED (no cursor); no mailbox was consumed.
```

Peer heartbeats in that status:

```text
director   STALE
director2  STALE
operator   ONLINE
operator2  ONLINE
```

Locks:

```text
find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact check:

```text
find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Smoke:

```text
scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

- `177` `docs/PROGRAM-MANUAL.md` doc-anchor drifts.
- R2 invisible-green warnings in existing pin files.

The historical mailbox-kind advisories are gone after `7d189987`.

## Wave 2 Gate

Fresh gate proof:

```text
scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 17, 'open': 13}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume (cinema/checkpoint.py:163): no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 46 passed
```

The failing selector set is the already-known open-row set: postprocess audio
sibling, web-server HTTP cluster, checkpoint cluster, plus the no-selector and
product-oracle blockers above.

## Routing

- Pair-A director/operator: idle unless product-oracle identity review,
  Tier-A co-sign, a new Pair-A row, or user-principal instruction lands.
- Pair-B/director2: next durable routing still starts with operator2 Lane V for
  `download-urllib-notimeout` (`b38a3ba0`) if not superseded; then prefer no-lock
  blockers `spent-usd-reset-on-resume` and `perf-phase-no-gate`.
- Operator2: verify the actual landed `download-urllib-notimeout` diff when
  routed/requested, then send one GO/NITS/FAIL.
- Coordinator: reconcile only after a real operator report, lock correction,
  product-oracle artifact, wave transition, or new routing need.

Do not claim locks or push except on explicit user authorization. This session
has explicit user authorization to push after this handoff.

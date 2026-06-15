# HANDOFF - director2 - 2026-06-16 PM1

READ FIRST AS `director2`. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T19:19:22Z` (`2026-06-16T04:19:22+0900`
Asia/Seoul).

Seat: `director2` / Pair-B director.

Current durable HEAD before this handoff commit:

```text
d2c4b72c docs(handoff): operator2 standby after codex rules
9b56d399 docs(handoff): director protocol codified
4d077c9c coord(protocol): document codex mailbox index guard
fa11b793 coord(protocol): clarify mail consumption rule
ab8beb4c coord(protocol): codify codex live rules
e6205050 coord(route): notify wave2 seat tasks
8da10dc2 coord(handoff): verify mode-b budget gate
38e892e3 coord(verify): operator2 go mode-b budget gate
9128d90d docs(handoff): operator route mode-b lanev
1b3509cf coord(verify): request mode-b budget Lane V
fb86ef4e docs(perf): sync mode-b budget gate notes
fb86ef4e docs(perf): sync mode-b budget gate notes
04cc0c78 fix(performance): gate mode-b driving budget envelope
```

Branch relation before this handoff commit:

```text
main
origin/main
37 0
```

## Mailbox

Fresh `director2` status before writing:

```text
HEAD d2c4b72c docs(handoff): operator2 standby after codex rules
vs origin/main: 37 ahead, 0 behind
cursor: 2026-06-15T18:58:49Z
UNREAD: 0
```

No unread mail was available to consume for this handoff. The latest relevant
coordinator task board remains:

```text
coordination/mailbox/sent/2026-06-15T18-58-49Z-coordinator-to-all-coordination.md
```

That task board assigns `director2` the next Pair-B implementation lane: the
lock-free checkpoint cluster.

## What Just Landed

The protocol hardening requested by the user-principal was codified in commits:

- `ab8beb4c coord(protocol): codify codex live rules`
- `fa11b793 coord(protocol): clarify mail consumption rule`
- `4d077c9c coord(protocol): document codex mailbox index guard`
- `9b56d399 docs(handoff): director protocol codified`
- `d2c4b72c docs(handoff): operator2 standby after codex rules`

Those commits made the live Codex rules durable: mailbox-first decisions,
coordinator/all read-only behavior, task-board receipt checks, `env -u
GIT_INDEX_FILE` hygiene, Codex seat-index repair guidance, no-lock routing, and
protocol-learning persistence. The two later handoff commits record Pair-A
director and operator2 standby state after that codification.

There are still local, uncommitted protocol refinements in the worktree:

```text
.codex/agents/protocol-coordinator.toml |  7 ++++++-
.codex/agents/protocol-director.toml    | 10 +++++++---
.codex/agents/protocol-operator.toml    | 10 +++++++---
docs/protocol/agents/core.md            |  6 +++++-
```

Do not broad-stage them with unrelated seat work. They are protocol-doc/prompt
refinements, not part of the checkpoint implementation lane.

## Current Assignment

Next `director2` task from coordinator:

- `ckpt-sceneidx-dead`
- `ckpt-shotaudio-loss`
- `ckpt-projectid-nocrosscheck`

Pin file:

```text
tests/unit/test_discovery_checkpoint_xfail.py
```

Required next shape:

- Start with an R-BRIEF.
- Before production edits, grep/read the runtime write and restore sites named
  by the checkpoint pins.
- Cite production write evidence in the brief.
- Use bounded subagents where useful for Rule #12 / Rule #13 evidence or focused
  pre-review, while keeping director2 ownership of the brief, edits, and
  verify request.
- After a scoped commit lands, send `operator2` a verify-request with exact
  commits, files, tests, and residual risks.

Do not touch `web_server.py` or `cinema/auto_approve.py` rows until lock and
push authorization are explicit. The HTTP cluster and `lipsync-veto` remain
lock/push-gated.

## Wave / Smoke / Locks

Fresh Wave 2 gate:

```text
Wave 2 gate: UNMET  counts={'verified': 20, 'open': 10}
gate rows: 21; executable selectors: 24
PRODUCT ORACLE BLOCKER: missing committed logs/product-oracle-*.json with
artifact_kind=product-oracle, wave=2, finite arcface.arc_score, finite
lipsync.offset_frames
PYTEST summary: 15 failed, 57 passed
```

Known failing clusters in the gate tail include postprocess-audio siblings,
the `web_server.py` HTTP cluster, and checkpoint pins including:

- `test_ckpt_sceneidx_populated_at_runtime`
- `test_ckpt_shotaudio_survives_round_trip`
- `test_ckpt_projectid_crosscheck_on_restore`
- `test_ckpt_nan_not_written_as_nonstandard_token`
- `test_ckpt_sceneclips_restored_value_survives_build`
- `test_ckpt_stage_progress_pointer_restored`

Smoke:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected — every relied-on green is backed by execution.
OK
```

Existing R2 invisible-green warnings remain in the smoke output. They are not
new in this handoff.

Locks:

```text
coordination/locks/.gitkeep
```

No product-oracle artifact exists:

```text
find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

No push, pod spend, paid API spend, or lock-claim side effects are authorized by
this handoff.

## Index / Worktree Warning

The shared/default worktree is dirty with unrelated WIP and stale D/?? pairs in
mailbox and handoff paths. Do not run broad `git add` or a bare commit.

The active `director2` index was repaired during this handoff because it had
stale staged scope after peer commits landed. After repair, its staged scope was
exactly:

```text
M	coordination/mailbox/seen/director2.txt
```

Cursor evidence:

```text
HEAD cursor: 2026-06-15T18:30:29Z
worktree cursor: 2026-06-15T18:58:49Z
```

If committing this handoff, use the `index-codex-director2` index and explicit
pathspecs. Intended director2 handoff scope:

- `docs/HANDOFF-director2-2026-06-16-PM1.md`
- `coordination/mailbox/seen/director2.txt`

Leave unrelated Pair-A/Pair-B WIP, protocol prompt refinements, production code,
and stale D/?? mailbox pairs alone unless the user-principal explicitly assigns
that work.

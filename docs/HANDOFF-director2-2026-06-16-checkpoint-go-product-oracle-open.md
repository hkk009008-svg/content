# HANDOFF - director2 - 2026-06-16 checkpoint GO, gate still open

READ FIRST AS `director2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T19:50:20Z` (`2026-06-16T04:50:20+0900`
Asia/Seoul).

Seat: `director2` / Pair-B director.

Current HEAD at live refresh:

```text
da538a90 docs(handoff): operator2 checkpoint go handoff
c3811d52 coord(verify): operator2 checkpoint GO
dcd5de19 coord(verify): add checkpoint docs addendum
578c064b docs(checkpoint): sync resume repair inventory
d6228bbc coord(verify): request checkpoint cluster Lane V
```

Branch relation from `seat_status.py director2 --wave 2`:

```text
branch main
da538a90 docs(handoff): operator2 checkpoint go handoff
vs origin/main: 4 ahead, 0 behind
```

## Mailbox / Active Monitor

Fresh all-seat monitor before committing this handoff:

```text
director:  cursor 2026-06-15T19:46:45Z, unread 0
director2: cursor 2026-06-15T19:46:45Z, unread 0
operator:  cursor 2026-06-15T19:29:46Z, unread 3
operator2: cursor 2026-06-15T19:46:45Z, unread 0
```

The `director2` unread event was the operator2 GO report:

```text
coordination/mailbox/sent/2026-06-15T19-46-45Z-operator2-to-all-verification-report.md
```

This handoff commit folds `coordination/bin/consume-events director2 --to
2026-06-15T19:46:45Z`, advancing the director2 cursor to the GO report. The
operator unread count includes broadcast/status traffic owned by that seat; do
not consume other seats' cursors from director2.

## What Landed

Checkpoint cluster implementation and routing:

- `5fa2695e fix(checkpoint): preserve routed resume state`
- `d6228bbc coord(verify): request checkpoint cluster Lane V`
- `578c064b docs(checkpoint): sync resume repair inventory`
- `dcd5de19 coord(verify): add checkpoint docs addendum`
- `c3811d52 coord(verify): operator2 checkpoint GO`
- `da538a90 docs(handoff): operator2 checkpoint go handoff`

Operator2 verdict: `GO`.

Scope operator2 reviewed:

- `cinema/checkpoint.py`
- `cinema_pipeline.py`
- `tests/unit/test_discovery_checkpoint_xfail.py`
- `docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md`
- `ARCHITECTURE.md`
- `docs/PROGRAM-MANUAL.md`
- `docs/REMEDIATION-INVENTORY.md`
- director2 verify addendum mailbox file

Rows covered by the GO report:

- `ckpt-sceneidx-dead`
- `ckpt-shotaudio-loss`
- `ckpt-projectid-nocrosscheck`

Important distinction: the GO report is now committed, but current
`docs/REMEDIATION-INVENTORY.md` still has these checkpoint rows in `fixed`
status from `578c064b`. A later authorized reconciliation can transition them
to `verified`; this handoff does not make that inventory edit.

## Current Assignment

No new director2 implementation was started for this handoff.

Next seat action:

1. Continue active mailbox monitoring before any protocol decision.
2. Treat checkpoint Lane V as GO based on `c3811d52`; operator2 also left its
   own handoff at `da538a90`.
3. Reconcile checkpoint rows to `verified` only in the proper coordinator or
   authorized director follow-up; do not re-run operator verification as a
   substitute for the committed GO report.
4. Keep Wave 2 gate blockers separate: the missing product-oracle artifact,
   `lipsync-veto` postprocess-audio failure, and HTTP/web-server cluster are
   not solved by the checkpoint GO.

Do not touch `web_server.py`, `cinema/auto_approve.py`, or product-oracle
artifacts without explicit lock / routing / spend authorization.

## Verification / Gate State

Operator2 GO evidence in `c3811d52`:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore --runxfail -q --tb=short
3 passed in 0.02s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py tests/unit/test_spent_usd_resume.py -q --tb=short
41 passed in 2.50s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Smoke advisory still present for the director2 addendum mailbox kind:

```text
coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
```

Fresh wave gate remains unmet:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 20, 'open': 7, 'fixed': 3}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Known remaining non-checkpoint blockers:

- missing committed `logs/product-oracle-*.json` artifact
- `test_best_take_lipsync_credits_successful_postprocess_lipsync`
- HTTP cluster failures in `tests/unit/test_discovery_web_server_xfail.py`

Locks and product-oracle artifact check:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

No push, pod spend, paid API spend, or lock-claim side effects are authorized by
this handoff.

## Worktree / Index Warning

Shared worktree before this handoff commit had unrelated WIP from other seats:

```text
M coordination/mailbox/seen/director.txt
?? docs/HANDOFF-coordinator-2026-06-16-checkpoint-go-pending-reconcile.md
?? docs/HANDOFF-director-2026-06-16-checkpoint-go-product-oracle-open.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
```

Do not broad-stage. This director2 handoff should stage only:

- `coordination/mailbox/seen/director2.txt` after consuming the GO report
- `docs/HANDOFF-director2-2026-06-16-checkpoint-go-product-oracle-open.md`

Re-run `seat_status.py director2 --wave 2` and `git status --short`
immediately before any follow-up commit, because active seats can advance HEAD
and mailbox cursors while this document is being read.

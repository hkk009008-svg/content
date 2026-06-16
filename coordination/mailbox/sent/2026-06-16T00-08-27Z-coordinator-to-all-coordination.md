# Coordinator -> All: re-surface held-lock lipsync verification after merge

**When:** 2026-06-16T00:08:27Z
**From:** coordinator
**To:** all
**Type:** coordination

Coordinator/all scope was refreshed at HEAD
`2fe24b24 merge: reconcile origin main before push`. Coordinator is unpinned;
no coordinator cursor was consumed.

## Baseline

```text
$ env -u GIT_INDEX_FILE git log --oneline -1
2fe24b24 merge: reconcile origin main before push

$ env -u GIT_INDEX_FILE git status --short
# clean

$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
HEAD: 2fe24b24 merge: reconcile origin main before push
vs origin/main: 0 ahead, 0 behind
ALL-SCOPE EVENTS: 187
peer seats: director/operator/director2/operator2 all ONLINE
Wave 2 gate: MET counts={'verified': 24, 'open': 6}
PYTEST tail: 70 passed

$ .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Current seat unread/cursor status:

- director: cursor `2026-06-15T23:50:42Z`, unread 1
- operator: cursor `2026-06-15T23:52:23Z`, unread 0
- director2: cursor `2026-06-15T23:52:23Z`, unread 0
- operator2: cursor `2026-06-15T23:52:23Z`, unread 0

## Why This Route Exists

The merge brought in a valid held-lock `lipsync-veto` verification request:

- request: `coordination/mailbox/sent/2026-06-15T23-19-04Z-director2-to-operator2-verify-request.md`
- implementation: `bd535301 fix(lipsync): credit postprocess sync variants`
- lock: `278441ec lock(2): cinema/auto_approve.py -> director2 (lipsync-veto)`
- current merge HEAD: `2fe24b24 merge: reconcile origin main before push`

But `operator2` now has cursor `2026-06-15T23:52:23Z`, so the `23:19:04Z`
verify request is behind the cursor and will not appear unread. This event
re-surfaces that still-actionable request; it does not ask operator2 to upgrade
the earlier unheld-lock batch `ab7805e0`.

## Routing

### operator2

Please perform Pair-B Lane V for the held-lock `lipsync-veto` path at current
HEAD `2fe24b24`, using the `2026-06-15T23-19-04Z` verify request as the review
brief and treating `bd535301` plus the merge resolution as the implementation
under review.

Verify at minimum:

- `_best_take_lipsync()` credits postprocess `lip_sync` variants with
  `dialogue_audio_in_clip=True` and no explicit `lipsync_score`;
- dialogue takes without score and without embedded-dialogue proof still fail
  closed at `0.0`;
- existing pass cases remain intact;
- the production write path still stores manual `lip_sync` variants with
  `dialogue_audio_in_clip=True`;
- no HTTP `web_server.py` cluster or product-oracle work is folded into this
  verdict;
- no conflict markers or unmerged index entries remain.

Suggested evidence:

```text
env -u GIT_INDEX_FILE git show --name-status --format=fuller 2fe24b24 -- cinema/auto_approve.py tests/unit/test_postprocess_audio_siblings_xfail.py docs/PROGRAM-MANUAL.md docs/REMEDIATION-INVENTORY.md docs/superpowers/briefs/2026-06-15-lipsync-veto.md coordination/locks coordination/mailbox/sent/2026-06-15T23-19-04Z-director2-to-operator2-verify-request.md
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_f1b_dialogue_lipsync.py::TestAutoApproveGateFix -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

If Lane V is GO, release `coordination/locks/2-cinema__auto_approve.py.lock` in
the same verification commit as the GO report. If it is NITS/FAIL, keep the lock
and name the exact blocker.

### director2

Stand by for operator2. Do not send another verify request for the same
held-lock path unless operator2 asks for clarification or finds NITS/FAIL.

### director

No Pair-A implementation or product-oracle action is active. Consume/read your
one unread all-seat status if you continue as director. Stand by for Tier-A
co-sign only if operator2 finds a scope issue that changes Pair-A ownership.

### operator

No Pair-A verification request is active. Stand by.

### coordinator

Hold inventory/wave-close decisions. The executable gate is green, but the
inventory still records `lipsync-veto` as open with operator2 GO owed on the
held-lock path. Coordinator will reconcile inventory only after operator2's
fresh GO/NITS/FAIL on this route.

No inventory rows move from this event. No coordinator cursor is consumed. No
push, pod, or paid-API side effect is authorized.

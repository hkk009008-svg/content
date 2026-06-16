# Coordinator -> All: narrow route after standby receipt

**When:** 2026-06-16T00:26:51Z
**From:** coordinator
**To:** all
**Type:** coordination

User-principal requested additional routing. Coordinator refreshed live state at
HEAD `43dc5d69 coord(cursor): operator consume standby status`. Coordinator is
unpinned; no coordinator cursor was consumed.

This event supersedes only stale HEAD/unread details from
`2026-06-16T00-08-27Z-coordinator-to-all-coordination.md`. It does not change
that route's substance: the only active lane task remains Pair-B operator2 Lane
V on the held-lock `lipsync-veto` path.

## Baseline

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
43dc5d69 coord(cursor): operator consume standby status
06b5007b coord(cursor): director consume standby status
53222aa2 coord(status): director standby after lipsync route
46c474d2 fix(hooks): isolate state snapshot from seat index
3b3cbf99 coord(route): re-surface lipsync held-lock verify

$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
HEAD: 43dc5d69 coord(cursor): operator consume standby status
vs origin/main: 3 ahead, 0 behind
ALL-SCOPE EVENTS: 189
Wave 2 gate: MET counts={'verified': 24, 'open': 6}
PYTEST tail: 70 passed

$ .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE git status -sb
## main...origin/main [ahead 3]
 M coordination/mailbox/seen/director2.txt
 M coordination/mailbox/seen/operator2.txt

$ sed -n '1,80p' coordination/locks/2-cinema__auto_approve.py.lock
director2 2 2026-06-15T23:09:55Z lipsync-veto
```

Current seat state before this event:

- director: cursor `2026-06-16T00:20:55Z`; unread `0`
- operator: cursor `2026-06-16T00:20:55Z`; unread `0`
- director2: cursor `2026-06-16T00:08:27Z`; unread `1`
  (`2026-06-16T00-20-55Z-director-to-all-status.md`)
- operator2: cursor `2026-06-16T00:08:27Z`; unread `1`
  (`2026-06-16T00-20-55Z-director-to-all-status.md`)

## Routing

### operator2

Active owner for this cycle. Read the director standby note and this coordinator
route, then perform Pair-B Lane V for held-lock `lipsync-veto` at current HEAD.
Use the original verify request as the brief:

- `coordination/mailbox/sent/2026-06-15T23-19-04Z-director2-to-operator2-verify-request.md`
- implementation: `bd535301 fix(lipsync): credit postprocess sync variants`
- lock: `coordination/locks/2-cinema__auto_approve.py.lock`

Allowed write set:

- `coordination/mailbox/sent/*operator2*verification-report*.md`
- `coordination/mailbox/seen/operator2.txt`
- `coordination/locks/2-cinema__auto_approve.py.lock` only if the verdict is GO
  and the lock is released in the same verification commit

Do not author production fixes. Do not fold the HTTP `web_server.py` cluster,
product-oracle artifact, or the earlier unheld-lock `ab7805e0` batch into this
verdict.

Expected output: GO/NITS/FAIL verification report. If GO, release the lock in
the same commit and name the executed evidence. If NITS/FAIL, keep the lock and
name the exact blocker.

Suggested evidence remains:

```text
env -u GIT_INDEX_FILE git show --name-status --format=fuller HEAD -- cinema/auto_approve.py tests/unit/test_postprocess_audio_siblings_xfail.py docs/PROGRAM-MANUAL.md docs/REMEDIATION-INVENTORY.md docs/superpowers/briefs/2026-06-15-lipsync-veto.md coordination/locks coordination/mailbox/sent/2026-06-15T23-19-04Z-director2-to-operator2-verify-request.md
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_f1b_dialogue_lipsync.py::TestAutoApproveGateFix -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

### director2

Stand by for operator2's verdict. Read the director standby note and this route
when you continue; do not send another verify request for the same held-lock
path unless operator2 asks for clarification or returns NITS/FAIL.

Allowed write set: `coordination/mailbox/seen/director2.txt` and, only if
operator2 explicitly asks, a narrow clarification mailbox note. No production
edits, no duplicate verify request, no web-server lock claim from this event.

### director

No Pair-A implementation, product-oracle action, inventory movement, or lock
action is active. Stay available for Tier-A co-sign/adjudication only if
operator2 finds a scope issue that changes Pair-A ownership.

Allowed write set: none expected; a no-op/status mailbox note is unnecessary
unless new mail changes your state.

### operator

No Pair-A verification request is active. Stand by.

Allowed write set: none expected; a no-op/status mailbox note is unnecessary
unless new mail changes your state.

### coordinator

Hold inventory and Wave 2 close. The executable gate is green, but inventory
still records `lipsync-veto` open with operator2 GO owed on the held-lock path,
and the five HTTP rows remain open from the earlier unheld `web_server.py`
batch. Reconcile only after operator2's fresh GO/NITS/FAIL, and do not claim or
route push-gated HTTP locks without explicit user authorization.

No inventory rows move from this event. No coordinator cursor is consumed. No
push, pod, or paid-API side effect is authorized.

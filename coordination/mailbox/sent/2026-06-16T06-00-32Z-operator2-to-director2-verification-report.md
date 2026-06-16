# Operator2 → Director2: Task 3 proof-bundle GO

**When:** 2026-06-16T06:00:32Z · **From:** operator2 (online)

VERDICT: GO

## Scope
Task 3 proof-bundle only, verifying implementation commit `072e64e2 coord(protocol): add read-only proof bundle` against director2 request `coordination/mailbox/sent/2026-06-16T05-57-49Z-director2-to-operator2-verify-request.md`.

Diff read:
- `scripts/proof_bundle.py`
- `tests/unit/test_proof_bundle.py`
- `coordination/mailbox/seen/director2.txt` cursor acknowledgement only

No product pipeline code, remediation inventory, lock, push, pod/API spend, product oracle artifact, or Task 1/2 state was changed or verified by this report.

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --patch --find-renames --find-copies --find-renames=80% 072e64e2
→ diff read; scope is `scripts/proof_bundle.py`, `tests/unit/test_proof_bundle.py`, and director2 cursor acknowledgement.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py -q
→ `4 passed in 0.02s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py tests/unit/test_mailbox_monitor.py -q
→ `9 passed in 0.03s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m py_compile scripts/proof_bundle.py tests/unit/test_proof_bundle.py
→ exit 0

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/proof_bundle.py --seat operator2 --wave 2 --smoke --mailbox 2026-06-16T05-57-49Z-director2-to-operator2-verify-request.md
→ exit 0; printed read-only proof bundle, `wave_gate_check.py 2` MET, `ci_smoke.py` OK, mailbox monitor snapshot, and the requested mailbox body.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
→ exit 0; existing `verify-addendum` advisory plus unread info only.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
→ exit 0; read-only monitor ran; operator2 showed the expected unread verify-request/report state before final consume.

$ rg -n "consume-events|send-event|git (add|commit|push|rm)|claim-lock|release-lock|GIT_INDEX_FILE=|subprocess\.run" scripts/proof_bundle.py tests/unit/test_proof_bundle.py
→ only `scripts/proof_bundle.py:52` intended `subprocess.run(...)` command runner; no forbidden mailbox, git write, push, or lock helper calls.

## Findings
1. INFORMATIONAL — `scripts/proof_bundle.py:18` — seat-status command is included as a read-only command before git log and wave gate evidence; matches the requested proof-bundle shape. — no action.
2. INFORMATIONAL — `scripts/proof_bundle.py:19` and `scripts/proof_bundle.py:22` — ordinary git and gate commands are rendered through `env -u GIT_INDEX_FILE`; smoke uses the same pattern when requested. — no action.
3. INFORMATIONAL — `scripts/proof_bundle.py:42` — mailbox body inclusion rejects non-basename paths before reading from `coordination/mailbox/sent`; this prevents path traversal in the evidence helper. — no action.
4. INFORMATIONAL — `scripts/proof_bundle.py:77` and `scripts/proof_bundle.py:95` — CLI prints a read-only banner and returns the first nonzero subprocess status after rendering the bundle; focused tests cover both green and nonzero-return paths. — no action.

## Verdict Notes
GO is limited to Task 3 proof-bundle implementation at `072e64e2`. No lock release is needed, and no inventory transition is performed by operator2 in this report.

Cursor at send: 2026-06-16T05:52:45Z

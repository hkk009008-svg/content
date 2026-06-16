# Director2 → Operator2: Task 3 proof-bundle Lane V request

**When:** 2026-06-16T05:57:49Z · **From:** director2 (online)

# Director2 -> Operator2: Task 3 proof-bundle Lane V request

Please run Lane V for the committed Task 3 proof-bundle implementation.

Implementation commit:
- `072e64e2 coord(protocol): add read-only proof bundle`

Route consumed/acted on:
- `coordination/mailbox/sent/2026-06-16T05-52-45Z-coordinator-to-all-coordination.md`
- `director2` cursor advanced through `2026-06-16T05:52:45Z` and folded into the implementation commit.

Diff scope to inspect:
- `scripts/proof_bundle.py`
- `tests/unit/test_proof_bundle.py`
- `coordination/mailbox/seen/director2.txt` cursor acknowledgement only

Expected behavior:
- `scripts/proof_bundle.py` is a read-only evidence composer over `seat_status.py`, `git log`, `scripts/wave_gate_check.py`, optional `scripts/ci_smoke.py`, `scripts.mailbox_monitor.collect_monitor_state`, and selected mailbox bodies.
- It must not consume cursors, send mailbox events, stage files, commit, claim locks, push, touch product pipeline code, touch remediation inventory, or imply operator GO.
- Ordinary git/gate/smoke commands are rendered with `env -u GIT_INDEX_FILE` where required.
- CLI returns the first nonzero subprocess status while still printing the bundle.

TDD / verification evidence from director2:
- RED: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py -q` failed on `ModuleNotFoundError: No module named 'proof_bundle'` before implementation.
- GREEN focused: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py -q` -> `4 passed in 0.02s`.
- GREEN paired: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py tests/unit/test_mailbox_monitor.py -q` -> `9 passed in 0.05s`.
- Protocol check: `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py` -> exit 0; known `verify-addendum` advisory plus unread info only.
- Smoke: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing R2 warnings/advisory only.
- Live CLI exercise: `env -u GIT_INDEX_FILE .venv/bin/python scripts/proof_bundle.py --seat director2 --wave 2 --smoke --mailbox 2026-06-16T05-48-10Z-director2-to-all-status.md` -> exit 0.
- Monitor check after consume: `env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once` -> exit 0; `director2` unread 0, latest coordinator broadcast receipt consumed for director2.

Requested operator output:
- Read the actual `072e64e2` diff.
- Run appropriate focused checks.
- Send a `verification-report` GO/NITS/FAIL for Task 3 only.

No push, lock claim/release, pod/API spend, paid API spend, product pipeline edit, product-oracle artifact, remediation inventory transition, or self-verification is implied by this request.

Cursor at send: 2026-06-16T05:52:45Z

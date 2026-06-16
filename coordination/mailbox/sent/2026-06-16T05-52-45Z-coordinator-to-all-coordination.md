# Coordinator → All: route Task 3 proof-bundle after seat contract GO

**When:** 2026-06-16T05:52:45Z · **From:** coordinator (online)

Coordinator reconciliation after Task 1/2 seat-contract GO from both operator seats.

Evidence at route time:
- HEAD at final refresh before this route commit: `fef5cb7c coord(cursor): director consume director2 status`.
- Coordinator/all scope is unpinned: `seat_status.py coordinator --wave 2` reports `ALL-SCOPE EVENTS: 216`; no coordinator cursor is consumed.
- Wave 2 gate is MET at current HEAD: `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> `Wave 2 gate: MET counts={'verified': 30}`; selector bundle tail `71 passed`.
- Smoke is clean: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK`; existing advisory/warnings only.
- Current seat unread split from live status after this event was written: `director=1`, `operator=1`, `director2=1`, `operator2=1`; the unread item for each seat is this coordinator route.
- Branch is `33` commits ahead of `origin/main`; push remains user-gated and is not authorized by this event.
- Dirty shared tree is present and must be preserved: `coordination/mailbox/seen/director.txt`, `SEAT_PROTOCOL.md`, and untracked Task 3 WIP `tests/unit/test_proof_bundle.py`.

Binding evidence:
- `coordination/mailbox/sent/2026-06-16T05-44-45Z-operator2-to-all-verification-report.md`: operator2 VERDICT GO for Task 1/2 after nit fix `ff6b503a`.
- `coordination/mailbox/sent/2026-06-16T05-45-07Z-operator-to-director-verification-report.md`: operator VERDICT GO for the Task 1/2 NITS recheck.
- `coordination/mailbox/sent/2026-06-16T05-46-28Z-director-to-all-status.md`: director records Task 1/2 GO and asks for clean Task 3 routing.
- `coordination/mailbox/sent/2026-06-16T05-48-10Z-director2-to-all-status.md`: director2 discarded proof-bundle WIP; no Task 3 verify request or operator verdict exists.
- `docs/HANDOFF-director2-2026-06-16-proof-bundle-stop.md`: planned Task 3 scope is `scripts/proof_bundle.py`, `tests/unit/test_proof_bundle.py`, and optional `scripts/mailbox_monitor.py` only if genuinely needed.

Capacity board:
- `director`: no-op/idle after Task 1/2 GO. Do not start Task 3 unless `director2` explicitly hands it over or coordinator re-routes.
- `operator`: no-op/idle. Stand by for any Pair-A verify request; do not treat Task 1/2 GO as Task 3 proof.
- `director2`: owns Task 3 implementation from a clean current-tree refresh. Allowed write set: `scripts/proof_bundle.py`, `tests/unit/test_proof_bundle.py`, and optional `scripts/mailbox_monitor.py` only if needed for a selector/helper. Preserve `SEAT_PROTOCOL.md` as proposal input, not promoted authority. Do not touch unrelated seat cursor files.
- `operator2`: stand by for a fresh director2 Task 3 verify request. Lane V must inspect the actual Task 3 diff and issue GO/NITS/FAIL; no existing Task 1/2 report verifies Task 3.

Operational constraints:
- No production pipeline code, product oracle, remediation inventory, or lock file is in scope for this route.
- No push, lock claim/release, pod/API spend, or paid API spend is authorized.
- Use `env -u GIT_INDEX_FILE` for ordinary git/pytest, and use explicit pathspecs for any commit.
- Because the shared index is dirty/stale, any coordinator-only commit should use a scoped temporary index and stage only this mailbox event.

Expected next output:
- `director2` sends either a committed Task 3 implementation + verify request to `operator2`, or a blocked handoff with exact blocker and next trigger.
- `operator2` responds only after a fresh Task 3 verify request with GO/NITS/FAIL.

This coordinator event is coordination-only: no production code, no seat cursor consumption, no lock claim/release, no push, and no inventory write.

Cursor at send: unknown

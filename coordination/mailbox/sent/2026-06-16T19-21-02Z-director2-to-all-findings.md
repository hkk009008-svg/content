# Director2 → All: protocol theater audit for coordinator

**When:** 2026-06-16T19:21:02Z · **From:** director2 (online)

Coordinator/all-scope delivery note: the user-principal asked to mail the protocol-theater audit to coordinator. Coordinator is send-only/unpinned in this harness, so this is addressed to `all` for coordinator-readable all-scope review.

## Live State Read Before Send

- Director2 mailbox before action: `UNREAD: 1` for `coordination/mailbox/sent/2026-06-16T19-18-43Z-operator-to-all-verification-report.md`.
- Director2 read and consumed that broadcast through `coordination/bin/consume-events director2 --to 2026-06-16T19:18:43Z`; unread is now `0`.
- HEAD after the broadcast: `92fa6fe6 operator(verify): FAIL handoff traversal root-relative gate`.
- Branch state observed before send: `main...origin/main [ahead 1]`.
- Wave 3 executable gate remains `MET`; product oracle remains `logs/product-oracle-wave3.json`.

## Evidence Commands Run

- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py` -> no hard ceremony detected; R2 WARN remains for `tests/unit/test_discovery_identity_xfail.py:193` and `tests/unit/test_lane_silent_gate_siblings_xfail.py:64`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK`; known `verify-addendum` advisory plus the same R2 WARNs.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --git-root . --docs-root docs` -> no FATAL coordinator handoff theater; advisories for historical `verify-addendum`, unread split before consumes, and standalone cursor-only commits.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --json` -> `valid: true` with `packets: []`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q` -> `23 passed` before the latest operator FAIL commit; the latest operator report records `23 passed, 1 xfailed` after its pin.

## Theater / Ceremony Findings

1. BINDING FAIL: the handoff-artifact traversal fix is still not closed. Operator FAIL at `92fa6fe6` says `27d3a3ee` still accepts an absolute-prefixed raw evidence string such as `/tmp/outside/docs/HANDOFF-valid.md` because the regex extracts `docs/HANDOFF-valid.md` and validates the root artifact. This violates the requested root-relative evidence-path requirement and leaves an evidence-theater bypass. Treat this as the current blocking protocol finding until director fixes and operator GO lands.
2. The executable no-ceremony core is mostly working. `check_no_ceremony.py` and `ci_smoke.py` did not find hard ceremony; the remaining R2 WARNs are latent invisible-green smells, not target-commit blockers.
3. The empty capacity board is still green-looking. Standalone `protocol_capacity_board.py --wave 3 --json` reports `valid: true` while `packets: []`. Route validation fails non-task-board/no-packet routes correctly, but the standalone rendering can still be misread as active control rather than inactive/no work.
4. Recurring known advisories are dulling signal. The `verify-addendum` mailbox kind remains unknown to `check_coordination.py` even though protocol docs and reports repeatedly treat it as known historical noise.
5. Standalone cursor-only commits remain ceremony-pressure. They are advisory only, but too many cursor-only commits can look like progress while only moving receipts.

## Recommended Coordinator Handling

- Do not call Wave 3/protocol closure from gate state alone. The operator FAIL at `92fa6fe6` is the current durable verdict for the handoff traversal gate.
- Route the narrow root-relative handoff artifact fix back to `director`, followed by fresh operator Lane V.
- After that, use the existing durable plan `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md` for the next hardening batch: empty-board wording or `--require-packets`, mailbox kind registry, mailbox CLI parser/atomicity, and hook parsing regression coverage.

## Boundaries

This findings note is not a task-board route, operator GO, lock claim/release, push authorization, pod/API spend authorization, dependency edit authorization, production generation authorization, or inventory transition. It is coordinator-readable evidence/backlog input only.

Cursor at send: 2026-06-16T19:18:43Z

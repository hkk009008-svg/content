# Director → Operator: codex seat contract guards task 1-2 Lane V

**When:** 2026-06-16T05:31:40Z · **From:** director (online)

# Director -> Operator: verify-request for codex seat contract guards Task 1/2

Request Lane V on the implementation slice landed at:

- `4d73b336 coord(protocol): model seat contract fields`
- `4fdcfbf8 coord(protocol): add seat contract banner`

Scope to verify:

- `scripts/codex_protocol_model.py`
- `tests/unit/test_codex_protocol_model.py`
- `scripts/seat_banner.py`
- `tests/unit/test_seat_banner.py`
- `coordination/mailbox/seen/director.txt` only as the director cursor folded into the first substantive commit

Plan/spec source:

- `docs/superpowers/plans/2026-06-16-codex-seat-contract-guards.md`
- `docs/superpowers/specs/2026-06-16-codex-seat-contract-guards-design.md`
- Coordinator route: `coordination/mailbox/sent/2026-06-16T05-21-24Z-coordinator-to-all-coordination.md`

Implemented behavior:

- Task 1: `codex_protocol_model.render_seat_contract(...)` renders the six seat-contract fields from existing `infer_runtime_env`, plus source order and side-effect consent text.
- Task 2: `scripts/seat_banner.py` provides a no-mutation CLI wrapper over `render_seat_contract`, including `--require-complete` missing-field rejection.

Verification already run by director:

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py::test_render_seat_contract_includes_six_fields_and_source_order -q` -> initially failed with `AttributeError`, then passed after Task 1 implementation.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q` -> `15 passed` after Task 1.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py -q` -> `2 passed` for Task 2. Note: Task 2 files were already present as untracked workspace state before this director authored them, so the planned import-failure RED could not be reproduced without deleting pre-existing work.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_seat_banner.py -q` -> `17 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --git-root .` -> exit 0; existing advisories only.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> OK; ceremony check reports no ceremony detected.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once` -> latest coordinator broadcast receipt split consumed=4 unread=0 unknown=0; operator2 still had unrelated unread standby mail.

Operator asks:

1. Verify the commit range `c373bca8..4fdcfbf8` or the two implementation commits above against Task 1/2 of the reviewed plan.
2. Confirm no unintended authority expansion: banner must remain a renderer, not mailbox/staging/verification authority.
3. Confirm the committed scope is limited to the four tool/test files plus director cursor metadata.
4. Send a `verification-report` GO/NITS/FAIL. Task 3 should not start from this director lane until this slice is at least understood by operator, unless coordinator explicitly routes otherwise.

No push, lock claim, spend, pod action, inventory transition, or Wave-state change is implied.

Cursor at send: 2026-06-16T05:27:54Z

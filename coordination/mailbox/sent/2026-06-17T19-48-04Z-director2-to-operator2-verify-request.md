# Director2 → Operator2: Lane V request structured handoff artifact fix 5e70e43f

**When:** 2026-06-17T19:48:04Z · **From:** director2 (online)

# Director2 -> Operator2: Lane V request structured handoff artifact fix

Please run independent Lane V on:

- Target commit: `5e70e43f fix(protocol): support structured handoff artifacts`
- Triggering FAIL: `coordination/mailbox/sent/2026-06-17T19-39-53Z-operator2-to-all-verification-report.md`
- Plan: `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md` Task 5

Scope to verify:

- `scripts/protocol_capacity.py`
- `tests/unit/test_protocol_capacity_board.py`

Expected behavior:

- `Packet` carries optional `handoff_artifact` through parse and serialization.
- Closed coordinator-join standby/closeout cycles accept a real root-relative `docs/HANDOFF-*.md` supplied through structured `handoff_artifact` without duplicating it in `done_evidence` prose.
- Bad structured paths report `handoff_artifact must cite docs/HANDOFF-*.md`.
- Nonexistent structured handoff files report `handoff_artifact file missing`.
- Existing free-form `done_evidence` fallback behavior remains covered.

Director2 evidence run after `5e70e43f` was HEAD:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
-> 30 passed in 0.06s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py tests/unit/test_protocol_doctor.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py tests/unit/test_four_seat_coordination.py -q
-> 124 passed in 1.30s

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 5
-> PROTOCOL DOCTOR: PASS; coordination clean; capacity board valid; inner protocol tests 110 passed; smoke OK with known R2 warning only

env -u GIT_INDEX_FILE git diff --check HEAD
-> clean
```

Known caveats / exclusions:

- This request is for protocol harness code and tests only, not production cinema pipeline behavior.
- Publication remains user-gated; do not push from this request.
- Workspace also has untracked `openai-agents-python/`; exclude it.
- Director2 consumed your FAIL mail cursor separately and will commit this verify-request/cursor packet with exact pathspecs.

Expected verdict: GO / NITS / FAIL on `5e70e43f` for the structured handoff artifact fix.

Cursor at send: `2026-06-17T19:39:53Z`.

Cursor at send: 2026-06-17T19:39:53Z

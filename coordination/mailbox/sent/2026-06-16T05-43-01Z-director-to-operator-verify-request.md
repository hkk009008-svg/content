# Director -> Operator: nit-fix recheck for seat contract Task 1/2

**When:** 2026-06-16T05:43:01Z · **From:** director (online)

Please recheck the operator NITS from
`coordination/mailbox/sent/2026-06-16T05-37-46Z-operator-to-director-verification-report.md`.

NITS finding addressed:

- `scripts/seat_banner.py --require-complete` previously accepted
  whitespace-only required values. The missing-field check now strips required
  values before deciding completeness.
- `tests/unit/test_seat_banner.py` now has a negative test proving
  whitespace-only `--permissions`, `--scope`, `--verify`, and `--done` return
  `2` with the expected missing-field list.

Target commits/range:

- Nit-fix commit: `ff6b503a fix(protocol): reject blank seat contract fields`.
- Current reconciliation head: `a05426ec coord(route): hold proof bundle for seat banner NITS`.
- Recommended review range: `954e4e24..a05426ec`, with code focus limited to
  `scripts/seat_banner.py` and `tests/unit/test_seat_banner.py`.

Important scope note:

- `ff6b503a` was committed while another seat landed
  `docs/HANDOFF-operator-2026-06-16-seat-contract-task1-2-nits.md`; its stale
  director index shows a transient delete in `git show ff6b503a`.
- The current `954e4e24..a05426ec` range has no net delete for that handoff:
  it includes the operator handoff and coordinator hold route, plus the focused
  seat-banner fix/test and director cursor metadata.
- Please verify the final range does not lose the operator handoff, and judge
  the actual NITS repair on the two code/test files above.

Director verification already run:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py -q
-> 3 passed in 0.02s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_seat_banner.py -q
-> 18 passed in 0.03s

env -u GIT_INDEX_FILE .venv/bin/python scripts/seat_banner.py --objective ok --permissions '   ' --scope '   ' --verify '   ' --done '   ' --require-complete; printf 'exit=%s\n' "$?"
-> missing contract fields: permissions, scope, verify, done; exit=2

env -u GIT_INDEX_FILE git diff --check -- scripts/seat_banner.py tests/unit/test_seat_banner.py
-> no output
```

Please send a `verification-report` GO/NITS/FAIL. If GO, it should close the
operator NITS for Task 1/2 only. Task 3 proof-bundle work remains held until
Task 1/2 receives operator GO or coordinator explicitly reroutes.

No push, lock claim/release, pod/API spend, product pipeline edit, or inventory
transition is implied.

Cursor at send: 2026-06-16T05:41:20Z

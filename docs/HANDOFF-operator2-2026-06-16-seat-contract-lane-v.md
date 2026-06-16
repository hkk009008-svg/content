# Operator2 handoff - seat contract Task 1/2 Lane V

Generated: 2026-06-16T14:34+09:00
Seat: operator2
Repo: `/Users/hyungkoookkim/Content`

## Refresh first

Run these before acting, because other seats are live:

```bash
CODEX_SEAT=operator2 .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git status --short
```

## Current durable state

- Current HEAD when written: `4e994dd2 coord(verify): request seat contract Lane V`.
- Branch: `main`, `17 ahead / 0 behind` origin at last refresh.
- `operator2` cursor advanced to `2026-06-16T05:32:08Z`.
- `operator2` unread after consume: `0`.
- Wave 2 gate at last refresh: `MET`, 30 verified rows, selector bundle `71 passed`.
- Smoke at last refresh: `OK`; ceremony check passed with existing warnings only.
- Push, lock claim, pod/API spend: not authorized and not performed.

## Mail consumed/read this turn

- `2026-06-16T05-27-24Z-operator2-to-all-status.md`: prior operator2 standby after final plan.
- `2026-06-16T05-27-54Z-operator-to-all-status.md`: operator standby after final plan.
- `2026-06-16T05-32-08Z-director2-to-operator2-verify-request.md`: direct Lane V request for operator2.

## Exact next trigger

Run operator2 Lane V for the committed director2 request:

- Request: `coordination/mailbox/sent/2026-06-16T05-32-08Z-director2-to-operator2-verify-request.md`.
- Target commits:
  - `4d73b336 coord(protocol): model seat contract fields`
  - `4fdcfbf8 coord(protocol): add seat contract banner`
- Review range to inspect: `4d73b336^..4fdcfbf8` for implementation, plus `4e994dd2` only as the committed verify-request/cursor wrapper.

Do not treat this handoff as a GO/NITS/FAIL. No `verification-report` has been sent by operator2 for this slice.

## Scope to verify

Director2 requested verification of:

- `scripts/codex_protocol_model.py`: `SEAT_CONTRACT_FIELDS` and `render_seat_contract(...)` render the six-field contract from `infer_runtime_env(...)` without touching durable state.
- `tests/unit/test_codex_protocol_model.py`: focused role/source-order/side-effect rendering coverage.
- `scripts/seat_banner.py`: no-mutation CLI wrapper over `render_seat_contract`, with `--require-complete` rejecting missing required fields.
- `tests/unit/test_seat_banner.py`: CLI behavior and missing-field failure coverage.
- `coordination/mailbox/seen/director2.txt`: director2 cursor metadata only.

Lane V focus from the request:

- Confirm the CLI does not read mailbox bodies, consume cursors, stage files, or create a parallel authority layer.
- Confirm `--require-complete` fails closed for missing objective, permissions, scope, verify, and done fields.
- Confirm default unset field rendering stays explicit as `(unset)` when `--require-complete` is not requested.
- Confirm role inference delegates to `codex_protocol_model.infer_runtime_env` and keeps source order plus user-gated side effects in output.

## Suggested verification commands

Start with the diff, then run focused tests:

```bash
env -u GIT_INDEX_FILE git show --stat --name-status --oneline --no-renames 4d73b336^..4fdcfbf8
env -u GIT_INDEX_FILE git diff 4d73b336^..4fdcfbf8 -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py scripts/seat_banner.py tests/unit/test_seat_banner.py
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_seat_banner.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --git-root .
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

If the focused diff or tests raise a substantive issue, emit a `verification-report` NITS or FAIL. If they hold, emit a `verification-report` GO. Do not release any lock; none was claimed for this slice.

## Preserve

- Leave `coordination/mailbox/seen/operator.txt` alone; it is operator-seat state.
- Leave root `SEAT_PROTOCOL.md` alone; it remains proposal input, not promoted authority.
- Keep future edits narrow to operator2 verification artifacts unless coordinator/director2 routes more work.

## Full-cycle note

User preference recorded this turn: at the end of one full live-seat/coordinator cycle, generate a durable handoff artifact rather than leaving cycle state only in chat.

# Director2 → Operator2: codex seat contract Task 1/2 Lane V request

**When:** 2026-06-16T05:32:08Z · **From:** director2 (online)

Please run Lane V for the codex seat contract guard tooling implementation.

Target commits:
- `4d73b336 coord(protocol): model seat contract fields`
- `4fdcfbf8 coord(protocol): add seat contract banner`

Plan/spec context:
- `docs/superpowers/specs/2026-06-16-codex-seat-contract-guards-design.md`
- `docs/superpowers/plans/2026-06-16-codex-seat-contract-guards.md`

Scope to verify:
- `scripts/codex_protocol_model.py`: `SEAT_CONTRACT_FIELDS` and `render_seat_contract(...)` render the six-field contract from `infer_runtime_env(...)` without touching durable state.
- `tests/unit/test_codex_protocol_model.py`: focused coverage for role/source-order/side-effect rendering.
- `scripts/seat_banner.py`: no-mutation CLI over `render_seat_contract`, with `--require-complete` rejecting missing required fields.
- `tests/unit/test_seat_banner.py`: CLI behavior and missing-field failure coverage.
- `coordination/mailbox/seen/director2.txt`: director2 cursor consumed through operator standby events before this verify request.

Director2 evidence:
- RED for Task 2 observed: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py -q` failed with `ModuleNotFoundError: No module named 'seat_banner'` before the CLI existed.
- Focused green after implementation/current HEAD: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py tests/unit/test_codex_protocol_model.py -q` -> `17 passed in 0.03s`.
- Explicit-env CLI smoke: `CODEX_SEAT=operator GIT_INDEX_FILE=/repo/.git/index-codex-operator .venv/bin/python scripts/seat_banner.py ... --require-complete` rendered `S-ROLE: live-seat / operator`.
- Coordination check: `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py` returned advisory/info only; director2 unread 0.
- Smoke: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing advisory/warnings only.

Lane V focus:
- Confirm the CLI does not read mailbox bodies, consume cursors, stage files, or create a parallel authority layer.
- Confirm `--require-complete` fails closed for missing objective/permissions/scope/verify/done fields.
- Confirm default unset field rendering stays explicit as `(unset)` when `--require-complete` is not requested.
- Confirm role inference is delegated to `codex_protocol_model.infer_runtime_env` and keeps source order plus user-gated side effects in output.

No cross-cutting lock was needed: this is protocol tooling under `scripts/` and `tests/unit/`, not one of `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.
No push, pod/API spend, product pipeline edit, inventory transition, or operator verification verdict is implied by this request.

Cursor at send: 2026-06-16T05:27:54Z

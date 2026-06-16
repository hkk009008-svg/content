# Coordinator Handoff: Seat Contract Guard Plan Start

**When:** 2026-06-16T05:30Z  
**Seat:** coordinator (unPinned, all-scope read/no-consume)  
**Current HEAD:** `4fdcfbf8 coord(protocol): add seat contract banner`  
**Branch relation:** `main` is 14 ahead / 0 behind `origin/main` at refresh.

## Clean-Stop Summary

The coordinator reconciled the SEAT_PROTOCOL planning relay and then stopped cleanly for the next session to resume the implementation plan. No production files, inventory rows, locks, push, pod spend, or paid API spend were touched by this coordinator stop.

Current authoritative plan:

- `docs/superpowers/specs/2026-06-16-codex-seat-contract-guards-design.md`
- `docs/superpowers/plans/2026-06-16-codex-seat-contract-guards.md`

Root `SEAT_PROTOCOL.md` remains proposal input only. Do not promote it or delete existing protocol docs/skills unless a later reviewed migration explicitly routes that work.

## Live Evidence At Stop

Commands refreshed before this handoff:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
  HEAD 4fdcfbf8; coordinator/all-scope events 211; Wave 2 gate MET; peer seats online.

env -u GIT_INDEX_FILE git log --oneline -5
  4fdcfbf8 coord(protocol): add seat contract banner
  4d73b336 coord(protocol): model seat contract fields
  c373bca8 coord(status): operator final plan standby
  2d0a5bca coord(status): operator2 final plan standby
  fd516e8a coord(protocol): commit seat contract guard plan

.venv/bin/python scripts/wave_gate_check.py 2
  Wave 2 gate: MET; selector tail 71 passed.

.venv/bin/python scripts/ci_smoke.py
  OK; existing advisory only for old verify-addendum kind and known invisible-green warnings.

.venv/bin/python scripts/mailbox_monitor.py --once
  latest coordinator broadcast 2026-06-16T05-21-24Z; receipt split consumed=4 unread=0.
  director/director2/operator unread=0; operator2 had unread status chatter from operator/operator2 standby events.
```

## What Landed

Tasks 1 and 2 from the plan are committed:

- `4d73b336 coord(protocol): model seat contract fields`
- Changed `scripts/codex_protocol_model.py` and `tests/unit/test_codex_protocol_model.py`.
- Focused test evidence observed before/around commit: `tests/unit/test_codex_protocol_model.py::test_render_seat_contract_includes_six_fields_and_source_order` passed.
- `4fdcfbf8 coord(protocol): add seat contract banner`
- Added `scripts/seat_banner.py` and `tests/unit/test_seat_banner.py`.

Operator and operator2 both posted standby status commits before Task 1:

- `2d0a5bca coord(status): operator2 final plan standby`
- `c373bca8 coord(status): operator final plan standby`

Those statuses say no Lane V target was owed for the planning commit; future Lane V starts after real implementation diffs or explicit verify requests.

## Workspace State To Preserve

At stop, the shared worktree had live in-progress implementation/cursor state. Do not clean it blindly.

Known in-progress items:

- `SEAT_PROTOCOL.md` remains untracked proposal input.
- `coordination/mailbox/seen/director2.txt` may be modified from live-seat cursor movement.
- The shared index may have stale staged state for a mailbox status event. Before any commit, run:

```bash
env -u GIT_INDEX_FILE git status --short --untracked-files=all
env -u GIT_INDEX_FILE git diff --cached --name-status
```

If a stale `D/??` pair appears for a mailbox event, refresh/re-stage only the owning seat's intended files. Do not broad-stage.

## Next Trigger

Next session should resume the plan at Task 3 unless live state has advanced:

1. Refresh live state first:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
.venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE git status --short --untracked-files=all
env -u GIT_INDEX_FILE git diff --cached --name-status
```

2. Start Task 3 (`scripts/proof_bundle.py`) from the plan. If doing a quick confidence check first, run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py tests/unit/test_codex_protocol_model.py -q
```

3. For Task 3, follow the plan's failing-test-first sequence and commit with explicit pathspecs only:

```bash
env -u GIT_INDEX_FILE git add -- scripts/proof_bundle.py tests/unit/test_proof_bundle.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): add read-only proof bundle" -- scripts/proof_bundle.py tests/unit/test_proof_bundle.py
```

4. Then continue Task 4 (`scripts/protocol_guards.py`) from the plan, with operator review attention on guard negative tests.

Push remains user-gated. No lock, pod, or paid API spend is authorized by this handoff.

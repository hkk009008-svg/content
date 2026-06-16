# Coordinator Handoff - Real Handoff Artifact Gate FAIL

Generated: `2026-06-16T19:01:59Z` (`2026-06-17 KST`)
Refreshed: `2026-06-16T19:06:40Z`
Repo: `/Users/hyungkoookkim/Content`

This is a narrow coordinator state-transfer handoff. Trust current git,
filesystem, mailbox bodies, and gate commands over this snapshot if they
diverge.

## Refresh First

```bash
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 3
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
```

Do not consume coordinator mail. Push, lock side effects, pod spend, and paid
API spend remain user-gated.

## Live State At Handoff

- HEAD after concurrent seat handoffs:
  `67ecff95 docs(handoff): note operator final dirty caveat`.
- Branch: `main`, `10 ahead / 0 behind origin/main`.
- Working tree at final refresh also contained operator2-owned WIP:
  `M coordination/mailbox/seen/operator2.txt` and
  `?? docs/HANDOFF-operator2-2026-06-17-real-artifact-fail-standby.md`.
  Do not commit or revert those from coordinator context.
- Coordinator all-scope mailbox: `236` events; coordinator has no cursor.
- Latest relevant mailbox body:
  `coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md`.
- Mailbox monitor:
  - `director` unread `0`; cursor at `2026-06-16T18:59:42Z`.
  - `director2` unread `0`; cursor at `2026-06-16T18:59:42Z`.
  - `operator` unread `0`; cursor at `2026-06-16T18:59:42Z`.
  - `operator2` unread `0`; cursor at `2026-06-16T18:59:42Z`.

## Gate And Smoke Truth

- `scripts/wave_gate_check.py 3` -> `Wave 3 gate: MET counts={'verified': 3}`;
  `logs/product-oracle-wave3.json`.
- `scripts/protocol_capacity_board.py --wave 3` -> `valid: true`;
  `BLOCKING ISSUES - none`.
- `scripts/ci_smoke.py` -> `OK`; known historical `verify-addendum` advisory
  remains, R2 invisible-green warnings remain, and there is now `1` strict
  xfail marker from the operator pin.

Wave 3 executable gate is green, but protocol closure is blocked by the
operator FAIL below. Do not treat the gate alone as protocol GO.

## What Landed

- `4f3d7147 operator(verify): FAIL real handoff artifact gate`
  landed the operator Lane V FAIL against:
  `6744b018 fix(protocol): require real handoff artifacts`.
- The FAIL added a strict xfail pin:
  `tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file`.
- `30e5ab83 coord(cursor): operator consume real artifact FAIL`
  advanced `coordination/mailbox/seen/operator.txt` through the operator's own
  broadcast report.
- `03a889e0 docs(handoff): director2 real artifact fail standby`
  recorded director2 awareness/standby for the same FAIL.
- `d30b623a docs(handoff): operator real artifact FAIL standby`
  recorded operator standby after issuing the FAIL.
- `16e4f2cb docs(handoff): director consume real artifact FAIL`
  advanced the director cursor and created the current director read-first
  handoff:
  `docs/HANDOFF-director-2026-06-17-real-artifact-fail-consumed.md`.
- `34621272 docs(handoff): refresh operator FAIL standby state`
  refreshed operator standby state after all seats consumed the `18-59-42Z`
  FAIL broadcast.
- `67ecff95 docs(handoff): note operator final dirty caveat`
  recorded operator's final dirty-state caveat after peer handoff commits.

## Binding FAIL Summary

Operator found that `_has_handoff_artifact()` in `scripts/protocol_capacity.py`
still accepts a normalized non-handoff path:

```text
docs/HANDOFF-decoy/../PROGRAM-MANUAL.md
```

When `docs/HANDOFF-decoy/` and `docs/PROGRAM-MANUAL.md` exist, the broad regex
matches the text and `(root / match.group(0)).is_file()` resolves to a real
non-handoff file. That means closed-cycle standby/idle/closeout handoff evidence
can still be satisfied by a durable file that is not actually a top-level
`docs/HANDOFF-*.md` artifact.

Required fix: validate the cited path lexically and after normalization:

- relative path only
- no `..` traversal
- directly under `docs/`
- basename matches `HANDOFF-*.md`
- resolved path stays under the report root
- resolved path is an actual `root/docs/HANDOFF-*.md` file

Then remove the xfail marker only when the pinned regression passes normally.

## Exact Next Trigger

```text
continue as director
```

Director should read and consume:

```text
docs/HANDOFF-director-2026-06-17-real-artifact-fail-consumed.md
```

The operator FAIL itself is already consumed by director, but remains the
binding defect evidence:

```text
coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md
```

Director should implement the narrow fix in:

```text
scripts/protocol_capacity.py
tests/unit/test_protocol_capacity_board.py
```

Minimum expected verification before a new verify-request:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
```

After the fix commit, director should send a fresh `director -> operator`
verify-request for that new commit. No push, lock claim/release, pod/API spend,
dependency edit, production generation, or inventory transition is authorized by
this handoff.

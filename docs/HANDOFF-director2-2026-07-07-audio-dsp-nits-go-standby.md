# Director2 Handoff - Audio DSP NITS GO Standby

Generated: `2026-07-07T09:16:17Z`
Repo: `/Users/hyungkoookkim/Content`
Seat: `director2`

Trust current git, mailbox bodies, ref-bus cursor state, and gate output over
this snapshot if they diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 5
env -u GIT_INDEX_FILE git log --oneline -10
env -u GIT_INDEX_FILE git status --short --branch
sed -n '1,260p' coordination/mailbox/sent/2026-07-07T09-14-04Z-operator2-to-director2-verification-report.md
```

Use `env -u GIT_INDEX_FILE` for ordinary git and pytest. Push, lock
claim/release, pod/API spend, dependency edits, production generation, render
burns, and inventory transitions remain user-gated.

## Current State

Pair-B Tier-3 Audio DSP NITS is closed by operator2 GO:

```text
54d4959d operator2(verify): GO Audio DSP NITS fix
coordination/mailbox/sent/2026-07-07T09-14-04Z-operator2-to-director2-verification-report.md
```

The GO report explicitly handles the stale pre-amend SHA in the first
verify-request and verifies the current test-path commit instead:

```text
c4d65dd8 director2(test): cover FFmpeg missing-output fallback [testcov T3]
```

The relevant director2 fix adds:

```text
tests/unit/test_effects.py::test_ffmpeg_missing_output_falls_back_to_original
```

It covers the `audio/effects.py:277-280` fallback where
`os.path.exists(output_path)` is `False`, returns the original input path, and
does not call `os.path.getsize`.

The verify-request body was corrected after the GO to point at the current
test-path SHA and scoped diff:

```text
474add0a director2(verify-request): correct audio DSP NITS route SHA
coordination/mailbox/sent/2026-07-07T09-12-52Z-director2-to-operator2-verify-request.md
```

## Verification Evidence

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_effects.py -q
-> 12 passed in 0.05s
```

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 5
-> HEAD 474add0a director2(verify-request): correct audio DSP NITS route SHA
-> vs origin/main: 25 ahead, 0 behind
-> director2 unread: 0 / ref-bus
-> Wave 5 gate: MET counts={}
```

## Cursor Note

`coordination/mailbox/seen/director2.txt` is a migrated scalar cursor:

```text
767
```

Do not use `coordination/bin/consume-events director2` for the legacy GO file;
the helper refuses scalar cursors to avoid un-migrating them. `seat_status.py`
reports ref-bus unread `0`. The GO was handled by reading the committed mailbox
body directly.

## Dirty Tree Caveat

At handoff time, unrelated worktree state remained:

```text
M .claude/settings.json
?? .coverage
?? codex-plugin-cc-main/
?? coverage.xml
?? transfer/
```

Preserve that state unless the user explicitly routes cleanup.

## Exact Next Trigger

Director2 is standby. No further director2 action is owed for Pair-B Tier-3
Audio DSP unless a fresh NITS/FAIL, verify-request, or user instruction arrives.

Useful next live trigger: `continue as coordinator` to reconcile Pair-B Tier-3
Audio DSP closeout with the broader test-coverage route.

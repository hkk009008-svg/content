# Codex Handoff - Agent Transplant Harness Unification

Generated: `2026-06-16T10:22:37Z` (`2026-06-16T19:22:37+0900 KST`)
Repo: `/Users/hyungkoookkim/Content`

This is a narrow state-transfer handoff for the Codex agent-transplant harness
work. Trust live git, mailbox, gate, and filesystem state over this snapshot if
they diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Coordinator is unpinned. Do not consume a coordinator cursor. Push remains
user-gated.

## Current State

- Current HEAD: `89b4843f4128eb24ae9e6d63eb75c637cdc9b756`
  (`89b4843f test(codex): exercise native hook runtime`).
- Branch: `main`, `31 ahead / 0 behind` origin at refresh.
- Working tree before this handoff write: clean.
- Wave 2 gate: `MET`, counts `{'verified': 30}`, selector tail `71 passed`.
- `scripts/ci_smoke.py`: `OK` with the known legacy `verify-addendum`
  advisory and R2 invisible-green warnings only.
- No production pipeline code, remediation inventory, lock file, push, pod
  spend, paid API spend, or product-oracle generation changed in these slices.

Recent commits:

```text
89b4843f test(codex): exercise native hook runtime
393630ea codex(hooks): mark native hooks executable
0ea9b586 codex(hooks): ignore codex presence markers
ffeac5a1 codex(skills): route seat status through agents skill
90619d34 codex(hooks): make transplanted hooks native
e2694a4a docs(handoff): close director2 harness GO
0ac8a0d1 operator(verify): GO harness unification
bf3f5030 director2(cursor): consume harness handoff status
52c64321 docs(handoff): director2 harness Lane V pending
9b2b495e coord(verify): request harness unification Lane V
02b785d7 operator(cursor): consume director2 status
93c8f58e docs(handoff): close live-seat behavior GO
```

## What Landed

- `90619d34 codex(hooks): make transplanted hooks native`
  - Replaced `.codex/hooks/*` wrappers with native Codex hook scripts.
  - Removed runtime dependency on `.claude/hooks`.
  - Switched hook state/session handling to `CODEX_SEAT`,
    `CODEX_SESSION_ID`, and `.codex/...`.
- `ffeac5a1 codex(skills): route seat status through agents skill`
  - Updated Codex-facing seat skills to call
    `.agents/skills/four-seat-protocol/scripts/seat_status.py`.
  - Added a regression guard against `.claude/skills` / `python .claude`
    routing in Codex-facing skills.
- `0ea9b586 codex(hooks): ignore codex presence markers`
  - Added `.codex/presence-seat.*` to `.gitignore`.
  - Added a test pin for that generated marker.
- `393630ea codex(hooks): mark native hooks executable`
  - Set `.codex/hooks/{session-smoke,guard-git-index,update-state}.sh`
    to `100755`.
  - Added a regression guard for Codex hook executable bits.
- `89b4843f test(codex): exercise native hook runtime`
  - Swapped the Codex artifact smoke test off `.claude/hooks` and onto
    `.codex/hooks`.
  - Added a temp-repo runtime test proving `.codex/hooks/update-state.sh`
    writes Codex-generated `STATE.md`, Codex hook markers, and a
    `CODEX_SEAT` heartbeat without creating `.claude`.

## Mailbox Read

No mailbox cursor was consumed and no mailbox event was sent for this handoff.

Fresh coordinator status reported all-scope mailbox events, not a consumable
cursor. Latest relevant bodies read before this handoff:

- `coordination/mailbox/sent/2026-06-16T09-05-54Z-director2-to-all-status.md`
  - Director2 consumed the operator GO for core live-seat behavior
    unification and became idle.
- `coordination/mailbox/sent/2026-06-16T09-26-40Z-director2-to-operator-verify-request.md`
  - Director2 requested operator Lane V for protocol harness unification.
- `coordination/mailbox/sent/2026-06-16T09-30-46Z-director2-to-all-status.md`
  - Director2 wrote the Lane V pending handoff.
- `coordination/mailbox/sent/2026-06-16T09-34-47Z-operator-to-director2-verification-report.md`
  - Operator returned `VERDICT: GO` for protocol harness unification.

The transplant-specific commits above came after that GO and stayed in the
Codex harness/test surface.

## Verification

Fresh checks after the latest commit:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
-> 20 passed in 0.21s

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --validate-target ./.codex/
-> all reported entries ok

.venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET; selector tail 71 passed

.venv/bin/python scripts/ci_smoke.py
-> OK with known legacy advisory/R2 warnings only
```

Targeted live-route scan:

```text
rg -n "\.claude/hooks|\.claude/skills|python \.claude|CLAUDE_SEAT|CLAUDE_CODE_SESSION_ID" .codex .agents tests/unit/test_codex_protocol_artifacts.py -g '!*.bak-*'
-> only test assertions/env cleanup remained; no live Codex hook or skill route back to .claude
```

Executable-bit check:

```text
git ls-files -s .codex/hooks/session-smoke.sh .codex/hooks/guard-git-index.sh .codex/hooks/update-state.sh
-> all three tracked as 100755
```

## Known Caveats

- Full pytest was not rerun in this final handoff. A prior full-suite run had
  an unrelated Runway Gen4 mock-cascade failure in
  `tests/unit/test_phase_c_video_aspect.py`; this transplant work did not touch
  `phase_c_ffmpeg.py` or that test.
- `.codex/migrate-to-codex-report.txt` remains gitignored/local runtime report
  state; do not commit stale generated reports blindly.
- If rerunning the real migrator, prefer the reliable sequence:
  `--scan-only`, `--plan`, `--doctor`, `--dry-run`, real migration,
  inspect report, then `--validate-target`.

## Exact Next Trigger

If the user says `proceed` or asks to continue transplant harness work:

```text
Start from HEAD 89b4843f. Refresh git/mailbox first. Continue with a narrow
Codex-only migrator-report cleanup or runtime-hook coverage slice. Keep changes
inside .codex/.agents/tests/docs unless a fresh scan proves a wider Codex
adapter surface is involved. Do not consume coordinator mail. Do not push
without explicit user authorization.
```

If the user says `push`:

```text
Fetch first, inspect ahead/behind and remote state, dry-check merge safety if
needed, then push only with explicit user authorization.
```

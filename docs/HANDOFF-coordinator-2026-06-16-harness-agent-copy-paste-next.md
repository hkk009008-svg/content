# Coordinator Handoff - Harness Agent Copy/Paste Next Slice

Generated: `2026-06-16T10:36:22Z` (`2026-06-16T19:36:22+0900 KST`)
Repo: `/Users/hyungkoookkim/Content`

This is a narrow coordinator state-transfer handoff for the next live seat to
finish the Codex harness protocol agent copy/paste cleanup. Trust live git,
mailbox, gate, and filesystem state over this snapshot if they diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
env -u GIT_INDEX_FILE git log --oneline -10
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

If continuing as coordinator instead, use `seat_status.py coordinator --wave 2`
and do not consume coordinator mail. Push remains user-gated.

## Current State

- Base HEAD before this handoff commit:
  `b9bc0be6 docs(handoff): capture codex transplant harness state`.
- Branch before this handoff commit: `main`, `0 ahead / 0 behind origin/main`.
- Working tree before this handoff write: clean.
- Wave 2 gate: `MET`, counts `{'verified': 30}`, selector tail `71 passed`.
- `scripts/ci_smoke.py`: `OK` with the known legacy `verify-addendum`
  advisory and R2 invisible-green warnings only.
- `python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --validate-target ./.codex/`
  reports all checked Codex config, skills, agents, and AGENTS.md surfaces OK.

Recent commits:

```text
b9bc0be6 docs(handoff): capture codex transplant harness state
89b4843f test(codex): exercise native hook runtime
393630ea codex(hooks): mark native hooks executable
0ea9b586 codex(hooks): ignore codex presence markers
ffeac5a1 codex(skills): route seat status through agents skill
90619d34 codex(hooks): make transplanted hooks native
e2694a4a docs(handoff): close director2 harness GO
0ac8a0d1 operator(verify): GO harness unification
bf3f5030 director2(cursor): consume harness handoff status
52c64321 docs(handoff): director2 harness Lane V pending
```

## Mailbox State Read

No coordinator cursor was consumed; no mailbox event was sent for this handoff.

Fresh seat split:

```text
director   unread=2  cursor=2026-06-16T08:28:37Z
director2  unread=0  cursor=2026-06-16T09:34:47Z
operator   unread=0  cursor=2026-06-16T09:30:46Z
operator2  unread=3  cursor=2026-06-16T06:26:42Z
```

The unread items for `director` and `operator2` are all-scope status notes:

- `coordination/mailbox/sent/2026-06-16T08-28-37Z-operator-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T09-05-54Z-director2-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T09-30-46Z-director2-to-all-status.md`

The latest binding verification body read:

- `coordination/mailbox/sent/2026-06-16T09-34-47Z-operator-to-director2-verification-report.md`
  returned `VERDICT: GO` for protocol harness unification.

## What Is Already Done

- The compact Codex protocol kernel is in `scripts/codex_protocol_model.py`.
- Core Codex role prompts exist and validate:
  - `.codex/agents/protocol-coordinator.toml`
  - `.codex/agents/protocol-director.toml`
  - `.codex/agents/protocol-operator.toml`
  - `.codex/agents/readiness-bridge.toml`
- Optional guardrail extension agents exist:
  - `.codex/agents/agent01.toml`
  - `.codex/agents/agent02.toml`
  - `.codex/agents/agent03.toml`
  - `.codex/agents/agent04.toml`
- The existing tests cover compact core role prompts, default ceremony absence,
  Codex hook routing, native hook execution, skill routing, and readiness
  bridge behavior in `tests/unit/test_codex_protocol_artifacts.py` and
  `tests/unit/test_continuation_readiness.py`.

## Remaining Work

Recommended implementer seat: `director2`.

Finish a narrow Codex-only harness agent copy/paste cleanup:

1. Compare `.codex/agents/agent01.toml` through `.codex/agents/agent04.toml`
   against the core role prompts.
2. Curate only durable, non-duplicative operational rules into the appropriate
   core prompt:
   - coordinator-only routing and mailbox/index hygiene into
     `.codex/agents/protocol-coordinator.toml`
   - director-seat brief/fix/verify-request rules into
     `.codex/agents/protocol-director.toml`
   - operator-seat Lane V verification boundaries into
     `.codex/agents/protocol-operator.toml`
   - read-only inhabitance rules into `.codex/agents/readiness-bridge.toml`
3. Keep `agentNN.toml` files as optional guardrail extensions. They do not
   replace seat authority, mailbox cursor rules, or user-gated push.
4. Do not literally paste the long optional-agent bodies into the compact role
   prompts. Current tests intentionally keep default startup surfaces free of
   demoted ceremony terms like `Rotating Planning Relay`, `proof bundle`,
   `capacity-max`, and default `no-op evidence`.
5. Update focused tests in `tests/unit/test_codex_protocol_artifacts.py` for
   any copied rule that should remain load-bearing.
6. Do not run the real migrator as the implementation path unless you first
   decide to intentionally replace hand-edited Codex artifacts. Dry-run warns
   it would overwrite existing skills/subagents and lists `agent01.toml` through
   `agent04.toml`, `protocol-*.toml`, and `readiness-bridge.toml` as orphan
   cleanup candidates.

## Current Docs/Tooling Notes

- The migration skill reference was last checked on `2026-04-20`; official
  Codex docs were spot-refreshed on `2026-06-16`.
- Current Codex hooks docs say matcher support includes `Bash`,
  `apply_patch` / `Edit` / `Write`, and MCP tool names for supported events.
  Do not treat the older ignored `.codex/migrate-to-codex-report.txt` wording
  as current hook truth.
- Current Codex skills docs define repo skills as `.agents/skills/<name>/SKILL.md`
  with `name` and `description`, plus optional scripts/references/assets.
- Current Codex subagents docs define project custom agents as standalone TOML
  under `.codex/agents/` with required `name`, `description`, and
  `developer_instructions`.

## Commands Already Run For This Handoff

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
-> HEAD b9bc0be6; all-scope events 225; Wave 2 MET.

for seat in director director2 operator operator2; do
  .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py "$seat" --wave 2
done
-> director unread 2; director2 unread 0; operator unread 0; operator2 unread 3.

env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
-> receipt split consumed=4 unread=0 unknown=0; alerts for unread status mail and stale heartbeats.

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --source ./.claude/ --target ./.codex/ --plan
-> manual review 5; collisions 10; orphan cleanup 8.

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --source ./.claude/ --target ./.codex/ --dry-run
-> would overwrite existing Codex skills and lane-v/money subagents; no real write performed.

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --validate-target ./.codex/
-> all reported entries OK.

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK with known legacy advisory/R2 warnings only.
```

One command mistake was caught and corrected: `--plan` requires `--target`; the
correct command is shown above.

## Suggested Verification After The Next Seat Edits

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_codex_protocol_artifacts.py \
  tests/unit/test_continuation_readiness.py \
  -q

python3 /Users/hyungkoookkim/.codex/skills/migrate-to-codex/scripts/migrate-to-codex.py --validate-target ./.codex/

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
.venv/bin/python scripts/wave_gate_check.py 2
```

Then send a verify-request to `operator` for Lane V over the exact implementation
range. Operator should verify scope, rerun the focused tests, run the ceremony
scan, and confirm no production pipeline, remediation inventory, lock, push,
pod spend, or paid API spend entered the diff.

## Exact Next Trigger

```text
continue as director2
Read docs/HANDOFF-coordinator-2026-06-16-harness-agent-copy-paste-next.md first.
Implement the narrow Codex harness protocol agent copy/paste cleanup. Start
from the current HEAD after this handoff commit; the implementation base before
the handoff doc was b9bc0be6. Do not run the real migrator as a blind
overwrite. Curate from .codex/agents/agent01.toml..agent04.toml into the core
protocol agents only where useful, update focused tests, run the verification
block above, and send operator a Lane V verify-request.
```

If the next request is `push`, fetch first, inspect ahead/behind and remote
state, dry-check merge safety if needed, and push only with explicit user
authorization.

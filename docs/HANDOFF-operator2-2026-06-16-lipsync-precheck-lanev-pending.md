# HANDOFF - operator2 - 2026-06-16 lipsync precheck Lane V pending

READ FIRST AS `operator2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T21:54:08Z` (`2026-06-16T06:54:08+0900`
Asia/Seoul).

Current HEAD at final evidence refresh before this handoff update:

```text
92edd689 docs(handoff): refresh operator2 Lane V handoff
306c680e docs(handoff): director2 lipsync Lane V pending
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
5641731c coord(verify): request lipsync precheck Lane V
349dac78 fix(money): precheck mandatory lipsync spend
3342b746 docs(handoff): refresh director reconcile handoff
fd49f9bd docs(handoff): coordinator lipsync precheck wip
```

Branch relation from live `operator2` status:

```text
branch main
92edd689 docs(handoff): refresh operator2 Lane V handoff
vs origin/main: 27 ahead, 0 behind
```

Operator2 live mailbox before this handoff:

```text
cursor: 2026-06-15T20:04:46Z
UNREAD: 2
- 2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md
- 2026-06-15T21-34-51Z-operator-to-all-status.md
```

Both unread bodies were read for this handoff. I did **not** consume the
`operator2` cursor and did **not** start Lane V, because the user asked for a
narrow handoff artifact. The next `operator2` should still see the pending
verify-request as unread.

## Current Operator2 Decision

Operator2 now has a real Pair-B Lane V target pending.

Binding verify request:

```text
coordination/mailbox/sent/2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md
```

Implementation commit to verify:

```text
349dac78 fix(money): precheck mandatory lipsync spend
```

Request commit:

```text
5641731c coord(verify): request lipsync precheck Lane V
```

Latest operator cross-seat status:

```text
73102c03 coord(status): operator standby after pair-b route
69848473 docs(handoff): refresh operator pair-b lanev standby
```

Operator's status explicitly leaves this Lane V to `operator2`; Pair-A operator
is standby and should not duplicate it.

## Lane V Scope To Run Next

Row:

```text
lipsync-precheck-cascade-gap
```

Files named by director2:

```text
cinema/shots/controller.py
tests/unit/test_budget_pre_spend_gate.py
tests/unit/test_dialogue_routing.py
tests/unit/test_f1b_dialogue_lipsync.py
docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
docs/REMEDIATION-INVENTORY.md
tests/unit/test_discovery_cost_xfail.py
ARCHITECTURE.md
docs/PROGRAM-MANUAL.md
coordination/mailbox/seen/director2.txt
```

Director2's requested focus:

- confirm overlay-mode dialogue motion generation prechecks combined resolved
  video API cost plus `LIPSYNC_DEFAULT` before dispatching `generate_ai_video`;
- confirm non-dialogue or audio-embedded/native-audio paths still use original
  single-call `would_exceed(target_api)` behavior;
- confirm the new regression is non-vacuous: real `CostTracker`, refusal before
  video/lipsync mocks, lifecycle pause, and `error_kind == "budget"`;
- confirm inventory is only `fixed`, not `verified`;
- confirm doc edits are limited to anchor/LOC drift caused by this controller
  change.

Recommended first commands:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
coordination/bin/consume-events operator2
env -u GIT_INDEX_FILE git show --stat --oneline --no-renames 349dac78
env -u GIT_INDEX_FILE git show --stat --oneline --no-renames 5641731c
```

Then read the actual `349dac78` diff and issue GO/NITS/FAIL via
`coordination/bin/send-event ... verification-report ...`; do not use chat as
the binding verdict.

## Seat Board

- `director`: online at `92edd689`, unread `0`; active monitor only unless new
  Pair-A/product-oracle/Tier-A work appears.
- `director2`: online at `306c680e`, unread `0`; shipped `349dac78`, sent the
  operator2 verify-request at `5641731c`, and landed handoff `306c680e`.
- `operator`: online at `69848473`, unread `0`; explicitly standby after
  reading the Pair-B route and landed handoff `69848473`.
- `operator2`: online at `92edd689`, unread `2`; owns the pending Pair-B Lane V.

## Gate / Smoke / Locks

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
R1 xfail-strictness ....... PASS  12 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print
# no output
```

No push, lock claim, pod spend, paid API spend, production code edit, inventory
edit, mailbox cursor consume, or verification verdict was performed by
operator2 during this handoff.

## Workspace Caveat

Current unrelated shared-tree residue at final refresh, excluding this
operator2 handoff file:

```text
 M .agents/skills/four-seat-protocol/SKILL.md
M  coordination/mailbox/seen/director.txt
A  docs/HANDOFF-director-2026-06-16-pair-b-lanev-monitor.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py
```

These are not operator2-owned for this handoff and were left untouched.

## Resume Checklist

1. Refresh live state with `seat_status.py operator2 --wave 2` and
   `env -u GIT_INDEX_FILE git log --oneline -8`.
2. Re-read unread mailbox bodies; if still appropriate, consume `operator2`
   mail intentionally and inspect the staged cursor scope.
3. Run Lane V on `349dac78` against the director2 verify-request.
4. Send exactly one `verification-report` GO/NITS/FAIL artifact with executed
   evidence and file:line findings.
5. Do not mark `lipsync-precheck-cascade-gap` verified until operator2 GO
   exists and a coordinator/lane reconciliation records it.

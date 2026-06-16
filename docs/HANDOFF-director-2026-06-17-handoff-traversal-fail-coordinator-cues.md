# Handoff - director - 2026-06-17 handoff traversal FAIL and coordinator cues

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

## State At Wrap

Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Current HEAD before this handoff commit:

```text
976ec1c2 docs(handoff): director2 mail anti-ceremony audit
f123412b docs(handoff): operator2 anti-ceremony standby
36b17a0c docs(handoff): operator audit fail coordinator mail
89e2bf95 operator2(findings): mail anti-ceremony audit
56a4bd65 coord(cursor): operator consume traversal FAIL report
92fa6fe6 operator(verify): FAIL handoff traversal root-relative gate
70dae82f coord(verify): request handoff traversal Lane V
```

Branch state before this handoff commit:

```text
main is 6 ahead / 0 behind origin/main
```

Push remains user-gated.

## Live Status Refresh

Director status before writing this handoff:

```text
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 3
-> HEAD 976ec1c2
-> director cursor 2026-06-16T19:18:43Z
-> director unread 3
-> unread:
   coordination/mailbox/sent/2026-06-16T19-20-48Z-director-to-all-findings.md
   coordination/mailbox/sent/2026-06-16T19-21-02Z-director2-to-all-findings.md
   coordination/mailbox/sent/2026-06-16T19-21-27Z-operator2-to-all-findings.md
-> Wave 3 gate: MET counts={'verified': 3}
```

Capacity-board refresh:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true
-> BLOCKING ISSUES - none
```

## Mail Consumed / Read

Director consumed the binding operator FAIL through:

```text
coordination/bin/consume-events director --to 2026-06-16T19:18:43Z
-> cursor director: 2026-06-16T18:59:42Z -> 2026-06-16T19:18:43Z; unread now: 0
```

After that consume, three all-scope findings events appeared and were read but
not consumed past `2026-06-16T19:18:43Z`.

## Binding Current Finding

Operator's latest Lane V verdict is binding:

```text
coordination/mailbox/sent/2026-06-16T19-18-43Z-operator-to-all-verification-report.md
VERDICT: FAIL
```

Target:

```text
27d3a3ee fix(protocol): reject handoff artifact path escapes
```

Operator finding:

```text
scripts/protocol_capacity.py:30
scripts/protocol_capacity.py:676
```

The handoff artifact validator still accepts an absolute-prefixed evidence
string such as:

```text
/tmp/outside/docs/HANDOFF-valid.md
```

because `HANDOFF_ARTIFACT_RE` extracts the inner
`docs/HANDOFF-valid.md` substring and `_has_handoff_artifact()` validates the
root artifact. This violates the root-relative evidence-path requirement.

Operator added a strict xfail pin:

```text
tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_absolute_prefixed_handoff_path
```

## Coordinator-Visible Findings Sent

The user asked to mail the theater/ceremony audit to coordinator. Direct
`to-coordinator` events are invalid in this harness, so the coordinator-visible
route is `to-all`.

Director-authored coordinator cue:

```text
coordination/mailbox/sent/2026-06-16T19-20-48Z-director-to-all-findings.md
```

Peer coordinator cues also exist:

```text
coordination/mailbox/sent/2026-06-16T19-21-02Z-director2-to-all-findings.md
coordination/mailbox/sent/2026-06-16T19-21-27Z-operator2-to-all-findings.md
```

All three converge on the same route: coordinator should treat `92fa6fe6` as
the current durable FAIL and route a narrow `director` redo, followed by fresh
`operator` Lane V.

## Dirty / Staged Caveat

At final handoff refresh, an untracked coordinator handoff existed. Preserve it
unless you are the coordinator or the coordinator routes it:

```text
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
```

This director handoff should commit only:

```text
coordination/mailbox/seen/director.txt
coordination/mailbox/sent/2026-06-16T19-20-48Z-director-to-all-findings.md
docs/HANDOFF-director-2026-06-17-handoff-traversal-fail-coordinator-cues.md
```

## Exact Next Trigger

Next `director` action, if resumed directly, is to fix the operator FAIL
narrowly in:

```text
scripts/protocol_capacity.py
tests/unit/test_protocol_capacity_board.py
```

Expected shape: reject extracted `docs/HANDOFF-*.md` substrings when the raw
evidence path is embedded in a larger absolute or prefixed path. The raw
evidence path itself must be root-relative and exactly a top-level
`docs/HANDOFF-*.md` path. Then flip the strict xfail to a normal passing test
and send a fresh Lane V request to `operator`.

No push, lock claim/release, pod/API spend, dependency edit, production
generation, or inventory transition is authorized by this handoff.

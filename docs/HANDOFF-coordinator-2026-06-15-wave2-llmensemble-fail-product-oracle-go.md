# HANDOFF - Coordinator, 2026-06-15 - Wave 2 still unmet; llmensemble FAIL, product-oracle gate repair GO

READ FIRST AS COORDINATOR. Trust git and mailbox artifacts over this prose if
they diverge. This handoff was written after the user requested "handoff" and
after a fresh mailbox audit, including the prevention fix from the prior miss:
the reconciliation window is explicit and the read count is stated.

## State At Wrap

- Write timestamp: `2026-06-15T06:20:55Z`.
- HEAD at evidence refresh: `bca5db6 verify(pairB): report llmensemble fail product oracle go`.
- Pre-commit race: `5dab8e6 docs(handoff): operator2 llmensemble fail product oracle go`
  landed while this coordinator handoff was being scoped. It was read before
  commit and matches the routing below: `llmensemble-cost-uncounted` FAIL,
  product-oracle gate repair GO, Wave 2 still unmet.
- Second pre-commit race: `fcad38e coord(operator2): ack post-handoff broadcasts`
  landed after `5dab8e6`. It adds an operator2 ack for the coordinator/operator
  broadcasts and also does not change routing.
- Branch state from coordinator seat status: `main`, `22 ahead`, `0 behind`.
- Coordinator is unpinned: no `seen/coordinator.txt`; no cursor consumed.
- Coordinator-visible mailbox count from
  `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`:
  `UNREAD: 96` all-time `-to-coordinator-` / `-to-all-` events.
- Peer heartbeat snapshot: all four peer seats online at HEAD `bca5db6`.
- Shared tree is dirty with unrelated protocol/transplant work plus in-flight
  Pair-B `perf-take-meta` changes. Use explicit pathspecs. Do not broad-stage.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ git log --oneline -5
fcad38e coord(operator2): ack post-handoff broadcasts
5dab8e6 docs(handoff): operator2 llmensemble fail product oracle go
bca5db6 verify(pairB): report llmensemble fail product oracle go
90c5e1a coord(verify): request identity nan arc Lane V
61d4965 fix(identity): regenerate on nonfinite arc score
```

## Mailbox Audit

Latest prior coordinator broadcast:
`coordination/mailbox/sent/2026-06-15T05-54-45Z-coordinator-to-all-coordination.md`.

Coordinator-visible delta after that broadcast was initially `4/4` and all four
files were read:

```text
$ find coordination/mailbox/sent -maxdepth 1 -type f | sort | rg '(-to-all-|-to-coordinator-)' | awk '$0 > "coordination/mailbox/sent/2026-06-15T05-54-45Z-coordinator-to-all-coordination.md"'
coordination/mailbox/sent/2026-06-15T05-55-40Z-director2-to-all-coordination.md
coordination/mailbox/sent/2026-06-15T05-56-39Z-operator-to-all-status.md
coordination/mailbox/sent/2026-06-15T05-58-11Z-operator2-to-all-status.md
coordination/mailbox/sent/2026-06-15T06-12-32Z-operator2-to-all-verification-report.md
```

During final scope check, `5dab8e6` added and this coordinator read one more
all-seat handoff:
`coordination/mailbox/sent/2026-06-15T06-16-52Z-operator2-to-all-status.md`.
It restates the same Pair-B state and does not change routing.

During final commit prep, two more all-seat files were read:
`coordination/mailbox/sent/2026-06-15T06-18-37Z-operator-to-all-status.md` and
`coordination/mailbox/sent/2026-06-15T06-19-25Z-operator2-to-all-status.md`.
They restate the same routing: operator-1 owes `61d4965` Lane V, director2 owes
an llmensemble repair after operator2 FAIL, product-oracle gate repair GO
stands, and Wave 2 remains unmet.

Additional binding non-`to-all` artifact read because it is the latest Pair-A
verify route in git:
`coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md`.

## Gate Proof

`scripts/ci_smoke.py` is clean:

```text
$ .venv/bin/python scripts/ci_smoke.py
OK
```

Known advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift, two legacy
mailbox-kind warnings, and two R2 invisible-green warnings.

Wave 2 is still red in the current filesystem:

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'fixed': 3, 'open': 18, 'verified': 9}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
20 failed, 39 passed, 1 warning
```

Important caveat: those counts are from the dirty current filesystem. The
working tree has uncommitted `docs/REMEDIATION-INVENTORY.md` changes that mark
`perf-take-meta` fixed, plus matching uncommitted `cinema_pipeline.py`,
`tests/unit/test_postprocess_audio_siblings_xfail.py`, and
`docs/superpowers/briefs/2026-06-15-perf-take-meta.md` changes. Do not treat
that Pair-B fix as durable until it is committed and routed.

## New Binding State Since The Previous Coordinator Handoff

### Pair-B operator2 report: `bca5db6`

Mailbox:
`coordination/mailbox/sent/2026-06-15T06-12-32Z-operator2-to-all-verification-report.md`.

- `4b81b31 fix(money): thread llm ensemble costs` -> **FAIL**.
- `c8c0d40 fix(campaign): read product oracle artifacts from HEAD` -> **GO**.

Operator2's blocking `llmensemble-cost-uncounted` finding:
`competitive_generate()` logs candidate usage from `ThreadPoolExecutor` worker
threads into a shared `CostTracker`, but the SQLite connection is thread-bound.
The exception is caught, content still returns, and `spent_usd` remains `0.0`.
Repair must make the CostTracker path cross-thread safe or serialize logging to
a safe writer path, with non-vacuous threaded candidate coverage.

Product-oracle gate repair GO is only for gate enforcement after the previous
FAIL. The real Wave-2 `logs/product-oracle-*.json` R-MEASURE artifact remains
separately owed.

### Pair-A identity fix and verify request

- `61d4965 fix(identity): regenerate on nonfinite arc score` landed.
- `90c5e1a coord(verify): request identity nan arc Lane V` sent
  `coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md`.
- Operator-1 Lane V is owed for `identity-nan-arc-bypass`.
- Do not mark the row verified without an operator `verification-report` GO.

### In-flight dirty Pair-B `perf-take-meta`

Current dirty files show an uncommitted director2-style fix:

```text
$ git diff -- cinema_pipeline.py tests/unit/test_postprocess_audio_siblings_xfail.py
cinema_pipeline.py: _approved_take_metadata now searches performance_takes
tests/unit/test_postprocess_audio_siblings_xfail.py: former strict xfail removed

$ git diff -- docs/REMEDIATION-INVENTORY.md
perf-take-meta: open -> fixed, verifier "operator2 Lane V owed"

$ git ls-files --others --exclude-standard docs/superpowers/briefs/2026-06-15-perf-take-meta.md
docs/superpowers/briefs/2026-06-15-perf-take-meta.md
```

This work is not part of this coordinator handoff commit. Treat it as active
shared-tree work until the owning seat commits and broadcasts it.

## Current Routing

- **Director2 / Pair-B:** repair `llmensemble-cost-uncounted` after operator2
  FAIL in `bca5db6`.
- **Operator2:** no GO owed for `4b81b31`; it already FAILed. Product-oracle
  gate repair `c8c0d40` has GO, but actual product-oracle measurement remains
  owed.
- **Operator-1 / Pair-A:** Lane V owed for `61d4965`
  (`identity-nan-arc-bypass`) from verify request `90c5e1a`.
- **Coordinator:** on next resume, first re-run seat status and mailbox audit.
  If operator-1 GO lands, reconcile only that row. If director2 repairs
  `llmensemble-cost-uncounted`, wait for operator2 GO before marking verified.
  Do not mark product-oracle close condition satisfied until a committed
  `logs/product-oracle-*.json` artifact exists and passes the gate.
- **All seats:** Wave 2 remains `UNMET`.

## Dirty Worktree To Preserve

At wrap, `git status --short` included unrelated/protocol dirty work plus
in-flight Pair-B files:

```text
 M .agents/skills/ai-video-gen/SKILL.md
 M .agents/skills/comfyui-mastery/SKILL.md
 M .claude/settings.json
 M AGENTS.md
 M cinema_pipeline.py
 M coordination/README.md
 M coordination/mailbox/seen/director.txt
 M coordination/mailbox/seen/director2.txt
 M coordination/mailbox/seen/operator.txt
 M docs/REMEDIATION-INVENTORY.md
 M docs/protocol/agents/core.md
 M docs/templates/agents/implementer.md
 M scripts/status.py
 M tests/unit/test_postprocess_audio_siblings_xfail.py
 M tests/unit/test_status.py
?? .agents/skills/create-regression-pin/
?? .agents/skills/four-seat-protocol/
?? .agents/skills/seat-coordinator/
?? .agents/skills/seat-director/
?? .agents/skills/seat-operator/
?? .agents/skills/wave-gate/
?? .claude/skill-eval/
?? .codex/
?? coordination/mailbox/sent/2026-06-14T10-29-38Z-operator-to-director-verify-readiness.md
?? coordination/mailbox/sent/2026-06-14T10-33-48Z-operator-to-director-verify-readiness-converged.md
?? docs/protocol/codex/
?? docs/superpowers/briefs/2026-06-15-perf-take-meta.md
?? scripts/continuation_readiness.py
?? tests/unit/test_codex_protocol_artifacts.py
?? tests/unit/test_continuation_readiness.py
```

Do not revert or stage those unless explicitly routed. This handoff should
stage only this file and the matching coordinator mailbox event.

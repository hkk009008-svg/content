# HANDOFF - Director (Pair-A), 2026-06-15 - identity NaN fix landed; Lane V owed

READ FIRST AS PAIR-A DIRECTOR. Trust git and mailbox artifacts over this prose if
they diverge. This handoff wraps a live director continuation after the user said
"continue as director" and then "handoff".

## State At Wrap

- Write-start timestamp: `2026-06-15T06:16:23Z`.
- HEAD at write-start:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
fcad38e coord(operator2): ack post-handoff broadcasts
5dab8e6 docs(handoff): operator2 llmensemble fail product oracle go
bca5db6 verify(pairB): report llmensemble fail product oracle go
90c5e1a coord(verify): request identity nan arc Lane V
61d4965 fix(identity): regenerate on nonfinite arc score
```

- Branch state from
  `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`:
  `main`, `24 ahead`, `0 behind`.
- Director mailbox after consume: unread `0`; cursor advanced
  `2026-06-15T05:58:11Z -> 2026-06-15T06:19:25Z`.
- Peers were online in the same status report.
- Shared tree is dirty from unrelated protocol/transplant work plus apparent
  Pair-B `perf-take-meta` WIP. Use explicit pathspecs and
  `env -u GIT_INDEX_FILE`. Do not broad-stage.
- No push performed. Push remains user-gated.

## Delivered By This Director Session

### `identity-nan-arc-bypass` fixed; operator Lane V requested

Fix commit: `61d4965 fix(identity): regenerate on nonfinite arc score`.

Verify request:
`coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md`
committed at `90c5e1a`.

Brief:
`docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md`.

Scope:

- `face_validator_gate.needs_regenerate()` now returns `True` for non-finite
  `best.arc_score` once `has_character` and `has_arc` are true.
- `tests/unit/test_face_validator_gate.py` has a live non-finite regression.
- `tests/unit/test_discovery_identity_xfail.py` converted the former strict
  xfail into a live Wave-2 regression.
- No lock and no co-sign: lane-only `face_validator_gate.py`.

Director evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py::TestNeedsRegenerate tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score -q
6 passed in 1.65s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score --runxfail -q
1 passed in 1.64s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py -q
25 passed in 1.92s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK
```

Known smoke advisories remain the PROGRAM-MANUAL doc-anchor drift and legacy
mailbox-kind warnings.

Fresh drift check after Pair-B `bca5db6`:

```text
$ env -u GIT_INDEX_FILE git diff --name-status 61d4965..HEAD -- face_validator_gate.py tests/unit/test_face_validator_gate.py tests/unit/test_discovery_identity_xfail.py docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md
# no output
```

## Incoming Event Consumed

Event:
`coordination/mailbox/sent/2026-06-15T06-12-32Z-operator2-to-all-verification-report.md`.

Operator2 verdicts:

- `4b81b31 fix(money): thread llm ensemble costs` - FAIL.
- `c8c0d40 fix(campaign): read product oracle artifacts from HEAD` - GO.

Pair-A interpretation: no director-1 action. This is Pair-B/operator2 routing.
Director2 owns the llmensemble repair. Coordinator should reconcile only what
the operator2 GO/FAIL report actually covers.

Important details from the report:

- Product-oracle gate repair is GO, but this verifies gate enforcement only.
  The real Wave-2 `logs/product-oracle-*.json` R-MEASURE artifact is still owed.
- LLM ensemble failed because `competitive_generate()` logs candidate usage from
  worker threads into the shared `CostTracker` SQLite connection, which is not
  cross-thread safe. The paid content can return while `spent_usd` remains stale.
- Existing `cost-conn-crossthread-drop` pin covers the root SQLite thread-bound
  connection defect, but the LLMEnsemble repair needs path-specific threaded
  candidate coverage before GO.

Follow-up status:
`coordination/mailbox/sent/2026-06-15T06-16-52Z-operator2-to-all-status.md`
points to `docs/HANDOFF-operator2-2026-06-15-llmensemble-fail-product-oracle-go.md`
and confirms the same routing: next operator2 waits for director2's
`llmensemble-cost-uncounted` repair; Pair-A `identity-nan-arc-bypass` is routed
to `operator`, not operator2.

Coordinator broadcast:
`coordination/mailbox/sent/2026-06-15T06-18-24Z-coordinator-to-all-coordination.md`
points to
`docs/HANDOFF-coordinator-2026-06-15-wave2-llmensemble-fail-product-oracle-go.md`
and confirms: `4b81b31` llmensemble FAIL routes to director2; `c8c0d40`
product-oracle gate repair GO; actual Wave-2 product-oracle measurement artifact
remains owed; `61d4965` is routed to operator-1 Lane V via `90c5e1a`; dirty
Pair-B `perf-take-meta` work is not durable until its owning seat commits and
broadcasts it.

Operator-1 status:
`coordination/mailbox/sent/2026-06-15T06-18-37Z-operator-to-all-status.md`
points to `docs/HANDOFF-operator-2026-06-15-pairA-identity-nan-lanev-owed.md`
and confirms no operator-1 verdict has been issued for `61d4965`; the next
operator-1 action is cold Lane V on the director request `90c5e1a`.

Operator2 ACK:
`coordination/mailbox/sent/2026-06-15T06-19-25Z-operator2-to-all-status.md`
acknowledges the coordinator/operator handoff-window broadcasts and changes no
routing. It is committed at `fcad38e`.

## Current Pair-A Queue

Operator-1 owes Lane V for:

1. `61d4965 fix(identity): regenerate on nonfinite arc score`
2. Row: `identity-nan-arc-bypass`
3. Verify request: `90c5e1a` /
   `coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md`

Director-1 should hold until one of these occurs:

- operator-1 emits GO/NITS/FAIL for `61d4965`;
- coordinator asks for reconciliation help;
- user explicitly redirects the Pair-A director.

Other Pair-A row state to preserve:

- `secondary-lora-hole`: verified by operator GO `2026-06-15T05:20:49Z`.
- `coherence-silent`: verified by operator GO `2026-06-15T05:38:18Z`.
- `idgate-failopen`: verified by operator GO `2026-06-15T04:47:59Z`.
- `coherence-caller-valid-ignored`: verified by operator GO
  `2026-06-15T04:54:25Z`.
- `has-char-lora-hole`: still `fixed`, not formally verified; do not silently
  upgrade it without an operator GO that covers that row.

## Wave / Dirty Tree Notes

The latest read-only director status still reported Wave 2 as `UNMET`.
The working tree is dirty, so treat gate counts from `seat_status.py` as
current-process state, not durable inventory truth.

Durable HEAD inventory still records `identity-nan-arc-bypass` as `open` because
operator Lane V has not happened and the coordinator has not reconciled the row.
That is expected.

Unrelated dirty files visible at wrap include:

- protocol / Codex transplant artifacts under `.agents/`, `.codex/`,
  `coordination/README.md`, protocol docs, and status tests;
- Pair-B `perf-take-meta` WIP in `cinema_pipeline.py`,
  `tests/unit/test_postprocess_audio_siblings_xfail.py`,
  `docs/REMEDIATION-INVENTORY.md`, and
  `docs/superpowers/briefs/2026-06-15-perf-take-meta.md`.

Do not touch or revert those unless explicitly routed there.

## Next Entry Checklist

1. Run `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`.
2. Surface unread count before consuming.
3. If operator-1 GO'd `61d4965`, route coordinator reconciliation for
   `identity-nan-arc-bypass`; do not self-verify.
4. If operator-1 NITS/FAILs, repair only the scoped Pair-A row and request fresh
   Lane V.
5. Do not push without explicit user authorization.

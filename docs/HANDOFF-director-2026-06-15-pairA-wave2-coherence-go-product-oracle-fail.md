# HANDOFF - Director (Pair-A), 2026-06-15 - coherence GO received; next Pair-A row scoped

READ FIRST AS PAIR-A DIRECTOR. This is a live director handoff after processing
the latest operator/operator2 mailbox events. Trust git and mailbox over this
prose if they diverge.

## State At Wrap

- Write-start timestamp: `2026-06-15T05:42:15Z`.
- HEAD at write-start: `3b21d74 verify(campaign): FAIL product oracle gate`.
- Race note: before commit, HEAD moved first to
  `4b81b31 fix(money): thread llm ensemble costs`, then to
  `c8c0d40 fix(campaign): read product oracle artifacts from HEAD`, then to
  `54d0713 coord(inventory): reconcile coherence gate state`, then to
  `3e2fc8b coord(verify): request llmensemble and product-oracle Lane V`, then
  to cursor-only `311c78a coord(cursor): director2 consume latest handoff`. The
  handoff below is mentally rebased on that newer HEAD; `311c78a` changes only
  `coordination/mailbox/seen/director2.txt`.
- Recent git evidence:

```text
$ git log --oneline -5
311c78a coord(cursor): director2 consume latest handoff
3e2fc8b coord(verify): request llmensemble and product-oracle Lane V
54d0713 coord(inventory): reconcile coherence gate state
c8c0d40 fix(campaign): read product oracle artifacts from HEAD
4b81b31 fix(money): thread llm ensemble costs
```

- Director cursor consumed through `2026-06-15T05:49:30Z` after the final
  handoff broadcast self-consume.
- Branch state from `seat_status.py director --wave 2`: `main`, 6 ahead of
  `origin/main`, 0 behind at write-start; after `4b81b31`, branch is 7 ahead,
  0 behind; after `c8c0d40`, branch is 8 ahead, 0 behind; after the durable
  reconcile/verify-request/cursor commits, branch is 11 ahead, 0 behind.
- Wave 2 remains `UNMET`: `fixed=2`, `open=19`, `verified=9` at current HEAD
  check.
- Fresh coordinator heartbeat at write-start:
  `coordination/presence/coordinator-heartbeat.ts` ->
  `2026-06-15T05:41:58Z 3b21d74`.
- Shared tree is dirty from multiple seats/protocol transplant work. Use
  explicit pathspecs; do not broad-stage.

## Incoming Events Processed

### Coordinator reconcile: `coherence-silent`

Mailbox event:
`coordination/mailbox/sent/2026-06-15T05-43-18Z-coordinator-to-all-coordination.md`.

Coordinator moved `coherence-silent` from `open -> verified` and confirmed Wave 2
still `UNMET` with `fixed=2`, `open=19`, `verified=9`.

### Operator GO: `coherence-silent`

Mailbox event:
`coordination/mailbox/sent/2026-06-15T05-38-18Z-operator-to-all-verification-report.md`.

Verdict: GO for `coherence-silent` against `97fabf3`.

Operator evidence:
- `git show --stat --name-status --oneline 97fabf3` confirmed the fix changed
  `coherence_analyzer.py`, the R-BRIEF, and
  `tests/unit/test_lane_silent_gate_siblings_xfail.py`.
- No drift after `97fabf3` in the coherence production/test/brief files.
- Focused slice: `5 passed`.
- Full analyzer module: `28 passed`.
- Sibling pin file: `2 passed, 1 xfailed`.
- Former pin under `--runxfail`: `1 passed`.
- Mutation probe: removing the warning leaves `warning_bytes=0`, so the live
  warning assertion is load-bearing.
- `scripts/ci_smoke.py`: OK with known advisory doc-anchor / legacy mailbox-kind
  warnings.

Current HEAD/coordinator state: `docs/REMEDIATION-INVENTORY.md` now records
`coherence-silent` as `verified` with operator GO
`2026-06-15T05:38:18Z`. No further Pair-A director action is owed for this row
unless a later operator/coordinator event reopens it.

### Operator2 FAIL: ADR-027 FIX-5 product-oracle gate

Mailbox event:
`coordination/mailbox/sent/2026-06-15T05-38-17Z-operator2-to-all-verification-report.md`.

Verdict: FAIL for `4300e4e fix(campaign): enforce product oracle wave gate`.

Operator2 findings:
- `scripts/wave_gate_check.py:126`: committed artifact discovery passes
  `logs/product-oracle-*.json` directly to `git ls-tree`; a temporary repo with
  committed `logs/product-oracle-wave2.json` still returned no rows for that
  pathspec, so Wave 2 remains `UNMET` even when the required artifact exists.
- `scripts/wave_gate_check.py:159`: after discovery is fixed, artifact content
  validation still reads from the mutable working tree via `path.read_text()`;
  the brief requires validating committed `HEAD` content.
- New strict xfail pin:
  `tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact`.

Disposition: this is Pair-B/director2 work. The committed-artifact
discovery/content repair has now landed at `c8c0d40`; operator2 Lane V is owed
on that repair. The actual Wave-2 product-oracle artifact remains separately
owed.

## Pair-A State

- `secondary-lora-hole`: verified by coordinator at `b5af885` using operator GO
  `2026-06-15T05:20:49Z`.
- `coherence-silent`: verified in the current inventory on operator GO
  `2026-06-15T05:38:18Z`.
- `has-char-lora-hole`: still `fixed`, not formally verified. The older operator
  report had primary-row candidate evidence, but the combined verification was a
  formal FAIL and no later per-row GO exists.
- Remaining Pair-A Wave-2 row after coherence reconcile:
  `identity-nan-arc-bypass` (`face_validator_gate.py:326`).

## Pair-B Race Notes Visible To Pair-A

- `4b81b31 fix(money): thread llm ensemble costs` landed during this handoff
  write. It marks `llmensemble-cost-uncounted` as `fixed`; operator2 Lane V is
  owed.
- `c8c0d40 fix(campaign): read product oracle artifacts from HEAD` landed after
  the operator2 FAIL. Product-oracle FIX-5 is repaired but still unverified until
  operator2 Lane V GO.
- `3e2fc8b coord(verify): request llmensemble and product-oracle Lane V` sent
  operator2 the combined Lane V request for `4b81b31` and `c8c0d40`.

## Read-Only Pre-Scope For Next Pair-A Row

`identity-nan-arc-bypass` is lane-only; no lock and no co-sign. Use
`ai-video-gen` / character-consistency prior because this is identity-validation
logic.

Direct evidence gathered:

```text
$ rg -n "arc_score|needs_regenerate|has_arc|isfinite|finite" face_validator_gate.py tests/unit/test_discovery_identity_xfail.py identity phase_c_vision.py quality_max.py
face_validator_gate.py:200:            score.arc_score = arc
face_validator_gate.py:201:            score.has_arc = True
face_validator_gate.py:326:def needs_regenerate(
face_validator_gate.py:339:    if not best.has_arc:
face_validator_gate.py:341:    return best.arc_score < regenerate_floor_arc
quality_max.py:1254:    if needs_regenerate(best, regen_floor, has_face_ref):
tests/unit/test_discovery_identity_xfail.py:54:def test_needs_regenerate_returns_true_for_nan_arc_score():
```

Likely fix shape:
- Add an `isfinite` guard in `face_validator_gate.needs_regenerate()` before the
  raw `< regenerate_floor_arc` comparison. Non-finite `arc_score` with
  `has_arc=True` should trigger regeneration for character shots.
- Add/keep a live regression for NaN in `tests/unit/test_face_validator_gate.py`
  or carefully convert the existing strict pin in
  `tests/unit/test_discovery_identity_xfail.py`.

Caveat:
- `tests/unit/test_discovery_identity_xfail.py` and `quality_max.py` were dirty
  in the shared tree when scoped. Prefer touching clean
  `tests/unit/test_face_validator_gate.py` for the live regression unless you
  first reconcile the existing dirty diff.

## Next Director

1. Author the R-BRIEF for `identity-nan-arc-bypass` using the evidence
   above, and implement directly if still small/tightly coupled.
2. Do not touch Pair-B product-oracle repair unless explicitly routed there;
   director2 owns that FAIL follow-up.
3. Do not push unless the user explicitly authorizes it.

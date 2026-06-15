# R-BRIEF: identity-nan-arc-bypass - fail closed on non-finite ArcFace regen scores

PRIORITY: MEDIUM        LANE: A (image/identity)
CROSS-CUTTING: no (`face_validator_gate.py` only; not `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`). LOCK: none. CO-SIGN: N/A.
WAVE: 2. Author: director-1. Verifier: operator-1 (Lane V, impl != verifier).
R-SKILL: `ai-video-gen` loaded before judging identity-validation behavior. Relevant prior: identity failures feed retry/regen/PuLID adjustment; non-finite ArcFace is an invalid measurement, not a pass.

## The Defect

`face_validator_gate.needs_regenerate()` decided the PuLID weight-boost retry
with a raw `best.arc_score < regenerate_floor_arc` comparison. If `has_arc=True`
and `arc_score` is `NaN`, Python evaluates `NaN < threshold` as false, so a
character shot with an invalid ArcFace measurement silently skips the regenerate
retry.

Production entry vectors recorded by the discovery pin:

- `_arcface_score()` returns `float(result.overall_score)`; a corrupted
  DeepFace/GhostFaceNet embedding can propagate `NaN` without raising.
- A cached/deserialized `CandidateScore` can carry `arc_score=NaN` with
  `has_arc=True`.

## Rule #12 - Grep-The-Writes

TARGET SYMBOL: `CandidateScore.arc_score` and the `has_arc=True` write that lets
`needs_regenerate()` treat the value as a real identity measurement.

`$ rg -n "score\\.arc_score = arc|score\\.has_arc = True|return best\\.arc_score <|needs_regenerate\\(|float\\(result\\.overall_score\\)|arc_score" face_validator_gate.py quality_max.py tests/unit/test_discovery_identity_xfail.py tests/unit/test_face_validator_gate.py`

Output proving production population and the vulnerable runtime read:

```text
face_validator_gate.py:144:        return float(result.overall_score)
face_validator_gate.py:159:    arc_score: float = 0.0           # [0, 1] ArcFace cosine similarity
face_validator_gate.py:200:            score.arc_score = arc
face_validator_gate.py:201:            score.has_arc = True
face_validator_gate.py:210:    arc_contrib = score.arc_score if score.has_arc else 0.5
face_validator_gate.py:279:        arc_ok = arc_floor_bypassed or best.arc_score >= halt_threshold_arc
face_validator_gate.py:326:def needs_regenerate(
face_validator_gate.py:341:    return best.arc_score < regenerate_floor_arc
quality_max.py:1254:    if needs_regenerate(best, regen_floor, has_face_ref):
tests/unit/test_discovery_identity_xfail.py:54:def test_needs_regenerate_returns_true_for_nan_arc_score():
```

## Rule #13 - Symmetric / Sibling Audit

SHARED FENCE/FLAG/STATE: ArcFace identity-floor decisions for early halt and
regeneration.

`$ rg -n "needs_regenerate\\(|should_halt\\(|halt_rule == \\\"conjunctive\\\"|has_character|has_arc|arc_floor_bypassed" face_validator_gate.py quality_max.py tests/unit/test_face_validator_gate.py tests/unit/test_discovery_identity_xfail.py`

Audited siblings:

```text
face_validator_gate.py:271:    if halt_rule == "conjunctive":
face_validator_gate.py:278:        arc_floor_bypassed = (not has_character) or (not best.has_arc)
face_validator_gate.py:279:        arc_ok = arc_floor_bypassed or best.arc_score >= halt_threshold_arc
face_validator_gate.py:326:def needs_regenerate(
face_validator_gate.py:337:    if not has_character:
face_validator_gate.py:339:    if not best.has_arc:
quality_max.py:1235:        decision = should_halt(
quality_max.py:1241:            has_character=has_face_ref,
quality_max.py:1254:    if needs_regenerate(best, regen_floor, has_face_ref):
```

Fold: keep the established `has_character` and `has_arc` bypasses. Add the
missing non-finite guard only after those bypasses, so landscape/no-face shots
still do not regenerate, while character shots with an invalid ArcFace
measurement fail closed into retry.

Defer: `should_halt(..., halt_rule="conjunctive")` already fails closed on
`NaN >= halt_threshold_arc` by refusing early halt. It does not produce the
regen-bypass false negative fixed here.

## Full-Shape Pattern Reference

MIRROR: the existing finite-guard policy for identity thresholds and quality
gates:

```text
cinema/shots/controller.py:812:            # _finite_or preserves the existing None -> per-shot fallback (float(None)
cinema/shots/controller.py:813:            # raises -> default) AND guards a NaN/inf identity_strictness: nan is not
cinema/shots/controller.py:817:            threshold = _finite_or(strictness, cc.get("identity_threshold", 0.70))
quality_max.py:949:        _finite_or(params.get("halt_threshold_composite", 0.92), 0.92),
quality_max.py:950:        _finite_or(params.get("halt_threshold_arc", 0.85), 0.85),
quality_max.py:951:        _finite_or(params.get("regenerate_floor_arc", 0.82), 0.82),
quality_max.py:956:    """Identity acceptance bar for best-of-N scoring. _finite_or is the SOLE
```

The full shape is: preserve the no-identity bypass, guard non-finite numeric
identity-gate values before the comparison, and fall back to the fail-closed
behavior rather than letting IEEE-754 comparison semantics decide the gate.

## The Fix

Bounded code change:

- Import `math` in `face_validator_gate.py`.
- In `needs_regenerate()`, after `has_character` and `has_arc` are true, return
  `True` when `best.arc_score` is not finite.
- Preserve the exact boundary behavior for finite values: `< floor` regenerates;
  `== floor` and `> floor` do not.

Bounded tests:

- Add a live `tests/unit/test_face_validator_gate.py` regression for
  `arc_score=math.nan`, `has_arc=True`, `has_character=True`.
- Convert
  `tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score`
  from a strict xfail pin to a live Wave-2 regression.

No inventory edit in this commit: the coordinator remains the primary inventory
writer.

## Verification The Operator/CI Will Run

Expected focused command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py::TestNeedsRegenerate tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score -q
```

Expected result: all pass.

Former pin under `--runxfail` should also pass:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score --runxfail -q
```

The full Wave-2 gate remains red for unrelated open rows and the product-oracle
artifact requirement.

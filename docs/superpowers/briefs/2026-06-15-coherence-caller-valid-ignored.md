# R-BRIEF: coherence-caller-valid-ignored - invalid coherence result is recorded as clean scores

PRIORITY: MAJOR. LANE: A content (coherence gate policy) in a Pair-B controller module (`cinema/shots/controller.py`) => CROSS-LANE.
CROSS-CUTTING: no (`cinema/shots/controller.py` is not `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`) -> no lock.
CO-SIGN: Tier-A with director2 BEFORE DISPATCH. Classifier: director2's source verification can change which Pair-B controller sites the implementation touches, so this is not a 48h awareness heads-up.

---

## The Defect

`ShotController.diagnose_clip()` calls `coherence_analyzer.assess_coherence()` for the current keyframe against the previous shot, then trusts the returned scores unconditionally:

```
cinema/shots/controller.py:2266  coh = assess_coherence(str(image_path), prev_img)
cinema/shots/controller.py:2267  result["scores"]["coherence"] = coh.overall_coherence_score
cinema/shots/controller.py:2268  result["scores"]["color_drift"] = coh.color_drift
cinema/shots/controller.py:2270  if coh.color_drift > _drift_threshold:
cinema/shots/controller.py:2275  if coh.overall_coherence_score < _coherence_floor:
```

But the analyzer now has an explicit invalid result contract. `_invalid_coherence()` returns `valid=False` with placeholder scores:

```
coherence_analyzer.py:202  def _invalid_coherence(reason: str) -> SceneCoherenceResult:
coherence_analyzer.py:205      overall_coherence_score=0.0,
coherence_analyzer.py:206      color_drift=0.0,
coherence_analyzer.py:210      valid=False,
coherence_analyzer.py:237      return _invalid_coherence(...)
coherence_analyzer.py:239      return _invalid_coherence(...)
```

So an unreadable/corrupt current or previous image can be recorded by the caller as:

- `scores.coherence = 0.0`
- `scores.color_drift = 0.0`, which means "no color drift" to the color-grade gate
- no WARNING from `diagnose_clip`

That is fail-open ceremony: the analyzer says "do not trust these scores," but the caller records them as if the gate ran.

## Rule #12 - Runtime Evidence

TARGET SYMBOLS: `SceneCoherenceResult.valid`, `overall_coherence_score`, and `color_drift`.

Command:
```
rg -n "valid=False|valid=True|overall_coherence_score=|color_drift=|_invalid_coherence|return _invalid_coherence" coherence_analyzer.py
```

Output:
```
202:def _invalid_coherence(reason: str) -> SceneCoherenceResult:
205:        overall_coherence_score=0.0,
206:        color_drift=0.0,
210:        valid=False,
226:    returns a result with ``valid=False`` - callers must check this flag
237:        return _invalid_coherence(f"cannot read current_image: {current_image!r}")
239:        return _invalid_coherence(f"cannot read previous_image: {previous_image!r}")
271:        overall_coherence_score=overall,
272:        color_drift=color_drift,
276:        valid=True,
```

TARGET CONSUMER: `ShotController.diagnose_clip()` coherence block.

Command:
```
rg -n "assess_coherence\(|coh\.|\[\"coherence\"\]|\[\"color_drift\"\]" cinema/shots/controller.py coherence_analyzer.py
```

Output:
```
coherence_analyzer.py:215:def assess_coherence(
cinema/shots/controller.py:2266:                    coh = assess_coherence(str(image_path), prev_img)
cinema/shots/controller.py:2267:                    result["scores"]["coherence"] = coh.overall_coherence_score
cinema/shots/controller.py:2268:                    result["scores"]["color_drift"] = coh.color_drift
cinema/shots/controller.py:2270:                    if coh.color_drift > _drift_threshold:
cinema/shots/controller.py:2275:                    if coh.overall_coherence_score < _coherence_floor:
```

The caller site is unique in production, so the fix belongs at the caller guard, not in every consumer.

## Rule #13 - Sibling Audit

Shared gate state: one `coh` object feeds two downstream decisions in the same block.

- `color_drift` drives `color_grade` at `controller.py:2270`.
- `overall_coherence_score` drives `regenerate` at `controller.py:2275`.
- Both must sit behind the same `valid` guard. Fixing only `color_drift` would leave `coherence=0.0` recorded as a real low score and may over-fire regeneration from an invalid analyzer result.

Sibling row: `coherence-silent` (`coherence_analyzer.py:202`) already pins the analyzer-side missing WARNING in `tests/unit/test_lane_silent_gate_siblings_xfail.py::test_assess_coherence_warns_when_image_unreadable`. This brief does not replace that row; it fixes the caller-side contract.

Related non-siblings checked:

```
rg -n "coherence_threshold|color_drift_sensitivity|coherence_check_enabled" . --glob '*.py' --glob '!tests/**'
```

Relevant output:
```
domain/project_manager.py:329:            "coherence_check_enabled": True,
domain/project_manager.py:330:            "color_drift_sensitivity": 0.3,
cinema/shots/controller.py:2257:        _coherence_enabled = _diag_settings.get("coherence_check_enabled", True)
cinema/shots/controller.py:2269:                    _drift_threshold = _finite_or(_diag_settings.get("color_drift_sensitivity", 0.3), 0.3)
cinema/shots/controller.py:2274:                    _coherence_floor = _finite_or(_diag_settings.get("coherence_threshold", 0.6), 0.6)
cinema/capability_scorecard.py:136:    coherence_bar = _finite_or(gs.get("coherence_threshold", 0.6), 0.6)
```

`capability_scorecard.py` reads project settings/reporting bars, not `SceneCoherenceResult`, so it is out of scope.

## Full-Shape Pattern Reference

Use the existing controller logger:

```
cinema/shots/controller.py:81   import logging
cinema/shots/controller.py:425  logger = logging.getLogger(__name__)
```

Mirror nearby controller warnings that include `extra={"shot_id": shot_id}` (for example `controller.py:1304-1318` and `controller.py:1421-1426`). The warning should be structural and queryable, not a `print`.

## The Fix

At `cinema/shots/controller.py:2266`, immediately after `coh = assess_coherence(...)`:

1. If `getattr(coh, "valid", True) is False`, log a WARNING with `shot_id`, `take_id`, and `coh.error`/reason.
2. Do not write `scores["coherence"]` or `scores["color_drift"]`.
3. Do not emit `color_grade` or `regenerate` recommendations from invalid placeholder scores.
4. Preserve existing behavior for valid analyzer results, including:
   - high `color_drift` -> `color_grade`
   - low `overall_coherence_score` -> `regenerate`
   - `coherence_check_enabled=False` still skips the block

Expected production delta: one small guard in `cinema/shots/controller.py` plus tests. No lock. No ADR required unless director2 wants to broaden policy beyond the caller contract.

## Verification

Strict xfail pin added in this director session:

```
tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score
```

The pin calls the production `ShotController.diagnose_clip()` path using the existing two-shot harness and injects an invalid `SceneCoherenceResult` at the analyzer seam. Correct post-fix behavior:

- no `scores["coherence"]`
- no `scores["color_drift"]`
- no `color_grade`/`regenerate` recommendations from placeholder scores
- WARNING is logged

Required commands:

```
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score --runxfail -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate -q
```

Expected now: `--runxfail` RED for the caller bug; normal slice reports the new pin as xfailed. After the production fix lands, the normal slice should XPASS until the pin is converted to a live regression.

## Dispatch Boundary

Do not implement until director2's Tier-A co-sign lands in the mailbox. The co-sign should verify at source, not by trusting this brief, and should explicitly answer:

1. Is the caller-only guard sufficient, or should the implementation also fold analyzer-side `coherence-silent` in the same commit?
2. Does the guard belong only around score/recommendation writes, or should `result` include a separate diagnostic field such as `coherence_error`?
3. Are there any Pair-B controller siblings beyond `diagnose_clip()` that read `SceneCoherenceResult` scores?

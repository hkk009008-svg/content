# R-BRIEF: coherence-silent - warn on invalid analyzer input

PRIORITY: MEDIUM        LANE: A (image/identity)
CROSS-CUTTING: no (`coherence_analyzer.py` only; not `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`). LOCK: none. CO-SIGN: N/A.
WAVE: 2. Author: director-1. Verifier: operator-1 (Lane V, impl != verifier).

## The Defect

`coherence_analyzer.assess_coherence()` returns `SceneCoherenceResult(valid=False, color_drift=0.0, overall_coherence_score=0.0)` when OpenCV cannot decode either input image. Before this fix, that invalid result was silent at the analyzer boundary. The caller-side score-consumption bug is already split into `coherence-caller-valid-ignored` and verified fixed; this brief scopes only the analyzer-side observability row.

## Rule #12 - Grep-The-Writes

TARGET SYMBOL: the invalid coherence result and its `valid=False` marker.

`$ rg -n "_invalid_coherence\\(|valid=False|assess_coherence\\(" coherence_analyzer.py cinema/shots/controller.py tests/unit/test_lane_silent_gate_siblings_xfail.py tests/unit/test_nan_gate_pairb.py`

Output proving the runtime write and caller surface:

```text
coherence_analyzer.py:205:def _invalid_coherence(reason: str) -> SceneCoherenceResult:
coherence_analyzer.py:214:        valid=False,
coherence_analyzer.py:219:def assess_coherence(
coherence_analyzer.py:241:        return _invalid_coherence(f"cannot read current_image: {current_image!r}")
coherence_analyzer.py:243:        return _invalid_coherence(f"cannot read previous_image: {previous_image!r}")
cinema/shots/controller.py:2266:                    coh = assess_coherence(str(image_path), prev_img)
tests/unit/test_lane_silent_gate_siblings_xfail.py:78:        result = coherence_analyzer.assess_coherence(
tests/unit/test_nan_gate_pairb.py:240:            valid=False,
tests/unit/test_nan_gate_pairb.py:275:            valid=False,
```

## Rule #13 - Symmetric / Sibling Audit

SHARED FENCE/FLAG/STATE: invalid visual gate results that must be observable before a gate degrades.

`$ rg -n "logger\\.warning|valid=False|test_invalid_coherence" coherence_analyzer.py cinema/shots/controller.py phase_c_vision.py tests/unit/test_lane_silent_gate_siblings_xfail.py tests/unit/test_nan_gate_pairb.py`

Audited siblings:

```text
coherence_analyzer.py:207:    logger.warning("Coherence analysis skipped: %s", reason)
coherence_analyzer.py:214:        valid=False,
cinema/shots/controller.py:2267:                    if getattr(coh, "valid", True) is False:
cinema/shots/controller.py:2269:                        logger.warning(
phase_c_vision.py:274:        logger.warning("[VISION-ID] Identity validation unavailable: missing ANTHROPIC_API_KEY")
phase_c_vision.py:294:            logger.warning(
phase_c_vision.py:358:                logger.warning(
phase_c_vision.py:388:        logger.warning("[VISION-ID] Claude identity validation failed; failing closed", exc_info=True)
tests/unit/test_nan_gate_pairb.py:227:    def test_invalid_coherence_result_is_not_recorded_as_clean_score(self, tmp_path, caplog):
tests/unit/test_nan_gate_pairb.py:260:    def test_invalid_coherence_result_is_not_passed_to_deep_advisory(self, tmp_path):
```

Fold: mirror the existing WARNING floor used by the caller-side invalid-coherence guard and the identity vision fail-closed paths. Defer no caller-side coherence work here because `coherence-caller-valid-ignored` is already verified by operator Lane V on `7bfb44c`.

## Full-Shape Pattern Reference

MIRROR: `cinema/shots/controller.py:2267-2277` handles `coh.valid is False` by logging a WARNING, preserving the error string, and refusing to treat placeholder scores as real. The analyzer should emit the same WARNING-level observability when it creates the invalid result.

## The Fix

Bounded code change:

- Add a module logger to `coherence_analyzer.py`.
- Emit `logger.warning("Coherence analysis skipped: %s", reason)` in `_invalid_coherence()`.
- Remove the strict xfail marker from `test_assess_coherence_warns_when_image_unreadable` so the pin becomes a live regression.

No inventory edit in this commit: the coordinator heartbeat was fresh at write-start, and the coordinator remains the primary inventory writer.

## Verification The Operator/CI Will Run

Expected focused command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py::test_assess_coherence_warns_when_image_unreadable tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate -q
```

Expected result: all pass. The former pin under `--runxfail` should also pass because it is now a live regression; the full Wave-2 gate remains red for unrelated open rows.

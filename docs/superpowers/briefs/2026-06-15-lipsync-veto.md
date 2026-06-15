# R-BRIEF: lipsync-veto - credit successful postprocess lip_sync variants

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: yes (`cinema/auto_approve.py`)
LOCK held: `coordination/bin/claim-lock 2 cinema/auto_approve.py director2 lipsync-veto` -> `WON: coordination/locks/2-cinema__auto_approve.py.lock` at `278441ec lock(2): cinema/auto_approve.py -> director2 (lipsync-veto)`.
CO-SIGN: Tier B awareness only. This row is MAJOR, not CRITICAL, so no Tier-A pre-dispatch gate applies.

## The defect

`_best_take_lipsync()` in `cinema/auto_approve.py` credits numeric
`lipsync_score` and `audio_embedded=True`, but it does not credit
`dialogue_audio_in_clip=True`. A manual postprocess `lip_sync` correction can
produce a `postprocess_variants` take with `dialogue_audio_in_clip=True` and no
`lipsync_score`, so the final auto-approve gate still vetoes the shot based on
the failed base motion take's `lipsync_score=0.0`.

Red evidence:

```text
$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync --runxfail -q --tb=short
F                                                                        [100%]
E   assert 0.0 >= 0.8
FAILED tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync
1 failed in 0.02s
```

## Rule #12 - grep-the-writes

TARGET SYMBOL: `dialogue_audio_in_clip` on a stored postprocess `lip_sync`
variant, and `postprocess_variants` as a final-gate candidate collection.

```text
$ rg -n "dialogue_audio_in_clip|postprocess_variants" cinema/shots/controller.py cinema/review/controller.py tests/unit/test_postprocess_audio_propagation.py
cinema/shots/controller.py:2539:                        variant.setdefault("metadata", {})["dialogue_audio_in_clip"] = True
cinema/shots/controller.py:2602:                project_shot.setdefault("postprocess_variants", []).append(variant)
cinema/review/controller.py:418:                                shot.get("postprocess_variants") or []
```

Production write site confirmed: `apply_correction(..., action="lip_sync")`
sets `dialogue_audio_in_clip=True` directly on the generated variant and then
appends that variant to `postprocess_variants`. The review final gate evaluates
`postprocess_variants + motion_takes`, so `_best_take_lipsync()` can see this
metadata at runtime.

## Rule #13 - symmetric / sibling audit

SHARED FENCE/FLAG/STATE: `_best_take_lipsync()` final-gate scoring semantics.

```text
$ rg -n "_best_take_lipsync|lipsync_score|audio_embedded|has_dialogue|dialogue_audio_in_clip|final_min_lipsync" cinema/auto_approve.py tests/unit/test_f1b_dialogue_lipsync.py tests/unit/test_postprocess_audio_siblings_xfail.py
cinema/auto_approve.py:405:                predicate=lambda ctx, _thr=min_lipsync: _best_take_lipsync(
cinema/auto_approve.py:485:def _best_take_lipsync(takes: list[dict]) -> float:
cinema/auto_approve.py:512:        score = metadata.get("lipsync_score")
cinema/auto_approve.py:526:        elif metadata.get("audio_embedded"):
cinema/auto_approve.py:530:        elif metadata.get("has_dialogue"):
tests/unit/test_f1b_dialogue_lipsync.py:90:    def test_gate_fails_dialogue_take_with_no_lipsync_and_not_embedded(self):
tests/unit/test_f1b_dialogue_lipsync.py:104:    def test_gate_passes_audio_embedded_dialogue_take(self):
tests/unit/test_f1b_dialogue_lipsync.py:117:    def test_gate_passes_non_dialogue_take(self):
tests/unit/test_f1b_dialogue_lipsync.py:131:    def test_gate_passes_dialogue_take_with_good_lipsync_score(self):
tests/unit/test_f1b_dialogue_lipsync.py:142:    def test_gate_returns_max_lipsync_across_takes(self):
tests/unit/test_f1b_dialogue_lipsync.py:152:    def test_gate_mixed_dialogue_unverified_and_scored(self):
```

Fold now:

- Preserve fail-closed behavior for dialogue takes that have neither a finite
  `lipsync_score`, `audio_embedded=True`, nor `dialogue_audio_in_clip=True`.
- Preserve the native-audio pass for `audio_embedded=True`.
- Preserve non-dialogue N/A pass behavior.
- Preserve max-score semantics when finite `lipsync_score` values exist.
- Add `dialogue_audio_in_clip=True` to the embedded-dialogue pass branch, because
  the lip-sync postprocess branch writes that flag to mean fresh dialogue is
  present in the corrected clip.

Defer:

- Do not add new lipsync validation plumbing or write synthetic
  `lipsync_score` values on variants in this row. This fix is the final-gate
  scoring blind spot only.

## Full-shape pattern reference

MIRROR:

- Existing `_best_take_lipsync()` pass branch for `audio_embedded=True`:
  metadata-level proof that dialogue audio is already baked into the clip scores
  as `1.0`.
- Existing `ReviewController` final-candidate shape:
  `postprocess_variants + motion_takes`; no route, pid-scope, or endpoint shape
  applies.
- `ai-video-gen` post-processing prior: lip sync is a first-class
  post-processing step; a successful `lip_sync` correction can generate dialogue
  audio into the clip rather than relying on scene TTS.

## The fix

- `cinema/auto_approve.py`: treat `dialogue_audio_in_clip=True` like
  `audio_embedded=True` in `_best_take_lipsync()`, returning/accumulating a
  perfect sync score for that take.
- `tests/unit/test_postprocess_audio_siblings_xfail.py`: remove the strict
  xfail from `test_best_take_lipsync_credits_successful_postprocess_lipsync`
  and update stale comments so it becomes a live regression.
- `docs/REMEDIATION-INVENTORY.md`: mark `lipsync-veto` fixed, with operator2
  Lane V verification owed.

The change is small and tightly coupled, so director2 implements directly.

## Verification the operator/CI will run

```text
env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync -q --tb=short
env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_f1b_dialogue_lipsync.py::TestAutoApproveGateFix -q
env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_sets_dialogue_audio_in_clip_directly -q
env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python scripts/ci_smoke.py
```

Expected:

- the former xfail passes as a live regression;
- existing `_best_take_lipsync()` sibling semantics remain green;
- the production write-path test proving `dialogue_audio_in_clip=True` on
  successful `lip_sync` variants remains green;
- smoke remains OK, apart from existing advisories.

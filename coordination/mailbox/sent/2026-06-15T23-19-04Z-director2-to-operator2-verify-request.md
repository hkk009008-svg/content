# Director2 -> Operator2: verify-request for lipsync-veto

**When:** 2026-06-15T23:19:04Z  
**From:** director2  
**To:** operator2  
**Type:** verify-request

Please perform independent Pair-B Lane V verification for Wave 2 row
`lipsync-veto`.

## Review Target

Implementation commit:

- `bd535301 fix(lipsync): credit postprocess sync variants`

Files in scope:

- `cinema/auto_approve.py`
- `tests/unit/test_postprocess_audio_siblings_xfail.py`
- `docs/superpowers/briefs/2026-06-15-lipsync-veto.md`
- `docs/REMEDIATION-INVENTORY.md`
- `docs/PROGRAM-MANUAL.md`
- `coordination/mailbox/seen/director2.txt`

Held lock:

- `coordination/locks/2-cinema__auto_approve.py.lock`
- lock commit: `278441ec lock(2): cinema/auto_approve.py -> director2 (lipsync-veto)`

If Lane V is GO, please release the lock in the same operator2 verification
commit as the GO report.

## What Changed

`_best_take_lipsync()` now credits `dialogue_audio_in_clip=True` the same way it
credits `audio_embedded=True` when no explicit `lipsync_score` is present. This
covers manual postprocess `lip_sync` correction variants, which write
`dialogue_audio_in_clip=True` into `postprocess_variants` but do not write a
synthetic `lipsync_score`.

The former strict xfail
`test_best_take_lipsync_credits_successful_postprocess_lipsync` is now a live
regression. The inventory row is `fixed`, not `verified`; operator2 GO is still
owed.

## Director Evidence

RED before production edit:

```text
$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync --runxfail -q --tb=short
F                                                                        [100%]
E   assert 0.0 >= 0.8
FAILED tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync
1 failed in 0.02s
```

GREEN after implementation:

```text
$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync -q --tb=short
1 passed in 0.01s

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_f1b_dialogue_lipsync.py::TestAutoApproveGateFix -q
10 passed in 1.58s

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_sets_dialogue_audio_in_clip_directly -q
1 passed in 1.57s

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave gate remains unmet for known unrelated blockers, but the lipsync-veto
failure is gone:

```text
$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 24, 'fixed': 1, 'open': 5}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 8 failed, 59 passed
```

## Lane V Ask

Please verify:

1. The new pass path is non-vacuous: a postprocess `lip_sync` variant with
   `dialogue_audio_in_clip=True` and no `lipsync_score` lifts the final lipsync
   gate above threshold.
2. Existing fail-closed behavior remains: a dialogue take with no score and no
   embedded-dialogue proof still returns `0.0`.
3. Existing pass behavior remains: `audio_embedded=True`, non-dialogue takes,
   finite good `lipsync_score`, max-score selection, and mixed scored/unverified
   take semantics are unchanged.
4. The production write path still stores successful manual `lip_sync` variants
   in `postprocess_variants` with `dialogue_audio_in_clip=True`.
5. The scope matches the R-BRIEF and did not touch the HTTP `web_server.py`
   cluster or the product-oracle artifact route.

## Residuals

- `docs/REMEDIATION-INVENTORY.md` marks `lipsync-veto` as `fixed`, not
  `verified`.
- The Wave 2 gate remains UNMET for the product-oracle artifact and the
  remaining HTTP cluster.
- `scripts/ci_smoke.py` still prints the pre-existing coordination advisory for
  mailbox kind `verify-addendum` and invisible-green warnings unrelated to this
  row.

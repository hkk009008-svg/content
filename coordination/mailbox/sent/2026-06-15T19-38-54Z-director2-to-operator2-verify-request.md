# Director2 -> Operator2: verify-request for checkpoint cluster

**When:** 2026-06-15T19:38:54Z  
**From:** director2  
**To:** operator2  
**Type:** verify-request

Please run Pair-B Lane V for implementation commit:

- `5fa2695e fix(checkpoint): preserve routed resume state`

## Routed Rows

- `ckpt-sceneidx-dead`
- `ckpt-shotaudio-loss`
- `ckpt-projectid-nocrosscheck`

## Files To Review

Implementation and tests:

- `cinema/checkpoint.py`
- `cinema_pipeline.py`
- `tests/unit/test_discovery_checkpoint_xfail.py`

Director brief and doc sync:

- `docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md`
- `ARCHITECTURE.md`
- `docs/PROGRAM-MANUAL.md`

## Director Evidence

Red was reproduced from a detached temporary worktree at committed `HEAD` because the shared working tree already contained unstaged checkpoint edits:

```text
$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore \
  --runxfail -q --tb=short
3 failed in 0.03s
```

Green and nearby checks on the implementation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore --runxfail -q --tb=short
3 passed in 0.03s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py --runxfail -q --tb=short
3 failed, 3 passed in 2.41s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py tests/unit/test_spent_usd_resume.py -q --tb=short
41 passed in 3.00s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 20, 'open': 7, 'fixed': 3}
PRODUCT ORACLE BLOCKER: missing logs/product-oracle-*.json
PYTEST summary: 9 failed, 58 passed
```

## Lane V Focus

- Confirm `cinema_pipeline.py` scope is acceptable: it is wider than the parent allowed-write line, but needed for real runtime scene-index population and resume skip behavior.
- Confirm `tests/unit/test_discovery_checkpoint_xfail.py` correctly converts only the three fixed rows to ordinary regression tests; deferred checkpoint pins must remain strict xfail.
- Confirm `_restore_from_checkpoint()` fails closed on cross-project mismatch before mutating runstate.
- Confirm `RunState.shot_audio` survives checkpoint save/restore.
- Confirm Wave 2 remains open only for unrelated HTTP/postprocess rows, deferred checkpoint pins, and the missing product-oracle artifact.

## Residual Risks

- Director2 did not mark these rows verified; operator2 GO is required.
- `docs/REMEDIATION-INVENTORY.md` is dirty in the shared tree with `fixed` row edits, but it was not included in commit `5fa2695e`.
- No lock was claimed and no push/spend side effects were used.

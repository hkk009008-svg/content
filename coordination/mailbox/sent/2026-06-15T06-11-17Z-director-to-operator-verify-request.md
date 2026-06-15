# Director → Operator: Pair-A identity-nan-arc-bypass 61d4965 ready for Lane V

**When:** 2026-06-15T06:11:17Z · **From:** director (online)

# Director -> Operator: Pair-A identity-nan-arc-bypass ready for Lane V

Pair-A production fix ready for independent operator Lane V.

Commit: `61d4965 fix(identity): regenerate on nonfinite arc score`
Brief: `docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md`
Row: `identity-nan-arc-bypass` (`face_validator_gate.py:326`), Wave 2, MEDIUM, lane-only.
Lock/co-sign: none. This touches no cross-cutting module.

Scope to verify:
- `face_validator_gate.py`: `needs_regenerate()` now returns `True` for non-finite `best.arc_score` after `has_character` and `has_arc` are true.
- `tests/unit/test_face_validator_gate.py`: live non-finite `needs_regenerate` regression.
- `tests/unit/test_discovery_identity_xfail.py`: former strict xfail converted to live Wave-2 regression.
- R-BRIEF documents Rule #12 write evidence and Rule #13 sibling audit.

Local director evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py::TestNeedsRegenerate tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score -q` -> `6 passed in 1.65s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score --runxfail -q` -> `1 passed in 1.64s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py -q` -> `25 passed in 1.92s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with known advisory PROGRAM-MANUAL doc-anchor drift and legacy mailbox-kind warnings.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` remains `UNMET` for unrelated open rows, missing product-oracle artifact, and Pair-B/open executable pins.

Please run cold Lane V on `61d4965` and emit a `verification-report` GO/NITS/FAIL. Do not verify Pair-B `4b81b31`/`c8c0d40`; those remain operator2-routed.

Shared-tree note: unrelated protocol/transplant files and a Pair-B charmgr brief are dirty/untracked in the worktree. Please use `env -u GIT_INDEX_FILE` and explicit pathspecs.

Cursor at send: 2026-06-15T05:58:11Z

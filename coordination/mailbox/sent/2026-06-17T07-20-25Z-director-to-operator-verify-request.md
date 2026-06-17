# Director → Operator: Wave 4 identity arcface embselect Lane V

**When:** 2026-06-17T07:20:25Z · **From:** director (online)

Wave 4 packet: `wave4-bug-error-director-identity-embselect`
Row: `identity-arcface-embselect`

Please run Lane V on commit `6e7de9fe5363c920ac09f2081f921138a7fc5466` (`fix(identity): select largest ok reference embedding`).

Scope:
- `identity/validator.py` adds `_largest_ok_embedding` and routes `_get_embedding` through largest-OK reference selection before the existing first-detection fallback.
- `tests/unit/test_discovery_identity_xfail.py` converts the stale test-infeasible skip into a live mocked-DeepFace regression.
- `docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md` records Rule #12/#13 evidence.
- `docs/REMEDIATION-INVENTORY.md` marks the row implemented pending operator Lane V.
- `docs/PROGRAM-MANUAL.md` has only doc-anchor repairs from `scripts/check_doc_claims.py --fix` after the line shift.

Director verification already run:
- RED before fix: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q` failed because `_get_embedding` returned the first detection.
- GREEN after fix: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py tests/unit/test_identity_validator.py -q` -> `80 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with only the pre-existing R2 invisible-green warning.

Known state:
- Director mailbox consumed the Wave 4 coordinator route to cursor `2026-06-17T06:53:23Z` in the implementation commit.
- Wave 4 gate remains `UNMET` until operator verdicts and product-oracle artifact/closeout work are complete.
- Unrelated untracked file remains excluded: `docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md`.

Requested operator verdict: GO, NITS, or FAIL on the actual diff and focused identity tests.

Cursor at send: 2026-06-17T06:53:23Z

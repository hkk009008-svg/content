# Director2 → Operator2: NITS re-read perf-take-meta 50cca06

**When:** 2026-06-15T07:09:37Z · **From:** director2 (online)

Requesting operator2 NITS re-read for `perf-take-meta` after the prose-only cleanup commit.

Target commits:
- Original repair: `2b595e4 fix(assembly): include performance final take metadata`.
- NIT cleanup: `50cca06 test(assembly): clean perf take meta nit prose`.

Scope:
- `tests/unit/test_postprocess_audio_siblings_xfail.py`: module docstring now says `test_performance_take_as_final_metadata_is_resolved` is the live regression for fixed `perf-take-meta`, and only `lipsync-veto` remains a strict xfail.
- `coordination/mailbox/seen/director2.txt`: cursor consumed through coordinator event `2026-06-15T06:57:52Z`.
- No production code changed in the NIT cleanup.

Evidence run from main worktree:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved -q` -> `1 passed in 1.78s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py -q` -> `1 passed, 1 xfailed in 1.86s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved --runxfail -q --tb=short` -> `1 passed in 1.91s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing advisories only: PROGRAM-MANUAL doc-anchor drift, legacy verify-readiness mailbox kinds, and R2 invisible-green warnings.

Freshness before commit:
- `env -u GIT_INDEX_FILE git log --oneline -5` initially showed `8567aab` at HEAD; immediately before commit it showed new `0c4e658 coord(cursor): operator consume broadcasts` ahead of it.
- `env -u GIT_INDEX_FILE git show --name-status --oneline 0c4e658` -> only `coordination/mailbox/seen/operator.txt`, no overlap with this NIT cleanup.
- `find coordination/mailbox/sent -maxdepth 1 -type f -name '2026-06-15T07-*' -print` -> no events before commit.

Ask:
- Please verify the touched-file prose no longer claims both siblings are unfixed / director2-owed.
- If clean, return GO so coordinator can reconcile `perf-take-meta` from fixed to verified.

Cursor at send: 2026-06-15T06:57:52Z

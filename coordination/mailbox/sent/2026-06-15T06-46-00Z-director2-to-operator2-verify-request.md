# Director2 -> Operator2: Lane V request perf-take-meta 2b595e4

**When:** 2026-06-15T06:46:00Z · **From:** director2 (online)

Please run fresh Lane V on `2b595e4 fix(assembly): include performance final take metadata`.

Row:
- `perf-take-meta` (MEDIUM assembly): `CinemaPipeline._approved_take_metadata()` now resolves an approved final `performance_takes` entry, so assembly can see embedded-audio metadata for performance takes just like motion and postprocess takes.

Director2 evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved -q` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py -q` -> `1 passed, 1 xfailed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved --runxfail -q --tb=short` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing doc-anchor / legacy mailbox-kind / R2 advisories only.

Scope:
- `cinema_pipeline.py`
- `tests/unit/test_postprocess_audio_siblings_xfail.py`
- `docs/superpowers/briefs/2026-06-15-perf-take-meta.md`
- `docs/REMEDIATION-INVENTORY.md` (`perf-take-meta` row only)

Wave 2 remains UNMET on unrelated blockers and the product-oracle artifact requirement; this request is only for `perf-take-meta`.

Cursor at send: 2026-06-15T06:33:13Z

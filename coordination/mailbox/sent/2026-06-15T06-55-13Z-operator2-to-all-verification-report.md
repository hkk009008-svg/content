# Operator2 → All: Lane V NITS perf take meta 2b595e4

**When:** 2026-06-15T06:55:13Z · **From:** operator2 (online)

VERDICT: NITS for `2b595e4 fix(assembly): include performance final take metadata`.

Row covered:
- `perf-take-meta` - runtime behavior GO, touched-file prose NIT.

Freshness / scope:
- Pre-report `git log --oneline -5` -> `95f9ca2`, `bf9f21c`, `1f1c830`, `1726dfc`, `02719a4`.
- `git show --name-status --oneline 2b595e4` -> touched `cinema_pipeline.py`, `docs/REMEDIATION-INVENTORY.md`, `docs/superpowers/briefs/2026-06-15-perf-take-meta.md`, and `tests/unit/test_postprocess_audio_siblings_xfail.py`.
- `git diff --name-status 2b595e4..HEAD -- cinema_pipeline.py tests/unit/test_postprocess_audio_siblings_xfail.py docs/superpowers/briefs/2026-06-15-perf-take-meta.md docs/REMEDIATION-INVENTORY.md coordination/mailbox/sent coordination/mailbox/seen/operator2.txt` -> only later mailbox events and `coordination/mailbox/seen/operator2.txt`; no scoped production/test/brief/inventory drift after `2b595e4`.

Evidence was run from clean HEAD archive `/private/tmp/content-lanev-cost-XALdy6` unless noted:
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved -q` -> `1 passed in 2.51s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py -q` -> `1 passed, 1 xfailed in 2.59s`.
- `env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved --runxfail -q --tb=short` -> `1 passed in 2.51s`.
- Main worktree smoke: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with existing PROGRAM-MANUAL doc-anchor drift, legacy mailbox-kind, and R2 invisible-green advisories only.

Write/scope audit:
- `cinema_pipeline.py:694` keeps `_approved_take_metadata(shot)` static/read-only and returns `{}` for missing IDs.
- `cinema_pipeline.py:703` now searches `("motion_takes", "postprocess_variants", "performance_takes")`, preserving existing motion/postprocess order and adding the missing final-performance case.
- Rule #12 write evidence remains: `cinema/shots/controller.py:1142` appends `performance_takes`; `cinema/review/controller.py:692` writes `approved_final_take_id` for final approvals that include performance takes.
- The separate `lipsync-veto` sibling remains pinned: module result is `1 passed, 1 xfailed`.

Findings:
1. MINOR - `tests/unit/test_postprocess_audio_siblings_xfail.py:1` - The touched file's module docstring still describes the audio siblings as debt pins left unfixed in commit `1eec3cd` and says director2 disposition is owed for both. That is stale now that `test_performance_take_as_final_metadata_is_resolved` is a live regression and `perf-take-meta` is fixed. Runtime behavior is sound, but the touched-file prose should say only the remaining `lipsync-veto` row is still xfailed/deferred. - NIT: update the docstring/prose, then request a NITS re-read.

Disposition:
- Do not reconcile `perf-take-meta` to verified yet; await the prose cleanup and operator2 NITS re-read.
- No cross-cutting lock/co-sign release is required; this lane touches `cinema_pipeline.py`, not the protocol lock-file set.

Cursor at send: 2026-06-15T06:51:29Z

# Director2 → Operator2: Lane V request: spent-usd-reset-on-resume 8b100459

**When:** 2026-06-15T15:30:32Z · **From:** director2 (online)

Please run Lane V on the landed spent-resume fix:

- Commit: `8b100459 fix(checkpoint): rehydrate spend on resume`
- Row: `spent-usd-reset-on-resume` (`cinema/checkpoint.py:163`, Pair-B, MAJOR, Wave 2)
- Brief: `docs/superpowers/briefs/2026-06-16-spent-usd-reset-on-resume.md`
- Production scope: `cost_tracker.py` adds `CostTracker.rehydrate_spent_usd_from_video(video_id)` and `cinema/checkpoint.py` calls it from `_restore_from_checkpoint()` after runstate restore.
- Regression scope: `tests/unit/test_spent_usd_resume.py` is the new executable selector for this row.
- Inventory scope: `docs/REMEDIATION-INVENTORY.md` replaces the prior `design-open` selector with the live regression and marks the row implemented pending Lane V.

Executed evidence from director2:

- Pre-fix red: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py -q` -> 2 failed for missing rehydrate helper and checkpoint restore leaving `spent_usd == 0.0`.
- Post-fix focused: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py -q` -> `2 passed`.
- Post-fix cost slice: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py tests/unit/test_cost_tracker.py -q` -> `85 passed, 2 warnings`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_spent_usd_resume.py --runxfail -q` -> `2 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> OK with existing PROGRAM-MANUAL doc-anchor and R2 invisible-green advisories only.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> still UNMET, but `spent-usd-reset-on-resume` is no longer a no-selector blocker; remaining explicit no-selector blocker is `perf-phase-no-gate`, plus missing product-oracle artifact and unrelated open pins.

Suggested checks:

- Inspect the actual `8b100459` diff and any drift after it.
- Run `tests/unit/test_spent_usd_resume.py -q` and the cost slice you judge necessary.
- Confirm the helper restores only rows for the current project/video id and does not require a `cinema/core.py` edit or cross-cutting lock.
- Confirm corrupt non-finite durable totals keep the gate fail-closed rather than silently resetting to zero.

No lock release applies; this is Pair-B lane work. Please send one GO/NITS/FAIL `verification-report` with executed evidence.

Cursor at send: 2026-06-15T15:25:12Z

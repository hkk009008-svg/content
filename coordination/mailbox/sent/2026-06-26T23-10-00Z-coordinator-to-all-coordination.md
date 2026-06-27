# Coordinator Consolidated Route: Cinema Pipeline Test Coverage

**When:** 2026-06-26T23:10:00Z · **From:** coordinator (online)

**Event Type**: coordination
**Sender**: coordinator
**Recipient**: all
**Timestamp**: 2026-06-26T23:10:00Z
**Context**: Test Coverage Analysis (2026-06-14) Gap Remediation

## Directives

The user-principal has authorized the execution of the full test-coverage closure mapped out in `docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md`. Work is to be distributed across the four-seat protocol as follows:

### To Pair A (director, operator)
Your focus is Tier 1 (HTTP Surface & State Mutation) and Tier 3 (Orchestration).
1. **director**: Scope and implement Flask-test-client regression tests for `api_serve_file` (guard containment), state mutators (`api_delete_project`, `api_pause`, `api_resume`, `api_restart_shot`), and gate endpoints (`api_generate_keyframe`, `api_approve_final_take`, etc.). Once Tier 1 is stable, move to Tier 3 Orchestration state-mutation paths in `cinema/shots/controller.py`. Issue Verify-Requests per component.
2. **operator**: Verify `director` implementations using `env -u GIT_INDEX_FILE pytest tests/unit/`. Issue GO/NITS/FAIL verification-reports.

### To Pair B (director2, operator2)
Your focus is Tier 2 (Quality Gates & Provider Error Paths) and Tier 3 (Audio DSP).
1. **director2**: Implement tests targeting boundary/halt paths in `face_validator_gate.should_halt`, `coherence_analyzer.assess_coherence`, `cinema/auto_approve.check_gate`, and provider failure modes (`kling_native.poll_task`, `ltx_native._native_generate`). Once Tier 2 is stable, move to Tier 3 Audio DSP (`audio/effects.py`, `audio/voiceover.py`). Issue Verify-Requests per component.
2. **operator2**: Verify `director2` implementations and ensure that crash handling paths operate cleanly without raising unexpected exceptions. Execute `wave_gate_check.py` as necessary. Issue GO/NITS/FAIL verification-reports.

### Shared Phase 0 Initiative (First-to-claim)
- Either `director` or `director2`: Add `pytest-cov` to `requirements.txt` and wire an advisory `--cov` report into the `pytest-unit` CI job so all subsequent work is measurable.

## Next Triggers
- **director** & **director2**: Send dispatch-claim receipts for Phase 0 and your respective first Tier components, then begin implementation.
- **operator** & **operator2**: Standby for Verify-Requests.

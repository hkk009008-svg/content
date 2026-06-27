# R-BRIEF — Pair-B Tier 2: quality-gate boundaries & provider failure modes

Seat: `director2` · Date: `2026-06-27` · Lane: Pair-B (video/assembly/audio)
Source directive: `coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`
Spec: `docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md` §4 Tier 2
Reviewer: `operator2` (impl ≠ verifier) — `env -u GIT_INDEX_FILE pytest tests/unit/`

## Scope & classification

Test-only additions. **No production-module edits → lane-only → NO lock claimed**
(writing tests that *import* `cinema/auto_approve.py` does not touch the
cross-cutting module; §6b locks are for editing the four cross-cutting modules,
not testing them). Mode: **orchestrate (R-ORCH ≥5 independent sub-tasks)** — one
fresh implementer per target, each extends the existing sibling module. No spend,
no network (all provider calls mocked), no pod, no dependency edit.

Phase 0 (`pytest-cov`) is **already landed** by another seat (`ad4cfdca
feat(ci): add advisory pytest-cov reporting to CI`) — not re-claimed here.

## Rule #12 evidence — every target read at its runtime branch (not type decl)

| # | Target (live file:line) | Branch under test (the gap) | Pin |
|---|---|---|---|
| 1 | `face_validator_gate.should_halt` `face_validator_gate.py:228` | conjunctive mode, `:272-301` — `composite_ok and arc_ok`; arc floor `arc_floor_bypassed = (not has_character) or (not best.has_arc)` `:279` | composite ≥0.92 but arc *just below* 0.85 with `has_character`+`has_arc` → **halt=False**; same composite with `has_character=False` OR `has_arc=False` → **halt=True**, reason contains `arc floor bypassed`. Plus budget halt `n≥8` unconditional, `n<4` no-halt, empty → no-halt. |
| 2 | `coherence_analyzer.assess_coherence` `coherence_analyzer.py:219` | unreadable-image guard `:240-243` → `_invalid_coherence` `:205` | nonexistent/corrupt `current_image` → `valid is False`, `overall_coherence_score == 0.0`, `error` names current_image; same for `previous_image`. (`valid=False` is the contract callers must not treat 0.0 as real data.) |
| 3 | `cinema/auto_approve.check_gate` `cinema/auto_approve.py:664` | predicate-raise handling `:722-743` | (a) predicate raises with **no prior veto** → `auto_approved False`, `deferred True`, veto text `eval error`; (b) predicate raises **after a veto already fired** → veto **stands**, `deferred False`, crashed predicate skipped (`:743 continue`) — *the documented-but-untested preserve path*. Plus `config.enabled=False`→`vetoes=["disabled"]`; unknown gate→`vetoes=["unknown gate: …"]`. |
| 4 | `kling_native.poll_task` `kling_native.py:170` | backoff `:190,226-229` `[3,5,8,12,15]` | mock `requests.get`+`time.sleep`: intervals advance 3→5→8→12→15 and **plateau at 15** (never exceed); `task_status=="succeed"`→returns data; `"failed"`→`RuntimeError`; `code!=0`→`RuntimeError`; never-complete→`TimeoutError`. |
| 5 | `ltx_native._native_generate` `ltx_native.py:204` | empty-200 guard `:256-263` | mock `urllib.request.urlopen` → `read()==b""` with `FAL_AVAILABLE=False`/no `fal_key` → returns **`None`**, and **no 0-byte file** left at `output_path`. |

## Rule #13 — sibling branches each test must also cover (not just the headline gap)

- **#1**: the three `halt_rule` siblings (`composite_only` default, `conjunctive`,
  `budget_only`→falls back to composite) share the `n≥halt_max_n`/`n<halt_min_n`
  fences — assert the budget + min-n branches alongside the conjunctive boundary
  so a future mode edit can't silently drop a fence.
- **#3**: `check_gate` has five decision states on the same try-block — `disabled`,
  `unknown gate`, `eval-error-no-veto (deferred)`, `eval-error-with-veto (veto
  stands)`, outer `module_error`. The headline gap is state 4; pin all five so the
  preserve path is anchored against its siblings.
- **#5**: the empty-body guard sits on the same `except` cascade as the 5xx→FAL and
  URLError→FAL recovery paths; assert the no-fallback branch returns `None` rather
  than raising, mirroring the existing transient-error tests.

## Per-target dispatch (extend the existing module; mirror its fixtures/style)

| # | Implementer writes into | Mirror |
|---|---|---|
| 1 | `tests/unit/test_face_validator_gate.py` | existing cases in same file |
| 2 | `tests/unit/test_coherence_analyzer.py` | existing (use `pytest.importorskip("cv2")` per repo R2 convention) |
| 3 | `tests/unit/test_auto_approve.py` | existing `check_gate` cases |
| 4 | `tests/unit/test_kling_native.py` | existing mock-`requests` cases |
| 5 | `tests/unit/test_ltx_native.py` | existing mock cases |

Acceptance per target: new tests **green** under
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_<x>.py -q`;
one clean commit per target (operator2 verifies BASE..HEAD per component). Any
defect surfaced that is NOT fixed this session ships a
`pytest.mark.xfail(strict=True, reason=…)` pin (R-VERIFY-TIER) — but these are
characterization tests of *correct* current behavior, so green is expected.

## Sequencing

Tier 2 first (this brief). Tier 3 Audio DSP (`audio/effects.apply_voice_effect`,
`audio/voiceover.get_voice_direction`) deferred until Tier 2 is operator2-stable,
per the directive ("Once Tier 2 is stable, move to Tier 3"). Push remains
user-gated.

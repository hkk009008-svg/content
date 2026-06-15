# Operator2 → All: Lane V GO charmgr-cost-fresh-instance 8226e30

**When:** 2026-06-15T08:17:43Z · **From:** operator2 (online)

VERDICT: GO for `charmgr-cost-fresh-instance` follow-up Lane V on `8226e30`.

Scope verified: `8226e30 fix(money): preserve charmgr budget fail-closed` repairs the prior operator2 FAIL edge by preserving malformed project budget caps for `CostTracker`'s fail-closed coercion. Coordinator may reconcile this row to `verified` after reading this operator GO. No cross-cutting lock release applies.

## Evidence
$ env -u GIT_INDEX_FILE git log --oneline -5
-> `7e762f4 coord(verify): request charmgr follow-up Lane V`; `8226e30 fix(money): preserve charmgr budget fail-closed`; `66a5e01 coord(cursor): operator2 consume charmgr fail routing`; `6b58240 coord(director): record pairA idle after charmgr fail`; `3f22a70 coord(inventory): record charmgr Lane V fail`.

$ env -u GIT_INDEX_FILE git show --stat --oneline 8226e30
-> `8226e30 fix(money): preserve charmgr budget fail-closed`; touched `coordination/mailbox/seen/director2.txt`, `docs/REMEDIATION-INVENTORY.md`, `docs/superpowers/briefs/2026-06-15-charmgr-cost-fresh-instance.md`, `domain/character_manager.py`, and `tests/unit/test_charmgr_cost_fresh_instance_xfail.py`; 78 insertions / 5 deletions.

$ env -u GIT_INDEX_FILE git diff --name-status 8226e30..HEAD -- domain/character_manager.py tests/unit/test_charmgr_cost_fresh_instance_xfail.py cost_tracker.py
-> no output; scoped production/test/cost-tracker files have not drifted after `8226e30`.

$ nl -ba domain/character_manager.py | sed -n '105,121p;198,205p;377,384p'
-> `domain/character_manager.py:105-113` returns floats for valid project budgets and returns malformed values unchanged for `CostTracker` coercion; `:116-120` constructs `CostTracker(budget_usd=_budget_usd_from_project(project))`; `:198-205` threads the project tracker plus `video_id=pid` into angle generation; `:377-384` records `FLUX_KONTEXT` on `cost_tracker or CostTracker()` with `video_id`.

$ nl -ba cost_tracker.py | sed -n '171,225p;443,460p'
-> `cost_tracker.py:171-192` maps non-coercible, NaN, and inf budget caps to `_NONFINITE_BUDGET_BLOCK = -1.0`; `:223-225` stores that sentinel instead of unlimited `None`; `:443-460` makes `would_exceed()` fire when a cap is present.

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
from domain.character_manager import _budget_usd_from_project, _cost_tracker_from_project
cases = ['12.5', 'abc', 'nan', 'inf', '', None, 0]
for value in cases:
    project = {'global_settings': {}}
    if value is not None:
        project['global_settings']['budget_limit_usd'] = value
    raw = _budget_usd_from_project(project)
    tracker = _cost_tracker_from_project(project)
    try:
        print(repr(value), 'raw=', repr(raw), 'tracker_budget=', repr(tracker.budget_usd), 'would_exceed=', tracker.would_exceed('FLUX_KONTEXT'))
    finally:
        tracker.close()
PY
-> `'12.5' raw= 12.5 tracker_budget= 12.5 would_exceed= False`; `'abc' raw= 'abc' tracker_budget= -1.0 would_exceed= True`; `'nan' raw= nan tracker_budget= -1.0 would_exceed= True`; `'inf' raw= inf tracker_budget= -1.0 would_exceed= True`; `'' raw= '' tracker_budget= -1.0 would_exceed= True`; `None raw= None tracker_budget= None would_exceed= False`; `0 raw= 0.0 tracker_budget= None would_exceed= False`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py -q
-> `3 passed in 2.57s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py --runxfail -q --tb=short
-> `3 passed in 2.57s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q
-> `83 passed, 2 warnings in 0.08s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_character_registration_single_face.py tests/unit/test_project_persistence.py -q
-> `13 passed, 10 subtests passed in 5.21s`.

$ tmp=$(mktemp -d /private/tmp/content-charmgr-budget-XXXXXX); env -u GIT_INDEX_FILE git archive HEAD | tar -x -C "$tmp"; perl -0pi -e 's/except \(TypeError, ValueError, OverflowError\):\n        # Preserve corrupted caps for CostTracker\x27s fail-closed coercion\.\n        return budget_usd/except (TypeError, ValueError, OverflowError):\n        return None/' "$tmp/domain/character_manager.py"; cd "$tmp"; env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py::test_project_budget_corruption_keeps_angle_tracker_gate_active -q --tb=short
-> `1 failed`; assertion showed `malformed project budget became an unlimited CostTracker`, proving the repaired malformed-budget regression is non-vacuous.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> `OK`; existing advisories only: PROGRAM-MANUAL doc-anchor drift, legacy `verify-readiness` mailbox kinds, and R2 invisible-green warnings.

$ find coordination/locks -maxdepth 1 -type f -print | sort
-> `coordination/locks/.gitkeep` only.

## Independent reviewers
- `lane-v-verifier` candidate: production/test behavior GO, with one doc-sync NIT: the brief overstated `cinema/core.py` malformed-budget behavior. I corrected that stale sibling-audit prose in this operator2 report commit.
- `money-gate-reviewer` candidate: FAIL because `_generate_multi_angle_refs()` does not call `would_exceed()` before FAL spend. I do not accept that as a blocker for this row: the brief explicitly says `No pre-spend would_exceed() gate; perf-phase-no-gate is separate`, and the inventory tracks pre-spend absence as a distinct open risk. This GO is for the scoped visibility / gate-source repair, not for closing any pre-spend gate row.

## Findings
1. INFORMATIONAL - `domain/character_manager.py:105` / `cost_tracker.py:171` - The prior FAIL edge is repaired: valid numeric project budgets still become floats, while malformed, NaN, inf, and empty-string caps now reach `CostTracker` and become the fail-closed `-1.0` sentinel instead of unlimited `None`. - GO.
2. INFORMATIONAL - `domain/character_manager.py:199` / `domain/character_manager.py:379` - Character angle generation now uses the project/caller tracker and records `FLUX_KONTEXT` with `video_id=pid`; no scoped production/test drift after `8226e30`. - GO.
3. INFORMATIONAL - `tests/unit/test_charmgr_cost_fresh_instance_xfail.py:74` - The malformed-budget regression is live, green, `--runxfail` clean, and mutation-sensitive. - GO.
4. INFORMATIONAL - `docs/superpowers/briefs/2026-06-15-charmgr-cost-fresh-instance.md` - Operator2 corrected stale sibling-audit prose: `cinema/core.py` still pre-coerces malformed strings to `None`; that residual sibling risk is not in this row's touched production path and is not a blocker for this GO. - record only.
5. INFORMATIONAL - `docs/REMEDIATION-INVENTORY.md:75` / brief non-goal - No pre-spend `would_exceed()` check is added here; that remains outside this row's scope and should not be treated as verified by this report. - separate open risk remains.

## Scope-match
No CRITICAL cross-cutting lock/co-sign path is implicated. `8226e30` did not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`, and `coordination/locks/` contains only `.gitkeep`. The landed diff matches the briefed CharacterManager scope after the operator2 doc-sync correction above.

Cursor at send: 2026-06-15T08:05:44Z

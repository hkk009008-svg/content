# R-BRIEF: charmgr-cost-fresh-instance - route character angle spend to a shared tracker

PRIORITY: CRITICAL (provisional, coordinator Session-12 upgrade pending
operator2 ratification)        LANE: B (video/assembly/audio)

CROSS-CUTTING: no for this brief. Do not edit `auto_approve.py`,
`cinema/context.py`, `core.py`, or `web_server.py`.

If implementation scope expands to pass a cached core tracker from
`web_server.py`, STOP and claim `W2-web_server.py.lock` first. This brief keeps
B6 lane-only by fixing the domain character-creation path itself.

## The Defect

`domain/character_manager.py:350` constructs a fresh `CostTracker()` inside
`_generate_multi_angle_refs()` and records every successful `FLUX_KONTEXT`
multi-angle reference on that throwaway tracker. The tracker has no project
budget and is not the caller's tracker, so the spend does not reach the
accumulator that budget gates read.

Production path verified in the discovery log:

`POST /api/projects/<pid>/characters -> web_server.py:587 create_character_with_images -> character_manager.py:179 _generate_multi_angle_refs -> character_manager.py:350 CostTracker().record_api_call(...)`.

Current RED / non-vacuity:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py --runxfail -q --tb=short
F                                                                        [100%]
E   TypeError: _generate_multi_angle_refs() got an unexpected keyword argument 'cost_tracker'
1 failed in 1.35s
```

Lane V FAIL addendum (operator2, 2026-06-15T07:47:04Z): the landed tracker
threading fix correctly routes valid numeric project budgets, but
`_budget_usd_from_project()` converts malformed persisted caps such as `"abc"`
to `None`. That silently creates an unlimited tracker, while direct
`CostTracker(budget_usd="abc")` correctly maps the corruption to the blocking
sentinel.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -c "from domain.character_manager import _budget_usd_from_project; from cost_tracker import CostTracker; p={'global_settings': {'budget_limit_usd': 'abc'}}; print('_budget_usd_from_project=', _budget_usd_from_project(p)); t=CostTracker(db_path=':memory:', budget_usd='abc'); print('direct_budget_usd=', t.budget_usd, 'would_exceed=', t.would_exceed('FLUX_KONTEXT')); t.close()"
_budget_usd_from_project= None
direct_budget_usd= -1.0 would_exceed= True
```

## Rule #12 - Grep The Writes

TARGET SYMBOL: `CostTracker.spent_usd`, the in-process budget-gate accumulator.

```text
$ rg -n "self\.spent_usd\s*[:+]?=|self\.spent_usd \+=" cost_tracker.py
307:            self.spent_usd += cost_usd
```

The runtime write is `CostTracker.log()`'s post-commit increment. Therefore the
fix must call `record_api_call()` on the caller/project tracker that owns the
gate accumulator, not on a new throwaway instance.

TARGET WRITE SITE: character multi-angle FLUX recording.

```text
$ nl -ba domain/character_manager.py | sed -n '343,353p'
   343	            # F-D.1 / MR-C0 closure (cycle-16 max-quality audit a79c59):
   344	            # character-creation FLUX Kontext Max Multi calls were
   345	            # untracked by cost_tracker — 5 calls × ~$0.04 = ~$0.20 per
   346	            # character invisible to budget enforcement. Mirrors M-B2
   347	            # best-effort pattern; non-fatal if tracker import fails.
   348	            try:
   349	                from cost_tracker import CostTracker
   350	                CostTracker().record_api_call(
   351	                    "FLUX_KONTEXT",
   352	                    operation="multi_angle_ref",
   353	                )
```

TARGET SYMBOL: `CostTracker.budget_usd`, the budget-gate cap that must preserve
fail-closed coercion for corrupted project settings.

```text
$ rg -n "self\.budget_usd\s*=|budget_usd = _finite_budget_or_block|_finite_budget_or_block\(|budget_limit_usd|CostTracker\(budget_usd=" cost_tracker.py domain/character_manager.py tests/unit/test_cost_tracker.py tests/unit/test_charmgr_cost_fresh_instance_xfail.py
domain/character_manager.py:106:    budget_usd = (project.get("global_settings") or {}).get("budget_limit_usd")
domain/character_manager.py:118:        return CostTracker(budget_usd=_budget_usd_from_project(project))
cost_tracker.py:171:def _finite_budget_or_block(value) -> float:
cost_tracker.py:224:            budget_usd = _finite_budget_or_block(budget_usd)
cost_tracker.py:225:        self.budget_usd = budget_usd if budget_usd else None
```

The helper may pre-coerce valid numeric strings for the domain caller, but it
must not swallow parse errors into `None`; malformed values need to reach
`CostTracker.__init__()` so `_finite_budget_or_block()` maps them to the
blocking sentinel.

## Rule #13 - Sibling Audit

SHARED FENCE/STATE: cost-gate source of truth, `CostTracker.spent_usd`.

```text
$ rg -n "CostTracker\(\)\.record_api_call|cost_tracker or CostTracker\(|cost_tracker=cost_tracker|record_api_call\(" domain/character_manager.py audio/foley.py audio/dialogue.py audio/music.py performance cinema/shots/controller.py cinema_pipeline.py
audio/foley.py:185:            _tracker = cost_tracker or CostTracker()
audio/foley.py:186:            _tracker.record_api_call("STABILITY_FOLEY", operation="scene_foley")
audio/dialogue.py:593:                    _tracker = cost_tracker or CostTracker()
audio/dialogue.py:594:                    _tracker.record_api_call(
audio/dialogue.py:643:                _tracker = cost_tracker or CostTracker()
audio/dialogue.py:644:                _tracker.record_api_call("ELEVENLABS", operation="dialogue_tts")
audio/music.py:248:            _tracker = cost_tracker or CostTracker()
audio/music.py:249:            _tracker.record_api_call("SUNO_V5", operation="bgm")
audio/music.py:375:                _tracker = cost_tracker or CostTracker()
audio/music.py:376:                _tracker.record_api_call("FAL_STABLE_AUDIO", operation="bgm")
domain/character_manager.py:350:                CostTracker().record_api_call(
performance/act_one.py:34:        (cost_tracker or CostTracker()).log_api(
performance/live_portrait.py:31:        (cost_tracker or CostTracker()).log_api(
performance/driving_video.py:37:        (cost_tracker or CostTracker()).log_api(
performance/viggle.py:30:        (cost_tracker or CostTracker()).log_api(
```

Audit result: audio and performance siblings already accept a caller-supplied
tracker and fall back only when absent. Character manager is the outlier because
it unconditionally creates the fallback tracker at the write site. Fold that
site into the same pattern.

Budget-coercion sibling audit:

```text
$ rg -n "CostTracker\(budget_usd=|cost_tracker or _cost_tracker_from_project|_cost_tracker_from_project\(" -g '*.py' .
./domain/character_manager.py:115:def _cost_tracker_from_project(project: dict):
./domain/character_manager.py:118:        return CostTracker(budget_usd=_budget_usd_from_project(project))
./domain/character_manager.py:198:        angle_cost_tracker = cost_tracker or _cost_tracker_from_project(project)
./cost_tracker.py:22:Construct ``CostTracker(budget_usd=N)`` to enable the soft cap. Call
./cinema/core.py:113:        cost_tracker=CostTracker(budget_usd=budget_usd),
```

Audit result: direct `CostTracker` construction lets the canonical constructor
enforce corrupted caps; `auto_approve.py` has its own explicit corrupt-cap
guard because it reads the project dict directly. `cinema/core.py` is a residual
sibling risk: it still pre-coerces malformed strings to `None` before constructing
`CostTracker`, so it does **not** prove the canonical constructor behavior.
Character manager must avoid that mistake for malformed project settings instead
of translating corruption to the `None`/unlimited sentinel.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
from cost_tracker import CostTracker
raw = "abc"
try:
    core_precoerced = float(raw) if raw else None
except (TypeError, ValueError):
    core_precoerced = None
tracker = CostTracker(db_path=":memory:", budget_usd=core_precoerced)
try:
    print("core_precoerced=", repr(core_precoerced), "tracker_budget=", repr(tracker.budget_usd), "would_exceed=", tracker.would_exceed("FLUX_KONTEXT"))
finally:
    tracker.close()
PY
core_precoerced= None tracker_budget= None would_exceed= False
```

Do not fold `perf-phase-no-gate` here: that is a separate pre-spend gate row.
Do not fold `web_server.py` HTTP hardening here: B3 owns the web lock and must
run after B2 `auto_approve.py`.

## Full-Shape Pattern Reference

Mirror the audio T5 pattern, including best-effort behavior:

```text
$ nl -ba audio/foley.py | sed -n '181,187p'
   181	        # T5: use caller-supplied tracker when provided so spend accumulates on
   182	        # the pipeline's budget-aware tracker (cross-process persistence deferred).
   183	        try:
   184	            from cost_tracker import CostTracker
   185	            _tracker = cost_tracker or CostTracker()
   186	            _tracker.record_api_call("STABILITY_FOLEY", operation="scene_foley")
   187	        except Exception:
```

Full shape to mirror: optional `cost_tracker` parameter, caller threads it when
available, provider function uses `cost_tracker or CostTracker()` at the
best-effort record site, and exceptions remain non-fatal.

## The Fix

Implement directly; expected scope is small and tightly coupled.

Touch:
- `domain/character_manager.py`
- `tests/unit/test_charmgr_cost_fresh_instance_xfail.py`
- this brief and `docs/REMEDIATION-INVENTORY.md` status notes if the fix lands

Required behavior:
- Add optional `cost_tracker=None` to `create_character_with_images()` and
  `_generate_multi_angle_refs()`.
- In `create_character_with_images()`, create a project-budget-aware tracker
  from `project["global_settings"]["budget_limit_usd"]` only when no caller
  supplied one, then pass it into `_generate_multi_angle_refs()`.
- Preserve `CostTracker`'s fail-closed coercion for malformed project budgets:
  valid numeric strings may become floats, but non-coercible values must not
  become `None`/unlimited.
- Pass the project id as `video_id` when recording multi-angle reference spend
  so `/cost-live` style queries can attribute the row.
- At the write site, use `_tracker = cost_tracker or CostTracker()` and call
  `_tracker.record_api_call("FLUX_KONTEXT", operation="multi_angle_ref",
  video_id=video_id)`.
- Convert the strict xfail to a live regression and update stale MAJOR prose to
  provisional CRITICAL wording.
- Add/keep a caller-path test proving `create_character_with_images()` threads a
  tracker into `_generate_multi_angle_refs()`, so the fix is not merely the
  internal seam.

Explicit non-goals:
- No `web_server.py` edit in this brief.
- No pre-spend `would_exceed()` gate; `perf-phase-no-gate` is separate.
- No product-oracle artifact; Wave-2 gate still needs that independently.

## Verification The Operator/CI Will Run

Specialist reviewer: operator2 should include the `money-gate-reviewer` lens
for the gate-source-mismatch question before returning Lane V GO.

Expected local commands:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_charmgr_cost_fresh_instance_xfail.py --runxfail -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Expected result: charmgr pin becomes live green; `--runxfail` also passes
because no xfail remains; cost tracker suite stays green; smoke remains OK with
only pre-existing advisories.

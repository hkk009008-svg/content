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

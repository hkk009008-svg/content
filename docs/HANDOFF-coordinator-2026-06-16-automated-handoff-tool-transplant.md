# HANDOFF DRAFT - coordinator

This is an automated evidence draft, not a final authority decision. It is
designed to speed up handoff writing while keeping the seat responsible for
reviewing scope, ownership, and next action.

Generated: `2026-06-16T06:57:14+0900`
Repo: `/Users/hyungkoookkim/Content`

## Snapshot, Not Truth

Trust order for the next session: user instruction, current git/filesystem,
mailbox bodies, then this handoff draft. Refresh live state before acting.
Do not consume mailbox cursors from this draft tool, and do not treat receipt
evidence as proof that assigned work is complete.

## Refresh Live State First

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
```

For coordinator work, also read recent `coordination/mailbox/sent/` bodies before
routing or reconciling. For live-seat work, surface the unread count before
processing mail and consume cursors only as an intentional mutation.

## Git

- branch: `main`
- HEAD: `79c5af5b docs(handoff): refresh director pair-b lanev monitor`
- origin/main: `28 ahead, 0 behind`

```text
79c5af5b docs(handoff): refresh director pair-b lanev monitor
af993382 docs(handoff): refresh operator2 Lane V handoff
306c680e docs(handoff): director2 lipsync Lane V pending
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
```

## Mailbox

- seat cursor: `(not used; coordinator is unpinned)`
- seat unread: `all-scope 12 shown`

Relevant seat mail:

- `2026-06-15T18-45-12Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-58-49Z-coordinator-to-all-coordination.md`
- `2026-06-15T19-29-46Z-director-to-all-status.md`
- `2026-06-15T19-32-26Z-operator-to-all-status.md`
- `2026-06-15T19-34-17Z-operator2-to-all-status.md`
- `2026-06-15T19-46-45Z-operator2-to-all-verification-report.md`
- `2026-06-15T19-57-31Z-operator-to-all-status.md`
- `2026-06-15T19-59-27Z-coordinator-to-all-coordination.md`
- `2026-06-15T20-01-25Z-director-to-all-status.md`
- `2026-06-15T20-04-00Z-operator-to-all-status.md`
- `2026-06-15T20-04-46Z-operator2-to-all-status.md`
- `2026-06-15T21-34-51Z-operator-to-all-status.md`

Recent coordinator/all mail:

- `2026-06-15T15-25-12Z-coordinator-to-all-coordination.md`
- `2026-06-15T16-25-06Z-coordinator-to-all-coordination.md`
- `2026-06-15T17-19-41Z-coordinator-to-all-coordination.md`
- `2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-18-10Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-45-12Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-58-49Z-coordinator-to-all-coordination.md`
- `2026-06-15T19-59-27Z-coordinator-to-all-coordination.md`

## Peer Heartbeats

- `director: 2026-06-15T21:56:31Z 79c5af5b`
- `director2: 2026-06-15T21:52:55Z 306c680e`
- `operator: 2026-06-15T21:50:31Z 69848473`
- `operator2: 2026-06-15T21:55:13Z af993382`

## Working Tree Scope

Staged scope:

```text
(none)
```

Status scope:

```text
M .agents/skills/four-seat-protocol/SKILL.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py
```

Human Review Required: confirm this scope is owned by `coordinator` before
staging, committing, routing, or deleting anything. Preserve unrelated seat WIP.

## Gate, Locks, And Artifacts

Wave 2 gate:

```text
Wave 2 gate: UNMET  counts={'verified': 23, 'open': 6, 'fixed': 1}
  gate rows: 21; executable selectors: 24
  PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
  PYTEST: exit=1 command=/Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py tests/unit/test_lane_silent_gate_siblings_xfail.py tests/unit/test_phase_c_vision.py::TestValidateIdentityVision tests/unit/test_phase_c_vision.py::TestValidateIdentityVisionEncodeFailure tests/unit/test_identity_validator.py::TestVisionFallbackMarkerMapping tests/unit/test_lane_silent_gate_siblings_xfail.py::test_validate_identity_vision_fails_closed_on_api_failure tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate tests/unit/test_discovery_lipsync_xfail.py tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection tests/unit/test_discovery_web_server_xfail.py tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_shot_spent_never_written_xfail.py tests/unit/test_web_research_uncounted_xfail.py tests/unit/test_llmensemble_cost_uncounted_xfail.py tests/unit/test_spent_usd_resume.py tests/unit/test_charmgr_cost_fresh_instance_xfail.py tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate::test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd tests/unit/test_cost_spent_nan_poison_xfail.py tests/unit/test_cost_conn_crossthread_xfail.py --runxfail -q --tb=short
  PYTEST output tail:
    ...
        return cors_after_request(app.make_response(f(*args, **kwargs)))
                                                    ^^^^^^^^^^^^^^^^^^
    .venv/lib/python3.13/site-packages/flask/app.py:1511: in wsgi_app
        response = self.full_dispatch_request()
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    .venv/lib/python3.13/site-packages/flask/app.py:919: in full_dispatch_request
        rv = self.handle_user_exception(e)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    .venv/lib/python3.13/site-packages/flask_cors/extension.py:176: in wrapped_function
        return cors_after_request(app.make_response(f(*args, **kwargs)))
                                                    ^^^^^^^^^^^^^^^^^^
    .venv/lib/python3.13/site-packages/flask/app.py:917: in full_dispatch_request
        rv = self.dispatch_request()
             ^^^^^^^^^^^^^^^^^^^^^^^
    .venv/lib/python3.13/site-packages/flask/app.py:902: in dispatch_request
        return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)  # type: ignore[no-any-return]
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    web_server.py:2656: in api_cleanup_all
        aggressive = request.json.get("aggressive", False) if request.is_json else False
                     ^^^^^^^^^^^^^^^^
    E   AttributeError: 'NoneType' object has no attribute 'get'
    _____________ test_upload_style_board_empty_filenames_returns_400 ______________
    tests/unit/test_discovery_web_server_xfail.py:408: in test_upload_style_board_empty_filenames_returns_400
        assert resp.status_code == 400, (
    E   AssertionError: Expected 400 when all file parts have empty filenames, got 201: b'{"total_refs":0,"uploaded":0}\n'
    E   assert 201 == 400
    E    +  where 201 = <WrapperTestResponse streamed [201 CREATED]>.status_code
    ----------------------------- Captured stdout call -----------------------------
    🎬 Created project 'xfail-test' → projects/bdc0775bc83d/
    =========================== short test summary info ============================
    FAILED tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_clear_performance_nonexistent_shot_returns_404
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_upload_driving_video_mutator_miss_returns_non_201
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_add_character_non_numeric_ip_weight_returns_400
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_add_object_non_numeric_ip_weight_returns_400
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_update_shot_prompt_null_json_body_returns_400
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_cleanup_null_json_body_returns_non_500
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_cleanup_all_null_json_body_returns_non_500
    FAILED tests/unit/test_discovery_web_server_xfail.py::test_upload_style_board_empty_filenames_returns_400
    9 failed, 58 passed in 2.50s
```

Smoke:

```text
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md — kind 'verify-addendum' not in KNOWN_KINDS
CEREMONY CHECK — forbid appearance-of-verification-without-substance (ADR-027 / ADR-028)

R1 xfail-strictness ....... PASS  12 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
     ~ tests/unit/test_discovery_identity_xfail.py:193: skip() in a pin file — confirm it cannot hide the pinned defect
     ~ tests/unit/test_lane_silent_gate_siblings_xfail.py:64: importorskip('cv2') — dep present (latent invisible-green risk)
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail

RESULT: no ceremony detected — every relied-on green is backed by execution.
OK
```

Locks:

```text
coordination/locks/.gitkeep
```

Product-oracle artifacts:

```text
(none)
```

## Next-Seat Notes To Fill In

- Current owned task: state-transfer for the partly automated handoff tool work.
  The tool itself was implemented before this handoff; this turn only refreshed
  the coordinator handoff artifact from live evidence.
- Files the next coordinator session may edit for this task:
  `scripts/draft_handoff.py`, `tests/unit/test_draft_handoff.py`,
  `scripts/continuation_readiness.py`,
  `tests/unit/test_continuation_readiness.py`,
  `tests/unit/test_codex_protocol_artifacts.py`,
  `.agents/skills/four-seat-protocol/SKILL.md`,
  `docs/protocol/codex/continuation.md`, and this handoff file.
- Files or work the next seat must preserve:
  `docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md` and
  `docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md` are
  untracked seat handoff drafts from other seats; do not delete or claim them
  from the coordinator seat. No shared-index staged scope was present at final
  refresh.
- Verification already run for the handoff-tool work:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_draft_handoff.py tests/unit/test_continuation_readiness.py tests/unit/test_codex_protocol_artifacts.py -q --tb=short`
  -> `14 passed`; `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
  -> `OK` with existing advisories/warnings only; this handoff was regenerated
  with `env -u GIT_INDEX_FILE .venv/bin/python scripts/draft_handoff.py coordinator --wave 2 --smoke --output docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md`.
- Verification still owed before any commit/claim: rerun the focused tests after
  further edits and refresh live coordinator state. Wave 2 remains UNMET for
  the missing product-oracle artifact and known HTTP/postprocess blockers; this
  handoff does not reconcile or verify Wave 2 rows.
- Lock, push, pod-spend, and paid-API status: no lock claimed, no push, no pod
  spend, no paid API spend. Coordinator remains unpinned and did not consume
  mailbox cursors.
- Exact next action: open a clean focused coordinator session, run the refresh
  commands above, inspect current dirty scope, preserve the two unrelated
  untracked seat handoffs, and either commit only the coordinator-owned
  handoff-tool scope if requested or continue with no-op reporting if no state
  transition occurred.

## Clean Focused Session Transplant

Open the clean session with:

```text
continue as coordinator
```

Then say:

```text
Read this handoff as a snapshot, refresh live mailbox and git state before acting, preserve unrelated WIP, and follow the role boundary for this seat.
```

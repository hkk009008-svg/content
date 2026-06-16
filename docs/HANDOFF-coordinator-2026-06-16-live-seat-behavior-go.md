# Coordinator Handoff - Live-Seat Behavior GO

This is a coordinator closeout for the core live-seat behavior unification
cycle. It is still a snapshot: refresh git, mailbox, gate, and smoke state
before acting.

Generated: `2026-06-16T18:06:35+0900`
Repo: `/Users/hyungkoookkim/Content`

## Snapshot, Not Truth

Trust order for the next session: user instruction, current git/filesystem,
mailbox bodies, then this handoff. Refresh live state before acting.
Do not consume mailbox cursors from this handoff tool, and do not treat receipt
evidence as proof that assigned work is complete.

## Coordinator Decision

- Current cycle: complete. `operator` issued Lane V GO for the core live-seat
  behavior unification verify request, and `director2` consumed that GO.
- Latest binding mailbox evidence:
  `coordination/mailbox/sent/2026-06-16T08-57-23Z-operator-to-director2-verification-report.md`
  and
  `coordination/mailbox/sent/2026-06-16T09-05-54Z-director2-to-all-status.md`.
- No coordinator route is needed from this state. The next action should come
  from an explicit user instruction, a new coordinator route, a new Pair-A or
  Pair-B director-owned task, or a Tier-A co-sign request.
- Push remains user-gated. No lock claim/release, production edit, inventory
  transition, pod spend, or paid API spend is authorized by this handoff.

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
- HEAD: `d43533a4 director2(status): consume live-seat GO`
- origin/main: `19 ahead, 0 behind`

```text
d43533a4 director2(status): consume live-seat GO
9b810bfd operator(verify): GO live-seat behavior unification
4f0135db coord(verify): request live-seat behavior Lane V
803c6362 docs(protocol): document live-seat behavior sources
d8155d2a codex(protocol): name canonical live-seat behavior
```

## Mailbox

- seat cursor: `(not used; coordinator is unpinned)`
- seat unread: `all-scope 12 shown`

Relevant seat mail:

- `2026-06-16T05-44-45Z-operator2-to-all-verification-report.md`
- `2026-06-16T05-46-28Z-director-to-all-status.md`
- `2026-06-16T05-48-10Z-director2-to-all-status.md`
- `2026-06-16T05-52-45Z-coordinator-to-all-coordination.md`
- `2026-06-16T06-02-09Z-operator2-to-all-status.md`
- `2026-06-16T06-06-26Z-director2-to-all-status.md`
- `2026-06-16T06-17-17Z-coordinator-to-all-query.md`
- `2026-06-16T06-26-37Z-director2-to-all-status.md`
- `2026-06-16T06-26-38Z-director-to-all-status.md`
- `2026-06-16T06-26-42Z-operator2-to-all-status.md`
- `2026-06-16T08-28-37Z-operator-to-all-status.md`
- `2026-06-16T09-05-54Z-director2-to-all-status.md`

Recent coordinator/all mail:

- `2026-06-16T01-17-28Z-coordinator-to-all-coordination.md`
- `2026-06-16T03-38-45Z-coordinator-to-all-coordination.md`
- `2026-06-16T04-19-21Z-coordinator-to-all-coordination.md`
- `2026-06-16T05-04-09Z-coordinator-to-all-coordination.md`
- `2026-06-16T05-21-24Z-coordinator-to-all-coordination.md`
- `2026-06-16T05-41-20Z-coordinator-to-all-coordination.md`
- `2026-06-16T05-52-45Z-coordinator-to-all-coordination.md`
- `2026-06-16T06-17-17Z-coordinator-to-all-query.md`

## Peer Heartbeats

- `director: 2026-06-16T08:31:23Z 937bc691`
- `director2: 2026-06-16T09:08:22Z d43533a4`
- `operator: 2026-06-16T09:03:55Z 9b810bfd`
- `operator2: 2026-06-16T08:28:13Z a22caf4a`

## Working Tree Scope

Staged scope:

```text
(none)
```

Status scope:

```text
?? docs/HANDOFF-coordinator-2026-06-16-live-seat-behavior-go.md
```

The director2 cursor/status closeout is committed in `d43533a4`; the only
remaining dirty path at final coordinator refresh is this coordinator handoff.

## Gate, Locks, And Artifacts

Wave 2 gate:

```text
Wave 2 gate: MET  counts={'verified': 30}
  gate rows: 21; executable selectors: 24
  PRODUCT ORACLE: logs/product-oracle-wave2.json
  PYTEST: exit=0 command=/Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_has_character_lora_only_hole.py tests/unit/test_lane_silent_gate_siblings_xfail.py tests/unit/test_phase_c_vision.py::TestValidateIdentityVision tests/unit/test_phase_c_vision.py::TestValidateIdentityVisionEncodeFailure tests/unit/test_identity_validator.py::TestVisionFallbackMarkerMapping tests/unit/test_lane_silent_gate_siblings_xfail.py::test_validate_identity_vision_fails_closed_on_api_failure tests/unit/test_postprocess_audio_siblings_xfail.py tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate tests/unit/test_discovery_lipsync_xfail.py tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection tests/unit/test_discovery_web_server_xfail.py tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_shot_spent_never_written_xfail.py tests/unit/test_web_research_uncounted_xfail.py tests/unit/test_llmensemble_cost_uncounted_xfail.py tests/unit/test_spent_usd_resume.py tests/unit/test_charmgr_cost_fresh_instance_xfail.py tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate::test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget tests/unit/test_budget_pre_spend_gate.py::TestPerformancePhaseBudgetAbort tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness::test_performance_capture_engines_priced_in_api_cost_usd tests/unit/test_cost_spent_nan_poison_xfail.py tests/unit/test_cost_conn_crossthread_xfail.py --runxfail -q --tb=short
  PYTEST output tail:
    .......................................................................  [100%]
    71 passed in 3.32s
```

Smoke:

```text
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md — kind 'verify-addendum' not in KNOWN_KINDS
CEREMONY CHECK — forbid appearance-of-verification-without-substance (ADR-027 / ADR-028)

R1 xfail-strictness ....... PASS  3 xfail markers; all strict=True+reason
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
logs/product-oracle-wave2.json
```

## Next-Seat Notes

- Current owned task: none for coordinator. Live-seat behavior unification is
  closed by operator GO plus director2 status.
- Files the next seat may edit: only the files named by the next explicit route
  or user instruction.
- Files or staged work the next seat must preserve: this untracked coordinator
  handoff, unless it is committed or intentionally superseded.
- Verification already run: operator Lane V report says `37 passed` for focused
  protocol tests, `scripts/ci_smoke.py` OK, and `scripts/wave_gate_check.py 2`
  MET with selector tail `71 passed`. This coordinator refresh also ran
  `scripts/ci_smoke.py` OK and `scripts/wave_gate_check.py 2` MET.
- Verification still owed: none for the core live-seat behavior unification
  cycle.
- Lock, push, pod-spend, and paid-API status: no locks held except `.gitkeep`;
  no push or spend authorized.
- Exact next action: wait for explicit user instruction or a new route. If the
  next request is `push`, fetch first, inspect ahead/behind, preserve current
  dirty director2 state, and do not force-push.

## Clean Focused Session Transplant

Open the clean session with:

```text
continue as coordinator
```

Then say:

```text
Read this handoff as a snapshot, refresh live mailbox and git state before acting, preserve unrelated WIP, and follow the role boundary for this seat.
```

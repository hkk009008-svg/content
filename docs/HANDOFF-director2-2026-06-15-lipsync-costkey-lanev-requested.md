# Handoff - director2 Pair-B - 2026-06-15 lipsync costkey fixed; Lane V requested

Seat: director2, Pair-B director. User requested `handoff` after the
`lipsync-postproc-costkey` implementation and verify-request. No push was
performed.

## Current Durable HEAD

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
aa6f00f9 coord(verify): request lipsync costkey Lane V
82c6a2a1 coord(protocol): adopt subagent workflow per seat
aeb1a2b7 fix(lipsync): price postprocess cost key
b366ae0d coord(director): publish product-oracle guidance
1e816f3e coord(status): operator ready after product-oracle guidance
d2b2de3d coord(all): resync wave2 seat routing
e1ab3105 docs(handoff): director2 codex mail consumed
04b42f60 docs(handoff): director codex idle
```

Director2 seat status after the verify-request commit:

```text
HEAD aa6f00f9 coord(verify): request lipsync costkey Lane V
vs origin/main: 84 ahead, 0 behind
cursor: 2026-06-15T11:26:36Z
UNREAD: 0
```

## Mailbox Processed

Consumed/read during this pass:

- `2026-06-15T11-01-23Z-coordinator-to-all-coordination.md` - assigned
  director2 as Pair-B implementation lead for remaining active Wave-2 rows,
  starting with no-lock `lipsync-postproc-costkey`.
- `2026-06-15T11-23-24Z-director-to-all-coordination.md` - Pair-A product-oracle
  identity guidance; read directly.
- `2026-06-15T11-26-36Z-operator-to-all-status.md` - Pair-A operator ready;
  no Pair-A Lane V trigger.
- Final handoff sweep consumed the peer/coordinator wrap events that landed
  while this handoff was being written:
  `2026-06-15T11-32-21Z-director-to-all-status.md`,
  `2026-06-15T11-32-23Z-operator2-to-all-status.md`,
  `2026-06-15T11-32-27Z-coordinator-to-all-coordination.md`, and this seat's
  own `2026-06-15T11-33-22Z-director2-to-all-status.md`.

Cursor file is committed at:

```text
coordination/mailbox/seen/director2.txt -> 2026-06-15T11:33:22Z
```

The first consume attempts hit sandboxed `.git/index.lock` writes after updating
the cursor file. Escalated retry plus explicit path staging repaired the cursor;
`scripts/ci_smoke.py` no longer reports the cursor-orphan advisory.
The final consume reported:

```text
cursor director2: 2026-06-15T11:26:36Z -> 2026-06-15T11:33:22Z; unread now: 0
```

## Work Landed

Implementation commit:

```text
aeb1a2b7 fix(lipsync): price postprocess cost key
```

Scope:

- `cinema/shots/controller.py` adds `_lipsync_cost_api_key()` and uses it in both
  the motion F1b lip-sync cost record and the postprocess `lip_sync` correction.
- Postprocess corrections now record `LIPSYNC_<engine>` instead of raw cascade
  engine names such as `syncSoV3`.
- Missing cascade engine metadata now falls back to `LIPSYNC_DEFAULT`.
- `tests/unit/test_postprocess_audio_propagation.py` adds a live
  `apply_correction("lip_sync")` regression with a real `CostTracker`.
- `tests/unit/test_discovery_cost_xfail.py` removes the obsolete strict xfail
  that directly called `record_api_call("syncsov3")`; that pin was mis-shaped
  because it did not exercise the controller call site.
- `docs/REMEDIATION-INVENTORY.md` now points the row's executable selector at
  the live regression. Status remains `open` pending operator2 Lane V and
  coordinator reconciliation.
- `ARCHITECTURE.md` controller LOC and one doc anchor were refreshed after the
  touched-file line shift.

Verify-request commit:

```text
aa6f00f9 coord(verify): request lipsync costkey Lane V
```

Event:

```text
coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md
```

Operator2 remains the Pair-B verifier. Do not mark the row verified until an
operator2 `verification-report` GO lands.

## Executed Evidence

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost -q
1 passed in 1.57s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py tests/unit/test_cost_tracker.py -q
95 passed, 2 warnings in 2.96s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK with existing advisory warnings only.
```

Wave gate remains unmet, but the row-specific effect is visible:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 16, 'open': 14}
executable selectors: includes tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost
pytest failures dropped from 17 to 16 after replacing the old mis-shaped cost xfail
remaining blockers: spent-usd-reset-on-resume no-selector, perf-phase-no-gate no-selector, missing product-oracle artifact, plus other open row pins
```

## Next Action

Wait for operator2 Lane V on `aeb1a2b7`.

Suggested operator2 checks are already in the verify-request:

- actual diff only;
- non-vacuity of the `apply_correction("lip_sync")` regression;
- default engine maps to `LIPSYNC_DEFAULT`;
- wave gate includes the new selector and no longer relies on the old direct
  `tests/unit/test_discovery_cost_xfail.py` pin for this row.

After operator2 GO, coordinator should reconcile `lipsync-postproc-costkey`.
Then director2 can continue the coordinator-recommended no-lock order:

1. `download-urllib-notimeout` in `phase_c_ffmpeg.py`;
2. checkpoint cluster (`ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
   `ckpt-projectid-nocrosscheck`);
3. design/blocker rows (`spent-usd-reset-on-resume`, `perf-phase-no-gate`);
4. lower-priority `lipsync-precheck-cascade-gap`.

## Dirty State Warning

The shared worktree still contains unrelated staged/unstaged changes from other
seats and transplant/protocol work. This pass used explicit pathspec commits.
Next seat should avoid broad staging, broad reset, or cleanup of files not
owned by its current task.

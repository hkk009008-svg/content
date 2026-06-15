# Handoff - director2 Pair-B - 2026-06-15 charmgr GO, B2 lock-gated

Seat: director2, Pair-B director. User requested one more cycle, then stop and
create a handoff. No production code edited in this cycle. No push performed.

## Current durable HEAD

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
ecaf9d69 coord(cursor): operator2 consume own charmgr go
634fc2c0 verify(pairB): go charmgr cost follow-up
7e762f4f coord(verify): request charmgr follow-up Lane V
8226e308 fix(money): preserve charmgr budget fail-closed
66a5e015 coord(cursor): operator2 consume charmgr fail routing
```

Branch status from director2 seat-status:

```text
HEAD ecaf9d69
vs origin/main: 62 ahead, 0 behind
```

## Mailbox consumed this cycle

Director2 had 1 unread event at startup:

```text
2026-06-15T08-17-43Z-operator2-to-all-verification-report.md
```

I consumed it; `coordination/mailbox/seen/director2.txt` is now advanced to:

```text
2026-06-15T08:17:43Z
```

The first consume attempt updated the cursor file but failed while staging the
per-seat index (`.git/index-codex-director2.lock` sandbox write). The escalated
retry reported:

```text
cursor director2: already at 2026-06-15T08:17:43Z (no-op)
```

## Binding event: charmgr is GO

Operator2 report:

```text
coordination/mailbox/sent/2026-06-15T08-17-43Z-operator2-to-all-verification-report.md
```

Verdict: GO for `charmgr-cost-fresh-instance` follow-up Lane V on `8226e30`.
Operator2 says coordinator may reconcile the row to `verified`; no
cross-cutting lock release applies.

Important report boundaries:

- The scoped row is visibility / gate-source repair for CharacterManager spend.
- The prior malformed-budget FAIL edge is repaired.
- No pre-spend `would_exceed()` check was added or verified here; that remains
  separate open risk (`perf-phase-no-gate`).

## Dirty state to preserve

Do not broad-stage. The worktree has multi-seat dirt.

Relevant dirty files after this cycle:

```text
$ env -u GIT_INDEX_FILE git status --short docs/REMEDIATION-INVENTORY.md coordination/mailbox/seen/director2.txt
MM coordination/mailbox/seen/director2.txt
MM docs/REMEDIATION-INVENTORY.md
```

`docs/REMEDIATION-INVENTORY.md` already has a working-tree update marking
`charmgr-cost-fresh-instance` verified on operator2 GO. I did not author that
inventory edit. Treat it as active coordinator/deputy reconciliation state, not
as a director2 production edit.

The cursor file change is from this director2 consume.

## Wave gate snapshot

Fresh gate command after the inventory working-tree update:

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 15, 'open': 15}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
...
18 failed, 43 passed, 1 warning
```

The live red executable pins include `lipsync-veto`:

```text
tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync
```

## Next Pair-B implementation row

Per `logs/discovery-wf_f57f0d89-bc2.json`, the execution order after
`B6-money-fresh-instance` is:

```text
B2-lipsync-veto
```

Inventory row:

```text
docs/REMEDIATION-INVENTORY.md:43
| lipsync-veto | gates | cinema/auto_approve.py:502 | MAJOR | ... | B | W2-auto_approve.py.lock | 2 | open |
```

Lock state:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Do not edit `cinema/auto_approve.py` until the cross-cutting lock is claimed
first. The required lock is:

```text
coordination/bin/claim-lock W2 auto_approve.py director2 lipsync-veto
```

That script commits and pushes the lock. Because the branch is 62 commits ahead
and push is user-gated, do not run it without explicit user/coordinator push
authorization.

## B2 read-only scoping already done

Skill context loaded: `ai-video-gen`, relevant `post-processing.md`.

Current defect shape:

- `cinema/shots/controller.py:2452` writes
  `variant["metadata"]["dialogue_audio_in_clip"] = True` after a successful
  manual `lip_sync` correction.
- `cinema_pipeline.py:734` already treats `dialogue_audio_in_clip` like embedded
  audio during assembly.
- `cinema/auto_approve.py:485` `_best_take_lipsync()` only credits
  `lipsync_score` and `audio_embedded`, so the final gate still sees the fixed
  postprocess take as 0.0 and vetoes it.

Pin evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync -q
x                                                                        [100%]
1 xfailed in 0.03s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync --runxfail -q --tb=short
FAILED ... assert 0.0 >= 0.8
```

Recommended B2 fix direction after lock:

- Author R-BRIEF first.
- Rule #12 target: `dialogue_audio_in_clip` production write sites in
  `cinema/shots/controller.py`.
- Rule #13 siblings: preserve current behavior for `lipsync_score`,
  `audio_embedded`, unverified dialogue, and non-dialogue N/A pass.
- Likely small direct director2 implementation: credit
  `dialogue_audio_in_clip` as a successful embedded-dialogue pass in
  `_best_take_lipsync()`, then convert the strict xfail to a live regression.

## Stop state

I am stopping here by user request. I did not claim the B2 lock, did not edit
production code, and did not push. Next seat should first run seat status and
mailbox audit because operator2/coordinator are online and the tree is moving.

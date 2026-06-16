# Operator2 -> All: verification-report GO for lipsync-precheck-cascade-gap

**When:** 2026-06-15T20:32:31Z
**From:** operator2
**To:** all
**Type:** verification-report
**Verdict:** GO

## Scope

Lane V target from director2:

- implementation: `d93c9d63 fix(lipsync): precheck mandatory overlay spend`
- verify request: `c2572b03 coord(verify): request lipsync precheck Lane V`
- row: `lipsync-precheck-cascade-gap`

Operator2 consumed the verify request
`coordination/mailbox/sent/2026-06-15T20-27-29Z-director2-to-operator2-verify-request.md`
and folded the cursor into this report commit.

## Findings

No blocking findings.

## Verification

Read the actual diff:

```text
$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline d93c9d63 c2572b03 --
d93c9d63 fix(lipsync): precheck mandatory overlay spend
M       cinema/shots/controller.py
M       coordination/mailbox/seen/director2.txt
A       docs/R-BRIEF-lipsync-precheck-cascade-gap-2026-06-15.md
M       tests/unit/test_budget_pre_spend_gate.py
M       tests/unit/test_dialogue_routing.py
M       tests/unit/test_f1b_dialogue_lipsync.py
c2572b03 coord(verify): request lipsync precheck Lane V
A       coordination/mailbox/sent/2026-06-15T20-27-29Z-director2-to-operator2-verify-request.md
```

Implementation check:

- `cinema/shots/controller.py:1723-1734` computes
  `API_COST_USD[target_api]` plus `LIPSYNC_DEFAULT` only when the shot has
  dialogue and is not a native-audio take.
- The refusal is before `generate_ai_video(...)` at
  `cinema/shots/controller.py:1832` and before the F1b lip-sync block at
  `cinema/shots/controller.py:1883`.
- The ai-video-gen lip-sync prior matches this route: existing-video dialogue
  overlay is structurally a post-processing lip-sync pass, while native-audio
  dialogue should not be charged as a separate overlay.

Focused tests:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate -q
....                                                                     [100%]
4 passed in 2.00s
```

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring tests/unit/test_dialogue_routing.py tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate -q
................................                                         [100%]
32 passed in 1.92s
```

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness tests/unit/test_cost_tracker.py::TestBudgetGate tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate -q
...............................                                          [100%]
31 passed in 1.92s
```

Additional native-audio budget probe:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
...
native probe OK: estimated=0.30; video_called=True; lipsync_calls=0; audio_embedded=True
PY
```

This probe set `spent_usd=0.26` and `budget_usd=0.60`, so `VEO_NATIVE` alone
fit but `VEO_NATIVE + LIPSYNC_DEFAULT` would exceed. Native mode still used only
the `VEO_NATIVE` estimate, called video generation, skipped lip-sync, and tagged
the take `audio_embedded=True`.

Scope:

```text
$ env -u GIT_INDEX_FILE git diff --name-status c2338cb0..d93c9d63 --
M       cinema/shots/controller.py
M       coordination/mailbox/seen/director2.txt
A       docs/R-BRIEF-lipsync-precheck-cascade-gap-2026-06-15.md
M       tests/unit/test_budget_pre_spend_gate.py
M       tests/unit/test_dialogue_routing.py
M       tests/unit/test_f1b_dialogue_lipsync.py

$ env -u GIT_INDEX_FILE git diff --name-status c2338cb0..d93c9d63 -- cinema/auto_approve.py web_server.py
# no output
```

Ceremony and gate evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

`ci_smoke.py` still reports existing advisories: a doc-anchor drift for
`docs/PROGRAM-MANUAL.md` `diagnose_clip`, and the known unknown-kind advisory
for `2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md`.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 23, 'open': 7}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

## Verdict

GO. The routed fix is non-vacuous, covers the overlay dialogue pre-spend gap,
preserves non-dialogue pre-dispatch budget refusal, and does not over-block
native-audio dialogue with a separate lip-sync estimate. Scope stayed within
the routed files and did not touch `cinema/auto_approve.py` or `web_server.py`.

Residuals remain coordinator-owned: inventory reconciliation for this row after
GO, product-oracle artifact absence, and unrelated Wave 2 red rows.

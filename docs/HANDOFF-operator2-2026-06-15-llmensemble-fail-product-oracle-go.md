# HANDOFF - Operator2 (Pair-B), 2026-06-15 - LLMEnsemble FAIL; product-oracle GO

READ FIRST AS OPERATOR2. Trust git and mailbox artifacts over this prose if
they diverge.

## State At Wrap

- Write-start timestamp: `2026-06-15T06:15:42Z`.
- Current HEAD at write-start:
  `bca5db6 verify(pairB): report llmensemble fail product oracle go`.
- Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -10
bca5db6 verify(pairB): report llmensemble fail product oracle go
90c5e1a coord(verify): request identity nan arc Lane V
61d4965 fix(identity): regenerate on nonfinite arc score
d540c00 docs(handoff): operator pairA coherence wrap
bf66cd4 docs(handoff): operator2 lanev queue
02f8332 coord(cursor): director2 consume operator2 handoff
806923a docs(handoff): director2 pairB lanev queue
8fa43c8 docs(handoff): coordinator wave2 state
f104e03 coord(director): restore director2 unread handoff
cb9d433 coord(director): hand off Pair-A wave2 state
```

- Operator2 cursor is consumed through `2026-06-15T06:12:32Z`.
- Live unread count at wrap-start: `0` per
  `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2`.
- Branch state at wrap-start: `main`, `22 ahead, 0 behind`.
- Wave 2 remains `UNMET`, counts `{'fixed': 3, 'open': 18, 'verified': 9}`.
- Wave blockers reported at wrap-start:
  - `spent-usd-reset-on-resume`: no executable xfail-pin selector.
  - `perf-phase-no-gate`: no executable xfail-pin selector.
  - missing committed `logs/product-oracle-*.json` product-oracle artifact.
  - executable pin run still red: `20 failed, 39 passed, 1 warning`.

No push performed.

## What Operator2 Did

Committed:

```text
bca5db6 verify(pairB): report llmensemble fail product oracle go
```

Mailbox report:
`coordination/mailbox/sent/2026-06-15T06-12-32Z-operator2-to-all-verification-report.md`.

### `4b81b31 fix(money): thread llm ensemble costs`

Verdict: **FAIL** for `llmensemble-cost-uncounted`.

Two cold reviewers agreed FAIL:
- money-gate-reviewer `019ec9e2-f22d-7171-9bc9-f8337c8ac83b`.
- lane-v-verifier `019ec9e3-16c6-7341-9649-3d7a920238db`.

Local operator2 reproduction: mocked two-candidate `competitive_generate()` with
a shared `CostTracker` returned content but left `spent_usd=0.0` and emitted two
warnings:

```text
[LLMEnsemble] Failed to record LLM usage for 'gpt-4o': SQLite objects created in a thread can only be used in that same thread...
[LLMEnsemble] Failed to record LLM usage for 'o4-mini': SQLite objects created in a thread can only be used in that same thread...
```

Blocking reason: candidates run in `llm/ensemble.py:219`
`ThreadPoolExecutor`; `_log_llm_usage()` calls the shared
`CostTracker.log_llm()` from worker threads, but `cost_tracker.py:228` creates a
default thread-bound SQLite connection. The exception is caught at
`llm/ensemble.py:171`, so the paid call succeeds while the budget accumulator
stays stale.

R-VERIFY-TIER note: no new overlapping pin was added because the root cause is
already the open Wave-2 row `cost-conn-crossthread-drop` with strict xfail pin
`tests/unit/test_cost_conn_crossthread_xfail.py`. Operator2 verified:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py -q
1 xfailed in 0.03s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py --runxfail -q --tb=short
FAILED tests/unit/test_cost_conn_crossthread_xfail.py::test_cross_thread_record_api_call_succeeds
```

Positive slices still passed but were insufficient for GO:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q
3 passed in 0.13s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_prompt_optimizer.py tests/unit/test_ensemble_judge_parse.py tests/unit/test_llm_caching.py tests/unit/test_cost_tracker.py tests/unit/test_web_research_uncounted_xfail.py -q
111 passed, 2 warnings in 0.93s
```

Next director2 repair should either make the shared `CostTracker` cross-thread
safe or move/serialize ensemble cost logging onto a safe writer path, then add
path-specific threaded candidate coverage before asking operator2 for a fresh GO.

### `c8c0d40 fix(campaign): read product oracle artifacts from HEAD`

Verdict: **GO** for the product-oracle gate repair after operator2 FAIL
`3b21d74`.

Cold reviewer `019ec9e3-390f-7241-9c07-efa8dba9aa4a` returned GO.

Operator2 evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q
13 passed in 0.18s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact tests/unit/test_wave_gate_check.py::test_wave2_reads_committed_product_oracle_artifact_not_worktree -q
2 passed in 0.25s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact --runxfail -q --tb=short
1 passed in 0.14s
```

Scope verified:
- `scripts/wave_gate_check.py:118` lists committed `logs/` entries from `HEAD`.
- `scripts/wave_gate_check.py:147` filters `logs/product-oracle-*.json` in Python.
- `scripts/wave_gate_check.py:177` / `:184` reads repo-owned artifact content via
  `git show HEAD:<path>`.
- `tests/unit/test_wave_gate_check.py:245` proves dirty worktree artifact content
  is ignored in favor of committed content.

Residual note: this GO verifies gate enforcement only. The real Wave-2
`logs/product-oracle-*.json` R-MEASURE artifact is still owed.

## Incoming / Relevant Events

- `90c5e1a coord(verify): request identity nan arc Lane V` added
  `coordination/mailbox/sent/2026-06-15T06-11-17Z-director-to-operator-verify-request.md`.
  It is Pair-A and routed to `operator`, not `operator2`.
- Operator2 has no unread mailbox events at wrap-start.

## Still Owed

- director2: repair `llmensemble-cost-uncounted` after operator2 FAIL in
  `bca5db6`.
- operator2: after director2 lands a repair, run fresh Lane V on that repair.
- coordinator: can reconcile product-oracle gate repair (`c8c0d40`) as GO if
  policy allows, but Wave 2 still cannot close without the real product-oracle
  artifact and remaining blockers.
- Pair-B/future director2: create the committed Wave-2
  `logs/product-oracle-*.json` R-MEASURE artifact with finite ArcFace and
  lip-sync metrics.
- Wave 2 remains red from open rows, the two no-selector blockers, missing
  product-oracle artifact, and executable pin failures.

## Dirty Worktree Caveat

At handoff authoring, `env -u GIT_INDEX_FILE git status --short` showed
unrelated concurrent/protocol changes including:

```text
 M .agents/skills/ai-video-gen/SKILL.md
 M .agents/skills/comfyui-mastery/SKILL.md
 M .claude/settings.json
 M AGENTS.md
 M cinema_pipeline.py
 M coordination/README.md
 M coordination/mailbox/seen/director2.txt
 M docs/REMEDIATION-INVENTORY.md
 M docs/protocol/agents/core.md
 M docs/templates/agents/implementer.md
 M scripts/status.py
 M tests/unit/test_postprocess_audio_siblings_xfail.py
 M tests/unit/test_status.py
```

plus untracked Codex/protocol transplant artifacts, two legacy
`verify-readiness` mailbox files, `docs/superpowers/briefs/2026-06-15-perf-take-meta.md`,
and continuation-readiness tests/scripts. I did not touch or revert these. Continue
using explicit pathspecs.

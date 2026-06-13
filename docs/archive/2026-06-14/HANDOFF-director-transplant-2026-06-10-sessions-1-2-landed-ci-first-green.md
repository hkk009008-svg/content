# Director transplant handoff — 2026-06-10 (PM): roadmap Sessions 1+2 LANDED — CI's first green pytest in 290 runs, live both-direction acceptance; P1-3 observability on the canonical path; next = Session 3 (P1-1 spec)

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-10-roadmap-arc-landed-strategic-review-successor.md`
(its ⭐#1 — Session 1 of STRATEGIC_REVIEW-2026-06-10 — is discharged, plus
Session 2 on top).

## Ground truth (verified this wrap)

- **HEAD == `5114574`** on `main` (operator's AST-guard tightening); **local
  ahead 11 of `origin/main` `4d10ccd`** (push USER-gated). The unpushed 11 =
  my Session-2 arc (`8594a52`, `828ece9`, 2 coords) + operator's bench
  (`86a3ba9`, `2d58fca`, `8a8e8a0`, `587838c`, `f85a6e8`, `9e795f2`,
  `5114574`). Everything through `4d10ccd` IS pushed (user said "push"
  mid-session; live CI acceptance recorded — below).
- Suite at wrap: **2015 passed / 0 failed** (`env -u GIT_INDEX_FILE
  .venv/bin/pytest tests/unit/ -q` → `2015 passed, 2 warnings, 10 subtests
  passed in 54.51s`). `ci_smoke` OK (now includes the operator's P2-2
  PROGRAM-MANUAL WARN — advisory, never gates); doc verifier "no drift";
  0 skip-worktree bits.
- **Mailbox: 0 unread** (cursor `10:48:08Z`; the only later event is my own
  10:56:37Z dispositions reply, consumed by operator `3da9358`).
- **Operator: LIVE all session**, queue FULLY DISCHARGED at `5114574` per
  their presence — re-check presence before assuming anything. Pod still
  DOWN (no pod work this session).

## Headline: CI actually tests now — proven in both directions, live

- **Green:** run `27267540679` on main — all 3 jobs success; pytest
  `1975 passed, 7 skipped ... in 27.41s` — **the first green pytest job in
  290 runs** (0-for-289 since 2026-05-24).
- **Red:** run `27267553553` on PR #12 (`ci-red-proof`, built via git
  plumbing, never merged, closed+deleted after) — pytest failed on exactly
  the planted test while smoke+tsc stayed green.
- Live baseline truth: ubuntu shows a few more environment-conditional
  self-skips than local; current count single-sourced in ARCHITECTURE.md §16
  (ci.yml comments stopped carrying counts after drifting twice in a day).

## What director did this session (chronological)

1. **Session 1, P0-1 (`0326f24`)** — `[tool.pytest.ini_options]
   pythonpath=["."]` (bare `pytest` couldn't import root modules at
   collection; the autouse fixture ran post-collection) + all four action
   majors bumped to Node-24 runtimes (release notes verified via gh api)
   ahead of the 2026-06-16 forcing.
2. **Session 1, P0-2 (`8a117cb`)** — falsy `budget_usd` coerced to None in
   `CostTracker.__init__` (default projects paused BUDGET_EXCEEDED after
   their FIRST motion cost record); `would_exceed` WIRED as the pre-spend
   gate in `generate_motion_take` (**ADR-022** records wire-vs-delete). TDD.
3. **Adversarial self-review `wf_4e0e2a6f`** (41 agents): 12/12 findings
   confirmed, incl. **CRITICAL C-1** — my P0-1 "green" was masked by local
   `.env`; a keyless runner still failed 49F+1E (`llm/ensemble.py:107`
   constructs `openai.OpenAI()` at `__init__`; gemini/anthropic key presence
   flips test-visible behavior). Same masking class as NF-1, one level
   deeper. Operator Lane V converged independently (their control: same
   clone + `.env` copied in → green).
4. **Dispositions (`9dcbb0c`, `d252900`)** — F2b storyboard batch pre-spend
   gate (my commit's "one check covers all paths" was WRONG; ADR-022 amended
   in place, marked); motion phase ABORTS on structured
   `error_kind:"budget"` refusal (`check_pause()` has zero production call
   sites — the pause flag halts nothing; abort is what stops the phase);
   dummy `OPENAI/GEMINI/ANTHROPIC_API_KEY` on the pytest job (CI-shape sim:
   keyless 49F+1E → 2 dummies 6F → 3 dummies 0F).
5. **Push + acceptance (`4d10ccd`)** — user said "push"; pushed main +
   ci-red-proof, opened+closed PR #12, watched both live runs, baselines
   corrected to live-run truth.
6. **Session 2, P1-3 (`8594a52`)** — SSE whitelist LIFTED
   (`make_progress_callback` passes producer extras through; lean-ness +
   JSON-serializability guard — one bad value would kill the whole stream at
   `/stream`'s json.dumps); `engine=target_api` on MOTION events
   (deliberately NOT on MOTION_READY — cascade winner may differ); NF-4
   closed (dialogue takes render BOTH `via X` video cascade and
   `lipsync via Y` overlay badges in ReviewStage/TakeStrip/Monitor);
   BudgetHaltBanner with structured spent/budget. TDD 6 RED→GREEN.
7. **Converged-review dispositions (`828ece9`)** — my `wf_9877b1d1` (5C/1R)
   and operator's cold Lane V both found the SAME root IMPORTANT: every new
   surface mounted only in setup mode, which UNMOUNTS when a run starts —
   canonical path stayed blind. Fixed: halt state hoisted to App.tsx,
   banner in BOTH PipelineLayout and EditorialShell; engine in pipeline
   mode via GenerationPanel event-log lines (MOTION carries percent=-1 so
   the progress block hides during exactly that wait); MOTION_DONE-on-abort
   suppressed (now MOTION_HALTED@72; no FE consumer keys on MOTION_DONE —
   grep-verified; **honest test gap**: the branch lives in the generate()
   monolith, no unit harness — P3-1 extraction is the fix); guard hardened
   (isinstance-before-`==`, RecursionError, `allow_nan=False`; TDD);
   `useSSE.start()` resets `latest` (stale cross-run VIA fragment).

## ⭐ #1 PICKUP

1. **Get the 11 commits pushed** (USER-gated — ask, then
   `git push origin <verified-sha>:main`) and confirm the CI run on the new
   HEAD goes green (it contains FE changes; tsc+vite are in the workflow).
2. **Session 3 of the review roadmap: P1-1 multi-character
   generation-identity SPEC** (design doc; mechanisms a/b/c costed —
   multi-image Kontext keyframes / per-char LoRA stacking on production
   tier / regional PuLID on max tier — pod-dependence explicit; recommend
   (b) first where LoRAs exist). This is the biggest capability gap:
   validation catches second-character drift (413317e), nothing PREVENTS it.

## Director backlog (recorded, not started)

- **Budget-coverage slice or ADR-022 exemption list** (operator K8 map):
  driving-video spends neither tracked nor gated; postproc lipsync tracked,
  ungated; F1b overlay unpriced in the gate's estimate; keyframe spend
  tracked, ungated; storyboard finalize-retry path doesn't key on
  `error_kind`.
- **LLMEnsemble hermeticity refactor** (lazy/injectable construction) — the
  honest fix behind the CI dummy keys.
- **`check_pause()` wiring** into phase loops (pause is currently a flag
  nothing blocks on; the budget abort sidesteps it for that one path).
- SSE bridge is no longer an information-flow boundary (operator M5 design
  note): exposure decisions live at emit sites now — keep in mind when
  adding producer kwargs.

## Operator lane (do NOT pick up as director)

Their queue was FULLY DISCHARGED at `5114574` (usage-cite acceptance rule →
manual residue clear → P2-2 WARN in ci_smoke → AST-guard 4-rule
tightening). Their next: presumably Lane V on `828ece9`+coords (queued per
their 10:48:08Z event) and a fresh wrap. Nothing owed cross-seat from my
side; their backlog items live in their handoffs.

## Operational notes (new this session — on top of predecessor's)

- **`git commit --amend` takes NO pathspec** — it commits the whole index.
  A message-only amend swept the D-a stale-index phantom deletions (peer's
  files briefly deleted from the tree); caught in seconds, repaired via
  `reset --soft <good>` + `read-tree HEAD` + re-amend. NEVER amend while
  status shows phantoms. Memory updated
  (`feedback_shared_index_sweep_use_pathspec`).
- **zsh in this harness:** backticks inside double-quoted `-m` strings are
  command substitution (a commit message lost a word); unquoted `===`
  tokens glob-fail and abort `&&` chains; `set -- $var` does NOT word-split.
  Use single quotes for inline code in messages; avoid `=`-runs in echoes.
- **Peer-WIP suite attribution:** when their presence/event announces WIP
  files, run `--ignore=<their file>` and `git status` those paths BEFORE
  attributing failures (worked verbatim this session: their 5 TDD RED tests
  in `test_check_doc_claims.py`).
- Presence files are hook-stamped after EVERY tool call — Read→Edit always
  races it; write presence via Bash heredoc.
- `gh api 'repos/<owner>/content/actions/runs?...'` + `gh run watch <id>
  --exit-status` (background) for CI forensics; `ruby -ryaml` is the only
  local YAML validator (no PyYAML in the venv).

*Last verified: 2026-06-10 PM (this wrap; suite/smoke/verifier outputs above).*

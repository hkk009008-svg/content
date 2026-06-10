# Director transplant handoff — 2026-06-10: roadmap arc LANDED+PUSHED + STRATEGIC_REVIEW-2026-06-10 successor written; next cycle = its 6-session roadmap

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-09-supir-settled-talkinghead-delivered.md`
(every open item from it is now discharged or formally re-prioritized into the
new strategic review).

## Ground truth (verified this wrap)

- **HEAD == `b550dcf`** on `main`; **local ahead 5 of `origin/main` `4b7135c`**
  (push USER-gated): operator's `61c7892`/`1f014c0`/`2b2da60`/`2ccb2a4` + my
  `b550dcf` (strategic review). Everything through `4b7135c` IS pushed (user
  said "push" mid-session; FF `a576ca0..4b7135c` verified before+after).
- Suite at wrap: **1974 passed / 0 failed** at `b550dcf`
  (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q` →
  `1974 passed, 2 warnings, 10 subtests passed in 52.75s`). `ci_smoke` OK;
  doc verifier "no drift"; tree clean; 0 skip-worktree bits.
- **Mailbox: 0 unread after this wrap's cursor advance to `00:36:30Z`** (both
  operator events read + dispositioned in-session; consumed in the wrap
  commit).
- **Pod: DOWN** (gateway 502; user terminated). **Operator: was LIVE in
  parallel all session** (pid 12694) — re-check presence before assuming
  anything.

## What director did this session (single 2026-06-10 session, both arcs)

1. **Session-start verification of the user's morning merge** — feat→main
   `91917df` checked out GREEN (suite 1948/0 at `a576ca0`, smoke OK, verifier
   clean); origin/feat branch deleted; doc-split (CLAUDE/AGENTS routers) live.
2. **`b9d12d2`** — closed ALL outstanding operator dispositions: V-MINOR-2
   docstring, FE slider min 0.2→0.4, `project.ts` comment, + Rule #13 sibling
   find (`supir_steps` FE preset/fallback 50→40 — the Maximum Fidelity preset
   was actively writing 50 over the A/B-validated 40). Operator Lane V ✅ SAFE.
3. **`44d1737`** — FAL timeout hardening: 22 `fal_client.subscribe` sites / 8
   files bounded via NEW `cinema/fal_limits.py` (VIDEO 600 / TALKING_HEAD 1800
   / IMAGE 180) + Seedance poll `timeout=30` with per-iteration retry + AST
   guard test (`tests/unit/test_fal_subscribe_timeouts.py`). The talking-head
   class exists because my ultracode review (`wf_e0d1765b`) adversarially
   CONFIRMED 600s would cancel legit long-form jobs (~40× realtime measured in
   `logs/_lipsync_gen_test.log`). Operator Lane V ✅ SAFE; their 4 MINORs
   closed `61c7892`.
4. **`413317e`** — multi-char identity gate: extracted
   `_validate_take_identity` from `_finalize_motion_take`, un-sliced
   `[chars_in_frame[0]]` → full list, per-char metadata
   (`identity_per_char`/`identity_all_matched`); TDD 11 tests. Lane V ✅ SAFE.
5. **`4b7135c`** — ADR-021: aspect-backstop probe fail-open decision recorded
   (layered-defense rationale; bounded precedent).
6. **PUSHED `a576ca0..4b7135c`** on user "push".
7. **`b550dcf` — `docs/STRATEGIC_REVIEW-2026-06-10.md`** (user "strategic
   review successor"): 05-24 ledger audited item-by-item via a 9-lane parallel
   evidence workflow (`wf_5ef8e23c-85b`; 10th lane hand-completed), every
   headline number re-verified by me at HEAD pre-commit. Routers
   (CLAUDE.md/AGENTS.md/README) repointed; README's false "All must pass" CI
   claim corrected. Ledger: 9 LANDED / 5 PARTIAL / 4 NOT_DONE / 1 REGRESSED.

## ⭐ #1 PICKUP — execute the new strategic review's roadmap, Session 1 first

`docs/STRATEGIC_REVIEW-2026-06-10.md` is the operative direction. Session 1
(P0, half a session, no pod, no user gate needed beyond commit/push):

- **P0-1 — make CI actually test.** The pytest job is **0-for-289 since
  2026-05-24** (collection dies: bare `pytest` + no path config +
  `tests/conftest.py` adds root inside an autouse fixture = too late; local
  `python -m pytest` masks it). Fix: root `conftest.py` OR
  `[tool.pytest.ini_options] pythonpath=["."]` OR `python -m pytest` in
  ci.yml. ALSO bump checkout@v4/setup-python@v5 (GitHub forces Node 24
  **2026-06-16** — six days). Acceptance: one green run on green code AND one
  red run on an intentionally broken branch.
- **P0-2 — budget zero-coercion defect (live bug).** Default
  `budget_limit_usd: 0` + `cinema/core.py` None-only guard + `is_over_budget`
  None-only check ⇒ default projects PAUSE with BUDGET_EXCEEDED after the
  first motion cost record. Repro:
  `CostTracker(db_path=':memory:', budget_usd=0.0)` + one `record_api_call`
  → `True`. Coerce falsy→None (one line) + regression test; decide
  `would_exceed` (zero production callers — wire it pre-spend or delete).

Then sessions 2–6 per the review (SSE whitelist/observability last-mile →
multi-char GENERATION identity spec → its first impl slice → print→logging
for phase_c_ffmpeg+lip_sync + silent-except honesty + NF-7 dead FAL-Hedra
attempt → assembly/ extraction + monolith ratchet + P2-4 ADR).

## USER-gated / waiting on user

- **Push** the 5 local commits (`4b7135c..b550dcf`).
- **P1-2 pod spend** — new-character onboarding to max-tier (pod-side LoRA
  training spike + no-PuLID over-cook mitigation) needs a pod session.

## Operator lane (do NOT pick up as director)

- AST-guard latent dodge vectors (assignment-alias receiver,
  `FAL_TIMEOUT_*`-named None) — design-first, theirs.
- Verifier residuals: 67+335 unbound anchors (`--list-unbound`), binder
  `Class.method` false-positive shape.
- P2-2 manual-gate cadence is a JOINT decision — my recommendation in the
  review: PROGRAM-MANUAL as WARN in ci_smoke + `--fix` on touch (it sits at
  **83 def-drifts** right now, re-drifted in ~2 days).

## Operational notes

🔑 `env -u GIT_INDEX_FILE` for pytest AND for `git add`+`git commit`
(pathspec). Peer LIVE → clear skip-worktree bits per-path only
(`git update-index --no-skip-worktree <your paths>`); solo → `read-tree
HEAD`. D-a-safe push = `git push origin <verified-sha>:main`. The presence
files are auto-stamped (`head_at_write`/`updated`) by the PostToolUse hook
`update-state.sh` — content stays agent-owned; a moving `head_at_write` in
your own presence file means THE PEER COMMITTED — `git log` before
attributing tree changes. Workflow evidence audits: agents must cite
command+output; re-run headline numbers yourself before publishing
(ADR-013). `gh api 'repos/hkk009008-svg/content/actions/runs?...'` works for
CI forensics.

*Last verified: 2026-06-10 (this wrap).*

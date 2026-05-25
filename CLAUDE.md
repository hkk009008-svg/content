<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (4309 symbols, 23541 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Content/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Content/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Content/clusters` | All functional areas |
| `gitnexus://repo/Content/processes` | All execution flows |
| `gitnexus://repo/Content/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# Session-start protocol (read me first)

**Truth lives in `ARCHITECTURE.md` at the repo root.** This file (CLAUDE.md)
is the *process layer* — GitNexus playbook, multi-task orchestration, session
discipline. `ARCHITECTURE.md` is the *truth layer* — verified facts about the
pipeline, with file:line references and a §15 smoke test. When they disagree
about facts, `ARCHITECTURE.md` wins.

Both files drift from the actual code between sessions. Before doing any
non-trivial work, verify against current source. If a claim is stale,
**fix the relevant file in the same change** that exposes the staleness —
don't let a wrong claim survive your session.

Concrete protocol at session start (≤2 minutes):

1. Run the §15 smoke block in `ARCHITECTURE.md`. If it fails, the doc is
   stale OR the working tree is broken — fix one or the other before
   proceeding with the user's task.
2. Skim `ARCHITECTURE.md` §2 component topology. Spot-check:
   - `ls cinema/ cinema/phases/ cinema/review/ cinema/shots/`
   - `wc -l cinema_pipeline.py web_server.py phase_c_ffmpeg.py`
3. `git log --oneline -20` — if any commit touched a module documented in
   `ARCHITECTURE.md` since it was last edited (the `*Last verified: ...*`
   timestamp at the file footer), re-read that section against the new code.
4. **If you find a stale claim:** edit `ARCHITECTURE.md` first, in the same
   commit (or a `docs:` prep commit right before) the user's task lands.
   The user has stated this as a standing requirement.

Trust the code; update the prose when it diverges.

# Repo doc map

| Need to | Read |
|---|---|
| Get oriented (purpose + quick start) | [README.md](README.md) |
| Understand the code (verified truth — what's where, what does what) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Run / configure / troubleshoot | [OPERATIONS.md](OPERATIONS.md) |
| See WHY the architecture is shaped this way (ADR log) | [DECISIONS.md](DECISIONS.md) |
| Current leadership critique + forward direction | [docs/STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md) |
| Execute a roadmap session (operator manual, why + how + acceptance) | [docs/HANDOFF-roadmap-2026-05-24.md](docs/HANDOFF-roadmap-2026-05-24.md) |
| Past handoffs (historical) | [docs/archive/](docs/archive/) |

Don't duplicate ARCHITECTURE.md content in this file. If you need to record
something load-bearing about how a subsystem works, find or add the
appropriate section in `ARCHITECTURE.md`. For decisions (with rationale),
append to `DECISIONS.md` — never edit prior entries.

# Verification discipline for factual claims

Codified 2026-05-24 after a director-level inventory error: STRATEGIC_REVIEW
and HANDOFF both claimed "only one unit test file" when there were 24. The
director wrote those docs from session memory of one scoped pytest run + an
anchored mental model, without ever running `ls tests/unit/`. Root cause:
session memory trusted over filesystem. See [DECISIONS.md ADR-013](DECISIONS.md).

The class of error is fully preventable. These three rules close it.

## Rule 1 — No inventory claim without verification output

Any factual claim in a doc, commit message, or code comment of the shape
**"X files," "Y functions," "Z tests," "N LOC," "present in <path>,"
"absent from <path>"** requires the producing command's output captured in
the same change.

- In docs: paste the command + its output in a code block under the claim,
  OR cite it explicitly (`verified via $ ls tests/unit/ | wc -l → 24`).
- In commit messages: include the command and result in the body.
- "Just trust me" is not acceptable. Cite or don't claim.

## Rule 2 — Scoped output stays scoped

A command scoped to one path produces output about that path only.
`pytest tests/unit/foo.py` gives you `foo.py`'s test result, NOT the unit
suite's. `grep X dir/file.py` covers `file.py`, NOT `dir/`. `ls one_file`
tells you about one file.

When you want a wider claim, **re-run at the wider scope.** Do not
generalize from a narrow command. The shell never lies about what it ran;
you can lie to yourself about what it covered.

## Rule 3 — Pre-commit trip-wire for strategic docs

Before committing any strategic-review, handoff, ARCHITECTURE.md, or any
other director-voice document, the author runs the verifying commands for
every factual claim and pastes the output (or a representative snippet) in
the commit message. If a verifying command would take >30 seconds, note
it explicitly: `verified via <command> on YYYY-MM-DD`.

Cost: seconds. Cost of skipping: wrong direction for the next operator
(the 24-vs-1 test error).

## When you cannot comply

If you genuinely cannot run the verifying command (no shell, no
filesystem, no internet), state the claim as **unverified** explicitly:
> I believe X based on session memory but did not run the verifying command.

This is honest and lets the next reader treat the claim as a hypothesis,
not a fact. **Never apply director-voice authority over an unverified
factual claim.** Authority and verification travel together.

## When does this apply?

| Yes — verify before stating | No — verify not required |
|---|---|
| "There are N test files" | "Tests live under tests/unit/" (no count) |
| "X function is unused" | "X function is referenced in the imports of Y" (your immediate context) |
| "Y file is N lines" | A general qualitative claim ("this is large", "this is well-tested") |
| "Z module has no callers" | A directional claim ("this could be deleted if zero callers") |
| Any specific count, file presence, function existence | Architectural reasoning, design rationale |

The rule is: **specific factual claims = verification required.**
Qualitative directional claims = use your judgment but flag uncertainty.

## When you change something

Beyond the GitNexus checks above:

- One commit per logical slice. Run the §15 smoke block in `ARCHITECTURE.md`
  before declaring a slice done.
- Don't combine concerns. A bug fix isn't a refactor isn't a feature.
- If your change touches a documented subsystem, update the relevant
  section in `ARCHITECTURE.md` in the same PR.
- **For work beyond a single slice (≥5 sub-tasks or ≥800 LOC of total
  change), don't implement in main context — orchestrate. See
  "Working a Multi-Task Plan" below.**

# Working a Multi-Task Plan

When the user points you at a written plan (e.g., `docs/superpowers/plans/*.md`)
with ≥5 sub-tasks, or you've drafted one yourself with comparable scope, you
ORCHESTRATE — you do not implement directly. Main context holds the plan,
TaskCreate state, and ~1-3k of summary per task; fresh subagents do the
reading, writing, and verification.

This is the mechanism that prevents quality degradation across long
(1M / 2M+ token) sessions: each subagent starts at ~0 tokens with a curated
self-contained prompt, returns a compact report, and disappears. Main context
grows linearly with the number of tasks, not with the volume of work.

## When to invoke

| Signal | Action |
|---|---|
| User references a plan file under `docs/superpowers/plans/` | Invoke `superpowers:subagent-driven-development` skill (subagents available here) |
| Plan has 5+ sub-tasks AND tasks are mostly independent | Same |
| Task is a single change OR tasks are tightly coupled | Stay in main context; the orchestration overhead isn't worth it |
| User is in an interactive exploration ("how does X work?") | Stay in main context; subagents hurt latency for Q&A |

## The per-task loop (sequential, never parallel)

For each task in the plan:

1. `TaskUpdate({taskId: N, status: "in_progress"})`
2. **Dispatch implementer** — `Agent({ subagent_type: "general-purpose", model: "sonnet", prompt: <curated, see template below> })`
3. Read the report. If status is `DONE_WITH_CONCERNS` / `BLOCKED` / `NEEDS_CONTEXT`, address the concern before reviewing.
4. **Dispatch spec compliance reviewer** — same subagent type. Reviewer reads the actual diff and compares to the spec line-by-line. Do NOT trust the implementer's self-report.
5. If spec issues → fix loop (see "Delegation heuristics" below) → re-review.
6. **Dispatch code quality reviewer** — `subagent_type: "superpowers:code-reviewer"`. Pass BASE_SHA, HEAD_SHA, what was implemented, plan reference.
7. If quality issues → fix loop → re-review.
8. `TaskUpdate({taskId: N, status: "completed"})` and move on.

After all tasks: dispatch a final cross-cutting reviewer with BASE_SHA = the
baseline commit and HEAD_SHA = current HEAD. Then invoke
`superpowers:finishing-a-development-branch`.

**Never dispatch multiple implementers in parallel** — they'd conflict on
files. Reviewers in parallel are fine but rarely needed.

## Delegation heuristics — Lane A / B / C

Three lanes for each unit of work. Match the lane to the task — wrong-lane
choices either waste tokens (lane B for trivial fixes) or burn main context
(lane A for big work that should have been delegated).

**Lane A — execute in main context (Edit / Bash directly):**
- File is **already in your context** AND change is ≤5 LOC
- Pure mechanical edit: rename, type alias, comment improvement, format fix
- A reviewer flagged a 1-2 line fix with clear instructions and you can see the surrounding code
- Test-data tweak (tighten a tolerance, swap a placeholder value)
- Final polish after a fresh subagent's commit you just reviewed

Costs: ~few hundred tokens. Risk: low — you can see what you're changing.

**Lane B — fresh implementer subagent:**
- Change touches ≥3 files OR a domain you haven't read yet
- ≥5 LOC of structural change (new function, new component, new module)
- Design judgment needed (naming, abstraction, layout choice)
- Multi-step task that benefits from fresh-eyes context
- Anything where the implementer needs to discover state you don't yet have

Costs: ~40-60k tokens in the subagent's context, ~1-3k in yours.
Risk: low if the prompt is well-formed; high if it's "implement task X" with no context.

**Lane C — Explore / grep subagent (read-only survey):**
- "Where is X defined?" / "Which files reference Y?" — open-ended search
- Codebase exploration before deciding how to dispatch lane B
- Verifying a reviewer claim before acting on it

Costs: ~10-30k tokens. No write actions. Use when you need findings, not a code change.

**Decision tree:**
1. Is this a 1-5 line mechanical change in a file you already understand? → **Lane A**
2. Is this open-ended search across multiple files with no code change? → **Lane C**
3. Everything else → **Lane B**
4. Special case: if a reviewer's claim contradicts what you remember about upstream behavior, do a quick **Lane C survey** (or single targeted `grep`/`Read`) before fixing. The reviewer may be wrong.

## Implementer prompt template

A good implementer prompt is 80-150 lines and lets the subagent act
**cold** — they have no memory of this session. Skeleton:

```
You are implementing Task <ID> from `<plan path>` (Slice <S>, sub-slice <ID>).
Working dir: `<absolute>`. Branch: `<branch>`. Latest commit: `<sha>`.

## Task Description (verbatim from plan §X.Y)

<paste exact plan text — code blocks, tables, prose intact>

## Critical Context

- <what shipped before that this builds on>
- <what's coming after that depends on this>
- <any plan-vs-source divergences already discovered>

## Where Exactly

- File path: <absolute path>
- Insertion point: <line ~N> after <existing landmark>
- Surrounding pattern to match: <existing convention>

## Project conventions you MUST follow

Per `/Users/.../CLAUDE.md`:
1. Run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before editing existing symbols
2. Run `gitnexus_detect_changes()` after edits — confirm scope is what you expect
3. <task-specific gotcha>
4. If GitNexus MCP isn't reachable in your environment, fall back to grep + file inspection.
5. **Brief-pattern reference adherence.** When the brief says "mirror pattern X at file:line" or "use the existing _foo_-style endpoint," verify the FULL shape of X — signature, route path, scope parameters, error handling, lock guards — not just the called function. Brief-pattern references are implicit specs; silent deviations cascade. If the named helper doesn't exist (e.g., brief says `_mutate_shot` but the actual pattern uses `mutate_project`) or the wording is ambiguous, report the divergence in your status BEFORE implementing.
6. **pid-scope check on new endpoints.** When adding/touching an HTTP endpoint operating on a project-scoped resource (shots, scenes, locations, characters), verify the route takes `<pid>` explicitly. Do NOT scan via `list_projects()` to find a matching resource — IDs can collide across projects (e.g., `shot_id` follows `shot_{scene}_{i}` and matches across projects with matching scene/index layouts). Inspect at least one similar existing endpoint in the same file (e.g., `api_update_shot_prompt`) to confirm the route shape and scoping.

## Verification

1. `<command>` — expected: <result>
2. `<command>` — expected: <result>

## Before You Begin

If you have questions about:
- <ambiguity 1>
- <ambiguity 2>

**Ask before implementing.**

## Your Job

1-7. <numbered steps>

## When You're in Over Your Head

If <X happens>, report BLOCKED with what you tried.

## Report Format

- Status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- gitnexus_impact findings (callers, risk) or grep-fallback equivalent
- Files changed (paths only)
- Verification command output
- Commit SHA — `git commit` stdout's SHA is authoritative as of cycle-8 B-003 Option E (the post-commit hook no longer amends; STATE.md is gitignored and regenerated locally). Use `git log --oneline -3` to double-check if desired, but the SHA from commit stdout matches HEAD.
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — they'll burn context
discovering everything you already know, and the report will be vague.

## Hardening notes — provenance for the implementer-template additions

Items 5-6 in "Project conventions you MUST follow" and the Commit SHA
capture guidance in "Report Format" are hardened in from cycle-5 + cycle-6
failure modes. Carry them forward in future dispatches; if you trim the
template, do NOT trim these:

- **Item 5 (brief-pattern adherence)** — S13 implementer interpreted the
  brief's `_mutate_shot` pattern reference as "use `mutate_project`"
  without inheriting the route shape (pid-scoping, single-project
  mutation). Operator-seat's Lane V caught **F1 CRITICAL** post-commit:
  multi-project `shot_id` collision via the `list_projects()`-scan
  fallback. Fix shipped at `9e24323` (`fix(web): address S13 Lane V F1
  (CRITICAL) + F2 — pid-scoped reject route + monotonic-run dedup`). The
  brief named a non-existent helper, but the pattern's shape was still
  recoverable by inspecting the cited `api_update_shot_prompt`
  endpoint — that's the inspection step item 5 codifies.
- **Item 6 (pid-scope check)** — same F1 CRITICAL root cause, codified
  as a standing project convention so the next implementer catches the
  failure mode at design time, not via Lane V post-commit. Cost
  comparison: design-time check is ~1 grep; post-commit Lane V catch
  cost ~234k tokens (cycle-6 dispatch) + the F1 fix commit's
  developer-time. Front-load is cheap.
- **Commit SHA capture** — historical context: cycle-5 dispatch surfaced
  that implementer-reported SHAs were sometimes 1 commit stale because
  the project's `.claude/hooks/update-state.sh` post-commit hook AMENDED
  STATE.md into the just-made commit, changing its SHA. The Item 6
  Report-Format guidance directed implementers to capture from
  `git log --oneline -3` after the hook settled. **Resolved at cycle-8
  B-003 Option E** — hook no longer amends; STATE.md is gitignored;
  `git commit` stdout's SHA is now authoritative again. Guidance kept
  for the audit trail but the stale-by-one failure mode no longer exists.

## Spec reviewer prompt template

```
You are reviewing whether Task <N>'s implementation matches its spec.
**Do NOT trust the implementer's report** — read the actual code.

## What Was Requested

<paste exact requirements + numbered checklist of behaviors>

## What Implementer Claims

<list claims to be verified, including commit SHA>

## Your Job

1. `git show <SHA> -- <file>` — read the diff
2. Verify each requirement above
3. Look for: missing requirements, extra unrequested features, misunderstandings
4. <task-specific verification commands>

## Report

- ✅ Spec compliant
- ❌ Issues — list with file:line refs

Under <N> words.
```

## Code quality reviewer prompt template

```
Code quality review for Task <N> (commit `<SHA>`).

**WHAT_WAS_IMPLEMENTED:** <one-paragraph summary>
**PLAN_OR_REQUIREMENTS:** <reference to plan section>
**BASE_SHA:** `<sha>`
**HEAD_SHA:** `<sha>`
**DESCRIPTION:** <one-paragraph context>

**Working directory:** `<absolute>`
**Diff command:** `git diff <BASE>..<HEAD> -- <files>`

In addition to standard concerns, check:
- <task-specific concern 1> (e.g., concurrency if threading is involved)
- <task-specific concern 2> (e.g., public API stability if refactor)

Report: Strengths, Issues (Critical / Important / Minor), Assessment.
Under <N> words.
```

## Plan vs. source — the divergence rule

Plans sketch values that may be stale by execution time:
- Hex codes guessed before reading the actual mockup
- Function names not aligned with the file's naming convention
  (e.g., plan said `motion_floor_for`; file convention is `get_*` prefix)
- Type fields that don't exist yet
- Library APIs the plan author assumed exist

**Standing instruction to every implementer:** "The plan's sketch is
approximate. Where the plan matches the actual source / mockup / type / API,
use the plan's value. Where they differ, use the actual value and report
the divergence in your status report."

This is how to catch the plan being wrong without blocking on a re-spec.

## Commit discipline for reviewability

- **Baseline commit first.** If the working tree has uncommitted prep work
  foundational to the plan (new files, modified types, prep methods),
  commit it as `chore(baseline): ...` BEFORE dispatching any implementer.
  Otherwise each task's diff is polluted with prep noise.
- **One commit per task.** Don't amend across tasks. Reviewers need a clean
  BASE_SHA..HEAD_SHA range.
- **Fix commits are separate from feature commits.** When a reviewer finds
  an issue, the fix is its own commit on top — don't `--amend`. This
  preserves the audit trail showing what the reviewer caught.
- **Commit message convention:** `<type>(<scope>): <subject>` plus a
  short body explaining the *why* if non-obvious. End with the
  `Co-Authored-By: Claude Opus 4.7 (1M context)` trailer that Claude Code
  injects by default.

## Context hygiene (the long-session rule)

Quality degrades across very long contexts only if you let large bodies of
text accumulate. Mitigate by:

- **Don't `Read` files >500 lines in main context.** Dispatch a subagent
  with the specific question.
- **Don't re-`Read` files you just edited.** `Edit`/`Write` would have
  errored if the change failed. The harness tracks state.
- **Spot-check, don't re-verify.** If a reviewer says "spec compliant,"
  trust it. If something feels off, do a targeted single-file `Read` or
  `grep`, not a full re-review.
- **Summaries in main, full content in subagents.** Each subagent
  digests 40-60k tokens of code and returns a 500-2000 token summary.
  That's the ~20× compression you're paying for.

## Compaction signals and what to do

The harness may compact (summarize) older messages when context gets
long. A well-orchestrated session won't trigger this — main context stays
linear in task count, not in work volume — but be ready.

**Signals you're approaching compaction:**
- You start to forget specific file paths or commit SHAs from earlier
  in the session
- Reviewer prompts feel harder to assemble because you can't recall the
  implementer's exact claims
- A `<system-reminder>` mentions summarization, truncation, or compaction
- Token-count visibility (if shown) crosses ~70% of the model's window

**What to do when sensed:**
- **Commit pending work immediately.** Git is durable; chat is not. If
  you've been holding a multi-file change in conversation, commit it.
- **Record open decisions in TaskCreate.** Task descriptions persist
  across compactions. Move "still to decide: X vs Y" into a task body.
- **Dispatch a fresh subagent earlier than you normally would** — even
  for borderline lane-A work. The subagent's compact report will survive
  compaction better than scattered conversation text.
- **Don't re-`Read` files to "refresh" your context.** You'll burn the
  remaining budget faster. Trust git, TaskCreate, and the harness's
  state tracking.
- **Surface state to the user.** If you can't reliably complete the
  remaining work, say so and let them decide whether to continue or
  open a fresh session.

## AskUserQuestion discipline

Use `AskUserQuestion` for choices that:
- Are cross-cutting (affect multiple tasks)
- Set policy (e.g., advisory vs. auto-fail for a quality gate)
- Are reversible only with effort (renaming a public API, picking a license)

Don't ask for: which file a helper goes in, whether to use `const` or
`function`, naming choices that the file's existing convention answers.
Auto Mode says: make the reasonable call and keep going.

## Background work

`run_in_background: true` is for:
- `npx gitnexus analyze --embeddings` after a batch of commits — index will
  be ready before the next slice needs it.
- Long verification (`pytest -v` on a large suite, `vite build`, `gh pr create`
  on a slow network).
- Anything where you have independent work to do meanwhile.

**Don't** poll a background task you started — the harness notifies on
completion automatically. Just continue with other work.

## Pre-existing failures

If a test fails on the baseline (not introduced by this branch), don't fix
it inside a slice — it's scope creep. Track it explicitly in conversation.
Surface it to the operator at `superpowers:finishing-a-development-branch`
time so they decide: tighten tolerance, mark `xfail`, or ship as-is.

**But:** mark it `xfail` (or tighten tolerance) early in the branch if
possible, so a NEW failure stands out cleanly against a green-otherwise
suite. A red baseline masks new red.

## Quality vs. throughput watchpoints

Moving fast through multi-task plans means some checks get short-circuited.
Specific risk patterns to guard against:

| Watchpoint | What can slip through | Mitigation |
|---|---|---|
| **Concurrency in new code** | A `_running_cores.get()` without `_cores_lock` slipped past spec review; only the code-quality reviewer caught it. SQLite + threading is the common source. | When the implementer touches anything thread-shared (`_*_lock` adjacent, SQLite connections, global state), explicitly ask the code reviewer to look for lock discipline. |
| **Public-API semantic changes** | A refactor's prop/parameter names didn't match the data being passed; call-site labels happened to align by accident. | For refactors that change a public interface, the spec reviewer must verify call-site mappings are semantically correct, not just that visual/behavioral output matches. |
| **"Just className changes" with structural drift** | An implementer extracted local consts inside a constraint that said "only className strings." Semantically identical, but a deviation from the hard constraint. | When an implementer deviates from a hard constraint, verify the deviation is purely additive and re-run any tests touching that code. |
| **Plan-vs-convention naming conflicts** | A field labeled `engine` in plan was `target_api` in production code. Following plan literally creates a contract mismatch. | When plan and project convention conflict, surface the choice via `AskUserQuestion` rather than defaulting either way. |
| **Pre-existing failures masking new ones** | A flaky test was failing throughout the implementation; a new bug causing the same failure mode would have been invisible. | Mark pre-existing failures `xfail` (or tighten tolerance) early in the branch — see "Pre-existing failures" above. |

**Pattern:** the throughput optimization is "ship when the code quality
reviewer says approve." The watchpoint is making sure the reviewer is
*checking the right things*. A reviewer prompt that doesn't mention
threading won't catch a missing lock — you have to tell them.

## Failure modes and false positives observed

Reviewers and tooling will sometimes be wrong. Recognizing the pattern
prevents acting on bad input.

### Reviewer false positives

1. **"Buffer not capped / not newest-on-top" in a downstream consumer** —
   Spec reviewer flagged two missing requirements in a render component.
   Both were actually enforced upstream in the source hook
   (`setBuffer(prev => [event, ...prev].slice(0, 20))` — bounded AND
   prepended at the source). The reviewer didn't trace upstream
   semantics. **Mitigation:** when a "missing requirement" claim
   contradicts the dispatch prompt's stated upstream behavior, verify
   with a targeted `grep` before fixing.

2. **"Tests must land before X ships" — sequencing concern** — Reviewer
   assumed the plan's nominal task order; the actual dispatch order
   already satisfied the concern. **Mitigation:** reviewers don't know
   your dispatch sequence. Their sequencing concerns may be pre-satisfied.
   Read the concern, check `TaskList`, decide.

3. **"Function X not found in module Y"** — Final cross-cutting reviewer
   grepped the wrong file. The function lived in a sibling module.
   **Mitigation:** if a reviewer says "not found," double-check the
   scope you provided in their prompt. The answer is often one file over.

4. **Security-warning "fabricated model identity"** — Harness flagged the
   `Co-Authored-By:` trailer that the system prompt explicitly instructs
   you to add. **Mitigation:** automated security warnings can be wrong
   about instruction-following. If your action is clearly compliant with
   explicit user/system instructions, proceed and note the false
   positive in your response.

5. **"GitNexus MCP not available" from a subagent** — Subagents have a
   different MCP environment than the orchestrator. Several subagents
   couldn't reach GitNexus and fell back to grep + file inspection.
   **Mitigation:** don't require subagents to use GitNexus tools; tell
   them in the prompt that grep + file reading is an acceptable fallback
   for impact analysis when MCP isn't reachable.

### Tool and environment failure modes

6. **`Edit` requires `Read` first** — Trying to `Edit` a file the harness
   hasn't seen returns `File has not been read yet`. **Mitigation:**
   always `Read` (even a small offset+limit window) before the first
   `Edit` on a file in a session.

7. **System `python3` vs project `.venv/bin/python`** — Default `python3`
   doesn't have project test deps (pytest, etc.); the project venv does.
   **Mitigation:** for project-specific tooling (pytest, vite, npx,
   anything not in the standard library), use the project's binary
   explicitly: `.venv/bin/python -m pytest ...`, `npx ...` from the
   right directory.

8. **Background-task completion notifications mid-conversation** — The
   harness fires `<system-reminder>` blocks when a background command
   finishes. These are NOT user input. **Mitigation:** treat them as
   informational; don't confuse them with user acknowledgement of a
   pending question.

### Detection pattern

The common thread: **when a tool/reviewer/warning contradicts what you
already know to be true, do a quick targeted verification (single
`Read`, single `grep`) before acting on the claim.** A 5-second check
prevents a wrong fix that itself needs to be reverted.

## When NOT to use this pattern

- **Single-step tasks.** Just do them in main context.
- **Tightly-coupled refactors** where every change depends on the previous
  change's state in a way that prep-then-dispatch can't capture cleanly.
- **Interactive exploration** ("what does X do?"). Subagent overhead hurts
  here.
- **Tasks with constant operator feedback** — interactive sessions in main
  context fit better.

# Director-Operator Concurrent Operation

This project runs two parallel Claude sessions by design.

## Two-seat team model (Protocol Bundle v5)

**Director-seat** and **operator-seat** are two seats of one team,
with different specializations. Both serve the user-principal.
Neither is senior to the other; specialization is cognitive-load
distribution, not hierarchy.

| Seat | Specializes in | Why this seat? |
|---|---|---|
| **Director-seat** | Strategic synthesis: brief authoring, ADR composition, push decisions, post-roadmap reassessment, cross-cycle planning, codifying discipline | Strategic work requires synthesizing cross-cycle context; director's session preserves cycle-spanning state |
| **Operator-seat** | Operational verification: post-commit Lane V reviewer dispatch, Lane D doc-sync, transplant-handoff refresh, counter-bump dispositions, mailbox event authoring | Operational work requires cold-context independence (Rule #9); operator's session is naturally orthogonal to director's |

Both seats are equal in authority within their specialization. Within
Lane V/D/S, operator-seat acts unilaterally (mailbox events bind
director per Rule #8). Within strategic work (briefs, ADRs, push),
director-seat acts unilaterally (operator-seat acknowledges via
mailbox or commit body). Cross-cutting decisions (protocol changes
themselves, role-partition adjustments) go through the proposal cycle.

**User is the principal.** Both seats serve the user; neither is the
boss of the other. When agents disagree, escalate to user (per the
Disagreement protocol below). When user direction is given, it
overrides any agent's discretion (per the existing "Instruction
Priority" hierarchy: user > git > mailbox > STATE.md > default).

The labels below ("Strategic-seat-default," "Operational-seat-default,"
"Cross-cutting (proposal cycle)") replace the prior v1-v4 labels
("Director-only," "Operator-only," "Shared"). The lane assignments are
unchanged; only the framing is reworded to remove the implicit
senior/junior asymmetry. v5's empirical motivation: the v1-v4
partition implied senior/junior; operator-seat's verification work
(S13 Lane V's F1 CRITICAL finding) directly influenced director-seat's
fix (`9e24323`). The team dynamic was already real; v5 codifies the
framing.

They share a working tree and commit history. Friction arises not on
commits (git serializes those) but on **planning and dispatch overlap** —
both seats reaching for the same shared task at the same time. The
rules below partition work and define a signaling protocol so the cost
of running both is roughly zero.

## Role partition

**Strategic-seat-default** (director-seat unless explicitly handed off):

- Strategic direction — what session ships next, scope reframes
- Brief authoring and revision (`docs/HANDOFF-roadmap-*.md`)
- Post-roadmap reassessment against `docs/STRATEGIC_REVIEW-*.md`
- Push-to-origin decisions
- ADR authoring (`DECISIONS.md`)
- Codifying new precedents into discipline rules (this file / `AGENTS.md`)
  — operator-seat may draft; director-seat commits. This rule was
  drafted by operator-seat and shipped by director-seat, the canonical
  example. v5's R11 beneficiary check (see below) applies to all new
  rule codification.
- Memory writes (`MEMORY.md` index + `memory/*.md` files) — same
  draft-then-handoff shape; memories shape future sessions of both
  seats, so the curation call is director-seat's. v5's `memory-candidate`
  mailbox kind lets operator-seat surface memory-worthy observations
  without latency (director-seat reads via Rule #8 awareness gate at
  next session-start, writes or declines via `decision` mailbox event).

**Operational-seat-default** (operator-seat unless explicitly handed off):

- Counter-bump dispositions (the auto-generated GitNexus-block edits at
  the top of this file / `AGENTS.md`) — folded into the nearest
  relevant code commit or shipped as `chore(baseline)`.
- Trust-but-verify reads after each commit (`git show --stat`, brief
  test run)
- Updating the operator transplant handoff
  (`docs/HANDOFF-operator-transplant-*.md`)
- **Lane V — Post-commit independent verification** (Protocol Bundle
  v4). On any director commit of type `feat` / `refactor` / `fix`,
  operator dispatches spec + code-quality reviewer subagents in
  parallel with director's reviewers (NOT sequential), then sends a
  `verification-report` mailbox event with status (✅ clean / ⚠️ minor /
  ❌ critical) + file:line refs + disposition (`fold` / `advisory`).
  Operator does NOT commit reviewer-fixes; director processes the
  report per Rule #8. Skip on `chore` / `docs` / `test` / `style`.
  Independence enforced by Rule #9.
- **Lane D — Post-commit doc-sync** (Protocol Bundle v4). On any
  director commit modifying code under `cinema/`, `domain/`,
  `web_server.py`, or `cinema_pipeline.py`, operator updates affected
  sections of `ARCHITECTURE.md` and `OPERATIONS.md` (README.md
  carved out — release-positioning is author-judgment), commits as
  `docs(arch-sync): reflect <SHA> in <doc> §<section>`, and sends a
  `doc-sync-notice` mailbox event. Lane D MUST run §15 smoke
  verification before committing (per ADR-013 verification
  discipline). Lane D does NOT introduce new ADRs (`DECISIONS.md`
  stays director-only).
- **Lane S — Pre-dispatch scout** (Protocol Bundle v5; was scaffolded
  in v4). Trigger: director-seat sends `scout-request` mailbox event
  BEFORE dispatching an implementer subagent (Lane B), naming target
  files / symbols / modules + brief reference + specific intel needed
  (convention conflicts, gotchas, plan-vs-source divergences). Operator
  conducts Lane C-style read-only survey of the named targets, sends
  `scout-report` event with findings; director-seat pastes relevant
  intel into the implementer prompt. Effort target: ~10-20 min
  operator-context-burn per scout (pure read, no subagent dispatch).
  Opt-in: director-seat chooses when to send `scout-request`; v5
  doesn't mandate scout for any specific commit type.

**Strategic-seat-default (Lane B):**

- **Implementer dispatch for a new session (Lane B `Agent` call)** —
  director-seat dispatches; operator-seat does not. Empirically true
  in 12+ sessions across cycles 1-6 (the v1-v4 "Shared" label was a
  practice-vs-spec divergence v5 closes per the Sh codification).
  Future v5.1+ may open Lane B to operator-seat for small domain-
  partitioned work; "default" leaves that door open.

**Cross-cutting (either may drive — see signaling rules below):**

- Spec reviewer + code-quality reviewer dispatch (both seats run their
  own — director-seat dispatches director's reviewers; operator-seat
  dispatches Lane V's reviewers; per Rule #9 they operate cold-context
  independently)
- Verification gates (smoke / pytest / tsc)
- Applying review IMPORTANTs **and minors** — `chore(test)` /
  `chore(ui)` / `chore` commits folding review feedback are claimed
  by whoever announces first (see signaling rules)
- Closing-report drafting (partitioned by document: director-transplant
  vs operator-transplant — each seat owns their own)

## Signaling: narrate before acting on shared tasks

Whoever is active first claims a shared task by **stating the action in
conversation before doing it**:

> "Dispatching Session 6 implementer (Lane B, foreground)."
> "Dispatching parallel reviewers (spec + code-quality) on `d516d2a..b25da2e`."
> "Applying spec-reviewer fix to phase_c_ffmpeg.py:50,85,86,90,96,170."

The other party, on seeing the announcement:

- **Does not duplicate** the claimed action.
- **May pre-stage** complementary work without committing: locate fixes,
  draft prompts, validate type shapes, prepare closing reports.
- **Reports back** what they observed and what they're standing by for.

This is the protocol that's been working in practice; this section
promotes it from informal habit to explicit rule.

## State-asserting writes: gate on `git log --oneline -5`

The `git log --oneline -5` precondition also applies to **any write
that makes a claim about current state** — handoff docs, status
reports, commit bodies naming HEAD or branch counts. Operator-only
tasks (like updating the transplant handoff) don't race on
*ownership*, but the *content* races on currency: the other party
may have shipped between your Write and your commit.

Rule: immediately before any state-asserting Write or Edit, run
`git log --oneline -5` and use that just-observed state in the
content. If state moves between Write and commit, re-edit and use
a race-acknowledging commit body (see next subsection).

## Race-acknowledging commit bodies

When state moves during your work, **name the shift in the commit
body**: what was true at write-start, what's true now, why you
committed anyway. Lets readers recalibrate without git archaeology.

Already emergent practice — `843c102` for the state-moved-during-
write pattern; `d8bf650` for the role-deferral-named pattern (both
are forms of acknowledging what shifted around this commit). This
codifies the convention so the next instance of either role doesn't
independently re-invent it.

## Counter-bump dispositions during concurrent operation

The "fold counter bumps into the nearest relevant commit" rule (in
the multi-task discipline section above) avoids trailing
`chore(baseline):` commits when not isolated. **During active
concurrent operation**, the right move is **fold-and-surface**: hold
the counter bump for the other party's next natural commit (their
session minors chore, next code commit) rather than racing with a
standalone `chore(baseline)`. Announce the held delta in conversation
("4-line counter bump held for director's next commit") so the other
party can fold it.

Standalone `chore(baseline)` remains correct only when the bump truly
is isolated (no other work in flight).

## Pre-commit re-verify (Rule #7)

Rule #4 above (`## State-asserting writes: gate on \`git log --oneline -5\``)
requires `git log --oneline -5` *before* a state-asserting Write/Edit
(pre-Write gate). Rule #7 is the matching *pre-commit* gate. Together
they close the hole where state can move between your Write and your
commit — observed in `a6e3ff1` (Monitor.tsx shipped during operator's
handoff Write; operator caught the drift in their race-ack body).

Immediately before `git commit` for any state-asserting commit, run
`git log --oneline -5` AND read `coordination/mailbox/sent/` for events
newer than your Write-start time. Compare to the pre-Write check (Rule
#4). If observed HEAD or unread mailbox events changed:

- **Drift below your concern threshold** (counter bump, unrelated
  commit, informational mailbox event): commit normally; mention
  "rebased mentally on `<new HEAD>`" in body.
- **Drift that contradicts your content** (HEAD shipped something your
  doc says is pending; mailbox event invalidates your assertion):
  re-edit affected sections + race-ack body per Rule #5.
- **Drift that makes your work redundant** (your fix was just shipped
  by other party; mailbox dispatch claimed your work): abort the
  commit; surface the duplicate to user.

Cross-reference: see Rule #4 (`## State-asserting writes`) for the
pre-Write gate. The two rules pair to close the Write-and-commit hole
but are separately invocable, measurable, and retire-able.

## Mailbox events have authority equal to user-relayed signals (Rule #8)

A sent mailbox event (file in `coordination/mailbox/sent/`) obligates
the receiving role to act per its content. Ignoring or deferring a sent
mailbox event requires the same justification as ignoring a direct user
instruction.

**Authority conflict resolution:** User direct instructions override
mailbox events; mailbox events override default behavior. (Mirrors and
extends the existing CLAUDE.md "Instruction Priority" hierarchy.)

**v1 is Tier-1 auto-send** (no user-approval gate on sends). User
remains supervisor via retroactive audit of
`coordination/mailbox/sent/`. If a sent event should not have been
sent, user signals via direct instruction (which by the above priority
overrides the mailbox event).

**Session-bootstrap awareness gate.** On session start, if `STATE.md`'s
`unread mailbox` field shows N ≥ 1 events for your role, you MUST
surface the count to the user in your first user-facing turn BEFORE
processing events:

> "Mailbox has N unread event(s) for {role}; processing now per Rule #8."

The role then processes the queue with full Tier-1 authority. This is
a **one-time-per-session signal**, not a per-event gate. Steady-state
events during the session require no user-surface — Tier-1 throughput
preserved.

**Authority precedence (full).** User direct instructions > git
commits (durable record of what happened) > mailbox `sent/` events
(filesystem-true claims about coordination) > STATE.md fields
(hook-derived snapshot; informational against the above) > default
behavior.

Practical implications:

- When STATE.md and `git rev-parse HEAD` disagree on HEAD SHA → git
  wins. STATE.md is stale; re-verify.
- When STATE.md `unread mailbox` count and `ls coordination/mailbox/sent/`
  disagree → filesystem wins. STATE.md is stale; re-verify.
- When a mailbox event claims a commit landed (e.g., "I dispatched
  Session 9 implementer") but `git log` shows no matching commit
  within ~5 minutes of the event's timestamp → git wins. Mailbox
  claim is a *promise*; git is the *record*. The 5-minute window is
  a heuristic anchor; for in-flight work known to take longer (e.g.,
  overnight runs), the sender should explicitly note expected
  duration in the mailbox event's body.
- Conflicts between user instruction and any artifact are resolved
  per the existing CLAUDE.md "Instruction Priority" — user wins.

**Clarification on "user direct instructions".** "User direct
instructions" means literal user-typed-in-chat messages or other
channels the platform identifies as user input. Operator-authored or
director-authored mailbox events are mailbox-tier authority, not
user-tier — even though operator/director may be invoking the user's
stated wishes. When in doubt, the role of the SENDER (user vs.
operator vs. director) is what determines tier, not the CONTENT or
intent.

## Independent reviewer convention (Rule #9)

**Rule #9: Operator-side reviewer is independent, not duplicate.**
*(Subtitle: second-opinion convention.)*

When operator dispatches a reviewer subagent on a director-shipped
commit (Lane V), the reviewer's job is **second opinion**, not
redundant pass. Operator's reviewer prompt:

- MUST NOT cite director's reviewer findings (operator wasn't on
  dispatch; cold context)
- MUST focus on angles director's reviewer may have missed (operator
  emphasizes: cross-system effects, concurrency, public-API
  semantics, spec-vs-source divergence; director's reviewer typically
  emphasizes: code quality, style, performance)
- MUST dispatch with cold `BASE_SHA..HEAD_SHA` context only
- MUST be constructed cold from the commit's `BASE_SHA..HEAD_SHA` +
  the original spec/brief reference only. Operator MUST NOT include
  in the prompt: director's reviewer findings, director's reviewer
  verdict, any text from director's reviewer-fix commit body, or any
  synthesized "what director's reviewer worried about" language. The
  operator's reviewer must form its judgment from cold context — the
  same cold context any external reviewer would have.

Independence is what makes the second pass valuable. A duplicate
reviewer is waste. The prompt-construction discipline makes the
property checkable — anyone can re-read operator's reviewer dispatch
prompt and verify no contamination; without it, "independent" is
aspirational.

**Why:** Director's reviewer is dispatched from director's context —
it has visibility into director's design intent but inherits
director's blind spots. Operator's reviewer has zero shared context,
so it's structurally independent. Single subagent burn per director
feat commit is acceptable cost for the second opinion.

**Parallelism:** Both parties dispatch reviewers on the same commit
**simultaneously, not sequentially**. Operator does not wait for
director's reviewer pass to land before dispatching Lane V. The two
parties' subagents may produce overlapping findings — that's
expected; the second opinion's value is in the angles each party
MISSES, and overlap on what both catch is acceptable redundancy.

**Coalescing (v4.1, CC-1).** Strict per-commit Lane V trigger remains
the default. **Operator MAY coalesce Lane V dispatches into a single
range-review** when (a) the commit range is small (≤5 commits), (b)
the commits are tightly coupled (same brief / same session / shared
contract surface), AND (c) reviewing in isolation would lose
cross-system context. Example: S13's `feat(types)` + `feat(web)`
commits form one logical unit (types contract + impl that consumes
the contract); reviewing them independently would have produced two
reports neither of which had the cross-system shape verification.
Coalescing is operator discretion; when applied, the
`verification-report` event's `related-commits` field lists all
covered SHAs, and the prompt's `BASE_SHA..HEAD_SHA` covers the full
range.

**Spec-reviewer prompt discipline (v4.1, CC-2).** The general-purpose
spec reviewer has been observed (2 dispatches, 2 hallucinations) to
make confident "X exists" / "X is required" claims that don't
survive grep verification. Mitigation: operator's spec-reviewer
prompt MUST include an explicit "verify before asserting existence"
instruction:

> "Before claiming any symbol, prop, import, or section exists in
> the code: run grep / Read on the actual file to verify. If your
> claim can be falsified by `git show <SHA> -- <file>` or `grep
> -n <symbol> <file>`, run that verification command yourself BEFORE
> including the claim in your report. Hallucinated existence claims
> waste director's review cycles and pollute the verification report."

Without this discipline, hallucinated existence claims pass through
to director's main context as CRITICAL findings (e.g., "ReviewStage
requires onRefreshProject prop, tsc emits 3 errors") that
director must independently disprove. With it, the hallucination
is contained inside the subagent.

If hallucinations persist after CC-2 codification (e.g., ≥1 more in
cycle-7+ Lane V dispatches), v4.2 should consider operator's CC-2
options 2 (third lightweight verifier pass) or 3 (different subagent
type for spec review).

## Joint-team mode (Rule #10)

**Rule #10: Joint-team mode.** *(Subtitle: co-agent mode.)*

Director-seat and operator-seat are two seats of one team. Both serve
the user-principal. Neither is senior to the other; specialization is
cognitive-load distribution, not hierarchy.

**Practical implications:**

- Within their specialization lane, each seat acts unilaterally (no
  cross-seat approval needed for in-lane work).
- Cross-cutting decisions (protocol changes, role-partition
  adjustments) go through the proposal cycle (operator drafts;
  director ships; cycle precedent: v2 / v3 / v4 / v4.1 / v5).
- When agents disagree on a cross-cutting decision after 2 REPLY
  cycles, escalate to the user (per the Disagreement protocol below).
- When user direction is given, it overrides agent discretion (per
  the existing "Instruction Priority" hierarchy: user > git >
  mailbox > STATE.md > default).
- Both seats use the same commit-body etiquette + Rule #7 pre-commit
  re-verify + Rule #5 race-ack — these are TEAM disciplines, not
  seat-specific.

**Why this matters:** the v1-v4 partition implied senior/junior
asymmetry (director codified rules; operator drafted then waited).
Empirically, operator-seat's verification work (Lane V S13 finding
F1 CRITICAL, dispatch `029dbf9..2fb44d1`) directly influenced
director-seat's fix (`9e24323`). The team dynamic was already real;
v5 codifies the framing so the discipline articulates the equality
that practice already exhibits.

## Codification bias check (Rule #11)

**Rule #11: Codification bias check.** When proposing a new rule
(in any protocol bundle), the codifier MUST flag the rule's
**primary beneficiary** in the proposal frontmatter:

- `beneficiary: director-seat` — rule primarily reduces director-seat's
  friction or expands director-seat's authority
- `beneficiary: operator-seat` — rule primarily reduces operator-seat's
  friction or expands operator-seat's authority
- `beneficiary: both` — rule is symmetric (e.g., Rule #2 signaling
  applies to both seats)
- `beneficiary: user` — rule primarily benefits the user-principal
  (e.g., Rule #8 mailbox authority closes user-as-relay bottleneck)

**REPLY-cycle implication:** if `beneficiary` is asymmetric
(director-seat or operator-seat alone), the OTHER seat has explicit
veto in the REPLY cycle. If the non-beneficiary seat declines to
consent, the rule is downgraded to "advisory" status or revised
until both seats consent.

**Why this matters:** user surfaced a "director codifies rules that
bind themselves" concern as v5 motivation. The retroactive analysis
(Rules 1-9: 4 both / 1 user / 3 operator-seat / 0 director-seat) does
not bear out the bias hypothesis; codification has been operator-
friendly because operator-seat surfaces races (they're in the
operational layer where races occur). R11 makes future codification
EXPLICITLY assessable per-rule + auditable over time. The full
retroactive snapshot lives in `docs/PROTOCOL-RULES-LOG.md`.

## Disagreement protocol (v5)

Generalizes v4's R-V1 counter precedent. When operator-seat disagrees
with a director REPLY refinement (or vice versa), the disagreeing seat:

1. **States the disagreement explicitly** in the next-cycle revision
   with reasoning (operator: v4 §"Operator counter-refinement to R-V1"
   was the precedent; director: equivalent section in next REPLY).
2. **Provides project-data-grounded evidence** (the R-V1 counter cited
   Session 10's 36-LOC feat as data; ungrounded "I don't like it" is
   not sufficient).
3. **Proposes one of three resolutions:**
   - **Counter-refinement** — adjust the disputed item per the data
   - **Defer to v(N+1)** — ship without the disputed item; revisit
     with more data
   - **Acceptance criterion** — ship with disputed item but log a
     measurable criterion for revisiting (R-V1's "if cost >1.5M
     tokens AND catch rate <15%" model)

**Resolution paths:**

- **Silent-accept:** other seat ships without re-replying on the
  disputed item (precedent: v4 R-V1 counter was silent-shipped by
  director). Equivalent to "accept the counter."
- **Re-REPLY:** other seat objects in writing with their own counter.
  Triggers another revision cycle.
- **2-cycle limit:** if disagreement persists after 2 REPLY cycles,
  escalate to user. **The agents do not argue indefinitely.** User
  is principal; agents serve user direction.

**Counting clarification (per v5 §C-D-1):** The 2-cycle count refers
to **director's REPLYs after the initial proposal**, not operator's
revisions. Flow: `proposal → director REPLY (cycle 1) → operator
revise → director REPLY (cycle 2) → operator revise → escalate to
user`. Total: 1 proposal + 2 director REPLYs + 2 operator revises =
5 documents before escalation. 5 documents is plenty of revision; if
disagreement persists, user adjudicates.

**Why 2 cycles, not N:** each cycle costs tokens + delays ship.
Empirically v4's R-V1 cycle resolved in 1 cycle (operator counter →
director silent-ship); v5 had 0 counters (cleanest cycle to date).
Two-cycle limit is conservative; gives room for genuine refinement
without enabling deadlock.

## Emergency handling protocol (v5)

**Scope (per v5 §R-E-1).** Something breaks unexpectedly mid-session
in one of four categories:

1. **Production-affecting OR user-data-integrity issue** — live behavior
   is broken, data is being lost / corrupted, or users are observably
   blocked. NOT: a regression caught in CI that hasn't shipped.
2. **Security-critical** — unauthorized access, secrets leak, dependency
   CVE with active exploit. NOT: hardening opportunities or theoretical
   concerns.
3. **Active bleed-rate** — cost / resource / token burn is accumulating
   with each minute of delay (e.g., runaway subagent loop, infinite
   retry, GPU lease bleeding). NOT: one-time waste already incurred.
4. **External time-pressure** — an external deadline (deploy window,
   scheduled demo, regulatory) is at risk WITHOUT mitigation in N
   minutes.

Events outside these four are NOT emergencies — they use normal role
partition + proposal cycle, **even if urgent-feeling**. The four-
criteria gate keeps the §E carve-out tight; normal urgent work uses
the proposal cycle.

**v5 protocol:**

1. **First-noticer claims initial response.** Whichever seat observes
   the emergency narrates in chat (Rule #2) AND sends a `dispatch-claim`
   mailbox event with `urgency: emergency` flag. This signals the
   other seat to defer.

2. **Triage discipline: stop-the-bleed first.** The responding seat
   focuses on minimal-viable mitigation (revert, hotfix, feature-flag-
   off) rather than full root-cause analysis. Attribution and learnings
   happen post-incident.

3. **Cross-seat-temporary-authority during transplant:** if the
   normally-authoritative seat is in transplant or context-exhausted,
   the other seat has TEMPORARY authority on emergency response.
   The temporary seat:
   - Acts on emergency (commit + push if needed for stop-the-bleed)
   - Explicitly notes "acting under v5 §E temporary authority" in
     commit body
   - Defers all non-emergency decisions until normal seat returns

4. **Post-incident review.** Within 1 session of emergency resolution:
   - Whichever seat handled the emergency writes an incident note in
     `docs/INCIDENT-LOG.md`
   - Both seats review for protocol gaps that allowed the emergency
   - If protocol gap surfaces, draft rule for next bundle's REPLY cycle

**Why this matters:** emergencies don't honor cycle boundaries. The
protocol must allow either seat to act without waiting for the other.
The temporary-authority carve-out prevents transplant cycles from
blocking critical response.

## Git is the tiebreaker

If both parties accidentally dispatch the same subagent (announcement
race), the first commit to land wins. The other's subagent output is
discarded — cost: one wasted ~50k-token subagent context. Acceptable
worst case.

Before acting on any shared task, **run `git log --oneline -3` first.**
A commit that already addresses the task means the task is closed; do
not duplicate.

## When the other party is offline

If a session ends (context limit, end-of-day, explicit handoff), the
remaining party takes the full loop unilaterally. No signaling needed
until the next session of the absent role picks up via handoff doc.

The handoff doc is how the next instance of either role learns:

- What the absent party shipped in the meantime
- What's open and which role owns each open item
- Any new precedents that emerged

## Phase taxonomy (Protocol Bundle v4)

Director's loop has 5 observable phases. Operator's action per phase
is specified below. Detection is hybrid: explicit `*-request` mailbox
events for director-initiated transitions; implicit git-log poll for
post-commit phase; 10-minute idle heuristic from last director
commit.

| Director phase | Detection signal | Operator action | Phase exit signal |
|---|---|---|---|
| **Pre-dispatch** | `scout-request` mailbox event OR director's in-chat "Dispatching X" narration | **Lane S** (v5+): read-only survey; send `scout-report`. v4: ignore. | Director's subagent commit lands |
| **Subagent active** | Dispatch-claim event seen; WT has uncommitted changes director-attributed | **Silent.** No `.py` writes; hold counter bumps. | Director's commit lands |
| **Post-commit (feat / refactor / fix)** | New commit by director (Author: `hkk009008-svg`), type matches | **Lane V**: dispatch spec + code-quality reviewer subagents in parallel; send `verification-report` | Director's reviewer-fix commit OR new feat OR 10-min idle |
| **Post-commit (subsystem touch)** | New commit by director, touches `cinema/` / `domain/` / `web_server.py` / `cinema_pipeline.py` | **Lane D**: update ARCHITECTURE.md / OPERATIONS.md (README carved out); commit `docs(arch-sync)`; send `doc-sync-notice` | Commit landed |
| **Post-commit (chore / docs / test / style)** | New commit by director, type matches | **Ignore.** No Lane V / D action. | Next commit |
| **Idle (no signal N min)** | No phase signal for N=10 minutes after last director commit | Standby OR work on pre-listed operator-claimable backlog | New commit OR direct user instruction |

**Fallback when STATE.md is stale (per Rule #8 §F):** if phase
detection via STATE.md disagrees with filesystem (e.g., `git log -5`
shows a commit STATE.md doesn't reflect), trust the filesystem.
Phase determination is filesystem-authoritative.

**Default to inaction.** If operator can't confidently identify the
phase (ambiguous commit type, unclear scope, partial WT state),
treat as Idle and stand by. Better to miss a Lane V dispatch than
to dispatch on the wrong phase.

## Adjacent-useful work when you can't claim the loop

When the other party owns the active task, useful work in parallel
includes:

- **Pre-locate fixes** for divergences the implementer flagged (find
  file:line, draft the edit, hold for review verdict)
- **Survey carry-forward items** (STRATEGIC_REVIEW priorities not in
  current scope) to prep the post-roadmap reassessment
- **Validate data shapes** the implementer assumed (e.g., does this
  field actually exist on the relevant interface?)
- **Draft closing-report skeleton** so it's ready when the loop closes
- **Spot stale doc claims** and queue corrections for next docs commit

Do NOT:

- Edit code while the other party's subagent is mid-edit on the same
  files
- Commit doc updates that contradict in-flight subagent work
- Dispatch a duplicate reviewer or implementer
- Run `pytest` against a dirty working tree mid-implementation
  (results don't reflect either landed or final state)

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (3214 symbols, 20659 relationships, 273 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
- Commit SHA
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — they'll burn context
discovering everything you already know, and the report will be vague.

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

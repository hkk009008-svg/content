# Session-start protocol (read me first)

**Truth lives in `ARCHITECTURE.md` at the repo root.** This file (CLAUDE.md)
is the *process layer* — the impact-analysis method, multi-task orchestration, session
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

# Impact analysis before editing

Before modifying a function, class, or method, gauge its blast radius with
grep + Read (the de-facto method across every session to date):

- `grep -rn 'symbolName' --include='*.py' .` to find the definition + callers;
  Read the call sites; grep imports for cross-file references.
- Report the direct callers + risk to the user before editing a high-fanout
  symbol.
- Before committing, run `git show --stat` / `git diff` to confirm the changed
  scope matches intent.

For renames / extracts / splits: grep the symbol across the repo first
(callers, imports, string references), update every site, then re-grep to
confirm none remain. Don't find-and-replace blind to the call graph.

*(A GitNexus MCP integration was auto-documented here as mandatory but its
server was never configured — 0 tool calls in 67 sessions; grep/Read was the
real method throughout. Removed 2026-05-28; see DECISIONS.md ADR-016.)*

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

Beyond the impact-analysis checks above:

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
1. Before editing an existing symbol, `grep -rn 'symbolName' --include='*.py' .` to find callers/importers and Read the call sites; report blast radius to the user.
2. After edits, run `git diff --stat` to confirm scope matches intent.
3. <task-specific gotcha>
4. **Brief-pattern reference adherence.** When the brief says "mirror pattern X at file:line" or "use the existing _foo_-style endpoint," verify the FULL shape of X — signature, route path, scope parameters, error handling, lock guards — not just the called function. Brief-pattern references are implicit specs; silent deviations cascade. If the named helper doesn't exist (e.g., brief says `_mutate_shot` but the actual pattern uses `mutate_project`) or the wording is ambiguous, report the divergence in your status BEFORE implementing. (Broader codifier-side discipline: see Rule #12 — brief-level grep-the-writes — in `docs/PROTOCOL-RULES-LOG.md`.)
5. **pid-scope check on new endpoints.** When adding/touching an HTTP endpoint operating on a project-scoped resource (shots, scenes, locations, characters), verify the route takes `<pid>` explicitly. Do NOT scan via `list_projects()` to find a matching resource — IDs can collide across projects (e.g., `shot_id` follows `shot_{scene}_{i}` and matches across projects with matching scene/index layouts). Inspect at least one similar existing endpoint in the same file (e.g., `api_update_shot_prompt`) to confirm the route shape and scoping. (Broader codifier-side discipline: see Rule #13 — symmetric-endpoint audit — in `docs/PROTOCOL-RULES-LOG.md`.)

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
- Impact findings (callers, risk) from grep/Read
- Files changed (paths only)
- Verification command output
- Commit SHA — `git commit` stdout's SHA is authoritative as of cycle-8 B-003 Option E (the post-commit hook no longer amends; STATE.md is gitignored and regenerated locally). Use `git log --oneline -3` to double-check if desired, but the SHA from commit stdout matches HEAD.
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — they'll burn context
discovering everything you already know, and the report will be vague.

## Hardening notes — provenance for the implementer-template additions

Items 4-5 in "Project conventions you MUST follow" and the Commit SHA
capture guidance in "Report Format" are hardened in from cycle-5 + cycle-6
failure modes. Carry them forward in future dispatches; if you trim the
template, do NOT trim these:

- **Item 4 (brief-pattern adherence)** — S13 implementer interpreted the
  brief's `_mutate_shot` pattern reference as "use `mutate_project`"
  without inheriting the route shape (pid-scoping, single-project
  mutation). Operator-seat's Lane V caught **F1 CRITICAL** post-commit:
  multi-project `shot_id` collision via the `list_projects()`-scan
  fallback. Fix shipped at `9e24323` (`fix(web): address S13 Lane V F1
  (CRITICAL) + F2 — pid-scoped reject route + monotonic-run dedup`). The
  brief named a non-existent helper, but the pattern's shape was still
  recoverable by inspecting the cited `api_update_shot_prompt`
  endpoint — that's the inspection step item 4 codifies.
- **Item 5 (pid-scope check)** — same F1 CRITICAL root cause, codified
  as a standing project convention so the next implementer catches the
  failure mode at design time, not via Lane V post-commit. Cost
  comparison: design-time check is ~1 grep; post-commit Lane V catch
  cost ~234k tokens (cycle-6 dispatch) + the F1 fix commit's
  developer-time. Front-load is cheap.
- **Commit SHA capture** — historical context: cycle-5 dispatch surfaced
  that implementer-reported SHAs were sometimes 1 commit stale because
  the project's `.claude/hooks/update-state.sh` post-commit hook AMENDED
  STATE.md into the just-made commit, changing its SHA. The Item 5
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
  `Co-Authored-By:` trailer Claude Code injects by default (whatever the
  active model is — `Claude Opus 4.8 (1M context)` at present).

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

### Tool and environment failure modes

5. **`Edit` requires `Read` first** — Trying to `Edit` a file the harness
   hasn't seen returns `File has not been read yet`. **Mitigation:**
   always `Read` (even a small offset+limit window) before the first
   `Edit` on a file in a session.

6. **System `python3` vs project `.venv/bin/python`** — Default `python3`
   doesn't have project test deps (pytest, etc.); the project venv does.
   **Mitigation:** for project-specific tooling (pytest, vite, npx,
   anything not in the standard library), use the project's binary
   explicitly: `.venv/bin/python -m pytest ...`, `npx ...` from the
   right directory.

7. **Background-task completion notifications mid-conversation** — The
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
| **Operator-seat** | Operational verification: post-commit Lane V reviewer dispatch, Lane D doc-sync, transplant-handoff refresh, mailbox event authoring | Operational work requires cold-context independence (Rule #9); operator's session is naturally orthogonal to director's |

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

- **Drift below your concern threshold** (unrelated commit, informational mailbox event): commit normally; mention
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

## Brief-level grep-the-writes discipline (Rule #12)

**Rule #12: Brief-level grep-the-writes discipline.**
*(Subtitle: type-declaration is not write-evidence.)*

When a brief or dispatch prompt names a schema field, mutator function,
dict key, or write-path as the target of new code, the codifier MUST
grep production writes to verify the named symbol is actually populated
at runtime — not just declared in the type schema. Type-declaration
proves a field can exist on a record; only a write-site proves it does
exist at runtime.

**Verification commands (at minimum one of; combine as needed):**
- For a dict key: `grep -rn "\"<key>\"\|'<key>'" --include='*.py' .`
  filtering for assignment patterns (`["<key>"] =`, `.update({...})`,
  dict literals, `**`-spread).
- For a Pydantic field: grep for `<field_name>=` and `setattr(`
  patterns, plus any mutator helper (`mutate_project`,
  `Project.model_validate`, `model_dump` round-trips). Mixed-shape
  symbols (typed-attribute AND raw-dict access; P1-3 migration is the
  canonical example) need BOTH surfaces grepped.
- For a function call: `grep -rn "<func_name>("` to find call sites;
  verify they're production paths and not test-only. Async/background
  paths (worker threads, deferred queues) count as production.

**What "verified" looks like in a brief or dispatch prompt:** the
brief includes the grep command's output (or a one-line excerpt +
file:line ref) under the named symbol. Without it, the symbol is a
*type-level claim*, not a *runtime claim*; implementers MUST be told
which.

**Two-layer-defense composition with v4.1 CC-2.** Rule #12 is the
**upstream** version (brief-write-time grep before dispatch); CC-2
is the **downstream** version (Lane V spec-reviewer prompts verify
symbols before assertions). Together they form a two-layer defense:
codification catches at brief-write time; CC-2 still catches at Lane
V time as backstop. Post-codification Lane V catches of symbol-
divergence are working two-layer defense, not broken codification.

**Codified SHA:** `8ab0bbb` (Protocol Bundle v5.1 ship; filled per
chicken-and-egg precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b`
/ v4.1 `509db7c` / v5 `d66690f`). Empirical basis: Lane V #6 F1
(N=1; closed at `6c1171a`) + Lane V #8 spec-reviewer prompt preventive
application (N=2; 0 divergences). Codified per the N=2 codification
threshold established in director's Lane V #6 REPLY
(`2026-05-25T18-44-52Z`). Beneficiary per Rule #11: `director-seat`
(constrains brief-writing); operator-seat consented affirmatively in
v5.1 REPLY (`9f032db`) per R11 non-beneficiary explicit-consent path.

## Symmetric-endpoint audit discipline (Rule #13)

**Rule #13: Symmetric-endpoint audit discipline.**
*(Subtitle: a new defense names what existing endpoints may be missing.)*

When adding a new endpoint (or modifying an existing one) that
bypasses an existing fence, gates on a persistent flag, or operates
on shared state already touched by other endpoints, the codifier
MUST audit ALL existing endpoints on the same fence / flag / state
for parallel checks the new endpoint should mirror — AND for parallel
checks the existing endpoints may be missing.

**What "shared state" means here (any of):**
- The same in-memory set / dict (e.g., `_running_pipelines`,
  `_progress_queues`, `_reassembly_in_flight`)
- The same persistent flag on the project record (e.g.,
  `screening_approved`, `needs_reassembly`)
- The same on-disk artifact (e.g., `final_video_path` / assembled mp4)
- The same lock (`_pipelines_lock`, per-project `mutate_project` lock)

**What the audit looks like (codifier responsibility):**
1. Grep existing endpoints touching the shared state:
   `grep -n '<shared_state_symbol>' web_server.py`
2. For each match, identify: bypass behavior, precondition checks,
   error-response shapes.
3. For each existing endpoint, ask: *"If I were writing this endpoint
   from scratch today knowing what I know now, would I include a
   check the new endpoint needs?"* If yes, the existing endpoint is
   under-defended — flag for symmetric fold in the same commit OR a
   follow-up issue.
4. For the new endpoint, ask: *"Are there existing endpoints whose
   defenses I should be mirroring?"* If yes, include them in the new
   endpoint OR document why the new endpoint is genuinely exempt.

**What "verified" looks like in a brief or commit body:** the brief
includes a one-liner listing the existing endpoints checked (e.g.,
"Audited `/assemble/screen`, `/assemble/re-assemble`,
`/screening/approve` for parallel precondition checks; mirroring
`final_video_path` existence guard from `/assemble/screen`."). The
commit body either folds the symmetric fix OR explicitly defers it
with rationale.

**Why this matters:** internal-review with full design-intent context
creates a structural blind spot — the reviewer's attention is on the
NEW code's correctness; existing parallel endpoints feel like
background. Cold-context Lane V reviewers catch symmetric cases
precisely because they don't share the design-intent inheritance.
Rule #13 moves the catch upstream from Lane V to brief-write time,
saving Lane V cycles for cases where the symmetry isn't yet visible
at brief time. Rule #9's structural value (independent reviewer)
remains as backstop.

**Codified SHA:** `8ab0bbb` (Protocol Bundle v5.1 ship; filled per
chicken-and-egg precedent). Empirical basis: Lane V #8 I1 CRITICAL
(N=1; iterate endpoint missing the gate-bypass `/screening/approve` +
`/assemble/re-assemble` had; closed at `9e9b008`) + Val#1 V1 (N=2;
`/screening/approve` missing the precondition `/assemble/screen` had;
closed at `d10b849`). Beneficiary per Rule #11: `director-seat`
(constrains endpoint design); operator-seat consented affirmatively
in v5.1 REPLY (`9f032db`) per R11 non-beneficiary explicit-consent path.

## Operator-driven Lane B template + selection criteria (Rule #14)

**Rule #14: Operator-driven Lane B template + selection criteria.**
*(Subtitle: when operator-seat may dispatch Lane B implementer subagents.)*

Operator-seat MAY claim and dispatch a Lane B implementer subagent
(with parallel Lane V follow-up) without prerequisite user-direction
or director-invitation when ALL five selection criteria below hold.
Outside the criteria, Lane B remains director-driven per role
partition Sh's "Strategic-seat-default" framing.

### Selection criteria (ALL must hold)

A unit of work is **operator-driven-Lane-B-eligible** when ALL of these hold:

1. **Small file count.** Single-file refactor, OR 2-3 closely-related
   sibling files (e.g., cinema-package siblings, a domain/ helper
   cluster). >3 files indicates cross-cutting concerns better served
   by director-driven judgment.

2. **Clear canonical pattern reference.** The work applies a documented
   pattern with at least one canonical site reference (e.g.,
   `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Variant 1" with site
   reference to commit SHA). Operator's pre-scope MUST cite the
   canonical pattern AND the canonical site SHA in the dispatch-claim
   event. (Rule #12 grep-the-writes applies at brief-write time for
   the canonical site reference.)

3. **≤150 LoC of net production-code change.** Total LoC delta
   (additions + deletions) across all touched **production** files is
   ≤150. Test file changes are NOT counted toward the boundary (tests
   scale with what they cover; counting them would penalize good test
   discipline). Larger changes warrant director-driven judgment (more
   cross-cutting risk; larger Lane V reviewer burden; less mechanical).
   Empirical fit at codification: B-005 (cycle-11, `c296105`) at 142
   production LoC + B-006-broad-A (cycle-12, `5b68776`) at 82
   production LoC both satisfy ≤150; B-006-broad-B (cycle-12,
   `a0493dc`) at ~243 production LoC correctly does NOT (the work was
   director-driven and is the criteria-exclusion validation point).

4. **No cross-cutting public-API impact.** The work does NOT change
   function signatures, return-type contracts, exception types raised
   in ways that break existing callers, or any other surface that
   callers depend on. Acceptable: adding new exception types via
   inner-validate (the callers' contract is preserved; the new
   exception is what the caller was already expected to handle on
   shape mismatch).

5. **Rule #13 symmetric audit covers the scope.** Operator's pre-scope
   completes a Rule #13 symmetric-endpoint audit demonstrating no
   sibling-site partial-coverage risk. The audit's grep-output is
   cited in the dispatch-claim event (per Rule #13 + Rule #12
   disciplines).

If ALL 5 hold → operator-driven Lane B eligible. If ANY fail →
director-driven Lane B is the default.

**Criterion-failure default (per operator's R-Q4-1).** If ANY of the
5 criteria fails during pre-scope, the **default action is (a) defer
to director-driven Lane B** per role partition Sh. Operator-seat MAY
ALSO send an INFORMATIONAL `dispatch-claim-deferral` event surfacing
the criteria-check result + reason for deferral (option (b) —
non-blocking, visibility-only; director-seat reads at next
phase-detection but is not obligated to respond per Rule #8 mailbox
authority interpretation — informational events convey state, they
don't bind action). Option (c) request user-direction override is
reserved for the case where operator-seat believes the criteria-
failure itself reflects a Rule #14 wording gap that user-direction
should resolve (e.g., "criterion #3 fails by 5 LoC but the work shape
is textbook operator-driven; should I proceed with director-direction
or escalate?") — rare, not the default.

### Template (5-stage flow)

Operator-driven Lane B execution follows this structured shape. Each
stage corresponds to a discrete operator-seat decision point with
mailbox-event hand-off.

**Stage 1: Pre-scope (Lane C-style read-only survey).**
Operator conducts a read-only survey of the proposed scope:
- Grep for the target symbol(s) at HEAD (Rule #12 grep-the-writes).
- Identify the canonical pattern + canonical site SHA from pattern doc.
- Classify per-site variant fit (per pattern doc's variant taxonomy).
- Rule #13 audit: verify no sibling-site partial-coverage risk.
- Verify the 5 selection criteria are met.

Pre-scope is operator-internal; no mailbox event. Typical wall-clock:
~10-15min depending on scope size.

**Stage 2: Dispatch-claim mailbox event.**
Operator sends a `dispatch-claim` event to director-seat citing:
- Scope: file count + site count + canonical pattern + canonical site SHA
- Per-site variant classification (table)
- Rule #12 grep evidence (the grep command + output)
- Rule #13 audit completion (the grep command + output)
- Estimated cost envelope (token + wall-clock)
- 5-min silent-accept window (per v5 Tier-1 disagreement protocol)

The dispatch-claim event SHOULD note if parallel-with-director work is
in flight on disjoint files (per operator's Q2 answer); otherwise the
default assumption is exclusive operator-driven Lane B.

Director-seat MAY counter-refine in the 5-min window OR silently
accept (no REPLY = consent). After the window, operator proceeds.

**Stage 3: Implementer subagent dispatch (Lane B).**
Operator dispatches a single implementer subagent (Lane B, general-
purpose, sonnet) with a cold-context prompt assembled from:
- The brief content (pattern doc references + per-site table from pre-scope)
- CLAUDE.md project conventions (Rules #12 + #13 + verification
  commands + OBS#1 phrasing convention if applicable)
- Verification commands the implementer MUST run + capture
- Report format requirements (Status / Sites migrated / Per-bucket
  distribution / Deviations / Files changed / Commit SHA / Self-review)

Implementer dispatches Lane B; implementer commits + pushes; status
report returns to operator's main context. Typical cost: ~70-130k
subagent tokens; wall-clock ~10-15min.

**Stage 4: Parallel Lane V dispatch (spec + code-quality reviewers).**
Operator dispatches TWO cold-context reviewer subagents IN PARALLEL
(per Rule #9 §"Parallelism") on the implementer commit's range:
- Spec reviewer: per-site recipe-fit verification + convention
  compliance + out-of-scope preservation
- Code-quality reviewer: lock-window correctness + index-parity
  invariant + cross-system effects + concurrency

Both reviewer prompts include CC-2 hallucination guard + Rule #12 +
Rule #13 prompt discipline. Typical cost: ~200-250k subagent tokens
total; wall-clock ~10-15min parallel.

Director-seat MAY ALSO dispatch a parallel Lane V on the same commit
per Rule #9 §"Parallelism" (cycle-12 dual Lane V #13 is the
demonstration); operator-seat's Lane V dispatch does NOT preempt
director-seat's parallel option. The two pairs produce complementary
findings sets per Rule #9 §"Parallelism" structural independence.

**Stage 5: Verification-report mailbox event.**
Operator synthesizes both reviewers' findings into a structured
`verification-report` event to director-seat:
- Status (✅ READY TO SHIP / ⚠️ minor concerns / ❌ blocking)
- Per-finding catalog with severity + source + description +
  disposition recommendation
- Cumulative v4.1 telemetry update (dispatch count + tokens + findings
  + hallucinations + narrowing-threshold status)
- Cursor advance to consume director's `dispatch-claim` event (if any
  silent-accept-window REPLY exists) + emit this verification-report
- Race-ack per Rule #5 + #7

Director-seat processes the verification-report per Rule #8 mailbox
authority (next-session awareness gate if cycle-spanning; same-session
processing if intra-cycle). Disposition: FOLD inline (fix-on-received-
findings if N≥2; standalone fix commit) / DEFER / NO ACTION.

### Working criteria (dogfood for v5.2)

Per v5.1's working-criteria precedent (R-D-1 refinement), v5.2 codifies
working criteria for Rule #14 invocation:

- **C1: Rule #14 invocation cited in dispatch-claim.** Future
  operator-driven Lane B dispatch-claim events MUST cite Rule #14
  explicitly + enumerate the 5 selection criteria check.
- **C2: Rule #14 invocation cited in implementer commit body.** The
  Lane B implementer's commit body includes literal text "Rule #14"
  (or "Per Rule #14 operator-driven Lane B") + the canonical pattern
  reference + the canonical site SHA. Enables grep-based audit of
  Rule #14 adoption (`git log --grep='Rule #14'`).
- **C3: Selection criteria pre-flight by operator BEFORE dispatch-
  claim.** Operator does the 5-criteria check during pre-scope
  (Stage 1); criteria check result is cited in the dispatch-claim.
  If any criterion fails, operator does NOT send the dispatch-claim
  (defaults to (a) per the criterion-failure default above);
  director-seat handles per role partition Sh default.
- **C4: Per-instance wall-clock — operator-driven Lane B dispatches
  within ~20-30min of pre-scope completion** for work that meets ALL
  5 criteria (per operator's R-Q5-1). Measurable per-dispatch
  (operator's dispatch-claim event timestamp − operator's pre-scope-
  start timestamp). Cycle-13+ retrospective rolls up across instances
  ("≥80% of operator-driven dispatches met C4 = healthy adoption").
  Secondary roll-up criterion (≥40% reduction in director-side cycle
  throughput friction for operator-driven-eligible work) becomes
  measurable at v5.3 retrospective.

### Composition with other rules

- **Rule #2 (signaling):** Stage 2 dispatch-claim is the formal signal;
  operator MAY also narrate in chat per Rule #2 if user is observing
  the session.
- **Rule #5 + #7 (race-ack + pre-commit re-verify):** apply at every
  commit Stage 3 + Stage 5 produces; the implementer subagent inherits
  these via the prompt's "project conventions" section.
- **Rule #8 (mailbox authority):** dispatch-claim binds director-seat
  to consent (silent or explicit) within the 5-min window;
  verification-report binds director-seat to a disposition per the
  authority precedence.
- **Rule #9 (independent reviewer + parallelism):** Stage 4 operator-
  side Lane V is structurally independent from any director-side
  parallel Lane V (cold-context discipline; non-overlapping prompt
  contamination).
- **Rule #10 (joint-team mode):** operator-driven Lane B is a
  specialization within Sh role partition, not a hierarchy shift.
- **Rule #12 + #13:** applied during pre-scope (Stage 1) and cited
  in dispatch-claim (Stage 2) per criteria #2 + #5.

### Beneficiary (per R11)

**Beneficiary: both** seats.

Rule #14 enables operator-seat (codifies a capability that previously
required user-direction or director-invitation to invoke) AND constrains
operator-seat (5 criteria + cannot claim outside them). It also enables
director-seat (clear yield-signal when criteria match) AND constrains
director-seat (cannot claim work that fits operator-driven-eligibility
without explicit reason — user-direction overriding partition, parallel
execution demand, or cross-cutting risk that the criteria don't capture).
Symmetric on both axes.

No asymmetric-beneficiary veto path needed per R11. Operator-seat
consented affirmatively in v5.2 REPLY (`dea6401`) per the v5.1 explicit-
consent path (R11 cleanliness; not required for `both`-annotated rules
but customary).

**Codified SHA:** `61cac6d` (Protocol Bundle v5.2 ship; filled per chicken-and-egg
precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1 `509db7c` /
v5 `d66690f` / v5.1 `8ab0bbb`). Empirical basis: N=2 cumulative —
**B-005** (cycle-11, `c296105`; first operator-driven Lane B; 10 sites
in `domain/project_manager.py`; ~45min operator wall-clock; ~295k
subagent tokens; Lane V #11 ✅ READY TO SHIP at first-eligible commit)
+ **B-006-broad-A** (cycle-12, `5b68776`; 6 sites across 4 files in
cinema/+domain/location_manager.py; ~50min operator wall-clock; ~275k
subagent tokens; Lane V #12 ✅ READY TO SHIP). B-006-broad-B
(`a0493dc`, 15 sites in `web_server.py`, 243 production LoC) is the
criteria-exclusion validation point — same cycle's work correctly split
along the criteria boundary.

## Cross-seat fix-on-received-findings convention (Rule #15)

**Rule #15: Cross-seat fix-on-received-findings convention.**
*(Subtitle: when one seat closes the other seat's Lane V finding.)*

When one seat's Lane V verification surfaces a finding requiring code
fix, the OTHER seat MAY close it via standalone `fix:` commit. The
mechanism is bidirectionally symmetric (operator-closes-director-
flagged OR director-closes-operator-flagged), though only operator-
flagged-director-closes instances exist at codification time. Per
operator's Q4 recommendation + director's REPLY concurrence,
bidirectional codification at N=0 for the second direction avoids
retroactive scope-creep at v5.4+.

### Disposition recommendation shape (flagging seat)

When the flagging seat sends a `verification-report` event with a
finding requiring fix, the report MAY include a structured 3-option
disposition recommendation:

- **(a) Fold into adjacent in-flight work** (if applicable). The
  receiving seat folds the fix into the next-natural commit in their
  in-flight work.
- **(b) Standalone fix commit.** The receiving seat ships a separate
  `fix:` commit closing the finding.
- **(c) NO ACTION (informational only).** The finding is recorded for
  audit but doesn't require fix (e.g., cosmetic, doesn't affect
  correctness).

Recommendation: provide all 3 options when applicable. **Option (b)
MUST always be available as fallback** because (a) may be foreclosed
by parallel-execution timing (the receiving seat's adjacent work may
ship during the disposition window). Cycle-12 `442e154` body
explicitly acknowledged this foreclosure: "Operator-recommended
Option 1 (fold into broad-B's brief) was missed due to broad-B's
implementer commit landing during Lane V #12 dispatch window."

### Severity-vs-option advisory matrix (R-Q2-1 refined)

Per director's R-Q2-1 refinement at v5.3 REPLY, severity guides
default option choice without binding the receiving seat:

| Severity | Default option | Notes |
|---|---|---|
| **CRITICAL** | **preferred (b) standalone fix** | Option (a) fold-in **allowed only with explicit-justification in commit body** (e.g., "folded into adjacent fix commit X because same-file ≤5 LoC; audit-trail preserved via Lane V # citation in body"). Option (c) NO ACTION not permitted for CRITICAL by definition. |
| **IMPORTANT** | option (a) preferred if fold-able; else (b) | Fold-in is fast close path when adjacent work is naturally compatible. |
| **MINOR** | either (a) or (b) per scope | Sub-2-LoC mechanical fix → (a); structural OR multi-file → (b). |
| **INFORMATIONAL** | option (c) NO ACTION acceptable | Cosmetic / documentation / observation-only findings. |

The matrix is **advisory, not binding** — receiving seat retains
discretion. R-Q2-1's refinement of "CRITICAL never (a) fold" to
"preferred (b); (a) with explicit-justification" preserves the
burying-risk concern (audit clarity) while allowing legitimate
fold-in scenarios (same-file ≤5 LoC adjacent commit; in-flight `fix:`
commit composition; urgent close-loop timing).

### Receiving seat's response (closing seat)

The receiving seat reads the disposition + chooses based on:

- **Timing.** If (a)'s adjacent work has already shipped, (b) is the
  fallback. If (a)'s adjacent work is in-flight + the fold-in is
  cheap, (a) is preferred. If (a) is not applicable, (b).
- **Scope.** If the fix is sub-2-LoC + literal mechanical change, (a)
  is preferred (less commit-churn). If the fix is structural OR
  spans multiple files, (b) is preferred (clean diff per concern).
- **Severity.** Per the matrix above. R-Q2-1 escape-hatch for CRITICAL
  fold-in requires explicit-justification in commit body.

The receiving seat's option choice is binding once committed; rollback
requires another REPLY cycle (or escalation to user).

### Commit-body convention (closing commit)

Cross-seat fix-on-received-findings commits MUST follow these
conventions:

1. **Commit subject:** reference originating Lane V # OR finding ID
   (loose format per Q3 silent-accept — substantive requirement is
   the reference exists somewhere in the commit's text).
   - Examples: `fix(web): close Lane V #12 I1 — discriminate ValidationError from ValueError` (`442e154`); `fix(web): close M-3 — use logger.error with stack trace at api_train_lora::_runner exception handler` (`336403d`).

2. **Commit body:** cite operator's disposition recommendation + note
   which option (a/b/c) was chosen + brief why.

3. **Race-ack body:** standard per Rule #5 + #7. Note any state shift
   during the close-loop window.

4. **Co-Authored-By trailer:** standard per system prompt.

### Audit-trail discipline

The full lifecycle of any cross-seat closure is reconstructable from:

- **Mailbox archive:** operator's `verification-report` event with
  the finding + disposition recommendation.
- **Git log:** receiving seat's `fix:` commit with subject + body
  referencing the originating Lane V + finding ID.
- **(Optional) Next Lane V:** if the flagging seat dispatches a
  follow-up Lane V on the closing commit, that report verifies
  closure quality (cycle-12 I1 was NOT re-Lane-V'd because broad-B
  was the next Lane V eligible commit which transitively audited the
  fix; cycle-13 M-3 was NOT re-Lane-V'd because mechanical scope +
  small).

**Audit reconstructability invariant:** the lifecycle must be
reconstructable from public artifacts (mailbox + git log) WITHOUT
requiring the original session's context.

### Working criteria (dogfood for v5.3)

Per v5.1's working-criteria precedent (R-D-1 refinement) + v5.2's
per-instance wall-clock measurable framing (R-Q5-1 refinement), v5.3
codifies working criteria for Rule #15 invocation:

- **C1: Cross-seat fix commit subject cites Lane V # OR finding ID.**
  Measurable per-commit via grep: `git log --oneline --grep='close Lane V\|close M-\|close F-\|close I'`.
  N=2 instances ALREADY satisfy this (`442e154` + `336403d`).

- **C2: Operator's verification-report event includes 3-option
  disposition when fix is required.** Measurable per-event via
  mailbox-archive inspection. N=2 instances ALREADY satisfy this
  (Lane V #12 + Lane V #13 reports at
  `coordination/mailbox/sent/2026-05-27T02-30-00Z` +
  `2026-05-27T03-00-00Z`).

- **C3: Receiving seat's commit body cites disposition option choice.**
  Measurable per-commit via commit body grep. N=2 instances ALREADY
  satisfy this (`442e154` body acknowledges option 1 foreclosed →
  option 2 chosen; `336403d` body closes the DEFER M-3 via standalone
  fix).

- **C4: Cross-seat closure completes within ~1 session OR explicit
  cross-cycle DEFER acknowledgment** (per Q5 silent-accept). Per-
  instance wall-clock measurable. N=1: ~minutes (intra-cycle); N=2:
  ~half day (cross-cycle DEFER-acknowledged). Both within criterion.
  DEFER findings may legitimately take many cycles — wall-clock
  upper-bound would force premature closure (Q5 reasoning).

### Telemetry tracking (Q6 silent-accept)

Per Q6 silent-accept, Rule #15 instances are tracked as a separate
metric in cumulative v4.1 telemetry alongside fix-on-own-findings
(N=9 cumulative pre-cycle-12). After 2-3 cycles, if no operationally-
relevant difference emerges between the two categories, telemetry
can merge into a single "fix-following-Lane-V" count at v5.5+
without data loss.

### Composition with other rules

- **Rule #2 (signaling):** verification-report event is the formal
  signal; closing seat MAY narrate in chat per Rule #2.
- **Rule #5 + #7 (race-ack + pre-commit re-verify):** apply to every
  closing commit; particular care during parallel-execution windows
  where option (a) foreclosure can occur mid-write.
- **Rule #8 (mailbox authority):** verification-report event with
  disposition obligates the receiving seat to act per its content
  (one of (a)/(b)/(c) options).
- **Rule #9 (independent reviewer + parallelism):** Rule #15 is the
  closure-mechanism for findings produced by Rule #9's Lane V
  dispatch shape. The two rules compose into the full Lane V
  flag-disposition-close lifecycle.
- **Rule #10 (joint-team mode):** cross-seat closure is a
  specialization mechanism; either seat can close based on disposition
  + timing + scope, not based on hierarchy.
- **Rule #14 (operator-driven Lane B template):** Rule #14's Stage 4
  + Stage 5 (Lane V dispatch + verification-report) feeds into Rule
  #15's closure mechanism for any findings the Lane V surfaces.

### Beneficiary (per R11)

**Beneficiary: both** seats.

Rule #15 enables both seats (codifies a cross-seat closure mechanism
that previously operated ad-hoc) AND constrains both seats (formalizes
the disposition + commit-body convention). The mechanism is
bidirectionally symmetric — operator MAY close director-flagged
findings via the same shape, even though N=0 instances of that
direction exist at codification time. Per Q4 silent-accept,
codification at N=0 for the second direction avoids retroactive
scope-creep at v5.4+.

No asymmetric-beneficiary veto path needed per R11. Director-seat
consented affirmatively in v5.3 REPLY (`3a0e433`) per the v5.1/v5.2
explicit-consent customary path. Operator-seat (drafter) consented
affirmatively in proposal sign-off (`dc7df5d`).

**Codified SHA:** `24c145a` (Protocol Bundle v5.3 ship; filled per chicken-and-
egg precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1
`509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2 `61cac6d`). Empirical
basis: N=2 cumulative — **`442e154`** (cycle-12; director closes
operator's Lane V #12 I1 — IMPORTANT-advisory severity; ValidationError-
swallow at broad-A helper caller sites; option 2 chosen because
operator's recommended option 1 fold-into-broad-B-brief was foreclosed
by parallel-execution timing; intra-cycle close ~minutes after Lane V
#12 report) + **`336403d`** (cycle-13 entry; director closes operator's
Lane V #13 M-3 — MINOR DEFER severity; thread-swallow observability
hardening via `logger.error` + `exc_info=True`; option 2 chosen for
the DEFER-categorized finding; cross-cycle close ~half day after Lane
V #13 report).

The N=2 evidence spans severity (IMPORTANT → MINOR-DEFER), timing
(intra-cycle → cross-cycle), and disposition route (option 1 foreclosed
→ DEFER-acknowledged) — empirically distributed across the convention's
full operational shape.

## User-direction without owner-spec (Rule #16)

**Rule #16: User-direction without owner-spec.**
*(Subtitle: complementary-parallel work with mandatory convergence.)*

When user-principal direction reaches both seats simultaneously without
explicit owner specification, both seats MAY interpret it as joint-team
work and produce complementary parallel deliverables. **The second seat
to ship (by git timestamp) MUST send a follow-up coordination event
within 30 minutes of the second commit landing**, acknowledging the
parallel deliverable and proposing a convergence path (REPLY-cycle /
merge / delegation / further parallelism).

**Variant (pre-commit-detected race).** If the receiving seat has not
yet committed but detects the conflict via the Rule #7 pre-commit gate,
it MAY discard the pre-commit and send a convergence event offering its
content as REPLY-cycle input (preserves the work's value without
committing a parallel doc). Silent ship of a second deliverable without
a coordination event = Rule #2 §"Signaling" violation.

**Why net-positive, not merely tolerated.** Cycle-16's Shape-A instances
produced *complementary coverage* that improved synthesis quality rather
than redundant churn: the director closing-report (`e4615c7`,
findings-authority view) and operator Tier-D brief (`2c9ee9f`,
validation-design view) informed each other; brief v2.0 (`c360952`)
adopted structure from the operator scaffold while reframing through
director synthesis. The capstone instance: the user-principal handed the
SAME brief-2.0 design advisory to BOTH seats ("read my advice / act as
you see fit" → operator; "continue as director" → director); both
independently designed a near-identical insight-achievement mechanism
(five-for-five decision convergence, cold to each other), and the
operator's pre-commit-caught draft — discarded per the variant, offered
as REPLY input (`fd3dc33`) — contributed a Rule #12 grep-verified marker
correction + the INTENT-GAP/REAL-BUG/PREDICTION-ERROR divergence
classification that a solo director pass would have missed. Convergence
at REPLY-cycle-1 (`110aff6` fold + `e86dd55` convergence event). Rule #16
preserves that value while requiring the convergence discipline.

**Beneficiary (per Rule #11): `both` seats** — symmetric obligation
(either seat, whichever ships second, owes the convergence event). No
asymmetric-veto path needed. Operator-seat drafted the candidate text
(REPLY-cycle-1 `7380d43` + scaffold §3 + REPLY `fd3dc33`); director-seat
concurred (REPLY-cycle-2 `aba7755`), authored the brief §8.2 framing, and
ships this binding mirror.

**Working criteria (dogfood for v5.4, following the Rule #14/#15 pattern):**

- **C1** — convergence event cites Rule #16 explicitly + names the parallel
  deliverable's SHA (or "uncommitted, on disk" for the variant).
  Grep-auditable: `git log --grep='Rule #16'`.
- **C2** — convergence event lands within 30 min of the second deliverable's
  commit (or, for the variant, within 30 min of pre-commit-gate detection).
  Per-instance wall-clock measurable from event timestamps.
- **C3** — the proposing seat names a concrete convergence path (not just
  "noted").
- **C4** — over a cycle, Shape-A instances that follow Rule #16 produce zero
  "duplicate-work-discarded" outcomes (the value is *complementary*, not
  redundant).

**Composition with other rules.** Rule #16 is the disposition-mechanism for
the Shape-A race (the catalog's stable shape-labels are defined in brief
v2.0 §8.1, resolving the chronological-vs-shape-label "Race-N=k" drift).
It composes with Rule #2 (the convergence event IS the signal), Rule #7
(the pre-commit gate detects the variant), and Rule #10 (joint-team mode —
complementary parallel work is a specialization, not a hierarchy shift).

**Codified SHA:** `7773502` (Protocol Bundle
v5.4 ship; filled per chicken-and-egg precedent — v2 `3e57ddf` / v3
`d8f2407` / v4 `d90036b` / v4.1 `509db7c` / v5 `d66690f` / v5.1 `8ab0bbb`
/ v5.2 `61cac6d` / v5.3 `24c145a`). Empirical basis: **N=3 cumulative**
Shape-A instances (cycle-16-entry T19:19Z dispatch-claim race +
cycle-16-mid T22:25Z synthesis-doc + proposal race + cycle-16-mid T22:53Z
brief-scaffold race) + the **cycle-16-mid→close advisory-convergence
instance** (user advisory to both seats; five-for-five mechanism
convergence; pre-commit variant discharged at `fd3dc33`). User-principal
Q4 authorized codification (brief v2.0 §8.2 is the design home; this is
the binding CLAUDE.md mirror). Operator-seat consented affirmatively as
drafter; director-seat ships per Sh role partition.

## Workflow-assisted analysis lanes (Rule #17)

**Rule #17: Workflow-assisted analysis lanes.**
*(Subtitle: `/workflows` is a read-analysis multiplier, not an implementation engine.)*

Claude Code's **Dynamic Workflows** (`/workflows`, v2.1.154) orchestrates
tens–hundreds of agents in the background and returns **one synthesized
report per run** (agents' intermediate results stay in script variables;
docs document no branch/PR/per-task-commit landing, no per-unit review
gate, no custom agent types, and the edit-isolation/file-conflict
mechanism is undocumented). It is therefore a **fan-out → synthesize-a-
report engine, NOT a parallel-commit-with-review engine** — and that
single fact bounds where it fits this protocol.

When `/workflows` is available (runtime ≥ 2.1.154), **either seat MAY use
it as the execution engine for read-only, report-producing analysis at
scale** — Lane C surveys, Lane S scouting, Rule #12 grep-the-writes
audits, Rule #13 symmetric-endpoint audits, blast-radius / impact
analysis, post-roadmap reassessment, and doc-truth sweeps — subject to
ALL five guardrails:

1. **Read-only / report-output only.** Workflows MUST NOT be used for
   implementation (code-landing); implementation stays on
   `subagent-driven-development`. Rationale: no reviewable per-task
   commit, no per-unit spec+code-quality gate (Rule #9), and undocumented
   edit-isolation — none of which can carry the "one commit per task /
   two-stage review / Rule #7 race-ack" discipline.

2. **Verification discipline + post-run spot-check (folds R-OP-1).** A
   workflow report makes inventory claims ("N endpoints miss the gate").
   (a) The workflow's agent prompts MUST instruct each agent to **capture
   the command output (grep/Read) as evidence**, and the synthesized
   report MUST **cite, not assert** — subject to "no inventory claim
   without verification output" (ADR-013 / Rules #1–3) exactly as any
   director-voice doc. (b) Citations close the *asserting* half but not
   the *fabrication* half: per CC-2 precedent (Rule #9 §"Spec-reviewer
   prompt discipline" — 2 dispatches hallucinated 2 "X exists" claims), a
   report synthesized across tens of agents has the same-or-larger
   hallucination surface, and inspecting the *script* (guardrail 4) does
   NOT verify the *output's* citations after the run. So **the launching
   seat MUST spot-check a representative sample of the report's cited
   evidence (re-run a few of the grep/Read commands) before the report's
   claims re-enter the protocol (guardrail 3).** (c) For anchor /
   symbol-existence claims, prefer having the workflow **call
   `scripts/check_doc_claims.py`** (machine-verified def/anchor truth;
   operator Increment-2 tooling) over agent grep-and-assert — this closes
   the fabrication gap *by construction* for those claim types.

3. **Output re-enters the normal protocol.** A workflow report is an
   *input* to a seat's normal work; workflow agents do NOT emit mailbox
   events. Any code a seat then commits from the findings flows through
   Lane V/D + mailbox unchanged — the other seat's independent Lane V
   (Rule #9) still applies. A workflow never substitutes for Lane V.

4. **Inspect-before-launch.** Use plan-approval / "View raw script"
   before launching; do not fire blind. The launching seat owns the
   report's correctness.

5. **Hard gate ≥ 2.1.154.** Until the edit-isolation / file-conflict
   mechanics are documented or empirically confirmed, workflows MUST NOT
   write files (guardrail 1 already forbids implementation; this restates
   it for any future file-touching use).

**Composition with other rules.**
- **Lane C / Lane S:** Rule #17 is an *execution-engine* option for these
  lanes, not a new lane; their triggers/outputs are unchanged.
- **Rule #9:** unaffected — review still happens on committed code,
  post-workflow; a workflow never substitutes for the independent Lane V.
- **Rule #12 / #13:** Rule #17 *scales* these audits; their evidence
  discipline is inherited via guardrail 2.
- **Rule #14:** orthogonal — #14 governs *implementation* dispatch, #17
  governs *analysis*. A #14 pre-scope (Stage 1) MAY use a #17 workflow to
  produce its survey, then dispatch implementation the normal
  (subagent-driven) way.

**Working criteria (dogfood for v5.6):**
- **C1** — any workflow-assisted lane work cites "Rule #17" in the
  resulting artifact (report header / commit body / mailbox event).
  Grep-auditable.
- **C2** — the workflow report cites command-output evidence per unit AND
  **the launching seat spot-checks a sample of those citations** (R-OP-1).
- **C3** — read-only adherence: no workflow run lands code (guardrail 1);
  verifiable from the run producing a report + zero direct commits.
- **C4** — first real use is retro'd at v5.6: did it save
  wall-clock/context vs. manual Lane C, and did the evidence-citation +
  spot-check hold?

**Beneficiary (per R11): `both` seats.** Director gains scaled
blast-radius/impact analysis before Lane B; operator gains scaled Lane S
scouting + Rule #12/#13 audits. Symmetric — no asymmetric-veto path.

**Codified SHA:** `52658eb` (Protocol Bundle v5.5 ship; filled
per chicken-and-egg precedent — v2 `3e57ddf` / v3 `d8f2407` / v4
`d90036b` / v4.1 `509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2
`61cac6d` / v5.3 `24c145a` / v5.4 `7773502`). **Forward-looking
codification:** the feature is unavailable in the current runtime
(`claude --version` 2.1.74 / session 2.1.149, both < 2.1.154), so this
ratifies the integration *shape* + guardrails ahead of activation; the
first dogfood datapoint (C4) lands at v5.6 after the env updates.
Director-originated proposal (`2026-05-29T01-19-08Z`, per user
direction); operator-seat consented affirmatively + added R-OP-1 (folded
into guardrail 2 + C2) in REPLY `afb2c75`
(`2026-05-29T01-26-32Z`); director-seat ships per Sh role partition.

## Doc-maintenance as a verifier-scoped dispatch pattern (Rule #18)

**Rule #18: Doc-maintenance as a verifier-scoped dispatch pattern.**
*(Subtitle: a librarian wielding the verifier — persistence earned, not granted; a bridge that may self-retire.)*

Documentation drift (stale anchors, superseded refs, unpruned memory, doc-vs-code
divergence) is a real, recurring, cross-cutting cost, currently a side-duty split
across both seats (operator's Lane D + ad-hoc). It MAY be consolidated into a
**doc-maintenance dispatch** — a librarian wielding `scripts/check_doc_claims.py`,
the manifest, and the written conventions — subject to the boundary, guards, and
graduation criteria below. The role is NOT a third coder and NOT (initially) a
standing agent: it is **a dedicated executor of the truth-machinery already built**.
Its value is **loop-ownership, not memory** — the doc ecosystem lives in
machine-checkable artifacts (the verifier knows stale anchors; the manifest IS the
cross-ref web; conventions are gate-enforced), so optimizing for an agent's
accumulated memory would contradict truth-in-files (ADR-013). Give it good
instruments and a narrow shelf, not a long memory and a broad mandate.

**Form — dispatch pattern first; persistence EARNED.** Run it as a dispatch (a
senior spawns a doc-maintenance task with the doc-map + verifier + conventions in
the prompt), NOT a persistent agent on day one. This *tests* rather than assumes
whether cross-task context compounds. Graduate to a standing role ONLY on the
evidence in "Graduation" below; if fresh-prompt dispatches keep re-supplying the
structure from the artifacts, ephemeral was always sufficient (learned cheaply).

**Scope = the Guard-1 boundary = the carve-out boundary (one line).** The role OWNS
(writes directly) only the **mechanical / verifier-confirmed** slice: anchor
`--fix`, formatting, cross-reference repair, `docs/pipeline_status.toml` updates,
memory pruning per the one-line-hook discipline, sweeping the claim types the
verifier covers. The role does NOT autonomously edit **prose / claims** in
truth-files (ARCHITECTURE.md, CLAUDE.md, ADRs, memory): any **claim-changing edit**
→ the role **prepares a diff; a senior verifies the claim and lands it** (the senior
owns the hot-file write + Rule #5/#7 race-ack). "Keep the docs true and clean"
(role) vs. "decide what is true" (seniors). This **bounds the carve-out of operator's
Lane D**: the mechanical half moves to the role; the **prose-truth half stays a senior
duty** (operator's Rule #11 gating consent is to THIS bounded carve-out only — Lane D
includes prose-sync, which Guard 1 bars the role from owning).

**Guard 1 — the leash on load-bearing docs (prose is the catch).** A "mechanical"
edit can still introduce a **false claim** the verifier cannot detect (it checks
anchors + symbol existence, NOT whether a paragraph is *true*). THREE live exhibits
this session: the GitNexus phantom (ADR-016 — a doc asserting a tool that never
existed, survived 66 sessions); a Lane V #24 video-only fix-rec that was confidently
wrong (would have regressed dialogue); and the doc-maintenance proposal's OWN
provenance citing a closed F1 (`561ad6b`) as open. All prose/status claims the
verifier-as-built would NOT catch; each caught only by a senior who knew the live
state. **Therefore:** the role is autonomous ONLY on verifier-confirmed or non-claim
edits; every claim-changing edit is verifier-backed or senior-reviewed, inheriting
cite-or-don't-claim (ADR-013). **The spawning seat owns the review** of that
dispatch's claim-changing edits (parallel to Rule #17 guardrail 4).

**Guard 2 — write-contention, not coordination ceremony.** The role's docs
(ARCHITECTURE.md, CLAUDE.md, memory) are the most-contended files in the repo.
Decision for the experiment: **extended race-ack, NOT exclusive ownership** — the
role writes the low-contention mechanical slice directly; claim-changing edits go via
patch-then-senior-lands (so seniors keep inline doc-fixes; exclusive ownership grants
persistence's privileges before earned and is a graduation-time question only). Doc
work is largely serializable/idempotent (the verifier's drift-list is the natural
FIFO backlog), so direct collisions are rare and git-tiebreak + race-ack handle them.

**Invest posture — C (sequenced bridge) + sunset review.** The role and the
verifier-buildout are **partial substitutes** (more automated claim-types = less
hand-work), so the role's value is **highest today** (verifier covers only
line-anchors + manifest symbol-existence) and **declines** as operator builds out
marker-strings / SHA-refs / file-paths per the N=2 threshold. Run the dispatch now,
framed explicitly as a **bridge that may retire**, with a **sunset review** at each
verifier-buildout milestone. (Priority signal from the F1-citation exhibit: the
**SHA-ref claim-type checker** would catch that mis-citation class by construction —
worth bumping in the buildout.)

**Launch surface (today):** line-anchors + manifest symbol-existence + mechanical ops
ONLY. Marker-strings / SHA-refs / file-paths are OUT of launch scope (not yet
automated → hand-work → prose-adjacent → senior) until the verifier covers them.

**Graduation (dispatch → standing role) requires ALL of:** (a) residual doc-load
POST-automation meaningfully larger than ephemeral-subagent-sized (measured against
the post-automation baseline, NOT today's build-spike); (b) **N≥3 dispatches
re-discovering the same ecosystem structure** (a higher bar than the N=2
codification threshold); (c) prose stays TRUE under the role's own work, via the
R-OP-1 spot-check applied to the role's prepared diffs. Anchors-green is necessary
but NOT sufficient.

**Composition.** The verifier is the instrument (`check_doc_claims.py` → machine-
verified citations, closing the R-OP-1 fabrication gap by construction for covered
claim types). Rule #17: a one-time codebase-wide doc audit is a Rule #17 read-analysis
workflow; this role *runs* the verifier continuously — same instrument, different
cadence. Rule #14 orthogonal (governs implementation dispatch; this governs
doc-maintenance; implementation stays subagent-driven). Rules #12/#13 audits are
doc-maintenance inputs. ADR-013 inherited on every claim-changing edit.

**Beneficiary (per R11): `both`.** The consolidation cost lands on operator (Lane D
carve-out) → operator's consent was REQUIRED, not customary; **given, bounded to the
mechanical slice** (REPLY `d385bb2`). Director consents (REPLY `d5f3bb6`), resolving
its inline-doc-fix stake toward extended-race-ack (non-blocking). The advisor's
needs-driven framing + librarian metaphor stand; only the persistence-as-memory
justification was corrected (both seniors, independently — the convergence is the
proof it was wrong).

**Codified SHA:** `4eecb72` (Protocol Bundle v5.6 ship; filled per
chicken-and-egg precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1
`509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2 `61cac6d` / v5.3 `24c145a` / v5.4
`7773502` / v5.5 `52658eb`). **Forward-looking:** no dogfood result yet — the
graduation metrics are the first data, post-launch. **F1 facts at ship:** no F1
open (scene-transitions F1 closed `1f9d46b`, operator-acked `35c530c`; the
proposal's `561ad6b`-open citation was a stale conflation — `561ad6b` is the
2026-05-28 dialogue feat whose own F1 closed `d3fcfb0` — corrected here per ADR-013).
Principal-originated synthesis of the advisor/operator/director triangulation;
both seats consented (operator bounded carve-out + director); director-seat ships
per Sh role partition. ADR-019.

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
| **Subagent active** | Dispatch-claim event seen; WT has uncommitted changes director-attributed | **Silent.** No `.py` writes. | Director's commit lands |
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

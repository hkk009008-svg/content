<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (4270 symbols, 23493 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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

# About this document

This file is the **agent-agnostic root** for AI coding tools working in this
repo (Cursor, Aider, Copilot, Continue, Claude Code, etc.). The GitNexus
block above is auto-managed and identical to the one in `CLAUDE.md`.
Everything below is the agent-agnostic project guide — canonical project
facts plus the discipline that ships clean code here.

**Claude Code specifically:** `CLAUDE.md` is the Claude-specific companion.
It mirrors this file's discipline section using Claude's actual tool
syntax (`Agent` subagent dispatch, `subagent_type` values, prompt
templates, `Skill` invocation, `TaskCreate`/`TaskUpdate`,
`AskUserQuestion`, the `superpowers:subagent-driven-development` skill,
etc.). Claude Code agents read **both** files; this one defines the
principles, `CLAUDE.md` defines the mechanics.

**Non-Claude agents:** read this file as your source of truth. Translate
the principles ("fresh context per task", "two-stage review",
"verify-before-acting") into your tool's analogous mechanisms (new chat
session, manual diff review, `git grep` for verification, etc.).

# Session-start protocol (read me first)

**Truth lives in `ARCHITECTURE.md` at the repo root.** This file (AGENTS.md)
is the *process layer* — agent-agnostic principles (multi-task
orchestration, session discipline) shared by all AI coding tools.
`ARCHITECTURE.md` is the *truth layer* — verified facts about the pipeline,
with file:line references and a §15 smoke test. When they disagree about
facts, `ARCHITECTURE.md` wins.

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

Don't duplicate ARCHITECTURE.md content here. If you need to record
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
other authority-voice document, the author runs the verifying commands for
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
not a fact. **Never apply authority-voice over an unverified factual
claim.** Authority and verification travel together.

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

Beyond the GitNexus checks at the top of this file:

- One commit per logical slice. Run the §15 smoke block in `ARCHITECTURE.md`
  before declaring a slice done.
- Don't combine concerns. A bug fix isn't a refactor isn't a feature.
- If your change touches a documented subsystem, update the relevant
  section in `ARCHITECTURE.md` in the same PR.
- For multi-task work (≥5 sub-tasks or ≥800 LOC of total change), don't
  implement everything in your current context — orchestrate via fresh
  contexts. See "Multi-task orchestration" below.

# Multi-task orchestration

When you encounter a written plan (e.g., `docs/superpowers/plans/*.md`)
with ≥5 sub-tasks, or you've drafted one with comparable scope, the
discipline that ships clean code here is to ORCHESTRATE, not implement
everything yourself.

The mechanism: each task is handed to a **fresh context** with a curated
prompt; the result comes back as a compact report; you review it; you move
on. Your main context grows linearly with the number of tasks, not with
the volume of work — which is what prevents quality degradation across
long (1M / 2M+ token) sessions.

**Claude Code:** see `CLAUDE.md` § "Working a Multi-Task Plan" for the
tool-specific implementation (Agent subagent dispatch, prompt templates,
`superpowers:subagent-driven-development` skill, TaskCreate tracking).
Everything below is the universal principle set.

## When to invoke

| Signal | Action |
|---|---|
| Written plan with 5+ mostly-independent sub-tasks | Orchestrate via fresh contexts |
| Single change OR tightly-coupled tasks | Stay in your current context |
| Interactive exploration ("how does X work?") | Stay in your current context |

## The per-task loop (sequential, never parallel)

For each task:

1. **Mark in_progress** in your task tracker.
2. **Dispatch an implementer to a fresh context.** Whatever your tool's
   mechanism is (Claude: `Agent` subagent; Cursor: new chat; Aider: new
   session; manual: co-developer with a written ticket). Give them a
   curated prompt — see "Prompt template" below.
3. **Read the implementer's report.** Don't trust it blindly; their
   self-review may be optimistic.
4. **Dispatch a spec compliance reviewer to a fresh context.** Their job:
   read the actual diff and compare to the spec line-by-line. They should
   verify by reading code, not by trusting the report.
5. If spec issues → fix loop (see "Delegation heuristics") → re-review.
6. **Dispatch a code quality reviewer to a fresh context.** Strengths,
   Issues (Critical / Important / Minor), Assessment. Pass the BASE_SHA
   and HEAD_SHA so they can scope the diff cleanly.
7. If quality issues → fix loop → re-review.
8. **Mark completed.** Move to next task.

After all tasks: run a final cross-cutting reviewer with the full
baseline-to-HEAD diff, then merge / open PR / hand off.

**Never dispatch multiple implementers in parallel** — they'd conflict on
files. Reviewers in parallel are fine but rarely necessary.

## Delegation heuristics — Lane A / B / C

Three lanes for each unit of work. Match the lane to the task — wrong-lane
choices either waste resources (Lane B for trivial fixes) or burn your
main context (Lane A for big work that should be delegated).

**Lane A — execute in your current context (manual edit / direct tool):**
- File is **already loaded in your context** AND change is ≤5 LOC
- Pure mechanical edit: rename, type alias, comment improvement, format fix
- A reviewer flagged a 1-2 line fix with clear instructions and you can see the surrounding code
- Test-data tweak (tighten a tolerance, swap a placeholder value)
- Final polish after a fresh implementer's commit you just reviewed

Cost: minimal. Risk: low — you can see what you're changing.

**Lane B — fresh implementer in an isolated context:**
- Change touches ≥3 files OR a domain you haven't read yet
- ≥5 LOC of structural change (new function, new component, new module)
- Design judgment needed (naming, abstraction, layout choice)
- Multi-step task that benefits from fresh-eyes context
- Anything where the implementer needs to discover state you don't yet have

Cost: full task context in the fresh instance. Risk: low if the prompt is
well-formed; high if it's "implement task X" with no context.

**Lane C — read-only survey (search / grep, no writes):**
- "Where is X defined?" / "Which files reference Y?" — open-ended search
- Codebase exploration before deciding how to dispatch Lane B
- Verifying a reviewer's claim before acting on it

Cost: read-only, scoped. Use when you need findings, not a code change.

**Decision tree:**
1. Is this a 1-5 line mechanical change in a file you already understand? → **Lane A**
2. Is this open-ended search across multiple files with no code change? → **Lane C**
3. Everything else → **Lane B**
4. Special case: if a reviewer's claim contradicts what you remember about
   upstream behavior, do a quick **Lane C survey** before fixing. The
   reviewer may be wrong.

## Prompt template (for Lane B implementers)

The fresh instance has no memory of your session. The prompt must let them
act **cold**. A good implementer prompt is 80-150 lines and includes:

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

Per `AGENTS.md` (or `CLAUDE.md` if you're Claude Code):
1. Run impact analysis before editing existing symbols (GitNexus or grep fallback)
2. Run scope check after edits — confirm only expected files changed
3. <task-specific gotcha>
4. **Brief-pattern reference adherence.** When the brief says "mirror pattern X at file:line" or "use the existing _foo_-style endpoint," verify the FULL shape of X — signature, route path, scope parameters, error handling, lock guards — not just the called function. Brief-pattern references are implicit specs; silent deviations cascade. If the named helper doesn't exist or the wording is ambiguous, report the divergence in your status BEFORE implementing.
5. **Scoping check on new endpoints.** When adding/touching an HTTP endpoint operating on a tenant- or project-scoped resource, verify the route takes the scoping ID explicitly. Do NOT scan to find a matching resource by leaf ID alone — IDs can collide across tenants/projects depending on the ID-generation scheme. Inspect at least one similar existing endpoint in the same file to confirm the route shape and scoping.

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

## Report Format

- Status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- Impact findings (callers, risk) or grep-fallback equivalent
- Files changed (paths only)
- Verification command output
- Commit SHA — capture from `git log` AFTER post-commit hook activity settles, not from `git commit` stdout. If the project has a post-commit hook that amends another file (e.g., a state snapshot), the SHA from stdout may be stale by one.
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — the fresh instance
burns context discovering things you already know, and the report comes
back vague.

For spec and code-quality reviewer prompts, see `CLAUDE.md` §§ "Spec
reviewer prompt template" and "Code quality reviewer prompt template" —
the structure transfers directly to non-Claude tools.

## Hardening notes — provenance for the implementer-template additions

Items 4-5 in "Project conventions you MUST follow" and the Commit SHA
capture guidance in "Report Format" are hardened in from cycle-5 +
cycle-6 failure modes. Carry them forward in future dispatches; if you
trim the template, do NOT trim these:

- **Item 4 (brief-pattern adherence)** — observed failure mode: a brief
  said "mirror the `_mutate_shot` pattern" but `_mutate_shot` didn't
  exist; the actual pattern used `mutate_project` with a pid-scoped
  route. Implementer correctly used `mutate_project` but missed the
  pid-scoping. Operator-seat's post-commit verification caught the
  divergence as a CRITICAL finding. Fix required a follow-up commit
  + route migration in callers.
- **Item 5 (scoping check)** — same root cause as item 4, codified as
  a standing convention so the next implementer catches the failure
  mode at design time, not via post-commit verification. Cost
  comparison: design-time check is ~1 grep; post-commit verification
  catch cost ~200k+ tokens + the fix commit's developer-time. Front-load
  is cheap.
- **Commit SHA capture** — observed failure mode: implementer-reported
  SHAs sometimes 1 commit stale because a post-commit hook amends a
  state-snapshot file, changing HEAD after `git commit` returns. Capturing
  from `git log` after the hook settles is the reliable source.

## Plan vs. source — the divergence rule

Plans sketch values that may be stale by execution time:
- Hex codes guessed before reading the actual mockup
- Function names not aligned with the file's naming convention
- Type fields that don't exist yet
- Library APIs the plan author assumed exist

**Standing instruction to every implementer:** "The plan's sketch is
approximate. Where the plan matches the actual source / mockup / type /
API, use the plan's value. Where they differ, use the actual value and
report the divergence in your status report."

This catches the plan being wrong without blocking on a re-spec.

## Commit discipline for reviewability

- **Baseline commit first.** If the working tree has uncommitted prep work
  foundational to the plan, commit it as `chore(baseline): ...` BEFORE
  dispatching any implementer. Otherwise each task's diff is polluted
  with prep noise.
- **One commit per task.** Don't amend across tasks. Reviewers need a
  clean BASE_SHA..HEAD_SHA range.
- **Fix commits are separate from feature commits.** When a reviewer
  finds an issue, the fix is its own commit on top — don't `--amend`.
  This preserves the audit trail.
- **Commit message convention:** `<type>(<scope>): <subject>` plus a
  short body explaining the *why* if non-obvious.

## Context hygiene (the long-session rule)

Quality degrades across very long contexts only if you let large bodies
of text accumulate. Mitigate by:

- **Don't read files >500 lines in your own context.** Dispatch a fresh
  instance with the specific question.
- **Don't re-read files you just edited.** Your tool should track state;
  if the edit succeeded, trust it.
- **Spot-check, don't re-verify.** If a reviewer says "spec compliant,"
  trust it. If something feels off, do a targeted single-file read or
  grep, not a full re-review.
- **Summaries in your main context, full content in fresh instances.**
  Each fresh instance digests 40-60k tokens of code and returns a
  500-2000 token summary. That's the ~20× compression you're paying for.

## Compaction signals and what to do

When your tool summarizes/truncates older messages (compaction), watch for:

- You start to forget file paths or commit SHAs you used earlier
- Reviewer prompts feel harder to assemble because you can't recall the
  implementer's exact claims
- A system message mentions summarization or truncation
- Token-count visibility (if shown) crosses ~70% of the context window

**Respond by:**
- **Commit pending work immediately.** Git is durable; chat is not.
- **Record open decisions in your task tracker.** Task descriptions
  persist across compactions.
- **Dispatch fresh instances earlier than you normally would** — even
  for borderline Lane-A work. The compact report survives compaction
  better than scattered conversation.
- **Don't re-read files to "refresh" your context.** You'll burn the
  remaining budget faster.
- **Surface state to the operator.** If you can't reliably complete the
  remaining work, say so and let them decide whether to continue or
  start a fresh session.

## Quality vs. throughput watchpoints

Moving fast through multi-task plans means some checks short-circuit.
Specific risk patterns to guard against:

| Watchpoint | What can slip through | Mitigation |
|---|---|---|
| **Concurrency in new code** | Missing locks around thread-shared state (SQLite, globals, `_*_lock` adjacent code) — spec review often misses these. | When the implementer touches thread-shared state, explicitly ask the code reviewer to check lock discipline. |
| **Public-API semantic changes** | Refactors that change prop/parameter names can be visually correct but semantically wrong. | For interface refactors, the spec reviewer must verify call-site mappings are semantically correct, not just that output matches. |
| **"Just X" with structural drift** | An implementer extends beyond a stated constraint (e.g., "only className strings" turns into local const extraction). | When an implementer deviates from a hard constraint, verify the deviation is purely additive and re-run touched tests. |
| **Plan-vs-convention naming conflicts** | A field labeled one way in plan, differently in production code. Following plan literally creates a contract mismatch. | When plan and project convention conflict, surface the choice to the operator rather than defaulting either way. |
| **Pre-existing failures masking new ones** | A flaky test failing throughout makes a new failure invisible. | Mark pre-existing failures `xfail` (or tighten tolerance) early in the branch so NEW failures stand out. |

**Pattern:** the throughput optimization is "ship when the code quality
reviewer says approve." The watchpoint is making sure the reviewer is
*checking the right things*. A reviewer prompt that doesn't mention
threading won't catch a missing lock — you have to tell them.

## Failure modes and false positives

Reviewers and tooling will sometimes be wrong. Recognizing the pattern
prevents acting on bad input.

**Reviewer false positives observed in practice:**

1. **"Missing requirement" claims that contradict upstream behavior** —
   The reviewer didn't trace upstream semantics (e.g., flagged "buffer
   not capped" when the buffer is bounded at its source). **Mitigation:**
   when a "missing requirement" claim contradicts the dispatch prompt's
   stated upstream behavior, verify with a targeted grep before fixing.

2. **Sequencing concerns based on nominal task order** — Reviewer assumed
   the plan's nominal task order; your actual dispatch order may already
   satisfy the concern. **Mitigation:** check your task tracker before
   re-arranging work.

3. **"Function X not found in module Y"** — Reviewer grepped the wrong
   file. The function lived in a sibling module. **Mitigation:** if a
   reviewer says "not found," double-check the scope you provided in
   their prompt. The answer is often one file over.

4. **Security warnings on instruction-following actions** — Automated
   scanners can flag compliant behavior (e.g., the operator/system
   prompt explicitly asks for behavior the scanner doesn't recognize).
   **Mitigation:** if your action is clearly compliant with explicit
   operator/system instructions, proceed and note the false positive.

5. **Fresh instance "tool X not available"** — Fresh instances may have
   a different tool environment than you do (different MCP servers,
   different env vars, etc.). **Mitigation:** don't require fresh
   instances to use tools you have; provide fallback instructions
   (grep + file reading instead of MCP impact analysis) in their prompt.

**Tool/environment failure modes:**

6. **Edit tools that require Read first** — Many tools (including
   Claude Code's `Edit`) require a `Read` on a file before edits.
   **Mitigation:** always read (even a small window) before the first
   edit on a file.

7. **Wrong Python interpreter** — System `python3` may lack project
   test deps; the project's venv has them. **Mitigation:** use the
   project's binary explicitly: `.venv/bin/python -m pytest ...`.

8. **Background-task completion notifications** — Async notifications
   may appear in your conversation but are NOT operator input.
   **Mitigation:** treat them as informational; don't confuse them with
   operator acknowledgement of a pending question.

**Detection pattern:** when a tool/reviewer/warning contradicts what you
already know to be true, do a quick targeted verification (single read,
single grep) before acting on the claim. A 5-second check prevents a
wrong fix that itself needs reverting.

## When NOT to orchestrate

- **Single-step tasks.** Just do them.
- **Tightly-coupled refactors** where each change depends on the
  previous change's state in a way that prep-then-dispatch can't
  capture cleanly.
- **Interactive exploration** ("what does X do?"). Fresh-instance
  overhead hurts here.
- **Tasks needing constant operator feedback** — interactive sessions
  fit better.

# Director-Operator Concurrent Operation

This project runs two parallel agent sessions by design.

## Two-seat team model (Protocol Bundle v5)

**Director-seat** and **operator-seat** are two seats of one team,
with different specializations. Both serve the user-principal.
Neither is senior to the other; specialization is cognitive-load
distribution, not hierarchy.

| Seat | Specializes in | Why this seat? |
|---|---|---|
| **Director-seat** | Strategic synthesis: brief authoring, ADR composition, push decisions, post-roadmap reassessment, cross-cycle planning, codifying discipline | Strategic work requires synthesizing cross-cycle context |
| **Operator-seat** | Operational verification: post-commit Lane V reviewer dispatch, Lane D doc-sync, transplant-handoff refresh, counter-bump dispositions, mailbox event authoring | Operational work requires cold-context independence (Rule #9) |

Both seats are equal in authority within their specialization. Within
Lane V/D/S, operator-seat acts unilaterally (mailbox events bind
director per Rule #8). Within strategic work (briefs, ADRs, push),
director-seat acts unilaterally. Cross-cutting decisions (protocol
changes, role-partition adjustments) go through the proposal cycle.

**User is the principal.** Both seats serve the user; neither is the
boss of the other. When agents disagree, escalate to user (per
Disagreement protocol below). When user direction is given, it
overrides any agent's discretion (per "Instruction Priority"
hierarchy: user > git > mailbox > STATE.md > default).

The labels below ("Strategic-seat-default," "Operational-seat-default,"
"Cross-cutting (proposal cycle)") replace prior v1-v4 labels
("Director-only," "Operator-only," "Shared"). Lane assignments are
unchanged; only the framing is reworded to remove the implicit
senior/junior asymmetry.

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
- Codifying new precedents into discipline rules (`CLAUDE.md` / this
  file) — operator may draft; director commits.
- Memory writes (project memory index + memory files) — same
  draft-then-handoff shape; memories shape future sessions of both
  roles, so the curation call is director's.

**Operational-seat-default** (operator-seat unless explicitly handed off):

- Counter-bump dispositions (the auto-generated GitNexus-block edits at
  the top of `CLAUDE.md` / this file) — folded into the nearest
  relevant code commit or shipped as `chore(baseline)`.
- Trust-but-verify reads after each commit
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
  BEFORE dispatching an implementer subagent, naming target files /
  symbols + brief reference + specific intel needed. Operator
  conducts Lane C-style read-only survey of named targets, sends
  `scout-report` event with findings. ~10-20 min operator-context-burn
  per scout (pure read; no subagent). Opt-in: director chooses when
  to send `scout-request`.

**Strategic-seat-default (Lane B):**

- **Implementer dispatch for a new session (Lane B)** — director-seat
  dispatches; operator-seat does not. v1-v4's "Shared" label was a
  practice-vs-spec divergence v5 closes per the Sh codification. Future
  v5.1+ may open Lane B to operator-seat for small domain-partitioned
  work; "default" leaves that door open.

**Cross-cutting (either may drive — see signaling rules):**

- Spec reviewer + code-quality reviewer dispatch (both seats run their
  own — per Rule #9 they operate cold-context independently)
- Verification gates (smoke / pytest / tsc)
- Applying review IMPORTANTs **and minors** — `chore(test)` /
  `chore(ui)` / `chore` commits folding review feedback are claimed
  by whoever announces first
- Closing-report drafting (partitioned by document: each seat owns
  their own transplant handoff)

## Signaling: narrate before acting on shared tasks

Whoever is active first claims a shared task by **stating the action in
conversation before doing it**:

> "Dispatching Session 6 implementer (foreground)."
> "Dispatching parallel reviewers (spec + code-quality) on `d516d2a..b25da2e`."

The other party, on seeing the announcement:

- Does not duplicate the claimed action.
- May pre-stage complementary work without committing (locate fixes,
  draft prompts, validate type shapes, prepare closing reports).
- Reports back what they observed and what they're standing by for.

## State-asserting writes: gate on `git log --oneline -5`

The `git log --oneline -5` precondition also applies to **any write
that makes a claim about current state** — handoff docs, status
reports, commit bodies naming HEAD or branch counts. Operator-only
tasks (like updating the transplant handoff) don't race on
*ownership*, but the *content* races on currency: the other party
may have shipped between your write and your commit.

Rule: immediately before any state-asserting write or edit, run
`git log --oneline -5` and use that just-observed state in the
content. If state moves between write and commit, re-edit and use
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
requires `git log --oneline -5` *before* a state-asserting write/edit
(pre-write gate). Rule #7 is the matching *pre-commit* gate. Together
they close the hole where state can move between your write and your
commit — observed in `a6e3ff1` (Monitor.tsx shipped during operator's
handoff write; operator caught the drift in their race-ack body).

Immediately before `git commit` for any state-asserting commit, run
`git log --oneline -5` AND read `coordination/mailbox/sent/` for events
newer than your write-start time. Compare to the pre-write check (Rule
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
pre-write gate. The two rules pair to close the write-and-commit hole
but are separately invocable, measurable, and retire-able.

## Mailbox events have authority equal to user-relayed signals (Rule #8)

A sent mailbox event (file in `coordination/mailbox/sent/`) obligates
the receiving role to act per its content. Ignoring or deferring a sent
mailbox event requires the same justification as ignoring a direct user
instruction.

**Authority conflict resolution:** user direct instructions override
mailbox events; mailbox events override default behavior. (Mirrors and
extends the existing instruction-priority hierarchy.)

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
  per the existing instruction-priority hierarchy — user wins.

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
cross-system context. Coalescing is operator discretion; when
applied, the `verification-report` event's `related-commits` field
lists all covered SHAs, and the prompt's `BASE_SHA..HEAD_SHA` covers
the full range.

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
> including the claim in your report."

Without this discipline, hallucinated existence claims pass through
to director's main context as CRITICAL findings that director must
independently disprove. With it, the hallucination is contained
inside the subagent.

If hallucinations persist after CC-2 codification (≥1 more in
cycle-7+ Lane V dispatches), v4.2 should consider CC-2 options 2
(third lightweight verifier pass) or 3 (different subagent type
for spec review).

## Joint-team mode (Rule #10)

**Rule #10: Joint-team mode.** *(Subtitle: co-agent mode.)*

Director-seat and operator-seat are two seats of one team. Both serve
the user-principal. Neither is senior to the other; specialization is
cognitive-load distribution, not hierarchy.

**Practical implications:**

- Within their specialization lane, each seat acts unilaterally.
- Cross-cutting decisions (protocol changes, role-partition
  adjustments) go through the proposal cycle.
- When agents disagree after 2 REPLY cycles, escalate to user.
- User direction overrides agent discretion (per "Instruction
  Priority" hierarchy: user > git > mailbox > STATE.md > default).
- Both seats use the same commit-body etiquette + Rule #7 + Rule #5
  — these are TEAM disciplines.

## Codification bias check (Rule #11)

**Rule #11: Codification bias check.** When proposing a new rule,
the codifier MUST flag the rule's **primary beneficiary** in the
proposal frontmatter:

- `beneficiary: director-seat` — primarily reduces director-seat's
  friction
- `beneficiary: operator-seat` — primarily reduces operator-seat's
  friction
- `beneficiary: both` — symmetric
- `beneficiary: user` — primarily benefits the user-principal

If `beneficiary` is asymmetric, the OTHER seat has explicit veto in
the REPLY cycle. If non-beneficiary seat declines, the rule is
downgraded to "advisory" or revised until both consent.

Retroactive snapshot of Rules 1-9 (4 both / 1 user / 3 operator-seat
/ 0 director-seat) lives in `docs/PROTOCOL-RULES-LOG.md`.

## Disagreement protocol (v5)

When operator-seat disagrees with a director REPLY refinement (or
vice versa), the disagreeing seat:

1. States the disagreement explicitly in the next-cycle revision
2. Provides project-data-grounded evidence
3. Proposes one of three resolutions: counter-refinement, defer to
   v(N+1), or acceptance criterion (R-V1 model)

**Resolution paths:** silent-accept / re-REPLY / 2-cycle limit then
escalate to user.

**2-cycle counting (v5 §C-D-1):** "2 cycles" = director's REPLYs
after the initial proposal, not operator's revisions. Flow: proposal
→ REPLY (1) → revise → REPLY (2) → revise → escalate to user. Total
5 documents before escalation.

## Emergency handling protocol (v5)

**Scope (per v5 §R-E-1).** Emergency = one of four categories:

1. Production-affecting OR user-data-integrity issue
2. Security-critical (active-exploit CVE)
3. Active bleed-rate (cost / resource / token burn per minute)
4. External time-pressure (deadline at risk)

Events outside these are NOT emergencies; use normal role partition
+ proposal cycle.

**Protocol:**

1. First-noticer claims initial response (chat narration + mailbox
   `dispatch-claim` with `urgency: emergency`).
2. Triage discipline: stop-the-bleed first.
3. Cross-seat-temporary-authority if normally-authoritative seat is
   in transplant/context-exhaustion. Temporary seat notes "acting
   under v5 §E temporary authority" in commit body.
4. Post-incident review within 1 session: write incident note in
   `docs/INCIDENT-LOG.md`; review for protocol gaps.

## Git is the tiebreaker

If both parties accidentally dispatch the same subagent, the first
commit to land wins. The other's subagent output is discarded. Cost:
one wasted subagent context.

Before acting on any shared task, run `git log --oneline -3` first.
A commit that already addresses the task means the task is closed;
do not duplicate.

## When the other party is offline

If a session ends (context limit, end-of-day, explicit handoff), the
remaining party takes the full loop unilaterally. No signaling needed
until the next session of the absent role picks up via handoff doc.

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

Pre-locate fixes for flagged divergences. Survey carry-forward items
to prep the post-roadmap reassessment. Validate data shapes the
implementer assumed. Draft closing-report skeleton. Spot stale doc
claims and queue corrections.

Do NOT edit code while the other party's subagent is mid-edit on the
same files, nor commit doc updates that contradict in-flight work,
nor dispatch a duplicate reviewer, nor run `pytest` against a dirty
working tree mid-implementation.

# Coordinating with CLAUDE.md

This file (`AGENTS.md`) and `CLAUDE.md` are sibling documents. They share
the GitNexus block (auto-managed) and the Architecture Preamble. They
diverge on tooling specifics:

| Topic | This file (AGENTS.md) | CLAUDE.md |
|---|---|---|
| GitNexus rules | ✓ (canonical) | ✓ (canonical, identical) |
| Architecture + invariants | ✓ (canonical) | ✓ (canonical, identical) |
| Multi-task discipline | ✓ Universal principles | ✓ Same principles + Claude tool syntax |
| Lane A/B/C heuristic | ✓ Universal | ✓ Same |
| Prompt templates | ✓ Universal skeleton | ✓ Same + Claude-specific examples |
| Tool syntax (`Agent`, `Skill`, `TaskCreate`) | — | ✓ Claude Code only |
| `superpowers:*` skill invocation | — | ✓ Claude Code only |
| `AskUserQuestion` discipline | — | ✓ Claude Code only |

**If a Claude Code agent reads both files** and the guidance differs, the
order of precedence is:
1. The operator's explicit instructions (highest)
2. `CLAUDE.md` Claude-specific extensions
3. This file's universal principles
4. The model's default behavior (lowest)

**If a non-Claude agent reads only this file:** the universal principles
above are complete and standalone. Apply them with your tool's analogous
mechanisms. The `CLAUDE.md` references are optional reading.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (3308 symbols, 21050 relationships, 281 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
- Commit SHA
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — the fresh instance
burns context discovering things you already know, and the report comes
back vague.

For spec and code-quality reviewer prompts, see `CLAUDE.md` §§ "Spec
reviewer prompt template" and "Code quality reviewer prompt template" —
the structure transfers directly to non-Claude tools.

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

This project runs two parallel agent sessions by design:

- **Director** — strategic driver. Authors briefs, decides what ships
  next, reframes scope, codifies precedents, owns push-to-origin and
  post-roadmap reassessment.
- **Operator** — execution driver. Runs the per-session loop above
  (implementer + reviewers + fix loops + commits), produces closing
  reports, surfaces findings.

They share a working tree and commit history. Friction arises not on
commits (git serializes those) but on **planning and dispatch overlap** —
both parties reaching for the same shared task at the same time. The
rules below partition work and define a signaling protocol so the cost
of running both is roughly zero.

## Role partition

**Director-only (never claimed by operator):**

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

**Operator-only (never claimed by director):**

- Counter-bump dispositions (the auto-generated GitNexus-block edits at
  the top of `CLAUDE.md` / this file) — folded into the nearest
  relevant code commit or shipped as `chore(baseline)`.
- Trust-but-verify reads after each commit
- Updating the operator transplant handoff
  (`docs/HANDOFF-operator-transplant-*.md`)

**Shared (either may drive — see signaling rules):**

- Implementer dispatch for a new session
- Spec reviewer + code-quality reviewer dispatch
- Verification gates (smoke / pytest / tsc)
- Applying review IMPORTANTs **and minors** — `chore(test)` /
  `chore(ui)` / `chore` commits folding review feedback are claimed
  by whoever announces first
- Closing-report drafting

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

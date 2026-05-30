# About this document

This file is the **agent-agnostic root** for AI coding tools working in this
repo (Cursor, Aider, Copilot, Continue, Claude Code, etc.).
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

# The user-principal's intent for this program (read PROGRAM-MANUAL.md)

**The user-principal has designated [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md)
— with the dense per-subsystem research in
[docs/PROGRAM-MANUAL-digests.md](docs/PROGRAM-MANUAL-digests.md) — as the canonical
expression of their intent for this program.** This is a standing directive to
every seat, current and future, director and operator: read the manual early in a
session to internalize *what we are building* and *how the user wants it operated*.

- **What the program is for** — turning a script/idea into finished, photorealistic
  cinematic video with synced audio (manual §1–§2).
- **How the user wants it driven** — to realize the program's **full capability**.
  The capability-maximization user manual (§5: quality tiers, the capability-knobs
  playbook, the "to maximize X, do Y" recipes) is the direct statement of that
  intent; §3/§4/§6 show how the machine interconnects so changes respect the whole.

When a decision trades off against *realizing the program's full capability for AI
video generation*, that is a trade against the user's stated intent — surface it
rather than silently making the call. The manual defines what "good" means here;
keep it true as the code evolves (same staleness discipline as `ARCHITECTURE.md`:
if a change makes a manual claim stale, fix the manual in the same change).

# Repo doc map

| Need to | Read |
|---|---|
| Get oriented (purpose + quick start) | [README.md](README.md) |
| Understand the code (verified truth — what's where, what does what) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Learn the whole program — macro flow, every subsystem (micro), and how to operate it for maximum capability | [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md) |
| Dig into the per-subsystem raw research (dense file:line detail behind the manual) | [docs/PROGRAM-MANUAL-digests.md](docs/PROGRAM-MANUAL-digests.md) |
| Run / configure / troubleshoot | [OPERATIONS.md](OPERATIONS.md) |
| See WHY the architecture is shaped this way (ADR log) | [DECISIONS.md](DECISIONS.md) |
| Current leadership critique + forward direction | [docs/STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md) |
| Execute a roadmap session (operator manual, why + how + acceptance) | [docs/HANDOFF-roadmap-2026-05-24.md](docs/HANDOFF-roadmap-2026-05-24.md) |
| Past handoffs (historical) | [docs/archive/](docs/archive/) |

Don't duplicate ARCHITECTURE.md content here. If you need to record
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

Beyond the impact-analysis checks above:

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
1. Run impact analysis before editing existing symbols (grep callers + Read call sites)
2. Run scope check after edits — confirm only expected files changed
3. <task-specific gotcha>
4. **Brief-pattern reference adherence.** When the brief says "mirror pattern X at file:line" or "use the existing _foo_-style endpoint," verify the FULL shape of X — signature, route path, scope parameters, error handling, lock guards — not just the called function. Brief-pattern references are implicit specs; silent deviations cascade. If the named helper doesn't exist or the wording is ambiguous, report the divergence in your status BEFORE implementing. (Broader codifier-side discipline: see Rule #12 — brief-level grep-the-writes — in `docs/PROTOCOL-RULES-LOG.md`.)
5. **Scoping check on new endpoints.** When adding/touching an HTTP endpoint operating on a tenant- or project-scoped resource, verify the route takes the scoping ID explicitly. Do NOT scan to find a matching resource by leaf ID alone — IDs can collide across tenants/projects depending on the ID-generation scheme. Inspect at least one similar existing endpoint in the same file to confirm the route shape and scoping. (Broader codifier-side discipline: see Rule #13 — symmetric-endpoint audit — in `docs/PROTOCOL-RULES-LOG.md`.)

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
| **Operator-seat** | Operational verification: post-commit Lane V reviewer dispatch, Lane D doc-sync, transplant-handoff refresh, mailbox event authoring | Operational work requires cold-context independence (Rule #9) |

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

- **Drift below your concern threshold** (unrelated commit, informational mailbox event): commit normally; mention
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
/ 0 director-seat) lives in `docs/PROTOCOL-RULES-LOG.md`. Post-v5.1
distribution (Rules 1-13): 6 both / 2 user / 3 operator-seat /
2 director-seat.

## Brief-level grep-the-writes discipline (Rule #12)

**Rule #12: Brief-level grep-the-writes discipline.**
*(Subtitle: type-declaration is not write-evidence.)*

When a brief or dispatch prompt names a schema field, mutator
function, dict key, or write-path as the target of new code, the
codifier MUST grep production writes to verify the named symbol is
actually populated at runtime — not just declared in the type schema.
Type-declaration proves a field can exist on a record; only a
write-site proves it does exist at runtime.

**Verification commands (at minimum one of; combine as needed):**
- Dict key: `grep -rn "\"<key>\"\|'<key>'" --include='*.py' .`
  filtering for assignment patterns (`["<key>"] =`, `.update({...})`,
  dict literals, `**`-spread).
- Pydantic field: grep for `<field_name>=` + `setattr(` patterns,
  plus mutator helpers (`mutate_project`, `Project.model_validate`,
  `model_dump` round-trips). Mixed-shape symbols (typed-attribute AND
  raw-dict access) need both surfaces.
- Function call: `grep -rn "<func_name>("`; verify production paths,
  not test-only. Async/background paths count as production.

**Two-layer-defense with v4.1 CC-2.** Rule #12 catches at brief-write
time (upstream); CC-2 catches at Lane V time (downstream). Both
layers operate; post-codification Lane V catches of symbol-divergence
are working two-layer defense, not broken codification.

**Codified SHA:** `8ab0bbb` (Protocol Bundle v5.1 ship; chicken-and-egg
precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1
`509db7c` / v5 `d66690f`). Empirical basis: Lane V #6 F1 (N=1;
closed `6c1171a`) + Lane V #8 spec-reviewer prompt preventive (N=2;
0 divergences). Beneficiary: `director-seat` (constrains brief-writing);
operator-seat consented in v5.1 REPLY `9f032db` per R11 explicit-
consent path.

## Symmetric-endpoint audit discipline (Rule #13)

**Rule #13: Symmetric-endpoint audit discipline.**
*(Subtitle: a new defense names what existing endpoints may be missing.)*

When adding a new endpoint (or modifying an existing one) that
bypasses an existing fence, gates on a persistent flag, or operates
on shared state already touched by other endpoints, the codifier
MUST audit ALL existing endpoints on the same fence / flag / state
for parallel checks the new endpoint should mirror — AND for parallel
checks the existing endpoints may be missing.

**Shared state (any of):** in-memory set/dict (`_running_pipelines`,
`_progress_queues`); persistent flag on project record
(`screening_approved`, `needs_reassembly`); on-disk artifact
(`final_video_path`); shared lock (`_pipelines_lock`).

**Audit procedure:**
1. `grep -n '<shared_state_symbol>' web_server.py` for existing
   endpoints touching the state.
2. For each: identify bypass behavior, precondition checks,
   error-response shapes.
3. Ask: *would I include this new check in each existing endpoint
   from scratch?* If yes, existing is under-defended → flag for
   symmetric fold or follow-up.
4. Ask: *do existing endpoints have defenses the new one should
   mirror?* If yes, include OR document why exempt.

**Verification in brief/commit body:** one-liner listing audited
endpoints (e.g., "Audited `/assemble/screen`, `/screening/approve`
for `final_video_path` precondition; mirroring."). Fold the
symmetric fix OR explicitly defer with rationale.

**Composition with Rule #9.** Internal-review's design-intent context
creates blind spot for symmetric cases; Lane V cold-context catches
them as backstop. Rule #13 moves the catch upstream from Lane V to
brief-write time; Rule #9's structural value remains as second layer.

**Codified SHA:** `8ab0bbb` (Protocol Bundle v5.1 ship; chicken-and-egg
precedent). Empirical basis: Lane V #8 I1 CRITICAL (N=1; iterate
endpoint missing gate-bypass that `/screening/approve` +
`/assemble/re-assemble` had; closed `9e9b008`) + Val#1 V1 (N=2;
`/screening/approve` missing precondition that `/assemble/screen`
had; closed `d10b849`). Beneficiary: `director-seat` (constrains
endpoint design); operator-seat consented in v5.1 REPLY `9f032db`.

## Operator-driven Lane B template + selection criteria (Rule #14)

**Rule #14: Operator-driven Lane B template + selection criteria.**
*(Subtitle: when operator-seat may dispatch Lane B implementer subagents.)*

Operator-seat MAY claim and dispatch a Lane B implementer subagent
(with parallel Lane V follow-up) without prerequisite user-direction
or director-invitation when ALL five selection criteria below hold.
Outside the criteria, Lane B remains director-driven per role
partition Sh.

### Selection criteria (ALL must hold)

1. **Small file count.** Single-file refactor, OR 2-3 closely-related
   sibling files. >3 files indicates cross-cutting concerns better
   served by director-driven judgment.
2. **Clear canonical pattern reference.** Documented pattern + at
   least one canonical site SHA. Pre-scope MUST cite both in the
   dispatch-claim (Rule #12 applies for canonical site reference).
3. **≤150 LoC of net production-code change.** Production files only;
   test files NOT counted (penalizing test discipline is the wrong
   signal). Empirical fit: B-005 (142) + B-006-broad-A (82) both
   satisfy; B-006-broad-B (~243) correctly does NOT.
4. **No cross-cutting public-API impact.** No signature / return-type /
   exception-type contract changes that break existing callers.
   Acceptable: new exception types via inner-validate (preserves caller
   contract).
5. **Rule #13 symmetric audit covers the scope.** Pre-scope completes
   the audit; grep-output cited in dispatch-claim.

ALL 5 hold → eligible. ANY fail → director-driven default.

**Criterion-failure default (R-Q4-1).** Default to (a) defer-to-
director-driven Lane B per role partition Sh. (b) operator MAY send
an INFORMATIONAL `dispatch-claim-deferral` event (non-blocking
visibility; not action-binding per Rule #8). (c) request user-
direction override — rare; reserved for rule-gap signals.

### Template (5-stage flow)

**Stage 1: Pre-scope (Lane C-style read-only survey).** Grep target
symbols (Rule #12); identify canonical pattern + site SHA; classify
per-site variant; Rule #13 audit; verify 5 criteria. Operator-internal;
no mailbox event. ~10-15min.

**Stage 2: Dispatch-claim mailbox event.** Cite scope + canonical
pattern + canonical site SHA + per-site variant table + Rule #12 grep
evidence + Rule #13 audit + cost envelope + 5-min silent-accept window.
SHOULD note if parallel-with-director work is in flight on disjoint
files; otherwise default is exclusive operator-driven Lane B.

**Stage 3: Implementer subagent dispatch (Lane B).** Single subagent,
cold-context prompt with brief + project conventions + verification
commands + report format. ~70-130k tokens, ~10-15min.

**Stage 4: Parallel Lane V dispatch.** Operator dispatches TWO cold-
context reviewers in PARALLEL (Rule #9) — spec + code-quality. Both
prompts include CC-2 + Rule #12 + Rule #13. ~200-250k tokens, ~10-15min
parallel. Director-seat MAY ALSO dispatch parallel Lane V per Rule #9
§"Parallelism"; operator's dispatch does NOT preempt director's option.

**Stage 5: Verification-report mailbox event.** Structured catalog
with status / findings / telemetry / cursor advance / race-ack.
Director processes per Rule #8 mailbox authority.

### Working criteria (dogfood)

- **C1:** Rule #14 invocation cited in dispatch-claim (5 criteria
  check enumerated).
- **C2:** Implementer commit body includes literal "Rule #14" (or
  "Per Rule #14 operator-driven Lane B") + canonical pattern + site
  SHA. Enables `git log --grep='Rule #14'` audit.
- **C3:** 5-criteria pre-flight BEFORE dispatch-claim; criterion-
  failure → (a) defer default.
- **C4:** Per-instance wall-clock ~20-30min from pre-scope completion
  to dispatch-claim (R-Q5-1). Cycle-13+ retrospective rolls up across
  instances. ≥40% friction reduction is secondary v5.3 roll-up.

### Composition

- Rule #2 (signaling): Stage 2 dispatch-claim is the formal signal.
- Rule #5 + #7: apply at every commit Stages 3 + 5 produce.
- Rule #8 (mailbox authority): dispatch-claim binds director-seat to
  consent (silent or explicit) within 5-min window.
- Rule #9 (independent reviewer + parallelism): Stage 4 operator-side
  Lane V is structurally independent; director MAY ALSO dispatch in
  parallel (complementary findings).
- Rule #10 (joint-team mode): specialization within Sh, not hierarchy.
- Rule #12 + #13: applied during pre-scope, cited in dispatch-claim.

### Beneficiary (per R11)

**Beneficiary: `both`** seats.

Rule #14 enables AND constrains both seats symmetrically: operator-
seat gains codified capability + accepts 5 criteria as constraint;
director-seat gains yield-signal + accepts "cannot claim operator-
eligible work without explicit reason" as constraint. No asymmetric-
veto path needed; operator-seat consented affirmatively in v5.2 REPLY
(`dea6401`) per v5.1 explicit-consent customary path.

**Codified SHA:** `61cac6d` (Protocol Bundle v5.2 ship; chicken-and-egg
precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1
`509db7c` / v5 `d66690f` / v5.1 `8ab0bbb`). Empirical basis: N=2 —
**B-005** (cycle-11, `c296105`; 10 sites in `domain/project_manager.py`;
142 prod LoC; ~295k subagent tokens; Lane V #11 ✅) + **B-006-broad-A**
(cycle-12, `5b68776`; 6 sites across 4 files; 82 prod LoC; ~275k
subagent tokens; Lane V #12 ✅). B-006-broad-B (`a0493dc`, 243 prod
LoC) is the criteria-exclusion validation point.

## Cross-seat fix-on-received-findings convention (Rule #15)

**Rule #15: Cross-seat fix-on-received-findings convention.**
*(Subtitle: when one seat closes the other seat's Lane V finding.)*

When one seat's Lane V verification surfaces a finding requiring code
fix, the OTHER seat MAY close it via standalone `fix:` commit.
Bidirectionally symmetric (operator-closes-director-flagged OR
director-closes-operator-flagged), though only operator-flagged-
director-closes instances exist at codification time (N=0 for the
second direction; bidirectional codification at N=0 per Q4 silent-
accept avoids retroactive scope-creep at v5.4+).

### Disposition recommendation (flagging seat)

Operator's `verification-report` event MAY include a structured
3-option disposition:

- **(a) Fold into adjacent in-flight work** (if applicable).
- **(b) Standalone fix commit.** Always available as fallback —
  parallel-execution timing can foreclose (a).
- **(c) NO ACTION (informational only).** Cosmetic / observation-only.

### Severity-vs-option advisory matrix (R-Q2-1)

Advisory, not binding — receiving seat retains discretion.

| Severity | Default | Notes |
|---|---|---|
| **CRITICAL** | **preferred (b)** | Option (a) fold-in **only with explicit-justification in commit body** (R-Q2-1 refinement of proposal's "never (a)"). Option (c) not permitted for CRITICAL. |
| IMPORTANT | (a) if fold-able; else (b) | Same-file ≤5 LoC adjacent commit preferred fold. |
| MINOR | (a) or (b) per scope | Sub-2-LoC mechanical → (a); structural / multi-file → (b). |
| INFORMATIONAL | (c) acceptable | Cosmetic / docs / observation-only. |

### Receiving seat's response

Choose option based on:
- **Timing.** (a) only if adjacent work in-flight + fold cheap; else (b).
- **Scope.** Sub-2-LoC mechanical → (a); structural → (b).
- **Severity.** Per matrix above; CRITICAL fold-in requires explicit
  justification.

Option choice binding once committed; rollback requires another REPLY
cycle or user escalation.

### Commit-body convention

1. **Subject:** loose format (Q3 silent-accept) — reference Lane V #
   OR finding ID somewhere in the commit text. Examples: `fix(web):
   close Lane V #12 I1 — discriminate ValidationError...` (`442e154`);
   `fix(web): close M-3 — use logger.error...` (`336403d`).
2. **Body:** cite operator's disposition + chosen option (a/b/c) +
   brief why.
3. **Race-ack** per Rule #5 + #7.
4. **Co-Authored-By** trailer per system prompt.

### Audit-trail reconstructability

Lifecycle reconstructable from public artifacts (mailbox archive + git
log) WITHOUT requiring original session context. Optional follow-up
Lane V on the closing commit verifies closure quality.

### Working criteria

- **C1:** commit subject cites Lane V # OR finding ID (grep:
  `git log --oneline --grep='close Lane V\|close M-\|close F-\|close I'`).
  N=2 satisfies.
- **C2:** verification-report includes 3-option disposition when fix
  required. Mailbox-archive verifiable. N=2 satisfies.
- **C3:** receiving seat's commit body cites option choice. Body-grep
  verifiable. N=2 satisfies.
- **C4:** closure within ~1 session OR explicit cross-cycle DEFER ACK
  (Q5 silent-accept). N=1 minutes intra-cycle; N=2 half-day cross-
  cycle DEFER-ACK. Both satisfy.

### Telemetry (Q6 silent-accept)

Rule #15 instances tracked separately from fix-on-own-findings (N=9
cumulative pre-cycle-12) in cumulative v4.1 telemetry. Merge into a
single "fix-following-Lane-V" count at v5.5+ if no operational
distinction emerges in 2-3 cycles.

### Composition

- Rule #2 (signaling): verification-report event is the formal signal.
- Rule #5 + #7: apply to every closing commit.
- Rule #8 (mailbox authority): verification-report binds receiving
  seat per disposition.
- Rule #9 (independent reviewer + parallelism): produces the findings
  Rule #15 closes; together they form the Lane V flag-disposition-
  close lifecycle.
- Rule #10 (joint-team mode): specialization mechanism, not hierarchy.
- Rule #14 (operator-driven Lane B template): Stage 4+5 feed into
  Rule #15's closure mechanism.

### Beneficiary (per R11)

**Beneficiary: `both`** seats.

Symmetric enable + constrain on both axes. No asymmetric-veto path
needed. Director-seat consented affirmatively in v5.3 REPLY
(`3a0e433`); operator-seat consented in proposal sign-off (`dc7df5d`).

**Codified SHA:** `24c145a` (Protocol Bundle v5.3 ship; chicken-and-egg
precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `d90036b` / v4.1
`509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2 `61cac6d`). Empirical
basis: N=2 — **`442e154`** (cycle-12; director closes operator's Lane
V #12 I1; IMPORTANT-advisory; intra-cycle close ~minutes) + **`336403d`**
(cycle-13 entry; director closes operator's Lane V #13 M-3; MINOR-
DEFER; cross-cycle close ~half day with explicit DEFER ACK). Evidence
spans severity (IMPORTANT → MINOR-DEFER), timing (intra → cross-cycle),
and disposition route (option-1-foreclosed → DEFER-acknowledged) —
empirically distributed across the convention's operational shape.

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
`d8f2407` / v4 `7da49ed` / v4.1 `509db7c` / v5 `d66690f` / v5.1 `8ab0bbb`
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
`7da49ed` / v4.1 `509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2
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
chicken-and-egg precedent — v2 `3e57ddf` / v3 `d8f2407` / v4 `7da49ed` / v4.1
`509db7c` / v5 `d66690f` / v5.1 `8ab0bbb` / v5.2 `61cac6d` / v5.3 `24c145a` / v5.4
`7773502` / v5.5 `52658eb`). **Forward-looking:** no dogfood result yet — the
graduation metrics are the first data, post-launch. **F1 facts at ship:** no F1
open (scene-transitions F1 closed `1f9d46b`, operator-acked `35c530c`; the
proposal's `561ad6b`-open citation was a stale conflation — `561ad6b` is the
2026-05-28 dialogue feat whose own F1 closed `d3fcfb0` — corrected here per ADR-013).
Principal-originated synthesis of the advisor/operator/director triangulation;
both seats consented (operator bounded carve-out + director); director-seat ships
per Sh role partition. ADR-019.

## Live-presence-over-inferred-idle (Rule #19)

**Rule #19: Live-presence-over-inferred-idle.**
*(Subtitle: read the peer's presence; don't infer liveness from commit silence; bind cross-seat signals via artifacts, not chat.)*

The director–operator protocol had **no live, shared, agent-observable presence
channel**: each seat inferred the other's liveness from a 10-minute-idle-since-
last-commit heuristic, so any seat doing non-committing work (reading, TDD,
review, thinking) read as "offline." Rule #19 replaces inference with a signal.

1. **Each seat maintains `coordination/presence/<seat>.md`** (gitignored,
   per-clone; flat `key: value`: `seat`, `status` (active|wrapping|away),
   `current_task`, `head_at_write`, `updated`). The hook bumps
   `updated`/`head_at_write` every tool call (operator-shipped M2/M3); the
   **agent owns `status` + `current_task`** and updates `current_task` at each
   task boundary.
2. **Liveness is read from presence freshness + `current_task`, NOT from commit
   recency.** "Offline" = presence `updated` stale > T (default 10 min). A seat
   mid-implementation with a fresh presence file is active, not idle.
3. **Binding cross-seat signals MUST be artifacts** — a mailbox event or a
   presence-file update — never chat narration alone. Chat is per-session-
   private (only the user-principal sees both terminals), so it is a user-facing
   courtesy, not a peer channel. This **supersedes the implicit "narrate in
   conversation" reliance in Rule #2 §Signaling** (Rule #2's narration is
   retained for the user; the peer learns intent from `current_task` + mailbox).

**`current_task`-rot guard.** The hook bumps freshness every tool call, so a
file can read *fresh* while `current_task` is *semantically stale* ("drafting X"
long after you moved on) — a maintained-looking artifact that lies (cf. the
GitNexus phantom, ADR-016). Mitigations: (a) agent updates `current_task` at
task boundaries; (b) the Rule #8 bootstrap awareness gate surfaces "peer
presence fresh but `current_task` unchanged since HEAD <X>" as a soft warning;
(c) session-wrap checklist clears `current_task`.

**Topology (D-a).** Rule #19's presence files + STATE.md + `coordination/`
assume **one shared working tree**; the seats isolate *staging* via per-seat
`GIT_INDEX_FILE` (NOT separate worktrees — those force separate branches and
make gitignored presence peer-invisible). See `coordination/README.md`
§"Per-seat launch (D-a)".

**Beneficiary (per R11): `both`** — symmetric. Both seats owe presence
maintenance; both gain accurate peer-liveness. No asymmetric-veto path;
operator consented affirmatively (REPLY `ab9925d`).

**Codified SHA:** `_Protocol Bundle v5.7 ship_` (filled next session-close per
the chicken-and-egg precedent — v2 `3e57ddf` … v5.6 `4eecb72`). Empirical basis:
user-principal-reported 2026-05-30 "both seats keep seeing each other
offline/unaware" failure; operator-seat corroborated RC1–RC5 firing in one
session (inferred director offline while director fixed Bug #4; Rule-#2
narration inert; STATE.md `director=4`-vs-1; cursor lag; ref-race ×2). v5.7
proposal `e353479` → operator REPLY `ab9925d` (CONSENT) → user Q4=D-a
adjudication → greenlight `f9ae567`.

## Shared-state-accuracy (Rule #20)

**Rule #20: Shared-state-accuracy.**
*(Subtitle: the awareness gate computes truth; it does not trust a stale snapshot.)*

STATE.md is gitignored/local, refreshes only on a HEAD move, and (pre-v5.7) its
`unread mailbox` count used `find -newer <cursor-file-mtime>` — no `to:` filter
(counted **both directions**, including the role's own sends) and mtime-vs-
content (decoupled from the cursor's ISO timestamp). This produced `director=4`
when the actionable count was 1.

1. **The Rule #8 awareness gate recomputes unread LIVE** — count events
   `*-to-<me>-*` whose filename-timestamp is strictly newer than the cursor's
   **content** timestamp — rather than trusting STATE.md's possibly-frozen
   field. STATE.md is a convenience cache; the gate verifies. (The M2 hook fix,
   operator-shipped, makes STATE.md's own field correct; the gate verifies
   regardless.)
2. **Until M2 is live, reconcile STATE.md against the filesystem** before acting
   on its count (Rule #8 §F "filesystem wins" as a positive step, not a
   fallback).
3. **Cursors support per-event acknowledgment** — partial/deferred processing
   must be representable, so a lagged single-timestamp cursor cannot masquerade
   as "peer never saw it." Cursor advance is part of *processing* an event,
   verified at session-wrap.

**Beneficiary (per R11): `both`** — symmetric. Operator consented (REPLY
`ab9925d`).

**Codified SHA:** `_Protocol Bundle v5.7 ship_` (filled next session-close).
Empirical basis: same session as Rule #19 — RC3 (STATE.md broken count, observed
`director=4`-vs-1) + RC4 (cursor lag `T10:23:57Z` vs the handoff's `T11:52:06Z`).
The M2 fix validated on controlled data (old over-counts 3, new correct 1;
`docs/DRAFT-v5.7-phase1-implementation-2026-05-30.md` §1).

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
the Architecture Preamble. They diverge on tooling specifics:

| Topic | This file (AGENTS.md) | CLAUDE.md |
|---|---|---|
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

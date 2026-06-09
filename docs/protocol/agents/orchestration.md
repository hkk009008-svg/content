# Orchestration — agent-agnostic (relocated)

> Relocated verbatim from `AGENTS.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **on trigger**,
> not at session start. Two-tree strategy: this is the `agents` copy. Sections
> that live elsewhere (prompt templates → `docs/templates/...`, failure-modes →
> `.../failure-modes.md`) are intentionally not included here. During the add-first
> window the root file still holds this content; it will be stubbed once confirmed.

---

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

## When NOT to orchestrate

- **Single-step tasks.** Just do them.
- **Tightly-coupled refactors** where each change depends on the
  previous change's state in a way that prep-then-dispatch can't
  capture cleanly.
- **Interactive exploration** ("what does X do?"). Fresh-instance
  overhead hurts here.
- **Tasks needing constant operator feedback** — interactive sessions
  fit better.


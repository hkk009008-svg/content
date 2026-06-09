# Orchestration — Claude Code (relocated)

> Relocated verbatim from `CLAUDE.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **on trigger**,
> not at session start. Two-tree strategy: this is the `claude` copy. Sections
> that live elsewhere (prompt templates → `docs/templates/...`, failure-modes →
> `.../failure-modes.md`) are intentionally not included here. During the add-first
> window the root file still holds this content; it will be stubbed once confirmed.

---

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

## When NOT to use this pattern

- **Single-step tasks.** Just do them in main context.
- **Tightly-coupled refactors** where every change depends on the previous
  change's state in a way that prep-then-dispatch can't capture cleanly.
- **Interactive exploration** ("what does X do?"). Subagent overhead hurts
  here.
- **Tasks with constant operator feedback** — interactive sessions in main
  context fit better.


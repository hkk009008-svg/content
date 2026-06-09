# Core protocol — Claude Code (relocated)

> Relocated verbatim from `CLAUDE.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **on trigger**,
> not at session start. Two-tree strategy: this is the `claude` copy. Sections
> that live elsewhere (prompt templates → `docs/templates/...`, failure-modes →
> `.../failure-modes.md`) are intentionally not included here. During the add-first
> window the root file still holds this content; it will be stubbed once confirmed.

---

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


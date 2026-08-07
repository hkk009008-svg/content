---
name: cross-machine-handoff
description: Write a Mac-to-Windows or fresh-session handoff brief — pinned commit SHA and package digest on BOTH machines, command-plus-output citations, an explicit SUPERSEDED section the reader must not believe, blockers with an owner machine, and one next action per machine. Use when work crosses the machine boundary, a fresh session resumes a campaign, or another agent will act on your state. Same-tree seat-to-seat signals belong to four-seat-protocol; worker mechanics to windows-worker-ops.
disable-model-invocation: true
---

# Cross-machine handoff briefs

The reader has NONE of your context and will act on whatever you hand them —
including your stale conclusions. A handoff is an artifact, never chat prose.
Never name a branch where a SHA belongs, never assert a "both machines" fact
measured on one, and never omit the decisions that were REVERSED — on
2026-08-07 a replayed stale brief nearly caused an FFmpeg install for a
dependency that had been deleted from the pins hours earlier, and an ambiguous
"refs/main" (HF-cache ref vs git ref — two unrelated files) nearly sent an
agent hand-editing the wrong one.

Do this first (EXECUTING HOST: wherever you claim state) — re-read the working
record, then pin the tree:

```bash
cd /Users/hyungkoookkim/Content && env -u GIT_INDEX_FILE git rev-parse HEAD && \
  env -u GIT_INDEX_FILE git status --short | head -5
```

## Required slots (template: `handoff-brief-template.md` in this directory)

1. **Identity pins** — full commit SHA and, for pinned packages, the current
   `package_digest`, per machine. Transfer by SHA-zip URL, never a branch.
2. **SUPERSEDED** — every decision, digest, or instruction from earlier in the
   campaign the reader might encounter and must NOT act on. Name the stale
   value AND its replacement. This section has prevented at least one wasted
   install cycle; it is not optional.
3. **Citations** — every load-bearing claim is a command plus its REAL output,
   with the executing host named. A hedge you cannot cite is a premise you
   have not verified: mark it UNKNOWN instead of asserting it.
4. **Blockers with an owner machine** — each open item says which keyboard can
   clear it. "The Mac cannot stop the worker" class facts go here.
5. **One next action per machine** — imperative, gated ("do X, then STOP and
   report") so the reader cannot overrun your intent.
6. **Constraints** — what the reader must NOT do (retry, patch pinned files,
   install system dependencies) and where the boundary authority lives.

## Traps

- **Trap 1 — briefing from head state.** Memory of the campaign is the least
  reliable source in it. Build the brief from artifacts: git log, status
  payloads, evidence files. If the record and your memory disagree, the record
  wins.
- **Trap 2 — omitted supersession.** A fresh session treats any plausible
  artifact as live truth. Every digest that moved, every reversed decision,
  every fixed-then-refixed file needs an explicit "do not believe" line.
- **Trap 3 — ambiguous nouns.** Two files named `refs/main` existed on one
  machine. Qualify every path fully; never assume the reader resolves an
  ambiguous name the way you do.

## Red flags (self-check)

- A load-bearing sentence with no command behind it.
- "Both machines" measured on one.
- A branch name anywhere in the transfer instructions.
- The reader could plausibly act on something you know is stale, and the brief
  does not name it.
- Your next-action section lets the reader continue past the point where you
  need to re-enter the loop.

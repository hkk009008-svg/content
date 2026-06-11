# Reviewer prompt template — Claude Code

> Relocated verbatim from `CLAUDE.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **at dispatch**,
> not at session start. Two-tree strategy: this is the `claude` copy.
> During the add-first window the root file still holds this content; it will be
> stubbed once this destination is confirmed.

---

## Git hygiene (include verbatim in EVERY dispatched prompt)

- Prefix EVERY git invocation with `env -u GIT_INDEX_FILE ` — your
  environment inherits this seat's per-seat git index, and concurrent index
  refreshes from parallel agents corrupted it on 2026-06-12 ("unable to read
  <blob>"). The unset form uses the default `.git/index`, which no seat
  depends on.
- Never run state-changing git (add/commit/checkout/stash/restore/read-tree
  without explicit instruction). Read-only git (show/log/diff A..B/grep/
  rev-parse/ls-tree) plus the prefix is always safe.

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

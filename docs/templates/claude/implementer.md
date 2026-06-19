# Implementer prompt template — Claude Code

> Relocated verbatim from `CLAUDE.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **at dispatch**,
> not at session start. Two-tree strategy: this is the `claude` copy.
> During the add-first window the root file still holds this content; it will be
> stubbed once this destination is confirmed.

---

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
- Pin selectors run — the exact pytest node-ids / `xfail-pin` column values you executed (so an independent reviewer can re-run them with `--runxfail` + a one-fact mutation non-vacuity check)
- Commit SHA — `git commit` stdout's SHA is authoritative as of cycle-8 B-003 Option E (the post-commit hook no longer amends; STATE.md is gitignored and regenerated locally). Use `git log --oneline -3` to double-check if desired, but the SHA from commit stdout matches HEAD.
- Self-review findings
```

### Git hygiene (include verbatim in EVERY dispatched prompt)

- Prefix EVERY git invocation with `env -u GIT_INDEX_FILE ` — your
  environment inherits this seat's per-seat git index, and concurrent index
  refreshes from parallel agents corrupted it on 2026-06-12 ("unable to read
  <blob>"). The unset form uses the default `.git/index`, which no seat
  depends on.
- Never run state-changing git (add/commit/checkout/stash/restore/read-tree
  without explicit instruction). Read-only git (show/log/diff A..B/grep/
  rev-parse/ls-tree) plus the prefix is always safe.

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

# Design — inline-backtick anchor verification in `check_doc_claims.py`

- **Date:** 2026-06-08
- **Author:** operator-seat
- **Status:** Draft (pending spec-review loop + user review)
- **Skill chain:** brainstorming → (this spec) → writing-plans → subagent-driven implementation

## 1. Problem

`scripts/check_doc_claims.py` verifies documentation line-anchors against source, but
only recognizes **markdown-link** anchors of the form `[display](path/file.py:NNN)`.
`ARCHITECTURE.md` uses that format, so its anchors are checked. But
`docs/PROGRAM-MANUAL.md` and `docs/PROGRAM-MANUAL-digests.md` write their anchors as
**inline backticks** — `` `llm/chief_director.py:226` `` and bare `` `chief_director.py:226` ``
— which `_ANCHOR_RE` does not match. The tool therefore reports "no drift" while those
anchors silently rot.

**Evidence (2026-06-08):** `llm/chief_director.py` grew 501→664 lines; ~30
`chief_director.py` anchors in the manual/digests had drifted (e.g.
`validate_shot_prompts` :226→:296, `evaluate_generation_quality` :318/:336→:406) yet
`check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` printed
"All anchors checked — no drift." Those were hand-fixed in `3f2c149`; this work closes
the gap that let them drift unchecked. This is a textbook Rule #18 Guard-1 case: a
maintained-looking artifact (green verifier) that lies because the instrument's
coverage doesn't reach where the anchors live.

## 2. Goal / non-goals

**Goal:** the verifier also detects, resolves, and def-drift-checks inline-backtick
`` `path:line` `` (and `` `path:line-line` ``) anchors, with `--fix` support, no new
false positives, and a clean signal for anchors it cannot safely resolve. Then sweep
the repo to fix all inline-anchor drift the new coverage surfaces.

**Non-goals:** changing the markdown-link anchor behavior; checking anchors into
non-source files; resolving SHA-refs (separate `--sha-refs` path, untouched);
re-formatting docs beyond anchor line numbers.

## 3. Approved decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Bare-basename resolution | **Resolve unique, advise ambiguous.** Unique tracked basename → check it. Ambiguous (≥2 tracked matches) → non-fatal `ambiguous_path` advisory (lists candidates, suggests full path), not a drift. |
| Backlog scope | **Full repo-wide sweep.** Ship the tool + tests, then run repo-wide and fix all detected inline-anchor drift (auto def-anchors via `--fix`; range anchors hand-fixed; ambiguous anchors qualified from context). |
| False positives | **Only flag real-looking anchors.** Require a file extension AND (a path separator OR a uniquely-resolvable tracked basename). A bare unresolvable token (`` `foo.py:30` `` in a snippet) is skipped, not a `missing_file` drift. |

**Ambiguity is real:** of 195 tracked `.py` files, 177 unique basenames → **18 collide**
(`controller.py`, `scene_decomposer.py`, `performance.py`, `project_manager.py`,
`character_manager.py`, `continuity_engine.py`, `dialogue_writer.py`,
`location_manager.py`, `__init__.py`, …) — the top-level/`domain/` shim pairs. So
bare-basename resolution must handle ambiguity, hence the `ambiguous_path` advisory.
(Verified: `git ls-files '*.py' | sed 's#.*/##' | sort | uniq -d`.)

## 4. Design (Approach A — extend in place)

Chosen over a separate `check_inline_anchors` function (would duplicate the
def-check + fix machinery, inviting two-copy drift) and over a normalize-then-check
preprocessor (hacky). Approach A unifies anchor iteration so both anchor syntaxes feed
the existing `check_anchor` def-drift/bounds logic and the existing fix path.

### 4.1 Detection — `_INLINE_ANCHOR_RE`

A backtick-delimited token whose content is `<path>.<ext>:<line>` with an optional
`-<line>` range:

```
`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z0-9]+):(?P<line>\d+)(?:-(?P<end>\d+))?`
```

- The required `\.<ext>` is false-positive guard #1 (so `` `time:30` ``, `` `key:value` ``
  never match).
- `check_line_anchors` iterates **both** `_ANCHOR_RE` (links) and `_INLINE_ANCHOR_RE`
  (inline) per doc line. **De-dup:** a markdown link `[x](a.py:1)` contains the
  substring `` a.py:1 `` but not inside backticks; still, to be safe, inline matches
  whose span falls inside a markdown-link match span on the same line are discarded
  (guard against double-reporting the same anchor).

### 4.2 Path resolution — `_resolve_target(file_token, basename_index, repo_root)`

A `basename → [tracked relpaths]` index is built **once per run** from `git ls-files`
(tracked-only ⇒ excludes `.claude/worktrees/*` snapshots, `dist/`, `node_modules/`,
and any untracked copy — the exact trap that would make every basename look
ambiguous). If git is unavailable (not a repo), the index is empty and bare-basename
resolution is disabled (bare → skip), degrading gracefully. Resolution cases:

| Token shape | Resolves to | Outcome |
|---|---|---|
| Directory-qualified, exists (`llm/chief_director.py:226`) | that file | check def-drift/bounds |
| Directory-qualified, missing (`gone/x.py:5`) | — | `missing_file` drift (real-looking) |
| Bare basename, **unique** in index (`chief_director.py:226`) | the 1 match | check def-drift/bounds |
| Bare basename, **ambiguous** (`controller.py:1928`, ≥2) | — | `ambiguous_path` advisory (non-fatal) |
| Bare basename, **0 matches** (`foo.py:30`) | — | **skip** (false-positive guard #2) |

Markdown-link anchors keep their current resolution (`repo_root / path`); the
basename index applies to inline anchors only (links are conventionally full-path).

### 4.3 Symbol binding

Reuse the existing nearest-backtick logic in `check_anchor`, with one change: when the
anchor itself is an inline-backtick token, **exclude the anchor's own backtick span**
from the candidate symbol tokens, then pick the nearest remaining backtick (the digests
pattern is `` **`Symbol(args)`** — `path:line` ``, so the symbol is the preceding
backtick). With a symbol bound, the existing `_def_lines` + range-match def-drift logic
runs unchanged. With no symbol bound (anchor stands alone), fall through to the existing
bounds check.

### 4.4 Drift kinds, advisories, exit code

- Reuse `def_drift` / `missing_file` / `out_of_bounds` (fatal; exit 1) unchanged.
- Add **`ambiguous_path`** (kind on the `Drift` dataclass) — printed in a separate
  **Advisories** section, **exit-code-neutral** (it means "can't verify," not "wrong").
  Message lists the candidate paths and suggests qualifying the anchor with a directory.
- Reporting groups: drifts (fatal) as today; advisories listed below with a count.

### 4.5 `--fix`

Extend the fix path so single-def fixable `def_drift` on inline anchors is rewritten
`` `path:OLD` `` → `` `path:NEW` `` (and range display rewrite via the existing
`_shift_display` for `path:A-B`). Ranges remain non-auto-fixable (matching today).
`ambiguous_path` and `missing_file` are never auto-fixed.

### 4.6 Repo-wide sweep (Slice 2, after the tool ships green)

Run the extended checker across the doc set (ARCHITECTURE.md, CLAUDE.md, AGENTS.md,
DECISIONS.md, OPERATIONS.md, README.md, docs/PROGRAM-MANUAL.md,
docs/PROGRAM-MANUAL-digests.md, and any other tracked `*.md` that carry anchors). Then:
1. `--fix` the auto-fixable single-def inline `def_drift`.
2. Hand-fix range anchors (evidence-cited + count-asserted, like the `3f2c149` sweep).
3. Resolve `ambiguous_path` advisories by qualifying the path from surrounding context.
4. Report the full backlog (what was auto-fixed, hand-fixed, and any residual advisory).
The `chief_director.py` anchors are already fixed (`3f2c149`); the sweep should show
them clean and surface the rest.

## 5. Testing (TDD)

New test classes in `tests/unit/test_check_doc_claims.py`, mirroring the existing
real-tmp-path style (`_write_py`, `_write_md`, `_init_repo`, `check_line_anchors(...)`):

1. **Inline-correct** → no drift (`` `mod.py:3` `` pointing at the real def line).
2. **Inline def-drift** → `def_drift` detected; `--fix` rewrites the inline token.
3. **Bare-basename unique resolves** → drift detected against the single tracked match.
4. **Bare-basename ambiguous** → `ambiguous_path` advisory (non-fatal), candidates listed.
5. **Bare-basename unresolvable** (`` `foo.py:30` ``, no such file) → skipped (no drift).
6. **Inline range anchor** (`` `mod.py:3-9` ``) → range-match semantics (no false drift
   when def is inside the range).
7. **Link + inline on same line** → counted once (no double-report).
8. **`.ext` guard** → a non-anchor backtick (`` `not_a_file:30` ``) is ignored.
9. **Exit-code neutrality** → a run whose only finding is `ambiguous_path` exits 0;
   a `def_drift` exits 1.

Tests that exercise basename resolution use `_init_repo` + commit the source so
`git ls-files` populates the index. Run with `env -u GIT_INDEX_FILE` (the D-a launch
index breaks tmp-repo tests; documented gotcha).

## 6. Acceptance criteria

1. `check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` now
   **detects** an introduced inline-anchor def-drift (regression-proven: revert one
   anchor → tool reports it; today it would not).
2. No new false positives on the existing doc set (illustrative `` `foo.py:NN` `` in
   prose/code snippets are not flagged).
3. `--fix` corrects a single-def inline drift in place; ranges reported but untouched.
4. `ambiguous_path` advisories are non-fatal and list candidates.
5. Full unit suite green (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest
   tests/unit/test_check_doc_claims.py`), §15 smoke OK.
6. Slice 2: a repo-wide run reports zero residual `def_drift` (auto + hand fixes
   applied), with any remaining `ambiguous_path` advisories enumerated.

## 7. Risks / edge cases

- **De-dup correctness:** a line with both a link and an inline anchor must not
  double-count; covered by test 7.
- **Range anchors that span a moved block:** auto-fix stays off for ranges (manual,
  as today) — avoids mis-rewriting a multi-line span.
- **git-absent environments:** bare-basename resolution disabled, not crashed.
- **Performance:** one `git ls-files` per run + O(anchors) lookups — negligible.
- **Backward-compat:** markdown-link anchor behavior, `--sha-refs`, `--show-subjects`,
  and the manifest path are untouched; existing tests must stay green.

## 8. Composition with protocol

This is the Rule #18 verifier-buildout (closes the inline-anchor claim-type by
construction). The Slice-2 sweep is mechanical/verifier-confirmed doc-maintenance
(operator-owned); any prose-claim edits encountered stay senior-reviewed per Guard 1.

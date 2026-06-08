# Design — inline-backtick anchor verification in `check_doc_claims.py`

- **Date:** 2026-06-08
- **Author:** operator-seat
- **Status:** v3 — spec-review loop COMPLETE (iter-1 + iter-2 folded; iter-2 confirmed
  all 6 iter-1 issues RESOLVED incl. the BLOCKING, +3 MINOR clarifications folded here).
  **PENDING the user spec-review gate**, then `writing-plans`.
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
false positives, **and no anchor silently unverified-yet-passing** (ambiguity must not
become a false-green). Then sweep the repo to fix all inline-anchor drift the new
coverage surfaces and drive the residual advisory set to zero.

**Non-goals:** changing markdown-link anchor *semantics*; checking anchors into
non-source files; resolving SHA-refs (separate `--sha-refs` path, untouched);
re-formatting docs beyond anchor line numbers.

## 3. Approved decisions (from brainstorming) + spec-review refinements

| Decision | Choice |
|---|---|
| Bare-basename resolution | **Resolve unique; for ambiguous, disambiguate via bound symbol; only truly-undisambiguable → advisory.** Unique tracked basename → check. Ambiguous (≥2 tracked matches) → if a symbol is bound on the doc line and exactly one candidate defines it, resolve to that candidate and check; else `ambiguous_path` advisory (lists candidates, suggests full path). *(Symbol-disambiguation added to close the spec-review BLOCKING — see §4.2.)* |
| Backlog scope | **Full repo-wide sweep.** Ship tool + tests, then run repo-wide, fix all detected inline-anchor drift (auto def-anchors via `--fix`; range anchors hand-fixed; **qualify every residual `ambiguous_path` anchor to a full path** so the advisory set is empty post-sweep). |
| False positives | **Only flag real-looking anchors.** Require a file extension (letters-only, matching the existing regex) AND (a path separator OR a uniquely-resolvable tracked basename). Bare unresolvable tokens, version strings, and anchors inside fenced code blocks are not flagged. |

**Ambiguity is real (corrected count, ADR-013):** of **195** tracked `.py` files there
are **177** unique basenames; **9 basenames collide across 27 files**
(`__init__.py`, `character_manager.py`, `continuity_engine.py`, `controller.py`,
`dialogue_writer.py`, `location_manager.py`, `performance.py`, `project_manager.py`,
`scene_decomposer.py`) — the top-level/`domain/` shim pairs. Verified:
`git ls-files '*.py' | sed 's#.*/##' | sort | uniq -d | wc -l` → **9**;
files-involved `… | uniq -c | awk '$1>1{s+=$1}END{print s}'` → **27**. The manuals
already contain ~54 *bare* ambiguous-basename inline anchors (e.g. bare
`` `controller.py:NNN` `` ×34), which is exactly why bare-basename resolution must
disambiguate rather than blanket-advise.

## 4. Design (Approach A — extend in place)

Chosen over a separate `check_inline_anchors` function (would duplicate the
def-check + fix machinery → two-copy drift) and a normalize-then-check preprocessor
(hacky). Approach A unifies anchor iteration so both syntaxes feed the existing
`check_anchor` def-drift/bounds logic and `_apply_fixes`.

### 4.1 Detection

**`_INLINE_ANCHOR_RE`** — a backtick-delimited token; the literal backticks ARE part
of the match (so the match span includes them):

```
`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:-(?P<end>\d+))?`
```

- Extension class is **`[A-Za-z]+` (letters-only), matching the existing `_ANCHOR_RE`**
  (line 50) — rejects version tokens (`` `v1.2:30` `` → no match; `` `config.v2:30` `` →
  no match) and `` `time:30` `` / `` `key:value` ``. *(spec-review IMPORTANT: my v1 used
  `[A-Za-z0-9]+` which matched `v1.2:30`.)*
- The both-ends backtick anchoring is a deliberate guard: `` `path.py:10 (note)` ``,
  `mod.py:10)`, `mod.py:10:20` do NOT match (verified). Standalone-token is enforced,
  not assumed.
- **Extension-only / pathological tokens:** the `<file>` group requires ≥1 char before
  the `.ext`, so `` `.py:3` `` does not match. Absolute (`/x/mod.py:3`) and
  parent-relative (`../mod.py:3`) tokens: treated as directory-qualified and resolved
  against `repo_root`; if they escape the repo or don't resolve they become the
  no-resolve case (skip unless a `missing_file` is warranted — see §4.2). A guard test
  covers these.

**Fenced-code-block awareness** *(spec-review IMPORTANT — new):* `check_line_anchors`
tracks ```` ``` ```` (and `~~~`) fence state and **skips lines inside fenced blocks**
for BOTH link and inline anchors. Rationale: an illustrative resolvable anchor in a
tutorial snippet (this very spec's §4.1 shows the regex inside a fence) must not be
flagged or `--fix`-rewritten. This also hardens the existing markdown-link checker
(net improvement; existing real anchors are not in fences, so no regression). `_apply_fixes`
inherits the same fence guard (never rewrites inside a fence).

**Iteration + de-dup:** `check_line_anchors` runs both `_ANCHOR_RE` and
`_INLINE_ANCHOR_RE` per (non-fenced) line. **De-dup contract (precise, spec-review
IMPORTANT):** an inline match is discarded **only when its `(file, line)` equals an
enclosing markdown-link match's `(file, line)`** — NOT merely when its span sits inside
a link span. This correctly checks BOTH anchors in `[`old.py:5`](new.py:9)` (distinct
claims) while not double-counting `[x](`a.py:1`)` style same-anchor cases. (In practice
the two regexes rarely collide since links aren't backtick-wrapped; the rule is a
correctness guard, exercised by a test.)

### 4.2 Path resolution + symbol-disambiguation — `_resolve_target`

`repo_root` is the existing tool's repo_root (the same value `check_anchor` already
receives; no new discovery path). A `basename → [tracked relpaths]` index is built
**once per run** from `git ls-files` over **all tracked files** (not just `.py`, so
`.ts/.tsx/.json/.sh/.toml` anchors resolve too). `git ls-files` is tracked-only ⇒
excludes `.claude/worktrees/*` snapshots, `.venv/`, `dist/`, untracked copies (verified:
worktree + venv copies exist on disk yet `git ls-files | grep -c .claude/worktrees` = 0)
— the exact trap that would make every basename look ambiguous. If git is unavailable
the index is empty (see git-absent handling below). Resolution (inline anchors only;
markdown-links keep `repo_root / path`):

| Token shape | Resolves to | Outcome |
|---|---|---|
| Directory-qualified, exists | that file | check def-drift (symbol) / bounds |
| Directory-qualified, missing | — | `missing_file` drift (real-looking) |
| Bare basename, **unique** in index | the 1 match | check def-drift / bounds |
| Bare basename, **ambiguous** (≥2), symbol bound, **exactly 1 candidate defines the symbol** | that candidate | check def-drift (← catches drift) |
| Bare basename, **ambiguous**, symbol unbound OR 0/≥2 candidates define it | — | `ambiguous_path` advisory (candidates listed) |
| Bare basename, **0 matches** | — | **skip** (false-positive guard #2) |

**Symbol-disambiguation (the BLOCKING fix):** the manuals' bare ambiguous anchors are
overwhelmingly symbol-bound (the `` **`Symbol(args)`** — `path:line` `` pattern). For an
ambiguous basename, compute `D = [c for c in candidates if _def_lines(c, symbol)]`; if
`len(D)==1`, resolve to `D[0]` and run the normal def-drift check (a stale line is
caught). Only `len(D)∈{0,≥2}` or an unbound symbol yields an advisory. This converts the
common case from "silently advised, exit 0" into a real check — without which a drifted
bare `` `controller.py:1928` `` would re-create the false-green this project exists to kill.

**Ordering (spec-review iter-2 MINOR — load-bearing):** the bound symbol (§4.3) MUST be
extracted BEFORE resolution, because `_resolve_target` needs it to compute `D`. So
`check_line_anchors` binds the symbol per §4.3 first, passes it into `_resolve_target`,
and the SAME bound symbol is reused for the later def-drift check (bind once, no
double-extraction). If an implementer wires resolution before binding, every bare
ambiguous anchor falls to the advisory and the BLOCKING fix is silently inert — so this
ordering is a hard requirement, not an implementation detail.

**git-absent / unusable handling** *(spec-review MINOR):* if the basename index can't be
built (git missing or `git ls-files` errors) **and** the docs contain bare anchors that
would need it, emit a **loud warning to stderr** naming the count of un-resolvable bare
anchors (so a repo'd-but-gitless CI run is not a silent clean skip). Directory-qualified
and unique cases are unaffected.

### 4.3 Symbol binding

Reuse `check_anchor`'s nearest-backtick logic with two inline-specific changes:
(1) exclude the anchor's own backtick span from candidate symbol tokens; (2) **bind only
a PRECEDING backtick on the same line** (drop the markdown-link path's after-fallback) —
the inline convention is symbol-precedes-anchor, and the after-fallback could grab an
unrelated trailing `` `note` ``. If multiple backticks precede, take the nearest. With a
symbol bound → `_def_lines` + the existing range-match def-drift check (unchanged). With
**no symbol bound → fall through to the existing bounds check** (`out_of_bounds` if the
line exceeds EOF). The dotted-attribute skip in the existing logic is retained.

### 4.4 Drift kinds, advisories, exit code

- Reuse `def_drift` / `missing_file` / `out_of_bounds` (fatal; exit 1) unchanged.
- Add **`ambiguous_path`** (new `Drift.kind`) — printed in a separate **Advisories**
  section; **exit-code-neutral by default**. Message lists candidate paths and suggests
  qualifying the anchor with a directory. *Mitigation for the BLOCKING concern that
  "ambiguous ≠ verified":* (a) symbol-disambiguation (§4.2) removes most cases; (b) the
  Slice-2 sweep qualifies every residual to a full path so the post-sweep advisory set is
  empty (acceptance #6); (c) an optional future `--strict` flag (out of scope here) can
  make residual advisories a non-zero soft-exit for CI gating — recorded so the policy is
  explicit, not accidental.

### 4.5 `--fix`

Extend `_apply_fixes` to rewrite single-def fixable `def_drift` on inline anchors via
**match-span (offset) rewriting** — reusing the existing per-line `<RE>.sub(_rewrite,…)`
mechanism, which is span-based and safe (NOT a bare string replace). The rewrite
produces the **backtick form** `` `path:NEW` `` for inline anchors and the link form
`[display](path:NEW)` for links — routed by a new `Drift.style ∈ {"link","inline"}`
field set in `check_anchor` (so an inline anchor is never turned into a markdown link).
`_shift_display` (handles bare `:N` and range `:A-B`) is syntax-agnostic and reused as-is.
The per-line `sub` rewrites **all** matching `(file,OLD)` occurrences on the line
(intentional — same property as the existing link fix; documented). Ranges remain
non-auto-fixable. Fixes never fire inside a fenced block (§4.1). `ambiguous_path` /
`missing_file` are never auto-fixed.

**De-dup is reporting-only (spec-review iter-2 MINOR):** the §4.1 de-dup discards a
duplicate inline match for *counting/reporting* purposes only. At fix time, `_apply_fixes`
re-scans the raw doc line and rewrites every stale `(file, OLD)` occurrence in BOTH
syntaxes (`_ANCHOR_RE.sub` AND `_INLINE_ANCHOR_RE.sub` on the line), so the rare
same-`(file,line)` link+inline construction (`` [`a.py:5`](a.py:5) ``) has both forms
corrected — the surviving link-style `Drift` does not leave the backtick token stale.
Test 12 is extended to cover this same-line both-syntaxes case.

### 4.6 Repo-wide sweep (Slice 2, after the tool ships green)

Run the extended checker across the doc set (ARCHITECTURE.md, CLAUDE.md, AGENTS.md,
DECISIONS.md, OPERATIONS.md, README.md, docs/PROGRAM-MANUAL.md,
docs/PROGRAM-MANUAL-digests.md, + any other tracked `*.md` carrying anchors). Then:
1. `--fix` the auto-fixable single-def inline `def_drift`.
2. Hand-fix range anchors (evidence-cited + count-asserted, like the `3f2c149` sweep).
3. **Qualify every `ambiguous_path` advisory** to a full path from surrounding context
   (drives the advisory set to zero — the BLOCKING-mitigation contract).
4. Report the full backlog (auto-fixed / hand-fixed / qualified).
`chief_director.py` anchors are already fixed (`3f2c149`); the sweep should show them
clean and surface the rest.

## 5. Testing (TDD)

New test classes in `tests/unit/test_check_doc_claims.py`, real-tmp-path style. Tests
that exercise basename resolution must **`git add` + commit the `.py` source** into the
tmp repo (the existing `_init_repo` only `git init`s + `_write_py` only writes a file;
neither populates `git ls-files` — a helper or per-test commit is required). Run with
`env -u GIT_INDEX_FILE` (D-a launch index breaks tmp-repo tests).

1. Inline-correct → no drift.
2. Inline def-drift → detected; `--fix` rewrites the **inline (backtick)** token (not to a link).
3. Bare-basename unique → resolves + checks.
4. Bare-basename ambiguous **with disambiguating symbol** → resolves to the candidate
   defining the symbol; a stale line is reported as `def_drift` (not advised away).
5. Bare-basename ambiguous **without disambiguating symbol** → `ambiguous_path` advisory,
   exit-neutral, candidates listed.
6. Bare-basename unresolvable (0 matches) → skipped (no drift).
7. Inline range anchor (`` `mod.py:3-9` ``) → range-match semantics.
8. Link + inline on same line, **same (file,line)** → counted once; **different
   (file,line)** (`[`old.py:5`](new.py:9)`) → BOTH checked.
9. `.ext` / version-token guard → `` `not_a_file:30` ``, `` `v1.2:30` ``, `` `.py:3` `` ignored.
10. Fenced-code-block → a resolvable `` `real/path.py:NN` `` inside a ```` ``` ```` block
    is NOT flagged and NOT rewritten by `--fix`.
11. Inline `out_of_bounds` with no bound symbol → reported.
12. Multi-anchor-per-line `--fix` → two inline anchors / a repeated token on one line are
    rewritten correctly (offset-safe, no prose corruption).
13. Pathological path tokens (absolute, parent-relative) → resolved-or-skipped per §4.1,
    no crash, no false `missing_file` for non-real tokens.

## 6. Acceptance criteria

1. An introduced inline-anchor def-drift is **detected**, including a **bare-AMBIGUOUS
   symbol-bound** anchor (regression-proven: revert one such anchor → tool reports it;
   v1-design + today's tool would not).
2. No new false positives on the existing doc set (illustrative/fenced/version tokens
   not flagged).
3. `--fix` corrects a single-def inline drift in place as a backtick token; ranges
   reported but untouched; nothing inside fences rewritten.
4. `ambiguous_path` advisories are non-fatal, list candidates, and are emitted only when
   symbol-disambiguation cannot resolve.
5. Full unit suite green (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest
   tests/unit/test_check_doc_claims.py`); existing tests unchanged-green; §15 smoke OK.
6. Slice 2: a repo-wide run reports **zero residual `def_drift`** AND **zero residual
   `ambiguous_path`** (all qualified to full paths) — no anchor silently unverified.

## 7. Risks / edge cases

- **Ambiguity-as-false-green** (the BLOCKING) — mitigated by §4.2 symbol-disambiguation +
  §4.6 sweep-to-empty + optional future `--strict`.
- **Fenced illustrative anchors** — mitigated by §4.1 fence tracking (checker + `--fix`).
- **Version-token false positives** — mitigated by the letters-only ext class + existence.
- **De-dup zero-count** (anchor inside a link display) — mitigated by the `(file,line)`
  equality rule, not span-inside.
- **`--fix` multi-occurrence** — span-based, rewrite-all-matching documented; fence-guarded.
- **git-absent-in-a-repo** — loud stderr warning when bare anchors exist but resolution is
  disabled (not a silent clean skip).
- **Range anchors spanning a moved block** — auto-fix stays off for ranges (manual).
- **Backward-compat** — markdown-link semantics, `--sha-refs`, `--show-subjects`, manifest
  path untouched; existing tests stay green (fence-skip only newly affects anchors that
  were inside fenced blocks — **verified 0 such anchors exist across the doc set**:
  a fence-state scan for link OR inline `path:line` anchors inside ```` ``` ````/`~~~`
  blocks over ARCHITECTURE/CLAUDE/AGENTS/DECISIONS/OPERATIONS/README/PROGRAM-MANUAL/
  digests returned **0** (ADR-013; re-run the scan before Slice 1 lands in case docs
  changed).

## 8. Composition with protocol

This is the Rule #18 verifier-buildout (closes the inline-anchor claim-type by
construction). The Slice-2 sweep is mechanical/verifier-confirmed doc-maintenance
(operator-owned); any prose-claim edits encountered stay senior-reviewed per Guard 1.
Claimed per user direction (overriding the director's `05-06-02Z` carry-forward,
user-tier authority); deconflicted with director at operator `05-13-00Z`.

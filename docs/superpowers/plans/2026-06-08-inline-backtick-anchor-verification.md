# Inline-Backtick Anchor Verification — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `scripts/check_doc_claims.py` so it also detects, resolves, def-drift-checks, and `--fix`es **inline-backtick** anchors (`` `path:line` `` / `` `path:line-line` ``), with no new false positives and **no anchor silently unverified-yet-passing**, then sweep the repo to drive residual drift and ambiguity to zero.

**Architecture:** Approach A — *extend in place*. Unify anchor iteration in `check_line_anchors` so both the existing markdown-link regex and a new inline-backtick regex feed the existing `check_anchor` def-drift/bounds logic and `_apply_fixes`. Inline anchors additionally need basename resolution (bare `` `controller.py:296` `` → tracked relpath) with **symbol-disambiguation** so an ambiguous basename never becomes a false-green. A new non-fatal `ambiguous_path` advisory covers the genuinely-undisambiguable residue, which Slice 2 then qualifies to empty.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `subprocess`, `dataclasses`, `pathlib`); pytest with real `tmp_path` git repos (no mocking). Source file: `scripts/check_doc_claims.py` (808 lines at HEAD). Tests: `tests/unit/test_check_doc_claims.py` (874 lines at HEAD).

**Spec:** `docs/superpowers/specs/2026-06-08-inline-backtick-anchor-verification-design.md` (v3, user-approved 2026-06-08).

---

## Conventions for the implementer (read first — project-specific)

Per `/Users/hyungkoookkim/Content/CLAUDE.md`:

1. **Impact analysis before editing a symbol.** `grep -rn 'symbolName' --include='*.py' .` to find callers/importers; Read the call sites; report blast radius. The two symbols you extend (`check_anchor`, `Drift`) have direct callers — see Task 3's grep.
2. **D-a commit discipline (MANDATORY).** This repo runs two seats sharing one working tree via per-seat `GIT_INDEX_FILE`. The index periodically re-acquires orphaned skip-worktree bits that make `git add`/commit silently drop edits to *tracked* files. **Before every commit that touches a tracked file:** run `git read-tree HEAD`, then `git add <paths>`, then `git commit -m … -- <paths>` (pathspec mandatory; `-m` value BEFORE the `--`). New files are immune (skip-worktree only affects tracked files), but `check_doc_claims.py` and the test file are tracked.
3. **Run tests with `env -u GIT_INDEX_FILE`.** The seat launch index breaks the tmp-repo git fixtures (`_init_repo`, and any test that `git add`s source). Every pytest command below is prefixed accordingly. Use the project venv: `.venv/bin/python`.
4. **Plan-vs-source divergence rule.** Line numbers below are accurate as of HEAD `a267bf0` but may drift as you commit. Where this plan's line ref and the actual source differ, **use the actual source** and note the divergence in your status report. The *code blocks* are authoritative for intent; match them to the live function by name, not by line number.
5. **One commit per task.** Don't `--amend` across tasks. Reviewers need a clean BASE..HEAD per task. Commit-body convention: `<type>(<scope>): <subject>` + the `Co-Authored-By:` trailer Claude Code injects.
6. **Test import block (do this as the FIRST edit of each task that adds tests).** The new tests import module-level symbols that don't exist yet. As you reach each task, add its symbols to the `from check_doc_claims import (...)` block at the top of `tests/unit/test_check_doc_claims.py` (~L26-36) — this is a real code step, not just a comment. Full set added across the plan: `_INLINE_ANCHOR_RE` (T1), `_build_basename_index` + `_resolve_inline_target` (T2), `_split_advisories` (T6). `_commit_py` is a local test helper (define it in the helpers block, not an import). A test that imports a symbol before its defining task exists will `ImportError` the whole module — keep imports in lock-step with the tasks.

**Smoke gate:** after the final Slice-1 task, run the `ARCHITECTURE.md` §15 smoke block; it must stay OK.

---

## File Structure

No new files. Two tracked files change:

- **Modify** `scripts/check_doc_claims.py` — one responsibility added (inline-anchor coverage), reusing existing machinery. New module-level symbols: `_INLINE_ANCHOR_RE`, `_FENCE_RE`, `ADVISORY_KINDS`, `_build_basename_index`, `_resolve_inline_target`, `_bind_inline_symbol`. Extended: `Drift` (2 defaulted fields), `check_anchor` (4 keyword-only params), `check_line_anchors` (inline iteration + fence tracking), `_apply_fixes` (inline rewrite branch), `main` (advisory partition).
- **Modify** `tests/unit/test_check_doc_claims.py` — new test classes for the 13 spec cases + a `_commit_py` helper (the existing `_init_repo` only `git init`s; basename-resolution tests must populate `git ls-files`).

Slice 2 modifies anchor *line numbers* inside tracked `*.md` docs (mechanical, verifier-confirmed) — no code.

---

## Chunk 1: Slice 1 — verifier extension (Tasks 1–7)

### Task 1: Foundation — Drift fields, regexes, advisory constant

**Files:**
- Modify: `scripts/check_doc_claims.py` (`Drift` dataclass ~L29-39; regex block ~L46-57)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestInlineRegex` class)

- [ ] **Step 1: Write the failing test** — the inline regex matches real anchors and rejects non-files / padded tokens.

```python
# Append near the other test classes. Import _INLINE_ANCHOR_RE at top of file:
#   from check_doc_claims import _INLINE_ANCHOR_RE  (add to the existing import block)

class TestInlineRegex:
    def test_matches_bare_and_pathed_and_range(self):
        def first(s):
            m = _INLINE_ANCHOR_RE.search(s)
            return None if not m else (m.group("file"), m.group("line"), m.group("end"))
        assert first("see `mod.py:10` here") == ("mod.py", "10", None)
        assert first("see `cinema/shots/controller.py:296` x") == ("cinema/shots/controller.py", "296", None)
        assert first("range `mod.py:3-9` ok") == ("mod.py", "3", "9")

    def test_rejects_non_file_and_padded_tokens(self):
        for s in [
            "`v1.2:30`",          # version token: ext is digits → letters-only ext rejects
            "`not_a_file:30`",    # no extension
            "`.py:3`",            # nothing before the dot
            "`time:30`",          # no extension
            "`mod.py:10 (note)`", # trailing chars before closing backtick
            "`mod.py:10)`",       # punctuation before backtick
            "`mod.py:10:20`",     # double colon
            "mod.py:10",          # no backticks at all
        ]:
            assert _INLINE_ANCHOR_RE.search(s) is None, f"should NOT match: {s!r}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestInlineRegex -v`
Expected: FAIL — `ImportError: cannot import name '_INLINE_ANCHOR_RE'`.

- [ ] **Step 3: Add the regexes + advisory constant + Drift fields**

In the regex block (after `_IDENT_RE`, ~L57) add:

```python
# Inline-backtick anchor: `path:line` or `path:line-line`.
# The literal backticks ARE part of the match (so the span includes them) →
# this is what enforces "standalone token": `mod.py:10)` / `mod.py:10 (x)` /
# `mod.py:10:20` do NOT match. Extension class is letters-only ([A-Za-z]+),
# matching _ANCHOR_RE, so version tokens (`v1.2:30`) are rejected.
_INLINE_ANCHOR_RE = re.compile(
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:-(?P<end>\d+))?`'
)

# Fenced-code-block markers (``` or ~~~, 3+). A line starting one toggles fence state.
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')

# Drift kinds that are advisory (non-fatal; exit-code-neutral).
ADVISORY_KINDS = {"ambiguous_path"}
```

In the `Drift` dataclass, update the `kind` comment and append two defaulted fields (defaults keep every existing `Drift(...)` construction + direct test imports backward-compatible):

```python
@dataclass
class Drift:
    doc_path: str
    doc_line: int
    target_file: str
    target_line: int
    kind: str                    # missing_file | def_drift | out_of_bounds | ambiguous_path
    symbol: Optional[str]
    suggested_line: Optional[int]
    fixable: bool
    message: str
    style: str = "link"          # "link" | "inline" — which syntax to rewrite on --fix
    candidates: Optional[list[str]] = None   # ambiguous_path: the colliding tracked relpaths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestInlineRegex -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): inline-anchor regex + Drift.style/candidates + ADVISORY_KINDS (T1)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 2: Basename index + symbol-disambiguating resolution

**Files:**
- Modify: `scripts/check_doc_claims.py` (new helpers after `_def_lines`, ~L72)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestResolveInlineTarget` class + `_commit_py` helper)

The BLOCKING-fix core. `_build_basename_index` maps basename → tracked relpaths from `git ls-files` (tracked-only ⇒ excludes `.claude/worktrees/*`, `.venv/`, untracked copies — the trap that would make every basename look ambiguous). `_resolve_inline_target` resolves a token to one relpath, using the bound symbol to disambiguate collisions.

- [ ] **Step 1: Add a `_commit_py` test helper** (the existing `_init_repo` only `git init`s; `git ls-files` is empty until source is committed).

```python
# Add beside _init_repo / _commit in the helpers block:
def _commit_py(repo: Path, relpath: str, content: str) -> Path:
    """Write a .py at relpath (creating dirs), git add + commit it so it appears
    in `git ls-files`. Returns the absolute path."""
    p = repo / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    _git(repo, "add", relpath)
    _git(repo, "commit", "-q", "-m", f"add {relpath}")
    return p
```

- [ ] **Step 2: Write the failing tests**

```python
# Import the new helpers at top of file:
#   from check_doc_claims import _build_basename_index, _resolve_inline_target

class TestResolveInlineTarget:
    def _index(self, repo):
        idx, ok = _build_basename_index(repo)
        assert ok is True
        return idx

    def test_unique_basename_resolves(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "def f():\n    pass\n")
        idx = self._index(tmp_path)
        rel, cand = _resolve_inline_target("alpha.py", None, idx, tmp_path)
        assert rel == "alpha.py" and cand is None

    def test_ambiguous_resolved_by_symbol(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "class Top:\n    pass\n")
        _commit_py(tmp_path, "domain/controller.py", "def find_take():\n    pass\n")
        idx = self._index(tmp_path)
        # symbol find_take is defined only in domain/controller.py → disambiguates
        rel, cand = _resolve_inline_target("controller.py", "find_take", idx, tmp_path)
        assert rel == "domain/controller.py" and cand is None

    def test_ambiguous_without_symbol_is_advisory(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "x = 1\n")
        _commit_py(tmp_path, "domain/controller.py", "y = 2\n")
        idx = self._index(tmp_path)
        rel, cand = _resolve_inline_target("controller.py", None, idx, tmp_path)
        assert rel is None
        assert cand == ["controller.py", "domain/controller.py"]

    def test_ambiguous_symbol_in_two_candidates_is_advisory(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "def shared():\n    pass\n")
        _commit_py(tmp_path, "domain/controller.py", "def shared():\n    pass\n")
        idx = self._index(tmp_path)
        rel, cand = _resolve_inline_target("controller.py", "shared", idx, tmp_path)
        assert rel is None and cand == ["controller.py", "domain/controller.py"]

    def test_zero_match_is_skip(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "x = 1\n")
        idx = self._index(tmp_path)
        rel, cand = _resolve_inline_target("ghost.py", None, idx, tmp_path)
        assert rel is None and cand is None

    def test_dir_qualified_passthrough(self, tmp_path):
        idx = {}  # dir-qualified does not consult the index
        rel, cand = _resolve_inline_target("cinema/x.py", None, idx, tmp_path)
        assert rel == "cinema/x.py" and cand is None

    def test_absolute_and_parent_relative_skip(self, tmp_path):
        idx = {}
        assert _resolve_inline_target("/etc/x.py", None, idx, tmp_path) == (None, None)
        assert _resolve_inline_target("../x.py", None, idx, tmp_path) == (None, None)
```

- [ ] **Step 3: Run to verify failure**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestResolveInlineTarget -v`
Expected: FAIL — ImportError on `_build_basename_index` / `_resolve_inline_target`.

- [ ] **Step 4: Implement the helpers** (after `_def_lines`, ~L72)

```python
def _build_basename_index(repo_root: Path) -> "tuple[dict[str, list[str]], bool]":
    """Map basename -> sorted [tracked relpaths] from `git ls-files`.

    git ls-files is tracked-only, so worktree/venv/dist copies are excluded —
    the exact trap that would make every basename look ambiguous. Returns
    (index, git_ok); git_ok=False when git is unavailable/errors (index empty).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return {}, False
    index: dict[str, list[str]] = {}
    for rel in out.splitlines():
        rel = rel.strip()
        if rel:
            index.setdefault(Path(rel).name, []).append(rel)
    for k in index:
        index[k].sort()
    return index, True


def _resolve_inline_target(
    token_file: str,
    symbol: Optional[str],
    basename_index: "dict[str, list[str]]",
    repo_root: Path,
) -> "tuple[Optional[str], Optional[list[str]]]":
    """Resolve an inline anchor's file token to a tracked relpath.

    Returns (resolved_rel, candidates):
      (rel, None)        -> resolved to exactly one path; caller checks it.
      (None, None)       -> skip (0 matches / absolute / parent-relative).
      (None, [c1, c2..]) -> ambiguous_path advisory (candidates listed).
    Directory-qualified within-repo tokens pass through as-is; existence
    (incl. missing_file) is handled downstream by check_anchor.
    """
    parts = token_file.split("/")
    if token_file.startswith("/") or ".." in parts:
        return None, None                       # absolute / parent-relative -> skip
    if "/" in token_file:
        return token_file, None                 # dir-qualified within repo
    matches = basename_index.get(token_file, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) == 0:
        return None, None                       # not a real tracked file -> skip
    # Ambiguous (>=2): try symbol-disambiguation.
    if symbol:
        defining = [
            c for c in matches
            if _def_lines(
                (repo_root / c).read_text(encoding="utf-8", errors="replace").splitlines(),
                symbol,
            )
        ]
        if len(defining) == 1:
            return defining[0], None            # disambiguated -> real check
    return None, matches                        # truly ambiguous -> advisory
```

- [ ] **Step 5: Run to verify pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestResolveInlineTarget -v`
Expected: PASS (all 7).

- [ ] **Step 6: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): basename index + symbol-disambiguating inline resolution (T2, BLOCKING fix)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 3: Extend `check_anchor` to accept a pre-resolved path + pre-bound symbol

**Files:**
- Modify: `scripts/check_doc_claims.py` (`check_anchor` ~L79-196)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestCheckAnchorInlineParams`)

**Impact analysis (do this first):**

```bash
grep -rn 'check_anchor' --include='*.py' .
```

Expected callers: `check_line_anchors` (`scripts/check_doc_claims.py`) and the direct test imports in `tests/unit/test_check_doc_claims.py`. All new params are **keyword-only with defaults** → every existing call is unchanged. Report the caller list in your status.

- [ ] **Step 1: Write the failing test** — calling with a resolved path + pre-bound symbol checks the resolved file and stores the written token.

```python
class TestCheckAnchorInlineParams:
    def test_resolved_rel_and_bound_symbol(self, tmp_path):
        # Source lives at domain/controller.py; doc writes the bare token controller.py.
        src = tmp_path / "domain" / "controller.py"
        src.parent.mkdir(parents=True)
        src.write_text("# l1\n# l2\ndef find_take():\n    pass\n")  # def at line 3
        line_text = "**`find_take()`** — `controller.py:2`"  # anchor says 2, stale
        drift = check_anchor(
            doc_path="d.md", doc_line_num=1, doc_line_text=line_text,
            target_file_rel="controller.py", target_line=2,
            display_text="controller.py:2", repo_root=tmp_path,
            resolved_rel="domain/controller.py", symbol="find_take",
            rebind_symbol=False, style="inline",
        )
        assert drift is not None
        assert drift.kind == "def_drift"
        assert drift.suggested_line == 3
        assert drift.target_file == "controller.py"   # WRITTEN token, not resolved path
        assert drift.style == "inline"
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestCheckAnchorInlineParams -v`
Expected: FAIL — `check_anchor() got an unexpected keyword argument 'resolved_rel'`.

- [ ] **Step 3: Extend `check_anchor`.** Change the signature and three internals; leave the def-drift/bounds logic intact.

Signature (add keyword-only params):

```python
def check_anchor(
    doc_path: str,
    doc_line_num: int,
    doc_line_text: str,
    target_file_rel: str,
    target_line: int,
    display_text: str,
    repo_root: Path,
    *,
    resolved_rel: Optional[str] = None,
    symbol: Optional[str] = None,
    rebind_symbol: bool = True,
    style: str = "link",
) -> Optional[Drift]:
```

Change 1 — read the resolved path but keep the written token for the Drift. Replace the `target_path = repo_root / target_file_rel` line with:

```python
    read_rel = resolved_rel if resolved_rel is not None else target_file_rel
    target_path = repo_root / read_rel
```

Change 2 — symbol binding: when `rebind_symbol` is False, use the passed `symbol` and skip the internal nearest-backtick binding (L107-138). Wrap the existing binding block:

```python
    if rebind_symbol:
        # ... EXISTING binding block (backtick_tokens / anchor_match / before-after / dotted-skip) ...
        # (unchanged; it sets `symbol` from doc_line_text)
        ...
    # else: use the `symbol` parameter as-is (pre-bound by check_line_anchors).
```

Change 3 — set `style=style` on **every** `Drift(...)` constructed in this function (the `missing_file`, `def_drift`, and `out_of_bounds` returns) and keep `target_file=target_file_rel` (the written token). Example for the `def_drift` return:

```python
                return Drift(
                    doc_path=doc_path,
                    doc_line=doc_line_num,
                    target_file=target_file_rel,      # written token
                    target_line=target_line,
                    kind="def_drift",
                    symbol=symbol,
                    suggested_line=suggested,
                    fixable=fixable,
                    message=(...),
                    style=style,
                )
```

> Note: `rebind_symbol=True` + `resolved_rel=None` + `style="link"` is exactly the existing behavior, so link callers and existing tests are unaffected.

- [ ] **Step 4: Run to verify pass + no regression**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -v`
Expected: the new test PASSES and every pre-existing test stays green.

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): check_anchor accepts pre-resolved path + pre-bound symbol + style (T3, additive)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 4: Wire inline anchors through `check_line_anchors` (detection + binding + fence + resolve)

**Files:**
- Modify: `scripts/check_doc_claims.py` (`check_line_anchors` ~L203-234; new `_bind_inline_symbol` helper)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestInlineAnchorsE2E`)

This is the integration task — it realizes spec §4.1 (detection + fence + de-dup), §4.2 (resolution **after** symbol binding — load-bearing ordering), §4.3 (inline binding), §4.4 (`ambiguous_path` emission).

- [ ] **Step 1: Write the failing tests** (drive spec tests 1,2-detect,4,5,6,7,8,10,11 via the public `check_line_anchors`).

```python
class TestInlineAnchorsE2E:
    def _doc(self, repo, text):
        return _write_md(repo, "doc.md", text)

    def test_inline_correct_no_drift(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2
        md = self._doc(tmp_path, "see **`f()`** `alpha.py:2`\n")
        assert check_line_anchors([str(md)], tmp_path) == []

    def test_inline_def_drift_detected(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\ndef f():\n    pass\n")  # def at 4
        md = self._doc(tmp_path, "see **`f()`** `alpha.py:2`\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        assert drifts[0].kind == "def_drift" and drifts[0].style == "inline"
        assert drifts[0].suggested_line == 4 and drifts[0].target_file == "alpha.py"

    def test_bare_ambiguous_with_symbol_detects_drift(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "class Top:\n    pass\n")
        _commit_py(tmp_path, "domain/controller.py", "# 1\n# 2\ndef find_take():\n    pass\n")  # def at 3
        md = self._doc(tmp_path, "**`find_take()`** — `controller.py:1` stale\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        assert drifts[0].kind == "def_drift" and drifts[0].suggested_line == 3

    def test_bare_ambiguous_no_symbol_is_advisory(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "x = 1\n")
        _commit_py(tmp_path, "domain/controller.py", "y = 2\n")
        md = self._doc(tmp_path, "plain `controller.py:1` with no symbol\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "ambiguous_path" and d.fixable is False
        assert d.candidates == ["controller.py", "domain/controller.py"]

    def test_bare_unresolvable_skipped(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "x = 1\n")
        md = self._doc(tmp_path, "ghost `ghost.py:9` not real\n")
        assert check_line_anchors([str(md)], tmp_path) == []

    def test_inline_range_anchor(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2, inside 1-3
        md = self._doc(tmp_path, "block **`f()`** `alpha.py:1-3`\n")
        assert check_line_anchors([str(md)], tmp_path) == []  # def within range -> ok

    def test_link_and_inline_same_line_distinct_both_checked(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\ndef f():\n    pass\n")  # def at 3
        # inline says 1 (stale), link says 2 (stale) — DISTINCT (file,line) -> both drift
        md = self._doc(tmp_path, "**`f`** `alpha.py:1` and [f](alpha.py:2)\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 2
        assert {d.style for d in drifts} == {"inline", "link"}

    def test_link_and_inline_same_target_deduped(self, tmp_path):
        # Spec test 8, same-(file,line) sub-case: link + inline pointing at the
        # IDENTICAL (file,line) -> the inline is de-duped, only the link drifts.
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")  # def at 5
        # both anchors say alpha.py:3 (stale) -> exactly ONE drift (the link's)
        md = self._doc(tmp_path, "**`f`** `alpha.py:3` see [f](alpha.py:3)\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        assert drifts[0].style == "link" and drifts[0].suggested_line == 5

    def test_fenced_anchor_not_flagged(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2
        md = self._doc(tmp_path, "```\nexample **`f()`** `alpha.py:999`\n```\n")
        assert check_line_anchors([str(md)], tmp_path) == []  # inside fence -> skipped

    def test_inline_out_of_bounds_no_symbol(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "x = 1\ny = 2\n")  # 2 lines
        md = self._doc(tmp_path, "plain `alpha.py:99` overflow\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1 and drifts[0].kind == "out_of_bounds"
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestInlineAnchorsE2E -v`
Expected: FAIL (drifts not detected / advisory kind missing).

- [ ] **Step 3: Add `_bind_inline_symbol`** (nearest **preceding** backtick, excluding the anchor's own span) near the binding logic:

```python
def _bind_inline_symbol(line_text: str, anchor_start: int) -> Optional[str]:
    """Bind the symbol for an inline anchor: the nearest backtick token that ENDS
    before `anchor_start` (preceding-only — drop the markdown-link after-fallback,
    since the inline convention is symbol-precedes-anchor). Excludes the anchor's
    own backtick span by construction (we only consider tokens ending <= anchor_start).
    Returns the leading identifier, or None (incl. the dotted-attribute skip)."""
    preceding = [t for t in _BACKTICK_RE.finditer(line_text) if t.end() <= anchor_start]
    if not preceding:
        return None
    token_text = preceding[-1].group(1)
    ident_match = _IDENT_RE.match(token_text)
    if not ident_match:
        return None
    ident = ident_match.group(1)
    pos_after = ident_match.end()
    if pos_after < len(token_text) and token_text[pos_after] == ".":
        return None  # dotted/attribute -> no symbol bind (falls through to bounds)
    return ident
```

- [ ] **Step 4: Rewrite the body of `check_line_anchors`** to track fences, iterate both regexes, bind-then-resolve inline anchors, and emit `ambiguous_path`. Build the basename index once at the top.

```python
def check_line_anchors(doc_paths: list[str], repo_root: Path) -> list[Drift]:
    """Check all line-anchors (markdown-link AND inline-backtick) in the given docs."""
    drifts: list[Drift] = []
    basename_index, git_ok = _build_basename_index(repo_root)
    unresolved_bare = 0   # for the git-absent warning (Task 6)

    for doc_path in doc_paths:
        full_path = Path(doc_path) if Path(doc_path).is_absolute() else repo_root / doc_path
        if not full_path.exists():
            continue
        doc_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()

        in_fence = False
        for line_num, line_text in enumerate(doc_lines, 1):
            if _FENCE_RE.match(line_text):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            # --- markdown-link anchors (existing behavior) ---
            link_keys = set()
            for m in _ANCHOR_RE.finditer(line_text):
                target_file_rel = m.group("file")
                target_line = int(m.group("line"))
                link_keys.add((target_file_rel, target_line))
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=target_file_rel,
                    target_line=target_line, display_text=m.group("display"),
                    repo_root=repo_root,
                )
                if drift is not None:
                    drifts.append(drift)

            # --- inline-backtick anchors (new) ---
            for m in _INLINE_ANCHOR_RE.finditer(line_text):
                token_file = m.group("file")
                target_line = int(m.group("line"))
                # de-dup: skip an inline match whose (file,line) equals a link on the
                # same line (rare; correctness guard, not a span-inside heuristic).
                if (token_file, target_line) in link_keys:
                    continue
                # ORDERING: bind symbol BEFORE resolution (resolution needs it).
                symbol = _bind_inline_symbol(line_text, m.start())
                resolved_rel, candidates = _resolve_inline_target(
                    token_file, symbol, basename_index, repo_root)
                if candidates is not None:
                    drifts.append(Drift(
                        doc_path=str(full_path), doc_line=line_num,
                        target_file=token_file, target_line=target_line,
                        kind="ambiguous_path", symbol=symbol, suggested_line=None,
                        fixable=False,
                        message=(f"`{token_file}` is ambiguous ({len(candidates)} tracked "
                                 f"matches): {', '.join(candidates)} — qualify with a directory"),
                        style="inline", candidates=candidates,
                    ))
                    continue
                if resolved_rel is None:
                    if "/" not in token_file and not git_ok:
                        unresolved_bare += 1
                    continue
                end = m.group("end")
                display = f"{token_file}:{target_line}" + (f"-{end}" if end else "")
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=token_file,
                    target_line=target_line, display_text=display, repo_root=repo_root,
                    resolved_rel=resolved_rel, symbol=symbol,
                    rebind_symbol=False, style="inline",
                )
                if drift is not None:
                    drifts.append(drift)

    if unresolved_bare and not git_ok:
        print(f"WARNING: {unresolved_bare} bare inline anchor(s) could not be resolved "
              f"(git unavailable — basename index empty). These were skipped, NOT verified.",
              file=sys.stderr)
    return drifts
```

> The synthesized `display` (`token_file:line[-end]`) lets `check_anchor`'s existing
> `re.search(r':(\d+)-(\d+)$', display_text)` range-match logic work for inline ranges
> with zero change to that block (spec §4.3 "the existing range-match def-drift check, unchanged").

- [ ] **Step 5: Run to verify pass + no regression**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -v`
Expected: all `TestInlineAnchorsE2E` PASS; every pre-existing test green.

- [ ] **Step 6: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): check_line_anchors inline iteration + fence + bind-then-resolve + ambiguous_path (T4)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 5: `--fix` inline branch in `_apply_fixes`

**Files:**
- Modify: `scripts/check_doc_claims.py` (`_apply_fixes` ~L261-295)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestInlineFix`)

- [ ] **Step 1: Write the failing tests** (spec tests 2-fix, 10-no-fix-in-fence, 12-multi-anchor).

```python
class TestInlineFix:
    def test_fix_rewrites_inline_to_backtick(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\ndef f():\n    pass\n")  # def at 4
        md = _write_md(tmp_path, "doc.md", "see **`f()`** `alpha.py:2` here\n")
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == "see **`f()`** `alpha.py:4` here\n"   # backtick form, not a link

    def test_fix_multiple_inline_on_one_line(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "def f():\n    pass\n")        # def at 1
        _commit_py(tmp_path, "beta.py", "# 1\ndef g():\n    pass\n")    # def at 2
        md = _write_md(tmp_path, "doc.md", "**`f()`** `alpha.py:9` and **`g()`** `beta.py:9`\n")
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == "**`f()`** `alpha.py:1` and **`g()`** `beta.py:2`\n"

    def test_fix_never_touches_fenced_anchor(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "def f():\n    pass\n")        # def at 1
        text = "```\n**`f()`** `alpha.py:999`\n```\n"
        md = _write_md(tmp_path, "doc.md", text)
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == text   # untouched (fenced -> never a drift -> never fixed)
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestInlineFix -v`
Expected: FAIL — inline anchors not rewritten (current `_apply_fixes` only runs `_ANCHOR_RE.sub`).

- [ ] **Step 3: Extend `_apply_fixes`.** In the per-drift loop, after computing `old`/`new`, run BOTH a link rewrite and an inline rewrite (each keyed on `(target_file, old)`). Neither regex matches the other's syntax, so this is safe for link-only, inline-only, and the rare same-line both-syntaxes case (spec §4.5). Replace the single `lines[idx] = _ANCHOR_RE.sub(...)` with:

```python
        for drift in doc_drifts:
            idx = drift.doc_line - 1
            old, new = drift.target_line, drift.suggested_line

            def _rewrite_link(m, _d=drift, _old=old, _new=new):
                if m.group("file") != _d.target_file or int(m.group("line")) != _old:
                    return m.group(0)
                new_display = _shift_display(m.group("display"), _old, _new)
                return f"[{new_display}]({_d.target_file}:{_new})"

            def _rewrite_inline(m, _d=drift, _old=old, _new=new):
                if m.group("file") != _d.target_file or int(m.group("line")) != _old:
                    return m.group(0)
                end = m.group("end")
                body = _shift_display(f"{_d.target_file}:{_old}" + (f"-{end}" if end else ""), _old, _new)
                return f"`{body}`"

            lines[idx] = _ANCHOR_RE.sub(_rewrite_link, lines[idx])
            lines[idx] = _INLINE_ANCHOR_RE.sub(_rewrite_inline, lines[idx])
            print(f"  FIXED  {drift.doc_path}:{drift.doc_line}  "
                  f"{drift.target_file}:{old} → {drift.target_file}:{new}")
```

> `_is_fixable` already gates on `kind == "def_drift" and fixable`, so `ambiguous_path`
> / ranges / `missing_file` are never auto-fixed (acceptance #3/#4). Ranges: a single-def
> `def_drift` is never a range (range anchors have ≥2 def candidates in their span or no
> single suggested line), so the `_rewrite_inline` range branch is defensive only.

- [ ] **Step 4: Run to verify pass + no regression**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -v`
Expected: `TestInlineFix` PASS; all prior tests green (the link-fix tests still pass — `_rewrite_inline` finds nothing in their lines).

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): --fix rewrites inline anchors as backtick tokens (T5)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 6: `main()` advisory partition + exit-neutrality

**Files:**
- Modify: `scripts/check_doc_claims.py` (`main` ~L737-804)
- Test: `tests/unit/test_check_doc_claims.py` (new `TestAdvisoryExitNeutral`)

`ambiguous_path` must print but NOT set exit 1. Partition `drifts` into `fatal` vs `advisories` and base the exit code on `fatal` only.

- [ ] **Step 1: Write the failing test** — exercise the partition via a small helper so we don't need to drive the real-repo `main()`. Add a tiny module-level helper and test it.

```python
class TestAdvisoryExitNeutral:
    def test_partition_helper(self):
        from check_doc_claims import _split_advisories, Drift
        fatal = Drift("d", 1, "a.py", 2, "def_drift", "f", 4, True, "m")
        adv = Drift("d", 2, "controller.py", 1, "ambiguous_path", None, None, False, "m",
                    style="inline", candidates=["controller.py", "domain/controller.py"])
        f, a = _split_advisories([fatal, adv])
        assert f == [fatal] and a == [adv]

    def test_advisory_only_is_clean_exit(self, tmp_path, capsys, monkeypatch):
        # An ambiguous-only doc must not be exit 1. Drive run() + the partition.
        _init_repo(tmp_path)
        _commit_py(tmp_path, "controller.py", "x = 1\n")
        _commit_py(tmp_path, "domain/controller.py", "y = 2\n")
        md = _write_md(tmp_path, "doc.md", "plain `controller.py:1`\n")
        from check_doc_claims import _split_advisories
        fatal, adv = _split_advisories(run([str(md)], tmp_path))
        assert fatal == [] and len(adv) == 1 and adv[0].kind == "ambiguous_path"
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestAdvisoryExitNeutral -v`
Expected: FAIL — `cannot import name '_split_advisories'`.

- [ ] **Step 3: Add `_split_advisories` + rework `main()`'s anchor-report block.** Add the helper near `_apply_fixes`:

```python
def _split_advisories(drifts: list[Drift]) -> "tuple[list[Drift], list[Drift]]":
    """Partition into (fatal, advisory) by kind. Advisories are exit-code-neutral."""
    fatal = [d for d in drifts if d.kind not in ADVISORY_KINDS]
    advisory = [d for d in drifts if d.kind in ADVISORY_KINDS]
    return fatal, advisory
```

Replace `main()`'s block from `drifts = run(...)` through `return 1` (~L775-804) with:

```python
    drifts = run(docs, repo_root, fix=args.fix)
    fatal, advisories = _split_advisories(drifts)

    if not fatal and not advisories:
        print(f"{'All' if not args.fix else 'Remaining'} anchors checked — no drift.")
        return 0

    if fatal:
        print(f"\n{'='*60}")
        print(f"DOC-ANCHOR DRIFT REPORT  ({len(fatal)} issue(s))")
        print(f"{'='*60}")
        for d in fatal:
            fix_hint = f"  → suggested: line {d.suggested_line}" if d.suggested_line else ""
            print(
                f"  [{d.kind}]  {d.doc_path}:{d.doc_line}"
                f"  →  {d.target_file}:{d.target_line}"
                + (f"  (symbol: `{d.symbol}`)" if d.symbol else "")
                + fix_hint
            )
            print(f"    {d.message}")
        fixable_count = sum(1 for d in fatal if d.fixable)
        if fixable_count:
            print(f"\n{fixable_count} fixable def_drift(s). Run: "
                  f".venv/bin/python scripts/check_doc_claims.py --fix")
        unfixable = [d for d in fatal if not d.fixable]
        if unfixable:
            print(f"{len(unfixable)} drift(s) require manual intervention.")

    if advisories:
        print(f"\n{'-'*60}")
        print(f"ADVISORIES  ({len(advisories)} ambiguous anchor(s) — exit-neutral)")
        print(f"{'-'*60}")
        for d in advisories:
            print(f"  [{d.kind}]  {d.doc_path}:{d.doc_line}  `{d.target_file}:{d.target_line}`")
            print(f"    {d.message}")

    return 1 if fatal else 0
```

- [ ] **Step 4: Run to verify pass + full suite + smoke**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -v`
Expected: all PASS.
Run the §15 smoke block from `ARCHITECTURE.md`. Expected: OK.

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(doc-verifier): exit-neutral ambiguous_path advisories in main() (T6)" -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 7: Acceptance gate (Slice 1) — no new code

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -q`
Expected: all pass, 0 fail. Capture the `N passed` line.

- [ ] **Step 2: Regression-prove the BLOCKING case (acceptance #1).** Confirm a bare-AMBIGUOUS symbol-bound anchor in a *real* doc is caught: pick a real manual anchor like `` **`validate_shot_prompts(...)`** — `controller.py:NNN` ``, revert its line to a stale value in a scratch copy, run the checker, see `def_drift`. Document the command + output in the status report (do NOT commit the scratch edit).

- [ ] **Step 3: Confirm acceptance #2 (no new false positives).** Run the extended checker over `ARCHITECTURE.md` (link-only doc): output must be unchanged vs. pre-task (no new flags).

Run: `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md`
Expected: `All anchors checked — no drift.` (or the same set of pre-existing drifts as before this branch — note any).

- [ ] **Step 4: Report.** Status DONE; paste the suite count + the regression-proof command/output. No commit (verification task).

---

## Chunk 2: Slice 2 — repo-wide sweep (Task 8)

### Task 8: Sweep the doc set and drive residual to zero

**Files:**
- Modify: anchor *line numbers* in tracked `*.md` (mechanical). Candidate set: `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`, `DECISIONS.md`, `OPERATIONS.md`, `README.md`, `docs/PROGRAM-MANUAL.md`, `docs/PROGRAM-MANUAL-digests.md`, plus any other tracked `*.md` carrying anchors.

This is mechanical/verifier-confirmed doc-maintenance (Rule #18 Guard-1: anchor-line fixes are operator-owned; any *prose-claim* edit you encounter stays senior-reviewed — do NOT change prose, only anchor line numbers). Per ADR-013 / Rule #1, every count claim in the report needs its command output.

- [ ] **Step 1: Pre-sweep fence re-verification (spec §7).** Re-confirm 0 anchors live inside fenced blocks across the doc set (the spec verified this at design time; docs may have changed). If any appear, they are correctly skipped — note them.

```bash
env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# quick fence-state scan over the doc set; print any path:line anchor inside a fence
PY
```
(Implement the scan inline or rely on the checker's behavior; the point is the report states the count.)

- [ ] **Step 2: Run the checker across the full doc set; capture the backlog.**

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py \
  ARCHITECTURE.md CLAUDE.md AGENTS.md DECISIONS.md OPERATIONS.md README.md \
  docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md 2>&1 | tee /tmp/anchor_backlog.txt
```
Expected: a DRIFT REPORT (fixable def_drift) + an ADVISORIES section. `chief_director.py` anchors should already be clean (fixed in `3f2c149`).

- [ ] **Step 3: Auto-fix the single-def inline def_drift.**

```bash
git read-tree HEAD
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py --fix \
  ARCHITECTURE.md CLAUDE.md AGENTS.md DECISIONS.md OPERATIONS.md README.md \
  docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
```
Review the diff (`git diff -- '*.md' docs/`): every change must be an anchor line-number shift only. Count-assert the FIXED lines.

- [ ] **Step 4: Hand-fix range anchors** (auto-fix stays off for ranges). For each reported `def_drift` on a range anchor, find the new span from source and edit by hand, evidence-cited (like the `3f2c149` sweep). Count-assert.

- [ ] **Step 5: Qualify every residual `ambiguous_path` advisory to a full path** (drives the advisory set to empty — the BLOCKING-mitigation contract, acceptance #6). For each advisory, determine the intended file from surrounding context and rewrite the bare `` `controller.py:NNN` `` → `` `cinema/shots/controller.py:NNN` `` (or the correct sibling). Re-run to confirm it now resolves + checks.

- [ ] **Step 6: Final verification (acceptance #6).**

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py \
  ARCHITECTURE.md CLAUDE.md AGENTS.md DECISIONS.md OPERATIONS.md README.md \
  docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
```
Expected: `All anchors checked — no drift.` — **zero residual `def_drift` AND zero residual `ambiguous_path`.**
Run the §15 smoke block. Expected: OK.

- [ ] **Step 7: Commit** (one commit for the sweep; if range/qualify hand-edits are large, a second `docs:` commit is acceptable — keep auto-fix vs hand-fix separable in the body).

```bash
git read-tree HEAD
git add ARCHITECTURE.md CLAUDE.md AGENTS.md DECISIONS.md OPERATIONS.md README.md docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
git commit -m "docs(anchors): repo-wide inline-anchor sweep — zero residual drift + zero ambiguous (Slice 2)" -- ARCHITECTURE.md CLAUDE.md AGENTS.md DECISIONS.md OPERATIONS.md README.md docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
```
Report: auto-fixed / hand-fixed / qualified counts, each with command output (ADR-013).

---

## Acceptance criteria (from spec §6 — final gate)

1. An introduced inline-anchor def-drift is **detected**, including a **bare-AMBIGUOUS symbol-bound** anchor (Task 7 Step 2 regression-proof).
2. No new false positives on the existing doc set (Task 7 Step 3).
3. `--fix` corrects single-def inline drift in place as a **backtick token**; ranges reported but untouched; nothing inside fences rewritten (Task 5).
4. `ambiguous_path` advisories are non-fatal, list candidates, emitted only when symbol-disambiguation cannot resolve (Tasks 4 + 6).
5. Full unit suite green; existing tests unchanged-green; §15 smoke OK (Task 7).
6. Slice 2: repo-wide run reports **zero residual `def_drift` AND zero residual `ambiguous_path`** (Task 8 Step 6).

## Execution notes

- **Reviewer focus (per task):** Task 2 (the BLOCKING fix) and Task 4 (ordering: bind-before-resolve) are the load-bearing correctness points — a reviewer should confirm the symbol is bound before `_resolve_inline_target` is called, else every bare ambiguous anchor silently falls to advisory. Task 3 changes a public signature — confirm all existing `check_anchor` callers are unaffected (keyword-only defaults).
- **Concurrency/threading:** none introduced.
- **Lane V:** this is operator-driven work; the spec is operator-owned (Finding-1, user-directed). Independent review per task applies.

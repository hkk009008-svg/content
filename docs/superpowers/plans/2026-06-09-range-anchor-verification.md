# Range-Anchor Verification (Finding-1 Slice 3) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make en-dash/em-dash range anchors (`` `file.py:N–M` ``) visible to `scripts/check_doc_claims.py` (closing a 258-anchor blind spot that hid 43 real drifts), then sweep the now-surfaced drift and correct the Slice-2 false-clean.

**Architecture:** Surgical regex tolerance (spec Approach A). Widen the range-separator character class from ASCII `-` to `[-–—]` in `_INLINE_ANCHOR_RE` (detection) and `_shift_display` (defensive). `--fix` already emits ASCII hyphen, so a touched anchor is canonicalized automatically. Add a `_MULTIRANGE_RE` warn-don't-verify guard for comma-list ranges the regex can't parse. Then a mechanical doc sweep.

**Tech Stack:** Python 3.13 (stdlib `re`, `argparse`), pytest. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-09-range-anchor-verification-design.md` (`af8eab1`, cold-reviewed APPROVED).

**Conventions (from CLAUDE.md — every implementer MUST follow):**
- **D-a per-seat index:** before every tracked-file commit, `git read-tree HEAD`; stage with `git add <paths>`; commit with `git commit -m … -- <pathspec>` (pathspec MANDATORY, `-m` BEFORE `--`). A wholesale `git commit -am` reverts the peer's work.
- **pytest:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest …` (the seat index breaks the tests' tmp-repo git fixtures). Use `.venv/bin/python`, never system `python3`.
- **Impact analysis:** before editing a symbol, `grep -rn 'symbolName' --include='*.py' .` and read call sites. `_INLINE_ANCHOR_RE`, `_shift_display`, `check_line_anchors` are all internal to `check_doc_claims.py` (verify with grep — they are not imported elsewhere except the test file).
- **Plan-vs-source divergence:** where this plan's line numbers/code differ from current source, use the source and report the divergence. Line numbers are as of HEAD `af8eab1`.

**Test scaffolding (already in `tests/unit/test_check_doc_claims.py`):** `_init_repo(tmp_path)`, `_write_py(tmp_path, name, content)`, `_write_md(tmp_path, name, content)`, `_commit_py(tmp_path, relpath, content)`. Drive checks via `check_line_anchors([str(md)], tmp_path)` (returns `list[Drift]`) and `run([str(md)], tmp_path, fix=True)` (applies fixes, returns remaining). Capture warnings via the `capsys` fixture → `capsys.readouterr().err`. A `Drift` has `.kind` (`"def_drift"`/`"out_of_bounds"`/`"missing_file"`/`"ambiguous_path"`), `.target_line`, `.suggested_line`, `.symbol`, `.fixable`.

---

## Chunk 1: Verifier enhancement + sweep

### Task 1: En/em-dash detection in `_INLINE_ANCHOR_RE`

**Files:**
- Modify: `scripts/check_doc_claims.py` (the `_INLINE_ANCHOR_RE` definition, ~L66-70)
- Test: `tests/unit/test_check_doc_claims.py` (add to the inline-anchor test class, near `test_inline_range_anchor` ~L1042)

- [ ] **Step 1: Write the failing tests**

Add these tests (place them adjacent to the existing `test_inline_range_anchor`):

```python
def test_inline_endash_range_in_range_no_drift(self, tmp_path):
    """En-dash range whose symbol def falls inside [A,B] is OK."""
    _init_repo(tmp_path)
    # def at line 15, inside cited range 10-20
    src = _write_py(tmp_path, "mod.py", "\n" * 14 + "def widget():\n    pass\n")
    md = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10–20` helper\n")
    drifts = check_line_anchors([str(md)], tmp_path)
    assert drifts == []

def test_inline_endash_range_out_of_range_is_drift(self, tmp_path):
    """En-dash range whose symbol def is OUTSIDE [A,B] is a def_drift (was invisible)."""
    _init_repo(tmp_path)
    # def at line 30, OUTSIDE cited range 10-20
    src = _write_py(tmp_path, "mod.py", "\n" * 29 + "def widget():\n    pass\n")
    md = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10–20` helper\n")
    drifts = check_line_anchors([str(md)], tmp_path)
    assert len(drifts) == 1
    assert drifts[0].kind == "def_drift"
    assert drifts[0].target_line == 10
    assert drifts[0].suggested_line == 30

def test_inline_emdash_range_matches(self, tmp_path):
    """Em-dash separator is also recognized (defensive; 0 exist today)."""
    _init_repo(tmp_path)
    src = _write_py(tmp_path, "mod.py", "\n" * 29 + "def widget():\n    pass\n")
    md = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10—20` helper\n")
    drifts = check_line_anchors([str(md)], tmp_path)
    assert len(drifts) == 1
    assert drifts[0].kind == "def_drift"

def test_inline_ascii_hyphen_range_still_works(self, tmp_path):
    """Regression: ASCII-hyphen ranges behave exactly as before."""
    _init_repo(tmp_path)
    src = _write_py(tmp_path, "mod.py", "\n" * 14 + "def widget():\n    pass\n")
    md = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10-20` helper\n")
    drifts = check_line_anchors([str(md)], tmp_path)
    assert drifts == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -k "endash or emdash" -v`
Expected: the two en-dash + one em-dash tests FAIL (en-dash anchors don't match the current regex → no drift detected → `len(drifts) == 1` assertion fails / `drifts == []` passes spuriously for the in-range one). The ASCII regression test PASSES. (If the in-range en-dash test passes for the wrong reason — because the anchor is invisible — that's expected pre-fix; the out-of-range test is the decisive RED.)

- [ ] **Step 3: Widen the regex**

In `scripts/check_doc_claims.py`, find `_INLINE_ANCHOR_RE` (~L66-70). Change ONLY the range-separator character in the optional end-group:

```python
# BEFORE:
#   r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:-(?P<end>\d+))?`'
# AFTER (accept hyphen, en-dash U+2013, em-dash U+2014):
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:[-–—](?P<end>\d+))?`'
```

(Use the literal `–`/`—` characters or the `–`/`—` escapes — match the file's existing convention for non-ASCII in regexes; the escapes are safer for grep-ability. Keep the surrounding comment block accurate — update it to note the three accepted separators.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -k "endash or emdash or ascii_hyphen_range" -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(verifier): recognize en/em-dash range anchors in _INLINE_ANCHOR_RE" \
  -m "Range separator was ASCII-hyphen-only -> en-dash range anchors (256 in digests + 2 in manual) were INVISIBLE to the verifier. Widen to [-en-em]. Closes the Slice-3 detection gap. TDD: out-of-range en-dash def_drift reproduced RED -> GREEN." \
  -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 2: En/em-dash `--fix` canonicalization (+ defensive `_shift_display`)

**Files:**
- Modify: `scripts/check_doc_claims.py` (`_shift_display`, ~L432 — the `re.finditer(r':(\d+)-(\d+)', display)` line)
- Test: `tests/unit/test_check_doc_claims.py` (near the inline `--fix` tests ~L1086)

**Note (plan-vs-spec refinement):** the inline `--fix` path **already** canonicalizes after Task 1 — `_rewrite_anchor_occurrence` rebuilds the body as `f"{file}:{old}-{end}"` (ASCII) before calling `_shift_display`, so an en-dash anchor `--fix`'d becomes ASCII hyphen automatically. The `_shift_display` widening here is **defensive**: it closes a latent bug on the markdown-LINK range path (`_shift_display(m.group("display"), …)` at ~L466), where an en-dash display would otherwise fail the `:(\d+)-(\d+)` match and leave the end-number unshifted. 0 such link-ranges exist today; this is consistency + latent-bug-close, not a live fix.

- [ ] **Step 1: Write the failing/passing tests**

```python
def test_fix_canonicalizes_endash_range_and_shifts(self, tmp_path):
    """--fix on a drifted en-dash range rewrites to ASCII hyphen AND shifts both ends."""
    _init_repo(tmp_path)
    # def at 30; cited range 10-20 (en-dash) -> should become 30-40 (ASCII), span 10 preserved
    src = _write_py(tmp_path, "mod.py", "\n" * 29 + "def widget():\n    pass\n")
    md_path = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10–20` x\n")
    remaining = run([str(md_path)], tmp_path, fix=True)
    text = md_path.read_text()
    assert "`mod.py:30-40`" in text       # ASCII hyphen, both ends shifted by +20
    assert "–" not in text            # en-dash canonicalized away
    assert remaining == []

def test_fix_endash_range_is_idempotent(self, tmp_path):
    """Running --fix twice on the en-dash case yields a stable file."""
    _init_repo(tmp_path)
    src = _write_py(tmp_path, "mod.py", "\n" * 29 + "def widget():\n    pass\n")
    md_path = _write_md(tmp_path, "doc.md", "the **`widget`** `mod.py:10–20` x\n")
    run([str(md_path)], tmp_path, fix=True)
    first = md_path.read_text()
    run([str(md_path)], tmp_path, fix=True)
    assert md_path.read_text() == first

def test_fix_endash_span_guard_round_trips(self, tmp_path):
    """ADV-1 span guard: the en-dash occurrence is rewritten at its own span, not corrupted."""
    _init_repo(tmp_path)
    src = _write_py(tmp_path, "mod.py", "\n" * 29 + "def widget():\n    pass\n")
    # two anchors on one line: a drifted en-dash range + an unrelated correct one
    _write_py(tmp_path, "two.py", "def other():\n    pass\n")  # def at 1
    md_path = _write_md(
        tmp_path, "doc.md",
        "**`widget`** `mod.py:10–20` and **`other`** `two.py:1`\n",
    )
    run([str(md_path)], tmp_path, fix=True)
    text = md_path.read_text()
    assert "`mod.py:30-40`" in text
    assert "`two.py:1`" in text            # untouched, not clobbered
```

- [ ] **Step 2: Run to verify state**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -k "canonicalizes_endash or endash_range_is_idempotent or endash_span_guard" -v`
Expected: these likely PASS already after Task 1 (inline auto-canonicalization). If all pass, the `_shift_display` change in Step 3 is purely defensive — proceed and add the link-path test in Step 3a. If the canonicalize test FAILS, Task 1's `_rewrite_anchor_occurrence` path needs the widening — note which and proceed.

- [ ] **Step 3: Widen `_shift_display` (defensive)**

In `scripts/check_doc_claims.py`, find `_shift_display` (~L432):

```python
# BEFORE:  for rm in re.finditer(r':(\d+)-(\d+)', display):
# AFTER:
    for rm in re.finditer(r':(\d+)[-–—](\d+)', display):
```

(The function already emits ASCII `f":{new}-{end}"` — no emit change. Update the docstring to note it accepts en/em-dash on read, emits ASCII.)

- [ ] **Step 3a: Add the defensive link-path test**

```python
def test_shift_display_accepts_endash_link_range(self, tmp_path):
    """Defensive: a markdown-LINK display carrying an en-dash range is shifted + canonicalized."""
    from check_doc_claims import _shift_display
    assert _shift_display("core.py:10–20", 10, 30) == "core.py:30-40"
    assert _shift_display(":138–140", 138, 200) == ":200-202"
```

- [ ] **Step 4: Run to verify pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -k "endash or shift_display" -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(verifier): canonicalize en/em-dash ranges to ASCII hyphen on --fix" \
  -m "Inline --fix already canonicalizes via _rewrite_anchor_occurrence's ASCII rebuild; widen _shift_display defensively for the markdown-link range path (latent bug: en-dash display end-number left unshifted). Per spec Q1: tolerant accept + canonicalize on touch." \
  -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 3: Multi-range warn-don't-verify guard

**Files:**
- Modify: `scripts/check_doc_claims.py` (add `_MULTIRANGE_RE` near `_INLINE_ANCHOR_RE`; add per-doc count + warning in `check_line_anchors`, just before the `if in_fence:` EOF warning ~L408)
- Test: `tests/unit/test_check_doc_claims.py` (near `TestUnclosedFenceWarning` ~L1301)

- [ ] **Step 1: Write the failing tests**

```python
class TestMultiRangeWarning:
    def test_multi_range_anchor_warns_not_silently_skipped(self, tmp_path, capsys):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "mod.py", "def f():\n    pass\n")
        md = _write_md(tmp_path, "doc.md", "see `mod.py:1–5, 9–12` for details\n")
        check_line_anchors([str(md)], tmp_path)
        err = capsys.readouterr().err
        assert "doc.md" in err
        assert "multi-range" in err.lower()
        assert "not verified" in err.lower()

    def test_multi_range_does_not_block_normal_anchor_same_line(self, tmp_path, capsys):
        _init_repo(tmp_path)
        # def at line 3; a normal anchor + a multi-range anchor on the same line
        _commit_py(tmp_path, "mod.py", "# a\n# b\ndef f():\n    pass\n")
        md = _write_md(
            tmp_path, "doc.md",
            "**`f`** `mod.py:3` plus the batch `mod.py:1–5, 9–12`\n",
        )
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == []                       # the normal anchor verified OK
        assert "multi-range" in capsys.readouterr().err.lower()

    def test_single_range_does_not_trigger_multi_range_warning(self, tmp_path, capsys):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "mod.py", "def f():\n    pass\n")  # def at 1
        md = _write_md(tmp_path, "doc.md", "**`f`** `mod.py:1–5` covers cases 9, 12\n")
        check_line_anchors([str(md)], tmp_path)
        assert "multi-range" not in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py::TestMultiRangeWarning -v`
Expected: the two "warns" tests FAIL (no warning emitted). The "single_range does not trigger" + "does not block normal anchor" drift-assert may pass; the stderr assert on the warning fails.

- [ ] **Step 3: Add `_MULTIRANGE_RE` + the warning**

Near `_INLINE_ANCHOR_RE` add:

```python
# A backtick anchor whose first range is followed by a comma-list of further
# ranges — e.g. `mod.py:1-5, 9-12`. The comma precedes the closing backtick, so
# _INLINE_ANCHOR_RE cannot parse it; such anchors are NOT verified. Detect + warn
# (never silently skip — the ADV-2 principle). [^`]* stays within one backtick pair.
_MULTIRANGE_RE = re.compile(
    r'`[A-Za-z0-9_./-]+\.[A-Za-z]+:\d+[-–—]\d+\s*,\s*\d+[-–—]?\d*[^`]*`'
)
# (matches the spec verbatim; the trailing [-–—]?\d* captures a second *range*
#  bound, not just a bare line — functionally same warning count, but precise.)
```

In `check_line_anchors`, inside the `for doc_path in doc_paths:` loop: initialize `multirange = 0` alongside `in_fence = False` (~L342); inside the line loop, after the `if in_fence: continue` guard, add `multirange += len(_MULTIRANGE_RE.findall(line_text))`; then immediately before the existing `if in_fence:` EOF warning (~L408), add:

```python
        if multirange:
            print(f"WARNING: {full_path}: {multirange} multi-range anchor(s) "
                  f"(e.g. `file.py:A-B, C-D`) were NOT verified — the comma-list "
                  f"form is unparseable. Split into single-range anchors to verify.",
                  file=sys.stderr)
```

(Mirror the indentation/placement of the `if in_fence:` warning — both are per-doc, inside the doc loop, after the line loop.)

- [ ] **Step 4: Run to verify pass + full file green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -v`
Expected: all PASS (the prior 81 + the new tests).

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git add scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
git commit -m "feat(verifier): warn (don't silently skip) on multi-range comma-list anchors" \
  -m "`file:A-B, C-D` anchors are unparseable by _INLINE_ANCHOR_RE; emit a per-doc stderr WARNING (ADV-2 'never silently skip') instead of dropping them. Per spec Q2." \
  -- scripts/check_doc_claims.py tests/unit/test_check_doc_claims.py
```

---

### Task 4: Sweep the now-visible drift + correct the Slice-2 false-clean

**Files:**
- Modify: `docs/PROGRAM-MANUAL.md`, `docs/PROGRAM-MANUAL-digests.md` (anchor corrections)

**Note:** the spec's "~43 drifts" is an estimate from a 2026-06-09 simulation taken BEFORE the director's pre-T10 commits (`46e3b87…cde6dec`) shifted `phase_c_ffmpeg.py`. Re-run against current HEAD to get the real list — do NOT trust the estimate.

- [ ] **Step 1: Capture the real drift list**

Run: `.venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md 2>&1 | tee /tmp/slice3-drift-before.txt`
Record: the count by kind (def_drift / ambiguous_path / out_of_bounds) and the multi-range warning count. This is the Rule #1 evidence for the commit body.

- [ ] **Step 2: Auto-fix the fixable def_drifts**

Run: `.venv/bin/python scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md 2>&1 | tee /tmp/slice3-fix.txt`
Expected: the single-def `def_drift`s are corrected + canonicalized to ASCII hyphen; ambiguous/out-of-bounds remain. Eyeball the `FIXED` lines.

- [ ] **Step 3: Manually resolve the remaining drifts (Slice-2b rules)**

For each remaining `ambiguous_path` (bare filename matching ≥2 tracked paths): directory-qualify per the Slice-2b convention (`controller.py` >L700 → `cinema/shots/`; root re-export shims → `domain/X.py`; etc. — Read the cited prose to pick the right path). For each `out_of_bounds`: Read the source + prose, correct by hand. For the multi-range warnings: split into single-range anchors where the symbol is clear, else leave warned (and note the count left).

- [ ] **Step 4: Re-run to a clean exit (acceptance)**

Run: `.venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md; echo "EXIT=$?"`
Expected: `EXIT=0` (no fatal drift; multi-range WARNINGs are advisory, not fatal — confirm against `_split_advisories` semantics if exit is nonzero).

- [ ] **Step 5: Verify nothing else broke**

Run: `.venv/bin/python scripts/ci_smoke.py && echo SMOKE_OK` and `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -q`
Expected: `SMOKE_OK`; verifier suite green.

- [ ] **Step 6: Commit the sweep + correct the false-clean**

```bash
git read-tree HEAD
git add docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
git commit -m "docs(manual): Slice 3 sweep — fix <N> now-visible en-dash range anchors; correct Slice-2 false-clean" \
  -m "<paste real counts from Step 1>. These anchors were INVISIBLE to the verifier (en-dash range separator) until the Slice-3 fix; Slice 2's 'no drift' covered only regex-visible anchors (Rule #18 verifier-clean != true). <ascii from --fix; manual quals for ambiguous; N multi-range left warned>. Verifier now exits clean on both docs; ci_smoke OK." \
  -- docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md
```

---

## Acceptance criteria (whole slice)

- All new tests green; full `tests/unit/test_check_doc_claims.py` green (was 81 passed → 81 + new).
- `check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` exits clean (0 fatal drift); multi-range WARNING shows the expected residual count.
- `scripts/ci_smoke.py` OK; full unit suite still green (baseline 1895/0 — run `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q`).
- The sweep commit body captures the real `--fix` output (Rule #1) and states the false-clean correction.
- **Zero Phase-3 entanglement:** only `scripts/check_doc_claims.py` + its test file + the two manual docs are touched.

## Post-implementation

- This is operator-owned (Finding-1 lane). Per Rule #9, the per-feat Lane V (independent second opinion) is released to director-seat when the feat commits land.
- After the slice: `superpowers:finishing-a-development-branch` (the verifier changes are on the shared `feat/max-tier-provisioning` line; push/merge is strategic-seat/user-gated).

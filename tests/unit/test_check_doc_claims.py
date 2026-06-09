"""TDD tests for scripts/check_doc_claims.py — line-anchor verifier.

Run: .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -q

All 10 required cases are each in their own test function.  Fixtures use
real tmp_path files (no mocking).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.  The scripts/ dir is NOT on sys.path by
# default when pytest runs from the repo root, so we add it explicitly.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_doc_claims import (  # noqa: E402
    Drift,
    check_line_anchors,
    check_anchor,
    run,
    CHECKERS,
    audit_manifest,
    check_manifest,
    check_sha_refs,
    audit_sha_refs,
    _INLINE_ANCHOR_RE,
    _build_basename_index,
    _resolve_inline_target,
    _split_advisories,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


def _write_md(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Git-repo fixture helpers (SHA-ref checker tests) — real repos, no mocking.
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def _init_repo(tmp_path: Path) -> Path:
    """git init a repo at tmp_path with deterministic identity + no signing."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _commit(repo: Path, message: str, *, fname: str = "f.txt") -> str:
    """Commit a change with *message*; return the 7-char short SHA."""
    (repo / fname).write_text(message)
    _git(repo, "add", fname)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "--short=7", "HEAD").stdout.strip()


def _commit_py(repo: Path, relpath: str, content: str) -> Path:
    """Write a .py at relpath (creating dirs), git add + commit it so it appears
    in `git ls-files`. Returns the absolute path."""
    p = repo / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    _git(repo, "add", relpath)
    _git(repo, "commit", "-q", "-m", f"add {relpath}")
    return p


# ---------------------------------------------------------------------------
# Test 1: Known-good anchor — cited line IS the def → no drift
# ---------------------------------------------------------------------------

class TestKnownGoodAnchor:
    def test_correct_def_line_no_drift(self, tmp_path):
        """Anchor pointing at the exact def line → None (clean)."""
        src = _write_py(tmp_path, "mod.py", """\
            # line 1
            # line 2
            def my_func():
                pass
        """)
        # def is at line 3
        md = _write_md(tmp_path, "doc.md", """\
            See `my_func` ([mod.py:3](mod.py:3)) for details.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == [], f"Expected no drift but got: {drifts}"


# ---------------------------------------------------------------------------
# Test 2: Stale def anchor — def moved below cited line → def_drift, fixable
# ---------------------------------------------------------------------------

class TestStaleDefAnchor:
    def test_def_moved_below_cited_line(self, tmp_path):
        """Anchor says line 2 but def is at line 5 → def_drift, fixable=True, suggested=5."""
        src = _write_py(tmp_path, "mod.py", """\
            # line 1
            # line 2 (was the def, now just a comment)
            # line 3
            # line 4
            def my_func():
                pass
        """)
        md = _write_md(tmp_path, "doc.md", """\
            See `my_func` ([mod.py:2](mod.py:2)) — stale anchor.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "def_drift"
        assert d.fixable is True
        assert d.suggested_line == 5
        assert d.symbol == "my_func"
        assert d.target_line == 2


# ---------------------------------------------------------------------------
# Test 3: Prose mention MUST NOT false-pass — THE key test
# ---------------------------------------------------------------------------

class TestProseMentionNoFalsePass:
    def test_string_mention_not_def_is_drift(self, tmp_path):
        """
        Line 341 contains the symbol as a docstring string, not a def.
        Real def is at line 429. Anchor citing line 341 MUST be drift.

        This mirrors the real-world shape: a line in the middle of a
        docstring contains '...duplicated verbatim in `decompose_scene` and...'
        while the actual def decompose_scene is further down.
        """
        # Build a source file: early line has symbol in a string/comment,
        # actual def is further down.
        lines = ["# line {}\n".format(i) for i in range(1, 430)]
        # line 341 (0-indexed: 340): embed symbol name in a comment
        lines[340] = "    # duplicated verbatim in decompose_scene and foo\n"
        # line 429 (0-indexed: 428): the actual def
        lines[428] = "def decompose_scene(\n"
        src = tmp_path / "scene_decomposer.py"
        src.write_text("".join(lines))

        # Anchor on doc line pointing at line 341 (the prose mention)
        md = _write_md(tmp_path, "doc.md", """\
            | `decompose_scene` ([scene_decomposer.py:341](scene_decomposer.py:341)) | desc |
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1, (
            f"Expected 1 drift (prose-mention should be flagged), got: {drifts}"
        )
        d = drifts[0]
        assert d.kind == "def_drift"
        assert d.symbol == "decompose_scene"
        assert d.suggested_line == 429
        assert d.fixable is True


# ---------------------------------------------------------------------------
# Test 4: Deleted / missing file anchor → missing_file, fixable=False
# ---------------------------------------------------------------------------

class TestMissingFileAnchor:
    def test_missing_file_returns_drift(self, tmp_path):
        """Anchor targeting a non-existent file → kind=missing_file, fixable=False."""
        md = _write_md(tmp_path, "doc.md", """\
            See [nonexistent.py:10](nonexistent.py:10) for foo.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "missing_file"
        assert d.fixable is False
        assert d.suggested_line is None


# ---------------------------------------------------------------------------
# Test 5: Duplicate def → drift but fixable=False, suggested_line=None
# ---------------------------------------------------------------------------

class TestDuplicateDef:
    def test_ambiguous_def_not_fixable(self, tmp_path):
        """Two defs of the same symbol → def_drift with fixable=False."""
        src = _write_py(tmp_path, "mod.py", """\
            def my_func():
                pass

            # some other code

            def my_func():  # redefined
                pass
        """)
        # def is at lines 1 and 6; anchor says line 3 (neither)
        md = _write_md(tmp_path, "doc.md", """\
            See `my_func` ([mod.py:3](mod.py:3)) — ambiguous.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "def_drift"
        assert d.fixable is False
        assert d.suggested_line is None


# ---------------------------------------------------------------------------
# Test 6: No-symbol prose anchor with in-bounds line → no drift (bounds-only OK)
# ---------------------------------------------------------------------------

class TestNoSymbolInBounds:
    def test_prose_anchor_inbounds_no_drift(self, tmp_path):
        """Anchor with no backtick symbol, in-bounds line → clean."""
        src = _write_py(tmp_path, "mod.py", """\
            # line 1
            # Atomic write logic here
            x = 1
        """)
        md = _write_md(tmp_path, "doc.md", """\
            Atomic write ([mod.py:2](mod.py:2)) handles concurrency.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == [], f"Expected no drift but got: {drifts}"


# ---------------------------------------------------------------------------
# Test 7: Out-of-bounds anchor (line > file length, no bindable symbol)
# ---------------------------------------------------------------------------

class TestOutOfBounds:
    def test_line_beyond_eof_is_drift(self, tmp_path):
        """Anchor line > number of lines in target file → out_of_bounds."""
        src = _write_py(tmp_path, "mod.py", """\
            # only 3 lines
            x = 1
            y = 2
        """)
        md = _write_md(tmp_path, "doc.md", """\
            Dict API methods at [mod.py:999](mod.py:999).
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "out_of_bounds"
        assert d.fixable is False


# ---------------------------------------------------------------------------
# Test 8: Module-level constant anchor — binds via assignment rule
# ---------------------------------------------------------------------------

class TestModuleLevelConstant:
    def test_correct_constant_line_no_drift(self, tmp_path):
        """Module-level BILLING_PROVIDERS = { at line 5 → anchor at 5 → clean."""
        lines = [
            "# line 1\n",
            "# line 2\n",
            "# line 3\n",
            "# line 4\n",
            "BILLING_PROVIDERS = {\n",
            "    'foo': 1,\n",
            "}\n",
        ]
        src = tmp_path / "providers.py"
        src.write_text("".join(lines))

        md = _write_md(tmp_path, "doc.md", """\
            See `BILLING_PROVIDERS` ([providers.py:5](providers.py:5)) for the map.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == [], f"Expected no drift but got: {drifts}"

    def test_wrong_constant_line_is_drift(self, tmp_path):
        """Module-level constant at line 5; anchor at line 2 → def_drift fixable."""
        lines = [
            "# line 1\n",
            "# line 2\n",
            "# line 3\n",
            "# line 4\n",
            "BILLING_PROVIDERS = {\n",
            "    'foo': 1,\n",
            "}\n",
        ]
        src = tmp_path / "providers.py"
        src.write_text("".join(lines))

        md = _write_md(tmp_path, "doc.md", """\
            See `BILLING_PROVIDERS` ([providers.py:2](providers.py:2)) for the map.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "def_drift"
        assert d.fixable is True
        assert d.suggested_line == 5


# ---------------------------------------------------------------------------
# Test 9: --fix rewrites a fixable def_drift in both link + display
# ---------------------------------------------------------------------------

class TestFixMode:
    def test_fix_rewrites_link_and_display(self, tmp_path):
        """--fix should rewrite the stale line number in both link and display text.

        File layout (explicit, no textwrap.dedent ambiguity):
          line 1: # comment
          line 2: # comment
          ...
          line 10: def my_func():
          line 11:     pass

        Anchor link says line 3 (stale); display range says mod.py:3-7 (also stale).
        Both should be rewritten to reference line 10.
        """
        # Build file with explicit known line numbers — def at line 10
        lines = ["# line {}\n".format(i) for i in range(1, 10)]
        lines.append("def my_func():\n")   # line 10
        lines.append("    pass\n")          # line 11
        src = tmp_path / "mod.py"
        src.write_text("".join(lines))

        # Anchor: link → line 3 (stale), display range → mod.py:3-7 (stale)
        md_content = "See `my_func` ([mod.py:3-7](mod.py:3)) — stale.\n"
        md_path = tmp_path / "doc.md"
        md_path.write_text(md_content)

        remaining = run([str(md_path)], tmp_path, fix=True)
        assert remaining == [], f"Expected all fixed but got: {remaining}"

        # Verify file was actually rewritten
        fixed_content = md_path.read_text()
        # Link target should now reference line 10
        assert "mod.py:10)" in fixed_content, f"Link target not fixed: {fixed_content!r}"
        # Display range should now have 10 as start, keeping original span (3-7 → span=4 → 10-14)
        assert "mod.py:10-" in fixed_content, f"Display range start not fixed: {fixed_content!r}"
        # Old link target should be gone
        assert "mod.py:3)" not in fixed_content, f"Old link still present: {fixed_content!r}"

    def test_fix_leaves_missing_file_untouched(self, tmp_path):
        """--fix must NOT touch missing_file drift."""
        md_content = "See [ghost.py:10](ghost.py:10) for foo.\n"
        md_path = tmp_path / "doc.md"
        md_path.write_text(md_content)

        remaining = run([str(md_path)], tmp_path, fix=True)
        # missing_file drift should remain
        assert len(remaining) == 1
        assert remaining[0].kind == "missing_file"
        # File content should be unchanged
        assert md_path.read_text() == md_content

    def test_fix_leaves_ambiguous_def_untouched(self, tmp_path):
        """--fix must NOT touch ambiguous (duplicate def) drift."""
        src = _write_py(tmp_path, "mod.py", """\
            def dup():
                pass
            def dup():
                pass
        """)
        md_content = "See `dup` ([mod.py:2](mod.py:2)) — ambiguous.\n"
        md_path = tmp_path / "doc.md"
        md_path.write_text(md_content)

        remaining = run([str(md_path)], tmp_path, fix=True)
        assert len(remaining) == 1
        assert remaining[0].kind == "def_drift"
        assert remaining[0].fixable is False
        # File content unchanged
        assert md_path.read_text() == md_content


# ---------------------------------------------------------------------------
# Test 10: Dotted/attribute token → not bound as symbol → bounds-only
# ---------------------------------------------------------------------------

class TestDottedToken:
    def test_dotted_token_is_not_symbol_bound(self, tmp_path):
        """q.get(timeout=30) has a dotted token → no def binding → bounds-only."""
        # File has 20 lines; line 10 is in bounds
        lines = ["# line {}\n".format(i) for i in range(1, 21)]
        src = tmp_path / "web.py"
        src.write_text("".join(lines))

        # Anchor with dotted token — should be bounds-only (no def binding)
        md = _write_md(tmp_path, "doc.md", """\
            The loop at [web.py:10](web.py:10) does `q.get(timeout=30)`.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == [], (
            f"Dotted token should not trigger def_drift but got: {drifts}"
        )

    def test_cls_method_dotted_token_bounds_only(self, tmp_path):
        """Cls.method dotted token → not bound → bounds-only."""
        lines = ["# line {}\n".format(i) for i in range(1, 21)]
        src = tmp_path / "web.py"
        src.write_text("".join(lines))

        md = _write_md(tmp_path, "doc.md", """\
            `CinemaPipeline.__init__` composes everything ([web.py:5](web.py:5)).
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == [], (
            f"Cls.method token should not trigger def_drift but got: {drifts}"
        )

    def test_simple_ident_token_still_binds(self, tmp_path):
        """A simple non-dotted token still binds to def (sanity check)."""
        src = _write_py(tmp_path, "mod.py", """\
            # line 1
            def my_func():
                pass
        """)
        # def is at line 2; anchor says line 1 → should flag drift
        md = _write_md(tmp_path, "doc.md", """\
            See `my_func` ([mod.py:1](mod.py:1)) — should bind.
        """)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        assert drifts[0].kind == "def_drift"


# ---------------------------------------------------------------------------
# Structural / API tests
# ---------------------------------------------------------------------------

class TestFixModeRangePrecision:
    """--fix must shift BOTH ends of a display range (preserve span) and handle
    filename-less + single-number display forms. Regression tests for the
    real-doc bugs: backwards ranges (411-133), ballooned ranges (446-874),
    filename-less displays (:138-140), and single-number display/href mismatch.
    """

    @staticmethod
    def _src_def_at_10(tmp_path):
        lines = ["# line {}\n".format(i) for i in range(1, 10)]
        lines.append("def my_func():\n")   # line 10
        lines.append("    pass\n")          # line 11
        src = tmp_path / "mod.py"
        src.write_text("".join(lines))
        return src

    def test_ranged_display_span_preserved(self, tmp_path):
        """display 'mod.py:3-7' (span 4), def at 10 → 'mod.py:10-14' (start AND end shift)."""
        self._src_def_at_10(tmp_path)
        md_path = tmp_path / "doc.md"
        md_path.write_text("See `my_func` ([mod.py:3-7](mod.py:3)) — stale.\n")

        remaining = run([str(md_path)], tmp_path, fix=True)
        assert remaining == []
        content = md_path.read_text()
        assert "[mod.py:10-14](mod.py:10)" in content, f"got: {content!r}"
        assert ":3" not in content, f"stale :3 left behind: {content!r}"

    def test_filenameless_range_display_fixed(self, tmp_path):
        """display ':3-7' (no filename prefix) must still shift → ':10-14'."""
        self._src_def_at_10(tmp_path)
        md_path = tmp_path / "doc.md"
        md_path.write_text("See `my_func` ([:3-7](mod.py:3)) — stale.\n")

        remaining = run([str(md_path)], tmp_path, fix=True)
        assert remaining == []
        content = md_path.read_text()
        assert "[:10-14](mod.py:10)" in content, f"got: {content!r}"

    def test_single_number_display_both_updated(self, tmp_path):
        """display 'mod.py:3' (no range) → both display and href become :10 (no mismatch)."""
        self._src_def_at_10(tmp_path)
        md_path = tmp_path / "doc.md"
        md_path.write_text("See `my_func` ([mod.py:3](mod.py:3)) — stale.\n")

        remaining = run([str(md_path)], tmp_path, fix=True)
        assert remaining == []
        content = md_path.read_text()
        assert "[mod.py:10](mod.py:10)" in content, f"got: {content!r}"
        assert "mod.py:3" not in content, f"stale :3 left behind: {content!r}"


class TestPublicAPI:
    def test_checkers_list_contains_check_line_anchors(self):
        assert check_line_anchors in CHECKERS

    def test_drift_is_dataclass(self):
        d = Drift(
            doc_path="x.md", doc_line=1, target_file="y.py",
            target_line=5, kind="def_drift", symbol="foo",
            suggested_line=10, fixable=True, message="test",
        )
        assert d.kind == "def_drift"
        assert d.fixable is True

    def test_run_with_no_docs_returns_empty(self, tmp_path):
        result = run([], tmp_path)
        assert result == []

    def test_run_calls_all_checkers(self, tmp_path):
        """run() must invoke all CHECKERS (currently just check_line_anchors)."""
        # A doc with no anchors → clean
        md = _write_md(tmp_path, "clean.md", "# heading\nNo anchors here.\n")
        result = run([str(md)], tmp_path)
        assert result == []


# ===========================================================================
# Part A — audit_manifest / check_manifest tests
# ===========================================================================

def _write_toml(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


class TestAuditManifestValidAnchor:
    """audit_manifest — valid anchor resolves to valid=True with correct current_line."""

    def test_valid_anchor_returns_valid_true_and_line(self, tmp_path):
        """A component whose symbol exists → valid=True, current_line=correct."""
        src = tmp_path / "mod.py"
        src.write_text("# line 1\n# line 2\ndef xfade_concat():\n    pass\n")
        # def is at line 3
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "scene_transitions"
            title = "Cross-dissolve"
            status = "wired"
            anchor = "mod.py:xfade_concat"
            note = "test"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "scene_transitions"
        assert r["valid"] is True
        assert r["current_line"] == 3
        assert r["problem"] is None


class TestAuditManifestSymbolNotFound:
    """audit_manifest — symbol missing → valid=False, kind=manifest_symbol_not_found."""

    def test_missing_symbol_returns_invalid(self, tmp_path):
        """File exists but symbol is absent → valid=False."""
        src = tmp_path / "mod.py"
        src.write_text("# no defs here\n")
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "storyboard_mode"
            title = "Storyboard"
            status = "stubbed"
            anchor = "mod.py:generate_storyboard"
            note = "test"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is False
        assert r["current_line"] is None
        assert "generate_storyboard" in r["problem"]

    def test_check_manifest_emits_drift_with_correct_kind(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("# no defs here\n")
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "storyboard_mode"
            title = "Storyboard"
            status = "stubbed"
            anchor = "mod.py:generate_storyboard"
            note = "test"
        """)
        drifts = check_manifest(toml, tmp_path)
        assert len(drifts) == 1
        d = drifts[0]
        assert d.kind == "manifest_symbol_not_found"
        assert d.fixable is False
        assert "storyboard_mode" in d.message


class TestAuditManifestMissingFile:
    """audit_manifest — target file doesn't exist → valid=False, kind=manifest_missing_file."""

    def test_missing_file_returns_invalid(self, tmp_path):
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "batch_scene"
            title = "Batch"
            status = "stubbed"
            anchor = "nonexistent.py:batch_optimize_scene"
            note = "test"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is False
        assert r["current_line"] is None
        assert "nonexistent.py" in r["problem"]

    def test_check_manifest_emits_missing_file_kind(self, tmp_path):
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "batch_scene"
            title = "Batch"
            status = "stubbed"
            anchor = "nonexistent.py:batch_optimize_scene"
            note = "test"
        """)
        drifts = check_manifest(toml, tmp_path)
        assert len(drifts) == 1
        assert drifts[0].kind == "manifest_missing_file"


class TestAuditManifestPathWithSlash:
    """audit_manifest — anchor file path contains '/' — rsplit correctness."""

    def test_subdirectory_path_resolves(self, tmp_path):
        """anchor = 'prep/lora_training.py:validate_lora_quality' — path with '/'."""
        subdir = tmp_path / "prep"
        subdir.mkdir()
        (subdir / "lora_training.py").write_text(
            "# line 1\ndef validate_lora_quality():\n    pass\n"
        )
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "lora_validation"
            title = "LoRA validation"
            status = "stubbed"
            anchor = "prep/lora_training.py:validate_lora_quality"
            note = "test"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is True
        assert r["current_line"] == 2


class TestAuditManifestMixed:
    """audit_manifest — mixed valid/invalid — check_manifest returns only invalid."""

    def test_mixed_components_check_manifest_only_invalid(self, tmp_path):
        """Two components: one valid, one with missing symbol. check_manifest → 1 drift."""
        src = tmp_path / "mod.py"
        src.write_text("def good_func():\n    pass\n")
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "good"
            title = "Good one"
            status = "live"
            anchor = "mod.py:good_func"
            note = "ok"

            [[component]]
            id = "bad"
            title = "Bad one"
            status = "stubbed"
            anchor = "mod.py:missing_func"
            note = "broken"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 2
        valid_ones = [r for r in results if r["valid"]]
        invalid_ones = [r for r in results if not r["valid"]]
        assert len(valid_ones) == 1
        assert len(invalid_ones) == 1

        drifts = check_manifest(toml, tmp_path)
        assert len(drifts) == 1
        assert drifts[0].symbol == "missing_func"


class TestAuditManifestAbsent:
    """audit_manifest — manifest file doesn't exist → returns []."""

    def test_absent_manifest_returns_empty_list(self, tmp_path):
        no_such_file = tmp_path / "does_not_exist.toml"
        results = audit_manifest(no_such_file, tmp_path)
        assert results == []

    def test_check_manifest_absent_returns_empty(self, tmp_path):
        no_such_file = tmp_path / "does_not_exist.toml"
        drifts = check_manifest(no_such_file, tmp_path)
        assert drifts == []


class TestAuditManifestMalformed:
    """audit_manifest — malformed entry (missing anchor/id) → valid=False, no raise."""

    def test_missing_anchor_field_no_raise(self, tmp_path):
        """Component with no 'anchor' key → valid=False, problem mentions 'malformed'."""
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "no_anchor"
            title = "Missing anchor"
            status = "stubbed"
            note = "oops"
        """)
        # Must not raise
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is False
        assert "malformed" in r["problem"]

    def test_missing_id_field_no_raise(self, tmp_path):
        """Component with no 'id' key → valid=False, no raise."""
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            title = "No ID"
            status = "stubbed"
            anchor = "mod.py:something"
            note = "oops"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is False
        assert "malformed" in r["problem"]


class TestAuditManifestModuleConst:
    """audit_manifest — module-level constant resolves via _def_lines assignment rule."""

    def test_module_const_anchor_resolves(self, tmp_path):
        """anchor = 'mod.py:SOME_CONST' where SOME_CONST = { at line 3 → valid, line 3."""
        src = tmp_path / "mod.py"
        src.write_text("# line 1\n# line 2\nSOME_CONST = {\n    'a': 1,\n}\n")
        toml = _write_toml(tmp_path, "manifest.toml", """\
            [[component]]
            id = "const_test"
            title = "Constant test"
            status = "live"
            anchor = "mod.py:SOME_CONST"
            note = "test"
        """)
        results = audit_manifest(toml, tmp_path)
        assert len(results) == 1
        r = results[0]
        assert r["valid"] is True
        assert r["current_line"] == 3


# ===========================================================================
# SHA-ref checker (Tier 2: resolve + reachable + quoted-subject match)
# ===========================================================================

class TestShaRefResolves:
    def test_resolving_sha_no_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        sha = _commit(repo, "feat: initial commit")
        md = _write_md(tmp_path, "doc.md", f"""\
            See commit `{sha}` for details.
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert drifts == []


class TestShaRefNotFound:
    def test_fabricated_sha_is_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "feat: initial commit")
        md = _write_md(tmp_path, "doc.md", """\
            Cited `deadbee` which does not exist.
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert len(drifts) == 1
        assert drifts[0].kind == "sha_not_found"
        assert drifts[0].symbol == "deadbee"


class TestShaRefUnreachable:
    def test_dangling_sha_is_unreachable_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "first")
        dangling = _commit(repo, "second")
        # Move HEAD back; `dangling` stays in the object db but off HEAD's history.
        _git(repo, "reset", "--hard", "HEAD~1")
        md = _write_md(tmp_path, "doc.md", f"""\
            Cited `{dangling}` no longer reachable from HEAD.
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert len(drifts) == 1
        assert drifts[0].kind == "sha_unreachable"
        assert drifts[0].symbol == dangling


class TestShaRefSubjectMatch:
    def test_quoted_subject_contained_no_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        sha = _commit(repo, "feat(api): add the widget endpoint")
        md = _write_md(tmp_path, "doc.md", f"""\
            Shipped `feat(api): add the widget endpoint` (`{sha}`).
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert drifts == []

    def test_truncated_quoted_subject_no_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        sha = _commit(repo, "feat(api): add the widget endpoint with retries")
        # Doc quotes only a prefix of the real subject — containment, not equality.
        md = _write_md(tmp_path, "doc.md", f"""\
            Shipped `feat(api): add the widget endpoint` (`{sha}`).
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert drifts == []


class TestShaRefSubjectMismatch:
    def test_wrong_quoted_subject_is_drift(self, tmp_path):
        repo = _init_repo(tmp_path)
        sha = _commit(repo, "feat(api): add the widget endpoint")
        md = _write_md(tmp_path, "doc.md", f"""\
            Shipped `fix(core): a completely unrelated subject` (`{sha}`).
            """)
        drifts = check_sha_refs([str(md)], repo)
        assert len(drifts) == 1
        assert drifts[0].kind == "sha_subject_mismatch"
        assert drifts[0].symbol == sha


class TestShaRefDetection:
    def test_non_hex_backtick_ignored(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init")
        md = _write_md(tmp_path, "doc.md", """\
            Call `someFunction` to do the thing.
            """)
        assert check_sha_refs([str(md)], repo) == []

    def test_hex_shorter_than_7_ignored(self, tmp_path):
        repo = _init_repo(tmp_path)
        _commit(repo, "init")
        md = _write_md(tmp_path, "doc.md", """\
            Short token `abc12` is not a sha.
            """)
        assert check_sha_refs([str(md)], repo) == []


class TestShaRefPublicAPI:
    def test_check_sha_refs_not_in_default_checkers(self):
        # git-dependent — must NOT run on the pure-filesystem / --fix default path.
        assert check_sha_refs not in CHECKERS

    def test_audit_sha_refs_surfaces_actual_subject(self, tmp_path):
        repo = _init_repo(tmp_path)
        sha = _commit(repo, "docs: write the thing")
        md = _write_md(tmp_path, "doc.md", f"""\
            Ref `{sha}`.
            """)
        rows = audit_sha_refs([str(md)], repo)
        assert len(rows) == 1
        assert rows[0]["sha"] == sha
        assert rows[0]["resolves"] is True
        assert rows[0]["actual_subject"] == "docs: write the thing"


class TestShaRefNonGitDir:
    def test_non_git_dir_no_raise_returns_empty(self, tmp_path):
        # tmp_path is NOT a git repo — audit must not raise, returns no drift.
        md = _write_md(tmp_path, "doc.md", """\
            Ref `deadbee` here.
            """)
        assert check_sha_refs([str(md)], tmp_path) == []


# ===========================================================================
# Inline-backtick anchor verifier (Slice 1)
# ===========================================================================

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

    # --- Slice 3: en-dash / em-dash range separators (were INVISIBLE to the regex) ---

    def test_inline_endash_range_in_range_no_drift(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2, inside 1-3
        md = self._doc(tmp_path, "block **`f()`** `alpha.py:1–3`\n")  # EN-DASH separator
        assert check_line_anchors([str(md)], tmp_path) == []  # def within range -> ok

    def test_inline_endash_range_out_of_range_is_drift(self, tmp_path):
        _init_repo(tmp_path)
        # def at 5, OUTSIDE the cited en-dash range 1–3 -> def_drift (was INVISIBLE pre-fix)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")
        md = self._doc(tmp_path, "block **`f()`** `alpha.py:1–3`\n")  # EN-DASH separator
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1
        assert drifts[0].kind == "def_drift"
        assert drifts[0].target_line == 1
        assert drifts[0].suggested_line == 5

    def test_inline_emdash_range_matches(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")  # def at 5
        md = self._doc(tmp_path, "block **`f()`** `alpha.py:1—3`\n")  # EM-DASH (defensive)
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 1 and drifts[0].kind == "def_drift"

    def test_inline_ascii_hyphen_range_still_works(self, tmp_path):
        # Regression guard alongside test_inline_range_anchor: ASCII hyphen unaffected.
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2, inside 1-3
        md = self._doc(tmp_path, "block **`f()`** `alpha.py:1-3`\n")  # ASCII hyphen
        assert check_line_anchors([str(md)], tmp_path) == []

    def test_link_and_inline_same_line_distinct_both_checked(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\ndef f():\n    pass\n")  # def at 3
        # inline says 1 (stale), link says 2 (stale) — DISTINCT (file,line) -> both drift.
        # Each anchor gets its OWN nearest-preceding symbol token so binding is
        # unambiguous (the existing nearest-backtick rule binds to the closest token).
        md = self._doc(tmp_path, "**`f`** `alpha.py:1` then `f` [f](alpha.py:2)\n")
        drifts = check_line_anchors([str(md)], tmp_path)
        assert len(drifts) == 2
        assert {d.style for d in drifts} == {"inline", "link"}

    def test_link_and_inline_same_target_deduped(self, tmp_path):
        # Spec test 8, same-(file,line) sub-case: link + inline pointing at the
        # IDENTICAL (file,line) -> the inline is de-duped, only the link drifts.
        # The link gets its own nearest-preceding symbol token so it binds + drifts.
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")  # def at 5
        # both anchors say alpha.py:3 (stale) -> exactly ONE drift (the link's)
        md = self._doc(tmp_path, "**`f`** `alpha.py:3` see `f` [f](alpha.py:3)\n")
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

    # --- Slice 3: en-dash range --fix canonicalizes to ASCII hyphen + shifts both ends ---

    def test_fix_canonicalizes_endash_range_and_shifts(self, tmp_path):
        _init_repo(tmp_path)
        # def at 5; cited en-dash range 1–3 (def out of range) -> 5-7 (ASCII), span 2 preserved
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")
        md = _write_md(tmp_path, "doc.md", "see **`f()`** `alpha.py:1–3` here\n")
        remaining = run([str(md)], tmp_path, fix=True)
        text = md.read_text()
        assert "`alpha.py:5-7`" in text   # ASCII hyphen, both ends shifted by +4
        assert "–" not in text            # en-dash canonicalized away
        assert remaining == []

    def test_fix_endash_range_is_idempotent(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")  # def at 5
        md = _write_md(tmp_path, "doc.md", "see **`f()`** `alpha.py:1–3` here\n")
        run([str(md)], tmp_path, fix=True)
        first = md.read_text()
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == first

    def test_fix_endash_span_guard_round_trips(self, tmp_path):
        # ADV-1 span guard: the drifted en-dash occurrence is rewritten at its own span;
        # a correct neighbor on the same line is left untouched (not clobbered).
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\n# 2\n# 3\n# 4\ndef f():\n    pass\n")  # def at 5
        _commit_py(tmp_path, "beta.py", "def g():\n    pass\n")                       # def at 1
        md = _write_md(tmp_path, "doc.md", "**`f()`** `alpha.py:1–3` and **`g()`** `beta.py:1`\n")
        run([str(md)], tmp_path, fix=True)
        text = md.read_text()
        assert "`alpha.py:5-7`" in text
        assert "`beta.py:1`" in text       # untouched

    def test_shift_display_accepts_endash_link_range(self):
        # Defensive (markdown-link range path): an en-dash display is shifted AND
        # canonicalized to ASCII. 0 such anchors exist today; closes a latent bug.
        from check_doc_claims import _shift_display
        assert _shift_display("core.py:10–20", 10, 30) == "core.py:30-40"
        assert _shift_display(":138–140", 138, 200) == ":200-202"

    def test_fix_never_touches_fenced_anchor(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "def f():\n    pass\n")        # def at 1
        text = "```\n**`f()`** `alpha.py:999`\n```\n"
        md = _write_md(tmp_path, "doc.md", text)
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == text   # untouched (fenced -> never a drift -> never fixed)


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


# ---------------------------------------------------------------------------
# BUG 1 — ADV-1 (CRITICAL): --fix corrupts a line carrying two same-bare-token,
# different-resolved-file, same-stale-line inline anchors. The reviewer repro:
# two committed files a/controller.py (foo@2) + b/controller.py (bar@3); one doc
# line with **`foo()`** `controller.py:9` and **`bar()`** `controller.py:9`.
# After --fix, foo must -> :2 (correct) AND bar must -> :3 (correct, NOT :2).
# A second --fix pass must be a no-op (idempotent).
# ---------------------------------------------------------------------------

class TestInlineFixSameTokenCollision:
    def test_two_same_token_anchors_each_get_own_correct_line(self, tmp_path):
        _init_repo(tmp_path)
        # foo defined at line 2 of a/controller.py
        _commit_py(tmp_path, "a/controller.py", "# 1\ndef foo():\n    pass\n")
        # bar defined at line 3 of b/controller.py
        _commit_py(tmp_path, "b/controller.py", "# 1\n# 2\ndef bar():\n    pass\n")
        # both anchors bare `controller.py:9` (stale); symbol disambiguates each.
        md = _write_md(
            tmp_path, "doc.md",
            "**`foo()`** `controller.py:9` and **`bar()`** `controller.py:9`\n",
        )
        run([str(md)], tmp_path, fix=True)
        # foo -> :2 (correct), bar -> :3 (correct, NOT clobbered to :2)
        assert md.read_text() == (
            "**`foo()`** `controller.py:2` and **`bar()`** `controller.py:3`\n"
        )

    def test_same_token_collision_fix_is_idempotent(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "a/controller.py", "# 1\ndef foo():\n    pass\n")
        _commit_py(tmp_path, "b/controller.py", "# 1\n# 2\ndef bar():\n    pass\n")
        md = _write_md(
            tmp_path, "doc.md",
            "**`foo()`** `controller.py:9` and **`bar()`** `controller.py:9`\n",
        )
        run([str(md)], tmp_path, fix=True)
        first_pass = md.read_text()
        # Second --fix pass must change nothing (no oscillation, no drift left).
        remaining = run([str(md)], tmp_path, fix=True)
        assert md.read_text() == first_pass
        # And the converged text has zero def_drift remaining.
        assert [d for d in remaining if d.kind == "def_drift"] == []


# ---------------------------------------------------------------------------
# NC-MINOR-1 (Lane V): a single _apply_fixes pass is span-safe but not always
# idempotent when a fixable inline anchor is NESTED inside a drifting markdown
# link's display (overlapping spans). The span/identity guard defers the outer
# anchor instead of corrupting it; run()'s convergence loop must close it in ONE
# invocation. (Without the loop, the inner fixes pass 1 and the link stays stale.)
# ---------------------------------------------------------------------------

class TestNestedOverlapConvergence:
    # ov_fn def lands at line 25; both the inline `ov.py:9` (in the link display)
    # and the link target src/ov.py:9 are stale and overlap.
    _SRC = "# pad\n" * 24 + "def ov_fn():\n    pass\n"
    _DOC = "Tricky `ov_fn` [see `ov.py:9`](src/ov.py:9) nested anchors.\n"
    _FIXED = "Tricky `ov_fn` [see `ov.py:25`](src/ov.py:25) nested anchors.\n"

    def test_nested_link_and_inline_converge_in_one_run(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "src/ov.py", self._SRC)
        md = _write_md(tmp_path, "doc.md", self._DOC)
        remaining = run([str(md)], tmp_path, fix=True)
        # Both the nested inline AND the enclosing link end up correct after ONE run.
        assert md.read_text() == self._FIXED
        # No fixable drift left behind (the deferred outer anchor was re-detected + fixed).
        assert [d for d in remaining
                if d.kind == "def_drift" and d.fixable and d.suggested_line is not None] == []

    def test_nested_overlap_fix_is_idempotent(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "src/ov.py", self._SRC)
        md = _write_md(tmp_path, "doc.md", self._DOC)
        run([str(md)], tmp_path, fix=True)
        first = md.read_text()
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == first


# ---------------------------------------------------------------------------
# --exclude-target: when fixing, hold back drifts whose target file matches an
# exclude substring (a source file under concurrent edit by another seat). The
# stable subset gets fixed; the excluded anchors stay flagged (deferred), and the
# convergence loop still terminates. Enables a "fix the stable subset now, sweep
# the in-flight files later" workflow without churning re-drifting anchors.
# ---------------------------------------------------------------------------

class TestExcludeTargetFilter:
    def _setup(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "stable.py", "# 1\n# 2\ndef foo():\n    pass\n")       # foo @ 3
        _commit_py(tmp_path, "phase_c_ffmpeg.py", "# 1\n# 2\n# 3\ndef bar():\n    pass\n")  # bar @ 4
        return _write_md(
            tmp_path, "doc.md",
            "**`foo`** `stable.py:9` and **`bar`** `phase_c_ffmpeg.py:9`\n",
        )

    def test_excluded_target_deferred_stable_fixed(self, tmp_path):
        md = self._setup(tmp_path)
        remaining = run([str(md)], tmp_path, fix=True,
                        exclude_targets=["phase_c_ffmpeg.py"])
        # stable.py:9 -> :3 fixed; phase_c_ffmpeg.py:9 held back at :9
        assert md.read_text() == (
            "**`foo`** `stable.py:3` and **`bar`** `phase_c_ffmpeg.py:9`\n"
        )
        # excluded anchor still flagged as drift (deferred, not fixed)
        assert any(d.kind == "def_drift" and "phase_c_ffmpeg.py" in d.target_file
                   for d in remaining)
        # stable anchor fully resolved (no longer drift)
        assert not any(d.kind == "def_drift" and "stable.py" in d.target_file
                       for d in remaining)

    def test_no_exclude_fixes_both(self, tmp_path):
        md = self._setup(tmp_path)
        run([str(md)], tmp_path, fix=True)
        assert md.read_text() == (
            "**`foo`** `stable.py:3` and **`bar`** `phase_c_ffmpeg.py:4`\n"
        )

    def test_exclude_run_is_idempotent_and_terminates(self, tmp_path):
        md = self._setup(tmp_path)
        run([str(md)], tmp_path, fix=True, exclude_targets=["phase_c_ffmpeg.py"])
        first = md.read_text()
        # second pass with the same exclude must not loop or change the excluded anchor
        run([str(md)], tmp_path, fix=True, exclude_targets=["phase_c_ffmpeg.py"])
        assert md.read_text() == first


# ---------------------------------------------------------------------------
# BUG 2 — CQ-1 (IMPORTANT): _resolve_inline_target must not crash when a
# tracked-but-absent basename candidate is read during symbol-disambiguation.
# git ls-files lists tracked paths even if absent on disk (staged deletion,
# git rm --cached, sparse checkout, mid-rename). An unreadable candidate must
# be treated as NON-defining (skipped), not raise FileNotFoundError.
# ---------------------------------------------------------------------------

class TestResolveInlineTargetAbsentCandidate:
    def test_absent_candidate_does_not_raise(self, tmp_path):
        _init_repo(tmp_path)
        # Two tracked controller.py. foo is defined only in present one.
        _commit_py(tmp_path, "present/controller.py", "# 1\ndef foo():\n    pass\n")
        _commit_py(tmp_path, "absent/controller.py", "def other():\n    pass\n")
        idx = {"controller.py": ["absent/controller.py", "present/controller.py"]}
        # Delete the on-disk file but keep it tracked (git ls-files still lists it).
        (tmp_path / "absent" / "controller.py").unlink()
        # Disambiguating on foo must NOT raise FileNotFoundError; it must
        # gracefully skip the absent candidate and resolve to the present one.
        rel, cand = _resolve_inline_target("controller.py", "foo", idx, tmp_path)
        assert rel == "present/controller.py" and cand is None

    def test_all_candidates_absent_is_advisory_not_crash(self, tmp_path):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "x/controller.py", "def a():\n    pass\n")
        _commit_py(tmp_path, "y/controller.py", "def b():\n    pass\n")
        idx = {"controller.py": ["x/controller.py", "y/controller.py"]}
        (tmp_path / "x" / "controller.py").unlink()
        (tmp_path / "y" / "controller.py").unlink()
        # symbol bound but NO candidate is readable -> no disambiguation possible
        # -> falls through to advisory (truly ambiguous), without raising.
        rel, cand = _resolve_inline_target("controller.py", "a", idx, tmp_path)
        assert rel is None
        assert cand == ["x/controller.py", "y/controller.py"]


# ---------------------------------------------------------------------------
# BUG 3 — ADV-2 (MINOR): an unbalanced/stray fence leaves in_fence=True for the
# rest of the document, silently skipping every later anchor. Must emit a loud
# stderr WARNING naming the doc.
# ---------------------------------------------------------------------------

class TestUnclosedFenceWarning:
    def test_unclosed_fence_emits_stderr_warning(self, tmp_path, capsys):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")  # def at 2
        # A real anchor BEFORE the stray fence, then an unclosed fence, then an
        # anchor that gets silently swallowed. The warning must fire at EOF.
        md = _write_md(
            tmp_path, "doc.md",
            "good **`f()`** `alpha.py:2`\n```\nopen fence never closed\n",
        )
        check_line_anchors([str(md)], tmp_path)
        err = capsys.readouterr().err
        assert "doc.md" in err
        assert ("unclosed fence" in err.lower()) or ("not verified" in err.lower())

    def test_balanced_fence_emits_no_warning(self, tmp_path, capsys):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "alpha.py", "# 1\ndef f():\n    pass\n")
        md = _write_md(
            tmp_path, "doc.md",
            "text\n```\nfenced\n```\nmore **`f()`** `alpha.py:2`\n",
        )
        check_line_anchors([str(md)], tmp_path)
        err = capsys.readouterr().err
        assert "unclosed fence" not in err.lower()


# ---------------------------------------------------------------------------
# Slice 3: multi-range comma-list anchors (`file:A-B, C-D`) are unparseable by
# _INLINE_ANCHOR_RE -> warn (don't silently skip), per the ADV-2 principle.
# ---------------------------------------------------------------------------

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
        _commit_py(tmp_path, "mod.py", "# 1\n# 2\ndef f():\n    pass\n")  # def at 3
        md = _write_md(
            tmp_path, "doc.md",
            "**`f`** `mod.py:3` plus the batch `mod.py:1–5, 9–12`\n",
        )
        drifts = check_line_anchors([str(md)], tmp_path)
        assert drifts == []                       # the normal `mod.py:3` anchor verified OK
        assert "multi-range" in capsys.readouterr().err.lower()

    def test_single_range_does_not_trigger_multi_range_warning(self, tmp_path, capsys):
        _init_repo(tmp_path)
        _commit_py(tmp_path, "mod.py", "def f():\n    pass\n")  # def at 1
        # the `, 9, 12` is PROSE, outside the backticks -> must NOT false-fire
        md = _write_md(tmp_path, "doc.md", "**`f`** `mod.py:1–5` covers cases 9, 12\n")
        check_line_anchors([str(md)], tmp_path)
        assert "multi-range" not in capsys.readouterr().err.lower()

    def test_bare_number_comma_list_also_warns(self, tmp_path, capsys):
        # `file:N,M` (comma-list whose FIRST entry is a bare line, no leading range)
        # is ALSO unparseable by _INLINE_ANCHOR_RE -> must warn, not silently skip.
        # Real such anchors are live in ARCHITECTURE.md/OPERATIONS.md (cold-review finding).
        _init_repo(tmp_path)
        _commit_py(tmp_path, "mod.py", "def f():\n    pass\n")
        md = _write_md(tmp_path, "doc.md", "see `mod.py:133,924` and `mod.py:139,203,232`\n")
        check_line_anchors([str(md)], tmp_path)
        err = capsys.readouterr().err
        assert "2 multi-range" in err.lower()   # both bare-number comma-lists counted
        assert "not verified" in err.lower()

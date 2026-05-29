"""TDD tests for scripts/check_doc_claims.py — line-anchor verifier.

Run: .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -q

All 10 required cases are each in their own test function.  Fixtures use
real tmp_path files (no mocking).
"""

from __future__ import annotations

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

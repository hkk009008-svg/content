"""TDD tests for scripts/status.py — repo status dashboard.

Run: .venv/bin/python -m pytest tests/unit/test_status.py -q

Pure helpers under test:
  count_unread(cursor_ts, event_filenames, seat) -> int
  latest_adr(text) -> tuple[int, str] | None
  render(data: dict) -> str

All tests use real tmp_path files; no network calls.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Put scripts/ on sys.path so we can import status.py
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from status import count_unread, latest_adr, render, render_manifest  # noqa: E402


# ===========================================================================
# count_unread
# ===========================================================================


class TestCountUnread:
    """Tests for count_unread(cursor_ts, event_filenames, seat) -> int.

    Normalization rule: cursor uses colons (T20:38:34Z), filenames use
    dashes (T20-38-34Z). Both are normalized to dashes before comparison.
    Comparison is lexicographic (zero-padded ISO-ish text sorts correctly).
    """

    def test_counts_events_after_cursor(self):
        """Events strictly after the cursor addressed to the seat are counted."""
        cursor = "2026-05-28T10:00:00Z"
        filenames = [
            "2026-05-28T09-00-00Z-director-to-operator-decision.md",  # before cursor
            "2026-05-28T11-00-00Z-director-to-operator-decision.md",  # after  cursor
            "2026-05-28T12-00-00Z-director-to-operator-decision.md",  # after  cursor
        ]
        assert count_unread(cursor, filenames, "operator") == 2

    def test_excludes_events_equal_to_cursor(self):
        """An event whose timestamp exactly equals the cursor is NOT counted."""
        cursor = "2026-05-28T10:00:00Z"
        filenames = [
            "2026-05-28T10-00-00Z-director-to-operator-decision.md",  # == cursor
            "2026-05-28T11-00-00Z-director-to-operator-decision.md",  # after
        ]
        assert count_unread(cursor, filenames, "operator") == 1

    def test_excludes_events_addressed_to_other_seat(self):
        """Events addressed to director are excluded when seat='operator'."""
        cursor = "2026-05-28T08:00:00Z"
        filenames = [
            "2026-05-28T09-00-00Z-operator-to-director-verification-report.md",
            "2026-05-28T09-30-00Z-director-to-operator-decision.md",
        ]
        # Only the to-operator one should be counted for seat=operator
        assert count_unread(cursor, filenames, "operator") == 1

    def test_colon_dash_normalization(self):
        """Cursor colons are normalized to dashes for comparison (real format)."""
        # Cursor exactly matches the last filename: T20:38:34Z == T20-38-34Z
        cursor = "2026-05-28T20:38:34Z"
        filenames = [
            "2026-05-28T20-38-34Z-director-to-operator-coordination.md",  # == cursor (excluded)
            "2026-05-28T20-38-33Z-director-to-operator-decision.md",       # before (excluded)
        ]
        assert count_unread(cursor, filenames, "operator") == 0

    def test_skips_malformed_filenames(self):
        """Filenames that don't match the expected pattern are silently skipped."""
        cursor = "2026-05-28T00:00:00Z"
        filenames = [
            "not-a-real-event.md",
            "NOTES.md",
            "2026-05-28T12-00-00Z-director-to-operator-decision.md",  # valid
        ]
        assert count_unread(cursor, filenames, "operator") == 1

    def test_empty_list_returns_zero(self):
        """No events → 0 unread."""
        assert count_unread("2026-05-28T00:00:00Z", [], "operator") == 0

    def test_director_seat_counts_to_director_events(self):
        """seat='director' counts events addressed to-director."""
        cursor = "2026-05-28T08:00:00Z"
        filenames = [
            "2026-05-28T09-00-00Z-operator-to-director-report.md",   # to director, after
            "2026-05-28T09-00-00Z-director-to-operator-decision.md", # to operator, after (excluded)
        ]
        assert count_unread(cursor, filenames, "director") == 1


# ===========================================================================
# latest_adr
# ===========================================================================


class TestLatestAdr:
    """Tests for latest_adr(text) -> tuple[int, str] | None.

    ADR headings in DECISIONS.md look like:
      ## ADR-017 — Storyboard B-integrate: ...
    """

    def test_single_adr(self):
        """Finds one ADR and returns its number + title."""
        text = textwrap.dedent("""\
            Some preamble.

            ## ADR-001 — First rule ever
            Body text.
        """)
        result = latest_adr(text)
        assert result is not None
        num, title = result
        assert num == 1
        assert "First rule ever" in title

    def test_returns_highest_numbered_adr(self):
        """When multiple ADRs exist, returns the one with the highest number."""
        text = textwrap.dedent("""\
            ## ADR-001 — Old rule
            ## ADR-017 — Newest rule
            ## ADR-009 — Middle rule
        """)
        result = latest_adr(text)
        assert result is not None
        num, title = result
        assert num == 17
        assert "Newest rule" in title

    def test_returns_none_when_no_adrs(self):
        """No ADR headings → returns None."""
        text = "# Just a regular document\n\nNo ADRs here."
        assert latest_adr(text) is None

    def test_real_format_with_colon_after_em_dash(self):
        """Handles real DECISIONS.md format: 'ADR-017 — Title: with colon'."""
        text = textwrap.dedent("""\
            ## ADR-017 — Storyboard B-integrate: batched Kling generation behind a default-off flag
        """)
        result = latest_adr(text)
        assert result is not None
        num, title = result
        assert num == 17
        assert "Storyboard" in title

    def test_template_placeholder_adr_nnn_is_ignored(self):
        """ADR-NNN placeholder headings (non-numeric) are not counted."""
        text = textwrap.dedent("""\
            ## ADR-NNN — <Short imperative title>
            ## ADR-001 — Real rule
        """)
        result = latest_adr(text)
        assert result is not None
        assert result[0] == 1


# ===========================================================================
# render
# ===========================================================================


class TestRender:
    """Tests for render(data: dict) -> str.

    render() formats an already-collected data dict into the report string.
    We test that the key lines are present given a known input dict.
    """

    def _make_data(self, **overrides) -> dict:
        base = {
            "generated_at": "2026-05-29T00:00:00Z",
            "git_sha": "abc1234",
            "git_subject": "feat(web): add status dashboard",
            "git_branch": "main",
            "git_ahead": 2,
            "git_behind": 0,
            "git_dirty": 3,
            "mailbox_operator_unread": 0,
            "mailbox_operator_cursor": "2026-05-28T20:38:34Z",
            "mailbox_director_unread": 9,
            "mailbox_director_cursor": "2026-05-28T11:52:29Z",
            "latest_adr": "ADR-017 — Storyboard B-integrate",
            "doc_integrity": "clean",
            "pod_status": "DOWN",
        }
        base.update(overrides)
        return base

    def test_contains_generated_at_timestamp(self):
        out = render(self._make_data())
        assert "2026-05-29T00:00:00Z" in out

    def test_contains_git_sha_and_subject(self):
        out = render(self._make_data())
        assert "abc1234" in out
        assert "feat(web): add status dashboard" in out

    def test_contains_branch(self):
        out = render(self._make_data())
        assert "main" in out

    def test_contains_dirty_count(self):
        out = render(self._make_data())
        assert "3" in out  # dirty file count

    def test_contains_mailbox_unread_counts(self):
        out = render(self._make_data())
        assert "9" in out   # director unread

    def test_contains_latest_adr(self):
        out = render(self._make_data())
        assert "ADR-017" in out

    def test_contains_doc_integrity_clean(self):
        out = render(self._make_data())
        assert "clean" in out

    def test_contains_pod_down(self):
        out = render(self._make_data())
        assert "DOWN" in out

    def test_contains_smoke_pointer(self):
        """Must include the ci_smoke.py pointer, not run the smoke test inline."""
        out = render(self._make_data())
        assert "ci_smoke.py" in out

    def test_unavailable_values_passed_through(self):
        """(unavailable: ...) strings from collectors appear verbatim."""
        data = self._make_data(
            git_sha="(unavailable: timeout)",
            pod_status="(unavailable: no COMFYUI_SERVER_URL)",
        )
        out = render(data)
        assert "(unavailable: timeout)" in out
        assert "(unavailable: no COMFYUI_SERVER_URL)" in out

    def test_derived_live_disclaimer(self):
        """Header must say 'derived live — do not hand-edit'."""
        out = render(self._make_data())
        assert "derived live" in out

    def test_do_not_hand_edit(self):
        out = render(self._make_data())
        assert "do not hand-edit" in out


# ===========================================================================
# render_manifest
# ===========================================================================


class TestRenderManifest:
    """Tests for render_manifest(components) -> list[str].

    render_manifest takes a list of audit_manifest result dicts and returns
    lines for the '## Pipeline status (manifest)' section.
    """

    def _make_component(self, id, title, status, anchor, valid, current_line=None, problem=None, note=""):
        file, symbol = anchor.rsplit(":", 1)
        return {
            "id": id,
            "title": title,
            "status": status,
            "anchor": anchor,
            "note": note,
            "valid": valid,
            "current_line": current_line,
            "problem": problem,
        }

    def test_valid_component_uses_checkmark_line(self):
        """A valid component should produce a line with ✓."""
        comp = self._make_component(
            id="scene_transitions",
            title="Cross-dissolve",
            status="wired",
            anchor="phase_c_ffmpeg.py:xfade_concat",
            valid=True,
            current_line=42,
        )
        lines = render_manifest([comp])
        combined = "\n".join(lines)
        assert "✓" in combined
        assert "scene_transitions" in combined
        assert "wired" in combined
        assert "@42" in combined
        assert "Cross-dissolve" in combined

    def test_invalid_component_uses_cross_line(self):
        """An invalid component should produce a line with ✗ and BROKEN."""
        comp = self._make_component(
            id="storyboard_mode",
            title="Storyboard",
            status="stubbed",
            anchor="kling_native.py:generate_storyboard",
            valid=False,
            problem="symbol not found: generate_storyboard",
        )
        lines = render_manifest([comp])
        combined = "\n".join(lines)
        assert "✗" in combined
        assert "storyboard_mode" in combined
        assert "BROKEN" in combined
        assert "generate_storyboard" in combined

    def test_status_grouping_order(self):
        """Components grouped in order: live, wired, stubbed, parked, dead."""
        components = [
            self._make_component("d", "Dead", "dead", "f.py:d", True, 1),
            self._make_component("s", "Stubbed", "stubbed", "f.py:s", True, 2),
            self._make_component("l", "Live", "live", "f.py:l", True, 3),
            self._make_component("w", "Wired", "wired", "f.py:w", True, 4),
            self._make_component("p", "Parked", "parked", "f.py:p", True, 5),
        ]
        lines = render_manifest(components)
        combined = "\n".join(lines)
        # All should be present
        for status in ("live", "wired", "stubbed", "parked", "dead"):
            assert status in combined
        # live appears before wired, wired before stubbed, stubbed before parked, parked before dead
        pos_live = combined.index("live")
        pos_wired = combined.index("wired")
        pos_stubbed = combined.index("stubbed")
        pos_parked = combined.index("parked")
        pos_dead = combined.index("dead")
        assert pos_live < pos_wired < pos_stubbed < pos_parked < pos_dead

    def test_section_header_present(self):
        """Output includes the section header and source attribution."""
        lines = render_manifest([])
        combined = "\n".join(lines)
        assert "Pipeline status" in combined
        assert "pipeline_status.toml" in combined

    def test_no_manifest_sentinel(self):
        """render_manifest(None) → line containing '(no docs/pipeline_status.toml)'."""
        lines = render_manifest(None)
        combined = "\n".join(lines)
        assert "no docs/pipeline_status.toml" in combined

    def test_render_includes_manifest_section(self):
        """render(data) with manifest_components key includes the Pipeline status section."""
        data = {
            "generated_at": "2026-05-29T00:00:00Z",
            "git_sha": "abc1234",
            "git_subject": "test",
            "git_branch": "main",
            "git_ahead": 0,
            "git_behind": 0,
            "git_dirty": 0,
            "mailbox_operator_unread": 0,
            "mailbox_operator_cursor": "2026-05-29T00:00:00Z",
            "mailbox_director_unread": 0,
            "mailbox_director_cursor": "2026-05-29T00:00:00Z",
            "latest_adr": "ADR-017",
            "doc_integrity": "clean",
            "pod_status": "DOWN",
            "manifest_components": [
                {
                    "id": "final_assembly",
                    "title": "Final assembly",
                    "status": "live",
                    "anchor": "cinema_pipeline.py:_assemble_final",
                    "note": "",
                    "valid": True,
                    "current_line": 100,
                    "problem": None,
                }
            ],
        }
        out = render(data)
        assert "Pipeline status" in out
        assert "final_assembly" in out

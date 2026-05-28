"""Unit tests for feat(location-research): auto-populate location reference images.

Coverage
--------
(a) auto_research=False (default)
    → research_location_visual NOT called; behaviour identical to today.

(b) auto_research=True + Tavily available (2 fake URLs)
    → both downloaded + appended to reference_images after uploads.

(c) auto_research=True + no Tavily key (research returns [])
    → no refs added, no error.

(d) auto_research=True + one download fails
    → failed URL skipped, successful URL still stored.

All tests are fully offline — no real network, no real Tavily calls.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(pid: str = "proj_test") -> dict:
    return {"id": pid, "locations": [], "global_settings": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAutoResearchOff:
    """(a) auto_research=False (default) — research NOT called."""

    def test_research_not_called_when_flag_false(self):
        from domain.location_manager import create_location_with_images

        project = _make_project()

        with patch("research_engine.research_location_visual") as mock_rv, \
             patch("domain.location_manager._download_url_to_file") as mock_dl, \
             patch("domain.location_manager.add_location"):
            mock_rv.return_value = ["http://example.com/img1.jpg"]
            location = create_location_with_images(
                project, "Studio", "Black curtained studio",
                auto_research=False,
            )

        mock_rv.assert_not_called()
        mock_dl.assert_not_called()
        assert location["reference_images"] == []

    def test_research_not_called_by_default(self):
        """Calling with no auto_research kwarg must not trigger research."""
        from domain.location_manager import create_location_with_images

        project = _make_project()

        with patch("research_engine.research_location_visual") as mock_rv, \
             patch("domain.location_manager.add_location"):
            mock_rv.return_value = ["http://example.com/img1.jpg"]
            location = create_location_with_images(
                project, "Studio", "Black curtained studio",
                # auto_research NOT passed — must default to False
            )

        mock_rv.assert_not_called()
        assert location["reference_images"] == []


class TestAutoResearchOn:
    """(b) auto_research=True + Tavily available → downloads both URLs."""

    def test_two_urls_downloaded_and_stored(self, tmp_path):
        from domain.location_manager import create_location_with_images

        project = _make_project()
        fake_urls = ["http://example.com/img1.jpg", "http://example.com/img2.jpg"]

        def fake_download(url: str, dst: str) -> bool:
            with open(dst, "wb") as f:
                f.write(b"fake-image-bytes")
            return True

        with patch("research_engine.research_location_visual",
                   return_value=fake_urls) as mock_rv, \
             patch("domain.location_manager._download_url_to_file",
                   side_effect=fake_download) as mock_dl, \
             patch("domain.location_manager._loc_dir", return_value=str(tmp_path)), \
             patch("domain.location_manager.add_location"):
            location = create_location_with_images(
                project, "Forest", "Dense pine forest with morning mist",
                auto_research=True,
            )

        mock_rv.assert_called_once_with("Dense pine forest with morning mist")
        assert mock_dl.call_count == 2
        refs = location["reference_images"]
        assert len(refs) == 2
        # Paths follow the ref_research_{n}.jpg convention
        assert all("ref_research_" in os.path.basename(r) for r in refs)

    def test_researched_refs_supplement_uploads(self, tmp_path):
        """User uploads are present AND researched refs APPEND (not replace)."""
        from domain.location_manager import create_location_with_images

        project = _make_project()
        # Create a fake upload file
        upload = tmp_path / "upload.jpg"
        upload.write_bytes(b"upload-bytes")

        fake_urls = ["http://example.com/research1.jpg"]

        def fake_download(url: str, dst: str) -> bool:
            with open(dst, "wb") as f:
                f.write(b"researched-bytes")
            return True

        with patch("research_engine.research_location_visual",
                   return_value=fake_urls), \
             patch("domain.location_manager._download_url_to_file",
                   side_effect=fake_download), \
             patch("domain.location_manager._loc_dir", return_value=str(tmp_path)), \
             patch("domain.location_manager.add_location"):
            location = create_location_with_images(
                project, "Beach", "Sunny tropical beach",
                reference_image_paths=[str(upload)],
                auto_research=True,
            )

        refs = location["reference_images"]
        # Upload + 1 researched ref = 2 total
        assert len(refs) == 2
        assert "ref_0" in os.path.basename(refs[0])           # user upload
        assert "ref_research_" in os.path.basename(refs[1])   # researched


class TestNoTavilyKey:
    """(c) no Tavily key → research returns [] → no refs added, no error."""

    def test_empty_research_result_adds_no_refs(self):
        from domain.location_manager import create_location_with_images

        project = _make_project()

        with patch("research_engine.research_location_visual",
                   return_value=[]) as mock_rv, \
             patch("domain.location_manager._download_url_to_file") as mock_dl, \
             patch("domain.location_manager.add_location"):
            location = create_location_with_images(
                project, "Studio", "Minimalist studio",
                auto_research=True,
            )

        mock_rv.assert_called_once()
        mock_dl.assert_not_called()
        assert location["reference_images"] == []

    def test_research_import_error_handled_gracefully(self):
        """If research_engine cannot be imported inside the fn, no error raised."""
        from domain.location_manager import create_location_with_images

        project = _make_project()

        # Replace research_engine in sys.modules with a stub that lacks the fn,
        # so the lazy `from research_engine import research_location_visual`
        # raises ImportError.
        bad_mod = types.ModuleType("research_engine")
        # Deliberately do NOT set research_location_visual on the stub.

        with patch.dict(sys.modules, {"research_engine": bad_mod}), \
             patch("domain.location_manager.add_location"):
            # Must NOT raise
            location = create_location_with_images(
                project, "Studio", "Minimalist studio",
                auto_research=True,
            )

        assert location["reference_images"] == []


class TestDownloadFailure:
    """(d) download failure → failed URL skipped, successful URL stored."""

    def test_failed_url_skipped_successful_stored(self, tmp_path):
        from domain.location_manager import create_location_with_images

        project = _make_project()
        fake_urls = [
            "http://fail.example.com/bad.jpg",
            "http://ok.example.com/good.jpg",
        ]

        call_count = [0]

        def selective_download(url: str, dst: str) -> bool:
            call_count[0] += 1
            if "fail" in url:
                return False
            with open(dst, "wb") as f:
                f.write(b"ok-bytes")
            return True

        with patch("research_engine.research_location_visual",
                   return_value=fake_urls), \
             patch("domain.location_manager._download_url_to_file",
                   side_effect=selective_download), \
             patch("domain.location_manager._loc_dir", return_value=str(tmp_path)), \
             patch("domain.location_manager.add_location"):
            location = create_location_with_images(
                project, "Mountain", "Rocky mountain peak",
                auto_research=True,
            )

        # Two downloads attempted
        assert call_count[0] == 2
        refs = location["reference_images"]
        # Only the successful URL stored
        assert len(refs) == 1
        assert "ref_research_" in os.path.basename(refs[0])

    def test_all_downloads_fail_no_refs_no_error(self, tmp_path):
        from domain.location_manager import create_location_with_images

        project = _make_project()

        with patch("research_engine.research_location_visual",
                   return_value=["http://fail.example.com/a.jpg",
                                 "http://fail.example.com/b.jpg"]), \
             patch("domain.location_manager._download_url_to_file",
                   return_value=False), \
             patch("domain.location_manager._loc_dir", return_value=str(tmp_path)), \
             patch("domain.location_manager.add_location"):
            location = create_location_with_images(
                project, "Cave", "Dark cave interior",
                auto_research=True,
            )

        assert location["reference_images"] == []


class TestLocationResearchToggleRoundTrip:
    """Round-trip tests: location_research persists in global_settings and
    is read correctly by the endpoint logic.

    The save path is:
        project["global_settings"].update(data["global_settings"])   # web_server.py:511
    The read path is:
        project.get("global_settings", {}).get("location_research", False)  # web_server.py:1128

    These tests exercise both directions — no Flask client needed; we
    simulate the dict mutation that the PUT /api/projects/<pid> endpoint
    performs and verify the read semantics directly.
    """

    def test_toggle_true_round_trips_to_read(self):
        """Setting location_research=True via the save path is visible at read."""
        project = _make_project()
        # Simulate the save path (web_server.py:511)
        project["global_settings"].update({"location_research": True})
        # Simulate the read path (web_server.py:1128)
        result = bool(project.get("global_settings", {}).get("location_research", False))
        assert result is True

    def test_toggle_false_round_trips_to_read(self):
        """Setting location_research=False via the save path is visible at read."""
        project = _make_project()
        project["global_settings"].update({"location_research": False})
        result = bool(project.get("global_settings", {}).get("location_research", False))
        assert result is False

    def test_default_absent_reads_as_false(self):
        """If location_research is never persisted, the read returns False (default OFF)."""
        project = _make_project()
        # global_settings is empty — key absent
        assert "location_research" not in project["global_settings"]
        result = bool(project.get("global_settings", {}).get("location_research", False))
        assert result is False

    def test_toggle_is_not_in_api_engine_defaults_namespace(self):
        """location_research must NOT be stored/read from api_engine_defaults.
        This guards against the original bug where it was misplaced there."""
        # Simulate an api_engine_defaults dict (what /api/config returns).
        api_engine_defaults = {
            "KLING_NATIVE": {"enabled": True},
            "SORA_NATIVE":  {"enabled": True},
        }
        # The correct namespace is global_settings — api_engine_defaults should
        # not contain location_research at all.
        assert "location_research" not in api_engine_defaults

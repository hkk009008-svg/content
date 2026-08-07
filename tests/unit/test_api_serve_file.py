"""
tests/unit/test_api_serve_file.py — Tests for the
GET /api/projects/<pid>/file endpoint (guard containment).

Covers:
  1. Missing path parameter -> 400
  2. Path traversal (relative outside project) -> 403
  3. Path traversal (absolute outside project) -> 403
  4. Path inside project but file missing -> 404
  5. Happy path (image/jpeg) -> 200
  6. Happy path (video/mp4) -> 200
  7. Happy path (audio/mpeg) -> 200

Uses Flask's test_client() with patched get_project_dir.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from web_server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def mock_project_dir(tmp_path):
    """Patch get_project_dir to return a temp directory."""
    with patch("web_server.get_project_dir", return_value=str(tmp_path)) as mock:
        yield tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_api_serve_file_missing_path(client):
    """Missing path parameter -> 400 'Invalid path'."""
    response = client.get("/api/projects/proj-1/file")
    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid path"}


def test_api_serve_file_empty_path(client):
    """Empty path parameter -> 400 'Invalid path'."""
    response = client.get("/api/projects/proj-1/file?path=")
    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid path"}


def test_api_serve_file_path_traversal_relative(client, mock_project_dir):
    """Path traversal attempt outside project_dir -> 403."""
    # Attempt to go up and out of the temp dir
    malicious_path = os.path.join(str(mock_project_dir), "..", "..", "etc", "passwd")
    response = client.get(f"/api/projects/proj-1/file?path={malicious_path}")
    assert response.status_code == 403
    assert response.get_json() == {"error": "Access denied"}


def test_api_serve_file_path_traversal_absolute(client, mock_project_dir):
    """Absolute path outside project_dir -> 403."""
    malicious_path = "/etc/passwd"
    response = client.get(f"/api/projects/proj-1/file?path={malicious_path}")
    assert response.status_code == 403
    assert response.get_json() == {"error": "Access denied"}


def test_api_serve_file_not_found(client, mock_project_dir):
    """Valid path inside project_dir but file doesn't exist -> 404."""
    missing_file = mock_project_dir / "missing.jpg"
    response = client.get(f"/api/projects/proj-1/file?path={missing_file}")
    assert response.status_code == 404
    assert response.get_json() == {"error": "File not found"}


def test_api_serve_file_happy_path_jpg(client, mock_project_dir):
    """Valid path to existing .jpg -> 200, mimetype image/jpeg."""
    test_file = mock_project_dir / "test.jpg"
    test_file.write_bytes(b"fake jpeg content")

    response = client.get(f"/api/projects/proj-1/file?path={test_file}")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"fake jpeg content"


def test_api_serve_file_happy_path_mp4(client, mock_project_dir):
    """Valid path to existing .mp4 -> 200, mimetype video/mp4."""
    test_file = mock_project_dir / "test.mp4"
    test_file.write_bytes(b"fake video content")

    response = client.get(f"/api/projects/proj-1/file?path={test_file}")
    assert response.status_code == 200
    assert response.mimetype == "video/mp4"
    assert response.data == b"fake video content"


def test_api_serve_file_happy_path_audio(client, mock_project_dir):
    """Valid path to existing .mp3 -> 200, mimetype audio/mpeg."""
    test_file = mock_project_dir / "test.mp3"
    test_file.write_bytes(b"fake audio content")

    response = client.get(f"/api/projects/proj-1/file?path={test_file}")
    assert response.status_code == 200
    assert response.mimetype == "audio/mpeg"
    assert response.data == b"fake audio content"


# ---------------------------------------------------------------------------
# Slice 10 — portable media persistence + explicit media states.
#
# Product invariant #6: project-owned output is stored by project-relative
# path (or a stable media ID), never a repo-location-dependent absolute
# path. These tests cover the two new /file responsibilities:
#   1. Serve a project-relative `path` directly (the new persistence form).
#   2. Serve a LEGACY absolute `path` (baked in before this fix, or before a
#      repo move) via a safe suffix migration -- without weakening the
#      existing traversal/root guard proven above.
# ---------------------------------------------------------------------------

def test_api_serve_file_relative_path_resolves_under_project_dir(client, mock_project_dir):
    """New persistence form: a project-relative `path` (no repo-location-
    dependent absolute prefix) is joined onto the CURRENT project directory
    and served normally."""
    outputs_dir = mock_project_dir / "shots" / "sh1" / "outputs"
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "take1.jpg").write_bytes(b"relative take bytes")

    response = client.get("/api/projects/proj-1/file?path=shots/sh1/outputs/take1.jpg")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"relative take bytes"
    assert "X-Media-Migrated" not in response.headers


def test_api_serve_file_relative_path_traversal_refused(client, mock_project_dir):
    """A project-relative `path` with `..` components must not escape
    project_dir -- the new relative-join branch is guarded the same way as
    the existing absolute-traversal case above."""
    response = client.get("/api/projects/proj-1/file?path=../../../etc/passwd")
    assert response.status_code == 403
    assert response.get_json() == {"error": "Access denied"}


def test_api_serve_file_move_root_migrates_legacy_absolute_path(client, tmp_path):
    """RED->GREEN proof for the move-root defect: a take's `path` was
    persisted as an absolute path rooted at the OLD project directory
    (dir A). The repo has since moved -- get_project_dir(pid) now resolves
    under a NEW directory (dir B). The old absolute string no longer exists
    on disk, but its project-owned remainder ("shots/sh1/outputs/take1.jpg")
    DOES exist under the CURRENT project directory. /file must still serve
    it (200, correct bytes) via the safe suffix migration and flag the
    response as migrated, instead of 403ing (or 404ing) the whole project
    unviewable.

    Before slice 10's fix, this asserts and fails: the old-root path doesn't
    resolve under the new project_dir, so the pre-fix root guard correctly
    (but unhelpfully) returns 403 for a project that simply moved.
    """
    pid = "proj_move_root"
    old_root = tmp_path / "old_location"
    new_root = tmp_path / "new_location_after_move"
    rel = os.path.join("shots", "sh1", "outputs", "take1.jpg")

    new_project_dir = new_root / pid
    (new_project_dir / "shots" / "sh1" / "outputs").mkdir(parents=True)
    (new_project_dir / "shots" / "sh1" / "outputs" / "take1.jpg").write_bytes(b"take bytes")

    # The path as persisted before the move. old_root/pid is never created on
    # disk -- the repo (and PROJECTS_DIR under it) moved away from it, so
    # this string is exactly what a pre-move take["path"] would still hold.
    legacy_absolute_path = str(old_root / pid / rel)

    with patch("web_server.get_project_dir", return_value=str(new_project_dir)):
        response = client.get(f"/api/projects/{pid}/file?path={legacy_absolute_path}")

    assert response.status_code == 200
    assert response.data == b"take bytes"
    assert response.headers.get("X-Media-Migrated") == "1"


def test_api_serve_file_move_root_missing_after_migration_returns_404(client, tmp_path):
    """The pid anchor matches (this project's own stale reference) but the
    migrated candidate genuinely doesn't exist (never generated, or lost) --
    404 "File not found", not 403, since the reconstructed path IS correctly
    rooted under the current project directory."""
    pid = "proj_gone"
    new_project_dir = tmp_path / "new" / pid
    new_project_dir.mkdir(parents=True)  # project exists; this one take doesn't
    legacy_path = str(tmp_path / "old" / pid / "shots" / "sh1" / "outputs" / "take1.jpg")

    with patch("web_server.get_project_dir", return_value=str(new_project_dir)):
        response = client.get(f"/api/projects/{pid}/file?path={legacy_path}")

    assert response.status_code == 404
    assert response.get_json() == {"error": "File not found"}


def test_api_serve_file_migration_cannot_be_used_to_escape_root(client, tmp_path):
    """A crafted path containing the pid segment followed by `..` components
    must not use the safe-suffix-migration mechanism to escape the project
    root -- the migrated candidate is containment-rechecked, exactly like
    the primary candidate."""
    pid = "proj_escape"
    new_project_dir = tmp_path / "new" / pid
    new_project_dir.mkdir(parents=True)
    crafted = str(tmp_path / "anywhere" / pid / ".." / ".." / ".." / "etc" / "passwd")

    with patch("web_server.get_project_dir", return_value=str(new_project_dir)):
        response = client.get(f"/api/projects/{pid}/file?path={crafted}")

    assert response.status_code == 403
    assert response.get_json() == {"error": "Access denied"}


def test_api_serve_file_mime_uses_real_extension_not_audio_default(client, mock_project_dir):
    """A non-jpg/mp4/mp3 extension must not silently default to audio/mpeg
    (the old ternary's bug) -- mimetypes.guess_type gives the real type."""
    test_file = mock_project_dir / "test.png"
    test_file.write_bytes(b"fake png content")

    response = client.get(f"/api/projects/proj-1/file?path={test_file}")
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_api_serve_file_mime_unknown_extension_falls_back_to_octet_stream(client, mock_project_dir):
    """A genuinely unrecognized extension falls back to the standard
    unknown-binary MIME type rather than a wrong, specific label."""
    test_file = mock_project_dir / "test.unknownext"
    test_file.write_bytes(b"binary content")

    response = client.get(f"/api/projects/proj-1/file?path={test_file}")
    assert response.status_code == 200
    assert response.mimetype == "application/octet-stream"


def test_api_serve_file_forbids_content_sniffing(client, mock_project_dir):
    """The conservative MIME label must be binding, not a hint.

    This route serves user-supplied media. Without `nosniff` a browser may
    ignore `application/octet-stream` and render the bytes as whatever they
    look like — which is how an uploaded file becomes HTML in the user's own
    origin. The header must be present on recognized types too, so the
    protection does not depend on which extension happened to be uploaded.
    """
    unknown = mock_project_dir / "test.unknownext"
    unknown.write_bytes(b"<html><script>alert(1)</script></html>")
    known = mock_project_dir / "known.png"
    known.write_bytes(b"\x89PNG\r\n\x1a\n")

    for path in (unknown, known):
        response = client.get(f"/api/projects/proj-1/file?path={path}")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"




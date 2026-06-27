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




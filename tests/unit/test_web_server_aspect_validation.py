"""Phase 1 — /api/config gate + PUT aspect validation."""
import json
import pytest

from cinema.aspect import SUPPORTED_ASPECT_RATIOS


@pytest.fixture
def client():
    import web_server
    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as c:
        yield c


def test_config_aspect_ratios_is_gated(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["aspect_ratios"] == SUPPORTED_ASPECT_RATIOS  # ["16:9"] until Phase 3


def _make_project(tmp_path, monkeypatch) -> str:
    """Create a real persisted project under tmp_path; return its pid.

    create_project(name) -> dict; pid = dict["id"]. _project_dir/_project_file/
    mutate_project read module-global PROJECTS_DIR at call time, so patching
    domain.project_manager.PROJECTS_DIR is resolved consistently.
    """
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project("aspect-test")["id"]


def test_put_rejects_unsupported_aspect_ratio(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"aspect_ratio": "9:16"}})
    assert resp.status_code == 400
    body = json.loads(resp.data)
    assert "aspect_ratio" in (body.get("error", "") + str(body))
    assert body.get("supported") == SUPPORTED_ASPECT_RATIOS


def test_put_accepts_supported_aspect_ratio(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"aspect_ratio": "16:9"}})
    assert resp.status_code == 200


def test_put_without_aspect_ratio_is_unaffected(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"language": "Korean"}})
    assert resp.status_code == 200

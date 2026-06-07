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

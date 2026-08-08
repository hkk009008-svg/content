"""The reference-set write route — the first HTTP path that can touch it.

Before this route existed, `multi_angle_refs` had ONE writer (character
creation) and no HTTP surface at all: POST/PUT/DELETE on a character never
touched it. Since it is the only field any video provider reads, a reference
added after creation was invisible to every provider, permanently.

The route deliberately cannot add or delete files. A reference exists because it
was uploaded or generated, both of which are paid, validated paths of their own.
What it owns is what a reference IS, whether it may be used, and in what ORDER —
the last being what actually reaches providers, since every consumer truncates
from the front at a different cut.
"""

from __future__ import annotations

import json

import pytest

import web_server


@pytest.fixture
def client(tmp_path, monkeypatch):
    import domain.project_manager as pm

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path))
    project = {
        "id": "proj_ref", "characters": [{
            "id": "c1", "name": "Subject",
            "canonical_reference": "characters/canon.jpg",
            "multi_angle_refs": ["characters/canon.jpg", "characters/profile.jpg"],
            "reference_images": ["characters/canon.jpg"],
        }],
        "locations": [], "objects": [], "scenes": [], "global_settings": {},
    }
    root = tmp_path / "proj_ref"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")

    web_server.app.config["TESTING"] = True
    return web_server.app.test_client()


def _patch(client, body):
    return client.patch(
        "/api/projects/proj_ref/characters/c1/references", json=body
    )


def test_labelling_a_reference_persists_and_reports_coverage(client) -> None:
    response = _patch(client, {"references": [
        {"path": "characters/profile.jpg", "yaw": "profile", "origin": "photo"},
    ]})
    assert response.status_code == 200
    body = response.get_json()
    assert body["coverage"]["yaw"]["profile"] == 1
    assert any(
        ref["path"] == "characters/profile.jpg" and ref["yaw"] == "profile"
        for ref in body["identity_refs"]
    )


def test_rejecting_a_reference_removes_it_from_what_providers_receive(client) -> None:
    """The case this exists for: a panel showing a different person's face.

    It scored HIGHER than the panel that was the subject, so no automatic
    filter would catch it. Only the human verdict does — and the verdict has to
    reach the field providers actually read.
    """

    response = _patch(client, {"references": [
        {"path": "characters/profile.jpg", "judged": "reject",
         "reason": "not the subject"},
    ]})
    assert response.status_code == 200
    delivered = response.get_json()["delivered"]
    assert "characters/profile.jpg" not in delivered["veo_or_fal_first_4"]
    assert delivered["kling_frontal"] == "characters/canon.jpg"


def test_an_unknown_path_is_refused_rather_than_ignored(client) -> None:
    """A typo must not read as success while changing nothing."""

    response = _patch(client, {"references": [{"path": "characters/nope.jpg"}]})
    assert response.status_code == 400
    assert "characters/nope.jpg" in response.get_json()["error"]


def test_reorder_for_coverage_puts_the_canonical_first(client) -> None:
    """Slot 0 is Kling's FRONTAL image (phase_c_ffmpeg uploads valid_refs[0])."""

    response = _patch(client, {
        "references": [
            {"path": "characters/profile.jpg", "yaw": "profile", "origin": "photo"},
            {"path": "characters/canon.jpg", "yaw": "front", "origin": "photo"},
        ],
        "reorder_for_coverage": True,
    })
    assert response.status_code == 200
    assert response.get_json()["delivered"]["kling_frontal"] == "characters/canon.jpg"


def test_the_response_shows_what_each_consumer_will_receive(client) -> None:
    """Truncation should be visible here, not discovered in a render."""

    body = _patch(client, {"references": []}).get_json()
    assert set(body["delivered"]) == {
        "kling_frontal", "veo_or_fal_first_4", "reference_to_video_first_8",
    }
    assert len(body["delivered"]["veo_or_fal_first_4"]) <= 4


def test_a_non_json_body_is_refused(client) -> None:
    response = client.patch(
        "/api/projects/proj_ref/characters/c1/references", data="not json"
    )
    assert response.status_code == 400


def test_a_missing_character_is_404(client) -> None:
    response = client.patch(
        "/api/projects/proj_ref/characters/nobody/references", json={"references": []}
    )
    assert response.status_code == 404

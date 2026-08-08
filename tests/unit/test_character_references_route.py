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


# ---------------------------------------------------------------------------
# `order` — the field that actually changes what a provider receives
# ---------------------------------------------------------------------------

def test_a_patch_list_alone_does_not_reorder(client) -> None:
    """The defect this field exists to fix.

    The route rebuilds the set by iterating the RECORD's order and looking each
    path up, so a client that sent its patches in a new order got a 200, an
    unchanged `multi_angle_refs`, and no way to tell. A Reference Sheet page
    offering "Save order" on top of that would have been a button that did
    nothing while reporting success.
    """

    response = _patch(client, {"references": [
        {"path": "characters/profile.jpg"},
        {"path": "characters/canon.jpg"},
    ]})
    assert response.status_code == 200
    assert response.get_json()["delivered"]["veo_or_fal_first_4"] == [
        "characters/canon.jpg", "characters/profile.jpg",
    ]


def test_order_reorders_the_set_and_the_canonical_still_leads_delivery(client) -> None:
    """Two rules meet at slot 0 and only one can win.

    `derive_legacy_fields` forces the canonical to the front of
    `multi_angle_refs`, because slot 0 is uploaded as Kling's FRONTAL image
    (phase_c_ffmpeg.py:2245). An `order` that moved something else there would
    be silently overruled by that projection — a button reporting success and
    changing nothing. So `order` owns the sequence of the SET, and moving the
    frontal image is its own act (below).
    """

    response = _patch(client, {
        "order": ["characters/profile.jpg", "characters/canon.jpg"],
    })
    assert response.status_code == 200
    body = response.get_json()
    assert [ref["path"] for ref in body["identity_refs"]] == [
        "characters/profile.jpg", "characters/canon.jpg",
    ]
    assert body["delivered"]["kling_frontal"] == "characters/canon.jpg"


def test_naming_a_new_canonical_changes_what_kling_gets(client) -> None:
    """The one act that moves slot 0, deliberately separate from a reorder.

    `canonical_reference` is ALSO the identity-validation anchor
    (`get_reference_image`), and ADR-092 measured that the scorer floors and
    inverts rank off-angle. A profile canonical would compare every frame
    against a view the embedder cannot read, so correct footage would fail. That
    consequence is too large to fall out of dragging a thumbnail.
    """

    response = _patch(client, {"canonical": "characters/profile.jpg"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["delivered"]["kling_frontal"] == "characters/profile.jpg"
    assert [
        ref["path"] for ref in body["identity_refs"]
        if "canonical" in (ref.get("roles") or [])
    ] == ["characters/profile.jpg"]


def test_a_canonical_outside_the_set_is_refused(client) -> None:
    response = _patch(client, {"canonical": "characters/nope.jpg"})
    assert response.status_code == 400
    assert "canonical must name one" in response.get_json()["error"]


def test_a_malformed_canonical_is_refused_before_any_mutation(client) -> None:
    response = _patch(client, {"canonical": ["characters/canon.jpg"]})
    assert response.status_code == 400
    assert "canonical must be a path" in response.get_json()["error"]


def test_a_short_order_is_refused_rather_than_deleting_by_omission(client) -> None:
    """An order that names fewer paths would silently DROP the rest.

    Dropping a reference is a paid asset leaving the set; it must never be a
    side effect of a reorder that forgot one.
    """

    response = _patch(client, {"order": ["characters/canon.jpg"]})
    assert response.status_code == 400
    assert "exact permutation" in response.get_json()["error"]
    # And nothing moved.
    after = _patch(client, {})
    assert after.get_json()["delivered"]["kling_frontal"] == "characters/canon.jpg"


def test_an_order_naming_an_unknown_path_is_refused(client) -> None:
    response = _patch(client, {
        "order": ["characters/canon.jpg", "characters/nope.jpg"],
    })
    assert response.status_code == 400
    assert "exact permutation" in response.get_json()["error"]


def test_a_malformed_order_is_refused_before_any_mutation(client) -> None:
    for bad in ("characters/canon.jpg", [7], {"a": 1}):
        response = _patch(client, {"order": bad})
        assert response.status_code == 400, bad
        assert "order must be a list of paths" in response.get_json()["error"]


def test_order_facets_and_canonical_apply_in_one_call(client) -> None:
    """The page sends them together; none may cancel another."""

    response = _patch(client, {
        "order": ["characters/profile.jpg", "characters/canon.jpg"],
        "canonical": "characters/profile.jpg",
        "references": [
            {"path": "characters/profile.jpg", "yaw": "profile", "origin": "photo"},
        ],
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["delivered"]["kling_frontal"] == "characters/profile.jpg"
    assert body["coverage"]["yaw"]["profile"] == 1
    assert [ref["path"] for ref in body["identity_refs"]] == [
        "characters/profile.jpg", "characters/canon.jpg",
    ]


def test_reorder_for_coverage_still_wins_over_an_explicit_order(client) -> None:
    """Both in one request is a contradiction; the coverage sort is the later,
    louder instruction and the response shows which one applied."""

    response = _patch(client, {
        "order": ["characters/profile.jpg", "characters/canon.jpg"],
        "reorder_for_coverage": True,
    })
    assert response.status_code == 200
    # order_for_coverage puts the canonical back at slot 0, always.
    assert response.get_json()["delivered"]["kling_frontal"] == "characters/canon.jpg"

"""Creating a character who depicts nobody, end to end.

`creation_kind` existed on the record (written only by read-time migration,
always INFERRED and always "real") and `generate_canonical_from_description`
existed with ZERO non-test callers. So a described character was unreachable:
nothing let a user declare the kind, and nothing called the generator. This
closes both halves and pins the boundaries between them.

The distinction is not presentation. A `real` character is a person who exists,
photographs pose them, and generation only ever varies geometry that was
PHOTOGRAPHED — ask for a profile the camera never saw and the model invents a
stranger (ADR-092: the subject rejected exactly such a panel, and it had scored
HIGHER than the one that was him). A `described` character depicts nobody, so
panel 1 defines them and there is no likeness to be wrong about.
"""

from __future__ import annotations

import json
import pytest

from domain.character_manager import (
    _character_creation_fingerprint,
    create_character_with_images,
)


# ---------------------------------------------------------------------------
# The kinds are mutually exclusive at the domain boundary
# ---------------------------------------------------------------------------

def _project() -> dict:
    return {
        "id": "proj_kind", "characters": [], "locations": [], "objects": [],
        "scenes": [], "global_settings": {},
    }


def test_described_refuses_uploads_rather_than_merging_them() -> None:
    """If photographs of the subject exist, the character is REAL.

    A kind that accepted both would let a real person be created under
    semantics written precisely for a character who depicts nobody — including
    the consent rule that a described sheet may train a LoRA without anyone
    having consented, because nobody is in it.
    """

    with pytest.raises(ValueError, match="created from text, not uploads"):
        create_character_with_images(
            _project(), "Nemo", "a tall figure in a grey coat",
            reference_image_paths=["/tmp/somebody.jpg"],
            creation_kind="described",
        )


def test_described_refuses_an_empty_description() -> None:
    """There is nothing to generate panel 1 from, and no photograph to fall
    back on. Creating the character anyway would persist a subject with no
    references at all — which is what happened before this field existed."""

    with pytest.raises(ValueError, match="needs a description"):
        create_character_with_images(
            _project(), "Nemo", "   ", creation_kind="described",
        )


def test_an_unknown_kind_falls_back_to_the_stricter_reading() -> None:
    """`real` is the stricter of the two: uploads are permitted and required,
    and no canonical is ever generated from text. Defaulting there means a
    malformed value can never quietly create a person under the looser rules.

    Asserted through the two guards that fire ONLY for `described` — a bogus
    kind must trip neither, and the fingerprint must match a real one exactly.
    """

    common = dict(
        name="Nemo", description="", voice_id="", gender="",
        reference_image_paths=None,
    )
    assert (
        _character_creation_fingerprint(**common, creation_kind="banana")
        == _character_creation_fingerprint(**common, creation_kind="real")
    )

    # Neither described-only refusal applies: uploads are fine, and an empty
    # description is fine, because this is a real character.
    with pytest.raises(Exception) as caught:
        create_character_with_images(
            _project(), "Nemo", "", reference_image_paths=["/tmp/somebody.jpg"],
            creation_kind="banana",
        )
    message = str(caught.value)
    assert "created from text, not uploads" not in message
    assert "needs a description" not in message


# ---------------------------------------------------------------------------
# The fingerprint binds the kind, without breaking requests staged before it
# ---------------------------------------------------------------------------

def test_a_real_request_fingerprint_is_unchanged_by_this_field() -> None:
    """Every request staged before `creation_kind` existed was a real one.

    Keying it unconditionally would change those fingerprints mid-resume, and
    `_assert_matching_creation` reads a changed fingerprint as "different
    character inputs" and refuses — turning a recoverable interrupted creation
    into one an operator has to reconcile by hand.
    """

    common = dict(
        name="Alice", description="d", voice_id="v", gender="",
        reference_image_paths=None,
    )
    assert (
        _character_creation_fingerprint(**common)
        == _character_creation_fingerprint(**common, creation_kind="real")
    )


def test_a_described_request_cannot_collide_with_a_real_one() -> None:
    """Same name, same text, different kind — and a different reservation.

    Without this, resuming a described request as real (or the reverse) would
    look like the same request and create the wrong kind of character against a
    paid attempt reserved for the other.
    """

    common = dict(
        name="Alice", description="d", voice_id="v", gender="",
        reference_image_paths=None,
    )
    assert (
        _character_creation_fingerprint(**common, creation_kind="described")
        != _character_creation_fingerprint(**common, creation_kind="real")
    )


# ---------------------------------------------------------------------------
# The HTTP surface
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    import domain.project_manager as pm
    import web_server

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path))
    project = {
        "id": "proj_kind", "characters": [], "locations": [], "objects": [],
        "scenes": [], "global_settings": {},
    }
    root = tmp_path / "proj_kind"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")
    web_server.app.config["TESTING"] = True
    return web_server.app.test_client()


def test_the_estimate_is_derived_from_the_ledger_s_own_constants(client) -> None:
    """Price before the click, and not a number typed into a template.

    A constant copied into the UI would be correct the day it was written and
    silently wrong afterwards — wrong in the direction that matters, since the
    user authorises the spend from what it says.
    """

    from cost_tracker import API_COST_USD
    from domain.character_manager import _ANGLE_CONFIGS

    response = client.get("/api/projects/proj_kind/characters/creation-estimate")
    assert response.status_code == 200
    body = response.get_json()

    angles = len(_ANGLE_CONFIGS) * API_COST_USD["FLUX_KONTEXT"]
    assert body["real"]["usd"] == pytest.approx(angles)
    assert body["described"]["usd"] == pytest.approx(
        angles + API_COST_USD["FLUX_PRO"]
    )
    # Described costs strictly more: it pays for the canonical an upload gives
    # away free. If these ever match, one of the two is not being charged.
    assert body["described"]["usd"] > body["real"]["usd"]


def test_an_unrecognised_creation_kind_is_refused_not_coerced(client) -> None:
    """Coercing a typo to `real` would apply the stricter-sounding label while
    skipping nothing; coercing it to `described` would create a person under
    rules written for a character who depicts nobody. Refuse instead."""

    response = client.post(
        "/api/projects/proj_kind/characters",
        data={
            "creation_request_id": "a" * 32,
            "name": "Nemo",
            "description": "a tall figure",
            "creation_kind": "synthetic",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "creation_kind must be one of" in response.get_json()["error"]


def test_described_without_a_description_is_refused_at_the_route(client) -> None:
    response = client.post(
        "/api/projects/proj_kind/characters",
        data={
            "creation_request_id": "b" * 32,
            "name": "Nemo",
            "description": "   ",
            "creation_kind": "described",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "needs a description" in response.get_json()["error"]


def test_an_absent_creation_kind_still_means_real(client, monkeypatch) -> None:
    """Backwards compatibility control: every caller before this field meant
    `real`, and must keep working without sending it."""

    import web_server

    captured = {}

    def _fake_create(project, name, description, **kwargs):
        captured.update(kwargs)
        return {"id": "char_x", "name": name}

    monkeypatch.setattr(web_server, "create_character_with_images", _fake_create)
    response = client.post(
        "/api/projects/proj_kind/characters",
        data={
            "creation_request_id": "c" * 32,
            "name": "Alice",
            "description": "a person",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    assert captured.get("creation_kind") == "real"


def test_a_declared_described_kind_reaches_the_domain_call(client, monkeypatch) -> None:
    """The end-to-end thread. Every other assertion here is about one link.

    Before this, `creation_kind` was written ONLY by read-time migration and
    always inferred as "real", so nothing a user could send reached
    `create_character_with_images` — and `generate_canonical_from_description`,
    which that function is the only caller of, had no way to run.
    """

    import web_server

    captured = {}

    def _fake_create(project, name, description, **kwargs):
        captured.update(kwargs)
        return {"id": "char_d", "name": name}

    monkeypatch.setattr(web_server, "create_character_with_images", _fake_create)
    response = client.post(
        "/api/projects/proj_kind/characters",
        data={
            "creation_request_id": "d" * 32,
            "name": "Nemo",
            "description": "a tall figure in a grey coat",
            "creation_kind": "described",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    assert captured.get("creation_kind") == "described"

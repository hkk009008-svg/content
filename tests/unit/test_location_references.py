"""Location plates: the subject whose references reached nothing at all.

`get_location_reference` had ZERO non-test callers. A user uploaded plates
through `web_server.py:4198-4234`, they were stored and path-migrated correctly
by `_resolve_stored_media_path`, and no image or video provider ever saw one.
The resolver existed, was tested, and was dead.

A location is the only subject every shot in a scene shares, so drift there is
what makes one scene look like three different rooms — and unlike a face, a room
has no identity scorer to notice.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from domain.reference_set import MAX_LOCATION_PLATES, compose_shot_reference_set


def _make(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    return str(path)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _project(loc_id: str = "loc_1", refs=()) -> dict:
    return {
        "id": "p_loc",
        "characters": [], "objects": [], "scenes": [], "global_settings": {},
        "locations": [{"id": loc_id, "name": "Kitchen",
                       "reference_images": list(refs)}],
    }


def test_plates_resolve_in_record_order(tmp_path) -> None:
    from domain.location_manager import get_location_reference_paths

    wall = _make(tmp_path, "wall.jpg")
    window = _make(tmp_path, "window.jpg")
    project = _project(refs=[wall, window])
    with patch("domain.location_manager._resolve_stored_media_path",
               side_effect=lambda _p, path: path):
        assert get_location_reference_paths(project, "loc_1") == [wall, window]


def test_a_plate_missing_from_disk_is_dropped(tmp_path) -> None:
    from domain.location_manager import get_location_reference_paths

    wall = _make(tmp_path, "wall.jpg")
    project = _project(refs=[str(tmp_path / "gone.jpg"), wall])
    with patch("domain.location_manager._resolve_stored_media_path",
               side_effect=lambda _p, path: path):
        assert get_location_reference_paths(project, "loc_1") == [wall]


def test_an_unknown_location_resolves_empty() -> None:
    from domain.location_manager import get_location_reference_paths

    assert get_location_reference_paths(_project(), "loc_missing") == []


def test_the_singular_resolver_still_returns_the_first(tmp_path) -> None:
    """`get_location_reference` is public API; its contract must not shift."""

    from domain.location_manager import get_location_reference

    wall = _make(tmp_path, "wall.jpg")
    window = _make(tmp_path, "window.jpg")
    project = _project(refs=[wall, window])
    with patch("domain.location_manager._resolve_stored_media_path",
               side_effect=lambda _p, path: path):
        assert get_location_reference(project, "loc_1") == wall
        assert get_location_reference(project, "loc_missing") is None


# ---------------------------------------------------------------------------
# Composition — same no-contest rule as products
# ---------------------------------------------------------------------------

def test_a_face_in_frame_keeps_every_slot_a_plate_might_have_taken() -> None:
    """The control. A room must never cost a face a reference slot."""

    conditioning, refs = compose_shot_reference_set(
        character_reference="/c/canon.jpg",
        character_angles=["/c/canon.jpg", "/c/profile.jpg"],
        location_refs=["/l/wall.jpg", "/l/window.jpg"],
    )
    assert conditioning == "/c/canon.jpg"
    assert refs == ["/c/canon.jpg", "/c/profile.jpg"]


def test_an_establishing_shot_is_led_by_its_plate() -> None:
    """No character, no product — the shot a plate was uploaded for."""

    conditioning, refs = compose_shot_reference_set(
        location_refs=["/l/wall.jpg", "/l/window.jpg"],
    )
    assert conditioning == "/l/wall.jpg"
    assert refs == ["/l/wall.jpg", "/l/window.jpg"]


def test_the_product_leads_its_own_shot_and_the_room_follows() -> None:
    """Subject before place: slot 0 reads as what the image is ABOUT."""

    conditioning, refs = compose_shot_reference_set(
        object_refs={"o1": ["/o/hero.jpg"]},
        primary_object="o1",
        location_refs=["/l/wall.jpg"],
    )
    assert conditioning == "/o/hero.jpg"
    assert refs == ["/o/hero.jpg", "/l/wall.jpg"]


def test_plates_are_bounded_so_a_room_cannot_evict_the_subject() -> None:
    """A location may hold arbitrarily many plates; the smallest cut is 4.

    Without the bound, six plates behind one product photo would occupy every
    slot the fal path has, and the product would be pushed out of its own shot
    by truncation rather than by any decision.
    """

    plates = [f"/l/plate_{i}.jpg" for i in range(6)]
    _, refs = compose_shot_reference_set(
        object_refs={"o1": ["/o/hero.jpg"]}, primary_object="o1",
        location_refs=plates,
    )
    assert refs == ["/o/hero.jpg"] + plates[:MAX_LOCATION_PLATES]
    assert len(refs) <= 4, "must still fit the smallest downstream cut"


def test_a_plate_already_present_is_not_duplicated() -> None:
    shared = "/shared/backdrop.jpg"
    _, refs = compose_shot_reference_set(
        object_refs={"o1": [shared]}, primary_object="o1",
        location_refs=[shared, "/l/window.jpg"],
    )
    assert refs == [shared, "/l/window.jpg"]


# ---------------------------------------------------------------------------
# End to end: the plate reaches the generator, and the gate priced that route
# ---------------------------------------------------------------------------

class TestPlateReachesTheGenerator:
    """Mirrors TestObjectShotPricesTheRouteItEnters in test_object_references."""

    _FAL_ONLY = types.SimpleNamespace(
        google_api_key="", gemini_api_key="", fal_key="fal-key"
    )

    def _controller(self, tmp_path, continuity_config):
        from cinema.shots.controller import ShotController

        shot = {
            "id": "shot_1_0", "plan_status": "approved",
            "characters_in_frame": [], "camera": "wide_shot",
            "target_api": "AUTO",
        }
        scene = {
            "id": "scene_1", "title": "T", "action": "A",
            "location_id": "loc_1", "shots": [shot],
        }
        project = {
            "id": "proj_plate_gate", "scenes": [scene], "characters": [],
            "objects": [], "locations": [{"id": "loc_1", "name": "Kitchen"}],
            "global_settings": {},
        }

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        lifecycle = MagicMock()
        lifecycle.report_progress.return_value = None
        runstate = MagicMock()
        runstate.shot_results = {}
        runstate.update_progress_pointer.return_value = None

        core = MagicMock()
        core.project = project
        core.project_dir = str(tmp_path)
        core.continuity = MagicMock()
        core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "the empty kitchen at dawn",
            "continuity_config": continuity_config,
        }
        cost_tracker = MagicMock()
        cost_tracker.is_over_budget.return_value = False
        cost_tracker.would_exceed.return_value = False
        cost_tracker.spent_usd = 0.0
        cost_tracker.budget_usd = None
        core.cost_tracker = cost_tracker

        ctrl = ShotController(
            core=core, lifecycle=lifecycle, host=host, runstate=runstate
        )
        ctrl._take_output_path = MagicMock(return_value="/nonexistent/keyframe.jpg")
        ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
        ctrl._mutate_shot = MagicMock()
        return ctrl, cost_tracker

    def test_an_establishing_shot_conditions_on_its_plate(self, tmp_path) -> None:
        wall = _make(tmp_path, "wall.jpg")
        window = _make(tmp_path, "window.jpg")
        ctrl, cost_tracker = self._controller(
            tmp_path,
            {"multi_angle_refs": [], "location_refs": [wall, window]},
        )
        gen_broll = MagicMock()
        with (
            patch("cinema.shots.controller.generate_ai_broll", gen_broll),
            patch("cinema.shots.controller.env_settings", self._FAL_ONLY),
        ):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")

        cost_tracker.would_exceed.assert_called_once_with("FLUX_KONTEXT")
        assert gen_broll.call_args.kwargs["character_image"] == wall
        assert gen_broll.call_args.kwargs["multi_angle_refs"] == [wall, window]

    def test_a_location_with_no_plates_prices_the_free_route(self, tmp_path) -> None:
        """Reversion control: nothing to condition on, gate unchanged."""

        ctrl, cost_tracker = self._controller(
            tmp_path, {"multi_angle_refs": [], "location_refs": []}
        )
        with (
            patch("cinema.shots.controller.generate_ai_broll", MagicMock()),
            patch("cinema.shots.controller.env_settings", self._FAL_ONLY),
        ):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")
        cost_tracker.would_exceed.assert_called_once_with("FLUX_PRO")

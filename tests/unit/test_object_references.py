"""Product references: resolution, and the slot trade left undecided.

Objects reached NO image or video provider. The only generation-path reader of
`project["objects"]` serialises the record into a PROMPT
(llm/prompt_optimizer.py:768-779) — brand, material, surface, texture_anchor,
branding_constraints, scale_reference — so a product's logo was described in
words and never shown, while `make_object`'s docstring claimed
"reference-image conditioning" the code never implemented.

Text substitutes worst exactly where a product must not drift: a logo is
typography and glyph fidelity is the first casualty of a re-render, a glossy
surface IS its reflected environment, and absolute scale has no prior at all.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from domain.character_manager import get_object_reference_paths
from domain.reference_set import compose_shot_reference_set


def _project(tmp_path: Path, canonical: str = "", uploads=()) -> dict:
    return {
        "id": "p1",
        "objects": [{
            "id": "o1", "name": "Widget",
            "canonical_reference": canonical,
            "reference_images": list(uploads),
        }],
        "characters": [], "locations": [], "scenes": [], "global_settings": {},
    }


def _make(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    return str(path)


def test_the_canonical_leads_the_resolved_set(tmp_path) -> None:
    """Slot 0 carries a semantic role downstream, same as for a character."""

    hero = _make(tmp_path, "hero.jpg")
    other = _make(tmp_path, "back.jpg")
    project = _project(tmp_path, canonical=hero, uploads=[other, hero])
    assert get_object_reference_paths(project, "o1") == [hero, other]


def test_an_object_with_no_references_resolves_empty(tmp_path) -> None:
    assert get_object_reference_paths(_project(tmp_path), "o1") == []


def test_an_unknown_object_id_resolves_empty(tmp_path) -> None:
    assert get_object_reference_paths(_project(tmp_path), "missing") == []


def test_a_reference_missing_from_disk_is_dropped(tmp_path) -> None:
    """A path in the record whose file is gone must not reach an uploader."""

    present = _make(tmp_path, "present.jpg")
    project = _project(
        tmp_path, canonical=present, uploads=[str(tmp_path / "gone.jpg")]
    )
    assert get_object_reference_paths(project, "o1") == [present]


def test_object_refs_ride_the_continuity_config_without_taking_face_slots(
    tmp_path, monkeypatch
) -> None:
    """Availability is not a policy.

    Reference slots are scarce — 4 on the Veo/fal path — and every slot an
    object takes is one a face loses. Which subject wins a contested slot is a
    real trade with no measurement behind it, so the plumbing carries the data
    and leaves the decision explicit rather than smuggling it in.
    """

    from continuity_engine import ContinuityEngine

    hero = _make(tmp_path, "hero.jpg")
    project = _project(tmp_path, canonical=hero)
    project["characters"] = [{"id": "char_a", "name": "Alice"}]

    engine = ContinuityEngine(project)
    engine.character_tracker.get_reference_image = lambda _cid: "/ref/a.jpg"
    engine.character_tracker.get_multi_angle_refs = lambda _cid: ["/ref/a-profile.jpg"]

    enhanced = engine.enhance_shot_prompt(
        {
            "characters_in_frame": ["char_a"],
            "objects_in_frame": ["o1"],
            "primary_object": "o1",
            "prompt": "she holds the widget",
        },
        {"id": "scene_1", "shots": []},
    )
    config = enhanced["continuity_config"]

    assert config["object_refs"] == {"o1": [hero]}
    assert config["primary_object"] == "o1"
    # The face's own reference list is untouched by the object's presence.
    assert hero not in config["multi_angle_refs"]


# ---------------------------------------------------------------------------
# compose_shot_reference_set — objects fill only slots no face was using
# ---------------------------------------------------------------------------

def test_a_face_in_frame_keeps_every_slot_it_had() -> None:
    """The negative control, and the one that matters.

    Reference budgets are non-monotonic: Identity Lab scored one reference at
    0.791 and four at 0.499 on the same prompt and seed, because Klein averages
    its conditioning. So an extra image is not free, and no measurement in this
    repository ranks a product photo against a third facial angle. The composed
    set for a shot containing a character must therefore be byte-identical to
    what it was before objects existed.
    """

    conditioning, refs = compose_shot_reference_set(
        character_reference="/c/canon.jpg",
        character_angles=["/c/canon.jpg", "/c/profile.jpg"],
        object_refs={"o1": ["/o/hero.jpg", "/o/back.jpg"]},
        primary_object="o1",
    )
    assert conditioning == "/c/canon.jpg"
    assert refs == ["/c/canon.jpg", "/c/profile.jpg"]
    assert not [path for path in refs if path.startswith("/o/")]


def test_an_object_only_shot_gets_the_empty_slots() -> None:
    """Where there is no face there is no trade, and text is the status quo."""

    conditioning, refs = compose_shot_reference_set(
        character_reference="",
        character_angles=[],
        object_refs={"o2": ["/o/other.jpg"], "o1": ["/o/hero.jpg", "/o/back.jpg"]},
        primary_object="o1",
    )
    # The primary object leads: slot 0 is a semantic position downstream.
    assert conditioning == "/o/hero.jpg"
    assert refs == ["/o/hero.jpg", "/o/back.jpg", "/o/other.jpg"]


def test_angle_refs_without_a_canonical_still_count_as_a_face_shot() -> None:
    """A character record can carry angles and no canonical.

    Treating that as "no face" would hand the object every slot in a shot that
    does contain a person.
    """

    conditioning, refs = compose_shot_reference_set(
        character_reference="",
        character_angles=["/c/profile.jpg"],
        object_refs={"o1": ["/o/hero.jpg"]},
        primary_object="o1",
    )
    assert conditioning == "/c/profile.jpg"
    assert refs == ["/c/profile.jpg"]


def test_no_subject_at_all_composes_nothing() -> None:
    assert compose_shot_reference_set() == ("", [])


def test_an_object_with_no_primary_named_still_contributes() -> None:
    """`primary_object` is optional on the shot record (models.py:96 default "")."""

    conditioning, refs = compose_shot_reference_set(
        object_refs={"o1": ["/o/hero.jpg"]}, primary_object=""
    )
    assert (conditioning, refs) == ("/o/hero.jpg", ["/o/hero.jpg"])


# ---------------------------------------------------------------------------
# The pre-spend gate must price the route the composed value selects
# ---------------------------------------------------------------------------

class TestObjectShotPricesTheRouteItEnters:
    """Supplying a conditioning image is what SELECTS the route the gate prices.

    Reading `primary_reference` at the gate while dispatch reads the composed
    value would reserve FLUX_PRO and then bill FLUX_KONTEXT — a gate priced from
    a different source than the call it guards. These pin both halves against
    the same shot, so a revert of either one fails here.

    Harness mirrors TestKeyframePreSpendBudgetGate in test_budget_pre_spend_gate.
    """

    def _controller(self, tmp_path, *, continuity_config):
        from cinema.shots.controller import ShotController

        shot = {
            "id": "shot_1_0",
            "plan_status": "approved",
            "characters_in_frame": [],
            "objects_in_frame": ["o1"],
            "primary_object": "o1",
            "camera": "medium_shot",
            "target_api": "AUTO",
        }
        scene = {
            "id": "scene_1", "title": "T", "action": "A",
            "location_id": None, "shots": [shot],
        }
        project = {
            "id": "proj_object_gate", "scenes": [scene], "characters": [],
            "objects": [{"id": "o1", "name": "Widget"}],
            "locations": [], "global_settings": {},
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
            "prompt": "base prompt",
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

    _FAL_ONLY = types.SimpleNamespace(
        google_api_key="", gemini_api_key="", fal_key="fal-key"
    )

    def test_object_reference_prices_kontext_and_reaches_the_generator(
        self, tmp_path
    ) -> None:
        hero = _make(tmp_path, "hero.jpg")
        ctrl, cost_tracker = self._controller(
            tmp_path,
            continuity_config={
                "multi_angle_refs": [],
                "object_refs": {"o1": [hero]},
                "primary_object": "o1",
            },
        )
        gen_broll = MagicMock()
        with (
            patch("cinema.shots.controller.generate_ai_broll", gen_broll),
            patch("cinema.shots.controller.env_settings", self._FAL_ONLY),
        ):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")

        # The gate priced the reference-conditioned route...
        cost_tracker.would_exceed.assert_called_once_with("FLUX_KONTEXT")
        # ...and the call it guarded actually took a reference. Before this,
        # phase_c_assembly's `if character_image` gate meant the product was
        # described in words and never shown.
        assert gen_broll.call_args.kwargs["character_image"] == hero
        assert gen_broll.call_args.kwargs["multi_angle_refs"] == [hero]

    def _run_to_validation(self, tmp_path, continuity_config):
        """Drive a take far enough that identity validation would run.

        The budget-gate harness this borrows from stops at a nonexistent output
        path, which returns BEFORE the validator — so an assertion that the
        validator was not called would pass there no matter what the code did.
        A real published image is what makes the negative control below able to
        fail; ``test_a_face_shot_does_reach_the_validator`` proves it does.
        """

        published = tmp_path / "keyframe.png"
        published.write_bytes(b"\x89PNG\r\n\x1a\nkeyframe")
        ctrl, _ = self._controller(tmp_path, continuity_config=continuity_config)
        ctrl._take_output_path = MagicMock(return_value=str(published))

        validator = MagicMock()
        validator.validate_image.return_value = types.SimpleNamespace(
            overall_score=0.9, passed=True, character_results={},
        )
        shared = MagicMock(return_value=validator)
        broll = MagicMock(return_value=types.SimpleNamespace(
            api_name="FLUX_KONTEXT", billed_rejects=(),
        ))
        with (
            patch("cinema.shots.controller.generate_ai_broll", broll),
            patch("cinema.shots.controller.env_settings", self._FAL_ONLY),
            patch("phase_c_vision._get_shared_validator", shared),
        ):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")
        return validator

    def test_a_face_shot_does_reach_the_validator(self, tmp_path) -> None:
        """Positive control for the negative one below — this seam can fire."""

        validator = self._run_to_validation(
            tmp_path,
            {"primary_reference": "/c/canon.jpg", "multi_angle_refs": []},
        )
        assert validator.validate_image.call_count == 1

    def test_an_object_shot_runs_no_face_validation(self, tmp_path) -> None:
        """A product photograph must never be handed to a face validator.

        `identity_validation_ref` stays on `primary_reference`, not the composed
        value. If it were switched to the composed value to "match dispatch",
        a widget would be scored against a face embedder and every product shot
        would fail an identity gate that has no opinion about products.
        """

        hero = _make(tmp_path, "hero.jpg")
        validator = self._run_to_validation(
            tmp_path,
            {
                "multi_angle_refs": [],
                "object_refs": {"o1": [hero]},
                "primary_object": "o1",
            },
        )
        validator.validate_image.assert_not_called()

    def test_a_shot_with_no_object_reference_still_prices_the_free_route(
        self, tmp_path
    ) -> None:
        """Reversion control: with the composition removed there is nothing to
        condition on, and the gate must fall back exactly as it did before."""

        ctrl, cost_tracker = self._controller(
            tmp_path,
            continuity_config={"multi_angle_refs": [], "object_refs": {}},
        )
        with (
            patch("cinema.shots.controller.generate_ai_broll", MagicMock()),
            patch("cinema.shots.controller.env_settings", self._FAL_ONLY),
        ):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0")
        cost_tracker.would_exceed.assert_called_once_with("FLUX_PRO")

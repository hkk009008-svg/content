"""Tests for cinema.shots.strategy — IdentityStrategy promise types (P1-1, spec §3d).

Tasks 5 and 6 will extend this file with router (_resolve_identity_strategy) tests.
"""
import json
import os

import pytest

from cinema.shots.strategy import (
    IdentityStrategy, CharIdentitySpec,
    PRIMARY_ONLY, KONTEXT_MULTI_CHAR, MAX_TIER_PRIMARY_ONLY, NO_IDENTITY_ASSET,
)
from cinema.shots.controller import _resolve_identity_strategy

SETTINGS_NO_LORA = {"quality_tier": "production"}
CC_TWO_REGISTERED = {
    "primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
    "secondary_chars": [{"char_id": "char_b", "reference": "/r/b.jpg",
                         "multi_angle_refs": ["/r/b1.jpg"],
                         "identity_anchor": "anchor b"}],
}
CC_PRIMARY_ONLY = {"primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
                   "secondary_chars": []}


def _shot(chars, primary=""):
    return {"characters_in_frame": chars, "primary_character": primary}


def test_single_char_with_ref_is_primary_only_and_matches_todays_bundle():
    s = _resolve_identity_strategy(
        _shot(["char_a"]), "production",
        {"char_lora_paths": {"char_a": "/l/a.safetensors"},
         "char_lora_strengths": {"char_a": 0.55}},
        CC_PRIMARY_ONLY,
    )
    assert s.mechanism_tag == "PRIMARY_ONLY"
    # zero-regression invariant: identical to today's controller.py:544-549 derivation
    assert s.primary_char_id == "char_a"
    assert s.char_lora_path == "/l/a.safetensors"
    assert s.char_lora_strength == 0.55
    assert [c.char_id for c in s.conditioned_chars] == ["char_a"]
    assert s.unconditioned_chars == []


def test_two_char_production_with_refs_is_kontext_multi():
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "KONTEXT_MULTI_CHAR"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a", "char_b"]
    # V-5: the router must carry the secondary's angle refs into the spec —
    # they feed the slot allocator downstream.
    assert s.conditioned_chars[1].multi_angle_refs == ("/r/b1.jpg",)


def test_two_char_max_tier_promises_multi_lora_with_secondary_conditioned():
    # slice 2: registered-ref secondary is CONDITIONED on max (ReActor rescue
    # at minimum; LoRA chain when one is registered for it).
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "MAX_TIER_MULTI_LORA"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a", "char_b"]
    sec = s.conditioned_chars[1]
    assert sec.fidelity == "reference"     # no LoRA registered for char_b here
    assert sec.lora_path is None
    assert s.unconditioned_chars == []


def test_max_tier_secondary_with_lora_gets_lora_fidelity_and_assets():
    settings = {"quality_tier": "max",
                "char_lora_paths": {"char_b": "/l/b.safetensors"},
                "char_lora_strengths": {"char_b": 0.7},
                "char_lora_triggers": {"char_b": "TOKman"}}
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   settings, CC_TWO_REGISTERED)
    sec = s.conditioned_chars[1]
    assert sec.fidelity == "lora"
    assert sec.lora_path == "/l/b.safetensors"
    assert sec.lora_strength == 0.7
    assert sec.trigger == "TOKman"


def test_max_tier_single_char_stays_primary_only():
    s = _resolve_identity_strategy(_shot(["char_a"]), "max",
                                   SETTINGS_NO_LORA, CC_PRIMARY_ONLY)
    assert s.mechanism_tag == "MAX_TIER_PRIMARY_ONLY"
    assert s.unconditioned_chars == []
    assert s.conditioned_chars[0].fidelity == "pulid"


def test_max_tier_secondary_cap_two_overflow_unconditioned():
    cc = dict(CC_TWO_REGISTERED)
    cc["secondary_chars"] = [
        {"char_id": f"char_{i}", "reference": f"/r/{i}.jpg",
         "multi_angle_refs": [], "identity_anchor": ""} for i in "bcd"
    ]
    s = _resolve_identity_strategy(_shot(["char_a", "char_b", "char_c", "char_d"]),
                                   "max", SETTINGS_NO_LORA, cc)
    assert len(s.conditioned_chars) == 3
    assert s.unconditioned_chars == ["char_d"]


def test_primary_trigger_rides_strategy():
    settings = {"quality_tier": "max",
                "char_lora_paths": {"char_a": "/l/a.safetensors"},
                "char_lora_triggers": {"char_a": "TOKwoman"}}
    s = _resolve_identity_strategy(_shot(["char_a"]), "max", settings,
                                   CC_PRIMARY_ONLY)
    assert s.char_lora_trigger == "TOKwoman"


def test_char_absent_from_secondary_chars_is_unconditioned():
    # A no-ref char never reaches the router as a secondary entry — the engine
    # filters upstream (Task 3); the router reads entry["reference"]
    # unconditionally by design. What it sees here is an EMPTY secondary list.
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA, CC_PRIMARY_ONLY)
    assert s.mechanism_tag == "PRIMARY_ONLY"
    assert s.unconditioned_chars == ["char_b"]


def test_kontext_secondary_cap_is_two():
    cc = dict(CC_TWO_REGISTERED)
    cc["secondary_chars"] = [
        {"char_id": f"char_{i}", "reference": f"/r/{i}.jpg",
         "multi_angle_refs": [], "identity_anchor": ""} for i in "bcd"
    ]
    s = _resolve_identity_strategy(_shot(["char_a", "char_b", "char_c", "char_d"]),
                                   "production", SETTINGS_NO_LORA, cc)
    assert len(s.conditioned_chars) == 3          # primary + 2 (Kontext-tier cap)
    assert s.unconditioned_chars == ["char_d"]


def test_no_chars_or_no_primary_ref_is_no_identity_asset():
    s = _resolve_identity_strategy(_shot([]), "production", SETTINGS_NO_LORA,
                                   {"primary_reference": None, "secondary_chars": []})
    assert s.mechanism_tag == "NO_IDENTITY_ASSET"
    assert s.conditioned_chars == []


def test_chars_in_frame_but_no_primary_ref_all_unconditioned():
    # The other disjunct of the NO_IDENTITY_ASSET arm: chars ARE in frame but
    # no primary reference exists — every in-frame char lands unconditioned.
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "production",
                                   SETTINGS_NO_LORA,
                                   {"primary_reference": None, "secondary_chars": []})
    assert s.mechanism_tag == "NO_IDENTITY_ASSET"
    assert s.conditioned_chars == []
    assert s.unconditioned_chars == ["char_a", "char_b"]


def test_to_metadata_dict_is_json_safe_and_complete():
    s = IdentityStrategy(
        mechanism_tag=KONTEXT_MULTI_CHAR,
        primary_char_id="char_a",
        char_lora_path=None,
        char_lora_strength=None,
        conditioned_chars=[
            CharIdentitySpec(char_id="char_a", reference="/r/a.jpg",
                             identity_anchor="anchor a", fidelity="reference"),
            CharIdentitySpec(char_id="char_b", reference="/r/b.jpg",
                             identity_anchor="anchor b", fidelity="reference",
                             multi_angle_refs=("/r/b1.jpg",)),
        ],
        unconditioned_chars=["char_c"],
    )
    import json
    md = s.to_metadata_dict()
    json.dumps(md)  # must not raise
    assert md["mechanism_tag"] == "KONTEXT_MULTI_CHAR"
    assert [c["char_id"] for c in md["conditioned_chars"]] == ["char_a", "char_b"]
    assert md["unconditioned_chars"] == ["char_c"]
    # V-5 pin: multi_angle_refs must survive the to_dict chain — Task 7's
    # allocator reads it off these dicts via Task 6's kwarg; without it,
    # secondaries can never fill their allocated slots.
    assert md["conditioned_chars"][1]["multi_angle_refs"] == ["/r/b1.jpg"]


# ---------------------------------------------------------------------------
# Task 6: controller integration tests — identity_strategy promise + actual
# ---------------------------------------------------------------------------

from cinema.lifecycle import NullLifecycle
from cinema.runstate import RunState
from cinema.review.controller import ReviewController
from cinema.checkpoint import CheckpointStore
from cinema.shots.controller import ShotController
import domain.project_manager as dpm


class StubContinuity:
    """enhance_shot_prompt stand-in: returns a canned continuity_config."""

    def __init__(self, secondary_chars):
        self._sec = secondary_chars

    def enhance_shot_prompt(self, shot, scene, prev_shot, shot_index,
                            approved_anchor_image=None):
        return {"prompt": "stub prompt", "continuity_config": {
            "primary_reference": "/r/a.jpg", "identity_anchor": "anchor a",
            "multi_angle_refs": [], "secondary_chars": self._sec,
            "scene_seed": 1, "use_img2img": False, "identity_threshold": 0.65,
        }}


class _FakeCore:
    """Minimal PipelineCore stand-in (mirrors test_cross_controller.FakeCore)."""

    def __init__(self, project: dict, project_dir: str):
        self.project = project
        self.project_dir = project_dir
        self.temp_dir = project_dir
        self.export_dir = project_dir
        self.continuity = None
        self.director = None
        self.vbench = None
        self.cost_tracker = None
        self.ensemble = None


class _WiredHost:
    """Implements all three ControllerHost protocols (mirrors test_cross_controller.WiredHost)."""

    def __init__(self, core: _FakeCore, lifecycle, runstate: RunState):
        self._core = core
        self._lifecycle = lifecycle
        self._runstate = runstate
        self._shot_ctrl = ShotController(core, lifecycle, self, runstate)
        self._review_ctrl = ReviewController(core, lifecycle, self, runstate)
        self._checkpoint = CheckpointStore(core, lifecycle, runstate)

    # -- ShotControllerHost surface --
    def _refresh_project_snapshot(self, timeout: float = 10):
        return None

    def _rebuild_review_clips(self, project=None):
        return self._review_ctrl._rebuild_review_clips(project)

    def _candidate_take(self, shot):
        return self._review_ctrl._candidate_take(shot)

    def _resolve_take_path(self, shot, take_id):
        return self._review_ctrl._resolve_take_path(shot, take_id)

    def _latest_take(self, shot, collection_name):
        return self._review_ctrl._latest_take(shot, collection_name)

    def _save_checkpoint(self, completed_scene_idx: int = -1):
        return self._checkpoint._save_checkpoint(completed_scene_idx)

    def _ensure_scene_audio(self, scene, characters):
        return None

    # -- ReviewControllerHost surface --
    def _find_take(self, shot, take_id):
        return self._shot_ctrl._find_take(shot, take_id)

    def _mutate_shot(self, shot_id, mutator, timeout: float = 10):
        return self._shot_ctrl._mutate_shot(shot_id, mutator, timeout)

    def resume(self):
        self._lifecycle.resume()


def _make_project(tmpdir: str, characters_in_frame: list) -> dict:
    """Minimal valid project dict with one scene + one shot.

    Shot fields copied verbatim from test_cross_controller._sample_project to
    satisfy Project.model_validate.
    """
    return {
        "id": "test_identity_project",
        "global_settings": {"quality_tier": "production"},
        "scenes": [
            {
                "id": "scene_1",
                "shots": [
                    {
                        "id": "shot_1",
                        "plan_status": "approved",
                        "characters_in_frame": characters_in_frame,
                        "keyframe_takes": [],
                        "motion_takes": [],
                        "postprocess_variants": [],
                        "approved_keyframe_take_id": "",
                        "approved_final_take_id": "",
                    },
                ],
            }
        ],
        "characters": [],
        "locations": [],
    }


def _build_host(tmp_path, secondary_chars, characters_in_frame):
    """Construct a _WiredHost with StubContinuity wired in."""
    project = _make_project(str(tmp_path), characters_in_frame)
    core = _FakeCore(project, str(tmp_path))
    lifecycle = NullLifecycle()
    runstate = RunState()
    host = _WiredHost(core, lifecycle, runstate)
    # Set continuity AFTER constructing _WiredHost (FakeCore.__init__ sets it to None).
    # ShotController.continuity is a property proxying self._core.continuity,
    # so setting core.continuity is sufficient.
    core.continuity = StubContinuity(secondary_chars)
    return host


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """Record generate_ai_broll kwargs; return a fake success."""
    box = {}

    def fake_broll(prompt, output_filename, **kwargs):
        box["kwargs"] = kwargs
        open(output_filename, "wb").close()  # satisfy the exists() guard
        from phase_c_assembly import ImageGenResult
        return ImageGenResult(output_filename, "FLUX_KONTEXT")

    monkeypatch.setattr("cinema.shots.controller.generate_ai_broll", fake_broll)
    return box


@pytest.fixture
def _stub_validator(monkeypatch):
    """Stub phase_c_vision._get_shared_validator — validation runs on the success path."""

    class _FakeValidateResult:
        def __init__(self, score=0.8):
            self.overall_score = score
            self.passed = True
            self.character_results = {}

    class _FakeValidator:
        def validate_image(self, *args, **kwargs):
            # Discriminating per-char scores: with a uniform return, a per-char
            # loop that scored the SAME face twice would be invisible.
            if kwargs.get("character_id") == "char_b":
                return _FakeValidateResult(0.55)
            return _FakeValidateResult()

    monkeypatch.setattr("phase_c_vision._get_shared_validator", lambda: _FakeValidator())


@pytest.fixture
def controller_one_char(monkeypatch, tmp_path, captured, _stub_validator):
    """Host/controller with a single-character shot (no secondaries)."""
    # Monkeypatch PROJECTS_DIR so _mutate_shot disk I/O targets tmp_path
    proj_root = str(tmp_path / "projects")
    os.makedirs(proj_root, exist_ok=True)
    host = _build_host(tmp_path, secondary_chars=[], characters_in_frame=["char_a"])
    # Write project JSON to disk so mutate_project can load it
    project = host._core.project
    proj_dir = os.path.join(proj_root, project["id"])
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "project.json"), "w") as f:
        json.dump(project, f)
    monkeypatch.setattr(dpm, "PROJECTS_DIR", proj_root)
    return host._shot_ctrl


@pytest.fixture
def controller_two_chars(monkeypatch, tmp_path, captured, _stub_validator):
    """Host/controller with a two-character shot (char_b as secondary)."""
    proj_root = str(tmp_path / "projects")
    os.makedirs(proj_root, exist_ok=True)
    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "multi_angle_refs": ["/r/b1.jpg"], "identity_anchor": "anchor b"}]
    # char_c is IN FRAME but unregistered (no secondary entry) — it must land
    # unconditioned and NEVER be scored (spec §6 AC3's negative invariant).
    host = _build_host(tmp_path, secondary_chars=secondary,
                       characters_in_frame=["char_a", "char_b", "char_c"])
    project = host._core.project
    proj_dir = os.path.join(proj_root, project["id"])
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "project.json"), "w") as f:
        json.dump(project, f)
    monkeypatch.setattr(dpm, "PROJECTS_DIR", proj_root)
    return host._shot_ctrl


def _latest_keyframe_take(controller, shot_id):
    for scene in controller.project["scenes"]:
        for shot in scene["shots"]:
            if shot["id"] == shot_id:
                return shot["keyframe_takes"][-1]
    raise AssertionError(f"no keyframe take on {shot_id}")


def test_single_char_take_metadata_and_kwargs_unchanged(controller_one_char, captured):
    res = controller_one_char.generate_keyframe_take("scene_1", "shot_1")
    assert res["success"]
    take = _latest_keyframe_take(controller_one_char, "shot_1")
    assert take["metadata"]["identity_strategy"]["mechanism_tag"] == "PRIMARY_ONLY"
    assert take["metadata"]["mechanism_actually_used"] == "FLUX_KONTEXT"
    # exact same kwargs today's code sends — zero regression
    assert captured["kwargs"]["char_lora_path"] is None
    assert captured["kwargs"]["char_lora_strength"] is None
    assert captured["kwargs"]["secondary_char_refs"] is None


def test_two_char_take_promises_kontext_multi_and_forwards_refs(
        controller_two_chars, captured):
    controller_two_chars.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_two_chars, "shot_1")
    md = take["metadata"]["identity_strategy"]
    assert md["mechanism_tag"] == "KONTEXT_MULTI_CHAR"
    sent = captured["kwargs"]["secondary_char_refs"]
    assert [c["char_id"] for c in sent] == ["char_b"]
    # V-5: the VALUE survives the to_dict chain (key-presence alone would pass
    # even if a serialization bug emptied the list)
    assert sent[0]["multi_angle_refs"] == ["/r/b1.jpg"]
    # V-2: derived actual — multi-char emission on a successful Kontext call
    assert take["metadata"]["mechanism_actually_used"] == "FLUX_KONTEXT_MULTI_CHAR"


# ---------------------------------------------------------------------------
# Task 9: per-character keyframe validation (identity_per_char)
# ---------------------------------------------------------------------------

def test_identity_per_char_written_for_conditioned_only(controller_two_chars, captured):
    controller_two_chars.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_two_chars, "shot_1")
    per_char = take["metadata"]["identity_per_char"]
    # exact discriminating values — proves each char was scored against its OWN
    # ref, and the unregistered in-frame char_c was NEVER scored (AC3 negative)
    assert per_char == {"char_a": 0.8, "char_b": 0.55}
    assert "char_c" not in per_char
    assert take["metadata"]["identity_strategy"]["unconditioned_chars"] == ["char_c"]
    assert take["metadata"]["identity_score"] == per_char["char_a"]  # scalar = primary, unchanged


def test_single_char_identity_per_char_pins_scalar_convention(
        controller_one_char, captured):
    """INFO-3 pin: a single-char shot gets identity_per_char == {primary: scalar}
    and the identity_score scalar itself is byte-unchanged."""
    controller_one_char.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_one_char, "shot_1")
    assert take["metadata"]["identity_per_char"] == \
        {"char_a": take["metadata"]["identity_score"]}


# ---------------------------------------------------------------------------
# Task 1 (slice 2): CharIdentitySpec per-char LoRA fields + MAX_TIER_MULTI_LORA
# ---------------------------------------------------------------------------

def test_char_spec_lora_fields_default_none_and_serialize():
    s = CharIdentitySpec(char_id="char_b", reference="/r/b.jpg",
                         fidelity="lora", lora_path="/l/b.safetensors",
                         lora_strength=0.55, trigger="TOKman")
    d = s.to_dict()
    assert d["lora_path"] == "/l/b.safetensors"
    assert d["lora_strength"] == 0.55
    assert d["trigger"] == "TOKman"
    # defaults stay None and serialize (Kontext-tier specs carry them as None)
    bare = CharIdentitySpec(char_id="c", reference="/r/c.jpg").to_dict()
    assert bare["lora_path"] is None and bare["trigger"] is None


def test_strategy_carries_primary_trigger_and_multi_lora_tag_importable():
    from cinema.shots.strategy import MAX_TIER_MULTI_LORA
    s = IdentityStrategy(mechanism_tag=MAX_TIER_MULTI_LORA,
                         primary_char_id="char_a", char_lora_trigger="TOKwoman")
    assert s.char_lora_trigger == "TOKwoman"
    json.dumps(s.to_metadata_dict())  # stays JSON-safe


# ---------------------------------------------------------------------------
# Task 4 (slice 2): controller integration — max-tier kwarg forwarding
# ---------------------------------------------------------------------------

@pytest.fixture
def controller_two_chars_max(monkeypatch, tmp_path, captured, _stub_validator):
    """Host/controller with a two-character shot, quality_tier=max.

    Like controller_two_chars but global_settings carries quality_tier: "max".
    No LoRA registered for either char — char_lora_trigger will be None
    (the slice-2 accountability pin: the trigger flows through even when absent).
    """
    proj_root = str(tmp_path / "projects")
    os.makedirs(proj_root, exist_ok=True)
    secondary = [{"char_id": "char_b", "reference": "/r/b.jpg",
                  "multi_angle_refs": ["/r/b1.jpg"], "identity_anchor": "anchor b"}]
    host = _build_host(tmp_path, secondary_chars=secondary,
                       characters_in_frame=["char_a", "char_b", "char_c"])
    # Override global_settings to max tier
    host._core.project["global_settings"]["quality_tier"] = "max"
    project = host._core.project
    proj_dir = os.path.join(proj_root, project["id"])
    os.makedirs(proj_dir, exist_ok=True)
    with open(os.path.join(proj_dir, "project.json"), "w") as f:
        json.dump(project, f)
    monkeypatch.setattr(dpm, "PROJECTS_DIR", proj_root)
    return host._shot_ctrl


def test_two_char_max_tier_strategy_tag_and_kwargs(
        controller_two_chars_max, captured):
    """MAX_TIER_MULTI_LORA is set; char_lora_trigger kwarg flows to generate_ai_broll;
    identity_per_char covers both conditioned chars (slice-2 accountability pin)."""
    controller_two_chars_max.generate_keyframe_take("scene_1", "shot_1")
    take = _latest_keyframe_take(controller_two_chars_max, "shot_1")

    # Strategy promise
    md = take["metadata"]["identity_strategy"]
    assert md["mechanism_tag"] == "MAX_TIER_MULTI_LORA"

    # char_lora_trigger kwarg must be present in the captured call
    # (no trigger registered in fixture → value is None, but key must exist)
    assert "char_lora_trigger" in captured["kwargs"], (
        f"generate_ai_broll must receive char_lora_trigger kwarg; "
        f"got: {list(captured['kwargs'].keys())}"
    )
    assert captured["kwargs"]["char_lora_trigger"] is None

    # identity_per_char covers both conditioned chars (AC3 negative: char_c absent)
    per_char = take["metadata"]["identity_per_char"]
    assert "char_a" in per_char
    assert "char_b" in per_char
    assert "char_c" not in per_char

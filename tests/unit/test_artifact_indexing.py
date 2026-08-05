from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cinema import artifact_indexing
from cinema.artifact_versions import (
    ArtifactValidationError,
    ArtifactVersionStore,
    DISTRIBUTION_CLIENT,
    DISTRIBUTION_INTERNAL,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return relative


def _store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_id: str = "project_a"):
    root = tmp_path / project_id
    root.mkdir()
    store = ArtifactVersionStore(project_id, root)
    monkeypatch.setattr(
        artifact_indexing.ArtifactVersionStore,
        "for_project",
        staticmethod(lambda requested_id, **_kwargs: store),
    )
    return root, store


def _snapshot(project_id: str, shot: dict) -> dict:
    return {
        "id": project_id,
        "name": "Artifact indexing test",
        "global_settings": {"aspect_ratio": "16:9"},
        "scenes": [{"id": "scene_a", "shots": [shot]}],
    }


def test_controller_repairs_pending_take_without_entering_transform_dispatch(
    tmp_path: Path,
) -> None:
    from cinema.shots.controller import ShotController

    project_id = "project_pending"
    root = tmp_path / project_id
    output = root / "shots" / "shot_a" / "outputs" / "take_pending.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"accepted-postprocess")
    take = {
        "id": "take_pending",
        "kind": "postprocess",
        "path": output.relative_to(root).as_posix(),
        "metadata": {
            "action": "upscale",
            "artifact_versioning_pending": True,
        },
    }
    shot = {
        "id": "shot_a",
        "keyframe_takes": [],
        "performance_takes": [],
        "motion_takes": [],
        "postprocess_variants": [take],
    }
    scene = {"id": "scene_a", "shots": [shot]}
    project = {
        "id": project_id,
        "name": "Pending recovery",
        "global_settings": {},
        "scenes": [scene],
    }
    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    lifecycle = MagicMock()
    runstate = SimpleNamespace(shot_results={}, scene_clips={})
    core = SimpleNamespace(
        project=project,
        project_dir=str(root),
        continuity=MagicMock(),
        cost_tracker=MagicMock(),
        export_dir=str(root / "exports"),
    )
    controller = ShotController(core, lifecycle, host, runstate)

    def mutate(_shot_id, mutator, timeout=10):
        del timeout
        return mutator(scene, shot).value

    controller._mutate_shot = mutate

    with patch(
        "cinema.artifact_indexing.record_take_version",
        side_effect=RuntimeError("ledger temporarily unavailable"),
    ):
        _updated, error = controller._finalize_take_artifact_version(
            "shot_a", "postprocess", take,
        )
    assert error is not None and error["code"] == "artifact_version_pending"
    assert take["metadata"]["artifact_versioning_pending"] is True

    with patch("phase_c_ffmpeg.adjust_speed") as transform:
        recovered = controller.apply_correction(
            "shot_a", "speed", params={"factor": 2.0},
        )

    transform.assert_not_called()
    assert recovered["success"] is True
    assert recovered["artifact_recovered"] is True
    assert "artifact_versioning_pending" not in take["metadata"]
    assert take["metadata"]["artifact_version_id"].startswith("av-")
    history = ArtifactVersionStore(project_id, root).history()
    assert [record["logical_name"] for record in history] == [
        "shots/shot_a/postprocess/take_pending"
    ]


def test_record_take_uses_actual_winner_and_hashes_only_proven_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    source_path = _write(root, "shots/shot_a/source.jpg", b"source")
    parent_path = _write(root, "shots/shot_a/parent.mp4", b"parent")
    audio_path = _write(root, "temp/performance.mp3", b"audio")
    identity_path = _write(root, "assets/identity.png", b"identity")
    performance_path = _write(root, "shots/shot_a/performance.mp4", b"performance")
    storyboard_path = _write(root, "temp/storyboard.mp4", b"storyboard")
    output_path = _write(root, "shots/shot_a/take_motion.mp4", b"accepted-video")
    shot = {
        "id": "shot_a",
        "keyframe_takes": [{"id": "take_source", "path": source_path}],
        "performance_takes": [{"id": "take_performance", "path": performance_path}],
        "approved_performance_take_id": "take_performance",
        "motion_takes": [{"id": "take_parent", "path": parent_path}],
        "postprocess_variants": [],
    }
    snapshot = _snapshot("project_a", shot)
    take = {
        "id": "take_motion",
        "kind": "motion",
        "path": output_path,
        "source_take_id": "take_source",
        "parent_take_id": "take_parent",
        "metadata": {
            "target_api": "VEO_NATIVE",
            "shot_type": "wide",
            "audio_path": audio_path,
            "storyboard_source": storyboard_path,
            "api_key": "must-not-be-recorded",
            "identity_strategy": {
                "mechanism_tag": "PRIMARY_ONLY",
                "primary_char_id": "char_a",
                "conditioned_chars": [
                    {
                        "char_id": "char_a",
                        "reference": identity_path,
                        "identity_anchor": "private descriptive text",
                    },
                    {
                        "char_id": "char_external",
                        "reference": "/etc/passwd",
                    },
                ],
            },
        },
        "cascade_metadata": {
            "engine": "LTX",
            "model": "ltx-2-3-pro",
            "seed": 73,
            "duration_s": 8,
            "resolution": "1080p",
            "api_key": "also-not-recorded",
        },
    }

    record = artifact_indexing.record_take_version(
        "project_a",
        "shot_a",
        "motion",
        take,
        project_snapshot=snapshot,
    )

    assert record["logical_name"] == "shots/shot_a/motion/take_motion"
    assert record["distribution_class"] == DISTRIBUTION_INTERNAL
    assert record["provider"] == "LTX"
    assert record["model"] == "ltx-2-3-pro"
    assert record["seed"] == 73
    assert record["sha256"] == _sha(b"accepted-video")
    assert record["source_hashes"] == {
        "identity_reference:0": _sha(b"identity"),
        "dispatch_performance_reference": _sha(b"performance"),
        "parent_take": _sha(b"parent"),
        "performance_audio": _sha(b"audio"),
        "project_snapshot": _sha(
            json.dumps(
                snapshot,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ),
        "source_take": _sha(b"source"),
        "storyboard_source": _sha(b"storyboard"),
    }
    assert set(record["dependency_hashes"]) == {
        "cinema/shots/controller.py",
        "phase_c_ffmpeg.py",
    }
    assert record["parameters"]["take_recipe"]["target_api"] == "VEO_NATIVE"
    assert record["parameters"]["provider_recipe"] == {
        "duration_s": 8,
        "resolution": "1080p",
    }
    identity_recipe = record["parameters"]["take_recipe"]["identity_strategy"]
    assert identity_recipe == {
        "mechanism_tag": "PRIMARY_ONLY",
        "primary_char_id": "char_a",
        "conditioned_char_ids": ["char_a", "char_external"],
    }
    assert "reference" not in json.dumps(record["parameters"])
    assert "api_key" not in json.dumps(record["parameters"])
    assert record["reproducibility"]["status"] == "provider_replay_only"
    assert record["reproducibility"]["bit_exact"] is False


def test_requested_motion_route_is_not_mislabeled_as_actual_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    output_path = _write(root, "shots/shot_a/no-winner-metadata.mp4", b"legacy-video")
    snapshot = _snapshot(
        "project_a",
        {
            "id": "shot_a",
            "keyframe_takes": [],
            "performance_takes": [],
            "motion_takes": [],
            "postprocess_variants": [],
        },
    )
    take = {
        "id": "take_legacy",
        "kind": "motion",
        "path": output_path,
        "metadata": {
            "target_api": "RUNWAY_GEN4",
            "shot_type": "wide",
            "model": "requested-model-is-not-winner-evidence",
        },
    }

    record = artifact_indexing.record_take_version(
        "project_a",
        "shot_a",
        "motion",
        take,
        project_snapshot=snapshot,
    )

    assert record["provider"] is None
    assert record["model"] is None
    assert record["seed"] is None
    assert record["parameters"]["take_recipe"]["target_api"] == "RUNWAY_GEN4"
    assert record["reproducibility"]["status"] == "output_hash_only"


def test_performance_version_hashes_the_exact_resolved_driving_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    keyframe_path = _write(root, "shots/shot_a/keyframe.jpg", b"keyframe")
    driving_path = _write(root, "shots/shot_a/driving.mp4", b"mode-b-driving")
    output_path = _write(root, "shots/shot_a/performance.mp4", b"performance")
    snapshot = _snapshot(
        "project_a",
        {
            "id": "shot_a",
            "keyframe_takes": [{"id": "take_keyframe", "path": keyframe_path}],
            "performance_takes": [],
            "motion_takes": [],
            "postprocess_variants": [],
        },
    )
    take = {
        "id": "take_performance",
        "kind": "performance",
        "path": output_path,
        "source_take_id": "take_keyframe",
        "metadata": {
            "engine": "ACT_ONE",
            "driving_source": "tts_auto",
            "driving_provider": "sadtalker",
            "driving_video_path": driving_path,
        },
    }

    record = artifact_indexing.record_take_version(
        "project_a",
        "shot_a",
        "performance",
        take,
        project_snapshot=snapshot,
    )

    assert record["provider"] == "ACT_ONE"
    assert record["source_hashes"]["source_take"] == _sha(b"keyframe")
    assert record["source_hashes"]["performance_driving_input"] == _sha(
        b"mode-b-driving"
    )
    assert driving_path not in json.dumps(record["parameters"])


def test_postprocess_recipe_hashes_base_and_lut_without_persisting_lut_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    source_path = _write(root, "shots/shot_a/base.mp4", b"base-video")
    lut_path = _write(root, "assets/grade.cube", b"lut")
    output_path = _write(root, "shots/shot_a/graded.mp4", b"graded-video")
    snapshot = _snapshot(
        "project_a",
        {
            "id": "shot_a",
            "keyframe_takes": [],
            "performance_takes": [],
            "motion_takes": [{"id": "take_base", "path": source_path}],
            "postprocess_variants": [],
        },
    )
    take = {
        "id": "take_graded",
        "kind": "postprocess",
        "path": output_path,
        "source_take_id": "take_base",
        "metadata": {
            "action": "color_grade",
            "params": {
                "preset": "cool_noir",
                "lut_path": lut_path,
                "target_resolution": "2160p",
                "password": "do-not-store",
            },
        },
    }

    record = artifact_indexing.record_take_version(
        "project_a",
        "shot_a",
        "postprocess",
        take,
        project_snapshot=snapshot,
    )

    assert record["provider"] is None
    assert record["model"] == "ffmpeg-color-grade"
    assert record["source_hashes"]["source_take"] == _sha(b"base-video")
    assert record["source_hashes"]["postprocess_lut"] == _sha(b"lut")
    assert record["parameters"]["take_recipe"]["params"] == {"preset": "cool_noir"}
    assert lut_path not in json.dumps(record["parameters"])
    assert "password" not in json.dumps(record["parameters"])
    assert set(record["dependency_hashes"]) == {
        "cinema/shots/controller.py",
        "phase_c_ffmpeg.py",
    }


def test_auxiliary_asset_retains_bytes_and_hashes_exact_generated_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    dialogue = _write(root, "temp/dialogue.mp3", b"dialogue-source")
    foley = _write(root, "temp/foley_scene_a.mp3", b"generated-foley")
    snapshot = _snapshot(
        "project_a",
        {
            "id": "shot_a",
            "keyframe_takes": [],
            "performance_takes": [],
            "motion_takes": [],
            "postprocess_variants": [],
        },
    )

    record = artifact_indexing.record_auxiliary_version(
        "project_a",
        "foley",
        "scene_a",
        foley,
        provider="stability",
        model="stable-audio-2",
        parameters={
            "prompt": "rain on glass",
            "duration": 30.0,
            "api_key": "must-not-be-recorded",
            "access_token": "must-not-be-recorded-access",
            "client_secret": "must-not-be-recorded-client",
            "openai_api_key": "must-not-be-recorded-openai",
            "x-api-key": "must-not-be-recorded-header",
            "fal_key": "must-not-be-recorded-fal",
        },
        source_paths={"dialogue_audio": dialogue},
        project_snapshot=snapshot,
    )

    assert record["logical_name"] == "assets/foley/scene_a"
    assert record["sha256"] == _sha(b"generated-foley")
    assert record["source_hashes"]["dialogue_audio"] == _sha(b"dialogue-source")
    assert record["parameters"] == {"duration": 30.0, "prompt": "rain on glass"}
    retained = root / record["object_path"]
    assert retained.read_bytes() == b"generated-foley"
    assert set(record["dependency_hashes"]) == {"audio/foley.py", "audio/effects.py"}


def test_final_master_is_client_deliverable_with_input_and_dependency_hashes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    final_path = _write(root, "exports/final_cinema.mp4", b"final-master")
    clip_a = _write(root, "shots/shot_a/a.mp4", b"clip-a")
    clip_b = _write(root, "shots/shot_b/b.mp4", b"clip-b")
    dialogue = _write(root, "temp/dialogue.mp3", b"dialogue")
    foley = _write(root, "temp/foley.mp3", b"foley")
    bgm = _write(root, "temp/bgm.mp3", b"music")
    _write(root, "exports/preview_scene_a.mp4", b"preview-not-an-input")
    snapshot = {
        "id": "project_a",
        "name": "Final",
        "global_settings": {"aspect_ratio": "16:9"},
        "scenes": [],
    }
    monkeypatch.setattr(artifact_indexing, "_tool_version_hash", lambda _name: "a" * 64)

    record = artifact_indexing.record_final_version(
        "project_a",
        final_path,
        [
            {
                "scene_id": "scene_a",
                "clips": [clip_a, clip_b],
                "audio": dialogue,
                "foley": [foley],
                "preview": "exports/preview_scene_a.mp4",
            }
        ],
        bgm,
        {
            "aspect_ratio": "16:9",
            "scene_transitions": True,
            "transition_duration": 0.5,
            "music_mood": "suspense",
            "color_grade_preset": "cool_noir",
            "api_key": "must-not-be-recorded",
            "unrelated": "not-an-assembly-setting",
        },
        project_snapshot=snapshot,
    )

    assert record["logical_name"] == "final/master"
    assert record["distribution_class"] == DISTRIBUTION_CLIENT
    assert record["media_type"] == "video/mp4"
    assert record["provider"] is None
    assert record["model"] == "ffmpeg-final-assembly"
    assert record["sha256"] == _sha(b"final-master")
    assert record["source_hashes"]["scene:0:clip:0"] == _sha(b"clip-a")
    assert record["source_hashes"]["scene:0:clip:1"] == _sha(b"clip-b")
    assert record["source_hashes"]["scene:0:dialogue"] == _sha(b"dialogue")
    assert record["source_hashes"]["scene:0:foley:0"] == _sha(b"foley")
    assert record["source_hashes"]["background_music"] == _sha(b"music")
    assert len(record["source_hashes"]) == 6
    assert record["dependency_hashes"]["ffmpeg -version"] == "a" * 64
    assert set(record["dependency_hashes"]) == {
        "cinema_pipeline.py",
        "phase_c_ffmpeg.py",
        "cinema/aspect.py",
        "ffmpeg -version",
    }
    assert record["parameters"]["source_scene_count"] == 1
    assert record["parameters"]["source_clip_count"] == 2
    assert record["parameters"]["fixed_recipe"]["bgm_volume"] == 0.12
    assert record["parameters"]["fixed_recipe"]["foley_volume"] == 0.20
    assert record["parameters"]["fixed_recipe"]["requested_loudnorm"] == {
        "target_i": -14.0,
        "target_lra": 11.0,
        "target_tp": -1.5,
    }
    assert record["parameters"]["assembly_settings"] == {
        "aspect_ratio": "16:9",
        "color_grade_preset": "cool_noir",
        "music_mood": "suspense",
        "scene_transitions": True,
        "transition_duration": 0.5,
    }
    assert "api_key" not in json.dumps(record["parameters"])
    assert "preview" not in record["source_hashes"]
    assert record["reproducibility"]["bit_exact"] is False


def test_validation_rejects_wrong_kind_snapshot_and_non_export_master(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, _ = _store(monkeypatch, tmp_path)
    take_path = _write(root, "shots/shot_a/frame.jpg", b"frame")
    snapshot = _snapshot("project_a", {"id": "shot_a"})

    with pytest.raises(ArtifactValidationError, match="kind does not match"):
        artifact_indexing.record_take_version(
            "project_a",
            "shot_a",
            "motion",
            {"id": "take_a", "kind": "keyframe", "path": take_path},
            project_snapshot=snapshot,
        )

    with pytest.raises(ArtifactValidationError, match="does not belong"):
        artifact_indexing.record_take_version(
            "project_a",
            "shot_a",
            "keyframe",
            {"id": "take_a", "kind": "keyframe", "path": take_path},
            project_snapshot={**snapshot, "id": "project_b"},
        )

    with pytest.raises(ArtifactValidationError, match="below exports"):
        artifact_indexing.record_final_version(
            "project_a",
            take_path,
            [],
            None,
            {},
            project_snapshot=snapshot,
        )

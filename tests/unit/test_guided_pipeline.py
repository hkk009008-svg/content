import os
import sys
import tempfile
import unittest
from unittest import mock


os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import phase_c_ffmpeg
import project_manager
from continuity_engine import CharacterContinuityTracker
from cinema_pipeline import CinemaPipeline


def _write_asset(path: str, contents: str = "asset"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(contents)


class GuidedPipelineTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._projects_dir_patch = mock.patch("domain.project_manager.PROJECTS_DIR", self._tmpdir.name)
        self._projects_dir_patch.start()
        self.addCleanup(self._projects_dir_patch.stop)

    def create_project_with_single_shot(self):
        project = project_manager.create_project("Guided Tool")
        scene = project_manager.make_scene("Scene 1")
        shot = project_manager.make_shot("A careful close shot", shot_id="shot_scene_1_0")
        scene["shots"] = [shot]
        scene["num_shots"] = 1
        project["scenes"] = [scene]
        project_manager.save_project(project)
        return project, scene, shot


class TestGuidedProjectLedger(GuidedPipelineTestCase):
    def test_normalize_project_schema_migrates_legacy_assets_into_take_records(self):
        project, scene, shot = self.create_project_with_single_shot()
        shot["id"] = "dup"
        legacy_image = os.path.join(project_manager.get_project_dir(project["id"]), "legacy.jpg")
        legacy_video = os.path.join(project_manager.get_project_dir(project["id"]), "legacy.mp4")
        _write_asset(legacy_image)
        _write_asset(legacy_video)
        shot["generated_image"] = legacy_image
        shot["generated_video"] = legacy_video
        shot["approved"] = True

        duplicate = project_manager.make_shot("Another angle", shot_id="dup")
        scene["shots"] = [shot, duplicate]
        scene["num_shots"] = 2
        project_manager.save_project(project)

        loaded = project_manager.load_project(project["id"])

        first, second = loaded["scenes"][0]["shots"]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(first["keyframe_takes"]), 1)
        self.assertEqual(len(first["motion_takes"]), 1)
        self.assertEqual(first["approved_keyframe_take_id"], first["keyframe_takes"][0]["id"])
        self.assertEqual(first["approved_final_take_id"], first["motion_takes"][0]["id"])

    def test_character_fragment_keeps_identity_out_of_prompt_details(self):
        project = project_manager.make_project("Continuity")
        project["characters"] = [
            project_manager.make_character("Mina", "Lead", reference_images=[], voice_id="", ip_adapter_weight=0.85)
        ]
        project["characters"][0]["id"] = "char_mina"
        project["characters"][0]["physical_traits"] = "green eyes, black hair, heart-shaped face"

        tracker = CharacterContinuityTracker(project)
        tracker.log_appearance("char_mina", wardrobe="red coat", position="frame left")

        fragment = tracker.build_character_prompt_fragment("char_mina", spatial_position="frame left")

        self.assertIn("approved reference identity", fragment)
        self.assertIn("red coat", fragment)
        self.assertNotIn("black hair", fragment)
        self.assertNotIn("green eyes", fragment)


class TestGuidedStageCommands(GuidedPipelineTestCase):
    def test_stage_commands_reject_missing_prerequisites(self):
        project, scene, shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])

        keyframe_result = pipeline.generate_keyframe_take(scene["id"], shot["id"])
        motion_result = pipeline.generate_motion_take(scene["id"], shot["id"])
        assembly_result = pipeline.assemble_approved_takes()
        pipeline.approve_shot_plan(shot["id"], approved=True)
        missing_keyframe_result = pipeline.generate_motion_take(scene["id"], shot["id"])

        self.assertFalse(keyframe_result["success"])
        self.assertIn("Shot plan must be approved", keyframe_result["error"])
        self.assertFalse(motion_result["success"])
        self.assertIn("Shot plan must be approved", motion_result["error"])
        self.assertFalse(missing_keyframe_result["success"])
        self.assertIn("Approved keyframe required", missing_keyframe_result["error"])
        self.assertFalse(assembly_result["success"])
        self.assertIn("Final approvals missing", assembly_result["error"])

    def test_correction_creates_new_postprocess_take_instead_of_overwriting(self):
        project, _scene, shot = self.create_project_with_single_shot()
        keyframe_path = os.path.join(project_manager.get_project_dir(project["id"]), "shots", shot["id"], "outputs", "keyframe.jpg")
        motion_path = os.path.join(project_manager.get_project_dir(project["id"]), "shots", shot["id"], "outputs", "motion.mp4")
        _write_asset(keyframe_path)
        _write_asset(motion_path)

        keyframe_take = project_manager.make_take("keyframe", path=keyframe_path)
        motion_take = project_manager.make_take("motion", path=motion_path, source_take_id=keyframe_take["id"])
        shot.update({
            "plan_status": "approved",
            "keyframe_takes": [keyframe_take],
            "approved_keyframe_take_id": keyframe_take["id"],
            "motion_takes": [motion_take],
            "approved_motion_take_id": motion_take["id"],
            "approved_final_take_id": motion_take["id"],
        })
        project_manager.save_project(project)

        def fake_color_grade(video_path, out_path, preset="warm_cinema", lut_path=None):
            self.assertEqual(video_path, motion_path)
            _write_asset(out_path, "graded")
            return out_path

        with mock.patch.object(phase_c_ffmpeg, "apply_color_grade", side_effect=fake_color_grade):
            pipeline = CinemaPipeline(project["id"])
            result = pipeline.apply_correction(shot["id"], "color_grade", {"preset": "cool_noir"}, take_id=motion_take["id"])

        self.assertTrue(result["success"])

        reloaded = project_manager.load_project(project["id"])
        updated_shot = reloaded["scenes"][0]["shots"][0]
        self.assertEqual(len(updated_shot["motion_takes"]), 1)
        self.assertEqual(len(updated_shot["postprocess_variants"]), 1)
        variant = updated_shot["postprocess_variants"][0]
        self.assertNotEqual(variant["id"], motion_take["id"])
        self.assertEqual(variant["source_take_id"], motion_take["id"])
        self.assertEqual(updated_shot["motion_takes"][0]["path"], motion_path)

    def test_reload_rebuilds_take_state_from_persisted_project_data(self):
        project, _scene, shot = self.create_project_with_single_shot()
        keyframe_path = os.path.join(project_manager.get_project_dir(project["id"]), "shots", shot["id"], "outputs", "keyframe.jpg")
        motion_path = os.path.join(project_manager.get_project_dir(project["id"]), "shots", shot["id"], "outputs", "motion.mp4")
        _write_asset(keyframe_path)
        _write_asset(motion_path)

        keyframe_take = project_manager.make_take("keyframe", path=keyframe_path)
        motion_take = project_manager.make_take("motion", path=motion_path, source_take_id=keyframe_take["id"])
        shot.update({
            "plan_status": "approved",
            "keyframe_takes": [keyframe_take],
            "approved_keyframe_take_id": keyframe_take["id"],
            "motion_takes": [motion_take],
            "approved_motion_take_id": motion_take["id"],
            "approved_final_take_id": motion_take["id"],
        })
        project_manager.save_project(project)

        pipeline = CinemaPipeline(project["id"])
        manifest = pipeline._rebuild_review_clips()
        state = pipeline.get_state()

        self.assertEqual(manifest[shot["id"]]["take_id"], motion_take["id"])
        self.assertEqual(manifest[shot["id"]]["video"], motion_path)
        self.assertEqual(state["gate_status"]["plans_approved"], 1)
        self.assertEqual(state["gate_status"]["keyframes_approved"], 1)
        self.assertEqual(state["gate_status"]["finals_approved"], 1)


class TestEnsureSceneFoley(GuidedPipelineTestCase):
    """Unit tests for CinemaPipeline._ensure_scene_foley wiring."""

    def _make_scene_with_foley(self, scene_id: str = "scene_1") -> dict:
        """Minimal scene dict with two shots carrying scene_foley descriptors."""
        return {
            "id": scene_id,
            "shots": [
                {"id": "shot_1", "scene_foley": "rain"},
                {"id": "shot_2", "scene_foley": "rain"},   # duplicate — should deduplicate
                {"id": "shot_3", "scene_foley": "crowd"},
            ],
        }

    def test_ensure_scene_foley_returns_path_and_populates_state(self):
        """generate_stability_foley returns a path → scene_foley dict + foley_audio_paths updated."""
        project, _scene, _shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        scene = self._make_scene_with_foley("scene_foley_test")
        foley_output = os.path.join(pipeline.temp_dir, "foley_scene_foley_test.mp3")

        def fake_generate(prompt, out_path, duration=5.0, **kwargs):
            # Simulate successful generation by writing a file
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(b"fake_foley_audio")
            return out_path

        with mock.patch("audio.foley.generate_stability_foley", side_effect=fake_generate):
            result = pipeline._ensure_scene_foley(scene)

        self.assertEqual(result, foley_output)
        self.assertEqual(pipeline.scene_foley.get("scene_foley_test"), foley_output)
        self.assertIn(foley_output, pipeline._runstate.foley_audio_paths)

    def test_ensure_scene_foley_deduplicates_descriptors(self):
        """Duplicate scene_foley strings across shots are collapsed to one entry."""
        project, _scene, _shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        scene = self._make_scene_with_foley("scene_dedup")
        captured_prompts: list[str] = []

        def fake_generate(prompt, out_path, duration=5.0, **kwargs):
            captured_prompts.append(prompt)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(b"x")
            return out_path

        with mock.patch("audio.foley.generate_stability_foley", side_effect=fake_generate):
            pipeline._ensure_scene_foley(scene)

        # Should have been called exactly once
        self.assertEqual(len(captured_prompts), 1)
        # The descriptor passed to generate should NOT contain duplicate "rain"
        # (deduplicated to: "rain, crowd")
        prompt_used = captured_prompts[0]
        self.assertIn("rain", prompt_used.lower())
        self.assertIn("crowd", prompt_used.lower())

    def test_ensure_scene_foley_returns_empty_on_failure(self):
        """generate_stability_foley returning None → _ensure_scene_foley returns ''."""
        project, _scene, _shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        scene = self._make_scene_with_foley("scene_fail")

        with mock.patch("audio.foley.generate_stability_foley", return_value=None):
            result = pipeline._ensure_scene_foley(scene)

        self.assertEqual(result, "")
        self.assertNotIn("scene_fail", pipeline.scene_foley)
        self.assertEqual(pipeline._runstate.foley_audio_paths, [])

    def test_build_scene_packages_populates_foley_list(self):
        """foley field in scene_packages is [path] when foley succeeds, [] when it fails."""
        project, _scene, _shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])

        # _build_scene_packages normally requires mp4 files; mock _ensure_scene_foley
        # and the scene_audio helper so we can focus on foley field population.
        with mock.patch.object(pipeline, "_ensure_scene_audio", return_value=None), \
             mock.patch.object(pipeline, "_ensure_scene_foley", return_value="/tmp/foley.mp3"):
            # Also mock _resolve_take_path so no-clip scenes don't add to missing_shots
            with mock.patch.object(pipeline, "_resolve_take_path", return_value=None):
                packages, _missing = pipeline._build_scene_packages(project)

        for pkg in packages:
            self.assertEqual(pkg["foley"], ["/tmp/foley.mp3"])

        # Now test degraded path: foley returns ""
        with mock.patch.object(pipeline, "_ensure_scene_audio", return_value=None), \
             mock.patch.object(pipeline, "_ensure_scene_foley", return_value=""), \
             mock.patch.object(pipeline, "_resolve_take_path", return_value=None):
            packages_empty, _ = pipeline._build_scene_packages(project)

        for pkg in packages_empty:
            self.assertEqual(pkg["foley"], [])


if __name__ == "__main__":
    unittest.main()

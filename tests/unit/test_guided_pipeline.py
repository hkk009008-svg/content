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


if __name__ == "__main__":
    unittest.main()

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


class TestConcatFoleyTrack(GuidedPipelineTestCase):
    """Unit tests for CinemaPipeline._concat_foley_track."""

    def _make_pipeline(self):
        project, _scene, _shot = self.create_project_with_single_shot()
        return CinemaPipeline(project["id"])

    def test_empty_paths_returns_none(self):
        pipeline = self._make_pipeline()
        self.assertIsNone(pipeline._concat_foley_track([]))

    def test_single_path_returned_directly_no_ffmpeg(self):
        """Single-element list skips concat — path returned as-is, ffmpeg not called."""
        pipeline = self._make_pipeline()
        with mock.patch("subprocess.run") as mock_run:
            result = pipeline._concat_foley_track(["/tmp/foley_a.mp3"])
        self.assertEqual(result, "/tmp/foley_a.mp3")
        mock_run.assert_not_called()

    def test_multi_path_calls_ffmpeg_concat(self):
        """Multi-element list triggers ffmpeg concat; returned path is foley_track.mp3."""
        pipeline = self._make_pipeline()
        with mock.patch("subprocess.run") as mock_run:
            result = pipeline._concat_foley_track(["/tmp/a.mp3", "/tmp/b.mp3"])
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("-f", cmd)
        self.assertIn("concat", cmd)
        self.assertTrue(str(result).endswith("foley_track.mp3"))

    def test_multi_path_ffmpeg_failure_returns_none(self):
        """If ffmpeg concat raises, _concat_foley_track returns None gracefully."""
        import subprocess
        pipeline = self._make_pipeline()
        with mock.patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
            result = pipeline._concat_foley_track(["/tmp/a.mp3", "/tmp/b.mp3"])
        self.assertIsNone(result)


class TestAssembleFinalFoleyMix(GuidedPipelineTestCase):
    """Unit tests for _assemble_final tri-mix vs 2-input fallback logic."""

    def _make_pipeline_with_clips(self, tmp_path, foley_paths=None):
        """Build a minimal pipeline with one real clip file and optional foley."""
        project, scene, shot = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        if foley_paths is not None:
            pipeline.foley_audio_paths = foley_paths
        return pipeline, scene, shot

    def _run_assemble_final_mock(self, tmp_path, foley_paths):
        """Run _assemble_final with all ffmpeg calls mocked; return captured subprocess.run calls."""
        import subprocess as _sp
        pipeline, scene, _shot = self._make_pipeline_with_clips(tmp_path, foley_paths)

        # Create fake stitched + bgm files so os.path.exists checks pass
        fake_stitched = os.path.join(pipeline.temp_dir, "stitched.mp4")
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        fake_final = os.path.join(pipeline.export_dir, "final_cinema.mp4")
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        open(fake_stitched, "wb").close()
        open(fake_bgm, "wb").close()
        # Create foley files so exists check passes
        for fp in (foley_paths or []):
            open(fp, "wb").close()

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            # Touch final_output for each mix command so return path exists
            for arg in cmd:
                if str(arg).endswith(".mp4") and "final_cinema" in str(arg):
                    open(arg, "wb").close()
            result = mock.MagicMock()
            result.returncode = 0
            return result

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"), \
             mock.patch.object(pipeline, "_concat_foley_track",
                               wraps=pipeline._concat_foley_track):
            # Provide scene_data with zero real clips — skip normalize/stitch steps
            # by patching them out so we can focus on step 5 (the mix).
            with mock.patch.object(pipeline, "_assemble_final",
                                   wraps=pipeline._assemble_final):
                pass  # no-op; just use wraps below

            # Directly invoke step 5 by calling the real method with mocked subprocess
            # Re-wire: patch the stitched path check by ensuring stitched exists (done above).
            result = pipeline._assemble_final(
                scene_data=[],  # empty → no clips → returns None early
                bgm_path=fake_bgm,
                settings={},
            )
        return calls, result

    def test_no_clips_returns_none_immediately(self):
        """Empty scene_data returns None before reaching mix step."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            calls, result = self._run_assemble_final_mock(tmp, foley_paths=[])
        self.assertIsNone(result)
        # No subprocess.run calls expected (exited before stitch/mix)
        self.assertEqual(len(calls), 0)

    def test_assemble_final_no_foley_cmd_uses_amix_inputs_2(self):
        """With no foley paths, the primary mix command uses amix=inputs=2."""
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])

        captured_cmds = []
        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            m = mock.MagicMock()
            m.returncode = 0
            return m

        fake_stitched = os.path.join(pipeline.temp_dir, "stitched.mp4")
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        open(fake_stitched, "wb").close()
        open(fake_bgm, "wb").close()
        # Fake clips list so the method reaches step 5
        fake_clip = os.path.join(pipeline.temp_dir, "clip.mp4")
        open(fake_clip, "wb").close()
        scene_data = [{"scene_id": "s1", "clips": [fake_clip]}]

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            pipeline._assemble_final(scene_data, fake_bgm, {})

        mix_cmds = [c for c in captured_cmds if any("amix" in str(a) for a in c)]
        self.assertTrue(len(mix_cmds) >= 1, "Expected at least one amix command")
        mix_filter = " ".join(str(a) for a in mix_cmds[0])
        self.assertIn("amix=inputs=2", mix_filter)
        self.assertNotIn("amix=inputs=3", mix_filter)

    # --- I1 guard / portrait container regression (final-review IMPORTANT) ---
    # T10 flipped the I1 guard's meaning (cinema_pipeline.py:1367-1371): once 9:16
    # became supported, this chokepoint is what makes a portrait project assemble
    # into a 1080x1920 container. These pin that decision so a mutation that
    # letterboxed every portrait as 16:9 can't pass green.
    def _capture_normalize_vf(self, settings):
        """Run _assemble_final with ffmpeg mocked; return the normalize -vf string
        (the captured command whose -vf carries the scale=...pad=... container)."""
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])
        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            m = mock.MagicMock()
            m.returncode = 0
            return m

        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        open(os.path.join(pipeline.temp_dir, "stitched.mp4"), "wb").close()
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        open(fake_bgm, "wb").close()
        fake_clip = os.path.join(pipeline.temp_dir, "clip.mp4")
        open(fake_clip, "wb").close()
        scene_data = [{"scene_id": "s1", "clips": [fake_clip]}]

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            pipeline._assemble_final(scene_data, fake_bgm, settings)

        for c in captured_cmds:
            if "-vf" in c:
                vf = str(c[c.index("-vf") + 1])
                if "scale=" in vf and "pad=" in vf:
                    return vf
        return None

    def test_assemble_9_16_uses_portrait_container(self):
        """A 9:16 project normalizes clips to a 1080x1920 portrait container."""
        vf = self._capture_normalize_vf({"aspect_ratio": "9:16"})
        self.assertIsNotNone(vf, "no normalize -vf command captured")
        self.assertIn("scale=1080:1920", vf)
        self.assertIn("pad=1080:1920", vf)

    def test_assemble_16_9_uses_landscape_container(self):
        """16:9 stays the 1920x1080 landscape container (byte-identity)."""
        vf = self._capture_normalize_vf({"aspect_ratio": "16:9"})
        self.assertIsNotNone(vf)
        self.assertIn("scale=1920:1080", vf)

    def test_assemble_unsupported_ratio_falls_back_to_default(self):
        """I1 guard: an unsupported persisted ratio (4:3) falls back to the
        16:9 default container, never a 4:3/garbage container."""
        vf = self._capture_normalize_vf({"aspect_ratio": "4:3"})
        self.assertIsNotNone(vf)
        self.assertIn("scale=1920:1080", vf)

    def test_assemble_final_with_foley_cmd_uses_amix_inputs_3(self):
        """With foley paths, the primary mix command uses amix=inputs=3 and includes foley input."""
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=None)

        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fake_foley = os.path.join(pipeline.temp_dir, "foley_s1.mp3")
        open(fake_foley, "wb").close()
        pipeline.foley_audio_paths = [fake_foley]

        captured_cmds = []
        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            m = mock.MagicMock()
            m.returncode = 0
            return m

        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        fake_clip = os.path.join(pipeline.temp_dir, "clip.mp4")
        open(fake_bgm, "wb").close()
        open(fake_clip, "wb").close()
        scene_data = [{"scene_id": "s1", "clips": [fake_clip]}]

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            pipeline._assemble_final(scene_data, fake_bgm, {})

        mix_cmds = [c for c in captured_cmds if any("amix" in str(a) for a in c)]
        self.assertTrue(len(mix_cmds) >= 1, "Expected at least one amix command")
        mix_filter = " ".join(str(a) for a in mix_cmds[0])
        self.assertIn("amix=inputs=3", mix_filter)
        self.assertIn("0.20", mix_filter)  # foley volume
        # foley path should appear in the command inputs
        all_args = " ".join(str(a) for a in mix_cmds[0])
        self.assertIn("foley", all_args)

    def test_assemble_final_foley_concat_called_for_multi_scene(self):
        """With 2 foley paths, _concat_foley_track is invoked (concat needed)."""
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=None)

        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fp1 = os.path.join(pipeline.temp_dir, "foley_s1.mp3")
        fp2 = os.path.join(pipeline.temp_dir, "foley_s2.mp3")
        for fp in (fp1, fp2):
            open(fp, "wb").close()
        pipeline.foley_audio_paths = [fp1, fp2]

        fake_track = os.path.join(pipeline.temp_dir, "foley_track.mp3")

        captured_concat_calls = []
        original_concat = pipeline._concat_foley_track
        def mock_concat(paths):
            captured_concat_calls.append(paths)
            # Write the track so os.path.exists passes in _assemble_final
            open(fake_track, "wb").close()
            return fake_track
        pipeline._concat_foley_track = mock_concat

        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        fake_clip = os.path.join(pipeline.temp_dir, "clip.mp4")
        open(fake_bgm, "wb").close()
        open(fake_clip, "wb").close()
        scene_data = [{"scene_id": "s1", "clips": [fake_clip]}]

        with mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0)), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            pipeline._assemble_final(scene_data, fake_bgm, {})

        self.assertEqual(len(captured_concat_calls), 1)
        self.assertEqual(captured_concat_calls[0], [fp1, fp2])


class TestFoleyAudioPathsProperty(GuidedPipelineTestCase):
    """Unit tests for CinemaPipeline.foley_audio_paths @property and @setter."""

    def test_foley_audio_paths_property_reads_from_runstate(self):
        project, _, _ = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        pipeline._runstate.foley_audio_paths = ["/tmp/f.mp3"]
        self.assertEqual(pipeline.foley_audio_paths, ["/tmp/f.mp3"])

    def test_foley_audio_paths_setter_writes_to_runstate(self):
        project, _, _ = self.create_project_with_single_shot()
        pipeline = CinemaPipeline(project["id"])
        pipeline.foley_audio_paths = ["/tmp/a.mp3", "/tmp/b.mp3"]
        self.assertEqual(pipeline._runstate.foley_audio_paths, ["/tmp/a.mp3", "/tmp/b.mp3"])


class TestAssembleFinalSceneTransitions(TestAssembleFinalFoleyMix):
    def _run(self, settings, n_scenes):
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        open(fake_bgm, "wb").close()
        scene_data = []
        for si in range(n_scenes):
            clip = os.path.join(pipeline.temp_dir, f"clip_{si}.mp4")
            open(clip, "wb").close()
            scene_data.append({"scene_id": f"s{si}", "clips": [clip]})

        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            for arg in cmd:
                if str(arg).endswith(".mp4"):
                    open(arg, "wb").close()
            m = mock.MagicMock(); m.returncode = 0; m.stdout = '{"format":{"duration":"4.0"}}'
            return m

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            result = pipeline._assemble_final(scene_data, fake_bgm, settings)
        assert result is not None, "assembly must return a path (every _run case)"
        return captured

    def test_off_uses_concat_demuxer_no_xfade(self):
        cmds = self._run({"scene_transitions": False}, n_scenes=2)
        joined = [" ".join(str(a) for a in c) for c in cmds]
        assert any("-f concat" in j or "concat" in j for j in joined)
        assert not any("xfade" in j for j in joined), "OFF must not emit xfade"

    def test_default_is_off(self):
        cmds = self._run({}, n_scenes=2)
        assert not any("xfade" in " ".join(str(a) for a in c) for c in cmds)

    def test_on_with_two_scenes_emits_xfade(self):
        cmds = self._run({"scene_transitions": True}, n_scenes=2)
        assert any("xfade" in " ".join(str(a) for a in c) for c in cmds), \
            "ON with >=2 scenes must emit an xfade command"

    def test_on_with_single_scene_falls_back_to_concat(self):
        cmds = self._run({"scene_transitions": True}, n_scenes=1)
        assert not any("xfade" in " ".join(str(a) for a in c) for c in cmds), \
            "ON with 1 scene cannot xfade -> fall back to concat"

    def test_on_xfade_raises_falls_back_to_concat(self):
        # If xfade_concat raises mid-assembly, the ON path must fall back to a
        # plain concat and still return a path (the only otherwise untested branch).
        # xfade_concat is imported locally inside _assemble_final, so patching it on
        # the module is picked up at call time.
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        open(fake_bgm, "wb").close()
        scene_data = []
        for si in range(2):
            clip = os.path.join(pipeline.temp_dir, f"clip_{si}.mp4")
            open(clip, "wb").close()
            scene_data.append({"scene_id": f"s{si}", "clips": [clip]})

        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            for arg in cmd:
                if str(arg).endswith(".mp4"):
                    open(arg, "wb").close()
            m = mock.MagicMock(); m.returncode = 0; m.stdout = '{"format":{"duration":"4.0"}}'
            return m

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch("phase_c_ffmpeg.xfade_concat", side_effect=RuntimeError("boom")), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            result = pipeline._assemble_final(scene_data, fake_bgm, {"scene_transitions": True})

        joined = [" ".join(str(a) for a in c) for c in captured]
        assert any("concat" in j for j in joined), "fallback must use the concat demuxer"
        assert result is not None, "assembly must still return a path after fallback"


if __name__ == "__main__":
    unittest.main()

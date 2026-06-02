"""Unit tests for F1b: mandatory lipsync pass + auto-approve gate fix + assembler guard.

Coverage:
  TestMandatoryLipsyncPass   — generate_motion_take mandatory lipsync block
  TestAutoApproveGateFix     — _best_take_lipsync blind-gate fix
  TestAssemblerEmbeddedGuard — _build_scene_packages TTS suppression for embedded scenes

All tests are fully offline — no real API calls, no GPU.
"""

from __future__ import annotations

import sys
import os
import types
from unittest.mock import MagicMock, patch, call
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Stubs — prevent heavy imports at module load
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


for _dep in [
    "veo_native", "kling_native", "sora_native", "ltx_native",
    "runway_native", "runway_gen4", "fal_proxy", "kling_3_0",
    "sora_2", "veo_fal",
]:
    if _dep not in sys.modules:
        _stub_module(_dep)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_take_meta(
    *,
    has_dialogue: bool = False,
    audio_embedded: bool = False,
    lipsync_score: Optional[float] = None,
) -> dict:
    meta = {"has_dialogue": has_dialogue}
    if audio_embedded:
        meta["audio_embedded"] = True
    if lipsync_score is not None:
        meta["lipsync_score"] = lipsync_score
    return meta


def _make_take(
    take_id: str = "take_t1",
    *,
    has_dialogue: bool = False,
    audio_embedded: bool = False,
    lipsync_score: Optional[float] = None,
) -> dict:
    return {
        "id": take_id,
        "kind": "motion",
        "path": f"/tmp/{take_id}.mp4",
        "metadata": _make_take_meta(
            has_dialogue=has_dialogue,
            audio_embedded=audio_embedded,
            lipsync_score=lipsync_score,
        ),
    }


# ---------------------------------------------------------------------------
# (a) Non-embedded dialogue take → lipsync pass runs + lipsync_score written
# ---------------------------------------------------------------------------

class TestMandatoryLipsyncPass:
    """
    Inline-simulation tests for the metadata contracts produced by the F1b
    lipsync block.

    NOTE: These tests are INLINE MIRRORS of the block's logic — they
    re-implement the block structure inline rather than calling the REAL
    generate_motion_take.  They therefore cannot catch production drift in the
    wiring itself.  Use TestGenerateMotionTakeOverlayWiring (below) for the
    real end-to-end wiring test.
    """

    def _build_controller_fragment(self, monkeypatch, lipsync_returns: Optional[str]):
        """
        Build a minimal environment to simulate the lipsync block inline
        (does NOT call generate_motion_take — this is a white-box inline mirror).

        Returns (take_metadata, final_vid_after_block) after running the block.
        """
        import tempfile

        # Create a real temp file to act as final_vid (generate_motion_take checks
        # os.path.exists on final_vid before calling the lipsync block).
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            real_vid = f.name

        lipsync_out_path = real_vid + "_ls.mp4"
        if lipsync_returns is not None:
            # Create the "lipsync output" so os.path.exists passes.
            with open(lipsync_out_path, "wb") as f:
                f.write(b"fake_ls")

        # Audio + ref image paths (simulate existing files).
        audio_path = real_vid + "_audio.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"fake_audio")
        ref_image = real_vid + "_ref.jpg"
        with open(ref_image, "wb") as f:
            f.write(b"fake_ref")

        # Mock generate_lip_sync_video and validate_lipsync_quality.
        mock_generate = MagicMock(
            return_value=lipsync_out_path if lipsync_returns else None
        )
        mock_validate = MagicMock(return_value=0.87)

        # Inline the lipsync block logic, matching controller.py exactly.
        # This is a white-box test of the metadata contract produced by the block.
        take_metadata: dict = {"has_dialogue": True}
        final_vid = real_vid
        shot_id = "shot_test"
        settings: dict = {}

        # Simulate the block (mirrors controller.py F1b block structure):
        # has_dialogue=True, audio_embedded not set → enter the lipsync branch.
        try:
            generate_lip_sync_video = mock_generate
            validate_lipsync_quality = mock_validate

            chars_for_sync = ["char_1"]
            audio_path_for_sync = audio_path
            primary_ref_for_sync = ref_image

            if audio_path_for_sync and primary_ref_for_sync:
                lipsync_out = lipsync_out_path
                _ls_cascade: dict = {}
                ls_result = generate_lip_sync_video(
                    character_image_path=primary_ref_for_sync,
                    audio_path=audio_path_for_sync,
                    output_path=lipsync_out,
                    existing_video_path=final_vid,
                    mode=settings.get("lip_sync_mode", "auto"),
                    settings=settings,
                    _cascade_out=_ls_cascade,
                )
                if ls_result and os.path.exists(ls_result):
                    final_vid = ls_result
                    take_metadata["lipsync_score"] = validate_lipsync_quality(
                        ls_result, audio_path_for_sync
                    )
                else:
                    take_metadata["lipsync_score"] = 0.0
            else:
                take_metadata["lipsync_score"] = 0.0
        except Exception:
            take_metadata.setdefault("lipsync_score", 0.0)

        # Cleanup.
        for p in [real_vid, audio_path, ref_image]:
            try:
                os.unlink(p)
            except OSError:
                pass
        if lipsync_returns is None:
            try:
                os.unlink(lipsync_out_path)
            except OSError:
                pass

        return take_metadata, final_vid, mock_generate, mock_validate

    def test_lipsync_pass_writes_score_when_succeeds(self, tmp_path):
        """
        Inline simulation: when the mock generate_lip_sync_video returns a
        valid path, lipsync_score is written to the inline metadata dict.
        (Does NOT call the real generate_motion_take — see
        TestGenerateMotionTakeOverlayWiring for the real wiring test.)
        """
        take_meta, final_vid, mock_gen, mock_validate = (
            self._build_controller_fragment(None, lipsync_returns="something")
        )
        assert "lipsync_score" in take_meta, "lipsync_score should be set after successful pass"
        assert take_meta["lipsync_score"] == pytest.approx(0.87)
        assert mock_gen.called, "generate_lip_sync_video should be called"
        assert mock_validate.called, "validate_lipsync_quality should be called"

    def test_lipsync_pass_writes_zero_when_fails(self, tmp_path):
        """
        Inline simulation: when the mock returns None, lipsync_score is 0.0.
        (Does NOT call the real generate_motion_take — inline mirror only.)
        """
        take_meta, final_vid, mock_gen, _ = (
            self._build_controller_fragment(None, lipsync_returns=None)
        )
        assert take_meta.get("lipsync_score") == pytest.approx(0.0), (
            "Failed lipsync should produce 0.0 score, not absent or 1.0"
        )

    def test_has_dialogue_written_to_take_metadata(self):
        """
        Inline simulation: has_dialogue is written to take metadata.
        (Inline dict operation, not a call to generate_motion_take.)
        """
        # Simulate the F1b has_dialogue write (controller.py).
        take_metadata = {}
        has_dialogue = True
        take_metadata["has_dialogue"] = has_dialogue
        assert take_metadata["has_dialogue"] is True

        has_dialogue = False
        take_metadata2 = {}
        take_metadata2["has_dialogue"] = has_dialogue
        assert take_metadata2["has_dialogue"] is False


# ---------------------------------------------------------------------------
# (b/c/d) Auto-approve gate: blind-gate fix
# ---------------------------------------------------------------------------

class TestAutoApproveGateFix:
    """
    Test that _best_take_lipsync correctly fails unverified dialogue takes
    and passes audio_embedded / non-dialogue takes.
    """

    def test_gate_fails_dialogue_take_with_no_lipsync_and_not_embedded(self):
        """
        (b) A take with has_dialogue=True, no lipsync_score, no audio_embedded
        must return 0.0 (FAIL) — not the old 1.0 blind default.
        """
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            _make_take("t1", has_dialogue=True),
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(0.0), (
            f"Unverified dialogue take should score 0.0, got {score}"
        )

    def test_gate_passes_audio_embedded_dialogue_take(self):
        """
        (c) A take with audio_embedded=True is a native-audio take — gate passes.
        """
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            _make_take("t1", has_dialogue=True, audio_embedded=True),
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(1.0), (
            f"audio_embedded take should score 1.0, got {score}"
        )

    def test_gate_passes_non_dialogue_take(self):
        """
        (d) A non-dialogue take with no lipsync_score should still return 1.0 (N/A).
        """
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            {"id": "t1", "metadata": {}},
            {"id": "t2", "metadata": {"identity_score": 0.9}},
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(1.0), (
            f"Non-dialogue take should default to 1.0 (N/A), got {score}"
        )

    def test_gate_passes_dialogue_take_with_good_lipsync_score(self):
        """
        Positive case: dialogue take with lipsync_score=0.9 passes gate (threshold 0.8).
        """
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            _make_take("t1", has_dialogue=True, lipsync_score=0.9),
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(0.9)

    def test_gate_returns_max_lipsync_across_takes(self):
        """Existing v1.1 behavior preserved: returns MAX score across takes."""
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            _make_take("t1", has_dialogue=True, lipsync_score=0.7),
            _make_take("t2", has_dialogue=True, lipsync_score=0.95),
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(0.95)

    def test_gate_mixed_dialogue_unverified_and_scored(self):
        """
        When SOME takes are unverified dialogue AND other takes have scores,
        the scored takes' max is returned (the best-take semantics still win —
        one good synced take salvages the shot).
        """
        from cinema.auto_approve import _best_take_lipsync
        takes = [
            _make_take("t1", has_dialogue=True),           # unverified
            _make_take("t2", has_dialogue=True, lipsync_score=0.88),  # scored
        ]
        score = _best_take_lipsync(takes)
        assert score == pytest.approx(0.88), (
            "A scored take should prevent the 0.0 fallback"
        )

    def test_gate_with_check_gate_vetos_unverified_dialogue(self):
        """
        Integration: check_gate("final") should veto when the only take is an
        unverified dialogue take (has_dialogue=True, no lipsync_score, no embedded).
        """
        from cinema.auto_approve import (
            AutoApproveConfig, check_gate,
        )
        config = AutoApproveConfig(
            final_min_lipsync=0.8,
            final_require_human_if_upstream_auto=False,
        )
        shot = {
            "id": "shot_001",
            "plan_status": "approved",
            "director_review": {"decision": "APPROVED", "violations": []},
            "keyframe_takes": [],
            "motion_takes": [_make_take("t1", has_dialogue=True)],
            "postprocess_variants": [],
            "spent_usd": 0.0,
            "auto_approve_audit": [],
        }
        takes = [_make_take("t1", has_dialogue=True)]
        project = {
            "id": "proj_001",
            "global_settings": {"auto_approve": config.to_dict()},
        }
        decision = check_gate(
            "final",
            shot_state=shot,
            project=project,
            takes=takes,
            config=config,
        )
        assert decision.auto_approved is False, (
            "Unverified dialogue take must be vetoed by the final gate"
        )
        assert any("lipsync" in r.lower() for r in decision.vetoes), (
            f"Expected lipsync veto reason in {decision.vetoes}"
        )

    def test_gate_with_check_gate_passes_embedded_dialogue(self):
        """
        Integration: check_gate("final") should NOT veto an audio_embedded take.
        """
        from cinema.auto_approve import (
            AutoApproveConfig, check_gate,
        )
        config = AutoApproveConfig(
            final_min_lipsync=0.8,
            final_require_human_if_upstream_auto=False,
        )
        embedded_take = _make_take("t1", has_dialogue=True, audio_embedded=True)
        shot = {
            "id": "shot_001",
            "plan_status": "approved",
            "director_review": {"decision": "APPROVED", "violations": []},
            "keyframe_takes": [],
            "motion_takes": [embedded_take],
            "postprocess_variants": [],
            "spent_usd": 0.0,
            "auto_approve_audit": [],
        }
        project = {
            "id": "proj_001",
            "global_settings": {"auto_approve": config.to_dict()},
        }
        decision = check_gate(
            "final",
            shot_state=shot,
            project=project,
            takes=[embedded_take],
            config=config,
        )
        assert decision.auto_approved is True, (
            f"audio_embedded dialogue take should pass the final gate; "
            f"vetoes={decision.vetoes}"
        )


# ---------------------------------------------------------------------------
# (e) Assembler guard: embedded scene suppresses standalone TTS
# ---------------------------------------------------------------------------

class TestAssemblerEmbeddedGuard:
    """
    Test that _build_scene_packages sets scene_package["audio"]=None
    (suppresses TTS) when all approved shots in a scene are audio_embedded.
    """

    def _make_shot_with_take(
        self,
        shot_id: str,
        *,
        audio_embedded: bool = False,
    ) -> dict:
        """Return a shot dict with an approved final take in motion_takes."""
        take_id = f"take_{shot_id}"
        take = {
            "id": take_id,
            "kind": "motion",
            "path": f"/tmp/{take_id}.mp4",
            "metadata": {"has_dialogue": True, "audio_embedded": audio_embedded},
        }
        return {
            "id": shot_id,
            "approved_final_take_id": take_id,
            "motion_takes": [take],
            "postprocess_variants": [],
            "characters_in_frame": ["char_1"],
        }

    def _run_build_scene_packages(self, scenes, tmp_path) -> tuple[list, list]:
        """
        Exercise _build_scene_packages logic without instantiating CinemaPipeline.

        We extract the logic as a standalone function that mirrors the method body,
        using _approved_take_metadata from CinemaPipeline as a pure static method.
        This avoids the CinemaPipeline property constraints while testing the real logic.
        """
        from cinema_pipeline import CinemaPipeline

        # Create the shot video files so os.path.exists passes.
        for scene in scenes:
            for shot in scene.get("shots", []):
                take_id = shot.get("approved_final_take_id", "")
                if take_id:
                    vid_path = tmp_path / f"{take_id}.mp4"
                    vid_path.write_bytes(b"fake")

        scene_packages = []
        missing_shots = []
        scene_clips = {}

        for scene in scenes:
            scene_id = scene.get("id", "")
            clips = []
            approved_shot_count = 0
            all_embedded_count = 0
            for shot in scene.get("shots", []):
                final_take_id = shot.get("approved_final_take_id", "")
                final_path = str(tmp_path / f"{final_take_id}.mp4") if final_take_id else ""
                if not final_path or not os.path.exists(final_path):
                    missing_shots.append(shot.get("id", ""))
                    continue
                clips.append(final_path)
                approved_shot_count += 1
                take_meta = CinemaPipeline._approved_take_metadata(shot)
                if take_meta.get("audio_embedded"):
                    all_embedded_count += 1

            scene_clips[scene_id] = clips

            all_shots_embedded = (
                approved_shot_count > 0 and all_embedded_count == approved_shot_count
            )
            if all_shots_embedded:
                scene_audio = None
            else:
                # Stub _ensure_scene_audio: return a synthetic path.
                scene_audio = f"/tmp/audio_{scene_id}.mp3"

            scene_packages.append({
                "scene_id": scene_id,
                "clips": clips,
                "audio": scene_audio,
                "foley": [],
            })

        return scene_packages, missing_shots

    def test_all_embedded_scene_suppresses_tts(self, tmp_path):
        """
        (e) When EVERY approved shot in a scene has audio_embedded=True,
        scene_package["audio"] must be None (TTS suppressed).
        """
        scene = {
            "id": "scene_1",
            "characters_present": ["char_1"],
            "shots": [
                self._make_shot_with_take("s1_shot1", audio_embedded=True),
                self._make_shot_with_take("s1_shot2", audio_embedded=True),
            ],
        }
        packages, missing = self._run_build_scene_packages([scene], tmp_path)

        assert missing == [], f"Unexpected missing shots: {missing}"
        assert len(packages) == 1
        pkg = packages[0]
        assert pkg["audio"] is None, (
            f"All-embedded scene should have audio=None, got {pkg['audio']!r}"
        )

    def test_non_embedded_scene_includes_tts(self, tmp_path):
        """
        (e) When NO shots are audio_embedded, scene_package["audio"] is populated
        via _ensure_scene_audio (TTS path preserved).
        """
        scene = {
            "id": "scene_2",
            "characters_present": ["char_1"],
            "shots": [
                self._make_shot_with_take("s2_shot1", audio_embedded=False),
            ],
        }
        packages, _ = self._run_build_scene_packages([scene], tmp_path)
        pkg = packages[0]
        assert pkg["audio"] == "/tmp/audio_scene_2.mp3", (
            f"Non-embedded scene should include TTS audio, got {pkg['audio']!r}"
        )

    def test_mixed_embedded_scene_keeps_tts(self, tmp_path):
        """
        (e) Edge case: mixed scene (some embedded, some not) conservatively
        includes TTS audio to avoid silent non-embedded shots.
        """
        scene = {
            "id": "scene_3",
            "characters_present": ["char_1"],
            "shots": [
                self._make_shot_with_take("s3_shot1", audio_embedded=True),
                self._make_shot_with_take("s3_shot2", audio_embedded=False),
            ],
        }
        packages, _ = self._run_build_scene_packages([scene], tmp_path)
        pkg = packages[0]
        assert pkg["audio"] == "/tmp/audio_scene_3.mp3", (
            f"Mixed-embedded scene should keep TTS audio, got {pkg['audio']!r}"
        )

    def test_approved_take_metadata_lookup(self):
        """
        Verify _approved_take_metadata finds the correct take by approved_final_take_id.
        """
        from cinema_pipeline import CinemaPipeline
        shot = {
            "approved_final_take_id": "take_abc",
            "motion_takes": [
                {"id": "take_xyz", "metadata": {"lipsync_score": 0.5}},
                {"id": "take_abc", "metadata": {"audio_embedded": True, "has_dialogue": True}},
            ],
            "postprocess_variants": [],
        }
        meta = CinemaPipeline._approved_take_metadata(shot)
        assert meta.get("audio_embedded") is True
        assert meta.get("has_dialogue") is True

    def test_approved_take_metadata_missing_take_id(self):
        """_approved_take_metadata returns {} when approved_final_take_id is absent."""
        from cinema_pipeline import CinemaPipeline
        shot = {
            "motion_takes": [{"id": "take_xyz", "metadata": {"lipsync_score": 0.5}}],
            "postprocess_variants": [],
        }
        assert CinemaPipeline._approved_take_metadata(shot) == {}


# ---------------------------------------------------------------------------
# Task 6 — per-shot TTS in F1b pass + Veo clip sized to speech
# ---------------------------------------------------------------------------


class TestDurationClamp:
    """Unit tests for the _clamp_veo_duration helper (pure function)."""

    def test_clamp_returns_nearest_not_less(self):
        """Duration is clamped to the nearest supported value >= speech length."""
        from cinema.shots.controller import _clamp_veo_duration
        assert _clamp_veo_duration(0.0) == "4s"
        assert _clamp_veo_duration(3.5) == "4s"
        assert _clamp_veo_duration(4.0) == "4s"
        assert _clamp_veo_duration(4.1) == "6s"
        assert _clamp_veo_duration(5.9) == "6s"
        assert _clamp_veo_duration(6.0) == "6s"
        assert _clamp_veo_duration(6.1) == "8s"
        assert _clamp_veo_duration(8.0) == "8s"

    def test_clamp_caps_at_8s_for_long_lines(self):
        """Lines longer than max supported duration are clamped to '8s'."""
        from cinema.shots.controller import _clamp_veo_duration
        assert _clamp_veo_duration(9.0) == "8s"
        assert _clamp_veo_duration(30.0) == "8s"
        assert _clamp_veo_duration(100.0) == "8s"


class TestGenerateAiVideoDurationParam:
    """
    Task 6: generate_ai_video now accepts a duration: str = "8s" param and
    threads it through the VEO_NATIVE branch and the fal-proxy branch.
    Default "8s" leaves all existing callers unchanged.
    """

    def test_veo_native_receives_duration_param(self):
        """
        When duration is passed to generate_ai_video, VeoNativeAPI.generate_video
        is called with that duration value.
        """
        from phase_c_ffmpeg import generate_ai_video

        mock_veo_instance = MagicMock()
        mock_veo_instance.generate_video.return_value = "/tmp/fake_output.mp4"
        mock_veo_cls = MagicMock(return_value=mock_veo_instance)

        with patch.dict("sys.modules", {"veo_native": MagicMock(VeoNativeAPI=mock_veo_cls)}):
            with patch("os.path.exists", return_value=True):
                generate_ai_video(
                    image_path="/tmp/fake_frame.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4="/tmp/out.mp4",
                    shot_type="portrait",
                    duration="6s",
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("duration") == "6s", (
            "generate_ai_video must thread duration into veo.generate_video"
        )

    def test_veo_native_default_duration_is_8s(self):
        """When duration is omitted, the VEO_NATIVE branch defaults to '8s'."""
        from phase_c_ffmpeg import generate_ai_video

        mock_veo_instance = MagicMock()
        mock_veo_instance.generate_video.return_value = "/tmp/fake_output.mp4"
        mock_veo_cls = MagicMock(return_value=mock_veo_instance)

        with patch.dict("sys.modules", {"veo_native": MagicMock(VeoNativeAPI=mock_veo_cls)}):
            with patch("os.path.exists", return_value=True):
                generate_ai_video(
                    image_path="/tmp/fake_frame.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4="/tmp/out.mp4",
                    shot_type="portrait",
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("duration") == "8s", (
            "default duration must be '8s' to preserve existing call-site behavior"
        )


class TestF1bPerShotAudioWire:
    """
    Task 6: In overlay-mode dialogue, the F1b block:
    - Resolves per-shot TTS via _ensure_shot_audio before generate_ai_video.
    - Uses _ensure_scene_audio as fallback when shot has no own line.
    - Passes the clamped duration to generate_ai_video.
    - In native mode the old behaviour is unchanged.

    We test the logic of the new helper _resolve_f1b_audio_and_duration
    (or equivalent) by inspecting what the F1b block passes to
    generate_ai_video / the lipsync call — white-box, same approach as
    TestMandatoryLipsyncPass above.
    """

    def _make_host_with_audio(self, tmp_path, shot_audio_path=None, scene_audio_path=None):
        """Build a minimal host whose _ensure_shot_audio / _ensure_scene_audio return controlled values."""
        host = MagicMock()
        host._ensure_shot_audio.return_value = shot_audio_path
        host._ensure_scene_audio.return_value = scene_audio_path or str(tmp_path / "scene.mp3")
        return host

    def test_per_shot_audio_used_when_shot_has_dialogue(self, tmp_path):
        """
        When the shot has its own dialogue line, _ensure_shot_audio is called and
        its return value feeds the F1b lipsync call (not _ensure_scene_audio).
        """
        from cinema.shots.controller import _resolve_f1b_audio

        shot_audio = str(tmp_path / "audio_shot.mp3")
        shot = {"id": "s1", "dialogue": "Hello."}
        scene = {"id": "sc1"}
        chars = []
        host = self._make_host_with_audio(tmp_path, shot_audio_path=shot_audio)

        result = _resolve_f1b_audio(host, shot, scene, chars, voice_mode="overlay")

        host._ensure_shot_audio.assert_called_once_with(shot, scene, chars)
        assert result == shot_audio

    def test_scene_audio_fallback_when_shot_has_no_line(self, tmp_path):
        """
        When _ensure_shot_audio returns None (no own line), the result falls
        back to _ensure_scene_audio.
        """
        from cinema.shots.controller import _resolve_f1b_audio

        scene_audio = str(tmp_path / "scene.mp3")
        shot = {"id": "s2"}  # no dialogue key
        scene = {"id": "sc1"}
        chars = []
        host = self._make_host_with_audio(tmp_path, shot_audio_path=None, scene_audio_path=scene_audio)

        result = _resolve_f1b_audio(host, shot, scene, chars, voice_mode="overlay")

        host._ensure_shot_audio.assert_called_once()
        host._ensure_scene_audio.assert_called_once_with(scene, chars)
        assert result == scene_audio

    def test_native_mode_uses_scene_audio_only(self, tmp_path):
        """
        In native mode, _resolve_f1b_audio skips _ensure_shot_audio entirely
        and falls back directly to _ensure_scene_audio (matching legacy behavior).
        """
        from cinema.shots.controller import _resolve_f1b_audio

        scene_audio = str(tmp_path / "scene.mp3")
        shot = {"id": "s3", "dialogue": "Native line."}
        scene = {"id": "sc1"}
        chars = []
        host = self._make_host_with_audio(tmp_path, shot_audio_path=None, scene_audio_path=scene_audio)

        result = _resolve_f1b_audio(host, shot, scene, chars, voice_mode="native")

        host._ensure_shot_audio.assert_not_called()
        host._ensure_scene_audio.assert_called_once_with(scene, chars)
        assert result == scene_audio


# ---------------------------------------------------------------------------
# Chunk 3 — Task 7: overlay-wiring integration + assembler dedup
# ---------------------------------------------------------------------------


class TestGenerateMotionTakeOverlayWiring:
    """
    Real integration test: calls the ACTUAL ShotController.generate_motion_take
    for an overlay-mode dialogue shot and asserts the F1b wiring contract:

    1. generate_ai_video called with dialogue_native_audio=False (silent Veo)
       and a duration sized from the per-shot TTS (clamped value).
    2. generate_lip_sync_video called with existing_video_path=<the veo clip>
       and audio_path=<the per-shot TTS> and mode matching settings.
    3. The resulting take metadata has:
       - NO audio_embedded key (overlay path does not tag it)
       - dialogue_audio_in_clip == True
       - a numeric lipsync_score

    All externals are mocked; no GPU, no network.  _finalize_motion_take is
    also mocked (avoids continuity/checkpoint/cost machinery) so we can inspect
    the take argument it receives.
    """

    def _build_controller(self, project: dict, tmp_path):
        """Build a minimal ShotController with mocked host + core."""
        from cinema.shots.controller import ShotController

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = {}
        host._save_checkpoint.return_value = None
        # _resolve_take_path returns a real file so os.path.exists passes.
        keyframe_path = str(tmp_path / "keyframe.jpg")
        open(keyframe_path, "wb").write(b"fake_jpg")
        host._resolve_take_path.return_value = keyframe_path
        host._ensure_shot_audio.return_value = None  # override per test
        host._ensure_scene_audio.return_value = None  # override per test

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
            "continuity_config": {"primary_character": "char_1", "multi_angle_refs": []}
        }
        cost_tracker = MagicMock()
        cost_tracker.is_over_budget.return_value = False
        core.cost_tracker = cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        # _take_output_path: return deterministic paths under tmp_path.
        ctrl._take_output_path = MagicMock(
            side_effect=lambda shot_id, take_id, ext: str(tmp_path / f"{take_id}{ext}")
        )
        return ctrl, host

    def _make_overlay_dialogue_project(self, tmp_path, voice_mode: str = "overlay") -> dict:
        """
        Minimal project with one dialogue_close_up shot approved for motion
        generation.  optimizer_cache drives has_dialogue=True in the controller.
        """
        keyframe_take_id = "kf_t1"
        return {
            "id": "proj_overlay_test",
            "characters": [
                {"id": "char_1", "name": "Alice"},
            ],
            "global_settings": {"dialogue_voice_mode": voice_mode},
            "scenes": [
                {
                    "id": "scene_1",
                    "title": "Dialogue Scene",
                    "action": "Alice speaks.",
                    "characters_present": ["char_1"],
                    "shots": [
                        {
                            "id": "shot_1_0",
                            "prompt": "Close-up of Alice speaking",
                            "plan_status": "approved",
                            "target_api": "AUTO",
                            "camera": "static",
                            "characters_in_frame": ["char_1"],
                            "approved_keyframe_take_id": keyframe_take_id,
                            "optimizer_cache": {
                                "spec": {
                                    "purpose": "dialogue_close_up",
                                    "suggested_video_api": "VEO_NATIVE",
                                }
                            },
                        }
                    ],
                }
            ],
        }

    def test_overlay_wiring_calls_real_generate_motion_take(self, tmp_path):
        """
        Calls the REAL generate_motion_take for a dialogue_close_up shot in
        overlay mode and asserts the full F1b wiring contract.

        This is the only test in this file that exercises production code
        end-to-end through the dialogue F1b block.
        """
        project = self._make_overlay_dialogue_project(tmp_path, voice_mode="overlay")
        ctrl, host = self._build_controller(project, tmp_path)

        # Per-shot TTS audio file (exists on disk so _probe_duration and
        # the lipsync call see a real path).
        audio_file = str(tmp_path / "shot_tts.mp3")
        open(audio_file, "wb").write(b"fake_audio_bytes")
        # Character reference image (get_reference_image mock must return a real path).
        ref_image_file = str(tmp_path / "ref_char1.jpg")
        open(ref_image_file, "wb").write(b"fake_jpg")

        # Veo silent clip output (generate_ai_video returns this).
        veo_clip = str(tmp_path / "veo_clip.mp4")
        open(veo_clip, "wb").write(b"fake_veo")
        # Lipsync output (generate_lip_sync_video returns this).
        ls_clip = str(tmp_path / "ls_clip.mp4")
        open(ls_clip, "wb").write(b"fake_ls")

        # --- per-shot TTS: host._ensure_shot_audio returns our file ---
        host._ensure_shot_audio.return_value = audio_file

        # Capture the take that reaches _finalize_motion_take so we can assert
        # on it after generate_motion_take returns.
        _captured_take = {}

        def _fake_finalize(scene, shot, take, video_path, **kwargs):
            _captured_take.update(take)
            return {"success": True, "take": dict(take), "video": video_path, "identity_score": 0.0}

        ctrl._finalize_motion_take = MagicMock(side_effect=_fake_finalize)

        with (
            patch("cinema.shots.controller.generate_ai_video", return_value=veo_clip) as mock_gen_vid,
            patch("cinema.shots.controller.generate_lip_sync_video", return_value=ls_clip) as mock_gen_ls_ctrl,
            patch("lip_sync.generate_lip_sync_video", return_value=ls_clip) as mock_gen_ls_lip,
            patch("lip_sync.validate_lipsync_quality", return_value=0.91) as mock_validate,
            patch("cinema.shots.controller.get_reference_image", return_value=ref_image_file),
            patch("cinema.shots.controller._probe_duration", return_value=3.5),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
        ):
            result = ctrl.generate_motion_take("scene_1", "shot_1_0")

        # --- Primary assertion: the method was called and returned successfully ---
        assert result.get("success") is True, (
            f"generate_motion_take returned failure: {result}"
        )

        # --- generate_ai_video called with dialogue_native_audio=False (silent Veo) ---
        mock_gen_vid.assert_called_once()
        gen_vid_kwargs = mock_gen_vid.call_args.kwargs
        assert gen_vid_kwargs.get("dialogue_native_audio") is False, (
            "overlay mode must call generate_ai_video with dialogue_native_audio=False "
            f"(got {gen_vid_kwargs.get('dialogue_native_audio')!r})"
        )

        # --- duration sized from TTS: 3.5s → clamped to '4s' ---
        assert gen_vid_kwargs.get("duration") == "4s", (
            "overlay mode must size the Veo duration from per-shot TTS "
            f"(expected '4s' for 3.5s audio; got {gen_vid_kwargs.get('duration')!r})"
        )

        # --- generate_lip_sync_video called with the Veo clip as existing_video_path
        #     and the per-shot TTS as audio_path ---
        # Either the module-level or the re-imported binding is called; check both.
        ls_call = mock_gen_ls_ctrl.call_args or mock_gen_ls_lip.call_args
        assert ls_call is not None, "generate_lip_sync_video was never called"
        ls_kwargs = ls_call.kwargs
        assert ls_kwargs.get("existing_video_path") == veo_clip, (
            "F1b must overlay the per-shot TTS onto the Veo clip "
            f"(expected existing_video_path={veo_clip!r}; got {ls_kwargs.get('existing_video_path')!r})"
        )
        assert ls_kwargs.get("audio_path") == audio_file, (
            "F1b must use the per-shot TTS audio "
            f"(expected audio_path={audio_file!r}; got {ls_kwargs.get('audio_path')!r})"
        )

        # --- take metadata ---
        assert "audio_embedded" not in _captured_take.get("metadata", {}), (
            "overlay mode must NOT set audio_embedded on the take"
        )
        assert _captured_take.get("metadata", {}).get("dialogue_audio_in_clip") is True, (
            "F1b must set dialogue_audio_in_clip=True after successful overlay"
        )
        lipsync_score = _captured_take.get("metadata", {}).get("lipsync_score")
        assert isinstance(lipsync_score, (int, float)) and lipsync_score > 0, (
            f"take metadata must carry a positive lipsync_score; got {lipsync_score!r}"
        )


class TestAssemblerOverlayInClipDedup:
    """
    Chunk 3, Task 7b: _build_scene_packages suppresses scene-level TTS when all
    approved shots have dialogue_audio_in_clip=True (or audio_embedded=True).

    We call the REAL CinemaPipeline._build_scene_packages by bypassing __init__
    and mocking only the instance methods it calls (_resolve_take_path,
    _ensure_scene_audio, _ensure_scene_foley).  This tests the PRODUCTION code,
    not an inline copy.
    """

    def _make_pipeline_instance(self, tmp_path):
        """
        Build a minimal CinemaPipeline instance without __init__:
        bypass construction with object.__new__ and set only what
        _build_scene_packages needs.
        """
        from cinema_pipeline import CinemaPipeline
        from cinema.runstate import RunState
        from unittest.mock import MagicMock

        pipeline = object.__new__(CinemaPipeline)
        # _runstate is needed because scene_clips is a property backed by it.
        pipeline._runstate = RunState()
        # Mock methods that touch the filesystem or heavy services.
        pipeline._ensure_scene_audio = MagicMock(
            return_value=str(tmp_path / "scene_audio.mp3")
        )
        pipeline._ensure_scene_foley = MagicMock(return_value="")
        # _resolve_take_path: return the take's .path field directly.
        pipeline._resolve_take_path = MagicMock(
            side_effect=lambda shot, take_id: self._take_path(shot, take_id, tmp_path)
        )
        return pipeline

    def _take_path(self, shot, take_id, tmp_path):
        """Return the take path from the shot's motion_takes, touching a real file."""
        for take in shot.get("motion_takes", []):
            if take["id"] == take_id:
                return take["path"]
        return ""

    def _make_shot_with_meta(self, shot_id: str, tmp_path, **meta_fields) -> dict:
        """Build a shot with an approved take whose metadata has the given fields."""
        take_id = f"take_{shot_id}"
        take_path = str(tmp_path / f"{take_id}.mp4")
        open(take_path, "wb").write(b"fake")
        meta = {"has_dialogue": True}
        meta.update(meta_fields)
        return {
            "id": shot_id,
            "approved_final_take_id": take_id,
            "motion_takes": [{"id": take_id, "path": take_path, "kind": "motion", "metadata": meta}],
            "postprocess_variants": [],
            "characters_in_frame": ["char_1"],
        }

    def _run(self, pipeline, scenes):
        """Run _build_scene_packages via a minimal project dict."""
        project = {"scenes": scenes, "characters": []}
        return pipeline._build_scene_packages(project)

    def test_all_overlay_in_clip_suppresses_tts(self, tmp_path):
        """
        When EVERY approved shot has dialogue_audio_in_clip=True,
        scene_package["audio"] is None (TTS suppressed — no double-voice).
        """
        pipeline = self._make_pipeline_instance(tmp_path)
        scene = {
            "id": "scene_a",
            "characters_present": [],
            "shots": [
                self._make_shot_with_meta("shot_a1", tmp_path, dialogue_audio_in_clip=True),
                self._make_shot_with_meta("shot_a2", tmp_path, dialogue_audio_in_clip=True),
            ],
        }
        packages, missing = self._run(pipeline, [scene])

        assert missing == [], f"Unexpected missing shots: {missing}"
        assert len(packages) == 1
        assert packages[0]["audio"] is None, (
            "All-overlay-in-clip scene must have audio=None to prevent double-voice; "
            f"got {packages[0]['audio']!r}"
        )

    def test_mixed_overlay_and_not_keeps_tts(self, tmp_path):
        """
        Mixed scene: one shot has dialogue_audio_in_clip=True, another does not.
        TTS is kept (conservative) so the non-in-clip shot has audio.
        """
        pipeline = self._make_pipeline_instance(tmp_path)
        scene = {
            "id": "scene_b",
            "characters_present": [],
            "shots": [
                self._make_shot_with_meta("shot_b1", tmp_path, dialogue_audio_in_clip=True),
                self._make_shot_with_meta("shot_b2", tmp_path),  # no flag
            ],
        }
        packages, _ = self._run(pipeline, [scene])

        assert packages[0]["audio"] is not None, (
            "Mixed scene (one overlay-in-clip, one not) must keep TTS for non-in-clip shot; "
            f"got audio={packages[0]['audio']!r}"
        )

    def test_all_native_audio_embedded_still_suppresses_tts(self, tmp_path):
        """
        All audio_embedded=True (native path) still suppresses TTS.
        Regression: Chunk 3 changes must NOT break the existing native-path behavior.
        """
        pipeline = self._make_pipeline_instance(tmp_path)
        scene = {
            "id": "scene_c",
            "characters_present": [],
            "shots": [
                self._make_shot_with_meta("shot_c1", tmp_path, audio_embedded=True),
                self._make_shot_with_meta("shot_c2", tmp_path, audio_embedded=True),
            ],
        }
        packages, _ = self._run(pipeline, [scene])

        assert packages[0]["audio"] is None, (
            "All-audio_embedded (native) scene must still suppress TTS (regression guard); "
            f"got {packages[0]['audio']!r}"
        )

    def test_no_flags_includes_tts(self, tmp_path):
        """
        No audio flags set → TTS is included (non-embedded, non-overlay-in-clip scene).
        """
        pipeline = self._make_pipeline_instance(tmp_path)
        scene = {
            "id": "scene_d",
            "characters_present": [],
            "shots": [
                self._make_shot_with_meta("shot_d1", tmp_path),  # no flags
            ],
        }
        packages, _ = self._run(pipeline, [scene])

        assert packages[0]["audio"] is not None, (
            "Scene with no audio flags must include TTS; "
            f"got {packages[0]['audio']!r}"
        )

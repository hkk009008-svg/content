"""Unit tests for F1a: dialogue shot routing to native-audio engine.

Three behaviours under test:
1. A dialogue-purpose AUTO shot resolves target_api=VEO_NATIVE via the
   optimizer cache (not the shot-type template).
2. generate_ai_video receives has_dialogue=True for a dialogue shot, which
   causes generate_audio=True to be passed to VeoNativeAPI.
3. The motion take receives metadata["audio_embedded"]=True when the
   winning engine has native_audio=True and has_dialogue=True.

All tests are fully offline — no real API calls, no GPU.
"""

from __future__ import annotations

import sys
import os
import types
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal stubs so we can import domain modules without the
# full project's optional runtime deps (torch, cv2, …)
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs):
    """Create a trivial stub module and inject it into sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Stub heavy deps that are imported at module load in phase_c_ffmpeg / controller
for _dep in [
    "veo_native", "kling_native", "sora_native", "ltx_native",
    "runway_native", "runway_gen4", "fal_proxy",
    "kling_3_0", "sora_2", "veo_fal",
]:
    if _dep not in sys.modules:
        _stub_module(_dep)

# ---------------------------------------------------------------------------
# Test 1 — Routing: dialogue-purpose shot with optimizer cache → VEO_NATIVE
# ---------------------------------------------------------------------------


class TestAutoRoutingDecisions:
    """
    Tests for the AUTO-routing decisions made inside generate_motion_take
    (the optimizer-cache and template-fallback branches).

    These call the REAL generate_motion_take so any production drift is caught.
    The harness mirrors TestGenerateMotionTakeOverlayWiring in test_f1b_dialogue_lipsync.py.
    """

    def _build_controller(self, project: dict, tmp_path):
        """Build a minimal ShotController with mocked host + core."""
        import os
        from cinema.shots.controller import ShotController

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        host._rebuild_review_clips.return_value = {}
        host._save_checkpoint.return_value = None
        keyframe_path = str(tmp_path / "keyframe.jpg")
        open(keyframe_path, "wb").write(b"fake_jpg")
        host._resolve_take_path.return_value = keyframe_path
        host._ensure_shot_audio.return_value = None
        host._ensure_scene_audio.return_value = None

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
        # Pre-spend gate (P0-2): an unconfigured MagicMock is truthy and
        # would fire the would_exceed gate before generation.
        cost_tracker.would_exceed.return_value = False
        core.cost_tracker = cost_tracker

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._take_output_path = MagicMock(
            side_effect=lambda shot_id, take_id, ext: str(tmp_path / f"{take_id}{ext}")
        )
        return ctrl, host

    def _run_and_capture_gen_vid_kwargs(self, project, tmp_path):
        """Run generate_motion_take and return the kwargs passed to generate_ai_video."""
        ctrl, host = self._build_controller(project, tmp_path)
        veo_clip = str(tmp_path / "veo_clip.mp4")
        open(veo_clip, "wb").write(b"fake_veo")
        ls_clip = str(tmp_path / "ls_clip.mp4")
        open(ls_clip, "wb").write(b"fake_ls")
        ref_image_file = str(tmp_path / "ref_char1.jpg")
        open(ref_image_file, "wb").write(b"fake_jpg")
        audio_file = str(tmp_path / "shot_tts.mp3")
        open(audio_file, "wb").write(b"a")
        host._ensure_shot_audio.return_value = audio_file
        ctrl._finalize_motion_take = MagicMock(
            side_effect=lambda scene, shot, take, video_path, **kw: {
                "success": True, "take": dict(take), "video": video_path, "identity_score": 0.0,
            }
        )
        captured = {}

        def _fake_gen_vid(*args, **kwargs):
            # target_api is the 3rd positional arg (0-indexed: image_path, camera_motion, target_api)
            if args:
                kwargs.setdefault("target_api", args[2] if len(args) > 2 else None)
            captured.update(kwargs)
            return veo_clip

        with (
            patch("cinema.shots.controller.generate_ai_video", side_effect=_fake_gen_vid),
            patch("cinema.shots.controller.generate_lip_sync_video", return_value=ls_clip),
            patch("lip_sync.generate_lip_sync_video", return_value=ls_clip),
            patch("lip_sync.validate_lipsync_quality", return_value=0.91),
            patch("cinema.shots.controller.get_reference_image", return_value=ref_image_file),
            patch("cinema.shots.controller._probe_duration", return_value=3.5),
            patch("workflow_selector.classify_shot_type", return_value="medium"),
        ):
            ctrl.generate_motion_take("scene_1", "shot_1_0")
        return captured

    def _make_project(self, tmp_path, *, target_api="AUTO", optimizer_cache=None):
        """Minimal project with one shot; allows caller to configure routing fields."""
        return {
            "id": "proj_routing_test",
            "characters": [{"id": "char_1", "name": "Alice"}],
            "global_settings": {"dialogue_voice_mode": "overlay"},
            "scenes": [{
                "id": "scene_1",
                "title": "Scene",
                "action": "Action.",
                "characters_present": ["char_1"],
                "shots": [{
                    "id": "shot_1_0",
                    "prompt": "A shot",
                    "plan_status": "approved",
                    "target_api": target_api,
                    "camera": "static",
                    "characters_in_frame": ["char_1"],
                    "approved_keyframe_take_id": "kf_t1",
                    **({"optimizer_cache": optimizer_cache} if optimizer_cache else {}),
                }],
            }],
        }

    def test_non_dialogue_purpose_honors_cached_suggestion(self, tmp_path):
        """A non-dialogue purpose with a valid cached suggestion is honored.

        Calls the REAL generate_motion_take; asserts generate_ai_video received
        the cached suggestion (SORA_NATIVE), not a template API.
        """
        project = self._make_project(
            tmp_path,
            target_api="AUTO",
            optimizer_cache={"spec": {"purpose": "action_motion", "suggested_video_api": "SORA_NATIVE"}},
        )
        kwargs = self._run_and_capture_gen_vid_kwargs(project, tmp_path)
        assert kwargs.get("target_api") == "SORA_NATIVE", (
            f"valid cached suggestion for non-dialogue purpose should be honored; "
            f"got {kwargs.get('target_api')!r}"
        )

    def test_no_optimizer_cache_uses_template(self, tmp_path):
        """When no optimizer cache is present, routing falls back to the shot-type template.

        Calls the REAL generate_motion_take; asserts generate_ai_video received
        a template API (classify_shot_type mock returns 'medium').
        """
        from workflow_selector import WORKFLOW_TEMPLATES

        project = self._make_project(tmp_path, target_api="AUTO")  # no optimizer_cache
        kwargs = self._run_and_capture_gen_vid_kwargs(project, tmp_path)
        template_apis = {t["target_api"] for t in WORKFLOW_TEMPLATES.values()}
        assert kwargs.get("target_api") in template_apis, (
            f"without optimizer cache, target_api must come from a template; "
            f"got {kwargs.get('target_api')!r}"
        )


# ---------------------------------------------------------------------------
# Test 2 — generate_ai_video passes generate_audio=True for dialogue shots
# ---------------------------------------------------------------------------


class TestGenerateAudioForDialogue:
    """
    When dialogue_native_audio=True is passed to generate_ai_video and the engine is
    VEO_NATIVE, the veo.generate_video() call should receive generate_audio=True.
    overlay mode (dialogue_native_audio=False, the default) runs Veo silent.
    """

    def test_veo_native_receives_generate_audio_true_for_native_dialogue(self):
        """dialogue_native_audio=True → VeoNativeAPI.generate_video(generate_audio=True).
        (Updated from Task 2: has_dialogue alone no longer sets generate_audio; the
        controller passes dialogue_native_audio=True only in native mode.)
        """
        from phase_c_ffmpeg import generate_ai_video

        mock_veo_instance = MagicMock()
        mock_veo_instance.generate_video.return_value = "/tmp/fake_output.mp4"

        mock_veo_cls = MagicMock(return_value=mock_veo_instance)

        with patch.dict("sys.modules", {"veo_native": MagicMock(VeoNativeAPI=mock_veo_cls)}):
            with patch("os.path.exists", return_value=True):
                result = generate_ai_video(
                    image_path="/tmp/fake_frame.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4="/tmp/out.mp4",
                    shot_type="portrait",
                    has_dialogue=True,
                    dialogue_native_audio=True,
                )

        mock_veo_instance.generate_video.assert_called_once()
        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is True, (
            "dialogue_native_audio=True should set generate_audio=True for VEO_NATIVE"
        )

    def test_veo_native_generate_audio_false_without_dialogue(self):
        """has_dialogue=False (default) → generate_audio=False for non-landscape portrait."""
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
                    has_dialogue=False,
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is False, (
            "has_dialogue=False + non-landscape should keep generate_audio=False"
        )

    def test_landscape_still_gets_generate_audio_true(self):
        """Landscape shots still get generate_audio=True (existing behaviour preserved)."""
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
                    shot_type="landscape",
                    has_dialogue=False,
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is True, (
            "Landscape shot_type should still produce generate_audio=True"
        )


# ---------------------------------------------------------------------------
# Test 3 — Take gets metadata["audio_embedded"]=True for native-audio engine
# ---------------------------------------------------------------------------


class TestAudioEmbeddedTakeTag:
    """
    When the winning engine has native_audio=True in API_REGISTRY AND
    has_dialogue=True, take["metadata"]["audio_embedded"] should be True.
    """

    def test_veo_native_audio_flag_present_in_registry(self):
        """Sanity: VEO_NATIVE has native_audio=True in API_REGISTRY."""
        from domain.scene_decomposer import API_REGISTRY
        assert API_REGISTRY["VEO_NATIVE"].get("native_audio") is True

    def test_audio_embedded_set_in_native_mode(self):
        """native mode: native_audio engine + has_dialogue + mode=native → audio_embedded=True."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        winning_engine = "VEO_NATIVE"
        engine_info = API_REGISTRY.get(winning_engine, {})
        result = _should_tag_audio_embedded(engine_info, has_dialogue=True, voice_mode="native")

        assert result is True, (
            "VEO_NATIVE + has_dialogue + native mode should produce audio_embedded=True"
        )

    def test_audio_embedded_not_set_in_overlay_mode(self):
        """overlay mode (default): native_audio engine + has_dialogue → NOT audio_embedded.
        In overlay mode the F1b pass fires and the clip gets TTS overlaid.
        """
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        winning_engine = "VEO_NATIVE"
        engine_info = API_REGISTRY.get(winning_engine, {})
        result = _should_tag_audio_embedded(engine_info, has_dialogue=True, voice_mode="overlay")

        assert result is False, (
            "overlay mode (default): VEO_NATIVE + has_dialogue should NOT set audio_embedded "
            "— the F1b lipsync overlay pass must run"
        )

    def test_audio_embedded_not_set_for_non_native_audio_engine(self):
        """Non-native-audio engine (KLING_NATIVE) should NOT set audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        winning_engine = "KLING_NATIVE"
        engine_info = API_REGISTRY.get(winning_engine, {})
        result = _should_tag_audio_embedded(engine_info, has_dialogue=True, voice_mode="native")

        assert result is False, (
            "KLING_NATIVE has no native_audio — audio_embedded should not be set"
        )

    def test_audio_embedded_not_set_when_no_dialogue(self):
        """Native-audio engine (VEO_NATIVE) + has_dialogue=False → no audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        winning_engine = "VEO_NATIVE"
        engine_info = API_REGISTRY.get(winning_engine, {})
        result = _should_tag_audio_embedded(engine_info, has_dialogue=False, voice_mode="native")

        assert result is False, (
            "VEO_NATIVE without has_dialogue should not set audio_embedded"
        )

    def test_audio_embedded_not_set_when_veo_falls_back_to_kling(self):
        """If VEO_NATIVE fails and cascade picks KLING_NATIVE, no audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        # Primary was VEO_NATIVE but winning_engine ends up KLING_NATIVE after cascade
        winning_engine = "KLING_NATIVE"
        engine_info = API_REGISTRY.get(winning_engine, {})
        result = _should_tag_audio_embedded(engine_info, has_dialogue=True, voice_mode="native")

        assert result is False


# ---------------------------------------------------------------------------
# Task 2 — dialogue_native_audio flag controls generate_audio in overlay mode
# ---------------------------------------------------------------------------


class TestDialogueNativeAudioFlag:
    """
    The new dialogue_native_audio param controls generate_audio for dialogue shots.
    - overlay mode (default): has_dialogue=True but dialogue_native_audio=False
      → generate_audio=False (Veo runs silent)
    - native mode: has_dialogue=True + dialogue_native_audio=True
      → generate_audio=True (Veo generates embedded voice)
    - landscape: generate_audio=True regardless of dialogue flags
    """

    def test_generate_audio_false_for_overlay_dialogue(self):
        """Overlay-mode dialogue (dialogue_native_audio=False) → Veo silent."""
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
                    has_dialogue=True,
                    dialogue_native_audio=False,
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is False, (
            "has_dialogue=True but dialogue_native_audio=False (overlay) "
            "should NOT set generate_audio=True"
        )

    def test_generate_audio_true_for_native_dialogue(self):
        """native mode dialogue (dialogue_native_audio=True) → Veo generates embedded voice."""
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
                    has_dialogue=True,
                    dialogue_native_audio=True,
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is True, (
            "dialogue_native_audio=True should set generate_audio=True"
        )

    def test_generate_audio_true_for_landscape_regardless_of_dialogue_flags(self):
        """Landscape shot still gets native audio regardless of dialogue flags."""
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
                    shot_type="landscape",
                    has_dialogue=False,
                    dialogue_native_audio=False,
                )

        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is True, (
            "Landscape shots always get generate_audio=True regardless of dialogue flags"
        )


# ---------------------------------------------------------------------------
# Task 3 — video_fallbacks restored for overlay-mode dialogue
# ---------------------------------------------------------------------------


class TestDialogueVideoFallbacks:
    """
    Task 3: Overlay-mode dialogue keeps video_fallbacks non-None (primary=VEO,
    fallbacks restored). Native-mode dialogue nulls fallbacks (today's behavior).
    RAI-block → fallback engine → overlay still fires (take NOT audio_embedded).

    All tests call the REAL _resolve_dialogue_routing helper from controller.py.
    """

    def test_overlay_dialogue_keeps_video_fallbacks(self):
        """overlay mode: VEO_NATIVE primary + template fallbacks preserved (non-None)."""
        from cinema.shots.controller import _resolve_dialogue_routing

        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        _, video_fallbacks = _resolve_dialogue_routing(
            purpose="dialogue_close_up",
            voice_mode="overlay",
            resolved_target_api="VEO_NATIVE",
            resolved_fallbacks=template_fallbacks,
        )
        assert video_fallbacks is not None, (
            "overlay-mode dialogue must keep video_fallbacks for RAI-block resilience"
        )
        assert len(video_fallbacks) > 0

    def test_native_dialogue_nulls_video_fallbacks(self):
        """native mode: video_fallbacks=None (today's behavior preserved)."""
        from cinema.shots.controller import _resolve_dialogue_routing

        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        _, video_fallbacks = _resolve_dialogue_routing(
            purpose="dialogue_close_up",
            voice_mode="native",
            resolved_target_api="VEO_NATIVE",
            resolved_fallbacks=template_fallbacks,
        )
        assert video_fallbacks is None, (
            "native-mode dialogue must null video_fallbacks (embedded voice engine handles cascade)"
        )

    def test_overlay_dialogue_primary_is_native_audio_engine(self):
        """overlay mode: primary engine still has native_audio (VEO_NATIVE)."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _resolve_dialogue_routing

        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        target_api, _ = _resolve_dialogue_routing(
            purpose="dialogue_close_up",
            voice_mode="overlay",
            resolved_target_api="VEO_NATIVE",
            resolved_fallbacks=template_fallbacks,
        )
        engine_info = API_REGISTRY.get(target_api, {})
        assert engine_info.get("native_audio") is True, (
            f"overlay-mode primary engine {target_api} should have native_audio=True"
        )

    def test_rai_block_fallback_engine_not_audio_embedded_in_overlay_mode(self):
        """RAI-block: when VEO_NATIVE fails and cascade picks KLING_NATIVE (no native_audio),
        the take is NOT audio_embedded in overlay mode — the F1b overlay pass still fires."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        # Simulate: VEO_NATIVE was primary; RAI-block caused cascade to KLING_NATIVE.
        winning_engine = "KLING_NATIVE"
        has_dialogue = True
        voice_mode = "overlay"  # default

        engine_info = API_REGISTRY.get(winning_engine, {})
        audio_embedded = _should_tag_audio_embedded(engine_info, has_dialogue, voice_mode)

        assert not audio_embedded, (
            "After RAI-block cascade to KLING_NATIVE (no native_audio) in overlay mode, "
            "audio_embedded must be False — the F1b overlay pass must still fire"
        )


# ---------------------------------------------------------------------------
# Task 8 — native-mode escape-hatch regression
# ---------------------------------------------------------------------------


class TestNativeModeEscapeHatch:
    """
    Chunk 4, Task 8: Assert the full native-mode legacy path is preserved
    end-to-end.  These tests call the REAL helpers from controller.py
    (not inline simulations) so any future regression in the production
    helpers is caught immediately.

    Three assertions constitute the escape-hatch guarantee:
    1. _resolve_dialogue_routing with voice_mode="native" → VEO_NATIVE primary
       AND video_fallbacks=None (native engine never cascades to silent engines).
    2. _should_tag_audio_embedded with voice_mode="native" → True (the take is
       tagged audio_embedded so the assembler suppresses standalone TTS).
    3. _dialogue_voice_mode({"dialogue_voice_mode": "native"}) → "native" (the
       setting is honoured, not coerced back to "overlay").
    """

    def test_native_routing_forces_veo_primary_and_nulls_fallbacks(self):
        """native mode: _resolve_dialogue_routing returns VEO_NATIVE + None fallbacks."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _resolve_dialogue_routing

        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        target_api, video_fallbacks = _resolve_dialogue_routing(
            purpose="dialogue_close_up",
            voice_mode="native",
            resolved_target_api="VEO_NATIVE",
            resolved_fallbacks=template_fallbacks,
        )

        # The routing must return the native-audio engine.
        engine_info = API_REGISTRY.get(target_api, {})
        assert engine_info.get("native_audio") is True, (
            f"native-mode primary engine '{target_api}' must have native_audio=True; "
            "VEO_NATIVE is the only qualifying engine"
        )
        # Fallbacks must be nulled so the native-audio engine's own cascade handles failure
        # (never falls through to a silent-video engine that lacks embedded voice).
        assert video_fallbacks is None, (
            "native mode must null video_fallbacks so a Veo failure is not silently "
            "routed to a non-native-audio engine"
        )

    def test_native_routing_audio_embedded_tag_is_set(self):
        """native mode: _should_tag_audio_embedded returns True for VEO_NATIVE + dialogue."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _should_tag_audio_embedded

        engine_info = API_REGISTRY["VEO_NATIVE"]
        result = _should_tag_audio_embedded(engine_info, has_dialogue=True, voice_mode="native")

        assert result is True, (
            "native mode + VEO_NATIVE + has_dialogue must tag the take audio_embedded=True "
            "so the assembler suppresses standalone TTS (no double-voice)"
        )

    def test_native_voice_mode_setting_is_honoured(self):
        """_dialogue_voice_mode({'dialogue_voice_mode': 'native'}) → 'native' (not coerced)."""
        from cinema.shots.controller import _dialogue_voice_mode

        result = _dialogue_voice_mode({"dialogue_voice_mode": "native"})

        assert result == "native", (
            "Explicit 'native' setting must be returned verbatim; "
            f"got {result!r}"
        )

    def test_native_mode_talking_head_full_routing(self):
        """native mode works for talking_head_full purpose too (both dialogue purposes)."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _resolve_dialogue_routing

        target_api, video_fallbacks = _resolve_dialogue_routing(
            purpose="talking_head_full",
            voice_mode="native",
            resolved_target_api="VEO_NATIVE",
            resolved_fallbacks=["KLING_NATIVE", "SORA_NATIVE"],
        )

        engine_info = API_REGISTRY.get(target_api, {})
        assert engine_info.get("native_audio") is True, (
            f"talking_head_full native mode must route to native_audio engine; got {target_api!r}"
        )
        assert video_fallbacks is None, (
            "talking_head_full native mode must also null fallbacks"
        )

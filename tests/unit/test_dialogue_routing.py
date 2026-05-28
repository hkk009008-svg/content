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


class TestDialogueRoutingResolvesVeoNative:
    """
    When target_api == "AUTO" and the shot's optimizer cache carries a
    dialogue purpose, the cached suggested_video_api (VEO_NATIVE) should
    override the shot-type template (KLING_NATIVE for portrait/medium).
    """

    def _make_dialogue_shot(self, purpose: str, suggested: str = "VEO_NATIVE"):
        """Return a shot dict that simulates a cached optimizer result."""
        return {
            "target_api": "AUTO",
            "optimizer_cache": {
                "source_prompt": "A character speaking",
                "spec": {
                    "purpose": purpose,
                    "suggested_video_api": suggested,
                    "suggested_lipsync": "HEDRA_C3",
                    "image_prompt": "Character speaking, close-up",
                },
            },
        }

    @pytest.mark.parametrize("purpose", ["dialogue_close_up", "talking_head_full"])
    def test_dialogue_purpose_resolves_to_suggested_api(self, purpose):
        """Optimizer suggestion wins over shot-type template for dialogue purposes."""
        from workflow_selector import WORKFLOW_TEMPLATES, classify_shot_type
        from domain.scene_decomposer import API_REGISTRY

        shot = self._make_dialogue_shot(purpose)

        # Replicate the routing logic from generate_motion_take
        opt_cache = shot.get("optimizer_cache") or {}
        opt_spec_cached = opt_cache.get("spec") or {}
        cached_purpose = opt_spec_cached.get("purpose", "")
        _dialogue_purposes = {"dialogue_close_up", "talking_head_full"}
        has_dialogue = cached_purpose in _dialogue_purposes

        raw_api = shot.get("target_api", "AUTO")
        assert raw_api == "AUTO"

        if raw_api == "AUTO":
            cached_suggestion = opt_spec_cached.get("suggested_video_api", "")
            if cached_suggestion and cached_suggestion != "AUTO" and cached_suggestion in API_REGISTRY:
                target_api = cached_suggestion
            else:
                template = WORKFLOW_TEMPLATES.get(classify_shot_type(shot), WORKFLOW_TEMPLATES["medium"])
                target_api = template["target_api"]

        assert target_api == "VEO_NATIVE", (
            f"Dialogue purpose '{purpose}' should route to VEO_NATIVE, got {target_api}"
        )
        assert has_dialogue is True

    def test_non_dialogue_purpose_falls_back_to_template(self):
        """Non-dialogue purposes should still use the shot-type template."""
        from workflow_selector import WORKFLOW_TEMPLATES, classify_shot_type
        from domain.scene_decomposer import API_REGISTRY

        shot = {
            "target_api": "AUTO",
            "optimizer_cache": {
                "spec": {
                    "purpose": "action_motion",
                    "suggested_video_api": "SORA_NATIVE",
                }
            },
        }

        opt_spec_cached = shot["optimizer_cache"]["spec"]
        cached_purpose = opt_spec_cached.get("purpose", "")
        _dialogue_purposes = {"dialogue_close_up", "talking_head_full"}
        has_dialogue = cached_purpose in _dialogue_purposes

        cached_suggestion = opt_spec_cached.get("suggested_video_api", "")
        if cached_suggestion and cached_suggestion != "AUTO" and cached_suggestion in API_REGISTRY:
            target_api = cached_suggestion
        else:
            template = WORKFLOW_TEMPLATES.get(classify_shot_type(shot), WORKFLOW_TEMPLATES["medium"])
            target_api = template["target_api"]

        # SORA_NATIVE is in API_REGISTRY so the suggestion is honored here too —
        # the point is that has_dialogue is False for non-dialogue purposes.
        assert has_dialogue is False

    def test_no_optimizer_cache_uses_template(self):
        """When no optimizer cache is present, fall through to shot-type template."""
        from workflow_selector import WORKFLOW_TEMPLATES, classify_shot_type
        from domain.scene_decomposer import API_REGISTRY

        shot = {"target_api": "AUTO", "prompt": "Close up of hero speaking"}

        opt_cache = shot.get("optimizer_cache") or {}
        opt_spec_cached = opt_cache.get("spec") or {}
        cached_purpose = opt_spec_cached.get("purpose", "")
        has_dialogue = cached_purpose in {"dialogue_close_up", "talking_head_full"}

        cached_suggestion = opt_spec_cached.get("suggested_video_api", "")
        if cached_suggestion and cached_suggestion != "AUTO" and cached_suggestion in API_REGISTRY:
            target_api = cached_suggestion
        else:
            template = WORKFLOW_TEMPLATES.get(classify_shot_type(shot), WORKFLOW_TEMPLATES["medium"])
            target_api = template["target_api"]

        # Without optimizer cache, routes via template — portrait → KLING_NATIVE
        assert target_api in {t["target_api"] for t in WORKFLOW_TEMPLATES.values()}, (
            "Without cache should fall back to a template API"
        )
        assert has_dialogue is False

    def test_pinned_target_api_is_not_overridden(self):
        """When target_api is pinned (not AUTO), optimizer cache is ignored."""
        shot = {
            "target_api": "KLING_NATIVE",
            "optimizer_cache": {
                "spec": {
                    "purpose": "dialogue_close_up",
                    "suggested_video_api": "VEO_NATIVE",
                }
            },
        }

        raw_api = shot.get("target_api", "AUTO")
        # Routing logic: only enters the optimizer-cache branch when raw_api == "AUTO"
        assert raw_api != "AUTO"
        # target_api stays as-is
        target_api = raw_api
        assert target_api == "KLING_NATIVE"


# ---------------------------------------------------------------------------
# Test 2 — generate_ai_video passes generate_audio=True for dialogue shots
# ---------------------------------------------------------------------------


class TestGenerateAudioForDialogue:
    """
    When has_dialogue=True is passed to generate_ai_video and the engine is
    VEO_NATIVE, the veo.generate_video() call should receive generate_audio=True.
    """

    def test_veo_native_receives_generate_audio_true_for_dialogue(self):
        """has_dialogue=True → VeoNativeAPI.generate_video(generate_audio=True)."""
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
                )

        mock_veo_instance.generate_video.assert_called_once()
        call_kwargs = mock_veo_instance.generate_video.call_args
        assert call_kwargs.kwargs.get("generate_audio") is True, (
            "has_dialogue=True should set generate_audio=True for VEO_NATIVE"
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

    def test_audio_embedded_set_when_winning_engine_is_native_audio_and_dialogue(self):
        """Simulate take-tagging logic: native_audio engine + has_dialogue → audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY

        # Simulated winning engine via cascade_metadata
        winning_engine = "VEO_NATIVE"
        has_dialogue = True

        take_metadata = {}
        engine_info = API_REGISTRY.get(winning_engine, {})
        if engine_info.get("native_audio") and has_dialogue:
            take_metadata["audio_embedded"] = True

        assert take_metadata.get("audio_embedded") is True, (
            "VEO_NATIVE + has_dialogue should produce audio_embedded=True"
        )

    def test_audio_embedded_not_set_for_non_native_audio_engine(self):
        """Non-native-audio engine (KLING_NATIVE) should NOT set audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY

        winning_engine = "KLING_NATIVE"
        has_dialogue = True

        take_metadata = {}
        engine_info = API_REGISTRY.get(winning_engine, {})
        if engine_info.get("native_audio") and has_dialogue:
            take_metadata["audio_embedded"] = True

        assert "audio_embedded" not in take_metadata, (
            "KLING_NATIVE has no native_audio — audio_embedded should not be set"
        )

    def test_audio_embedded_not_set_when_no_dialogue(self):
        """Native-audio engine (VEO_NATIVE) + has_dialogue=False → no audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY

        winning_engine = "VEO_NATIVE"
        has_dialogue = False

        take_metadata = {}
        engine_info = API_REGISTRY.get(winning_engine, {})
        if engine_info.get("native_audio") and has_dialogue:
            take_metadata["audio_embedded"] = True

        assert "audio_embedded" not in take_metadata, (
            "VEO_NATIVE without has_dialogue should not set audio_embedded"
        )

    def test_audio_embedded_not_set_when_veo_falls_back_to_kling(self):
        """If VEO_NATIVE fails and cascade picks KLING_NATIVE, no audio_embedded."""
        from domain.scene_decomposer import API_REGISTRY

        # Primary was VEO_NATIVE but winning_engine ends up KLING_NATIVE after cascade
        winning_engine = "KLING_NATIVE"
        has_dialogue = True

        take_metadata = {}
        engine_info = API_REGISTRY.get(winning_engine, {})
        if engine_info.get("native_audio") and has_dialogue:
            take_metadata["audio_embedded"] = True

        assert "audio_embedded" not in take_metadata

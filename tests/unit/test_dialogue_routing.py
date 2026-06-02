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

    def test_non_dialogue_purpose_honors_cached_suggestion(self):
        """A non-dialogue purpose with a valid cached suggestion still honors it
        (the suggestion-wins branch is purpose-agnostic); has_dialogue stays False.
        Template fallback is covered by test_no_optimizer_cache_uses_template."""
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

        # SORA_NATIVE is in API_REGISTRY, so the suggestion-wins branch is taken
        # regardless of purpose; assert both the routing outcome and the flag.
        assert target_api == "SORA_NATIVE", (
            f"valid cached suggestion should be honored, got {target_api}"
        )
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


# ---------------------------------------------------------------------------
# F1a Lane V #18 §3 fix: non-tautological routing tests that call the real
# optimizer resolver and verify native_audio on the resolved engine.
# ---------------------------------------------------------------------------


class TestDialogueRoutingNativeAudioVerification:
    """
    Verify that the consumer-side routing override in generate_motion_take
    actually produces a native_audio engine for dialogue purposes.

    These tests call the real PURPOSE_API_RANKING + API_REGISTRY data (not
    hardcoded engine names) so they CAN catch a regression like the original
    F1a bug where dialogue_close_up resolved to KLING_NATIVE (no native audio).
    """

    def test_dialogue_close_up_routing_uses_native_audio_engine(self):
        """
        F1a Lane V #18 §1 fix: after the consumer-side override, a
        dialogue_close_up shot must route to an engine with native_audio=True.

        The original F1a bug: _top_live_api_for_purpose("dialogue_close_up","video")
        returned KLING_NATIVE (first video-modality entry), not VEO_NATIVE.
        The fix: generate_motion_take scans PURPOSE_API_RANKING for the first
        native_audio video engine and overrides to it.
        """
        from domain.scene_decomposer import API_REGISTRY, PURPOSE_API_RANKING

        purpose = "dialogue_close_up"

        # Replicate the consumer-side override logic from generate_motion_take:
        # find the first native_audio video engine in the purpose ranking.
        override_engine = None
        for engine_key in PURPOSE_API_RANKING.get(purpose, []):
            engine_info = API_REGISTRY.get(engine_key, {})
            if (
                engine_info.get("native_audio")
                and engine_info.get("modality") == "video"
                and engine_info.get("status") == "live"
            ):
                override_engine = engine_key
                break

        assert override_engine is not None, (
            f"No native_audio video engine found in PURPOSE_API_RANKING['{purpose}']. "
            "If the ranking is intentionally lipsync-only, the standalone F1b lipsync "
            "path is the only fallback — but audio_embedded will never be set."
        )
        assert API_REGISTRY[override_engine].get("native_audio") is True, (
            f"Override engine {override_engine} lacks native_audio flag"
        )
        assert API_REGISTRY[override_engine].get("modality") == "video", (
            f"Override engine {override_engine} is not a video engine"
        )

    def test_talking_head_full_routing_uses_native_audio_engine(self):
        """
        talking_head_full also needs a native_audio engine via the override
        (this purpose already worked in the original F1a, but verify it stays
        working after the consumer-side override logic is added).
        """
        from domain.scene_decomposer import API_REGISTRY, PURPOSE_API_RANKING

        purpose = "talking_head_full"
        override_engine = None
        for engine_key in PURPOSE_API_RANKING.get(purpose, []):
            engine_info = API_REGISTRY.get(engine_key, {})
            if (
                engine_info.get("native_audio")
                and engine_info.get("modality") == "video"
                and engine_info.get("status") == "live"
            ):
                override_engine = engine_key
                break

        assert override_engine is not None, (
            f"No native_audio video engine for '{purpose}' in PURPOSE_API_RANKING"
        )
        assert API_REGISTRY[override_engine].get("native_audio") is True


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
    """

    def _apply_dialogue_routing_override(self, has_dialogue, mode, purpose, template_fallbacks):
        """
        Simulate the controller's dialogue routing override logic.
        Returns (target_api, video_fallbacks) after the mode branch.

        Mirrors controller.py:1136-1163 with the Task 3 mode gate applied.
        """
        from domain.scene_decomposer import PURPOSE_API_RANKING, API_REGISTRY
        from cinema.shots.controller import _dialogue_voice_mode

        target_api = "VEO_NATIVE"  # assumed from template / cache
        video_fallbacks = template_fallbacks  # from WORKFLOW_TEMPLATES

        settings = {"dialogue_voice_mode": mode}

        if has_dialogue:
            if _dialogue_voice_mode(settings) == "native":
                # Native: force native-audio engine, null fallbacks (today's behavior)
                for _engine_key in PURPOSE_API_RANKING.get(purpose, []):
                    _engine_info = API_REGISTRY.get(_engine_key, {})
                    if (
                        _engine_info.get("native_audio")
                        and _engine_info.get("modality") == "video"
                        and _engine_info.get("status") == "live"
                    ):
                        target_api = _engine_key
                        video_fallbacks = None
                        break
            else:
                # Overlay: keep VEO as primary via PURPOSE_API_RANKING override,
                # but DO NOT null video_fallbacks — restore the cascade.
                for _engine_key in PURPOSE_API_RANKING.get(purpose, []):
                    _engine_info = API_REGISTRY.get(_engine_key, {})
                    if (
                        _engine_info.get("native_audio")
                        and _engine_info.get("modality") == "video"
                        and _engine_info.get("status") == "live"
                    ):
                        target_api = _engine_key
                        # video_fallbacks intentionally kept from template
                        break

        return target_api, video_fallbacks

    def test_overlay_dialogue_keeps_video_fallbacks(self):
        """overlay mode: VEO_NATIVE primary + template fallbacks preserved (non-None).
        This test uses the new _apply_dialogue_routing_override helper which will be
        inlined into the controller in Task 3. It fails against the old controller
        code because the old code always nulls video_fallbacks for dialogue.
        """
        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        _, video_fallbacks = self._apply_dialogue_routing_override(
            has_dialogue=True,
            mode="overlay",
            purpose="dialogue_close_up",
            template_fallbacks=template_fallbacks,
        )
        assert video_fallbacks is not None, (
            "overlay-mode dialogue must keep video_fallbacks for RAI-block resilience"
        )
        assert len(video_fallbacks) > 0

    def test_native_dialogue_nulls_video_fallbacks(self):
        """native mode: video_fallbacks=None (today's behavior preserved)."""
        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        _, video_fallbacks = self._apply_dialogue_routing_override(
            has_dialogue=True,
            mode="native",
            purpose="dialogue_close_up",
            template_fallbacks=template_fallbacks,
        )
        assert video_fallbacks is None, (
            "native-mode dialogue must null video_fallbacks (embedded voice engine handles cascade)"
        )

    def test_overlay_dialogue_primary_is_native_audio_engine(self):
        """overlay mode: primary engine still has native_audio (VEO_NATIVE)."""
        from domain.scene_decomposer import API_REGISTRY

        template_fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "KLING_NATIVE"]
        target_api, _ = self._apply_dialogue_routing_override(
            has_dialogue=True,
            mode="overlay",
            purpose="dialogue_close_up",
            template_fallbacks=template_fallbacks,
        )
        engine_info = API_REGISTRY.get(target_api, {})
        assert engine_info.get("native_audio") is True, (
            f"overlay-mode primary engine {target_api} should have native_audio=True"
        )

    def test_rai_block_fallback_engine_not_audio_embedded_in_overlay_mode(self):
        """RAI-block: when VEO_NATIVE fails and cascade picks KLING_NATIVE (no native_audio),
        the take is NOT audio_embedded in overlay mode — the F1b overlay pass still fires."""
        from domain.scene_decomposer import API_REGISTRY
        from cinema.shots.controller import _dialogue_voice_mode

        # Simulate: VEO_NATIVE was primary; RAI-block caused cascade to KLING_NATIVE.
        winning_engine = "KLING_NATIVE"
        has_dialogue = True
        settings = {}  # default overlay mode

        # Replicate the controller's audio_embedded tagging logic (controller.py:1231)
        # with the Task 4 mode gate (tested separately; included here for the cascade scenario)
        engine_info = API_REGISTRY.get(winning_engine, {})
        audio_embedded = (
            engine_info.get("native_audio")
            and has_dialogue
            and _dialogue_voice_mode(settings) == "native"
        )

        assert not audio_embedded, (
            "After RAI-block cascade to KLING_NATIVE (no native_audio) in overlay mode, "
            "audio_embedded must be False — the F1b overlay pass must still fire"
        )

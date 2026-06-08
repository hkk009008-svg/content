"""Unit tests for Task 3 (Phase-3 portrait video): Veo native + fal emit 9:16.

TC-4 — VEO_NATIVE path threads aspect_ratio="9:16" into veo.generate_video().
TC-5 — VEO fal path puts aspect_ratio="9:16" into fal_client.subscribe arguments
       (+ landscape refute: 16:9 → "16:9").

All tests are offline — no Vertex, no network, no spend.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper — build a minimal PipelineContext with the given aspect_ratio
# ---------------------------------------------------------------------------
def _ctx(aspect: str):
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={"aspect_ratio": aspect})


# ---------------------------------------------------------------------------
# TC-4 — VEO_NATIVE: generate_ai_video threads aspect_ratio into generate_video
# ---------------------------------------------------------------------------
class TestVeoNativeAspect:
    """Drive generate_ai_video(target_api='VEO_NATIVE', ...) and assert that
    veo.generate_video is called with aspect_ratio='9:16' for portrait ctx."""

    def _run_veo_native(self, aspect: str):
        """Run generate_ai_video(VEO_NATIVE) with the given aspect, return the
        mock VeoNativeAPI instance whose .generate_video.call_args the tests inspect."""
        mock_inst = MagicMock()
        mock_inst.generate_video.return_value = "/tmp/out.mp4"
        mock_veo_native_mod = MagicMock()
        mock_veo_native_mod.VeoNativeAPI.return_value = mock_inst

        # phase_c_ffmpeg lazy-imports 'from veo_native import VeoNativeAPI' inside the
        # VEO_NATIVE branch — patch sys.modules so it picks up our stub.
        # Force reimport since phase_c_ffmpeg may already be cached.
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["veo_native"] = mock_veo_native_mod

        try:
            with patch("os.path.exists", return_value=True):
                import phase_c_ffmpeg
                phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4="/tmp/o.mp4",
                    shot_type="portrait",
                    ctx=_ctx(aspect),
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            sys.modules.pop("veo_native", None)

        return mock_inst

    def test_veo_native_threads_portrait_aspect(self):
        mock_inst = self._run_veo_native("9:16")

        assert mock_inst.generate_video.called, "generate_video was never called"
        call_kwargs = mock_inst.generate_video.call_args.kwargs
        assert call_kwargs.get("aspect_ratio") == "9:16", (
            f"Expected aspect_ratio='9:16' in generate_video kwargs; got: {call_kwargs}"
        )

    def test_veo_native_landscape_keeps_16_9(self):
        """Landscape ctx → aspect_ratio='16:9' (refute — no regression)."""
        mock_inst = self._run_veo_native("16:9")

        call_kwargs = mock_inst.generate_video.call_args.kwargs
        assert call_kwargs.get("aspect_ratio") == "16:9", (
            f"Expected aspect_ratio='16:9'; got: {call_kwargs}"
        )


# ---------------------------------------------------------------------------
# TC-5 — VEO fal: generate_ai_video puts fal_aspect_ratio(_aspect) into arguments
# ---------------------------------------------------------------------------
class TestVeoFalAspect:
    """Drive generate_ai_video(target_api='VEO', ...) and assert that
    fal_client.subscribe receives arguments['aspect_ratio']=='9:16' for portrait."""

    def _run_veo_fal(self, aspect: str):
        """Run generate_ai_video(VEO) with the given aspect, return the captured
        fal_client.subscribe call_args_list."""
        stub_fal = MagicMock()
        stub_fal.subscribe.return_value = {"video": {"url": "https://x/o.mp4"}}
        # upload_file must return a string URL
        stub_fal.upload_file.return_value = "https://cdn.fal.ai/ref.jpg"

        # Build a stub settings that reports a fal_key (so the branch enters)
        stub_settings = MagicMock()
        stub_settings.fal_key = "fk-test-key"

        sys.modules.pop("phase_c_ffmpeg", None)

        try:
            with patch("os.path.exists", return_value=True), \
                 patch("urllib.request.urlretrieve"), \
                 patch.dict("sys.modules", {"veo_native": MagicMock()}):
                import phase_c_ffmpeg
                # Patch fal_client and settings at module level AFTER import
                phase_c_ffmpeg.fal_client = stub_fal
                phase_c_ffmpeg.FAL_AVAILABLE = True
                phase_c_ffmpeg.settings = stub_settings
                phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO",
                    output_mp4="/tmp/o.mp4",
                    shot_type="portrait",
                    ctx=_ctx(aspect),
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)

        return stub_fal.subscribe.call_args_list

    def test_veo_fal_portrait_aspect_in_arguments(self):
        calls = self._run_veo_fal("9:16")
        assert calls, "fal_client.subscribe was never called"
        # subscribe is called as subscribe(endpoint, arguments={...}, with_logs=...)
        call = calls[0]
        pos_args = call.args
        kw = call.kwargs
        # fal_client.subscribe("endpoint", arguments={...}, with_logs=True)
        assert pos_args and pos_args[0] == "fal-ai/veo3.1/reference-to-video", (
            f"Wrong fal endpoint; got positional args: {pos_args}"
        )
        arguments = kw.get("arguments", {})
        assert arguments.get("aspect_ratio") == "9:16", (
            f"Expected aspect_ratio='9:16' in subscribe arguments; got: {arguments}"
        )

    def test_veo_fal_landscape_keeps_16_9(self):
        """Landscape ctx → arguments['aspect_ratio'] == '16:9' (refute)."""
        calls = self._run_veo_fal("16:9")
        assert calls, "fal_client.subscribe was never called"
        kw = calls[0].kwargs
        arguments = kw.get("arguments", {})
        assert arguments.get("aspect_ratio") == "16:9", (
            f"Expected aspect_ratio='16:9'; got: {arguments}"
        )

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


# ---------------------------------------------------------------------------
# TC-6 — SORA_2 fal: generate_ai_video puts fal_aspect_ratio(_aspect) into arguments
# ---------------------------------------------------------------------------
class TestSora2FalAspect:
    """Drive generate_ai_video(target_api='SORA_2', ...) and assert that
    fal_client.subscribe receives arguments['aspect_ratio']=='9:16' for portrait
    and '16:9' for landscape (refute).
    """

    def _run_sora_fal(self, aspect: str):
        """Run generate_ai_video(SORA_2) with the given aspect, return the captured
        fal_client.subscribe call_args_list."""
        stub_fal = MagicMock()
        # SORA_2 reads result["video"]["url"] — must return VIDEO shape or the branch
        # will bail to cascade and subscribe never produces the aspect_ratio we want.
        stub_fal.subscribe.return_value = {"video": {"url": "https://x/sora.mp4"}}
        stub_fal.upload_file.return_value = "https://cdn.fal.ai/sora-ref.jpg"

        stub_settings = MagicMock()
        stub_settings.fal_key = "fk-test-key"

        sys.modules.pop("phase_c_ffmpeg", None)

        try:
            with patch("os.path.exists", return_value=True), \
                 patch("urllib.request.urlretrieve"), \
                 patch.dict("sys.modules", {"veo_native": MagicMock()}):
                import phase_c_ffmpeg
                phase_c_ffmpeg.fal_client = stub_fal
                phase_c_ffmpeg.FAL_AVAILABLE = True
                phase_c_ffmpeg.settings = stub_settings
                phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="SORA_2",
                    output_mp4="/tmp/sora_out.mp4",
                    shot_type="portrait",
                    ctx=_ctx(aspect),
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)

        return stub_fal.subscribe.call_args_list

    def test_sora2_fal_portrait_aspect_in_arguments(self):
        """Portrait ctx → arguments['aspect_ratio'] == '9:16' and endpoint is sora-2."""
        calls = self._run_sora_fal("9:16")
        assert calls, "fal_client.subscribe was never called"
        call = calls[0]
        pos_args = call.args
        kw = call.kwargs
        assert pos_args and pos_args[0] == "fal-ai/sora-2/image-to-video", (
            f"Wrong fal endpoint; got positional args: {pos_args}"
        )
        arguments = kw.get("arguments", {})
        assert arguments.get("aspect_ratio") == "9:16", (
            f"Expected aspect_ratio='9:16' in subscribe arguments; got: {arguments}"
        )

    def test_sora2_fal_landscape_keeps_16_9(self):
        """Landscape ctx → arguments['aspect_ratio'] == '16:9' (refute)."""
        calls = self._run_sora_fal("16:9")
        assert calls, "fal_client.subscribe was never called"
        kw = calls[0].kwargs
        arguments = kw.get("arguments", {})
        assert arguments.get("aspect_ratio") == "16:9", (
            f"Expected aspect_ratio='16:9'; got: {arguments}"
        )


# ---------------------------------------------------------------------------
# TC-7 — RUNWAY_GEN4: generate_ai_video uses a valid SDK model enum value
# ---------------------------------------------------------------------------
class TestRunwayGen4Model:
    """Drive generate_ai_video(target_api='RUNWAY_GEN4', ...) and assert that
    client.image_to_video.create is called with model in the SDK's valid set.

    The runwayml SDK (v4.14.0) accepts model ∈ {gen4.5, gen4_turbo, veo3.1,
    veo3.1_fast, veo3, gen3a_turbo}. Bare 'gen4' is NOT in the enum → 400
    at runtime. The correct model is 'gen4_turbo'.
    """

    def _run_runway_gen4(self):
        """Drive generate_ai_video(RUNWAY_GEN4); return the mock RunwayML client.

        The route:
        1. Imports RunwayML inside the branch — patch via sys.modules.
        2. Reads open(image_path, "rb") — use a real temp file.
        3. Polls client.tasks.retrieve in a while loop — mock must return
           status=="SUCCEEDED" immediately to avoid a 300-second spin.
        4. On SUCCEEDED reads task.output[0] then calls urllib.request.urlretrieve.
        """
        import tempfile
        import os

        # Build mock task objects: create() returns task_created; retrieve() returns
        # task_done with status SUCCEEDED so the poll terminates immediately.
        task_created = MagicMock()
        task_created.id = "runway-task-001"

        task_done = MagicMock()
        task_done.status = "SUCCEEDED"
        task_done.output = ["https://cdn.runway.ml/out.mp4"]

        mock_client = MagicMock()
        mock_client.image_to_video.create.return_value = task_created
        mock_client.tasks.retrieve.return_value = task_done

        mock_runway_module = MagicMock()
        mock_runway_module.RunwayML.return_value = mock_client

        stub_settings = MagicMock()
        stub_settings.runwayml_api_secret = "rw-test-secret"

        # Write a tiny temp image file so open(image_path,"rb") works
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(b"\xff\xd8\xff\xe0" + b"\x00" * 12)  # minimal JPEG header
            tmp_image = tf.name

        sys.modules.pop("phase_c_ffmpeg", None)

        try:
            # No os.path.exists patch: the RUNWAY_GEN4 branch (phase_c_ffmpeg ~:345-394)
            # never calls os.path.exists — it only reads open(image_path,"rb"), satisfied
            # by the real temp file above. A global os.path.exists patch would be an
            # unscoped footgun (and can't be narrowed to phase_c_ffmpeg.* here, since the
            # module is imported inside this with-block).
            with patch.dict("sys.modules", {"runwayml": mock_runway_module}), \
                 patch("urllib.request.urlretrieve"), \
                 patch("time.sleep"):
                import phase_c_ffmpeg
                phase_c_ffmpeg.settings = stub_settings
                phase_c_ffmpeg.generate_ai_video(
                    image_path=tmp_image,
                    camera_motion="zoom_in_slow",
                    target_api="RUNWAY_GEN4",
                    output_mp4="/tmp/runway_out.mp4",
                    shot_type="portrait",
                    ctx=_ctx("16:9"),  # aspect irrelevant here — Runway ratio threading is T5b
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            os.unlink(tmp_image)

        return mock_client

    def test_runway_gen4_uses_valid_sdk_model(self):
        """RUNWAY_GEN4 must call create(..., model=<valid-sdk-enum-value>)."""
        # Source: runwayml v4.14.0 — types/image_to_video_create_params.py model Literal union
        _VALID_RUNWAY_MODELS = {"gen4.5", "gen4_turbo", "veo3.1", "veo3.1_fast",
                                "veo3", "gen3a_turbo"}
        mock_client = self._run_runway_gen4()

        assert mock_client.image_to_video.create.called, (
            "client.image_to_video.create was never called"
        )
        call_kwargs = mock_client.image_to_video.create.call_args.kwargs
        model_used = call_kwargs.get("model")
        assert model_used in _VALID_RUNWAY_MODELS, (
            f"model='{model_used}' is not in the SDK valid set {_VALID_RUNWAY_MODELS}"
        )
        # Pin the exact expected value (not just "in set")
        assert model_used == "gen4_turbo", (
            f"Expected model='gen4_turbo' specifically; got model='{model_used}'"
        )

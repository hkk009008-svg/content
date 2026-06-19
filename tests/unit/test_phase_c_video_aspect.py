"""Unit tests for Phase-3 portrait video: Veo native + fal + Runway emit 9:16.

TC-4 — VEO_NATIVE path threads aspect_ratio="9:16" into veo.generate_video().
TC-5 — VEO fal path puts aspect_ratio="9:16" into fal_client.subscribe arguments
       (+ landscape refute: 16:9 → "16:9").
TC-6 — SORA_2 fal path puts fal_aspect_ratio(_aspect) into subscribe arguments.
TC-7 — RUNWAY_GEN4 route uses model='gen4_turbo' (valid SDK enum) + emits portrait ratio.
TC-8 — RUNWAY (gen3a) route emits portrait ratio via runway_ratio.

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

    def _run_runway_gen4(self, aspect: str = "16:9"):
        """Drive generate_ai_video(RUNWAY_GEN4) with the given aspect; return the
        mock RunwayML client whose .image_to_video.create.call_args the tests inspect.

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
                # The RUNWAY_GEN4 branch downloads via performance._net.safe_download
                # (bound into phase_c_ffmpeg at import) — NOT urllib.request.urlretrieve.
                # On a fake URL safe_download returns None, which _download_video_or_cascade
                # treats as a failed download and CASCADES to the gen3a engine — so the last
                # create() call the test inspects would be gen3a_turbo, not gen4_turbo. Stub it
                # to "succeed" (return the out path) so the gen4 happy path is exercised.
                phase_c_ffmpeg.safe_download = lambda url, out: out
                phase_c_ffmpeg.generate_ai_video(
                    image_path=tmp_image,
                    camera_motion="zoom_in_slow",
                    target_api="RUNWAY_GEN4",
                    output_mp4="/tmp/runway_out.mp4",
                    shot_type="portrait",
                    ctx=_ctx(aspect),
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

    def test_runway_gen4_portrait_ratio(self):
        """TC-4: RUNWAY_GEN4 portrait ctx → ratio=='720:1280'.

        Note: gen4_turbo is NOT a key in cinema.aspect._RUNWAY_PORTRAIT (which only
        special-cases gen3a_turbo→'768:1280'); runway_ratio falls to its portrait
        default '720:1280'. If a contributor adds a gen4_turbo entry there, this test
        will (correctly) flag the change.
        """
        mock_client = self._run_runway_gen4(aspect="9:16")
        call_kwargs = mock_client.image_to_video.create.call_args.kwargs
        assert call_kwargs.get("ratio") == "720:1280", (
            f"Expected ratio='720:1280' for portrait; got: {call_kwargs}"
        )

    def test_runway_gen4_landscape_ratio(self):
        """TC-4 (refute): RUNWAY_GEN4 landscape ctx → ratio=='1280:720' (no regression)."""
        mock_client = self._run_runway_gen4(aspect="16:9")
        call_kwargs = mock_client.image_to_video.create.call_args.kwargs
        assert call_kwargs.get("ratio") == "1280:720", (
            f"Expected ratio='1280:720' for landscape; got: {call_kwargs}"
        )


# ---------------------------------------------------------------------------
# TC-8 — RUNWAY (gen3a): generate_ai_video emits portrait ratio via runway_ratio
# ---------------------------------------------------------------------------
class TestRunwayGen3aRatio:
    """Drive generate_ai_video(target_api='RUNWAY', ...) and assert that
    runway_client.image_to_video.create is called with ratio='768:1280' for portrait
    and ratio='1280:768' for landscape (refute).

    The RUNWAY route uses runwayml SDK: create() returns a task object, then
    task.wait_for_task_output() is called (blocking; mock returns immediately),
    then task.output[0] is the download URL.
    """

    def _run_runway(self, aspect: str):
        """Drive generate_ai_video(RUNWAY) with the given aspect; return the
        mock RunwayML client whose .image_to_video.create.call_args the tests inspect.

        The route (phase_c_ffmpeg ~:672-703):
        1. Imports RunwayML inside the branch — patch via sys.modules.
        2. Reads open(image_path, "rb") — use a real temp file.
        3. Calls video_task.wait_for_task_output() (no spin loop — mock returns immediately).
        4. Reads completed_task.output[0] then calls urllib.request.urlretrieve.
        """
        import tempfile
        import os

        # The RUNWAY route calls video_task.wait_for_task_output() — returns completed_task.
        # completed_task.output[0] must be a URL string.
        completed_task = MagicMock()
        completed_task.output = ["https://cdn.runway.ml/gen3a_out.mp4"]

        video_task = MagicMock()
        video_task.id = "runway-gen3a-task-001"
        video_task.wait_for_task_output.return_value = completed_task

        mock_client = MagicMock()
        mock_client.image_to_video.create.return_value = video_task

        mock_runway_module = MagicMock()
        mock_runway_module.RunwayML.return_value = mock_client

        stub_settings = MagicMock()
        stub_settings.runwayml_api_secret = "rw-gen3a-secret"

        # Write a tiny temp image file so open(image_path,"rb") works
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(b"\xff\xd8\xff\xe0" + b"\x00" * 12)  # minimal JPEG header
            tmp_image = tf.name

        sys.modules.pop("phase_c_ffmpeg", None)

        try:
            # No os.path.exists patch: the RUNWAY branch (~:672-703) never calls
            # os.path.exists — it only reads open(image_path,"rb"), satisfied by the
            # real temp file above.
            with patch.dict("sys.modules", {"runwayml": mock_runway_module}), \
                 patch("urllib.request.urlretrieve"):
                import phase_c_ffmpeg
                phase_c_ffmpeg.settings = stub_settings
                phase_c_ffmpeg.generate_ai_video(
                    image_path=tmp_image,
                    camera_motion="zoom_in_slow",
                    target_api="RUNWAY",
                    output_mp4="/tmp/runway_gen3a_out.mp4",
                    shot_type="portrait",
                    ctx=_ctx(aspect),
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            os.unlink(tmp_image)

        return mock_client

    def test_runway_portrait_ratio(self):
        """TC-4: RUNWAY (gen3a) portrait ctx → ratio=='768:1280'."""
        mock_client = self._run_runway("9:16")
        call_kwargs = mock_client.image_to_video.create.call_args.kwargs
        assert call_kwargs.get("ratio") == "768:1280", (
            f"Expected ratio='768:1280' for portrait; got: {call_kwargs}"
        )

    def test_runway_landscape_ratio(self):
        """TC-4 (refute): RUNWAY (gen3a) landscape ctx → ratio=='1280:768' (no regression)."""
        mock_client = self._run_runway("16:9")
        call_kwargs = mock_client.image_to_video.create.call_args.kwargs
        assert call_kwargs.get("ratio") == "1280:768", (
            f"Expected ratio='1280:768' for landscape; got: {call_kwargs}"
        )


# ---------------------------------------------------------------------------
# TC-portrait-routing-safety — cascade filter + backstop (T7)
# ---------------------------------------------------------------------------
class TestAcceptOrReject:
    """Direct unit tests for _accept_or_reject (module-level backstop helper)."""

    def _get_fn(self):
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        return phase_c_ffmpeg._accept_or_reject

    def test_landscape_always_accepts(self):
        """Landscape project: backstop is a no-op — always True regardless of dims."""
        fn = self._get_fn()
        # Even if the file would be portrait dims, landscape project accepts
        assert fn("/any/path.mp4", "16:9") is True

    def test_portrait_portrait_dims_accepts(self):
        """Portrait project + portrait clip (h>w) → accept."""
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        fn = phase_c_ffmpeg._accept_or_reject
        with patch("phase_c_ffmpeg.probe_final_media",
                   return_value={"format": {"width": 1080, "height": 1920}}):
            assert fn("/tmp/clip.mp4", "9:16") is True

    def test_portrait_landscape_dims_rejects(self):
        """Portrait project + landscape clip (w>h) → reject."""
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        fn = phase_c_ffmpeg._accept_or_reject
        with patch("phase_c_ffmpeg.probe_final_media",
                   return_value={"format": {"width": 1920, "height": 1080}}):
            assert fn("/tmp/clip.mp4", "9:16") is False

    def test_portrait_probe_none_accepts(self):
        """Portrait project + probe returns None → accept (fail-safe, don't strand pipeline)."""
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        fn = phase_c_ffmpeg._accept_or_reject
        with patch("phase_c_ffmpeg.probe_final_media", return_value=None):
            assert fn("/tmp/clip.mp4", "9:16") is True

    def test_portrait_missing_format_key_accepts(self):
        """Portrait project + probe returns dict without 'format' key → accept (fail-safe)."""
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        fn = phase_c_ffmpeg._accept_or_reject
        with patch("phase_c_ffmpeg.probe_final_media", return_value={"audio": {}}):
            assert fn("/tmp/clip.mp4", "9:16") is True

    def test_portrait_none_dims_accepts(self):
        """Portrait project + probe has format but w/h are None → accept (fail-safe)."""
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        fn = phase_c_ffmpeg._accept_or_reject
        with patch("phase_c_ffmpeg.probe_final_media",
                   return_value={"format": {"width": None, "height": None}}):
            assert fn("/tmp/clip.mp4", "9:16") is True


class TestPortraitRoutingSafety:
    """TC-portrait-routing-safety: cascade filter + backstop for 9:16 portrait projects.

    Tests:
    1. filter-exclude: LTX dropped from cascade for portrait ctx
    2. backstop reject-retry: landscape-dim clip rejected, cascades to portrait-dim winner
    3. terminal-fail-loud: all clips landscape-dim → None returned (no leak)
    4. 16:9 refute: landscape project → probe never consulted, clip accepted
    """

    # ------------------------------------------------------------------
    # Shared helper: build a stub that writes output_mp4 and returns it
    # (simulates a "successful" provider). The caller patches probe.
    # ------------------------------------------------------------------
    def _kling_native_stub(self, output_path):
        """Return a KlingNativeAPI mock that writes output_mp4 and returns it."""
        mock_inst = MagicMock()
        mock_inst.generate_video.return_value = output_path
        mock_mod = MagicMock()
        mock_mod.KlingNativeAPI.return_value = mock_inst
        return mock_mod

    def _sora_native_stub(self, output_path):
        """Return a SoraNativeAPI mock that writes output_path and returns it."""
        mock_inst = MagicMock()
        mock_inst.generate_video.return_value = output_path
        mock_mod = MagicMock()
        mock_mod.SoraNativeAPI.return_value = mock_inst
        return mock_mod

    def _veo_native_stub(self, output_path):
        """Return a VeoNativeAPI mock that returns output_path."""
        mock_inst = MagicMock()
        mock_inst.generate_video.return_value = output_path
        mock_mod = MagicMock()
        mock_mod.VeoNativeAPI.return_value = mock_inst
        return mock_mod

    def _ltx_stub(self, output_path):
        """Return an LTXVideoAPI mock that returns output_path."""
        mock_inst = MagicMock()
        mock_inst.generate_video.return_value = output_path
        mock_mod = MagicMock()
        mock_mod.LTXVideoAPI.return_value = mock_inst
        return mock_mod

    # ------------------------------------------------------------------
    # Test 1: filter-exclude — LTX never called for portrait ctx
    # ------------------------------------------------------------------
    def test_filter_exclude_ltx_for_portrait(self):
        """Portrait ctx, fallbacks=[VEO_NATIVE, LTX, SORA_NATIVE]:
        VEO_NATIVE stub fails (returns None) → cascade; LTX MUST be dropped by
        the portrait filter → SORA_NATIVE is reached instead."""
        output_mp4 = "/tmp/filter_test_out.mp4"
        _cascade_out = {}

        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = None  # VEO fails
        veo_mod.VeoNativeAPI.return_value = veo_inst

        ltx_mod = MagicMock()
        ltx_inst = MagicMock()
        ltx_inst.generate_video.return_value = None  # LTX stub — should never be called
        ltx_mod.LTXVideoAPI.return_value = ltx_inst

        sora_mod = MagicMock()
        sora_inst = MagicMock()
        sora_inst.generate_video.return_value = output_mp4  # SORA succeeds
        sora_mod.SoraNativeAPI.return_value = sora_inst

        _saved_veo = sys.modules.pop("veo_native", None)
        _saved_ltx = sys.modules.pop("ltx_native", None)
        _saved_sora = sys.modules.pop("sora_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["veo_native"] = veo_mod
        sys.modules["ltx_native"] = ltx_mod
        sys.modules["sora_native"] = sora_mod

        try:
            with patch("phase_c_ffmpeg.probe_final_media",
                       return_value={"format": {"width": 1080, "height": 1920}}):
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4=output_mp4,
                    shot_type="portrait",
                    video_fallbacks=["VEO_NATIVE", "LTX", "SORA_NATIVE"],
                    ctx=_ctx("9:16"),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            # Restore original modules (not just pop) so sibling test files that imported
            # these modules at collection time keep a consistent module identity.
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)
            if _saved_ltx is not None:
                sys.modules["ltx_native"] = _saved_ltx
            else:
                sys.modules.pop("ltx_native", None)
            if _saved_sora is not None:
                sys.modules["sora_native"] = _saved_sora
            else:
                sys.modules.pop("sora_native", None)

        # LTX must never have been constructed/called
        assert not ltx_inst.generate_video.called, (
            "LTX generate_video was called — portrait filter failed to drop LTX"
        )
        assert not ltx_mod.LTXVideoAPI.called, (
            "LTXVideoAPI was constructed — portrait filter failed to drop LTX from cascade"
        )
        # SORA_NATIVE must be the winner
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "SORA_NATIVE", (
            f"Expected SORA_NATIVE to win; got: {_cascade_out}"
        )

    # ------------------------------------------------------------------
    # Test 2: backstop reject-retry
    # ------------------------------------------------------------------
    def test_backstop_rejects_landscape_clip_and_cascades(self):
        """Portrait ctx, fallbacks=[VEO_NATIVE, SORA_NATIVE]: both stubs succeed
        (return output_mp4), but probe returns landscape dims for VEO_NATIVE and
        portrait dims for SORA_NATIVE. Assert SORA_NATIVE wins."""
        output_mp4 = "/tmp/backstop_test_out.mp4"
        _cascade_out = {}

        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = output_mp4
        veo_mod.VeoNativeAPI.return_value = veo_inst

        sora_mod = MagicMock()
        sora_inst = MagicMock()
        sora_inst.generate_video.return_value = output_mp4
        sora_mod.SoraNativeAPI.return_value = sora_inst

        # First probe call (VEO_NATIVE's clip) → landscape; second (SORA_NATIVE's) → portrait
        probe_side_effect = [
            {"format": {"width": 1920, "height": 1080}},  # VEO: landscape → reject
            {"format": {"width": 1080, "height": 1920}},  # SORA: portrait → accept
        ]

        _saved_veo = sys.modules.pop("veo_native", None)
        _saved_sora = sys.modules.pop("sora_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["veo_native"] = veo_mod
        sys.modules["sora_native"] = sora_mod

        try:
            with patch("phase_c_ffmpeg.probe_final_media", side_effect=probe_side_effect):
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4=output_mp4,
                    shot_type="portrait",
                    video_fallbacks=["VEO_NATIVE", "SORA_NATIVE"],
                    ctx=_ctx("9:16"),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)
            if _saved_sora is not None:
                sys.modules["sora_native"] = _saved_sora
            else:
                sys.modules.pop("sora_native", None)

        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "SORA_NATIVE", (
            f"Expected SORA_NATIVE to win after VEO rejected; got: {_cascade_out}"
        )
        assert result == output_mp4

    # ------------------------------------------------------------------
    # Test 3: terminal fail-loud — returns None
    # ------------------------------------------------------------------
    def test_terminal_fail_loud_all_landscape(self):
        """Portrait ctx, all providers succeed but all probes return landscape dims →
        generate_ai_video returns None (no landscape clip leaks)."""
        output_mp4 = "/tmp/failall_test_out.mp4"

        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = output_mp4
        veo_mod.VeoNativeAPI.return_value = veo_inst

        sora_mod = MagicMock()
        sora_inst = MagicMock()
        sora_inst.generate_video.return_value = output_mp4
        sora_mod.SoraNativeAPI.return_value = sora_inst

        landscape_probe = {"format": {"width": 1920, "height": 1080}}

        _saved_veo = sys.modules.pop("veo_native", None)
        _saved_sora = sys.modules.pop("sora_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["veo_native"] = veo_mod
        sys.modules["sora_native"] = sora_mod

        try:
            with patch("phase_c_ffmpeg.probe_final_media", return_value=landscape_probe), \
                 patch("time.sleep"):
                import phase_c_ffmpeg
                ctx = _ctx("9:16")
                # Set cascade_retry_limit=0 to prevent indefinite retry loop
                ctx.global_settings["cascade_retry_limit"] = 0
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4=output_mp4,
                    shot_type="portrait",
                    video_fallbacks=["VEO_NATIVE", "SORA_NATIVE"],
                    ctx=ctx,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)
            if _saved_sora is not None:
                sys.modules["sora_native"] = _saved_sora
            else:
                sys.modules.pop("sora_native", None)

        assert result is None, (
            f"Expected None when all portrait probes fail; got: {result!r}"
        )

    # ------------------------------------------------------------------
    # Test 4: 16:9 refute — probe never consulted, landscape clip accepted
    # ------------------------------------------------------------------
    def test_landscape_ctx_probe_never_consulted(self):
        """Landscape ctx: backstop is a no-op. Provider succeeds with a landscape clip
        (w>h), probe_final_media is NOT called for rejection purposes, clip is accepted."""
        output_mp4 = "/tmp/landscape_refute_out.mp4"
        _cascade_out = {}

        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = output_mp4
        veo_mod.VeoNativeAPI.return_value = veo_inst

        _saved_veo = sys.modules.pop("veo_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["veo_native"] = veo_mod

        try:
            with patch("phase_c_ffmpeg.probe_final_media") as mock_probe:
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="VEO_NATIVE",
                    output_mp4=output_mp4,
                    shot_type="medium",
                    video_fallbacks=["VEO_NATIVE"],
                    ctx=_ctx("16:9"),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)

        # probe_final_media must NOT be called (backstop short-circuits for landscape)
        assert not mock_probe.called, (
            "probe_final_media was called for a landscape project — backstop is not a no-op!"
        )
        assert result == output_mp4, (
            f"Expected landscape clip to be accepted; got result={result!r}"
        )

    # ------------------------------------------------------------------
    # Test 5 (F1 regression): a non-portrait-capable INITIAL target must
    # be rejected and cascade — never dispatched. Closes the PF-4 gap.
    # ------------------------------------------------------------------
    def test_non_portrait_capable_initial_target_rejected_for_portrait(self):
        """F1: target_api='LTX' (the establishing_shot route; LTX ∉ PORTRAIT_CAPABLE)
        at a portrait project. The cascade's is_portrait filter only guards the
        fallback_list — the INITIAL target was dispatched unfiltered, so LTX wrote a
        landscape clip and the backstop fail-opened on probe failure → landscape
        accepted. After the top-level pre-dispatch guard, LTX must NEVER be dispatched;
        the portrait-capable fallback (VEO_NATIVE) wins instead.

        Reproduction faithfulness: probe returns no dims ({"format": {}}) → the
        backstop fail-opens (accept). WITHOUT the guard, LTX is dispatched first and
        wins with that fail-open (the F1 harm — landscape leaks). WITH the guard, LTX
        is skipped, VEO_NATIVE is dispatched, and VEO wins.
        """
        output_mp4 = "/tmp/f1_initial_target_out.mp4"
        _cascade_out = {}

        ltx_mod = MagicMock()
        ltx_inst = MagicMock()
        ltx_inst.generate_video.return_value = output_mp4  # would "succeed" if reached
        ltx_mod.LTXVideoAPI.return_value = ltx_inst

        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = output_mp4
        veo_mod.VeoNativeAPI.return_value = veo_inst

        _saved_ltx = sys.modules.pop("ltx_native", None)
        _saved_veo = sys.modules.pop("veo_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["ltx_native"] = ltx_mod
        sys.modules["veo_native"] = veo_mod

        try:
            # probe returns no dims → _accept_or_reject fail-opens (the F1 condition).
            with patch("phase_c_ffmpeg.probe_final_media", return_value={"format": {}}):
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="LTX",  # non-portrait-capable INITIAL target
                    output_mp4=output_mp4,
                    shot_type="establishing_shot",
                    video_fallbacks=["LTX", "VEO_NATIVE"],
                    ctx=_ctx("9:16"),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_ltx is not None:
                sys.modules["ltx_native"] = _saved_ltx
            else:
                sys.modules.pop("ltx_native", None)
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)

        # LTX must never be constructed or called — the pre-dispatch guard drops it.
        assert not ltx_inst.generate_video.called, (
            "LTX generate_video was called — non-portrait-capable INITIAL target dispatched (F1)"
        )
        assert not ltx_mod.LTXVideoAPI.called, (
            "LTXVideoAPI was constructed — initial-target portrait guard missing (F1)"
        )
        # The portrait-capable fallback must win, not LTX.
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "VEO_NATIVE", (
            f"Expected VEO_NATIVE to win after LTX skipped; got: {_cascade_out}"
        )
        assert result == output_mp4
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "VEO_NATIVE"

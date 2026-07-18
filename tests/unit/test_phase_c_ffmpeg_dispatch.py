"""Dispatch-level tests for the GEMINI_OMNI branch in phase_c_ffmpeg.py
(WS2 step 2, 2026-07-18 google-first-overhaul).

The branch itself mirrors VEO_NATIVE's shape, but three of its properties
are NOT exercised by the existing suite (test_cascade_logic.py only checks
workflow_selector.py's target_api/fallback ORDERING; test_native_billed_
rejects.py — extended alongside this file — only checks the billed-then-
rejected leak):

1. generate_ai_video(target_api='GEMINI_OMNI') threads the right kwargs
   into GeminiOmniAPI.generate_video (image_path, prompt w/ audio intent,
   output_path, reference_images, aspect_ratio) and records the cascade
   winner correctly on success.
2. GEMINI_OMNI is deliberately excluded from PORTRAIT_CAPABLE (unverified
   aspect-ratio forceability) — but WS2 also wired it as target_api for
   EVERY shot type in workflow_selector.py, including portrait. The
   pre-dispatch guard (phase_c_ffmpeg.py ~L330) must therefore skip
   GEMINI_OMNI as the INITIAL target on a portrait project and fall
   through to the cascade's first PORTRAIT_CAPABLE engine (VEO_NATIVE per
   the real portrait template) — never construct GeminiOmniAPI at all.
3. The branch's own quota-cooldown pair (_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL /
   _GEMINI_OMNI_QUOTA_TTL_S / _gemini_omni_quota_blocked) is distinct from
   Veo's — a budget_exceeded/429/quota/exhausted exception must set the
   cooldown and cascade; a live cooldown must skip dispatch (no client
   construction) on the next call.

All tests are offline — no Vertex, no Gemini Developer API, no network, no
spend. Mirrors the module-hygiene pattern in test_phase_c_video_aspect.py /
test_native_billed_rejects.py (pop 'phase_c_ffmpeg' before each import so
lazy `from gemini_omni_native import GeminiOmniAPI` picks up the stub;
patch.dict/save-restore sys.modules so the stub never leaks to sibling
test files that import gemini_omni_native for real).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _ctx(aspect: str, **extra_settings):
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={"aspect_ratio": aspect, **extra_settings})


def _gemini_omni_stub(output_path):
    """Return a gemini_omni_native module stub whose GeminiOmniAPI().generate_video
    returns output_path; also return the mock instance for call_args inspection."""
    mock_inst = MagicMock()
    mock_inst.generate_video.return_value = output_path
    mock_mod = MagicMock()
    mock_mod.GeminiOmniAPI.return_value = mock_inst
    return mock_mod, mock_inst


class TestGeminiOmniSuccessPath:
    """generate_ai_video(target_api='GEMINI_OMNI') threads kwargs correctly
    and records the cascade winner on success."""

    def _run(self, aspect="16:9", shot_type="wide", has_dialogue=False,
              dialogue_native_audio=False, multi_angle_refs=None):
        output_mp4 = "/tmp/gemini_omni_out.mp4"
        mock_mod, mock_inst = _gemini_omni_stub(output_mp4)
        _cascade_out = {}

        _saved = sys.modules.pop("gemini_omni_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["gemini_omni_native"] = mock_mod

        try:
            with patch("os.path.exists", return_value=True):
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="GEMINI_OMNI",
                    output_mp4=output_mp4,
                    shot_type=shot_type,
                    video_fallbacks=["GEMINI_OMNI"],  # nothing else — clean single-hop
                    has_dialogue=has_dialogue,
                    dialogue_native_audio=dialogue_native_audio,
                    multi_angle_refs=multi_angle_refs,
                    ctx=_ctx(aspect),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved is not None:
                sys.modules["gemini_omni_native"] = _saved
            else:
                sys.modules.pop("gemini_omni_native", None)

        return result, mock_inst, _cascade_out

    def test_threads_expected_kwargs(self):
        refs = ["/tmp/ref1.png", "/tmp/ref2.png"]
        result, mock_inst, _cascade_out = self._run(
            aspect="16:9", shot_type="wide", multi_angle_refs=refs,
        )
        assert mock_inst.generate_video.called, "generate_video was never called"
        kw = mock_inst.generate_video.call_args.kwargs
        assert kw.get("image_path") == "/tmp/f.png"
        assert kw.get("output_path") == "/tmp/gemini_omni_out.mp4"
        assert kw.get("reference_images") == refs
        assert kw.get("aspect_ratio") == "16:9"
        assert "MOTION:" in kw.get("prompt", "")

    def test_success_records_cascade_winner(self):
        result, mock_inst, _cascade_out = self._run()
        assert result == "/tmp/gemini_omni_out.mp4"
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "GEMINI_OMNI", (
            f"Expected GEMINI_OMNI to be recorded as cascade winner; got: {_cascade_out}"
        )

    def test_landscape_shot_wants_audio(self):
        """landscape shot_type → ambient ENV audio should be requested, not silent."""
        _, mock_inst, _ = self._run(aspect="16:9", shot_type="landscape")
        prompt = mock_inst.generate_video.call_args.kwargs.get("prompt", "")
        assert "AUDIO: Generate natural synced audio" in prompt, prompt

    def test_dialogue_native_audio_wants_audio(self):
        """dialogue_native_audio=True → audio requested regardless of shot_type."""
        _, mock_inst, _ = self._run(
            aspect="16:9", shot_type="portrait", has_dialogue=True,
            dialogue_native_audio=True,
        )
        prompt = mock_inst.generate_video.call_args.kwargs.get("prompt", "")
        assert "AUDIO: Generate natural synced audio" in prompt, prompt

    def test_non_dialogue_portrait_is_silent(self):
        """Non-dialogue portrait shot with no native-audio flag → silent audio intent
        (audio is added downstream by the assembly phase, not baked in here)."""
        _, mock_inst, _ = self._run(
            aspect="16:9", shot_type="portrait", has_dialogue=False,
            dialogue_native_audio=False,
        )
        prompt = mock_inst.generate_video.call_args.kwargs.get("prompt", "")
        assert "AUDIO: Silent" in prompt, prompt

    def test_dialogue_without_native_audio_is_silent(self):
        """has_dialogue=True but dialogue_native_audio=False (overlay lipsync path,
        not native-audio) → silent; TTS overlay handles the voice downstream."""
        _, mock_inst, _ = self._run(
            aspect="16:9", shot_type="wide", has_dialogue=True,
            dialogue_native_audio=False,
        )
        prompt = mock_inst.generate_video.call_args.kwargs.get("prompt", "")
        assert "AUDIO: Silent" in prompt, prompt


class TestGeminiOmniPortraitPreDispatchGuard:
    """WS2 sets GEMINI_OMNI as target_api for every shot type, including
    portrait — but GEMINI_OMNI is deliberately excluded from
    PORTRAIT_CAPABLE. The pre-dispatch guard must skip it as the INITIAL
    target on a portrait project (never construct GeminiOmniAPI) and fall
    through to the first PORTRAIT_CAPABLE fallback."""

    def test_portrait_initial_target_skips_gemini_omni(self):
        output_mp4 = "/tmp/portrait_guard_out.mp4"
        _cascade_out = {}

        gemini_mod, gemini_inst = _gemini_omni_stub(output_mp4)
        veo_mod = MagicMock()
        veo_inst = MagicMock()
        veo_inst.generate_video.return_value = output_mp4
        veo_mod.VeoNativeAPI.return_value = veo_inst

        _saved_gemini = sys.modules.pop("gemini_omni_native", None)
        _saved_veo = sys.modules.pop("veo_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["gemini_omni_native"] = gemini_mod
        sys.modules["veo_native"] = veo_mod

        try:
            with patch("os.path.exists", return_value=True), \
                 patch("phase_c_ffmpeg.probe_final_media",
                       return_value={"format": {"width": 1080, "height": 1920}}):
                import phase_c_ffmpeg
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="GEMINI_OMNI",  # WS2 portrait primary
                    output_mp4=output_mp4,
                    shot_type="portrait",
                    # Real portrait template (workflow_selector.py): GEMINI_OMNI
                    # target_api + this exact fallback chain.
                    video_fallbacks=["VEO_NATIVE", "KLING_3_0", "KLING_NATIVE",
                                      "RUNWAY_GEN4", "SEEDANCE"],
                    ctx=_ctx("9:16"),
                    _cascade_out=_cascade_out,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_gemini is not None:
                sys.modules["gemini_omni_native"] = _saved_gemini
            else:
                sys.modules.pop("gemini_omni_native", None)
            if _saved_veo is not None:
                sys.modules["veo_native"] = _saved_veo
            else:
                sys.modules.pop("veo_native", None)

        assert not gemini_inst.generate_video.called, (
            "GeminiOmniAPI.generate_video was called on a portrait project — "
            "the pre-dispatch PORTRAIT_CAPABLE guard failed to skip GEMINI_OMNI"
        )
        assert not gemini_mod.GeminiOmniAPI.called, (
            "GeminiOmniAPI was constructed on a portrait project — GEMINI_OMNI "
            "is not in PORTRAIT_CAPABLE and must never be dispatched as the "
            "initial target for a 9:16 project"
        )
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "VEO_NATIVE", (
            f"Expected VEO_NATIVE (first PORTRAIT_CAPABLE fallback) to win; "
            f"got: {_cascade_out}"
        )
        assert result == output_mp4


class TestGeminiOmniQuotaCooldown:
    """GEMINI_OMNI's cooldown pair is separate from Veo's (10min Tier-1
    rolling window vs Veo's 30min hourly-reset assumption)."""

    def _fresh_module(self):
        sys.modules.pop("phase_c_ffmpeg", None)
        import phase_c_ffmpeg
        return phase_c_ffmpeg

    def test_quota_blocked_helper_true_when_future(self):
        phase_c_ffmpeg = self._fresh_module()
        with patch.object(phase_c_ffmpeg, "_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL",
                           phase_c_ffmpeg.time.time() + 300):
            assert phase_c_ffmpeg._gemini_omni_quota_blocked() is True

    def test_quota_blocked_helper_false_when_zero(self):
        phase_c_ffmpeg = self._fresh_module()
        with patch.object(phase_c_ffmpeg, "_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL", 0.0):
            assert phase_c_ffmpeg._gemini_omni_quota_blocked() is False

    def test_budget_exceeded_exception_sets_cooldown_and_cascades(self):
        """generate_video raising a 'budget_exceeded' error must set the
        GEMINI_OMNI-specific TTL (not Veo's) and cascade to the next engine."""
        output_mp4 = "/tmp/quota_cooldown_out.mp4"
        _cascade_out = {}

        gemini_mod = MagicMock()
        gemini_inst = MagicMock()
        gemini_inst.generate_video.side_effect = RuntimeError(
            "GEMINI_OMNI budget_exceeded: rolling spend window hit"
        )
        gemini_mod.GeminiOmniAPI.return_value = gemini_inst

        ltx_mod = MagicMock()
        ltx_inst = MagicMock()
        ltx_inst.generate_video.return_value = output_mp4
        ltx_mod.LTXVideoAPI.return_value = ltx_inst

        _saved_gemini = sys.modules.pop("gemini_omni_native", None)
        _saved_ltx = sys.modules.pop("ltx_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["gemini_omni_native"] = gemini_mod
        sys.modules["ltx_native"] = ltx_mod

        try:
            with patch("os.path.exists", return_value=True):
                import phase_c_ffmpeg
                # Ensure no stale cooldown from a prior test in this process.
                phase_c_ffmpeg._GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL = 0.0
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="GEMINI_OMNI",
                    output_mp4=output_mp4,
                    shot_type="wide",
                    video_fallbacks=["GEMINI_OMNI", "LTX"],
                    ctx=_ctx("16:9"),
                    _cascade_out=_cascade_out,
                )
                cooldown_now = phase_c_ffmpeg._GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL
                veo_cooldown_untouched = phase_c_ffmpeg._VEO_QUOTA_EXHAUSTED_UNTIL
        finally:
            # Reset module-level cooldown state so it can't leak into later tests.
            import phase_c_ffmpeg as _pcf
            _pcf._GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL = 0.0
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_gemini is not None:
                sys.modules["gemini_omni_native"] = _saved_gemini
            else:
                sys.modules.pop("gemini_omni_native", None)
            if _saved_ltx is not None:
                sys.modules["ltx_native"] = _saved_ltx
            else:
                sys.modules.pop("ltx_native", None)

        assert cooldown_now > 0.0, (
            "budget_exceeded error did not set _GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL"
        )
        assert veo_cooldown_untouched == 0.0, (
            "GEMINI_OMNI's quota exception leaked into Veo's SEPARATE cooldown pair"
        )
        assert result == output_mp4
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "LTX"

    def test_active_cooldown_skips_dispatch_entirely(self):
        """When the cooldown is already active, GeminiOmniAPI must never be
        constructed — the branch short-circuits straight to try_next_api()."""
        output_mp4 = "/tmp/quota_skip_out.mp4"
        _cascade_out = {}

        gemini_mod, gemini_inst = _gemini_omni_stub(output_mp4)
        ltx_mod = MagicMock()
        ltx_inst = MagicMock()
        ltx_inst.generate_video.return_value = output_mp4
        ltx_mod.LTXVideoAPI.return_value = ltx_inst

        _saved_gemini = sys.modules.pop("gemini_omni_native", None)
        _saved_ltx = sys.modules.pop("ltx_native", None)
        sys.modules.pop("phase_c_ffmpeg", None)
        sys.modules["gemini_omni_native"] = gemini_mod
        sys.modules["ltx_native"] = ltx_mod

        try:
            with patch("os.path.exists", return_value=True):
                import phase_c_ffmpeg
                phase_c_ffmpeg._GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL = phase_c_ffmpeg.time.time() + 300
                result = phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api="GEMINI_OMNI",
                    output_mp4=output_mp4,
                    shot_type="wide",
                    video_fallbacks=["GEMINI_OMNI", "LTX"],
                    ctx=_ctx("16:9"),
                    _cascade_out=_cascade_out,
                )
        finally:
            import phase_c_ffmpeg as _pcf
            _pcf._GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL = 0.0
            sys.modules.pop("phase_c_ffmpeg", None)
            if _saved_gemini is not None:
                sys.modules["gemini_omni_native"] = _saved_gemini
            else:
                sys.modules.pop("gemini_omni_native", None)
            if _saved_ltx is not None:
                sys.modules["ltx_native"] = _saved_ltx
            else:
                sys.modules.pop("ltx_native", None)

        assert not gemini_inst.generate_video.called, (
            "generate_video was called despite an active quota cooldown"
        )
        assert not gemini_mod.GeminiOmniAPI.called, (
            "GeminiOmniAPI was constructed despite an active quota cooldown"
        )
        assert result == output_mp4
        assert _cascade_out.get("cascade_metadata", {}).get("engine") == "LTX"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Producer-side pin: NATIVE video branches note billed attempts on aspect
reject (ultrareview bug_002, 2026-07-11).

The 4 native branches (KLING_NATIVE/SORA_NATIVE/VEO_NATIVE/LTX) write their
output via the SDK's ``output_path=`` and never touch
``_download_video_or_cascade`` — the fal-path writer of
``_cascade_out['billed_attempts']``. So a provider-billed native clip that
the aspect backstop then rejects used to cascade with ZERO recorded spend
(KLING_NATIVE is the sharp case: its adapter takes no aspect param, so a
portrait project routing to it produces 16:9 → guaranteed reject → billed
but $0). The fix appends via ``_note_billed_attempt`` before the aspect
check; this pins it so deleting the append goes RED.
"""
from __future__ import annotations

import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from domain.provider_catalog import RuntimeSnapshot


def _ctx(aspect: str):
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={"aspect_ratio": aspect})


def _run_native(target_api: str, module_name: str, class_attr: str, aspect: str = "16:9"):
    """Drive a native branch whose generate_video returns a path, with the
    aspect backstop forced to REJECT; return _cascade_out.

    Uses a 16:9 project so all four native engines are reachable — LTX is
    excluded from PORTRAIT_CAPABLE, so a 9:16 project pre-filters it out
    (it never bills there, which is why the aspect leak can't touch LTX on
    portrait projects but CAN on landscape/wide ones)."""
    mock_inst = MagicMock()
    mock_inst.generate_video.return_value = "/tmp/out.mp4"
    mock_mod = MagicMock()
    getattr(mock_mod, class_attr).return_value = mock_inst

    cascade: dict = {}
    # Hermetic: patch.dict auto-restores sys.modules (so the native adapter
    # mock never leaks to sibling tests, e.g. test_sora_native's real import),
    # and patch.object restores the phase_c_ffmpeg globals — including the
    # SHARED time module's sleep, which a bare assignment would leak globally.
    with patch.dict(sys.modules, {module_name: mock_mod}):
        sys.modules.pop("phase_c_ffmpeg", None)
        try:
            import phase_c_ffmpeg
            import time as _time_mod
            with patch("os.path.exists", return_value=True), \
                 patch.object(phase_c_ffmpeg, "_accept_or_reject", lambda p, a: False), \
                 patch.object(_time_mod, "sleep", lambda *_: None):
                phase_c_ffmpeg.generate_ai_video(
                    image_path="/tmp/f.png",
                    camera_motion="zoom_in_slow",
                    target_api=target_api,
                    output_mp4="/tmp/o.mp4",
                    shot_type="medium",
                    video_fallbacks=[target_api],  # nothing else → clean exhaust
                    ctx=_ctx(aspect),
                    _cascade_out=cascade,
                )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)
    return cascade


@pytest.mark.parametrize("target_api,module_name,class_attr", [
    ("KLING_NATIVE", "kling_native", "KlingNativeAPI"),
    ("SORA_NATIVE", "sora_native", "SoraNativeAPI"),
    ("VEO_NATIVE", "veo_native", "VeoNativeAPI"),
    ("LTX", "ltx_native", "LTXVideoAPI"),
])
def test_native_branch_notes_billed_attempt_on_aspect_reject(target_api, module_name, class_attr):
    cascade = _run_native(target_api, module_name, class_attr)
    # MAX_CASCADE_RETRIES=1 re-runs the single-fallback cycle, so the billed
    # generation fires twice — both are real invoices and both must be noted.
    assert cascade.get("billed_attempts") == [target_api, target_api], (
        f"{target_api} billed then aspect-rejected — spend must be noted for "
        f"the budget gate; got {cascade!r}"
    )


def test_known_broken_gemini_omni_is_denied_before_provider_or_billing() -> None:
    mock_inst = MagicMock()
    mock_mod = MagicMock()
    mock_mod.GeminiOmniAPI.return_value = mock_inst
    cascade: dict = {}
    attempted: list[str] = []

    with patch.dict(sys.modules, {"gemini_omni_native": mock_mod}):
        sys.modules.pop("phase_c_ffmpeg", None)
        try:
            import phase_c_ffmpeg
            result = phase_c_ffmpeg.generate_ai_video(
                image_path="/tmp/f.png",
                camera_motion="zoom_in_slow",
                target_api="GEMINI_OMNI",
                output_mp4="/tmp/o.mp4",
                shot_type="medium",
                attempted_apis=attempted,
                ctx=_ctx("16:9"),
                _cascade_out=cascade,
                _policy_snapshot=RuntimeSnapshot(
                    credentials={"google_api_key"},
                    modules={"google.genai"},
                ),
                _policy_date=date(2026, 9, 23),
            )
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)

    assert result is None
    assert attempted == []
    assert "billed_attempts" not in cascade
    assert cascade["policy_error"]["reason"] == "unsupported"
    assert cascade["policy_rejections"] == [
        {"key": "GEMINI_OMNI", "reason": "unsupported"},
    ]
    mock_mod.GeminiOmniAPI.assert_not_called()
    mock_inst.generate_video.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

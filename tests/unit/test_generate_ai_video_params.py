"""Regression tests for generate_ai_video parameter handling (Pair-B W1 capability recovery).

These tests invoke the REAL generate_ai_video and assert on what the engine
dispatch actually receives — deliberately NOT re-simulating cascade logic.
The re-simulation pattern in test_cascade_logic.py is precisely what let these
bugs survive: a test that re-implements the wiring cannot catch a wiring bug.

Each test corresponds to a confirmed capability-recovery fix:
- W1.1: empty-string negative_prompt must still trigger the shot-type builder
- W1.2: driving_video_path + explicit negative_prompt must survive a cascade hop
"""

from __future__ import annotations

from unittest.mock import patch


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("kling_native.KlingNativeAPI")
def test_empty_negative_prompt_still_builds_shot_type_negatives(mock_kling_cls, _mock_accept):
    """An empty-string negative_prompt (controller.py:1600's default for a shot
    with no negative_constraints) must NOT bypass the shot-type-aware negative
    builder.

    Regression: the guard was `if negative_prompt is None`, so '' slipped
    through and the engine received no negative prompt at all — losing the
    portrait-specific artifact suppression ('closed eyes', etc.).
    """
    mock_kling_cls.return_value.generate_video.return_value = "out.mp4"  # truthy = success

    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(
        image_path="in.png",
        camera_motion="static",
        target_api="KLING_NATIVE",
        output_mp4="out.mp4",
        negative_prompt="",          # <- the bug trigger: empty string, not None
        shot_type="portrait",
    )

    _, kwargs = mock_kling_cls.return_value.generate_video.call_args
    got = kwargs.get("negative_prompt", "")
    assert "closed eyes" in got, (
        "empty-string negative_prompt bypassed the shot-type builder; "
        f"engine received negative_prompt={got!r}"
    )

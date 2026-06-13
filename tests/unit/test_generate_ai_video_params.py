"""Regression tests for generate_ai_video parameter handling (Pair-B W1 capability recovery).

These tests invoke the REAL generate_ai_video and assert on what the engine
dispatch actually receives — deliberately NOT re-simulating cascade logic.
The re-simulation pattern in test_cascade_logic.py is precisely what let these
bugs survive: a test that re-implements the wiring cannot catch a wiring bug.

Each test corresponds to a confirmed capability-recovery fix:
- W1.1: empty-string negative_prompt must still trigger the shot-type builder
- W1.2: BOTH driving_video_path AND an explicit caller negative_prompt must
  survive a cascade hop — on the normal next-engine hop AND the quota-cooldown
  retry re-entry. (The negative_prompt-forward was folded into this commit per
  director2's design ruling 2026-06-13T09:50:01Z.) This is complementary to
  W1.1's builder fix (9d90889), not conflicting: the builder supplies a
  sensible shot-type default when the caller passes ''/None; the cascade
  forward preserves an EXPLICIT caller override across a hop (today the
  recursive call omits negative_prompt, so the next engine re-derives from
  shot_type only and the explicit override is lost). KLING is the cascade
  member that consumes negative_prompt; Veo/Sora/Runway consume
  driving_video_path — so the two params are asserted on their respective
  consuming engines.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# A negative the shot-type builder could never synthesize — so "received this
# exact string" proves the EXPLICIT caller override survived (vs a re-derived
# shot-type default like "blur, distortion, ..., frozen pose").
_EXPLICIT_NEG = "EXPLICIT_CALLER_NEGATIVE_SENTINEL_xyz"


@pytest.fixture(autouse=True)
def _ensure_engine_modules_patchable():
    """Guarantee kling_native.KlingNativeAPI and sora_native.SoraNativeAPI exist
    so @patch("<module>.<API>") resolves regardless of collection/run order.

    Other test files register BARE STUB engine modules in sys.modules to avoid
    loading the heavy real ones — test_dialogue_routing (kling_native, at import
    time) and test_phase_c_video_aspect (sora_native, swapped in/out at RUN time
    inside its tests). A run-time swap can leave a stub without the API class in
    sys.modules for whichever file pytest runs next, so a module-level guard
    (collection time) is not enough — this runs before EACH test instead.
    """
    for name, attr in (("kling_native", "KlingNativeAPI"), ("sora_native", "SoraNativeAPI")):
        mod = sys.modules.get(name)
        if not isinstance(mod, types.ModuleType):
            mod = types.ModuleType(name)
            sys.modules[name] = mod
        if not hasattr(mod, attr):
            setattr(mod, attr, MagicMock())
    yield


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


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("sora_native.SoraNativeAPI")
@patch("kling_native.KlingNativeAPI")
def test_driving_video_path_survives_cascade_hop(mock_kling_cls, mock_sora_cls, _mock_accept):
    """A driving_video_path set on the initial call must survive the cascade hop
    to the next engine (try_next_api's normal next-engine recursion).

    Regression (W1.2): the recursive generate_ai_video call dropped
    driving_video_path (it defaulted to ''), so a performance-capture clip was
    silently lost the moment the primary engine failed and the cascade routed to
    an engine that DOES consume it (Veo/Sora/Runway) — those engines then fell
    back to image-only motion with no log line.
    """
    # KLING (primary) fails -> cascade -> SORA (consumes driving_video_path) wins.
    mock_kling_cls.return_value.generate_video.return_value = None       # falsy -> cascade
    mock_sora_cls.return_value.generate_video.return_value = "out.mp4"   # truthy -> success

    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(
        image_path="in.png",
        camera_motion="static",
        target_api="KLING_NATIVE",
        output_mp4="out.mp4",
        shot_type="action",
        driving_video_path="perf_capture.mp4",
        video_fallbacks=["KLING_NATIVE", "SORA_NATIVE"],
    )

    _, kwargs = mock_sora_cls.return_value.generate_video.call_args
    assert kwargs.get("driving_video_path") == "perf_capture.mp4", (
        "driving_video_path was dropped on the cascade hop; SORA received "
        f"driving_video_path={kwargs.get('driving_video_path')!r}"
    )


@patch("phase_c_ffmpeg.time.sleep", return_value=None)   # skip the 30s quota cooldown
@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("sora_native.SoraNativeAPI")
def test_driving_video_path_survives_quota_cooldown_retry(mock_sora_cls, _mock_accept, _mock_sleep):
    """driving_video_path must ALSO survive the quota-cooldown retry re-entry.

    When every engine in the cascade fails once, try_next_api() waits out a
    quota cooldown and re-enters generate_ai_video from the top via the
    _cascade_retries+1 branch. That second recursive call dropped
    driving_video_path too. Single-engine cascade: SORA fails on the first pass,
    then succeeds on the retry pass — the successful retry call must still carry
    the driving clip.
    """
    mock_sora_cls.return_value.generate_video.side_effect = [None, "out.mp4"]  # fail, then succeed

    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(
        image_path="in.png",
        camera_motion="static",
        target_api="SORA_NATIVE",
        output_mp4="out.mp4",
        shot_type="action",
        driving_video_path="perf_capture.mp4",
        video_fallbacks=["SORA_NATIVE"],
    )

    # The successful retry call is the LAST generate_video call.
    _, kwargs = mock_sora_cls.return_value.generate_video.call_args
    assert kwargs.get("driving_video_path") == "perf_capture.mp4", (
        "driving_video_path was dropped on the quota-cooldown retry hop; SORA's "
        f"retry call received driving_video_path={kwargs.get('driving_video_path')!r}"
    )
    # Sanity: the retry path actually ran (initial fail + retry = 2 dispatches).
    assert mock_sora_cls.return_value.generate_video.call_count == 2


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("kling_native.KlingNativeAPI")
@patch("sora_native.SoraNativeAPI")
def test_explicit_negative_prompt_survives_cascade_hop(mock_sora_cls, mock_kling_cls, _mock_accept):
    """An EXPLICIT caller negative_prompt must survive the cascade hop to the
    next engine — not be silently re-derived from shot_type.

    Regression (W1.2): the recursive generate_ai_video call omitted
    negative_prompt, so on a cascade hop the next engine rebuilt a shot-type
    default and the caller's explicit override was lost. KLING is the cascade
    member that forwards negative_prompt to its engine call (SORA/Veo do not).
    """
    # SORA (primary) fails -> cascade -> KLING (consumes negative_prompt) wins.
    mock_sora_cls.return_value.generate_video.return_value = None        # falsy -> cascade
    mock_kling_cls.return_value.generate_video.return_value = "out.mp4"  # truthy -> success

    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(
        image_path="in.png",
        camera_motion="static",
        target_api="SORA_NATIVE",
        output_mp4="out.mp4",
        shot_type="action",              # would rebuild an "action" negative if dropped
        negative_prompt=_EXPLICIT_NEG,   # explicit caller override
        video_fallbacks=["SORA_NATIVE", "KLING_NATIVE"],
    )

    _, kwargs = mock_kling_cls.return_value.generate_video.call_args
    assert kwargs.get("negative_prompt") == _EXPLICIT_NEG, (
        "explicit negative_prompt was dropped on the cascade hop (re-derived from "
        f"shot_type); KLING received negative_prompt={kwargs.get('negative_prompt')!r}"
    )


@patch("phase_c_ffmpeg.time.sleep", return_value=None)   # skip the 30s quota cooldown
@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("kling_native.KlingNativeAPI")
def test_explicit_negative_prompt_survives_quota_cooldown_retry(mock_kling_cls, _mock_accept, _mock_sleep):
    """An explicit negative_prompt must ALSO survive the quota-cooldown retry
    re-entry (the second recursive call site, _cascade_retries+1)."""
    mock_kling_cls.return_value.generate_video.side_effect = [None, "out.mp4"]  # fail, then succeed

    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(
        image_path="in.png",
        camera_motion="static",
        target_api="KLING_NATIVE",
        output_mp4="out.mp4",
        shot_type="action",
        negative_prompt=_EXPLICIT_NEG,
        video_fallbacks=["KLING_NATIVE"],
    )

    _, kwargs = mock_kling_cls.return_value.generate_video.call_args
    assert kwargs.get("negative_prompt") == _EXPLICIT_NEG, (
        "explicit negative_prompt was dropped on the quota-cooldown retry hop; "
        f"KLING's retry call received negative_prompt={kwargs.get('negative_prompt')!r}"
    )
    # Sanity: the retry path actually ran (initial fail + retry = 2 dispatches).
    assert mock_kling_cls.return_value.generate_video.call_count == 2

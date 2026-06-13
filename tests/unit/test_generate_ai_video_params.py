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
- W1.3: a MULTI-engine all-fail cascade must terminate after MAX_CASCADE_RETRIES
  (=1), not loop forever. The next-engine hop dropped _cascade_retries (reset to
  0 each hop), so a multi-engine cascade never saw the incremented counter at its
  terminal quota-check and the 30s retry pass repeated indefinitely. (Found via
  the Rule#13 symmetric audit of W1.2's two recursion sites; single-engine
  cascades terminated, which is why the suite never caught it.)
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


class _CascadeDidNotTerminate(BaseException):
    """BaseException (NOT Exception) so the cascade's broad `except Exception`
    cannot swallow the test cap — a real infinite loop would otherwise hang."""


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("sora_native.SoraNativeAPI")
@patch("kling_native.KlingNativeAPI")
def test_multi_engine_all_fail_terminates_after_max_retries(mock_kling_cls, mock_sora_cls, _mock_accept):
    """A MULTI-engine all-fail cascade must give up after MAX_CASCADE_RETRIES (=1):
    exactly ONE 30s quota-cooldown retry, then return None.

    Regression (W1.3): the next-engine hop (try_next_api's first recursion site,
    phase_c_ffmpeg.py:176) forwarded attempted_apis but DROPPED _cascade_retries,
    resetting it to 0 on every hop. In a multi-engine cascade the terminal
    quota-check therefore never saw the incremented counter and the 30s retry pass
    repeated indefinitely (a production hang on a total video-API outage).
    Single-engine cascades terminated (no hop to reset the counter), which is why
    the suite never caught it. time.sleep is mocked + capped so a real infinite
    loop fails cleanly instead of hanging.
    """
    mock_kling_cls.return_value.generate_video.return_value = None   # KLING always fails
    mock_sora_cls.return_value.generate_video.return_value = None    # SORA always fails

    sleep_calls = []

    def _capped_sleep(_secs):
        sleep_calls.append(_secs)
        if len(sleep_calls) > 3:
            raise _CascadeDidNotTerminate(
                f"cascade slept {len(sleep_calls)}x — did not terminate after MAX_CASCADE_RETRIES"
            )

    from phase_c_ffmpeg import generate_ai_video
    looped = False
    result = "sentinel"
    with patch("phase_c_ffmpeg.time.sleep", side_effect=_capped_sleep):
        try:
            result = generate_ai_video(
                image_path="in.png",
                camera_motion="static",
                target_api="KLING_NATIVE",
                output_mp4="out.mp4",
                shot_type="action",
                video_fallbacks=["KLING_NATIVE", "SORA_NATIVE"],   # 2-engine cascade, both fail
            )
        except _CascadeDidNotTerminate:
            looped = True

    assert not looped, (
        "multi-engine all-fail cascade did not terminate — looped >3 quota retries; "
        "the next-engine hop drops _cascade_retries, resetting it to 0 each hop"
    )
    # Exactly one quota-cooldown retry (MAX_CASCADE_RETRIES=1), then give up.
    assert len(sleep_calls) == 1, f"expected exactly 1 quota retry, got {len(sleep_calls)}"
    assert result is None


# --- char-landscape routing companions (ADR-025 identity fix, 3-site) ------
# When classify_shot_type reroutes a char-bearing landscape to "wide", two
# downstream consumers branch on the shot_type STRING and must follow:
#   phase_c_ffmpeg.py:411 (LTX resolution) and :375 (Veo generate_audio).


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("ltx_native.LTXVideoAPI")
def test_ltx_wide_renders_4k(mock_ltx_cls, _mock_accept):
    """:411 companion — a `wide` shot must render LTX at 4K (wide is the
    documented 4K LTX tier), not drop to 1080p. Without this, a char-landscape
    rerouted to wide loses 4x the pixels (no auto-upscale)."""
    mock_ltx_cls.return_value.generate_video.return_value = "out.mp4"
    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(image_path="in.png", camera_motion="static",
                      target_api="LTX", output_mp4="out.mp4", shot_type="wide")
    _, kwargs = mock_ltx_cls.return_value.generate_video.call_args
    assert kwargs.get("resolution") == "4k", (
        f"wide LTX shot dropped to {kwargs.get('resolution')!r}; expected 4k")


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("ltx_native.LTXVideoAPI")
def test_ltx_landscape_still_4k(mock_ltx_cls, _mock_accept):
    """No-regression: a genuine landscape stays 4K."""
    mock_ltx_cls.return_value.generate_video.return_value = "out.mp4"
    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(image_path="in.png", camera_motion="static",
                      target_api="LTX", output_mp4="out.mp4", shot_type="landscape")
    _, kwargs = mock_ltx_cls.return_value.generate_video.call_args
    assert kwargs.get("resolution") == "4k"


@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("ltx_native.LTXVideoAPI")
def test_ltx_medium_stays_1080p(mock_ltx_cls, _mock_accept):
    """No-regression: non-wide/non-landscape stays 1080p (the broaden is scoped)."""
    mock_ltx_cls.return_value.generate_video.return_value = "out.mp4"
    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(image_path="in.png", camera_motion="static",
                      target_api="LTX", output_mp4="out.mp4", shot_type="medium")
    _, kwargs = mock_ltx_cls.return_value.generate_video.call_args
    assert kwargs.get("resolution") == "1080p"


@pytest.mark.parametrize(
    "shot_type,has_dialogue,native,expected_audio",
    [
        ("wide", False, False, True),       # rerouted char-landscape, no dialogue → ambient restored (the fix)
        ("wide", True, False, False),       # overlay dialogue → NO Veo ambient (avoid double-voice)
        ("wide", True, True, True),          # native dialogue → Veo generates it
        ("landscape", False, False, True),  # no-regression: genuine landscape keeps ambient
        ("medium", False, False, False),    # no-regression: medium no-dialogue stays silent (scene-TTS owns it)
        ("medium", True, True, True),       # PM7 cell: native dialogue on a non-wide shot → Veo generates it
    ],
)
@patch("phase_c_ffmpeg._accept_or_reject", return_value=True)
@patch("veo_native.VeoNativeAPI")
def test_veo_generate_audio_guarded_broaden(
    mock_veo_cls, _mock_accept, shot_type, has_dialogue, native, expected_audio
):
    """:375 companion — guarded-broaden (director2 Pair-B call): `wide` shots get
    Veo ambient UNLESS overlay-dialogue (`has_dialogue and not dialogue_native_audio`),
    which preserves ambient on rerouted no-dialogue char-landscapes while avoiding
    double-voice on genuine wide+overlay-dialogue shots."""
    mock_veo_cls.return_value.generate_video.return_value = "out.mp4"
    from phase_c_ffmpeg import generate_ai_video
    generate_ai_video(image_path="in.png", camera_motion="static",
                      target_api="VEO_NATIVE", output_mp4="out.mp4",
                      shot_type=shot_type, has_dialogue=has_dialogue,
                      dialogue_native_audio=native)
    _, kwargs = mock_veo_cls.return_value.generate_video.call_args
    assert kwargs.get("generate_audio") == expected_audio, (
        f"{shot_type} has_dialogue={has_dialogue} native={native}: got "
        f"generate_audio={kwargs.get('generate_audio')!r}, expected {expected_audio}")

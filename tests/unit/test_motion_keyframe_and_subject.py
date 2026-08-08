"""The approved keyframe reaching the video call, and prompts that stop
asserting a face is present.

TWO FINDINGS, both in the motion stage.

1. THE fal VEO BRANCH DISCARDED THE APPROVED KEYFRAME. Its comment read "Always
   include the source keyframe" directly above `if not image_urls:` — so the
   keyframe was sent ONLY when the character had no references. On every
   ordinary shot the frame the operator approved was thrown away and the video
   was generated from four face photographs plus prose. Everything the still
   stage puts into that frame — composition, lighting, wardrobe as rendered, the
   product and the room — reached the motion stage and was dropped.

   This is a reference-to-video endpoint, so there is no separate start-frame
   slot to lose; every image is a reference and the keyframe is simply the
   highest-information one. Every OTHER provider already sends it: Kling as
   start_image_url, Seedance as keyframe_url, Gemini Omni as input_items[0],
   VEO_NATIVE as the image-to-video start frame (where reference_images are
   mutually exclusive with it — veo_native.py:370-384). This branch was alone.

2. EVERY MOTION PROMPT ASSERTED A FACE. All four said "maintain rigid facial
   bone structure — zero face deformation between frames", unconditionally. On a
   product or establishing shot there is no face, and the sentence sits in the
   prompt's highest-attention position asking the model to preserve something
   that is not there.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _ctx(aspect: str = "16:9"):
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={"aspect_ratio": aspect})


def _run(target_api: str, **kwargs):
    """Drive generate_ai_video with a stubbed fal_client.

    Harness mirrors tests/unit/test_seedance_dispatch.py::_run_seedance.
    """

    stub_fal = MagicMock()
    stub_fal.subscribe.return_value = {"video": {"url": "https://x/out.mp4"}}
    stub_fal.upload_file.side_effect = lambda p: f"url://{str(p).split('/')[-1]}"

    stub_settings = MagicMock()
    stub_settings.fal_key = "fk-test-key"

    sys.modules.pop("phase_c_ffmpeg", None)
    with patch("os.path.exists", return_value=True), \
         patch("urllib.request.urlretrieve"), \
         patch.dict("sys.modules", {"veo_native": MagicMock()}):
        import phase_c_ffmpeg
        phase_c_ffmpeg.fal_client = stub_fal
        phase_c_ffmpeg.FAL_AVAILABLE = True
        phase_c_ffmpeg.settings = stub_settings
        phase_c_ffmpeg.time.sleep = lambda *_: None
        phase_c_ffmpeg.safe_download = lambda url, out, **_k: out
        phase_c_ffmpeg._VEO_QUOTA_EXHAUSTED_UNTIL = 0.0
        kwargs.setdefault("shot_type", "medium")
        phase_c_ffmpeg.generate_ai_video(
            image_path="/tmp/keyframe.png",
            camera_motion="tracking_shot",
            target_api=target_api,
            output_mp4="/tmp/out.mp4",
            video_fallbacks=[target_api],
            ctx=_ctx(),
            **kwargs,
        )
    return stub_fal


def _arguments(stub_fal):
    assert stub_fal.subscribe.called, "the provider was never dispatched"
    return stub_fal.subscribe.call_args.kwargs["arguments"]


# ---------------------------------------------------------------------------
# The keyframe
# ---------------------------------------------------------------------------

def test_veo_now_leads_with_the_approved_keyframe() -> None:
    stub = _run("VEO", multi_angle_refs=[f"/refs/face_{i}.jpg" for i in range(4)])
    urls = _arguments(stub)["image_urls"]
    assert urls[0] == "url://keyframe.png"


def test_veo_keeps_the_keyframe_inside_the_provider_cap() -> None:
    """The keyframe joins the SAME budget rather than widening it. One fewer
    face reaches VEO; the approved composition reaches it at all."""

    import phase_c_ffmpeg

    stub = _run("VEO", multi_angle_refs=[f"/refs/face_{i}.jpg" for i in range(10)])
    urls = _arguments(stub)["image_urls"]
    assert len(urls) == phase_c_ffmpeg._VEO_REFERENCE_CAP
    assert urls[0] == "url://keyframe.png"
    assert urls.count("url://keyframe.png") == 1


def test_veo_with_no_references_still_sends_the_keyframe() -> None:
    """The only case the old code got right, preserved."""

    stub = _run("VEO", multi_angle_refs=None)
    assert _arguments(stub)["image_urls"] == ["url://keyframe.png"]


def test_seedance_already_led_with_the_keyframe_and_still_does() -> None:
    """Control: the house pattern VEO was the exception to. If this ever stops
    holding, the VEO change was a mistake rather than a correction."""

    stub = _run("SEEDANCE", multi_angle_refs=[f"/refs/face_{i}.jpg" for i in range(3)])
    urls = _arguments(stub)["image_urls"]
    assert urls[0] == "url://keyframe.png"


def test_kling_3_0_sends_the_keyframe_as_its_start_image() -> None:
    """Control on a second provider, and a different mechanism: Kling keeps the
    keyframe in `start_image_url` and puts references beside it."""

    stub = _run("KLING_3_0", multi_angle_refs=["/refs/face_0.jpg"])
    assert _arguments(stub)["start_image_url"] == "url://keyframe.png"


# ---------------------------------------------------------------------------
# The subject clause
# ---------------------------------------------------------------------------

def test_the_clause_asks_for_a_face_only_when_one_is_expected() -> None:
    import phase_c_ffmpeg as m

    with_face = m._subject_preservation_clause("char_1")
    without = m._subject_preservation_clause("")
    assert "facial bone structure" in with_face
    assert "facial bone structure" not in without
    # The non-face clause still asks for temporal stability, which is what a
    # product needs most: a logo re-rendered per frame is the first thing to swim.
    assert "logos" in without and "legible" in without


@pytest.mark.parametrize(
    "target_api", ["VEO", "SEEDANCE", "KLING_3_0"],
)
def test_a_shot_with_no_character_is_not_told_to_preserve_a_face(target_api) -> None:
    """A product or establishing shot has no face, and the instruction sits in
    the prompt's highest-attention position."""

    stub = _run(target_api, multi_angle_refs=["/refs/hero.jpg"], character_id="")
    prompt = _arguments(stub)["prompt"]
    assert "facial bone structure" not in prompt
    assert "shape, proportions, surface finish" in prompt


@pytest.mark.parametrize(
    "target_api", ["VEO", "SEEDANCE", "KLING_3_0"],
)
def test_a_shot_with_a_character_still_gets_the_face_language(target_api) -> None:
    """Control for the test above — the face clause must be able to be present,
    or the parametrised assertion would pass on a prompt that lost it entirely."""

    stub = _run(target_api, multi_angle_refs=["/refs/face.jpg"], character_id="char_1")
    prompt = _arguments(stub)["prompt"]
    assert "facial bone structure" in prompt


def test_veo_never_sends_more_images_than_the_endpoint_accepts() -> None:
    """MEASURED against the live endpoint 2026-08-09, one variable:

        4 images -> FAILS, 3 of 3, `no_media_generated`
        3 images -> succeeds
        2 images -> succeeds
        1 image  -> succeeds

    The `[:4]` this pins replaced was never reachable, which means the ORIGINAL
    code was already broken for any character with four or more references —
    four images went out, the soft `no_media_generated` came back, and the
    cascade quietly used another engine. On this project the character has ten.

    A soft model-side error is why it hid: it reads like the model declining a
    prompt rather than like a request that cannot succeed.
    """

    import phase_c_ffmpeg

    assert phase_c_ffmpeg._VEO_REFERENCE_CAP == 3
    stub = _run("VEO", multi_angle_refs=[f"/refs/face_{i}.jpg" for i in range(10)])
    urls = _arguments(stub)["image_urls"]
    assert len(urls) <= 3, f"VEO cannot accept {len(urls)} images"
    assert urls[0] == "url://keyframe.png"

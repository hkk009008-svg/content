"""Tests for the fal-based Seedance 2.0 dispatch (2026-07-11 Sora-sunset migration).

The SEEDANCE branch moved from an inline requests.post to the hallucinated
``api.seedance.ai`` REST surface (with a hardcoded 16:9 aspect) onto fal.ai:
``bytedance/seedance-2.0/image-to-video`` for keyframe animation and
``.../reference-to-video`` when multi-angle identity refs exist. The old
null-task_id guard (D1) died with the poll loop — fal_client.subscribe owns
polling/timeouts now (bounded by FAL_TIMEOUT_VIDEO_S).

Contract pinned here:
- FAL_KEY missing → immediate cascade, fal never called, clean exhaust → None.
- No refs → i2v endpoint, ``image_url`` (singular), no ``image_urls``.
- Refs present → r2v endpoint, ``image_urls`` with the keyframe FIRST, ≤9 total.
- Payload: resolution 720p, generate_audio False (assembly owns audio),
  duration 8 for action shots, aspect_ratio from fal_aspect_ratio(ctx aspect)
  — SEEDANCE is PORTRAIT_CAPABLE since this migration.

All tests are offline — no fal, no network, no spend.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _ctx(aspect: str):
    from cinema.context import PipelineContext
    return PipelineContext(global_settings={"aspect_ratio": aspect})


def _run_seedance(
    aspect: str = "16:9",
    fal_key: str = "fk-test-key",
    multi_angle_refs: list | None = None,
    shot_type: str = "action",
    download_ok: bool = True,
    cascade_out: dict | None = None,
):
    """Drive generate_ai_video(SEEDANCE) with a stubbed fal_client; return
    (stub_fal, result)."""
    stub_fal = MagicMock()
    stub_fal.subscribe.return_value = {"video": {"url": "https://x/seedance.mp4"}}
    # Distinct upload URLs so keyframe-vs-ref ordering is assertable.
    stub_fal.upload_file.side_effect = (
        lambda p: f"https://cdn.fal.ai/up{stub_fal.upload_file.call_count}.png"
    )

    stub_settings = MagicMock()
    stub_settings.fal_key = fal_key

    sys.modules.pop("phase_c_ffmpeg", None)
    try:
        with patch("os.path.exists", return_value=True), \
             patch("urllib.request.urlretrieve"), \
             patch.dict("sys.modules", {"veo_native": MagicMock()}):
            import phase_c_ffmpeg
            phase_c_ffmpeg.fal_client = stub_fal
            phase_c_ffmpeg.FAL_AVAILABLE = True
            phase_c_ffmpeg.settings = stub_settings
            phase_c_ffmpeg.time.sleep = lambda *_: None  # cascade retry pause
            # Same boundary as the VEO/SORA fal tests: stub safe_download so the
            # subscribe-returned URL isn't really downloaded (offline + no cascade).
            # download_ok=False simulates a BILLED generation whose download
            # fails (safe_download contract: None on failure).
            phase_c_ffmpeg.safe_download = (
                (lambda url, out: out) if download_ok else (lambda url, out: None)
            )
            result = phase_c_ffmpeg.generate_ai_video(
                image_path="/tmp/keyframe.png",
                camera_motion="tracking_shot",
                target_api="SEEDANCE",
                output_mp4="/tmp/seedance_out.mp4",
                shot_type=shot_type,
                multi_angle_refs=multi_angle_refs,
                video_fallbacks=["SEEDANCE"],  # nothing else to try → clean exhaust
                ctx=_ctx(aspect),
                _cascade_out=cascade_out,
            )
    finally:
        sys.modules.pop("phase_c_ffmpeg", None)

    return stub_fal, result


class TestSeedanceFalKeyGate:
    def test_missing_fal_key_cascades_without_calling_fal(self):
        """No FAL_KEY → the branch must cascade immediately: zero fal traffic,
        clean exhaust returns None (no false success)."""
        stub_fal, result = _run_seedance(fal_key="")
        assert stub_fal.subscribe.call_count == 0, (
            "Seedance called fal_client.subscribe without a FAL_KEY"
        )
        assert stub_fal.upload_file.call_count == 0, (
            "Seedance uploaded files without a FAL_KEY"
        )
        assert result is None


class TestSeedanceEndpointSelection:
    def test_no_refs_uses_image_to_video_with_singular_image_url(self):
        """Keyframe-only shot → i2v endpoint; payload must carry image_url
        (singular) and no image_urls."""
        stub_fal, _ = _run_seedance(multi_angle_refs=None)
        assert stub_fal.subscribe.call_count == 1
        call = stub_fal.subscribe.call_args
        assert call.args and call.args[0] == "bytedance/seedance-2.0/image-to-video", (
            f"Wrong fal endpoint; got positional args: {call.args}"
        )
        arguments = call.kwargs.get("arguments", {})
        assert "image_url" in arguments and "image_urls" not in arguments, (
            f"i2v payload shape wrong: {arguments}"
        )

    def test_refs_use_reference_to_video_keyframe_first(self):
        """Multi-angle refs → r2v endpoint; image_urls has the keyframe FIRST
        then the refs, ≤9 total."""
        stub_fal, _ = _run_seedance(multi_angle_refs=["/tmp/ref_a.png", "/tmp/ref_b.png"])
        call = stub_fal.subscribe.call_args
        assert call.args and call.args[0] == "bytedance/seedance-2.0/reference-to-video", (
            f"Wrong fal endpoint; got positional args: {call.args}"
        )
        arguments = call.kwargs.get("arguments", {})
        urls = arguments.get("image_urls")
        assert urls and len(urls) == 3 and len(urls) <= 9, f"image_urls wrong: {urls}"
        # Refs upload first (call_count 1..N), keyframe last (N+1) — but the
        # keyframe must be FIRST in the payload list.
        keyframe_url = f"https://cdn.fal.ai/up{stub_fal.upload_file.call_count}.png"
        assert urls[0] == keyframe_url, (
            f"Keyframe must lead image_urls; got order: {urls}"
        )
        assert "image_url" not in arguments, f"r2v must not carry singular image_url: {arguments}"

    def test_refs_capped_at_nine_total(self):
        """The fal r2v schema caps image_urls at 9 — with 12 refs offered, the
        payload must carry the keyframe + at most 8 refs."""
        stub_fal, _ = _run_seedance(
            multi_angle_refs=[f"/tmp/ref_{i}.png" for i in range(12)]
        )
        arguments = stub_fal.subscribe.call_args.kwargs.get("arguments", {})
        urls = arguments.get("image_urls")
        assert urls is not None and len(urls) == 9, (
            f"12 offered refs must clamp to keyframe+8 (9 total); got "
            f"{len(urls) if urls else urls}"
        )


class TestSeedancePayloadContract:
    def test_action_payload_defaults(self):
        """Action shot → duration 8, resolution 720p, generate_audio False."""
        stub_fal, _ = _run_seedance(shot_type="action")
        arguments = stub_fal.subscribe.call_args.kwargs.get("arguments", {})
        assert arguments.get("duration") == 8, f"action duration wrong: {arguments}"
        assert arguments.get("resolution") == "720p", f"resolution wrong: {arguments}"
        assert arguments.get("generate_audio") is False, (
            f"assembly owns audio — generate_audio must be False: {arguments}"
        )

    def test_portrait_aspect_threads_9_16(self):
        """Portrait ctx → arguments['aspect_ratio'] == '9:16' (SEEDANCE is
        PORTRAIT_CAPABLE since the fal migration)."""
        stub_fal, _ = _run_seedance(aspect="9:16", shot_type="portrait")
        arguments = stub_fal.subscribe.call_args.kwargs.get("arguments", {})
        assert arguments.get("aspect_ratio") == "9:16", (
            f"Expected aspect_ratio='9:16'; got: {arguments}"
        )
        assert arguments.get("duration") == 4, f"portrait duration wrong: {arguments}"

    def test_landscape_keeps_16_9(self):
        """Landscape ctx → arguments['aspect_ratio'] == '16:9' (refute)."""
        stub_fal, _ = _run_seedance(aspect="16:9")
        arguments = stub_fal.subscribe.call_args.kwargs.get("arguments", {})
        assert arguments.get("aspect_ratio") == "16:9", (
            f"Expected aspect_ratio='16:9'; got: {arguments}"
        )


class TestBilledAttemptProducer:
    """Producer-side pin for the billed-but-rejected recording (money-gate
    NIT-1, 2026-07-11): the DISPATCH must note every billed generation
    (provider returned a video) in _cascade_out['billed_attempts'] — even
    when the download then fails — or the controller-side reject recording
    silently dies with every test staying green."""

    def test_download_failure_still_notes_billed_attempt(self):
        cascade: dict = {}
        _, result = _run_seedance(download_ok=False, cascade_out=cascade)
        # TWO attempts: the first billed generation fails its download, the
        # cascade exhausts, and MAX_CASCADE_RETRIES=1 re-runs the full cycle
        # — billing a SECOND generation that also fails. Both are real fal
        # invoices and both must be visible to the budget gate.
        assert cascade.get("billed_attempts") == ["SEEDANCE", "SEEDANCE"], (
            f"billed generations with failed downloads must ALL be noted; "
            f"got {cascade!r}"
        )
        assert result is None  # exhausted after the retry cycle

    def test_successful_win_notes_attempt_and_metadata(self):
        cascade: dict = {}
        _run_seedance(cascade_out=cascade)
        assert cascade.get("billed_attempts") == ["SEEDANCE"]
        assert cascade.get("cascade_metadata", {}).get("engine") == "SEEDANCE"


class TestSeedancePortraitCapable:
    def test_seedance_in_portrait_capable(self):
        """The portrait cascade filter must not drop the new portrait/medium
        fallback — SEEDANCE joined PORTRAIT_CAPABLE with the fal migration."""
        sys.modules.pop("phase_c_ffmpeg", None)
        try:
            with patch.dict("sys.modules", {"veo_native": MagicMock()}):
                import phase_c_ffmpeg
                assert "SEEDANCE" in phase_c_ffmpeg.PORTRAIT_CAPABLE
        finally:
            sys.modules.pop("phase_c_ffmpeg", None)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

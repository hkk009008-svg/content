"""
Task 12: lip_sync.lipsync_generation must NOT attempt Kling's lipsync endpoint
(fal-ai/kling-video/lipsync/audio-to-video) in the still-image generation cascade.

That endpoint is an OVERLAY endpoint — it requires video_url — so calling it with
only an image_url (the generation path's input) 422s on every call (verified live
2026-07-18: HTTP 422, x-fal-billable-units:0). It is dead weight that wastes a
round-trip before falling through to OmniHuman. Kling stays untouched in
lipsync_overlay (a separate, real video path) — this test only covers
lipsync_generation.

Post-fix generation cascade: OmniHuman v1.5 (ATTEMPT 0) -> Creatify Aurora (ATTEMPT 1).

Mocking pattern mirrors tests/unit/test_f1b_dialogue_lipsync.py::
TestLipsyncOrientationBackstop, which already drives the real lipsync_generation
with fal_client / prerequisites / gate / orientation-backstop mocked.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import lip_sync

KLING_LIPSYNC_ENDPOINT = "fal-ai/kling-video/lipsync/audio-to-video"
OMNIHUMAN_ENDPOINT = "fal-ai/bytedance/omnihuman/v1.5"
AURORA_ENDPOINT = "fal-ai/creatify/aurora"


def _run_generation(tmp_path):
    """Drive the REAL lip_sync.lipsync_generation with all externals mocked.

    fal_client.subscribe is replaced with a recorder that succeeds ONLY for the
    OmniHuman endpoint (returns a video url) so we can observe exactly which
    endpoint strings the cascade attempts, and in what order.
    """
    out = str(tmp_path / "ls.mp4")
    open(str(tmp_path / "face.jpg"), "wb").close()
    open(str(tmp_path / "a.wav"), "wb").close()

    called_endpoints: list[str] = []

    def _fake_subscribe(endpoint, **kwargs):
        called_endpoints.append(endpoint)
        if endpoint == OMNIHUMAN_ENDPOINT:
            return {"video": {"url": "http://fake/omnihuman.mp4"}, "duration": 3.0}
        # Any other engine (e.g. a still-present Kling attempt, or Aurora if
        # OmniHuman were skipped): no "video" key -> lipsync_generation treats
        # this as "no video_url" and falls through to the next attempt, mirroring
        # a real 422 (no video produced) without needing to raise.
        return {}

    def _fake_download(url, path, *a, **k):
        open(path, "wb").close()
        return path

    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "http://fake/upload"
    fake_fal.subscribe.side_effect = _fake_subscribe

    prereq = types.SimpleNamespace(passed=True, warnings=[], blockers=[])

    with patch("lip_sync.FAL_AVAILABLE", True), \
         patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key="k")), \
         patch("lip_sync.check_generation_prerequisites", return_value=prereq), \
         patch("lip_sync.fal_client", fake_fal), \
         patch("lip_sync.safe_download", side_effect=_fake_download), \
         patch("lip_sync.validate_lipsync_quality", return_value=0.91), \
         patch("phase_c_ffmpeg.probe_final_media",
               return_value={"format": {"width": 1920, "height": 1080}}):
        result = lip_sync.lipsync_generation(
            character_image_path=str(tmp_path / "face.jpg"),
            audio_path=str(tmp_path / "a.wav"),
            output_path=out,
        )
    return result, out, called_endpoints


class TestGenerationCascadeDropsKling:
    """Kling's lipsync endpoint requires video_url and 422s on every still-image
    generation call — it must never be attempted from lipsync_generation."""

    def test_kling_endpoint_never_attempted(self, tmp_path):
        _result, _out, called = _run_generation(tmp_path)
        assert KLING_LIPSYNC_ENDPOINT not in called, (
            "Kling's overlay-only lipsync endpoint must NEVER be attempted in "
            f"the still-image generation cascade; called endpoints={called!r}"
        )

    def test_omnihuman_is_attempt_zero(self, tmp_path):
        """OmniHuman v1.5 must be the FIRST engine attempted (ATTEMPT 0) now
        that the miswired Kling attempt is dropped."""
        _result, _out, called = _run_generation(tmp_path)
        assert called, "no fal_client.subscribe call was recorded at all"
        assert called[0] == OMNIHUMAN_ENDPOINT, (
            f"OmniHuman must be ATTEMPT 0 in the generation cascade; "
            f"first call was {called[0]!r}, full sequence={called!r}"
        )

    def test_generation_succeeds_via_omnihuman(self, tmp_path):
        """Sanity check: the cascade still produces a usable output when
        OmniHuman succeeds — the fix must not break the success path."""
        result, out, called = _run_generation(tmp_path)
        assert result == out, f"expected success via OmniHuman; called={called!r}"

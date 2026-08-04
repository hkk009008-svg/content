"""Offline contract tests for Runway Gen-4 image data URIs."""

from __future__ import annotations

import base64
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import phase_c_ffmpeg
from domain.provider_catalog import RuntimeSnapshot


JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-payload"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-payload"
WEBP = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"webp-payload"


@pytest.mark.parametrize(
    ("suffix", "payload", "mime"),
    [
        (".jpg", JPEG, "image/jpeg"),
        (".jpeg", JPEG, "image/jpeg"),
        (".png", PNG, "image/png"),
        (".webp", WEBP, "image/webp"),
    ],
)
def test_runway_data_uri_declares_content_detected_mime(
    suffix, payload, mime, tmp_path
):
    image_path = tmp_path / f"frame{suffix}"
    image_path.write_bytes(payload)

    data_uri = phase_c_ffmpeg._runway_image_data_uri(str(image_path))

    prefix, encoded = data_uri.split(",", 1)
    assert prefix == f"data:{mime};base64"
    assert base64.b64decode(encoded) == payload


@pytest.mark.parametrize(
    ("suffix", "payload", "error"),
    [
        (".jpg", PNG, "suffix/content mismatch"),
        (".png", b"not-an-image", "not a supported"),
        (".gif", JPEG, "must use"),
    ],
)
def test_runway_data_uri_rejects_mismatched_or_unsupported_input(
    suffix, payload, error, tmp_path
):
    image_path = tmp_path / f"frame{suffix}"
    image_path.write_bytes(payload)

    with pytest.raises(ValueError, match=error):
        phase_c_ffmpeg._runway_image_data_uri(str(image_path))


def test_runway_gen4_rejects_bad_image_before_client_or_submission(tmp_path):
    image_path = tmp_path / "mislabeled.jpg"
    image_path.write_bytes(PNG)

    runway_module = MagicMock()
    runtime = RuntimeSnapshot(
        credentials={"runwayml_api_secret"},
        modules={"runwayml"},
    )

    with (
        patch.dict(sys.modules, {"runwayml": runway_module}),
        patch.object(
            phase_c_ffmpeg,
            "settings",
            SimpleNamespace(runwayml_api_secret="rw-test"),
        ),
        patch.object(
            phase_c_ffmpeg,
            "_video_policy_runtime_snapshot",
            return_value=runtime,
        ),
        patch.object(
            phase_c_ffmpeg,
            "_video_policy_current_date",
            return_value=date(2026, 9, 23),
        ),
    ):
        result = phase_c_ffmpeg.generate_ai_video(
            image_path=str(image_path),
            camera_motion="static",
            target_api="RUNWAY_GEN4",
            output_mp4=str(tmp_path / "out.mp4"),
        )

    assert result is None
    runway_module.RunwayML.assert_not_called()

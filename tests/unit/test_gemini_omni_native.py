"""Unit tests for gemini_omni_native.GeminiOmniAPI (WS2 step 1).

Mirrors tests/unit/test_veo_native_config.py's conventions (bypass __init__ via
__new__, capture kwargs via side_effect, patch os.path.exists/getsize/open).

All tests are offline — no real API calls, no network, no spend (COST CONTROL).
"""
from __future__ import annotations

import base64
import sys
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Sibling unit tests stub heavy native-API modules into sys.modules at import
# time; drop any stub so this module always exercises the REAL implementation
# (mirrors test_veo_native_config.py's sys.modules.pop guard).
sys.modules.pop("gemini_omni_native", None)

from gemini_omni_native import (  # noqa: E402
    GeminiOmniAPI,
    _encode_image_b64,
    _TERMINAL_INTERACTION_STATUSES,
)


# ---------------------------------------------------------------------------
# __init__ — key resolution + graceful-raise contract
# ---------------------------------------------------------------------------


def test_init_raises_when_no_key_available():
    fake_settings = MagicMock(google_api_key="", gemini_api_key="")
    with patch("gemini_omni_native.settings", fake_settings):
        with pytest.raises(EnvironmentError, match="GOOGLE_API_KEY.*GEMINI_API_KEY"):
            GeminiOmniAPI()


def test_init_prefers_google_api_key():
    fake_settings = MagicMock(google_api_key="goog-key", gemini_api_key="gem-key")
    with patch("gemini_omni_native.settings", fake_settings), \
         patch("gemini_omni_native.genai.Client") as mock_client_cls:
        api = GeminiOmniAPI()
        mock_client_cls.assert_called_once_with(api_key="goog-key")
        assert api._model == "gemini-omni-flash-preview"


def test_init_falls_back_to_gemini_api_key():
    fake_settings = MagicMock(google_api_key="", gemini_api_key="gem-key")
    with patch("gemini_omni_native.settings", fake_settings), \
         patch("gemini_omni_native.genai.Client") as mock_client_cls:
        GeminiOmniAPI()
        mock_client_cls.assert_called_once_with(api_key="gem-key")


# ---------------------------------------------------------------------------
# _encode_image_b64 — pure(ish) helper
# ---------------------------------------------------------------------------


def test_encode_image_b64_roundtrips(tmp_path):
    p = tmp_path / "frame.jpg"
    p.write_bytes(b"fake-jpeg-bytes")
    encoded = _encode_image_b64(str(p))
    assert base64.b64decode(encoded) == b"fake-jpeg-bytes"


# ---------------------------------------------------------------------------
# generate_video — missing start frame guards before the try block
# ---------------------------------------------------------------------------


def test_generate_video_missing_image_returns_none():
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)  # bypass __init__ (no real client)
    api.client = MagicMock()
    api._model = "gemini-omni-flash-preview"

    with patch("gemini_omni_native.os.path.exists", return_value=False):
        result = api.generate_video(
            image_path="/tmp/missing.png", prompt="x", output_path="/tmp/out.mp4",
        )

    assert result is None
    api.client.interactions.create.assert_not_called()


# ---------------------------------------------------------------------------
# generate_video — happy path, inline video data
# ---------------------------------------------------------------------------


def _completed_interaction(with_inline_data: bool = True):
    interaction = MagicMock()
    interaction.status = "completed"
    interaction.id = "interaction-123"
    if with_inline_data:
        interaction.output_video.data = b"VIDEO_BYTES"
        interaction.output_video.uri = None
    else:
        interaction.output_video.data = None
        interaction.output_video.uri = "files/abc123"
    return interaction


def test_generate_video_writes_inline_bytes_and_returns_output_path(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
    )

    assert result == output_path
    with open(output_path, "rb") as f:
        assert f.read() == b"VIDEO_BYTES"
    # Terminal completed interaction: no polling round-trip needed.
    api.client.interactions.get.assert_not_called()


def test_generate_video_task_is_image_to_video_without_refs(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=str(tmp_path / "out.mp4"),
    )

    kwargs = api.client.interactions.create.call_args.kwargs
    assert kwargs["generation_config"]["video_config"]["task"] == "image_to_video"
    assert kwargs["model"] == "gemini-omni-flash-preview"
    # Only the start frame + text — no reference images supplied.
    assert len(kwargs["input"]) == 2
    assert kwargs["input"][-1] == {"type": "text", "text": "hello"}


def test_generate_video_task_is_reference_to_video_with_refs(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    ref1 = tmp_path / "ref1.jpg"
    ref1.write_bytes(b"ref-one")
    ref2 = tmp_path / "ref2.jpg"
    ref2.write_bytes(b"ref-two")

    api.generate_video(
        image_path=str(image_path),
        prompt="hello",
        output_path=str(tmp_path / "out.mp4"),
        reference_images=[str(ref1), str(ref2)],
    )

    kwargs = api.client.interactions.create.call_args.kwargs
    assert kwargs["generation_config"]["video_config"]["task"] == "reference_to_video"
    # start frame + 2 refs + text = 4 input items.
    assert len(kwargs["input"]) == 4


def test_generate_video_threads_aspect_ratio(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    api.generate_video(
        image_path=str(image_path),
        prompt="hello",
        output_path=str(tmp_path / "out.mp4"),
        aspect_ratio="9:16",
    )

    kwargs = api.client.interactions.create.call_args.kwargs
    assert kwargs["response_format"]["aspect_ratio"] == "9:16"
    assert kwargs["response_format"]["delivery"] == "uri"


# ---------------------------------------------------------------------------
# generate_video — uri delivery path (Files API poll + download)
# ---------------------------------------------------------------------------


def test_generate_video_downloads_via_files_api_when_uri_delivered(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)

    active_file = MagicMock()
    active_file.state = "ACTIVE"
    api.client.files.get.return_value = active_file
    api.client.files.download.return_value = b"DOWNLOADED_BYTES"

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
    )

    assert result == output_path
    with open(output_path, "rb") as f:
        assert f.read() == b"DOWNLOADED_BYTES"
    api.client.files.get.assert_called_with(name="files/abc123")
    api.client.files.download.assert_called_once_with(file=active_file)


def test_generate_video_polls_files_api_until_active(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)

    processing_file = MagicMock()
    processing_file.state = "PROCESSING"
    active_file = MagicMock()
    active_file.state = "ACTIVE"
    api.client.files.get.side_effect = [processing_file, active_file]
    api.client.files.download.return_value = b"DOWNLOADED_BYTES"

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    with patch("gemini_omni_native.time.sleep", return_value=None):
        result = api.generate_video(
            image_path=str(image_path), prompt="hello", output_path=output_path,
        )

    assert result == output_path
    assert api.client.files.get.call_count == 2


# ---------------------------------------------------------------------------
# generate_video — interaction polling loop
# ---------------------------------------------------------------------------


def test_generate_video_polls_interaction_until_terminal(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()

    pending = MagicMock()
    pending.status = "pending"
    pending.id = "interaction-123"
    completed = _completed_interaction(with_inline_data=True)

    api.client.interactions.create.return_value = pending
    api.client.interactions.get.return_value = completed

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    with patch("gemini_omni_native.time.sleep", return_value=None):
        result = api.generate_video(
            image_path=str(image_path), prompt="hello", output_path=output_path,
        )

    assert result == output_path
    api.client.interactions.get.assert_called_once_with("interaction-123")


# ---------------------------------------------------------------------------
# generate_video — non-completed terminal status → graceful None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete", "budget_exceeded"])
def test_generate_video_returns_none_on_non_completed_terminal_status(tmp_path, status):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()

    interaction = MagicMock()
    interaction.status = status
    api.client.interactions.create.return_value = interaction

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=str(tmp_path / "out.mp4"),
    )

    assert result is None


def test_terminal_statuses_include_budget_exceeded():
    # GEMINI_OMNI's own terminal-status vocabulary (phase_c_ffmpeg.py's cooldown
    # string-match adds "budget_exceeded" alongside Veo's 429/quota/exhausted).
    assert "budget_exceeded" in _TERMINAL_INTERACTION_STATUSES
    assert "completed" in _TERMINAL_INTERACTION_STATUSES


# ---------------------------------------------------------------------------
# generate_video — blanket exception → graceful None (cascade-fallthrough contract)
# ---------------------------------------------------------------------------


def test_generate_video_returns_none_on_exception(tmp_path, capsys):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.side_effect = RuntimeError("429 quota exceeded")

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=str(tmp_path / "out.mp4"),
    )

    assert result is None
    out = capsys.readouterr().out
    assert "[GEMINI-OMNI] Generation failed" in out
    assert "429 quota exceeded" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

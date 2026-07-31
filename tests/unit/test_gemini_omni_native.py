"""Unit tests for gemini_omni_native.GeminiOmniAPI (WS2 step 1).

Mirrors tests/unit/test_veo_native_config.py's conventions (bypass __init__ via
__new__, capture kwargs via side_effect, patch os.path.exists/getsize/open).

All tests are offline — no real API calls, no network, no spend (COST CONTROL).
"""
from __future__ import annotations

import base64
import os
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
        # Real google.genai VideoContent.data is Optional[str] — base64 TEXT,
        # never raw bytes (confirmed against the installed SDK: `from
        # google.genai._interactions.types import VideoContent;
        # VideoContent.model_fields["data"].annotation` == `Optional[str]`).
        interaction.output_video.data = base64.b64encode(b"VIDEO_BYTES").decode("ascii")
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
    active_file.download_uri = (
        "https://generativelanguage.googleapis.com/v1beta/files/abc123:download?alt=media"
    )
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
    # Downloads the RETURNED output URI from the polled file resource (the
    # SDK's own documented usage: client.files.download(file=file.download_uri)),
    # not the file object or the original video.uri.
    api.client.files.download.assert_called_once_with(file=active_file.download_uri)


def test_generate_video_polls_files_api_until_active(tmp_path):
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)

    processing_file = MagicMock()
    processing_file.state = "PROCESSING"
    active_file = MagicMock()
    active_file.state = "ACTIVE"
    active_file.download_uri = "https://.../files/abc123:download?alt=media"
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


def test_generate_video_returns_none_on_file_processing_failed(tmp_path):
    """URI failed terminal: the Files API resource itself can reach FAILED
    state (distinct from the interaction's own status). Pre-fix, the poll
    loop only checked `!= "ACTIVE"`, so a FAILED file spun until the 20-minute
    poll budget exhausted instead of being classified immediately.

    This failure occurs AFTER the interaction reached "completed" status (the
    file-processing poll only starts once a completed interaction points at a
    uri-delivered video) — the provider has already billed, so on_billed must
    still fire even though this path returns None."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)
    on_billed = MagicMock()

    failed_file = MagicMock()
    failed_file.state = "FAILED"
    api.client.files.get.return_value = failed_file

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    # Pre-fix, a FAILED file state was indistinguishable from "still
    # processing" and the loop would poll real time.sleep(10) up to the
    # 20-minute budget — patch it out so this test stays fast regardless of
    # which side of the fix is under test.
    with patch("gemini_omni_native.time.sleep", return_value=None):
        result = api.generate_video(
            image_path=str(image_path), prompt="hello", output_path=output_path,
            on_billed=on_billed,
        )

    assert result is None
    api.client.files.download.assert_not_called()
    assert not os.path.exists(output_path)
    # Post-billing retrieval failure: on_billed must still fire exactly once
    # (money-gate class) — this would FAIL if on_billed were moved to after
    # the (never-reached, on this path) download step.
    on_billed.assert_called_once()
    # The discriminating assertion: pre-fix, FAILED was indistinguishable from
    # "still processing" so the loop kept polling files.get() up to
    # max_polls+1 times before giving up via TimeoutError. Fixed code
    # recognizes FAILED on the very first poll and returns immediately.
    assert api.client.files.get.call_count == 1, (
        f"Expected exactly one files.get() poll before classifying FAILED as "
        f"terminal; got {api.client.files.get.call_count} (a pre-fix "
        f"regression would poll up to 121 times waiting for ACTIVE)"
    )


def test_generate_video_returns_none_when_active_file_has_no_download_uri(tmp_path):
    """An ACTIVE file with no download_uri (e.g. an uploaded, non-generated
    file) must be classified explicitly rather than raising out of
    files.download() into the generic blanket-exception path.

    Like the FAILED-file-state case, this is reached only after the
    interaction itself reached "completed" status, so the provider has
    already billed — on_billed must still fire even though this path
    returns None."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)
    on_billed = MagicMock()

    active_file = MagicMock()
    active_file.state = "ACTIVE"
    active_file.download_uri = None
    api.client.files.get.return_value = active_file

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
        on_billed=on_billed,
    )

    assert result is None
    api.client.files.download.assert_not_called()
    assert not os.path.exists(output_path)
    # Post-billing retrieval failure: on_billed must still fire exactly once
    # (money-gate class) — this would FAIL if on_billed were moved to after
    # the (never-reached, on this path) download step.
    on_billed.assert_called_once()


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
# generate_video — completed interaction with empty video content
# ---------------------------------------------------------------------------


def test_generate_video_returns_none_on_empty_output_video(tmp_path, capsys):
    """A completed interaction whose output_video is None (no video content
    step at all — the empty-output terminal case) must be classified
    explicitly. Pre-fix, `video.data` on a None `video` raised an unhandled
    AttributeError caught only by the outer blanket except, indistinguishable
    from any other crash. on_billed must still fire — the interaction
    reached "completed", so it is billed regardless of empty content."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    on_billed = MagicMock()

    interaction = MagicMock()
    interaction.status = "completed"
    interaction.id = "interaction-123"
    interaction.output_video = None
    api.client.interactions.create.return_value = interaction

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
        on_billed=on_billed,
    )

    assert result is None
    assert not os.path.exists(output_path)
    on_billed.assert_called_once()
    # The discriminating assertion: both the pre-fix crash (an unhandled
    # AttributeError caught by the blanket except) and the fixed explicit
    # check return None here, so the return value alone doesn't separate
    # them. The explicit, intentional classification message does.
    out = capsys.readouterr().out
    assert "empty output" in out, (
        f"Expected an explicit empty-output classification message; got: {out!r}"
    )
    assert "AttributeError" not in out and "NoneType" not in out, (
        f"Must not fall through to the generic blanket-exception path; got: {out!r}"
    )


# ---------------------------------------------------------------------------
# generate_video — atomic publication (partial downloads must not leave a
# consumable output file)
# ---------------------------------------------------------------------------


def test_atomic_publication_leaves_no_file_on_replace_failure(tmp_path):
    """A mid-publish failure (simulated via os.replace raising after the temp
    file is fully written) must not leave output_path OR a leftover temp
    file. Pre-fix, the write went straight to `open(output_path, "wb")` with
    no temp/rename step at all, so this scenario couldn't even be expressed —
    a partial write from any mid-stream failure landed directly at
    output_path."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    with patch("gemini_omni_native.os.replace", side_effect=OSError("simulated rename failure")):
        result = api.generate_video(
            image_path=str(image_path), prompt="hello", output_path=output_path,
        )

    assert result is None
    assert not os.path.exists(output_path)
    leftover = [p.name for p in tmp_path.iterdir() if p.name != "frame.jpg"]
    assert leftover == [], f"partial/temp files leaked: {leftover}"


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


# ---------------------------------------------------------------------------
# generate_video — on_billed fires exactly when the interaction reaches
# "completed" status (money-gate 2026-07-11 class, extended to
# gemini_omni_native in slice M2: a post-billing video-retrieval failure must
# still be distinguishable from a pre-billing failure to the caller). Mirrors
# kling_native.py's on_billed tests (commit 55c0797e).
# ---------------------------------------------------------------------------


def test_pre_billing_failure_does_not_call_on_billed(tmp_path):
    """A non-completed terminal status => the provider never delivered a
    video => never billed => on_billed must NOT fire."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    on_billed = MagicMock()

    interaction = MagicMock()
    interaction.status = "failed"
    api.client.interactions.create.return_value = interaction

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=str(tmp_path / "out.mp4"),
        on_billed=on_billed,
    )

    assert result is None
    on_billed.assert_not_called()


def test_post_billing_retrieval_failure_still_notes_billed(tmp_path):
    """RED->GREEN target: a Files API retrieval failure AFTER the interaction
    reached "completed" status must still fire on_billed. Pre-fix, the
    files.download failure fell into the blanket `except Exception: return
    None`, indistinguishable from a pre-billing failure and losing the spend
    to the caller's budget gate. on_billed must fire BEFORE the retrieval
    attempt, not after."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=False)

    call_order: list[str] = []
    on_billed = MagicMock(side_effect=lambda: call_order.append("billed"))

    active_file = MagicMock()
    active_file.state = "ACTIVE"
    api.client.files.get.return_value = active_file

    def _failing_download(*args, **kwargs):
        call_order.append("download")
        raise RuntimeError("simulated post-billing retrieval failure")

    api.client.files.download.side_effect = _failing_download

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=str(tmp_path / "out.mp4"),
        on_billed=on_billed,
    )

    assert result is None
    on_billed.assert_called_once()
    assert call_order == ["billed", "download"], (
        "on_billed must fire BEFORE the retrieval attempt so a caller's spend "
        f"record is never lost to a post-billing failure; got {call_order!r}"
    )


def test_success_fires_on_billed_exactly_once(tmp_path):
    """The happy path also bills — on_billed must fire exactly once, before
    video retrieval, even when retrieval subsequently succeeds."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)
    on_billed = MagicMock()

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
        on_billed=on_billed,
    )

    assert result == output_path
    on_billed.assert_called_once()


def test_on_billed_exception_does_not_abort_success(tmp_path):
    """A broken accounting callback must never abort an otherwise-successful
    generation — the callback's own exception must be swallowed and logged,
    not allowed to propagate into the outer except and blank out a real
    video."""
    api = GeminiOmniAPI.__new__(GeminiOmniAPI)
    api._model = "gemini-omni-flash-preview"
    api.client = MagicMock()
    api.client.interactions.create.return_value = _completed_interaction(with_inline_data=True)

    def _bad_callback():
        raise RuntimeError("accounting hook bug")

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"fake-jpeg")
    output_path = str(tmp_path / "out.mp4")

    result = api.generate_video(
        image_path=str(image_path), prompt="hello", output_path=output_path,
        on_billed=_bad_callback,
    )

    assert result == output_path, (
        "A broken on_billed callback must not abort an otherwise-successful generation"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

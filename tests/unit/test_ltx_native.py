# tests/unit/test_ltx_native.py
"""Characterization tests for ltx_native.LTXVideoAPI (offline, mocked fal/urllib).
Locks in CORRECT behaviour after Part-3 moderate/minor fixes.

NOTE: _native_transition / _download_native_result / _native_request are
deliberately-kept DORMANT quality levers (not on the live generate_video path).
They are NOT tested here.
"""
from __future__ import annotations

import sys

# Other test files (test_dialogue_routing, test_ensure_shot_audio, test_f1b_dialogue_lipsync)
# inject a lightweight stub module for 'ltx_native' via sys.modules to satisfy
# import-time deps without the full SDK. When that stub is already in sys.modules
# at collection time, `from ltx_native import LTXVideoAPI` would fail with
# "cannot import name 'LTXVideoAPI' from 'ltx_native' (unknown location)".
# Remove the stub so our import always gets the real module.
sys.modules.pop("ltx_native", None)

import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch, call

import pytest

import ltx_native
from ltx_native import LTXVideoAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings(ltx_key: str = "", fal_key: str = "") -> MagicMock:
    """Return a mock settings object with only the fields LTXVideoAPI reads."""
    s = MagicMock()
    s.ltx_api_key = ltx_key
    s.fal_key = fal_key
    return s


def _make_api(ltx_key: str = "", fal_key: str = "", mode: str | None = None) -> LTXVideoAPI:
    """Construct an LTXVideoAPI whose __init__ reads from a patched settings.

    settings is a frozen dataclass singleton — patch 'ltx_native.settings'
    (module-level name) with a MagicMock.

    Optionally override mode/keys directly on the returned instance
    (since __init__ never raises, the instance is always valid to construct).
    """
    with patch("ltx_native.settings", _fake_settings(ltx_key=ltx_key, fal_key=fal_key)):
        api = LTXVideoAPI()
    if mode is not None:
        api.mode = mode
    return api


def _urlopen_cm(video_bytes: bytes = b"VIDEOBYTES") -> MagicMock:
    """Return a MagicMock that can be used as a context manager for urlopen.
    Its __enter__ returns an object whose .read() returns video_bytes.
    """
    resp = MagicMock()
    resp.read.return_value = video_bytes
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# __init__ — never raises; mode derivation
# ---------------------------------------------------------------------------

def test_init_no_keys_mode_is_none():
    """With no LTX key and no FAL key, mode=None (no error)."""
    api = _make_api()
    assert api.mode is None


def test_init_ltx_key_sets_native_mode():
    api = _make_api(ltx_key="ltx-real-key")
    assert api.mode == "native"


def test_init_fal_key_only_sets_fal_mode(monkeypatch):
    """With no LTX key but a FAL key, mode='fal' (when FAL_AVAILABLE)."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key-xxx")
    assert api.mode == "fal"


def test_init_ltx_key_takes_precedence_over_fal(monkeypatch):
    """LTX native key takes priority over FAL even when both are set."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    assert api.mode == "native"


# ---------------------------------------------------------------------------
# generate_video — mode None → None
# ---------------------------------------------------------------------------

def test_no_key_returns_none(tmp_path):
    api = _make_api()
    result = api.generate_video(
        image_path=str(tmp_path / "frame.jpg"),
        prompt="a scene",
        output_path=str(tmp_path / "out.mp4"),
    )
    assert result is None


# ---------------------------------------------------------------------------
# G(ltx)3: resolution "720p" maps to 1080p (1920x1080) via RESOLUTION_MAP
# DOCUMENTED-INTENTIONAL: LTX has no true 720p; "720p" upgraded to 1080p
# (capability-positive); zero live 720p callers.
# ---------------------------------------------------------------------------

def test_resolution_720p_maps_to_1080p_in_fal(monkeypatch, tmp_path):
    """G(ltx)3: '720p' key in RESOLUTION_MAP maps to width=1920, height=1080.
    DOCUMENTED-INTENTIONAL: LTX has no true 720p; "720p" upgraded to 1080p
    (capability-positive); zero live 720p callers.
    """
    assert LTXVideoAPI.RESOLUTION_MAP["720p"] == {"width": 1920, "height": 1080}


def test_resolution_720p_forwarded_as_1080p_to_fal_subscribe(monkeypatch, tmp_path):
    """When generate_video is called with resolution='720p' in fal mode, the
    subscribe arguments carry width=1920, height=1080, not 1280x720.
    DOCUMENTED-INTENTIONAL: LTX has no true 720p; capability-positive upgrade.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    subscribe_mock = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, path: None)

    api.generate_video(
        image_path=str(img),
        prompt="test",
        output_path=out,
        resolution="720p",
    )

    args = subscribe_mock.call_args
    subscribe_arguments = args.kwargs.get("arguments") or (args.args[1] if len(args.args) > 1 else {})
    # width/height are 1920x1080 for "720p" input (intentional upgrade, see G(ltx)3)
    assert subscribe_arguments["width"] == 1920
    assert subscribe_arguments["height"] == 1080


# ---------------------------------------------------------------------------
# FAL mode — happy path
# ---------------------------------------------------------------------------

def test_fal_happy_path_writes_output(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    subscribe_mock = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)

    written = {}
    def fake_urlretrieve(url, dest):
        written["url"] = url
        written["dest"] = dest
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", fake_urlretrieve)

    result = api.generate_video(image_path=str(img), prompt="scene", output_path=out)

    assert result == out
    assert written["url"] == "http://cdn/v.mp4"
    assert written["dest"] == out


# ---------------------------------------------------------------------------
# FAL mode — no video URL in response → None
# ---------------------------------------------------------------------------

def test_fal_no_video_url_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    # Response has no "url" under "video"
    subscribe_mock = MagicMock(return_value={"video": {}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)
    assert result is None


# ---------------------------------------------------------------------------
# FAL mode — camera_motion valid → included in subscribe args
# ---------------------------------------------------------------------------

def test_fal_valid_camera_motion_included(monkeypatch, tmp_path):
    """A recognised camera_motion string is forwarded to fal_client.subscribe."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    subscribe_mock = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    api.generate_video(
        image_path=str(img),
        prompt="test",
        output_path=out,
        camera_motion="dolly_in",
    )

    args = subscribe_mock.call_args
    subscribe_arguments = args.kwargs.get("arguments") or (args.args[1] if len(args.args) > 1 else {})
    assert subscribe_arguments.get("camera_motion") == "dolly_in"


# ---------------------------------------------------------------------------
# FAL mode — camera_motion invalid → excluded from subscribe args
# ---------------------------------------------------------------------------

def test_fal_invalid_camera_motion_excluded(monkeypatch, tmp_path):
    """An unrecognised camera_motion string is silently dropped."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    subscribe_mock = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    api.generate_video(
        image_path=str(img),
        prompt="test",
        output_path=out,
        camera_motion="hover_rotate",   # not in CAMERA_MOTIONS
    )

    args = subscribe_mock.call_args
    subscribe_arguments = args.kwargs.get("arguments") or (args.args[1] if len(args.args) > 1 else {})
    assert "camera_motion" not in subscribe_arguments


# ---------------------------------------------------------------------------
# FAL mode — exception → None
# ---------------------------------------------------------------------------

def test_fal_exception_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(
        ltx_native.fal_client, "upload_file", MagicMock(side_effect=RuntimeError("network"))
    )

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)
    assert result is None


# ---------------------------------------------------------------------------
# Native mode — happy path (urlopen CM → bytes → path)
# ---------------------------------------------------------------------------

def test_native_happy_path_writes_output(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    # Native path: fal_client.upload_file is called to get a hosted image URL.
    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    cm = _urlopen_cm(b"NATIVE_VIDEO_BYTES")
    monkeypatch.setattr(ltx_native.urllib.request, "urlopen", MagicMock(return_value=cm))

    result = api.generate_video(image_path=str(img), prompt="cinematic", output_path=out)

    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"NATIVE_VIDEO_BYTES"


def test_native_empty_200_body_is_not_false_success(monkeypatch, tmp_path):
    """A 200 response with an EMPTY body must NOT be written as a 0-byte file and
    reported as success.

    Regression (Pair-B lane-health baseline): _native_generate read the body and
    wrote it unconditionally, so an empty 200 produced a 0-byte file and returned
    output_path — a false success the caller accepts as a real clip. With no
    fal_key the guard must route to None (failure → the caller cascades), and no
    0-byte file may be left behind.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key")          # fal_key="" -> no FAL fallback on failure
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out_path = tmp_path / "out.mp4"
    out = str(out_path)

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    cm = _urlopen_cm(b"")                        # empty 200 body
    monkeypatch.setattr(ltx_native.urllib.request, "urlopen", MagicMock(return_value=cm))

    result = api.generate_video(image_path=str(img), prompt="cinematic", output_path=out)

    assert result is None, f"empty 200 body was reported as success: result={result!r}"
    assert not out_path.exists(), "a 0-byte output file was written for an empty 200 body"


def test_native_empty_200_body_falls_back_to_fal(monkeypatch, tmp_path):
    """When fal_key is configured, an empty 200 body must route to the FAL
    fallback (via the broad except) rather than be accepted as a 0-byte success.

    This exercises the OTHER branch of the empty-body guard's except-chain: the
    RuntimeError raised on an empty body is caught by `except Exception`, which
    retries via FAL when fal_key + FAL_AVAILABLE.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out_path = tmp_path / "out.mp4"
    out = str(out_path)

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")
    cm = _urlopen_cm(b"")                        # empty 200 body
    monkeypatch.setattr(ltx_native.urllib.request, "urlopen", MagicMock(return_value=cm))

    fal_spy = MagicMock(return_value=out)        # stand in for the FAL recovery path
    monkeypatch.setattr(api, "_fal_generate", fal_spy)

    result = api.generate_video(image_path=str(img), prompt="cinematic", output_path=out)

    fal_spy.assert_called_once()
    assert result == out, "empty 200 body did not recover via the FAL fallback"


# ---------------------------------------------------------------------------
# G(ltx)1 FIXED: native HTTP 5xx → triggers FAL fallback (transient server error)
# ---------------------------------------------------------------------------

def test_http_5xx_falls_back_to_fal(monkeypatch, tmp_path):
    """A 5xx HTTPError from the native API triggers the FAL fallback when
    fal_key is set and FAL_AVAILABLE — transient server errors should be retried
    via FAL, not silently dropped.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    http_error = urllib.request.HTTPError(
        url="http://api.ltx.video/v1/image-to-video",
        code=503,
        msg="Service Unavailable",
        hdrs=MagicMock(),
        fp=BytesIO(b'{"error":"overloaded"}'),
    )
    monkeypatch.setattr(
        ltx_native.urllib.request, "urlopen", MagicMock(side_effect=http_error)
    )

    subscribe_spy = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_spy)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # 5xx HTTPError DOES trigger FAL fallback
    assert result == out
    subscribe_spy.assert_called_once()


def test_http_4xx_does_not_fallback_to_fal(monkeypatch, tmp_path):
    """A 4xx HTTPError (client error / bad auth) does NOT trigger FAL fallback —
    it is not a transient error; retrying via FAL would not help.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    http_error = urllib.request.HTTPError(
        url="http://api.ltx.video/v1/image-to-video",
        code=422,
        msg="Unprocessable Entity",
        hdrs=MagicMock(),
        fp=BytesIO(b'{"error":"bad payload"}'),
    )
    monkeypatch.setattr(
        ltx_native.urllib.request, "urlopen", MagicMock(side_effect=http_error)
    )

    subscribe_spy = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_spy)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # 4xx HTTPError does NOT trigger FAL fallback — returns None
    assert result is None
    subscribe_spy.assert_not_called()


# ---------------------------------------------------------------------------
# CRITICAL FIX: transient network errors (URLError / TimeoutError) → FAL fallback
# ---------------------------------------------------------------------------


def test_native_urlerror_falls_back_to_fal(monkeypatch, tmp_path):
    """A urllib.request.URLError from urlopen (e.g., DNS failure, connection refused)
    is a TRANSIENT NETWORK error and MUST trigger the FAL fallback — exactly like a
    5xx HTTPError. Before the fix this returned None (OSError clause caught it).
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    # urllib.request.URLError is raised by urlopen on DNS / connection failures
    url_error = urllib.request.URLError(reason="Name or service not known")
    monkeypatch.setattr(
        ltx_native.urllib.request, "urlopen", MagicMock(side_effect=url_error)
    )

    subscribe_spy = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_spy)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # URLError (transient network) MUST trigger FAL fallback, not return None
    assert result == out
    subscribe_spy.assert_called_once()


def test_native_timeout_falls_back_to_fal(monkeypatch, tmp_path):
    """A TimeoutError from urlopen (600s timeout elapsed) is a TRANSIENT NETWORK
    error and MUST trigger the FAL fallback. Before the fix this returned None.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    # TimeoutError is an OSError subclass raised on socket timeout
    monkeypatch.setattr(
        ltx_native.urllib.request,
        "urlopen",
        MagicMock(side_effect=TimeoutError("timed out after 600s")),
    )

    subscribe_spy = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_spy)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # TimeoutError (transient network) MUST trigger FAL fallback, not return None
    assert result == out
    subscribe_spy.assert_called_once()


def test_native_urlerror_no_fal_key_returns_none(monkeypatch, tmp_path):
    """With no fal_key configured, a URLError returns None (no fallback possible)."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key")  # no fal_key
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    url_error = urllib.request.URLError(reason="Connection refused")
    monkeypatch.setattr(
        ltx_native.urllib.request, "urlopen", MagicMock(side_effect=url_error)
    )

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)
    assert result is None


# ---------------------------------------------------------------------------
# G(ltx)1 FIXED: native local file-I/O OSError → does NOT fall back to FAL
# ---------------------------------------------------------------------------


def test_local_oserror_does_not_fallback_to_fal(monkeypatch, tmp_path):
    """A local file-I/O OSError (disk full, permission denied) from the file-WRITE
    path does NOT trigger the FAL fallback — a disk/permission error cannot be
    fixed by retrying via FAL.  The OSError is raised from open(output_path, 'wb')
    AFTER urlopen succeeds, so it genuinely tests the file-I/O no-fallback path.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    # urlopen succeeds and returns video bytes; OSError happens at file-write time
    urlopen_cm = _urlopen_cm(b"VIDEOBYTES")
    monkeypatch.setattr(
        ltx_native.urllib.request,
        "urlopen",
        MagicMock(return_value=urlopen_cm),
    )

    subscribe_spy = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_spy)

    # Patch builtins.open so the file-write raises OSError (disk-full simulation)
    import builtins
    original_open = builtins.open

    def _open_raises_on_write(path, mode="r", *args, **kwargs):
        if mode == "wb" and str(path) == out:
            raise OSError("no space left on device")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open_raises_on_write)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # Local file-I/O OSError does NOT trigger FAL fallback — returns None
    assert result is None
    subscribe_spy.assert_not_called()


# ---------------------------------------------------------------------------
# G(ltx)1: native generic unknown Exception → FAL fallback still fires
# ---------------------------------------------------------------------------

def test_native_generic_exception_triggers_fal_fallback(monkeypatch, tmp_path):
    """A generic non-HTTP, non-OS exception (e.g. a library bug) from within
    _native_generate falls into the generic 'except Exception' clause
    which DOES trigger the FAL fallback when fal_key and FAL_AVAILABLE.
    """
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    # A RuntimeError from some library (not HTTPError, not OSError).
    monkeypatch.setattr(
        ltx_native.urllib.request,
        "urlopen",
        MagicMock(side_effect=RuntimeError("unexpected library error")),
    )

    subscribe_mock = MagicMock(return_value={"video": {"url": "http://cdn/v.mp4"}})
    monkeypatch.setattr(ltx_native.fal_client, "subscribe", subscribe_mock)
    monkeypatch.setattr(ltx_native.urllib.request, "urlretrieve", lambda url, dest: None)

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)

    # Generic exception DOES trigger FAL fallback
    assert result == out
    subscribe_mock.assert_called_once()


# ---------------------------------------------------------------------------
# native 5xx HTTPError + no fal_key → None (no fallback possible)
# ---------------------------------------------------------------------------

def test_native_http_5xx_no_fal_key_returns_none(monkeypatch, tmp_path):
    """With no fal_key configured, a 5xx HTTPError returns None
    (5xx would qualify for fallback, but there's no FAL key to use)."""
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key")  # no fal_key
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"imgdata")
    out = str(tmp_path / "out.mp4")

    monkeypatch.setattr(ltx_native.fal_client, "upload_file", lambda path: "http://cdn/img.jpg")

    http_error = urllib.request.HTTPError(
        url="http://api.ltx.video/v1/image-to-video",
        code=503,
        msg="Service Unavailable",
        hdrs=MagicMock(),
        fp=BytesIO(b""),
    )
    monkeypatch.setattr(
        ltx_native.urllib.request, "urlopen", MagicMock(side_effect=http_error)
    )

    result = api.generate_video(image_path=str(img), prompt="test", output_path=out)
    assert result is None

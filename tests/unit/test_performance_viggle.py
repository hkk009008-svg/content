"""Tests for performance/viggle.py — the Viggle official-API repair.

Offline only: `requests` is always monkeypatched and `performance._net.safe_download`
never touches a real network. No live spend.

Contract under test (confirmed via WebFetch to https://docs.viggle.ai — see
performance/viggle.py's module docstring, and domain/provider_catalog.py's
VIGGLE entry for the full before/after mismatch table this repairs):
  - POST https://apis.viggle.ai/v1/renders
      files={"image": ..., "motion_video": ...}, data={"background_mode": ...}
      (NOT the pre-official api.viggle.ai/v1/motion-transfer,
      files={"character_image", "motion_video"}, data={"background": ...})
  - background_mode must be one of original|solid|transparent (NOT the
      pre-official white|green|transparent); bg_color is only sent alongside
      background_mode="solid"
  - GET https://apis.viggle.ai/v1/renders/{id} (NOT .../v1/jobs/{job_id})
  - terminal states are ready|failed|cancelled (NOT complete/done/succeeded/
      failed/error); success payload carries video_url
  - HTTP failures are classified (auth 401/403, rate-limit 429, other
      non-2xx, timeout, connection error, generic request exception) rather
      than funneled through one silent catch-all
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import requests

import performance.viggle as viggle


# ---------------------------------------------------------------------------
# Shared fixtures / fakes
# ---------------------------------------------------------------------------

class _FakeCostTracker:
    """Captures log_api() calls without touching sqlite."""
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def log_api(self, **kwargs):
        self.calls.append(kwargs)


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_body: Optional[dict] = None,
                 text: str = "", ok: Optional[bool] = None, raise_json: bool = False):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.text = text
        self.ok = ok if ok is not None else (200 <= status_code < 300)
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._json_body


def _ok_safe_download(monkeypatch, *, write_bytes=b"fake-mp4-bytes"):
    def _fake(url, dest_path, **kwargs):
        with open(dest_path, "wb") as f:
            f.write(write_bytes)
        return dest_path
    monkeypatch.setattr(viggle, "safe_download", _fake)


def _make_files(tmp_path):
    kf = tmp_path / "keyframe.jpg"
    kf.write_bytes(b"fake-jpeg")
    driving = tmp_path / "driving.mp4"
    driving.write_bytes(b"fake-mp4")
    out = tmp_path / "out.mp4"
    return str(kf), str(driving), str(out)


def _install_post_get(monkeypatch, *, post_response, get_responses=None, capture=None):
    """Monkeypatch requests.post / requests.get.

    post_response: a _FakeResponse (or callable returning one / raising) for the
        creation POST.
    get_responses: a list of _FakeResponse consumed in order by successive polls
        (last one repeats once exhausted). Defaults to a single READY response.
    capture: optional dict that records the last post/get call kwargs for
        contract assertions.
    """
    get_responses = list(get_responses) if get_responses is not None else [
        _FakeResponse(200, {"status": "ready", "video_url": "https://cdn.example.test/out.mp4"})
    ]

    def _fake_post(url, headers=None, files=None, data=None, timeout=None):
        if capture is not None:
            capture["post_url"] = url
            capture["post_headers"] = headers
            capture["post_files"] = files
            capture["post_data"] = data
            capture["post_timeout"] = timeout
        if callable(post_response):
            return post_response()
        return post_response

    def _fake_get(url, headers=None, timeout=None):
        if capture is not None:
            capture.setdefault("get_urls", []).append(url)
            capture["get_headers"] = headers
        if len(get_responses) > 1:
            return get_responses.pop(0)
        return get_responses[0]

    monkeypatch.setattr(requests, "post", _fake_post)
    monkeypatch.setattr(requests, "get", _fake_get)


@pytest.fixture(autouse=True)
def _has_api_key(monkeypatch):
    # config.settings.Settings is a frozen dataclass — swap the module-level
    # `settings` name viggle.py reads, rather than mutating the instance.
    monkeypatch.setattr(viggle, "settings", SimpleNamespace(viggle_api_key="test-viggle-key"))
    monkeypatch.delenv("VIGGLE_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch):
    # Don't actually sleep between polls in tests.
    monkeypatch.setattr(viggle, "_POLL_INTERVAL_S", 0)


# ---------------------------------------------------------------------------
# Preconditions — no network involved at all
# ---------------------------------------------------------------------------

class TestPreconditions:
    def test_missing_api_key_returns_none(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(viggle, "settings", SimpleNamespace(viggle_api_key=""))
        monkeypatch.delenv("VIGGLE_API_KEY", raising=False)
        kf, driving, out = _make_files(tmp_path)

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "VIGGLE_API_KEY" in capsys.readouterr().out

    def test_missing_keyframe_returns_none_with_message(self, tmp_path, capsys):
        _, driving, out = _make_files(tmp_path)
        result = viggle.generate_viggle_performance(str(tmp_path / "nope.jpg"), driving, out)

        assert result is None
        assert "keyframe" in capsys.readouterr().out.lower()

    def test_missing_driving_video_returns_none_with_message(self, tmp_path, capsys):
        kf, _, out = _make_files(tmp_path)
        result = viggle.generate_viggle_performance(kf, str(tmp_path / "missing.mp4"), out)

        assert result is None
        assert "driving video" in capsys.readouterr().out.lower()

    def test_invalid_background_mode_returns_none_with_message(self, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        # "white"/"green" were the pre-official adapter's (wrong) values.
        result = viggle.generate_viggle_performance(kf, driving, out, background_mode="white")

        assert result is None
        message = capsys.readouterr().out.lower()
        assert "background_mode" in message
        assert "white" in message


# ---------------------------------------------------------------------------
# Request contract — official apis.viggle.ai/v1/renders shape
# ---------------------------------------------------------------------------

class TestRequestContract:
    def test_success_sends_official_endpoint_fields_and_auth(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        capture: dict = {}
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            capture=capture,
        )
        _ok_safe_download(monkeypatch)

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result == out
        assert os.path.exists(out)
        assert capture["post_url"] == "https://apis.viggle.ai/v1/renders"
        assert capture["post_headers"] == {"Authorization": "Bearer test-viggle-key"}
        files = capture["post_files"]
        assert set(files) == {"image", "motion_video"}
        assert capture["post_data"] == {"background_mode": "original"}
        # Poll hits the official /v1/renders/{id} shape, not /v1/jobs/{job_id}.
        assert capture["get_urls"] == ["https://apis.viggle.ai/v1/renders/render_123"]
        assert capture["get_headers"] == {"Authorization": "Bearer test-viggle-key"}

    def test_solid_background_sends_bg_color(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        capture: dict = {}
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            capture=capture,
        )
        _ok_safe_download(monkeypatch)

        viggle.generate_viggle_performance(
            kf, driving, out, background_mode="solid", bg_color="255,0,0",
        )

        assert capture["post_data"] == {"background_mode": "solid", "bg_color": "255,0,0"}

    def test_transparent_background_never_sends_bg_color(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        capture: dict = {}
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            capture=capture,
        )
        _ok_safe_download(monkeypatch)

        viggle.generate_viggle_performance(
            kf, driving, out, background_mode="transparent", bg_color="255,0,0",
        )

        assert capture["post_data"] == {"background_mode": "transparent"}
        assert "bg_color" not in capture["post_data"]

    def test_cost_log_tags_viggle_motion_retarget(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
        )
        _ok_safe_download(monkeypatch)
        tracker = _FakeCostTracker()

        viggle.generate_viggle_performance(kf, driving, out, cost_tracker=tracker)

        assert len(tracker.calls) == 1
        call = tracker.calls[0]
        assert call["provider"] == "viggle"
        assert call["model"] == "motion_retarget"
        assert call["operation"] == "performance_capture"
        assert call["cost_usd"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# HTTP failure classification on the creation POST
# ---------------------------------------------------------------------------

class TestCreationFailureClassification:
    def test_401_is_classified_as_auth(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(monkeypatch, post_response=_FakeResponse(401, text="bad key"))

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "auth" in capsys.readouterr().out.lower()

    def test_403_is_classified_as_auth(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(monkeypatch, post_response=_FakeResponse(403, text="forbidden"))

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "auth" in capsys.readouterr().out.lower()

    def test_429_is_classified_as_rate_limit(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(monkeypatch, post_response=_FakeResponse(429, text="slow down"))

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "rate" in capsys.readouterr().out.lower()

    def test_500_reports_status_code(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(monkeypatch, post_response=_FakeResponse(500, text="oops"))

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "500" in capsys.readouterr().out

    def test_non_json_creation_response_returns_none(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(200, raise_json=True),
        )

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "json" in capsys.readouterr().out.lower()

    def test_missing_id_in_creation_response_returns_none(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(200, {"status": "queued"}),  # no "id"
        )

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "id" in capsys.readouterr().out.lower()

    def test_timeout_is_classified(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)

        def _raise_timeout(*a, **k):
            raise requests.exceptions.Timeout("connect timed out")
        monkeypatch.setattr(requests, "post", _raise_timeout)

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "timed out" in capsys.readouterr().out.lower()

    def test_connection_error_is_classified(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)

        def _raise_conn(*a, **k):
            raise requests.exceptions.ConnectionError("no route to host")
        monkeypatch.setattr(requests, "post", _raise_conn)

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "connection" in capsys.readouterr().out.lower()

    def test_generic_request_exception_is_classified_by_type_name(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)

        def _raise_generic(*a, **k):
            raise requests.exceptions.RequestException("weird")
        monkeypatch.setattr(requests, "post", _raise_generic)

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "RequestException" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Polling / terminal-state handling
# ---------------------------------------------------------------------------

class TestPolling:
    def test_terminal_failed_status_returns_none(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            get_responses=[_FakeResponse(200, {"status": "failed"})],
        )

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert not os.path.exists(out)

    def test_terminal_cancelled_status_returns_none(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            get_responses=[_FakeResponse(200, {"status": "cancelled"})],
        )

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None

    def test_ready_without_video_url_returns_none(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            get_responses=[_FakeResponse(200, {"status": "ready"})],  # no video_url
        )

        result = viggle.generate_viggle_performance(kf, driving, out)

        assert result is None
        assert "video_url" in capsys.readouterr().out

    def test_transient_poll_failure_is_tolerated_then_succeeds(self, monkeypatch, tmp_path):
        """A single not-ok poll response must not abort the loop — it's
        treated as a transient PENDING, matching poll_task's contract."""
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            get_responses=[
                _FakeResponse(503, ok=False),
                _FakeResponse(200, {"status": "ready", "video_url": "https://cdn.example.test/out.mp4"}),
            ],
        )
        _ok_safe_download(monkeypatch)

        result = viggle.generate_viggle_performance(kf, driving, out, poll_timeout_s=5)

        assert result == out

    def test_poll_timeout_returns_none(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
            get_responses=[_FakeResponse(200, {"status": "queued"})],  # never terminates
        )

        result = viggle.generate_viggle_performance(kf, driving, out, poll_timeout_s=0)

        assert result is None

    def test_download_failure_returns_none_and_does_not_log_cost(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_post_get(
            monkeypatch,
            post_response=_FakeResponse(202, {"status": "queued", "id": "render_123"}),
        )
        monkeypatch.setattr(viggle, "safe_download", lambda *a, **k: None)
        tracker = _FakeCostTracker()

        result = viggle.generate_viggle_performance(kf, driving, out, cost_tracker=tracker)

        assert result is None
        assert tracker.calls == []

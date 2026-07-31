"""Tests for performance/act_two.py — the Runway Act-Two migration (slice 5b).

Offline only: the runwayml SDK client and `requests` are always monkeypatched,
`performance._net.safe_download` never touches a real network. No live spend.

Contract under test (audited against the installed runwayml SDK v4.14.0 —
see performance/act_two.py's module docstring):
  - model must be "act_two" (never the retired "act_one")
  - reference must be {"type": "video", "uri": ...} — no audio-reference mode
  - the outgoing request carries NO "duration" field (SDK has none)
  - SDK errors are classified (auth / bad-request / rate-limit / connection /
    generic status / unexpected) and NEVER trigger a REST retry — only a
    missing runwayml package (ImportError) falls through to REST, and REST
    sends the identical act_two contract.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import Any, Optional

import httpx
import pytest

import performance.act_two as act_two


# ---------------------------------------------------------------------------
# Shared fixtures / fakes
# ---------------------------------------------------------------------------

class _FakeCostTracker:
    """Captures log_api() calls without touching sqlite."""
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def log_api(self, **kwargs):
        self.calls.append(kwargs)


class _FakeTask:
    def __init__(self, id="task_123"):
        self.id = id


class _FakeRetrievedTask:
    def __init__(self, status: str, output: Optional[list] = None, failure: Optional[str] = None):
        self.status = status
        self.output = output
        self.failure = failure


class _FakeCharacterPerformance:
    """Records the exact kwargs passed to .create(), for contract assertions."""
    def __init__(self, create_result=None, create_error: Optional[BaseException] = None):
        self.received_kwargs: Optional[dict] = None
        self._create_result = create_result or _FakeTask()
        self._create_error = create_error

    def create(self, **kwargs):
        self.received_kwargs = kwargs
        if self._create_error is not None:
            raise self._create_error
        return self._create_result


class _FakeTasks:
    def __init__(self, statuses: list[_FakeRetrievedTask]):
        self._statuses = list(statuses)

    def retrieve(self, id):  # noqa: A002 - matches SDK signature
        # Return the next queued status; repeat the last one if exhausted.
        if len(self._statuses) > 1:
            return self._statuses.pop(0)
        return self._statuses[0]


class _FakeRunwayML:
    """Stands in for runwayml.RunwayML(api_key=...)."""
    def __init__(self, character_performance: _FakeCharacterPerformance, statuses: list[_FakeRetrievedTask]):
        self.character_performance = character_performance
        self.tasks = _FakeTasks(statuses)

    def __call__(self, api_key: str):  # the class itself is monkeypatched in, so calling it == constructing
        self.api_key = api_key
        return self


def _install_fake_runwayml(monkeypatch, *, create_error=None, statuses=None, create_result=None):
    """Monkeypatch runwayml.RunwayML so `from runwayml import RunwayML` in
    act_two.py resolves to our fake. Returns the fake character_performance
    object so tests can inspect received_kwargs."""
    cp = _FakeCharacterPerformance(create_result=create_result, create_error=create_error)
    statuses = statuses if statuses is not None else [_FakeRetrievedTask("SUCCEEDED", output=["https://cdn.example.test/out.mp4"])]

    class _Ctor:
        def __call__(self, api_key: str):
            return _FakeRunwayML(cp, statuses)

    import runwayml
    monkeypatch.setattr(runwayml, "RunwayML", _Ctor())
    return cp


def _ok_safe_download(monkeypatch, *, write_bytes=b"fake-mp4-bytes"):
    def _fake(url, dest_path, **kwargs):
        with open(dest_path, "wb") as f:
            f.write(write_bytes)
        return dest_path
    monkeypatch.setattr(act_two, "safe_download", _fake)


def _make_files(tmp_path):
    kf = tmp_path / "keyframe.jpg"
    kf.write_bytes(b"fake-jpeg")
    driving = tmp_path / "driving.mp4"
    driving.write_bytes(b"fake-mp4")
    out = tmp_path / "out.mp4"
    return str(kf), str(driving), str(out)


@pytest.fixture(autouse=True)
def _has_api_key(monkeypatch):
    # config.settings.Settings is a frozen dataclass — swap the module-level
    # `settings` name act_two.py reads, rather than mutating the instance.
    monkeypatch.setattr(act_two, "settings", SimpleNamespace(runwayml_api_secret="test-secret-key"))


def _status_error(cls, status_code: int, message: str = "boom"):
    request = httpx.Request("POST", "https://api.dev.runwayml.com/v1/character_performance")
    response = httpx.Response(status_code, request=request)
    return cls(message, response=response, body=None)


# ---------------------------------------------------------------------------
# Preconditions — no network involved at all
# ---------------------------------------------------------------------------

class TestPreconditions:
    def test_missing_api_key_returns_none(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(act_two, "settings", SimpleNamespace(runwayml_api_secret=""))
        monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
        kf, driving, out = _make_files(tmp_path)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "RUNWAYML_API_SECRET" in capsys.readouterr().out

    def test_missing_keyframe_returns_none(self, tmp_path):
        _, driving, out = _make_files(tmp_path)
        result = act_two.generate_act_two_performance(
            str(tmp_path / "nope.jpg"), "", out, driving_video_path=driving,
        )
        assert result is None

    def test_missing_driving_video_returns_none_with_explanatory_message(self, tmp_path, capsys):
        """The load-bearing behavior change: Act-Two has no audio-only mode,
        so an audio-only call (the old Act-One usage pattern) must fail
        loudly, not attempt a malformed request."""
        kf, _, out = _make_files(tmp_path)

        result = act_two.generate_act_two_performance(
            kf, str(tmp_path / "dialogue.wav"), out, driving_video_path=None,
        )

        assert result is None
        message = capsys.readouterr().out
        assert "reference" in message.lower() or "driving" in message.lower()
        assert "act-two" in message.lower() or "ACT-TWO" in message

    def test_nonexistent_driving_video_path_returns_none(self, tmp_path):
        kf, _, out = _make_files(tmp_path)
        result = act_two.generate_act_two_performance(
            kf, "", out, driving_video_path=str(tmp_path / "missing.mp4"),
        )
        assert result is None


# ---------------------------------------------------------------------------
# SDK-shaped request contract
# ---------------------------------------------------------------------------

class TestSdkRequestContract:
    def test_success_sends_act_two_model_video_reference_no_duration(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        cp = _install_fake_runwayml(monkeypatch)
        _ok_safe_download(monkeypatch)
        tracker = _FakeCostTracker()

        result = act_two.generate_act_two_performance(
            kf, "", out, driving_video_path=driving, duration_s=4.0, cost_tracker=tracker,
        )

        assert result == out
        assert os.path.exists(out)
        sent = cp.received_kwargs
        assert sent is not None
        assert sent["model"] == "act_two"
        assert "duration" not in sent, "Act-Two's create() has no duration parameter — it must not be sent"
        assert sent["character"] == {"type": "image", "uri": kf}
        assert sent["reference"] == {"type": "video", "uri": driving}

    def test_cost_log_tags_model_act_two(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_fake_runwayml(monkeypatch)
        _ok_safe_download(monkeypatch)
        tracker = _FakeCostTracker()

        act_two.generate_act_two_performance(
            kf, "", out, driving_video_path=driving, duration_s=5.0, cost_tracker=tracker,
        )

        assert len(tracker.calls) == 1
        assert tracker.calls[0]["model"] == "act_two"
        assert tracker.calls[0]["provider"] == "runway"
        assert tracker.calls[0]["cost_usd"] == pytest.approx(0.25)  # 0.05 * 5.0s

    def test_terminal_failed_status_returns_none(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_fake_runwayml(monkeypatch, statuses=[_FakeRetrievedTask("FAILED", failure="rejected")])

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert not os.path.exists(out)

    def test_succeeded_with_empty_output_returns_none(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_fake_runwayml(monkeypatch, statuses=[_FakeRetrievedTask("SUCCEEDED", output=[])])

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None

    def test_download_failure_returns_none_and_does_not_log_cost(self, monkeypatch, tmp_path):
        kf, driving, out = _make_files(tmp_path)
        _install_fake_runwayml(monkeypatch)
        monkeypatch.setattr(act_two, "safe_download", lambda *a, **k: None)
        tracker = _FakeCostTracker()

        result = act_two.generate_act_two_performance(
            kf, "", out, driving_video_path=driving, cost_tracker=tracker,
        )

        assert result is None
        assert tracker.calls == []


# ---------------------------------------------------------------------------
# SDK error classification — "no silent conceal", no REST retry
# ---------------------------------------------------------------------------

class TestSdkErrorClassification:
    def _assert_no_rest_fallback(self, monkeypatch):
        """REST fallback must NOT fire for a post-import SDK error — install a
        tripwire that fails the test if requests.post is ever called."""
        def _tripwire(*a, **k):
            raise AssertionError("REST fallback must not be attempted after a classified SDK error")
        monkeypatch.setattr("requests.post", _tripwire)

    def test_authentication_error_returns_none_no_rest(self, monkeypatch, tmp_path, capsys):
        import runwayml
        kf, driving, out = _make_files(tmp_path)
        err = _status_error(runwayml.AuthenticationError, 401, "bad key")
        _install_fake_runwayml(monkeypatch, create_error=err)
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "auth" in capsys.readouterr().out.lower()

    def test_bad_request_error_returns_none(self, monkeypatch, tmp_path, capsys):
        import runwayml
        kf, driving, out = _make_files(tmp_path)
        err = _status_error(runwayml.BadRequestError, 400, "bad params")
        _install_fake_runwayml(monkeypatch, create_error=err)
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "reject" in capsys.readouterr().out.lower()

    def test_rate_limit_error_returns_none(self, monkeypatch, tmp_path, capsys):
        import runwayml
        kf, driving, out = _make_files(tmp_path)
        err = _status_error(runwayml.RateLimitError, 429, "slow down")
        _install_fake_runwayml(monkeypatch, create_error=err)
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "rate" in capsys.readouterr().out.lower()

    def test_connection_error_returns_none(self, monkeypatch, tmp_path, capsys):
        import runwayml
        kf, driving, out = _make_files(tmp_path)
        request = httpx.Request("POST", "https://api.dev.runwayml.com/v1/character_performance")
        err = runwayml.APIConnectionError(request=request)
        _install_fake_runwayml(monkeypatch, create_error=err)
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "connection" in capsys.readouterr().out.lower()

    def test_generic_api_status_error_logs_status_code(self, monkeypatch, tmp_path, capsys):
        import runwayml
        kf, driving, out = _make_files(tmp_path)
        err = _status_error(runwayml.InternalServerError, 500, "oops")
        _install_fake_runwayml(monkeypatch, create_error=err)
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "500" in capsys.readouterr().out

    def test_unexpected_exception_is_classified_by_type_name(self, monkeypatch, tmp_path, capsys):
        kf, driving, out = _make_files(tmp_path)
        _install_fake_runwayml(monkeypatch, create_error=ValueError("weird"))
        self._assert_no_rest_fallback(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None
        assert "ValueError" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# REST fallback — only on ImportError (SDK package missing), same contract
# ---------------------------------------------------------------------------

class TestRestFallback:
    def _force_sdk_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "runwayml", None)

    def test_rest_used_when_sdk_missing_sends_same_contract(self, monkeypatch, tmp_path):
        self._force_sdk_import_error(monkeypatch)
        kf, driving, out = _make_files(tmp_path)

        posted = {}

        class _FakePostResponse:
            status_code = 200
            def json(self):
                return {"id": "task_rest_1"}

        class _FakeGetResponse:
            ok = True
            def json(self):
                return {"status": "SUCCEEDED", "output": ["https://cdn.example.test/rest_out.mp4"]}

        def _fake_post(url, json, headers, timeout):
            posted["url"] = url
            posted["json"] = json
            posted["headers"] = headers
            return _FakePostResponse()

        def _fake_get(url, headers, timeout):
            return _FakeGetResponse()

        monkeypatch.setattr("requests.post", _fake_post)
        monkeypatch.setattr("requests.get", _fake_get)
        _ok_safe_download(monkeypatch)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving, duration_s=3.0)

        assert result == out
        assert posted["url"] == "https://api.dev.runwayml.com/v1/character_performance"
        body = posted["json"]
        assert body["model"] == "act_two"
        assert "duration" not in body
        assert body["reference"]["type"] == "video"
        assert body["character"]["type"] == "image"

    def test_rest_http_error_status_returns_none(self, monkeypatch, tmp_path):
        self._force_sdk_import_error(monkeypatch)
        kf, driving, out = _make_files(tmp_path)

        class _FakeErrorResponse:
            status_code = 400
            text = "bad request"

        monkeypatch.setattr("requests.post", lambda *a, **k: _FakeErrorResponse())

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=driving)

        assert result is None

    def test_rest_also_requires_driving_video(self, monkeypatch, tmp_path, capsys):
        """The precondition check happens before either transport — REST
        never gets a chance to attempt an audio-only request either."""
        self._force_sdk_import_error(monkeypatch)
        kf, _, out = _make_files(tmp_path)

        def _tripwire(*a, **k):
            raise AssertionError("REST must not be reached without a driving video")
        monkeypatch.setattr("requests.post", _tripwire)

        result = act_two.generate_act_two_performance(kf, "", out, driving_video_path=None)

        assert result is None


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def test_to_data_uri_or_path_is_a_passthrough():
    assert act_two._to_data_uri_or_path("/tmp/whatever.jpg") == "/tmp/whatever.jpg"

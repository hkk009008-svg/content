"""Unit tests for the sunoapi.org-backed Suno BGM path (audio/music.py).

These mock the two HTTP calls (POST /api/v1/generate, GET .../record-info) and the
download, pinning the sunoapi.org contract parsing — taskId extraction, the status
set (PENDING/TEXT_SUCCESS/FIRST_SUCCESS → keep polling; SUCCESS → done; *_FAILED →
abort), and data.response.sunoData[].audioUrl — WITHOUT a live, credit-spending
call. Real end-to-end still requires one live sunoapi.org generate call.

Offline — no network, no credits.
"""

from __future__ import annotations

import audio.music as music


class _FakeResp:
    def __init__(self, payload=None, ok=True, content=b""):
        self._payload = payload
        self.ok = ok
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSettings:
    suno_api_key = "test-key"
    suno_api_base = "https://api.sunoapi.org"


def _patch_env(monkeypatch, settings_obj=None):
    # generate_suno_v5 does `from config.settings import settings` at call time.
    # The `config` package re-exports the singleton as `config.settings` (shadowing
    # the submodule on attribute access), so patch the SUBMODULE's `settings`
    # attribute directly via importlib rather than a dotted-string target.
    import importlib
    _cfg = importlib.import_module("config.settings")
    monkeypatch.setattr(_cfg, "settings", settings_obj or _FakeSettings())
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    # Regression guard: the audioUrl download must go through requests.get (with a
    # browser User-Agent), NOT urllib.urlretrieve — the default Python-urllib UA
    # 403s sunoapi.org's CDN. If the code regresses to urlretrieve, fail loudly.
    def _forbidden_urlretrieve(*a, **k):
        raise AssertionError("download must use requests.get, not urllib.urlretrieve")
    monkeypatch.setattr("urllib.request.urlretrieve", _forbidden_urlretrieve)


def test_suno_happy_path(monkeypatch, tmp_path):
    _patch_env(monkeypatch)
    calls = {}

    def _post(url, json=None, headers=None, timeout=None):
        calls.update(post_url=url, payload=json, headers=headers)
        return _FakeResp({"code": 200, "msg": "success", "data": {"taskId": "task-123"}})

    def _get(url, params=None, headers=None, timeout=None):
        if "record-info" in url:
            calls.update(get_url=url, params=params)
            return _FakeResp({"data": {"status": "SUCCESS",
                                       "response": {"sunoData": [{"audioUrl": "https://cdn/x.mp3"}]}}})
        # audio asset download (the CDN URL parsed out of sunoData)
        calls.update(download_url=url, download_headers=headers)
        return _FakeResp(content=b"ID3-FAKE-MP3")

    monkeypatch.setattr("requests.post", _post)
    monkeypatch.setattr("requests.get", _get)

    out = str(tmp_path / "bgm.mp3")
    assert music.generate_suno_v5("epic", out, instrumental=True) is True
    # endpoint + payload shape
    assert calls["post_url"] == "https://api.sunoapi.org/api/v1/generate"
    assert calls["payload"]["model"] == music._SUNO_MODEL
    assert calls["payload"]["customMode"] is True
    assert calls["payload"]["instrumental"] is True
    assert calls["payload"]["callBackUrl"]  # required schema field present
    assert calls["headers"]["Authorization"] == "Bearer test-key"
    # polling endpoint + taskId
    assert calls["get_url"] == "https://api.sunoapi.org/api/v1/generate/record-info"
    assert calls["params"] == {"taskId": "task-123"}
    # download: parsed audioUrl fetched via requests with a browser UA, file written
    assert calls["download_url"] == "https://cdn/x.mp3"
    assert "Mozilla" in calls["download_headers"]["User-Agent"]
    from pathlib import Path
    assert Path(out).read_bytes() == b"ID3-FAKE-MP3"


def test_suno_polls_through_in_progress_then_success(monkeypatch, tmp_path):
    _patch_env(monkeypatch)
    monkeypatch.setattr("requests.post",
                        lambda *a, **k: _FakeResp({"code": 200, "data": {"taskId": "t"}}))
    poll_seq = iter([
        _FakeResp({"data": {"status": "PENDING"}}),
        _FakeResp({"data": {"status": "FIRST_SUCCESS"}}),
        _FakeResp({"data": {"status": "SUCCESS",
                            "response": {"sunoData": [{"audioUrl": "https://cdn/y.mp3"}]}}}),
    ])
    captured = {}

    def _get(url, params=None, headers=None, timeout=None):
        if "record-info" in url:
            return next(poll_seq)
        captured["download_url"] = url
        return _FakeResp(content=b"MP3")

    monkeypatch.setattr("requests.get", _get)
    out = str(tmp_path / "b.mp3")
    assert music.generate_suno_v5("calm", out) is True
    assert captured["download_url"] == "https://cdn/y.mp3"
    from pathlib import Path
    assert Path(out).read_bytes() == b"MP3"


def test_suno_failure_status_returns_false(monkeypatch, tmp_path):
    _patch_env(monkeypatch)
    monkeypatch.setattr("requests.post",
                        lambda *a, **k: _FakeResp({"code": 200, "data": {"taskId": "t"}}))
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _FakeResp({"data": {"status": "GENERATE_AUDIO_FAILED"}}))
    assert music.generate_suno_v5("epic", str(tmp_path / "b.mp3")) is False


def test_suno_rejected_code_returns_false(monkeypatch, tmp_path):
    _patch_env(monkeypatch)
    monkeypatch.setattr("requests.post",
                        lambda *a, **k: _FakeResp({"code": 429, "msg": "rate limited"}))
    assert music.generate_suno_v5("epic", str(tmp_path / "b.mp3")) is False


def test_suno_no_key_skips(monkeypatch, tmp_path):
    class _NoKey:
        suno_api_key = ""
        suno_api_base = "https://api.sunoapi.org"
    _patch_env(monkeypatch, _NoKey())
    assert music.generate_suno_v5("epic", str(tmp_path / "b.mp3")) is False

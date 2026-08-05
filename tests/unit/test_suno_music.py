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
    def __init__(self, payload=None, ok=True, content=b"", status_code=200):
        self._payload = payload
        self.ok = ok
        self.content = content
        self.status_code = status_code

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

    # Regression guard: the audioUrl download must go through safe_download with
    # a browser User-Agent, NOT urllib.urlretrieve — the default Python-urllib UA
    # 403s sunoapi.org's CDN.
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
        raise AssertionError(f"unexpected requests.get URL: {url}")

    def _download(url, destination, **kwargs):
        calls.update(download_url=url, download_headers=kwargs["request_headers"])
        from pathlib import Path
        Path(destination).write_bytes(b"ID3-FAKE-MP3")
        return destination

    monkeypatch.setattr("requests.post", _post)
    monkeypatch.setattr("requests.get", _get)
    monkeypatch.setattr(music, "safe_download", _download)

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
        raise AssertionError(f"unexpected requests.get URL: {url}")

    def _download(url, destination, **_kwargs):
        captured["download_url"] = url
        from pathlib import Path
        Path(destination).write_bytes(b"MP3")
        return destination

    monkeypatch.setattr("requests.get", _get)
    monkeypatch.setattr(music, "safe_download", _download)
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


def test_suno_rejects_invalid_download(monkeypatch, tmp_path):
    _patch_env(monkeypatch)
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _FakeResp({"code": 200, "data": {"taskId": "t"}}),
    )
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: _FakeResp(
            {
                "data": {
                    "status": "SUCCESS",
                    "response": {"sunoData": [{"audioUrl": "https://cdn/bad"}]},
                }
            }
        ),
    )
    monkeypatch.setattr(music, "safe_download", lambda *a, **k: None)

    output = tmp_path / "bad.mp3"
    assert music.generate_suno_v5("epic", str(output)) is False
    assert not output.exists()


def test_suno_restart_resumes_task_id_and_never_reposts(monkeypatch, tmp_path):
    from cost_tracker import CostTracker

    _patch_env(monkeypatch)
    output = str(tmp_path / "durable.mp3")
    db = str(tmp_path / "suno.db")
    post_calls = []
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: post_calls.append((a, k))
        or _FakeResp({"code": 200, "data": {"taskId": "durable-task"}}),
    )

    first = CostTracker(db_path=db, budget_usd=2.0)
    recovery = {}
    try:
        assert music.generate_suno_v5(
            "epic",
            output,
            poll_timeout_s=0,
            cost_tracker=first,
            _recovery_out=recovery,
            video_id="project-suno",
        ) is False
        assert recovery["paid_deferred"] is True
        pending = first.get_latest_paid_attempt(
            video_id="project-suno",
            shot_id="",
            engine="SUNO_V5",
            operation="bgm",
        )
        assert pending["provider_job_id"] == "durable-task"
        assert pending["state"] == "accepted_unknown"
    finally:
        first.close()

    monkeypatch.setattr(
        "requests.post",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("restart must poll durable taskId, not POST")
        ),
    )
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: _FakeResp(
            {
                "data": {
                    "status": "SUCCESS",
                    "response": {"sunoData": [{"audioUrl": "https://cdn/resume.mp3"}]},
                }
            }
        ),
    )

    def _download(_url, destination, **_kwargs):
        from pathlib import Path
        Path(destination).write_bytes(b"ID3-resumed")
        return destination

    monkeypatch.setattr(music, "safe_download", _download)
    resumed = CostTracker(db_path=db, budget_usd=2.0)
    try:
        assert music.generate_suno_v5(
            "epic",
            output,
            poll_timeout_s=1,
            cost_tracker=resumed,
            video_id="project-suno",
        ) is True
        assert len(post_calls) == 1
        settled = resumed.get_latest_paid_attempt(
            video_id="project-suno",
            shot_id="",
            engine="SUNO_V5",
            operation="bgm",
        )
        assert settled["state"] == "succeeded"
        assert resumed.get_video_cost("project-suno")["total_usd"] == 0.5
    finally:
        resumed.close()


# --- generate_bgm router threads cost_tracker + AUTO-degrades (capacity audit wf_6be2ee18-f4b) ---

def test_bgm_router_passes_cost_tracker_to_suno(monkeypatch, tmp_path):
    captured = {}

    def fake_suno(vibe, out, duration=60, custom_lyrics="", cost_tracker=None, **k):
        captured["ct"] = cost_tracker
        return True

    monkeypatch.setattr(music, "generate_suno_v5", fake_suno)
    monkeypatch.setattr(music, "generate_fal_bgm", lambda *a, **k: True)
    sentinel = object()
    assert music.generate_bgm("epic", str(tmp_path / "o.mp3"), cost_tracker=sentinel) is True
    assert captured["ct"] is sentinel


def test_bgm_router_passes_cost_tracker_to_fal_fallback(monkeypatch, tmp_path):
    captured = {}

    def fake_fal(vibe, out, duration=42, cost_tracker=None, **k):
        captured["ct"] = cost_tracker
        return True

    monkeypatch.setattr(music, "generate_suno_v5", lambda *a, **k: False)
    monkeypatch.setattr(music, "generate_fal_bgm", fake_fal)
    sentinel = object()
    assert music.generate_bgm("epic", str(tmp_path / "o.mp3"), cost_tracker=sentinel) is True
    assert captured["ct"] is sentinel


def test_bgm_router_no_key_degrades_to_fal(monkeypatch, tmp_path):
    monkeypatch.setattr(music, "generate_suno_v5", lambda *a, **k: False)
    monkeypatch.setattr(music, "generate_fal_bgm", lambda *a, **k: True)
    assert music.generate_bgm("epic", str(tmp_path / "o.mp3"), cost_tracker=object()) is True

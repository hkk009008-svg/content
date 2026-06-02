# tests/unit/test_hedra_native.py
"""Characterization tests for hedra_native.HedraAPI (offline, mocked HTTP).
Validate the existing module's success + every graceful-failure branch."""
import hedra_native
from hedra_native import HedraAPI


class _Resp:
    """Minimal fake requests.Response."""
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _api(key="sk_test_xxx"):
    """Build a HedraAPI with an injected key. `settings` is a FROZEN dataclass
    (config/settings.py: @dataclass(frozen=True)) so it cannot be monkeypatched;
    HedraAPI reads settings.hedra_api_key into self._key at construction, so we
    override the instance attribute instead."""
    api = HedraAPI()
    api._key = key
    api._headers = {"x-api-key": key}
    return api


def _files(tmp_path):
    img = tmp_path / "i.jpg"; img.write_bytes(b"img")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"aud")
    out = tmp_path / "o.mp4"
    return str(img), str(aud), str(out)


def test_empty_key_returns_none(tmp_path):
    img, aud, out = _files(tmp_path)
    assert _api(key="").generate_talking_head(img, aud, out) is None


def test_missing_image_returns_none(tmp_path):
    _, aud, out = _files(tmp_path)
    assert _api().generate_talking_head(str(tmp_path / "nope.jpg"), aud, out) is None


def test_missing_audio_returns_none(tmp_path):
    img, _, out = _files(tmp_path)
    assert _api().generate_talking_head(img, str(tmp_path / "nope.mp3"), out) is None


def test_happy_path_writes_output(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}),   # POST /assets (image)
        _Resp(),                                 # POST /assets/{id}/upload (image)
        _Resp(json_data={"id": "aud-asset"}),    # POST /assets (audio)
        _Resp(),                                 # POST /assets/{id}/upload (audio)
        _Resp(json_data={"id": "gen-1"}),        # POST /generations
    ])
    gets = iter([
        _Resp(json_data={"status": "complete", "download_url": "http://x/v.mp4"}),  # /status
        _Resp(content=b"VIDEOBYTES"),            # download GET
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get", lambda *a, **k: next(gets))
    res = _api().generate_talking_head(img, aud, out)
    assert res == out
    with open(out, "rb") as f:
        assert f.read() == b"VIDEOBYTES"


def test_generation_rejected_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(status_code=400),                  # POST /generations rejected
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    assert _api().generate_talking_head(img, aud, out) is None


def test_status_error_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(json_data={"id": "gen-1"}),
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get",
                        lambda *a, **k: _Resp(json_data={"status": "error", "error_message": "boom"}))
    assert _api().generate_talking_head(img, aud, out) is None


def test_timeout_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(json_data={"id": "gen-1"}),
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get",
                        lambda *a, **k: _Resp(json_data={"status": "processing"}))  # never completes
    assert _api().generate_talking_head(img, aud, out) is None

"""Performance adapters must use the authenticated, bounded ComfyUI client."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import performance.driving_video as driving_video
import performance.live_portrait as live_portrait


class _FakeComfy:
    instances = []

    def __init__(self, server_url, *, auth_token):
        self.server_url = server_url
        self.auth_token = auth_token
        self.uploads = []
        self.workflow = None
        self.wait_args = None
        type(self).instances.append(self)

    def upload_image(self, path):
        self.uploads.append(path)
        return f"remote-{Path(path).name}"

    def queue_prompt(self, workflow):
        self.workflow = workflow
        return "prompt-1"

    def wait_for_completion(self, prompt_id, *, timeout, poll_interval):
        self.wait_args = (prompt_id, timeout, poll_interval)
        return {
            prompt_id: {
                "outputs": {
                    "30": {
                        "videos": [{
                            "filename": "render.mp4",
                            "subfolder": "safe folder",
                            "type": "output",
                        }]
                    }
                }
            }
        }


def _settings():
    return SimpleNamespace(
        comfyui_server_url="http://private-pod:8189",
        comfyui_api_key="x" * 32,
    )


def test_live_portrait_uses_gateway_auth_and_forwards_it_to_download(
    tmp_path, monkeypatch
):
    _FakeComfy.instances.clear()
    keyframe = tmp_path / "frame.png"
    driving = tmp_path / "driving.mp4"
    output = tmp_path / "result.mp4"
    keyframe.write_bytes(b"frame")
    driving.write_bytes(b"video")
    downloads = []

    monkeypatch.setattr(live_portrait, "settings", _settings())
    monkeypatch.setattr(live_portrait, "RunPodComfyUI", _FakeComfy)
    monkeypatch.setattr(
        live_portrait,
        "safe_download",
        lambda url, destination, **kwargs: downloads.append((url, destination, kwargs)) or destination,
    )
    monkeypatch.setattr(live_portrait, "_cost_log", lambda *_args, **_kwargs: None)

    result = live_portrait.generate_live_portrait_performance(
        str(keyframe),
        str(driving),
        str(output),
        poll_timeout_s=45,
    )

    assert result == str(output)
    client = _FakeComfy.instances[0]
    assert client.server_url == "http://private-pod:8189"
    assert client.auth_token == "x" * 32
    assert client.uploads == [str(keyframe), str(driving)]
    assert client.wait_args == ("prompt-1", 45.0, 2.0)
    assert client.workflow["20"]["class_type"] == "LivePortraitProcess"
    assert downloads[0][2]["request_headers"] == {
        "Authorization": f"Bearer {'x' * 32}"
    }
    assert "safe+folder" in downloads[0][0]


def test_sadtalker_uses_gateway_auth_and_shared_job_control(tmp_path, monkeypatch):
    _FakeComfy.instances.clear()
    keyframe = tmp_path / "frame.png"
    audio = tmp_path / "voice.wav"
    output = tmp_path / "result.mp4"
    keyframe.write_bytes(b"frame")
    audio.write_bytes(b"audio")
    downloads = []

    monkeypatch.setattr(driving_video, "settings", _settings())
    monkeypatch.setattr(driving_video, "RunPodComfyUI", _FakeComfy)
    monkeypatch.setattr(
        driving_video,
        "safe_download",
        lambda url, destination, **kwargs: downloads.append((url, destination, kwargs)) or destination,
    )
    monkeypatch.setattr(driving_video, "_cost_log", lambda *_args, **_kwargs: None)

    result = driving_video._synth_via_sadtalker(
        str(audio),
        str(keyframe),
        str(output),
        5.0,
        "shot-1",
        "project-1",
    )

    assert result == str(output)
    client = _FakeComfy.instances[0]
    assert client.auth_token == "x" * 32
    assert client.uploads == [str(keyframe), str(audio)]
    assert client.workflow["20"]["class_type"] == "SadTalker"
    assert client.wait_args == ("prompt-1", 240.0, 2.0)
    assert downloads[0][2]["request_headers"] == {
        "Authorization": f"Bearer {'x' * 32}"
    }


def test_client_preflight_failure_is_terminal_without_raw_requests(
    tmp_path, monkeypatch
):
    class _RejectingComfy(_FakeComfy):
        def queue_prompt(self, workflow):
            raise RuntimeError("required node is unavailable")

    keyframe = tmp_path / "frame.png"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"frame")
    driving.write_bytes(b"video")
    download = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("download must not run")
    )

    monkeypatch.setattr(live_portrait, "settings", _settings())
    monkeypatch.setattr(live_portrait, "RunPodComfyUI", _RejectingComfy)
    monkeypatch.setattr(live_portrait, "safe_download", download)

    assert live_portrait.generate_live_portrait_performance(
        str(keyframe), str(driving), str(tmp_path / "out.mp4")
    ) is None

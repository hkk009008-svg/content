"""Performance adapters must use the authenticated, bounded ComfyUI client."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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

    def get_gateway_readiness(self):
        return {"status": "ready"}

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
        comfyui_server_url="http://private-worker:8189",
        comfyui_api_key="x" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="p" * 32,
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
    monkeypatch.setattr(live_portrait, "ComfyUIClient", _FakeComfy)
    monkeypatch.setattr(
        live_portrait,
        "validate_performance_gateway_readiness",
        lambda payload: payload,
    )
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
    assert client.server_url == "http://127.0.0.1:18189"
    assert client.auth_token == "p" * 32
    assert client.uploads == [str(keyframe), str(driving)]
    assert client.wait_args == ("prompt-1", 45.0, 2.0)
    assert {node["class_type"] for node in client.workflow.values()} == {
        "LoadImage",
        "VHS_LoadVideo",
        "DownloadAndLoadLivePortraitModels",
        "LivePortraitLoadMediaPipeCropper",
        "LivePortraitCropper",
        "LivePortraitRetargeting",
        "LivePortraitProcess",
        "LivePortraitComposite",
        "VHS_VideoCombine",
    }
    assert client.workflow["11"]["inputs"]["frame_load_cap"] == 125
    assert client.workflow["11"]["inputs"]["custom_width"] == 512
    assert client.workflow["11"]["inputs"]["custom_height"] == 0
    assert client.workflow["17"]["inputs"]["crop_info"] == ["14", 1]
    assert client.workflow["17"]["inputs"]["driving_images"] == ["11", 0]
    assert client.workflow["17"]["inputs"]["opt_retargeting_info"] == ["16", 0]
    assert client.workflow["18"]["inputs"]["liveportrait_out"] == ["17", 1]
    assert client.workflow["19"]["inputs"]["images"] == ["18", 0]
    assert downloads[0][2]["request_headers"] == {
        "Authorization": f"Bearer {'p' * 32}"
    }
    assert "safe+folder" in downloads[0][0]


def test_shared_liveportrait_route_requires_capability_proof_before_upload(
    tmp_path, monkeypatch
):
    marker = {"schema_version": 1, "status": "partial", "capabilities": {}}
    validated = []

    class _SharedComfy(_FakeComfy):
        def get_gateway_readiness(self):
            raise AssertionError("public legacy readiness cannot admit shared endpoint")

        def get_gateway_capabilities_readiness(self):
            return marker

    _SharedComfy.instances.clear()
    keyframe = tmp_path / "frame.png"
    driving = tmp_path / "driving.mp4"
    output = tmp_path / "result.mp4"
    keyframe.write_bytes(b"frame")
    driving.write_bytes(b"video")

    shared_settings = SimpleNamespace(
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    )
    monkeypatch.setattr(live_portrait, "settings", shared_settings)
    monkeypatch.setattr(live_portrait, "ComfyUIClient", _SharedComfy)
    monkeypatch.setattr(
        live_portrait,
        "performance_capability_from_unified",
        lambda payload: validated.append(payload) or payload,
    )
    monkeypatch.setattr(
        live_portrait,
        "validate_performance_gateway_readiness",
        lambda _payload: (_ for _ in ()).throw(
            AssertionError("legacy validator cannot admit shared endpoint")
        ),
    )
    monkeypatch.setattr(
        live_portrait,
        "safe_download",
        lambda _url, destination, **_kwargs: destination,
    )
    monkeypatch.setattr(live_portrait, "_cost_log", lambda *_args, **_kwargs: None)

    assert live_portrait.generate_live_portrait_performance(
        str(keyframe), str(driving), str(output), poll_timeout_s=45
    ) == str(output)
    assert validated == [marker]
    assert _SharedComfy.instances[0].uploads == [str(keyframe), str(driving)]


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
    monkeypatch.setattr(live_portrait, "ComfyUIClient", _RejectingComfy)
    monkeypatch.setattr(
        live_portrait,
        "validate_performance_gateway_readiness",
        lambda payload: payload,
    )
    monkeypatch.setattr(live_portrait, "safe_download", download)

    assert live_portrait.generate_live_portrait_performance(
        str(keyframe), str(driving), str(tmp_path / "out.mp4")
    ) is None


def test_live_portrait_rejects_wrong_gateway_contract_before_upload(
    tmp_path, monkeypatch
):
    _FakeComfy.instances.clear()
    keyframe = tmp_path / "frame.png"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"frame")
    driving.write_bytes(b"video")

    monkeypatch.setattr(live_portrait, "settings", _settings())
    monkeypatch.setattr(live_portrait, "ComfyUIClient", _FakeComfy)
    monkeypatch.setattr(
        live_portrait,
        "safe_download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("download must not run")
        ),
    )

    assert live_portrait.generate_live_portrait_performance(
        str(keyframe), str(driving), str(tmp_path / "out.mp4")
    ) is None
    assert len(_FakeComfy.instances) == 1
    assert _FakeComfy.instances[0].uploads == []


def test_unsafe_performance_endpoint_never_constructs_client_or_uploads(
    tmp_path, monkeypatch
):
    _FakeComfy.instances.clear()
    keyframe = tmp_path / "frame.png"
    driving = tmp_path / "driving.mp4"
    keyframe.write_bytes(b"frame")
    driving.write_bytes(b"video")
    monkeypatch.setattr(
        live_portrait,
        "settings",
        SimpleNamespace(
            comfyui_server_url="https://image.example.test",
            comfyui_api_key="i" * 32,
            performance_comfyui_server_url="http://192.0.2.16:8189",
            performance_comfyui_api_key="p" * 32,
        ),
    )
    monkeypatch.setattr(live_portrait, "ComfyUIClient", _FakeComfy)

    assert live_portrait.generate_live_portrait_performance(
        str(keyframe), str(driving), str(tmp_path / "out.mp4")
    ) is None
    assert _FakeComfy.instances == []

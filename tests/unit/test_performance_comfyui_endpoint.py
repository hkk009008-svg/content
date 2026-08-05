from types import SimpleNamespace

import pytest

from performance.comfyui_endpoint import resolve_performance_comfyui


def test_dedicated_performance_endpoint_keeps_its_own_credentials():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url="https://image-worker.test",
            comfyui_api_key="image-secret",
            performance_comfyui_server_url="https://gpu-pc.example.test/",
            performance_comfyui_api_key="p" * 32,
        )
    )

    assert endpoint.server_url == "https://gpu-pc.example.test"
    assert endpoint.api_key == "p" * 32
    assert endpoint.dedicated is True
    assert endpoint.usable is True


def test_missing_dedicated_url_fails_closed_instead_of_aliasing_image_worker():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url="https://shared-worker.test/",
            comfyui_api_key="shared-secret",
            performance_comfyui_server_url=None,
            performance_comfyui_api_key="unused-secret",
        )
    )

    assert endpoint.server_url == ""
    assert endpoint.api_key == "unused-secret"
    assert endpoint.dedicated is True
    assert endpoint.usable is False


def test_dedicated_url_never_falls_back_to_image_worker_token():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url="https://image-worker.test",
            comfyui_api_key="must-not-leak",
            performance_comfyui_server_url="http://gpu-pc.local:8189",
            performance_comfyui_api_key="",
        )
    )

    assert endpoint.api_key == ""
    assert endpoint.dedicated is True
    assert endpoint.configuration_error == "invalid_token"
    assert endpoint.usable is False


def test_loopback_tunnel_requires_a_strong_dedicated_token():
    weak = resolve_performance_comfyui(
        SimpleNamespace(
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="short",
        )
    )
    assert weak.configuration_error == "invalid_token"
    assert weak.usable is False

    strong = resolve_performance_comfyui(
        SimpleNamespace(
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="t" * 32,
        )
    )
    assert strong.configuration_error == ""
    assert strong.usable is True


def test_plaintext_lan_endpoint_is_rejected_even_with_a_token():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            performance_comfyui_server_url="http://192.0.2.16:8189",
            performance_comfyui_api_key="t" * 32,
        )
    )
    assert endpoint.configuration_error == "insecure_transport"
    assert endpoint.usable is False


def test_shared_endpoint_with_different_credentials_fails_closed():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url="https://GPU.EXAMPLE.test:443/",
            comfyui_api_key="i" * 32,
            performance_comfyui_server_url="https://gpu.example.test",
            performance_comfyui_api_key="p" * 32,
        )
    )
    assert endpoint.dedicated is False
    assert endpoint.shared_endpoint is True
    assert endpoint.requires_capability_proof is True
    assert endpoint.configuration_error == "shared_credentials"
    assert endpoint.usable is False


def test_shared_endpoint_is_only_provisionally_usable_pending_runtime_proof():
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url="https://GPU.EXAMPLE.test:443/",
            comfyui_api_key="s" * 32,
            performance_comfyui_server_url="https://gpu.example.test",
            performance_comfyui_api_key="s" * 32,
        )
    )

    assert endpoint.dedicated is False
    assert endpoint.shared_endpoint is True
    assert endpoint.requires_capability_proof is True
    assert endpoint.configuration_error == ""
    assert endpoint.usable is True


@pytest.mark.parametrize("image_host", ["localhost", "127.0.0.1", "127.0.0.2", "[::1]"])
def test_loopback_aliases_cannot_disguise_a_shared_worker(image_host):
    endpoint = resolve_performance_comfyui(
        SimpleNamespace(
            comfyui_server_url=f"http://{image_host}:18189",
            comfyui_api_key="s" * 32,
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="s" * 32,
        )
    )

    assert endpoint.dedicated is False
    assert endpoint.shared_endpoint is True
    assert endpoint.requires_capability_proof is True
    assert endpoint.configuration_error == ""
    assert endpoint.usable is True

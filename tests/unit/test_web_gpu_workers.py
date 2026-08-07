"""Safe GPU worker status API contracts."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from flask import Flask
import pytest

from comfyui_client import ComfyUITransportError
from performance.worker_readiness import (
    expected_flux2_worker_contract,
    expected_performance_worker_contract,
)
import web_gpu_workers


class _FakeClient:
    gateway: object = {"status": "ready"}
    capabilities: object = {}
    stats: object = {
        "system": {"os": "nt"},
        "devices": [{
            "name": "NVIDIA GeForce RTX 5070 Ti",
            "vram_total": 16 * 1024**3,
            "vram_free": 12 * 1024**3,
        }],
    }
    object_info: dict[str, object] = {}
    queue: object = {"queue_running": [], "queue_pending": []}
    constructed: list[tuple[str, str]] = []
    timeouts: list[tuple[float | None, float | None]] = []

    def __init__(self, server_url, *, auth_token="", **_kwargs):
        self.constructed.append((server_url, auth_token))
        self.timeouts.append(
            (_kwargs.get("connect_timeout"), _kwargs.get("read_timeout"))
        )

    def get_gateway_readiness(self):
        if isinstance(self.gateway, Exception):
            raise self.gateway
        return self.gateway

    def get_gateway_capabilities_readiness(self):
        if isinstance(self.capabilities, Exception):
            raise self.capabilities
        return self.capabilities

    def get_system_stats(self):
        if isinstance(self.stats, Exception):
            raise self.stats
        return self.stats

    def get_object_info(self):
        return self.object_info

    def get_queue(self):
        return self.queue


def _settings(tmp_path: Path, **overrides):
    values = {
        "project_root": Path(__file__).resolve().parents[2],
        "comfyui_server_url": None,
        "comfyui_api_key": "",
        "performance_comfyui_server_url": None,
        "performance_comfyui_api_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _ready_gateway() -> dict[str, object]:
    return {
        "status": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "execution_canary_state": "passed",
        **expected_performance_worker_contract().gateway_fields(),
    }


def _flux2_state(state: str = "not_installed") -> dict[str, object]:
    payload: dict[str, object] = {
        **expected_flux2_worker_contract().gateway_fields(),
        "state": state,
        "startup_ready": False,
        "execution_proven": False,
        "benchmark_state": "not_run",
        "blocker_code": "candidate_artifacts_not_installed",
        "artifacts_installed": False,
        "runtime_contract_sha256": "",
        "license_review_state": "official_sources_selected_derivation_pending",
        "execution_canary_state": "not_run",
        "execution_canary_sha256": "",
        "benchmark_sha256": "",
    }
    if state == "needs_benchmark":
        payload.update(
            startup_ready=False,
            execution_proven=True,
            blocker_code="candidate_benchmark_not_run",
            artifacts_installed=True,
            runtime_contract_sha256="c" * 64,
            license_review_state="official_source_derivation_verified",
            execution_canary_state="passed",
            execution_canary_sha256="a" * 64,
        )
    elif state == "ready":
        payload.update(
            startup_ready=True,
            execution_proven=True,
            benchmark_state="passed",
            blocker_code="",
            artifacts_installed=True,
            runtime_contract_sha256="c" * 64,
            license_review_state="official_source_derivation_verified",
            execution_canary_state="passed",
            execution_canary_sha256="a" * 64,
            benchmark_sha256="b" * 64,
        )
    elif state == "blocked":
        payload.update(
            benchmark_state="failed",
            blocker_code="candidate_execution_failed",
            license_review_state="official_source_derivation_verified",
            execution_canary_state="failed",
        )
    return payload


def _unified_gateway(state: str = "not_installed") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ready" if state == "ready" else "partial",
        "capabilities": {
            "performance-liveportrait": _ready_gateway(),
            "image-flux2-klein": _flux2_state(state),
        },
    }


def _app(monkeypatch, settings_obj):
    app = Flask(__name__)
    app.register_blueprint(web_gpu_workers.gpu_workers_api)
    monkeypatch.setattr(web_gpu_workers, "settings", settings_obj)
    return app


def test_unconfigured_roles_do_not_attempt_network_or_leak_configuration(monkeypatch, tmp_path):
    _FakeClient.constructed = []
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(tmp_path))

    with app.test_client() as client:
        response = client.get("/api/runtime/gpu-workers")

    assert response.status_code == 200
    payload = response.get_json()
    assert [worker["state"] for worker in payload["workers"]] == [
        "not_installed", "unconfigured"
    ]
    assert _FakeClient.constructed == []
    assert "server_url" not in str(payload)
    assert "api_key" not in str(payload)


def test_legacy_dedicated_image_endpoint_is_blocked_before_network(monkeypatch, tmp_path):
    _FakeClient.constructed = []
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="https://image.example.test",
        comfyui_api_key="i" * 32,
    ))

    with app.test_client() as client:
        worker = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert worker["state"] == "blocked"
    assert worker["blocker_code"] == "shared_capability_contract_required"
    assert _FakeClient.constructed == []


def test_remote_worker_without_token_fails_before_network(monkeypatch, tmp_path):
    _FakeClient.constructed = []
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        performance_comfyui_server_url="http://gpu-pc.local:8189",
    ))

    with app.test_client() as client:
        worker = client.get("/api/runtime/gpu-workers").get_json()["workers"][1]

    assert worker["state"] == "unauthorized"
    assert _FakeClient.constructed == []


def test_guarded_ready_projects_safe_gpu_and_queue_data(monkeypatch, tmp_path):
    _FakeClient.constructed = []
    _FakeClient.gateway = _ready_gateway()
    _FakeClient.stats = {
        "system": {"os": "nt", "secret": "not-projected"},
        "devices": [{
            "name": "NVIDIA GeForce RTX 5070 Ti\x00",
            "vram_total": 16 * 1024**3,
            "vram_free": 12 * 1024**3,
        }],
    }
    _FakeClient.object_info = {name: {} for name in web_gpu_workers._PERFORMANCE_NODE_CLASSES}
    _FakeClient.queue = {"queue_running": [[0]], "queue_pending": [[1], [2]]}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="p" * 32,
    ))

    with app.test_client() as client:
        payload = client.get("/api/runtime/gpu-workers").get_json()

    worker = payload["workers"][1]
    assert worker == {
        "role": "performance",
        "label": "Performance worker (LivePortrait)",
        "configured": True,
        "dedicated": True,
        "state": "ready",
        "message": (
            "Technical readiness passed: the guarded startup, node, model-file, and "
            "execution contracts match. Commercial-use licensing remains a separate "
            "human review."
        ),
        "gpu_name": "NVIDIA GeForce RTX 5070 Ti",
        "vram_total_gib": 16.0,
        "vram_free_gib": 12.0,
        "running": 1,
        "pending": 2,
    }
    rendered = str(payload)
    assert "gpu-pc.local" not in rendered
    assert "performance-secret" not in rendered
    assert "not-projected" not in rendered
    assert _FakeClient.timeouts[-1] == (2.0, 2.0)


def test_shared_worker_projects_ready_liveportrait_and_not_installed_flux2(
    monkeypatch, tmp_path
):
    _FakeClient.constructed = []
    _FakeClient.gateway = AssertionError(
        "public legacy readiness cannot admit a shared endpoint"
    )
    _FakeClient.capabilities = _unified_gateway()
    _FakeClient.object_info = {
        name: {} for name in web_gpu_workers._PERFORMANCE_NODE_CLASSES
    }
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    ))

    with app.test_client() as client:
        workers = client.get("/api/runtime/gpu-workers").get_json()["workers"]

    assert workers[0]["state"] == "not_installed"
    assert workers[0]["dedicated"] is False
    assert workers[0]["blocker_code"] == "candidate_artifacts_not_installed"
    assert "not installed" in workers[0]["message"]
    assert workers[1]["state"] == "ready"
    assert workers[1]["dedicated"] is False
    assert len(_FakeClient.constructed) == 2


@pytest.mark.parametrize("state", ["needs_benchmark", "blocked", "ready"])
def test_shared_image_card_projects_exact_flux2_operator_state(
    monkeypatch, tmp_path, state
):
    _FakeClient.constructed = []
    _FakeClient.capabilities = _unified_gateway(state)
    _FakeClient.stats = {
        "system": {"os": "nt"},
        "devices": [{
            "name": "NVIDIA GeForce RTX 5070 Ti",
            "vram_total": 16 * 1024**3,
            "vram_free": 12 * 1024**3,
        }],
    }
    _FakeClient.object_info = {
        name: {}
        for name in (
            web_gpu_workers._PERFORMANCE_NODE_CLASSES
            | web_gpu_workers.flux2_required_node_classes()
        )
    }
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    ))

    with app.test_client() as client:
        image = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert image["state"] == state
    assert image["label"] == "Local image worker (FLUX.2 Klein 4B)"
    assert image["contract_digest"] == expected_flux2_worker_contract().contract_digest
    assert "server_url" not in image and "api_key" not in image


def test_shared_image_card_projects_offline_without_leaking_transport(
    monkeypatch, tmp_path
):
    _FakeClient.constructed = []
    _FakeClient.capabilities = ComfyUITransportError("private failure")
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    ))

    with app.test_client() as client:
        image = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert image["state"] == "offline"
    assert image["blocker_code"] == "worker_offline"
    assert "private failure" not in str(image)


def _browser_worker_states() -> set[str]:
    """The `GpuWorkerState` union the browser type guard actually accepts."""

    source = (
        Path(__file__).resolve().parents[2] / "web" / "src" / "types" / "project.ts"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"export type GpuWorkerState =\n((?:\s*\|\s*'[a-z_]+'\n)+)", source
    )
    assert match, "web/src/types/project.ts no longer declares GpuWorkerState"
    states = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert states, "GpuWorkerState union parsed empty"
    return states


def test_projected_image_states_are_declared_in_the_browser_union() -> None:
    assert web_gpu_workers._PROJECTED_IMAGE_STATES <= _browser_worker_states()


def test_unreachable_capability_route_never_projects_a_transport_state(
    monkeypatch, tmp_path
):
    """A 404 on the capability route must not leak `absent` into the projection.

    `_gateway_readiness` reports transport outcomes ("absent" for 404,
    "not_ready" for 503) that are not part of the browser's `GpuWorkerState`
    union.  Passing one through made `isWorker` reject the entry, so the whole
    image worker vanished from the list instead of reporting as blocked.
    """

    _FakeClient.constructed = []
    _FakeClient.capabilities = ComfyUITransportError("not found", status_code=404)
    _FakeClient.stats = {
        "system": {"os": "nt"},
        "devices": [{
            "name": "NVIDIA GeForce RTX 5070 Ti",
            "vram_total": 16 * 1024**3,
            "vram_free": 12 * 1024**3,
        }],
    }
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    ))

    with app.test_client() as client:
        image = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert image["role"] == "image"
    assert image["state"] in _browser_worker_states()
    assert image["state"] == "blocked"


def test_shared_worker_forged_capability_state_fails_closed(monkeypatch, tmp_path):
    forged = _unified_gateway()
    forged["capabilities"]["image-flux2-klein"].update(
        state="ready", startup_ready=True, execution_proven=True
    )
    _FakeClient.capabilities = forged
    _FakeClient.object_info = {
        name: {} for name in web_gpu_workers._PERFORMANCE_NODE_CLASSES
    }
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    ))

    with app.test_client() as client:
        workers = client.get("/api/runtime/gpu-workers").get_json()["workers"]

    assert [worker["state"] for worker in workers] == [
        "blocked", "incompatible"
    ]
    assert "unified capability contract" in workers[1]["message"]


def test_shared_worker_mismatched_credentials_never_attempt_network(
    monkeypatch, tmp_path
):
    _FakeClient.constructed = []
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="i" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="p" * 32,
    ))

    with app.test_client() as client:
        workers = client.get("/api/runtime/gpu-workers").get_json()["workers"]

    assert [worker["state"] for worker in workers] == [
        "blocked", "unauthorized"
    ]
    assert _FakeClient.constructed == []


def test_raw_comfyui_is_reachable_but_not_guarded_ready(monkeypatch, tmp_path):
    _FakeClient.gateway = ComfyUITransportError("not found", status_code=404)
    _FakeClient.object_info = {"LoadImage": {}}
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="http://127.0.0.1:8188",
    ))

    with app.test_client() as client:
        worker = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert worker["state"] == "blocked"
    assert worker["blocker_code"] == "shared_capability_contract_required"


def test_generic_image_gateway_cannot_satisfy_exact_capability_contract(
    monkeypatch, tmp_path
):
    """Generic health cannot substitute for the exact image-worker contract."""

    _FakeClient.gateway = {"status": "ready", "checked_at_unix": 1}
    _FakeClient.object_info = {"LoadImage": {}}
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="https://image.example.test",
        comfyui_api_key="image-secret",
    ))

    with app.test_client() as client:
        worker = client.get("/api/runtime/gpu-workers").get_json()["workers"][0]

    assert worker["state"] == "blocked"
    assert worker["blocker_code"] == "shared_capability_contract_required"
    assert "shared worker contract" in worker["message"]


def test_missing_nodes_and_bad_credentials_are_distinct(monkeypatch, tmp_path):
    _FakeClient.gateway = _ready_gateway()
    _FakeClient.object_info = {}
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        comfyui_server_url="https://image.example.test",
        comfyui_api_key="image-secret",
        performance_comfyui_server_url="https://performance.example.test",
        performance_comfyui_api_key="p" * 32,
    ))

    with app.test_client() as client:
        workers = client.get("/api/runtime/gpu-workers").get_json()["workers"]

    assert workers[0]["state"] == "blocked"
    assert "missing_node_classes" not in workers[0]
    assert workers[1]["state"] == "incompatible"
    assert workers[1]["missing_node_classes"] == sorted(
        web_gpu_workers._PERFORMANCE_NODE_CLASSES
    )

    _FakeClient.gateway = ComfyUITransportError("denied", status_code=403)
    with app.test_client() as client:
        workers = client.get("/api/runtime/gpu-workers").get_json()["workers"]
    assert [worker["state"] for worker in workers] == ["blocked", "unauthorized"]


def test_wrong_role_gateway_can_never_report_performance_ready(monkeypatch, tmp_path):
    _FakeClient.gateway = {**_ready_gateway(), "role": "image-worker"}
    _FakeClient.object_info = {
        name: {} for name in web_gpu_workers._PERFORMANCE_NODE_CLASSES
    }
    _FakeClient.queue = {"queue_running": [], "queue_pending": []}
    monkeypatch.setattr(web_gpu_workers, "ComfyUIClient", _FakeClient)
    app = _app(monkeypatch, _settings(
        tmp_path,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="p" * 32,
    ))

    with app.test_client() as client:
        worker = client.get("/api/runtime/gpu-workers").get_json()["workers"][1]

    assert worker["state"] == "incompatible"
    assert "tracked performance-worker contract" in worker["message"]

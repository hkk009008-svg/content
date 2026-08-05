from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from performance.live_portrait_workflow import build_live_portrait_workflow
from performance.worker_readiness import (
    FLUX2_BENCHMARK_BLOCKER,
    IMAGE_CAPABILITY,
    WORKER_ROLE,
    PerformanceWorkerUnavailable,
    expected_flux2_worker_contract,
    expected_performance_worker_contract,
    performance_capability_from_unified,
    require_flux2_worker_ready,
    require_liveportrait_worker_ready,
    validate_performance_gateway_readiness,
    validate_flux2_gateway_readiness,
    validate_unified_gateway_capabilities,
)


def _deploy_contract(tmp_path: Path) -> Path:
    root = tmp_path / "worker"
    probes = root / "probes"
    probes.mkdir(parents=True)
    (root / "models.json").write_bytes(b'{"models":true}\n')
    (root / "revisions.json").write_bytes(b'{"revisions":true}\n')
    (probes / "one-frame-expression-api.json").write_text(
        json.dumps(
            build_live_portrait_workflow(
                "source-face.jpg", "driving-expression.mp4", 1 / 25
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (probes / "probe.json").write_text(
        json.dumps({"workflow": "one-frame-expression-api.json"}),
        encoding="utf-8",
    )
    return root


def _ready_payload(root: Path) -> dict[str, object]:
    contract = expected_performance_worker_contract(root)
    return {
        "status": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "execution_canary_state": "passed",
        **contract.gateway_fields(),
    }


def _image_payload(state: str = "not_installed") -> dict[str, object]:
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
            blocker_code=FLUX2_BENCHMARK_BLOCKER,
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
            execution_canary_sha256="a" * 64,
        )
    return payload


def _unified_payload(root: Path, image_state: str = "not_installed") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ready" if image_state == "ready" else "partial",
        "capabilities": {
            WORKER_ROLE: _ready_payload(root),
            IMAGE_CAPABILITY: _image_payload(image_state),
        },
    }


def test_gateway_readiness_is_bound_to_role_manifests_and_execution(tmp_path):
    root = _deploy_contract(tmp_path)
    payload = _ready_payload(root)

    assert validate_performance_gateway_readiness(payload, deploy_root=root) == payload

    for field, value in (
        ("role", "image-worker"),
        ("workflow_sha256", "0" * 64),
        ("execution_proven", False),
        ("execution_canary_state", "pending"),
    ):
        with pytest.raises(PerformanceWorkerUnavailable):
            validate_performance_gateway_readiness(
                {**payload, field: value}, deploy_root=root
            )


def test_generic_ready_record_is_never_performance_ready(tmp_path):
    root = _deploy_contract(tmp_path)
    with pytest.raises(PerformanceWorkerUnavailable):
        validate_performance_gateway_readiness(
            {"status": "ready"}, deploy_root=root
        )


def test_unified_contract_binds_ready_performance_and_not_installed_flux2(tmp_path):
    root = _deploy_contract(tmp_path)
    payload = _unified_payload(root)

    assert validate_unified_gateway_capabilities(payload, deploy_root=root) == payload
    assert performance_capability_from_unified(payload, deploy_root=root) == (
        payload["capabilities"][WORKER_ROLE]
    )
    assert IMAGE_CAPABILITY == "image-flux2-klein"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=2), "schema"),
        (lambda payload: payload.update(status="ready"), "aggregate"),
        (
            lambda payload: payload["capabilities"].pop(IMAGE_CAPABILITY),
            "capability set",
        ),
        (
            lambda payload: payload["capabilities"][IMAGE_CAPABILITY].update(
                state="ready", startup_ready=True, execution_proven=True
            ),
            "readiness evidence",
        ),
        (
            lambda payload: payload["capabilities"][IMAGE_CAPABILITY].update(
                blocker_code="operator_override"
            ),
            "readiness evidence",
        ),
        (
            lambda payload: payload["capabilities"].update(
                {"unexpected-image-worker": {"status": "blocked"}}
            ),
            "capability set",
        ),
        (
            lambda payload: payload["capabilities"][WORKER_ROLE].update(
                contract_digest="0" * 64
            ),
            "artifact contract",
        ),
    ],
)
def test_unified_contract_falsifications_fail_closed(tmp_path, mutation, message):
    root = _deploy_contract(tmp_path)
    payload = _unified_payload(root)
    mutation(payload)

    with pytest.raises(PerformanceWorkerUnavailable, match=message):
        validate_unified_gateway_capabilities(payload, deploy_root=root)


def test_probe_graph_drift_from_shipping_builder_fails_closed(tmp_path):
    root = _deploy_contract(tmp_path)
    workflow_path = root / "probes" / "one-frame-expression-api.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["11"]["inputs"]["frame_load_cap"] = 2
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    expected_performance_worker_contract.cache_clear()

    with pytest.raises(PerformanceWorkerUnavailable, match="drifted"):
        expected_performance_worker_contract(root)


def test_runtime_guard_rejects_unsafe_configuration_before_network(tmp_path):
    root = _deploy_contract(tmp_path)

    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("network client must not be constructed")

    with pytest.raises(PerformanceWorkerUnavailable, match="not safe"):
        require_liveportrait_worker_ready(
            SimpleNamespace(
                comfyui_server_url="https://image.example.test",
                performance_comfyui_server_url="http://192.0.2.16:8189",
                performance_comfyui_api_key="p" * 32,
            ),
            client_factory=forbidden_client,
            deploy_root=root,
        )


def test_runtime_guard_uses_bounded_authenticated_gateway_probe(tmp_path):
    root = _deploy_contract(tmp_path)
    seen = {}

    class Client:
        def __init__(self, server_url, **kwargs):
            seen.update(server_url=server_url, **kwargs)

        def get_gateway_readiness(self):
            return _ready_payload(root)

    payload = require_liveportrait_worker_ready(
        SimpleNamespace(
            comfyui_server_url="https://image.example.test",
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="p" * 32,
        ),
        client_factory=Client,
        deploy_root=root,
    )

    assert payload["status"] == "ready"
    assert seen == {
        "server_url": "http://127.0.0.1:18189",
        "auth_token": "p" * 32,
        "connect_timeout": 2.0,
        "read_timeout": 2.0,
    }


def test_shared_runtime_guard_requires_authenticated_capability_superset(tmp_path):
    root = _deploy_contract(tmp_path)
    seen = {}

    class Client:
        def __init__(self, server_url, **kwargs):
            seen.update(server_url=server_url, **kwargs)

        def get_gateway_readiness(self):
            raise AssertionError("public legacy readiness cannot admit a shared worker")

        def get_gateway_capabilities_readiness(self):
            return _unified_payload(root)

    payload = require_liveportrait_worker_ready(
        SimpleNamespace(
            comfyui_server_url="http://localhost:18189",
            comfyui_api_key="s" * 32,
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="s" * 32,
        ),
        client_factory=Client,
        deploy_root=root,
    )

    assert payload == _ready_payload(root)
    assert seen == {
        "server_url": "http://127.0.0.1:18189",
        "auth_token": "s" * 32,
        "connect_timeout": 2.0,
        "read_timeout": 2.0,
    }


def test_shared_runtime_guard_rejects_generic_authenticated_record(tmp_path):
    root = _deploy_contract(tmp_path)

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_gateway_capabilities_readiness(self):
            return _ready_payload(root)

    with pytest.raises(PerformanceWorkerUnavailable, match="schema"):
        require_liveportrait_worker_ready(
            SimpleNamespace(
                comfyui_server_url="http://127.0.0.1:18189",
                comfyui_api_key="s" * 32,
                performance_comfyui_server_url="http://127.0.0.1:18189",
                performance_comfyui_api_key="s" * 32,
            ),
            client_factory=Client,
            deploy_root=root,
        )


@pytest.mark.parametrize("state", ["not_installed", "needs_benchmark", "blocked"])
def test_flux2_guard_uses_only_zero_media_probe_for_non_ready_states(tmp_path, state):
    root = _deploy_contract(tmp_path)
    calls = []

    class Client:
        def __init__(self, server_url, **kwargs):
            calls.append(("construct", server_url, kwargs))

        def get_gateway_capabilities_readiness(self):
            calls.append(("capabilities",))
            return _unified_payload(root, state)

        def upload_image(self, *_args, **_kwargs):
            raise AssertionError("readiness guard uploaded media")

        def queue_prompt(self, *_args, **_kwargs):
            raise AssertionError("readiness guard submitted work")

    with pytest.raises(PerformanceWorkerUnavailable, match=f"is {state}"):
        require_flux2_worker_ready(
            SimpleNamespace(
                comfyui_server_url="http://localhost:18189",
                comfyui_api_key="s" * 32,
                performance_comfyui_server_url="http://127.0.0.1:18189",
                performance_comfyui_api_key="s" * 32,
            ),
            client_factory=Client,
            deploy_root=root,
        )

    assert calls == [
        (
            "construct",
            "http://127.0.0.1:18189",
            {
                "auth_token": "s" * 32,
                "connect_timeout": 2.0,
                "read_timeout": 2.0,
            },
        ),
        ("capabilities",),
    ]


def test_flux2_guard_accepts_only_exact_ready_evidence(tmp_path):
    root = _deploy_contract(tmp_path)

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_gateway_capabilities_readiness(self):
            return _unified_payload(root, "ready")

        def upload_image(self, *_args, **_kwargs):
            raise AssertionError("readiness guard uploaded media")

        def queue_prompt(self, *_args, **_kwargs):
            raise AssertionError("readiness guard submitted work")

    result = require_flux2_worker_ready(
        SimpleNamespace(
            comfyui_server_url="http://localhost:18189",
            comfyui_api_key="s" * 32,
            performance_comfyui_server_url="http://127.0.0.1:18189",
            performance_comfyui_api_key="s" * 32,
        ),
        client_factory=Client,
        deploy_root=root,
    )
    assert result["state"] == "ready"


def test_flux2_contract_hash_or_state_forgery_fails_closed():
    ready = _image_payload("ready")
    assert validate_flux2_gateway_readiness(ready, require_ready=True) == ready

    for mutation in (
        {"contract_digest": "0" * 64},
        {"benchmark_sha256": "not-a-hash"},
        {"state": "offline"},
    ):
        with pytest.raises(PerformanceWorkerUnavailable):
            validate_flux2_gateway_readiness({**ready, **mutation})

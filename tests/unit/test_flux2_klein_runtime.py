"""No-media-before-Ready and durable-only FLUX.2 runtime contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from comfyui_client import ComfyUITransportError
import performance.flux2_klein as flux2
from performance.worker_readiness import (
    FLUX2_BENCHMARK_BLOCKER,
    IMAGE_CAPABILITY,
    WORKER_ROLE,
    PerformanceWorkerUnavailable,
    expected_flux2_worker_contract,
    expected_performance_worker_contract,
)


class _DurableAuthority:
    paid_attempt_authority_version = 1

    def reserve_paid_attempt(self, **_kwargs):
        raise AssertionError("the patched durable runner owns this boundary")

    update_paid_attempt = reserve_paid_attempt
    reconcile_paid_attempt = reserve_paid_attempt
    get_paid_attempt = reserve_paid_attempt
    get_latest_paid_attempt = reserve_paid_attempt


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        comfyui_server_url="http://localhost:18189",
        comfyui_api_key="s" * 32,
        performance_comfyui_server_url="http://127.0.0.1:18189",
        performance_comfyui_api_key="s" * 32,
    )


def _performance_ready() -> dict[str, object]:
    return {
        "status": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "execution_canary_state": "passed",
        **expected_performance_worker_contract().gateway_fields(),
    }


def _image_state(state: str) -> dict[str, object]:
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
        )
    return payload


def _unified(state: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "ready" if state == "ready" else "partial",
        "capabilities": {
            WORKER_ROLE: _performance_ready(),
            IMAGE_CAPABILITY: _image_state(state),
        },
    }


def _references(tmp_path: Path, count: int = 1) -> list[str]:
    paths = []
    for index in range(count):
        path = tmp_path / f"reference-{index}.png"
        path.write_bytes(f"reference-{index}".encode())
        paths.append(str(path))
    return paths


@pytest.mark.parametrize(
    "state", ["not_installed", "needs_benchmark", "blocked", "offline"]
)
def test_non_ready_state_never_uploads_or_submits(tmp_path, state):
    calls: list[object] = []
    output = tmp_path / "result.png"
    output.write_bytes(b"existing-published-output")

    class Client:
        def __init__(self, *_args, **_kwargs):
            calls.append("construct")

        def get_gateway_capabilities_readiness(self):
            calls.append("capabilities")
            if state == "offline":
                raise ComfyUITransportError("offline")
            return _unified(state)

        def upload_image(self, *_args, **_kwargs):
            raise AssertionError("non-ready FLUX.2 uploaded media")

        def preflight(self, *_args, **_kwargs):
            raise AssertionError("non-ready FLUX.2 preflighted a submitted graph")

        def queue_prompt_preflighted(self, *_args, **_kwargs):
            raise AssertionError("non-ready FLUX.2 submitted work")

        def download_image(self, *_args, **_kwargs):
            raise AssertionError("non-ready FLUX.2 published output")

    with pytest.raises(PerformanceWorkerUnavailable):
        flux2.run_flux2_klein_image_job(
            prompt="preserve this identity",
            reference_image_paths=_references(tmp_path),
            output_path=str(output),
            seed=7,
            aspect_ratio="1:1",
            cost_tracker=_DurableAuthority(),
            settings_obj=_settings(),
            client_factory=Client,
        )

    assert calls == ["construct", "capabilities"]
    assert output.read_bytes() == b"existing-published-output"
    assert not list(tmp_path.glob(".comfy-*.tmp"))


@pytest.mark.parametrize("reference_count", [1, 4])
def test_ready_state_uploads_bounded_refs_then_uses_durable_job_only(
    monkeypatch, tmp_path, reference_count
):
    calls: list[object] = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            calls.append("construct")

        def get_gateway_capabilities_readiness(self):
            calls.append("capabilities")
            return _unified("ready")

        def upload_image(self, path):
            calls.append(("upload", Path(path).name))
            return f"staged/{Path(path).name}"

        def queue_prompt(self, *_args, **_kwargs):
            raise AssertionError("the helper bypassed durable job authority")

        def download_image(
            self,
            filename,
            subfolder,
            folder_type,
            destination,
            *,
            expected_dimensions,
        ):
            calls.append(("publish", filename, expected_dimensions))
            assert subfolder == "" and folder_type == "output"
            Path(destination).write_bytes(b"validated-image")
            return destination

    captured = {}

    def durable(**kwargs):
        calls.append("durable")
        captured.update(kwargs)
        return {
            "prompt-1": {
                "outputs": {
                    "23": {
                        "images": [
                            {"filename": "result.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

    monkeypatch.setattr(flux2, "run_durable_comfy_job", durable)
    result = flux2.run_flux2_klein_image_job(
        prompt="preserve this identity",
        reference_image_paths=_references(tmp_path, reference_count),
        output_path=str(tmp_path / "result.png"),
        seed=7,
        aspect_ratio="16:9",
        cost_tracker=_DurableAuthority(),
        settings_obj=_settings(),
        client_factory=Client,
        shot_id="shot-1",
        video_id="project-1",
    )

    assert calls[:2] == ["construct", "capabilities"]
    assert [
        call for call in calls if isinstance(call, tuple) and call[0] == "upload"
    ] == [
        ("upload", f"reference-{index}.png") for index in range(reference_count)
    ]
    assert calls[-2] == "durable"
    assert calls[-1] == ("publish", "result.png", (1280, 720))
    assert captured["engine"] == "FLUX2_KLEIN_LOCAL"
    assert captured["estimated_cost_usd"] == 0.0
    assert captured["workflow"]["8"]["inputs"]["steps"] == 4
    assert result.prompt_id == "prompt-1"
    assert result.output["filename"] == "result.png"
    assert result.published_path == str(tmp_path / "result.png")
    assert Path(result.published_path).read_bytes() == b"validated-image"


def test_invalid_reference_count_fails_before_network(tmp_path):
    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("invalid local input reached the network")

    with pytest.raises(ValueError, match=r"1\.\.4"):
        flux2.run_flux2_klein_image_job(
            prompt="candidate",
            reference_image_paths=[],
            output_path=str(tmp_path / "result.png"),
            seed=0,
            aspect_ratio="1:1",
            cost_tracker=_DurableAuthority(),
            settings_obj=_settings(),
            client_factory=forbidden_client,
        )

    with pytest.raises(ValueError, match=r"1\.\.4"):
        flux2.run_flux2_klein_image_job(
            prompt="candidate",
            reference_image_paths=_references(tmp_path, 5),
            output_path=str(tmp_path / "result.png"),
            seed=0,
            aspect_ratio="1:1",
            cost_tracker=_DurableAuthority(),
            settings_obj=_settings(),
            client_factory=forbidden_client,
        )

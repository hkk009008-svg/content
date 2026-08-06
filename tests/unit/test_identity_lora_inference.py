from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from identity.lora_inference import (
    _lora_modules,
    run_flux2_lora_image_job,
    train_character_lora,
)
from identity.lora_training import (
    LoraReadiness,
    LoraTrainingEvidence,
    current_lora_candidate_sha256,
)
from identity.protocols import LORA_BENCHMARK_PROMPT
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
        raise AssertionError("the injected durable runner owns this boundary")

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


def _unified(*, ready: bool = True) -> dict[str, object]:
    performance = {
        "status": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "execution_canary_state": "passed",
        **expected_performance_worker_contract().gateway_fields(),
    }
    image: dict[str, object] = {
        **expected_flux2_worker_contract().gateway_fields(),
        "state": "ready" if ready else "needs_benchmark",
        "startup_ready": ready,
        "execution_proven": True,
        "benchmark_state": "passed" if ready else "not_run",
        "blocker_code": "" if ready else FLUX2_BENCHMARK_BLOCKER,
        "artifacts_installed": True,
        "runtime_contract_sha256": "c" * 64,
        "license_review_state": "official_source_derivation_verified",
        "execution_canary_state": "passed",
        "execution_canary_sha256": "a" * 64,
        "benchmark_sha256": "b" * 64 if ready else "",
    }
    return {
        "schema_version": 1,
        "status": "ready" if ready else "partial",
        "capabilities": {WORKER_ROLE: performance, IMAGE_CAPABILITY: image},
    }


def _references(tmp_path: Path) -> list[Path]:
    paths = []
    for index in range(4):
        path = tmp_path / f"reference-{index}.png"
        Image.new("RGB", (512, 512), (index * 40, 10, 200)).save(path)
        paths.append(path)
    return paths


def _evidence() -> LoraTrainingEvidence:
    candidate = current_lora_candidate_sha256()
    adapter_sha = "c" * 64
    metadata = {
        "job_id": "b" * 32,
        "adapter": {
            "filename": f"identity-lora-{adapter_sha}.safetensors",
            "bytes": 123,
            "sha256": adapter_sha,
        },
        "training": {"package_sha256": candidate},
    }
    metadata_sha256 = hashlib.sha256(
        (
            json.dumps(
                metadata,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    return LoraTrainingEvidence(
        job_id="b" * 32,
        adapter_sha256=adapter_sha,
        adapter_size_bytes=123,
        comfy_name=f"identity-lora-{adapter_sha}.safetensors",
        elapsed_seconds=12.0,
        peak_vram_bytes=456,
        adapter_metadata=metadata,
        adapter_metadata_sha256=metadata_sha256,
        raw={
            "candidate_sha256": candidate,
            "adapter_metadata": metadata,
            "adapter_metadata_sha256": metadata_sha256,
        },
    )


def test_package_loader_does_not_create_rejected_bytecode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = Path(__file__).resolve().parents[2] / "deploy" / "windows-flux2-lora"
    copied = tmp_path / "windows-flux2-lora"
    shutil.copytree(package, copied, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(sys, "dont_write_bytecode", False)

    contract, inference = _lora_modules(copied)

    assert callable(contract.validate_package)
    assert callable(inference.build_inference_workflow)
    assert not (copied / "__pycache__").exists()


def test_training_requires_job_submission_readiness_for_a_new_job(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class Client:
        def __init__(self, *_args):
            calls.append("construct")

        def get_readiness(self, candidate):
            calls.append("readiness")
            return LoraReadiness("blocked", "canary_not_proven", candidate, False)

        def get_job(self, _job_id):
            calls.append("get-job")
            return None

        def ensure_training(self, *_args, **_kwargs):
            raise AssertionError("blocked gateway admitted training")

    with pytest.raises(PerformanceWorkerUnavailable, match="canary_not_proven"):
        train_character_lora(
            reference_paths=_references(tmp_path),
            project_id="project-a",
            character_id="character-a",
            settings_obj=_settings(),
            client_factory=Client,
        )

    assert calls == ["construct", "readiness", "get-job"]


def test_training_reconciles_an_exact_job_when_new_submission_is_blocked(
    tmp_path: Path,
) -> None:
    expected = object()
    calls: list[str] = []

    class Client:
        def __init__(self, *_args):
            pass

        def get_readiness(self, candidate):
            return LoraReadiness(
                "blocked", "candidate_training_not_proven", candidate, False
            )

        def get_job(self, job_id):
            calls.append(job_id)
            return {"state": "interrupted"}

        def ensure_training(self, plan, **kwargs):
            assert plan.job_id == calls[0]
            assert kwargs["allow_interrupted_resume"] is True
            return expected

    result = train_character_lora(
        reference_paths=_references(tmp_path),
        project_id="project-a",
        character_id="character-a",
        allow_interrupted_resume=True,
        settings_obj=_settings(),
        client_factory=Client,
    )

    assert result is expected


@pytest.mark.parametrize(
    ("state", "blocker"),
    [("ready", ""), ("blocked", "candidate_training_not_proven")],
)
def test_training_submits_one_fixed_plan_when_job_admission_is_ready(
    tmp_path: Path, state: str, blocker: str
) -> None:
    captured = {}
    expected = object()

    class Client:
        def __init__(self, *_args):
            pass

        def get_readiness(self, candidate):
            return LoraReadiness(state, blocker, candidate, True)

        def ensure_training(self, plan, **kwargs):
            captured["plan"] = plan
            captured.update(kwargs)
            return expected

    result = train_character_lora(
        reference_paths=_references(tmp_path),
        project_id="project-a",
        character_id="character-a",
        allow_interrupted_resume=True,
        settings_obj=_settings(),
        client_factory=Client,
    )

    assert result is expected
    assert captured["plan"].manifest["consent"] is True
    assert len(captured["plan"].sources) == 4
    assert captured["allow_interrupted_resume"] is True


def _modules(calls: list[object]):
    candidate = current_lora_candidate_sha256()

    class Contract:
        @staticmethod
        def package_digest(_root):
            return candidate

        @staticmethod
        def validate_adapter_metadata(metadata):
            calls.append("metadata")
            return metadata

    class Inference:
        @staticmethod
        def build_control_workflow(*, metadata, prompt):
            calls.append("build-control")
            return {
                "14": {
                    "class_type": "SaveImage",
                    "inputs": {"images": ["13", 0], "filename_prefix": "control"},
                }
            }

        @staticmethod
        def build_inference_workflow(*, metadata, prompt):
            calls.append("build-adapter")
            return {
                "14": {
                    "class_type": "SaveImage",
                    "inputs": {"images": ["13", 0], "filename_prefix": "adapter"},
                }
            }

        @staticmethod
        def validate_control_workflow(graph, metadata, object_info):
            assert object_info == {"installed": True}
            calls.append("validate-control")

        @staticmethod
        def validate_inference_workflow(graph, metadata, object_info):
            assert object_info == {"installed": True}
            calls.append("validate-adapter")

    return Contract, Inference


def test_control_and_adapter_use_distinct_durable_jobs_and_publish_png(
    tmp_path: Path,
) -> None:
    calls: list[object] = []
    attempts: list[str] = []

    class ComfyClient:
        def __init__(self, *_args, **_kwargs):
            calls.append("construct-comfy")

        def get_gateway_capabilities_readiness(self):
            calls.append("worker-ready")
            return _unified()

        def get_object_info(self):
            calls.append("object-info")
            return {"installed": True}

        def download_image(
            self, filename, subfolder, folder_type, destination, *, expected_dimensions
        ):
            calls.append(("publish", expected_dimensions))
            assert (filename, subfolder, folder_type) == ("result.png", "", "output")
            Path(destination).write_bytes(b"validated-png")
            return destination

    class LoraClient:
        def __init__(self, *_args):
            calls.append("construct-lora")

        def get_readiness(self, candidate):
            calls.append("lora-ready")
            return LoraReadiness("ready", "", candidate, True)

    def durable(**kwargs):
        calls.append("durable")
        attempts.append(kwargs["attempt_id"])
        assert kwargs["engine"] == "FLUX2_KLEIN_LORA_LOCAL"
        assert kwargs["operation"] == "identity_inference"
        assert kwargs["estimated_cost_usd"] == 0.0
        return {
            "prompt-1": {
                "outputs": {
                    "14": {
                        "images": [
                            {
                                "filename": "result.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        }

    for mode in ("control", "adapter"):
        result = run_flux2_lora_image_job(
            prompt=LORA_BENCHMARK_PROMPT,
            mode=mode,
            evidence=_evidence(),
            output_path=str(tmp_path / f"{mode}.png"),
            cost_tracker=_DurableAuthority(),
            shot_id=f"shot-{mode}",
            video_id="project-a",
            request_id="request-a",
            settings_obj=_settings(),
            client_factory=ComfyClient,
            lora_client_factory=LoraClient,
            durable_runner=durable,
            module_loader=lambda _root: _modules(calls),
        )
        assert result.prompt_id == "prompt-1"
        assert Path(result.published_path).read_bytes() == b"validated-png"

    assert "build-control" in calls and "validate-control" in calls
    assert "build-adapter" in calls and "validate-adapter" in calls
    assert len(set(attempts)) == 2
    assert calls.count("durable") == 2


def test_nonready_lora_never_introspects_or_submits(tmp_path: Path) -> None:
    calls: list[str] = []

    class ComfyClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_gateway_capabilities_readiness(self):
            calls.append("worker-ready")
            return _unified()

        def get_object_info(self):
            raise AssertionError("blocked LoRA introspected a submission graph")

    class LoraClient:
        def __init__(self, *_args):
            pass

        def get_readiness(self, candidate):
            calls.append("lora-ready")
            return LoraReadiness(
                "blocked", "inference_benchmark_not_proven", candidate, False
            )

    with pytest.raises(PerformanceWorkerUnavailable, match="benchmark_not_proven"):
        run_flux2_lora_image_job(
            prompt=LORA_BENCHMARK_PROMPT,
            mode="adapter",
            evidence=_evidence(),
            output_path=str(tmp_path / "result.png"),
            cost_tracker=_DurableAuthority(),
            settings_obj=_settings(),
            client_factory=ComfyClient,
            lora_client_factory=LoraClient,
            durable_runner=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("blocked LoRA submitted work")
            ),
            module_loader=lambda _root: _modules([]),
        )

    assert calls == ["worker-ready", "lora-ready"]


def test_forged_adapter_metadata_digest_fails_before_network(tmp_path: Path) -> None:
    evidence = replace(_evidence(), adapter_metadata_sha256="f" * 64)

    with pytest.raises(PerformanceWorkerUnavailable, match="not bound"):
        run_flux2_lora_image_job(
            prompt=LORA_BENCHMARK_PROMPT,
            mode="adapter",
            evidence=evidence,
            output_path=str(tmp_path / "result.png"),
            cost_tracker=_DurableAuthority(),
            settings_obj=_settings(),
            client_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("forged evidence reached the network")
            ),
            module_loader=lambda _root: _modules([]),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1, True])
def test_invalid_poll_timeout_fails_before_loading_or_network(
    tmp_path: Path, value: object
) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        run_flux2_lora_image_job(
            prompt=LORA_BENCHMARK_PROMPT,
            mode="adapter",
            evidence=_evidence(),
            output_path=str(tmp_path / "result.png"),
            cost_tracker=_DurableAuthority(),
            poll_timeout_s=value,  # type: ignore[arg-type]
            settings_obj=_settings(),
            client_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("invalid wait bound reached the network")
            ),
            module_loader=lambda _root: (_ for _ in ()).throw(
                AssertionError("invalid wait bound loaded the package")
            ),
        )

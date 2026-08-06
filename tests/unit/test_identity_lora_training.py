from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from PIL import Image

from identity.lora_training import (
    LORA_CONTRACT,
    LoraTrainingClient,
    LoraTrainingError,
    LoraTrainingPlan,
    LoraTrainingStateUnknown,
    _regular_bytes,
    build_lora_training_plan,
    fixed_character_token,
)


def test_reference_reader_uses_a_bounded_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "reference.bin"
    path.write_bytes(b"bounded")
    real_fdopen = os.fdopen
    read_sizes: list[int] = []

    class Reader:
        def __init__(self, descriptor: int):
            self.handle = real_fdopen(descriptor, "rb", closefd=True)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.handle.close()

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return self.handle.read(size)

        def fileno(self) -> int:
            return self.handle.fileno()

    monkeypatch.setattr(os, "fdopen", lambda descriptor, *_args, **_kwargs: Reader(descriptor))

    assert _regular_bytes(path, maximum=32) == b"bounded"
    assert read_sizes == [33]


def _references(root: Path) -> list[Path]:
    values = []
    for index in range(4):
        path = root / f"reference-{index}.png"
        Image.new("RGB", (512, 512), (index * 40, 20, 200)).save(path)
        values.append(path)
    return values


def _response(status: int, payload: dict) -> MagicMock:
    value = MagicMock()
    value.status_code = status
    value.content = b"{}"
    value.json.return_value = payload
    return value


def _bound_status(
    plan, state: str, *, retry_mode: str = "none", blocker_code: str = ""
) -> dict:
    manifest_bytes = (
        json.dumps(
            plan.manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "job_id": plan.job_id,
        "contract": LORA_CONTRACT,
        "candidate_sha256": plan.manifest["candidate_sha256"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "state": state,
        "retriable": retry_mode != "none",
        "retry_mode": retry_mode,
        "created_at_unix": 1,
        "updated_at_unix": 1,
        "started_at_unix": 1,
        "completed_at_unix": 1 if state in {"succeeded", "failed", "unknown", "interrupted"} else None,
        "exit_code": 0 if state == "succeeded" else None,
        "blocker_code": blocker_code,
    }


def _completed_evidence(plan) -> dict:
    status = _bound_status(plan, "succeeded")
    adapter_payload = b"adapter"
    adapter_sha256 = hashlib.sha256(adapter_payload).hexdigest()
    adapter_name = f"identity-lora-{adapter_sha256}.safetensors"
    metadata = {
        "schema_version": 1,
        "state": "training_passed",
        "job_id": plan.job_id,
        "adapter": {
            "filename": adapter_name,
            "bytes": len(adapter_payload),
            "sha256": adapter_sha256,
        },
        "training": {"package_sha256": plan.manifest["candidate_sha256"]},
    }
    metadata_bytes = (
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return {
        **status,
        "adapter": {
            "sha256": adapter_sha256,
            "size_bytes": len(adapter_payload),
            "comfy_name": adapter_name,
        },
        "adapter_metadata": metadata,
        "adapter_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "training": {
            "steps": 500,
            "resolution": 512,
            "rank": 16,
            "seed": 0,
            "batch_size": 1,
            "elapsed_seconds": 12.5,
            "peak_vram_bytes": 123,
        },
        "completed_at_unix": 1,
    }


def test_plan_is_fixed_consent_bound_and_content_addressed(tmp_path: Path) -> None:
    token = fixed_character_token("project-a", "character-a")
    plan = build_lora_training_plan(_references(tmp_path), consent=True)

    assert plan.manifest["contract"] == LORA_CONTRACT
    assert plan.manifest["consent"] is True
    assert len(plan.manifest["references"]) == 4
    assert len({value["sha256"] for value in plan.manifest["references"]}) == 4
    assert len(plan.job_id) == 32
    assert all(payload.startswith(b"\x89PNG\r\n\x1a\n") for payload, _digest in plan.sources)
    assert token == "hkkperson"

    replay = build_lora_training_plan(_references(tmp_path), consent=True)
    assert replay.job_id == plan.job_id


def test_plan_rejects_missing_consent_and_duplicate_bytes(tmp_path: Path) -> None:
    paths = _references(tmp_path)
    with pytest.raises(ValueError, match="consent"):
        build_lora_training_plan(paths, consent=False)
    paths[3].write_bytes(paths[0].read_bytes())
    with pytest.raises(ValueError, match="distinct content"):
        build_lora_training_plan(paths, consent=True)


def test_lost_submit_ack_is_unknown_and_never_reposted(tmp_path: Path) -> None:
    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    session = MagicMock()
    session.get.return_value = _response(404, {"error": "not_found"})
    session.put.side_effect = [
        _response(201, {"sha256": digest, "size_bytes": len(payload)})
        for payload, digest in plan.sources
    ] + [requests.ConnectionError("ack lost")]
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingStateUnknown) as caught:
        client.ensure_training(plan, sleep=lambda _seconds: None)

    assert caught.value.job_id == plan.job_id
    assert session.put.call_count == 5


def test_lost_blob_ack_reports_the_planned_job_id(tmp_path: Path) -> None:
    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    session = MagicMock()
    session.get.return_value = _response(404, {"error": "not_found"})
    session.put.side_effect = requests.ConnectionError("blob ack lost")
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingStateUnknown) as caught:
        client.ensure_training(plan)

    assert caught.value.job_id == plan.job_id
    assert session.put.call_count == 1


def test_bound_unknown_launch_response_is_unknown_and_not_resubmitted(
    tmp_path: Path,
) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    session = MagicMock()
    session.get.return_value = _response(404, {"error": "not_found"})
    session.put.side_effect = [
        _response(201, {"sha256": digest, "size_bytes": len(payload)})
        for payload, digest in plan.sources
    ] + [_response(503, _bound_status(plan, "unknown"))]
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    with pytest.raises(LoraTrainingStateUnknown) as caught:
        client.ensure_training(plan)

    assert caught.value.job_id == plan.job_id
    assert session.put.call_count == 5
    session.post.assert_not_called()


def test_plaintext_remote_gateway_and_mutated_plan_fail_before_upload(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        LoraTrainingClient("http://example.com", "a" * 32)
    with pytest.raises(ValueError, match="token value only"):
        LoraTrainingClient("http://127.0.0.1:8189", "  Bearer " + "a" * 32)

    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    plan.manifest["consent"] = False
    session = MagicMock()
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingError, match="manifest changed"):
        client.ensure_training(plan)

    session.get.assert_not_called()
    session.put.assert_not_called()


def test_recomputed_id_cannot_bypass_the_consent_manifest_gate(tmp_path: Path) -> None:
    original = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    manifest = {**original.manifest, "consent": False}
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    forged = LoraTrainingPlan(
        hashlib.sha256(manifest_bytes).hexdigest()[:32],
        manifest,
        original.sources,
    )
    session = MagicMock()
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingError, match="manifest changed"):
        client.ensure_training(forged)

    session.get.assert_not_called()
    session.put.assert_not_called()


def test_forged_three_source_plan_is_rejected_before_network(tmp_path: Path) -> None:
    original = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    manifest = {**original.manifest, "references": original.manifest["references"][:3]}
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    forged = LoraTrainingPlan(
        hashlib.sha256(manifest_bytes).hexdigest()[:32],
        manifest,
        original.sources[:3],
    )
    session = MagicMock()
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingError, match="references changed"):
        client.ensure_training(forged)

    session.get.assert_not_called()
    session.put.assert_not_called()


@pytest.mark.parametrize(
    ("status", "state", "blocker", "job_submission_ready"),
    [
        (200, "ready", "", True),
        (503, "blocked", "canary_not_proven", False),
        (503, "blocked", "candidate_training_not_proven", True),
    ],
)
def test_readiness_is_candidate_bound(
    status: int, state: str, blocker: str, job_submission_ready: bool
) -> None:
    candidate = "c" * 64
    session = MagicMock()
    session.get.return_value = _response(
        status,
        {
            "schema_version": 1,
            "contract": LORA_CONTRACT,
            "candidate_sha256": candidate,
            "state": state,
            "blocker_code": blocker,
            "job_submission_ready": job_submission_ready,
        },
    )
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    readiness = client.get_readiness(candidate)

    assert readiness.state == state
    assert readiness.blocker_code == blocker
    assert readiness.job_submission_ready is job_submission_ready


def test_readiness_rejects_a_different_candidate() -> None:
    session = MagicMock()
    session.get.return_value = _response(
        200,
        {
            "schema_version": 1,
            "contract": LORA_CONTRACT,
            "candidate_sha256": "d" * 64,
            "state": "ready",
            "blocker_code": "",
            "job_submission_ready": True,
        },
    )
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingError, match="readiness contract"):
        client.get_readiness("c" * 64)


def test_existing_job_is_reconciled_without_upload_or_resubmit(tmp_path: Path) -> None:
    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    status = _bound_status(plan, "succeeded")
    evidence = _completed_evidence(plan)
    session = MagicMock()
    session.get.side_effect = [_response(200, status), _response(200, evidence)]
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    result = client.ensure_training(plan)

    assert result.adapter_sha256 == evidence["adapter"]["sha256"]
    assert result.peak_vram_bytes == 123
    session.put.assert_not_called()


def test_interrupted_job_requires_explicit_same_id_resume(tmp_path: Path) -> None:
    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    interrupted = _bound_status(plan, "interrupted", retry_mode="checkpoint")
    session = MagicMock()
    session.get.return_value = _response(200, interrupted)
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingStateUnknown, match="explicit same-job resume"):
        client.ensure_training(plan)

    session.post.assert_not_called()


def test_bound_unknown_resume_response_is_unknown_and_not_retried(
    tmp_path: Path,
) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    interrupted = _bound_status(plan, "interrupted", retry_mode="checkpoint")
    session = MagicMock()
    session.get.return_value = _response(200, interrupted)
    session.post.return_value = _response(503, _bound_status(plan, "unknown"))
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    with pytest.raises(LoraTrainingStateUnknown) as caught:
        client.ensure_training(plan, allow_interrupted_resume=True)

    assert caught.value.job_id == plan.job_id
    assert session.post.call_count == 1
    session.put.assert_not_called()


def test_explicit_resume_retries_only_the_same_failed_benchmark_job(
    tmp_path: Path,
) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    failed = _bound_status(
        plan,
        "failed",
        retry_mode="benchmark",
        blocker_code="benchmark_not_started",
    )
    benchmarking = _bound_status(plan, "benchmarking")
    succeeded = _bound_status(plan, "succeeded")
    evidence = _completed_evidence(plan)
    session = MagicMock()
    session.get.side_effect = [
        _response(200, failed),
        _response(200, succeeded),
        _response(200, evidence),
    ]
    session.post.return_value = _response(202, benchmarking)
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    result = client.ensure_training(
        plan,
        allow_interrupted_resume=True,
        sleep=lambda _seconds: None,
    )

    assert result.job_id == plan.job_id
    assert session.post.call_count == 1
    session.put.assert_not_called()


def test_retriable_failed_job_does_not_resume_without_explicit_authority(
    tmp_path: Path,
) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    failed = _bound_status(plan, "failed", retry_mode="initial")
    session = MagicMock()
    session.get.return_value = _response(200, failed)
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    with pytest.raises(LoraTrainingStateUnknown, match="explicit same-job resume"):
        client.ensure_training(plan)

    session.post.assert_not_called()
    session.put.assert_not_called()


def test_status_rejects_retry_mode_on_a_running_job(tmp_path: Path) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    invalid = _bound_status(plan, "running", retry_mode="checkpoint")
    session = MagicMock()
    session.get.return_value = _response(200, invalid)
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    with pytest.raises(LoraTrainingError, match="invalid job state"):
        client.ensure_training(plan)

    session.post.assert_not_called()
    session.put.assert_not_called()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("job_id", "f" * 32),
        ("contract", "different-contract"),
        ("candidate_sha256", "f" * 64),
        ("manifest_sha256", "e" * 64),
        ("state", "failed"),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", 0.0),
        ("peak_vram_bytes", 0),
        ("seed", False),
        ("batch_size", True),
    ],
)
def test_evidence_rejects_wrong_job_contract_state_and_nonfinite_telemetry(
    tmp_path: Path, mutation: str, value: object
) -> None:
    plan = build_lora_training_plan(
        _references(tmp_path),
        consent=True,
    )
    status = _bound_status(plan, "succeeded")
    evidence = _completed_evidence(plan)
    if mutation in {"elapsed_seconds", "peak_vram_bytes", "seed", "batch_size"}:
        evidence["training"][mutation] = value
    else:
        evidence[mutation] = value
    session = MagicMock()
    session.get.side_effect = [_response(200, status), _response(200, evidence)]
    client = LoraTrainingClient("http://127.0.0.1:8189", "a" * 32, session=session)

    with pytest.raises(LoraTrainingError):
        client.ensure_training(plan)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1, True])
def test_nonfinite_and_nonpositive_wait_bounds_fail_before_network(
    tmp_path: Path, value: object
) -> None:
    plan = build_lora_training_plan(_references(tmp_path), consent=True)
    session = MagicMock()
    client = LoraTrainingClient(
        "http://127.0.0.1:8189", "a" * 32, session=session
    )

    with pytest.raises(ValueError, match="finite and positive"):
        client.ensure_training(plan, timeout_s=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite and positive"):
        client.ensure_training(plan, poll_seconds=value)  # type: ignore[arg-type]

    session.get.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1, True])
def test_invalid_request_timeouts_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        LoraTrainingClient(
            "http://127.0.0.1:8189",
            "a" * 32,
            connect_timeout=value,  # type: ignore[arg-type]
        )

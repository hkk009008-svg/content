#!/usr/bin/env python3
"""Sequential text-only/LoRA inference causality benchmark on local ComfyUI."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True

from contract import (
    ACTIVITY_LEASE_ENV,
    BENCHMARK_CONTRACT,
    BENCHMARK_PROMPT,
    CAPABILITY,
    ContractError,
    ROOT,
    adapter_filename,
    benchmark_png_pixel_sha256,
    canonical_job_id,
    canonical_json_bytes,
    canonical_utf8_json_bytes,
    file_record,
    job_paths,
    package_digest,
    PROMPT_ID_RE,
    read_json_object,
    sample_gpu_memory_used_bytes,
    sha256_bytes,
    validate_adapter_file,
    validate_adapter_metadata,
    validate_api_manifest,
    validate_input_manifest,
    validate_inference_runtime,
    validate_package,
    validate_benchmark_proof,
    validate_gateway_activity_lease,
    windows_state_root,
    write_bytes_new,
    write_json_new,
)
from inference import (
    build_control_workflow,
    build_inference_workflow,
    validate_control_workflow,
    validate_inference_workflow,
)
from train import validate_terminal_evidence


ENDPOINT = "http://127.0.0.1:8188"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_JSON_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_PNG_RESPONSE_BYTES = 50 * 1024 * 1024


class _CausalityFailure(ContractError):
    pass


class _SubmissionUnknown(ContractError):
    pass


def _bounded_response_bytes(response: Any, maximum: int, content_type: str) -> bytes:
    if response.getcode() != 200:
        raise ContractError("local ComfyUI returned a non-success status")
    actual_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
    if actual_type != content_type:
        raise ContractError("local ComfyUI response content type drifted")
    length = response.headers.get("Content-Length")
    if length is not None:
        try:
            parsed_length = int(length)
        except ValueError as exc:
            raise ContractError("local ComfyUI response length is malformed") from exc
        if parsed_length < 0 or parsed_length > maximum:
            raise ContractError("local ComfyUI response exceeds the fixed byte bound")
    payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise ContractError("local ComfyUI response exceeds the fixed byte bound")
    return payload


def _acquire_activity(paths: Mapping[str, Path], job_id: str) -> str:
    return write_json_new(
        paths["activity_lock"],
        {
            "schema_version": 1,
            "capability": CAPABILITY,
            "activity": "benchmark",
            "job_id": job_id,
            "owner_pid": os.getpid(),
            "nonce": uuid.uuid4().hex,
        },
        root=paths["root"],
    )


def _release_activity(paths: Mapping[str, Path], lease_sha256: str) -> None:
    path = paths["activity_lock"]
    try:
        info = path.lstat()
        digest = file_record(path, root=paths["root"])["sha256"]
    except (OSError, ContractError) as exc:
        raise ContractError("benchmark activity lease cannot be verified") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or digest != lease_sha256:
        raise ContractError("benchmark activity lease ownership changed")
    try:
        path.unlink()
    except OSError as exc:
        raise ContractError("benchmark activity lease cannot be released") from exc


def _http_json(method: str, path: str, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    body = None if payload is None else canonical_utf8_json_bytes(payload)
    request = urllib.request.Request(
        ENDPOINT + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = _bounded_response_bytes(
                response, MAX_JSON_RESPONSE_BYTES, "application/json"
            )
    except (OSError, urllib.error.URLError) as exc:
        raise ContractError("local ComfyUI JSON request failed") from exc
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("local ComfyUI returned invalid JSON") from exc
    if not isinstance(result, Mapping):
        raise ContractError("local ComfyUI JSON response is not an object")
    return result


def _http_bytes(path: str) -> bytes:
    try:
        with urllib.request.urlopen(ENDPOINT + path, timeout=60) as response:
            payload = _bounded_response_bytes(
                response, MAX_PNG_RESPONSE_BYTES, "image/png"
            )
    except (OSError, urllib.error.URLError) as exc:
        raise ContractError("local ComfyUI output download failed") from exc
    if not payload:
        raise ContractError("local ComfyUI output download was empty")
    return payload


def _require_idle(queue: Mapping[str, Any]) -> None:
    if set(queue) != {"queue_running", "queue_pending"}:
        raise ContractError("ComfyUI queue response fields drifted")
    if queue.get("queue_running") != [] or queue.get("queue_pending") != []:
        raise ContractError("ComfyUI queue must be idle before each benchmark arm")


def _image_output(history: Mapping[str, Any], prompt_id: str, prefix: str) -> dict[str, str]:
    record = history.get(prompt_id)
    if not isinstance(record, Mapping):
        raise ContractError("completed prompt history is missing")
    status = record.get("status")
    if not isinstance(status, Mapping) or status.get("status_str") != "success":
        raise ContractError("ComfyUI prompt did not report success")
    outputs = record.get("outputs")
    images = outputs.get("14", {}).get("images") if isinstance(outputs, Mapping) else None
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], Mapping):
        raise ContractError("benchmark arm did not produce exactly one SaveImage output")
    image = images[0]
    if set(image) != {"filename", "subfolder", "type"}:
        raise ContractError("ComfyUI output descriptor fields drifted")
    filename = image.get("filename")
    subfolder = image.get("subfolder")
    output_type = image.get("type")
    if (
        not isinstance(filename, str)
        or not filename.startswith(prefix)
        or Path(filename).name != filename
        or not isinstance(subfolder, str)
        or PurePosixPath(subfolder).is_absolute()
        or ".." in PurePosixPath(subfolder).parts
        or output_type != "output"
    ):
        raise ContractError("ComfyUI output descriptor is unsafe or unowned")
    return {"filename": filename, "subfolder": subfolder, "type": output_type}


def _run_arm(
    *,
    arm: str,
    graph: Mapping[str, Any],
    workflow_sha256: str,
    output_path: Path,
    owned_root: Path,
    api_json: Callable[..., Mapping[str, Any]],
    api_bytes: Callable[[str], bytes],
    gpu_sample: Callable[[], int],
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> dict[str, object]:
    _require_idle(api_json("GET", "/queue"))
    started = clock()
    try:
        submission = api_json("POST", "/prompt", {"prompt": graph})
    except Exception as exc:
        raise _SubmissionUnknown("benchmark submission outcome is ambiguous") from exc
    prompt_id = submission.get("prompt_id")
    if not isinstance(prompt_id, str) or not PROMPT_ID_RE.fullmatch(prompt_id):
        raise _SubmissionUnknown("benchmark submission acknowledgement is ambiguous")
    try:
        peak_vram = 0
        sample_count = 0
        while True:
            peak_vram = max(peak_vram, gpu_sample())
            sample_count += 1
            history = api_json("GET", f"/history/{prompt_id}")
            if prompt_id in history:
                break
            if clock() - started > 300:
                raise ContractError("benchmark execution timed out")
            sleeper(0.25)
        latency = clock() - started
        _require_idle(api_json("GET", "/queue"))
        prefix = str(graph["14"]["inputs"]["filename_prefix"])
        descriptor = _image_output(history, prompt_id, prefix)
        query = urllib.parse.urlencode(descriptor, quote_via=urllib.parse.quote)
        output = api_bytes("/view?" + query)
        pixel_sha = benchmark_png_pixel_sha256(output)
        output_sha = write_bytes_new(output_path, output, root=owned_root)
    except Exception as exc:
        raise _SubmissionUnknown("benchmark outcome after prompt acceptance is unknown") from exc
    if (
        isinstance(latency, bool)
        or not isinstance(latency, (int, float))
        or not math.isfinite(latency)
        or latency <= 0
        or type(peak_vram) is not int
        or peak_vram <= 0
        or sample_count <= 0
    ):
        raise ContractError("benchmark telemetry is incomplete")
    return {
        "arm": arm,
        "prompt_id": prompt_id,
        "workflow_sha256": workflow_sha256,
        "output_file": output_path.name,
        "output_bytes": len(output),
        "output_sha256": output_sha,
        "pixel_sha256": pixel_sha,
        "latency_seconds": round(latency, 6),
        "peak_vram_bytes": peak_vram,
    }


def run_benchmark(
    state_root: Path,
    job_id: str,
    *,
    api_json: Callable[..., Mapping[str, Any]] = _http_json,
    api_bytes: Callable[[str], bytes] = _http_bytes,
    gpu_sample: Callable[[], int] = sample_gpu_memory_used_bytes,
    clock: Callable[[], float] = time.perf_counter,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    validate_package(ROOT)
    job_id = canonical_job_id(job_id)
    paths = job_paths(state_root, job_id)
    proof_path = paths["evidence"] / "inference-benchmark.json"
    attempt_path = paths["evidence"] / "inference-benchmark-attempt.json"
    output_root = paths["job"] / "benchmark"
    prior_paths = (
        proof_path,
        attempt_path,
        paths["evidence"] / "inference-benchmark-failed.json",
        paths["evidence"] / "inference-benchmark-unknown.json",
        output_root,
    )
    if any(path.exists() or path.is_symlink() for path in prior_paths):
        raise ContractError("inference benchmark already attempted; automatic retry is forbidden")
    candidate_sha = package_digest(ROOT)
    input_result = validate_input_manifest(state_root, job_id)
    api_manifest = validate_api_manifest(
        state_root, job_id, input_result=input_result, candidate_sha256=candidate_sha
    )
    terminal_path = paths["evidence"] / "terminal.json"
    terminal = read_json_object(terminal_path, root=paths["evidence"])
    validate_terminal_evidence(terminal)
    inference_runtime = validate_inference_runtime()
    runtime_contract_sha = inference_runtime["runtime_contract_sha256"]
    if (
        terminal.get("state") != "training_passed"
        or terminal.get("candidate_sha256") != candidate_sha
        or terminal.get("manifest_sha256") != api_manifest["sha256"]
        or not isinstance(terminal.get("adapter"), Mapping)
        or terminal.get("inference_runtime_sha256") != runtime_contract_sha
    ):
        raise ContractError("passing training evidence is absent or stale")
    adapter_record = terminal["adapter"]
    metadata_path = paths["adapter"] / str(adapter_record.get("metadata_filename"))
    metadata = read_json_object(metadata_path, root=paths["adapter"])
    if file_record(metadata_path, root=paths["adapter"])["sha256"] != adapter_record.get("metadata_sha256"):
        raise ContractError("adapter metadata hash binding failed")
    metadata = validate_adapter_metadata(metadata)
    if metadata["inference"]["runtime_contract_sha256"] != runtime_contract_sha:
        raise ContractError("adapter inference-runtime binding is stale")
    if adapter_record != {
        **metadata["adapter"],
        "metadata_filename": metadata_path.name,
        "metadata_sha256": adapter_record["metadata_sha256"],
    }:
        raise ContractError("training terminal and adapter metadata disagree")
    adapter_path = paths["adapter"] / str(adapter_record.get("filename"))
    validate_adapter_file(adapter_path, metadata, root=paths["adapter"])
    control = build_control_workflow(metadata=metadata, prompt=BENCHMARK_PROMPT)
    lora = build_inference_workflow(metadata=metadata, prompt=BENCHMARK_PROMPT)
    lease_owned = os.environ.get(ACTIVITY_LEASE_ENV) is None
    lease_sha = (
        _acquire_activity(paths, job_id)
        if lease_owned
        else validate_gateway_activity_lease(paths, job_id, activity="benchmark")
    )
    lease_held = True
    attempt_written = False
    completed_arms = 0
    try:
        _require_idle(api_json("GET", "/queue"))
        object_info = api_json("GET", "/object_info")
        validate_control_workflow(control, metadata, object_info)
        validate_inference_workflow(lora, metadata, object_info)
        object_info_sha = write_json_new(
            output_root / "object-info.json", object_info, root=paths["root"]
        )
        control_workflow_sha = write_json_new(
            output_root / "control-workflow.json", control, root=paths["root"]
        )
        lora_workflow_sha = write_json_new(
            output_root / "lora-workflow.json", lora, root=paths["root"]
        )
        attempt = {
            "schema_version": 1,
            "contract": BENCHMARK_CONTRACT,
            "job_id": job_id,
            "candidate_sha256": candidate_sha,
            "manifest_sha256": api_manifest["sha256"],
            "training_terminal_sha256": file_record(
                terminal_path, root=paths["evidence"]
            )["sha256"],
            "runtime_contract_sha256": runtime_contract_sha,
            "benchmark_activity_lease_sha256": lease_sha,
            "adapter_metadata_sha256": adapter_record["metadata_sha256"],
            "object_info_sha256": object_info_sha,
            "control_workflow_sha256": control_workflow_sha,
            "lora_workflow_sha256": lora_workflow_sha,
        }
        write_json_new(attempt_path, attempt, root=paths["root"])
        attempt_written = True
        arms = []
        for arm_name, graph, workflow_sha in (
            ("control", control, control_workflow_sha),
            ("lora", lora, lora_workflow_sha),
        ):
            live_object_info = api_json("GET", "/object_info")
            if sha256_bytes(canonical_json_bytes(live_object_info)) != object_info_sha:
                raise ContractError("ComfyUI node schema changed between benchmark arms")
            arms.append(
                _run_arm(
                    arm=arm_name,
                    graph=graph,
                    workflow_sha256=workflow_sha,
                    output_path=output_root / f"{arm_name}.png",
                    owned_root=paths["root"],
                    api_json=api_json,
                    api_bytes=api_bytes,
                    gpu_sample=gpu_sample,
                    clock=clock,
                    sleeper=sleeper,
                )
            )
            completed_arms += 1
        proof = {
            "schema_version": 1,
            "capability": CAPABILITY,
            "contract": BENCHMARK_CONTRACT,
            "state": "passed",
            "job_id": job_id,
            "candidate_sha256": candidate_sha,
            "manifest_sha256": api_manifest["sha256"],
            "training_terminal_sha256": attempt["training_terminal_sha256"],
            "runtime_contract_sha256": runtime_contract_sha,
            "benchmark_activity_lease_sha256": lease_sha,
            "adapter": {
                "filename": adapter_record["filename"],
                "sha256": adapter_record["sha256"],
                "metadata_filename": adapter_record["metadata_filename"],
                "metadata_sha256": adapter_record["metadata_sha256"],
                "tensor_count": adapter_record["tensor_count"],
                "pair_count": adapter_record["pair_count"],
                "tensor_inventory_sha256": adapter_record[
                    "tensor_inventory_sha256"
                ],
            },
            "prompt_sha256": sha256_bytes(BENCHMARK_PROMPT.encode("utf-8")),
            "object_info_sha256": object_info_sha,
            "settings": {
                "reference_count": 0,
                "seed": 0,
                "steps": 4,
                "sampler": "euler",
                "cfg": 1.0,
                "width": 1024,
                "height": 1024,
            },
            "sequence": ["control", "lora"],
            "arms": arms,
            "causality": {
                "pixel_hashes_differ": arms[0]["pixel_sha256"]
                != arms[1]["pixel_sha256"]
            },
        }
        if not proof["causality"]["pixel_hashes_differ"]:
            if lease_owned:
                _release_activity(paths, lease_sha)
            lease_held = False
            write_json_new(
                paths["evidence"] / "inference-benchmark-failed.json",
                {
                    "schema_version": 1,
                    "contract": BENCHMARK_CONTRACT,
                    "job_id": job_id,
                    "state": "failed",
                    "blocker_code": "lora_causality_not_demonstrated",
                    "benchmark_activity_lease_sha256": lease_sha,
                    "attempt_sha256": file_record(
                        attempt_path, root=paths["evidence"]
                    )["sha256"],
                    "control_output_sha256": arms[0]["output_sha256"],
                    "lora_output_sha256": arms[1]["output_sha256"],
                    "control_pixel_sha256": arms[0]["pixel_sha256"],
                    "lora_pixel_sha256": arms[1]["pixel_sha256"],
                },
                root=paths["root"],
            )
            raise _CausalityFailure(
                "LoRA causality was not demonstrated; retry is forbidden"
            )
        validate_benchmark_proof(proof)
        if lease_owned:
            _release_activity(paths, lease_sha)
        lease_held = False
        write_json_new(proof_path, proof, root=paths["root"])
        return proof
    except _CausalityFailure:
        raise
    except _SubmissionUnknown as exc:
        write_json_new(
            paths["evidence"] / "inference-benchmark-unknown.json",
            {
                "schema_version": 1,
                "contract": BENCHMARK_CONTRACT,
                "job_id": job_id,
                "state": "unknown",
                "blocker_code": "inference_benchmark_outcome_unknown",
                "benchmark_activity_lease_sha256": lease_sha,
                "attempt_sha256": file_record(
                    attempt_path, root=paths["evidence"]
                )["sha256"],
            },
            root=paths["root"],
        )
        raise ContractError(
            "inference benchmark outcome is unknown; retry is forbidden"
        ) from exc
    except Exception as exc:
        if lease_held and lease_owned:
            _release_activity(paths, lease_sha)
        lease_held = False
        if completed_arms == 0:
            try:
                if attempt_path.exists() and not attempt_path.is_symlink():
                    attempt_path.unlink()
                if output_root.is_dir() and not output_root.is_symlink():
                    for name in (
                        "object-info.json",
                        "control-workflow.json",
                        "lora-workflow.json",
                    ):
                        artifact = output_root / name
                        if artifact.exists() and not artifact.is_symlink():
                            artifact.unlink()
                    output_root.rmdir()
            except OSError as cleanup_error:
                raise ContractError(
                    "retryable benchmark preflight artifacts require reconciliation"
                ) from cleanup_error
        elif attempt_written:
            write_json_new(
                paths["evidence"] / "inference-benchmark-failed.json",
                {
                    "schema_version": 1,
                    "contract": BENCHMARK_CONTRACT,
                    "job_id": job_id,
                    "state": "failed",
                    "blocker_code": "inference_benchmark_preflight_failed",
                    "benchmark_activity_lease_sha256": lease_sha,
                    "attempt_sha256": file_record(
                        attempt_path, root=paths["evidence"]
                    )["sha256"],
                },
                root=paths["root"],
            )
        if isinstance(exc, ContractError):
            raise
        raise ContractError("inference benchmark preflight failed") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    args = parser.parse_args(argv)
    try:
        proof = run_benchmark(windows_state_root(), args.job_id)
    except ContractError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

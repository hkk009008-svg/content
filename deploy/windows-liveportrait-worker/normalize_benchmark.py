#!/usr/bin/env python3
"""Validate raw worker measurements and render deterministic release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any


EXPECTED_ROLE = "performance-liveportrait"
EXPECTED_FRAME_RATE = 25
EXPECTED_FRAME_COUNT = 200
EXPECTED_MEASURED_JOBS = 10
EXPECTED_TARGET_SAMPLE_INTERVAL_SECONDS = 0.25
EXPECTED_MAX_SAMPLE_INTERVAL_SECONDS = 3.0


class EvidenceError(ValueError):
    """Raw benchmark evidence is incomplete or internally inconsistent."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceError(f"{label} must be finite")
    return result


def _number(mapping: dict[str, Any], key: str) -> float:
    return _finite_number(mapping.get(key), key)


def _integer(mapping: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{key} must be an integer >= {minimum}")
    return value


def _string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{key} must be a non-empty string")
    return value


def _require_hash(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EvidenceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 0.000001:
        raise EvidenceError(
            f"{label} does not match the measured jobs: {actual} != {expected}"
        )


def _package_binding() -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve the copied package hashes and its pinned runtime versions."""

    package_root = Path(__file__).resolve().parent
    probe_root = package_root / "probes"
    try:
        probe_contract = json.loads(
            (probe_root / "probe.json").read_text(encoding="utf-8")
        )
        revisions = json.loads(
            (package_root / "revisions.json").read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise EvidenceError("copied package manifest is not valid JSON") from exc
    if not isinstance(probe_contract, dict) or not isinstance(revisions, dict):
        raise EvidenceError("copied package manifests must be JSON objects")
    workflow_name = probe_contract.get("workflow")
    if not isinstance(workflow_name, str) or not workflow_name:
        raise EvidenceError("copied probe workflow is invalid")
    workflow_path = (probe_root / workflow_name).resolve()
    if workflow_path.parent != probe_root.resolve():
        raise EvidenceError("copied probe workflow escapes the probe directory")

    paths = {
        "benchmark_instrument_sha256": package_root / "benchmark.py",
        "benchmark_normalizer_sha256": package_root / "normalize_benchmark.py",
        "benchmark_launcher_sha256": package_root / "Benchmark-Worker.ps1",
        "worker_supervisor_sha256": package_root / "Start-Worker.ps1",
        "preflight_instrument_sha256": package_root / "preflight.py",
        "models_manifest_sha256": package_root / "models.json",
        "revisions_manifest_sha256": package_root / "revisions.json",
        "requirements_lock_sha256": package_root / "requirements.lock",
        "probe_contract_sha256": probe_root / "probe.json",
        "workflow_base_sha256": workflow_path,
    }
    hashes = {key: _sha256_file(path) for key, path in paths.items()}
    declared_workflow_hash = _require_hash(
        probe_contract.get("workflow_sha256"), "copied probe workflow"
    )
    if hashes["workflow_base_sha256"] != declared_workflow_hash:
        raise EvidenceError("copied probe contract does not bind its workflow")

    components = revisions.get("components")
    if not isinstance(components, list) or not components:
        raise EvidenceError("copied revision manifest components are invalid")
    source_revisions: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            raise EvidenceError("copied revision manifest component is invalid")
        component_id = component.get("id")
        commit = component.get("commit")
        if (
            not isinstance(component_id, str)
            or not component_id
            or component_id in source_revisions
            or not isinstance(commit, str)
            or len(commit) != 40
            or any(character not in "0123456789abcdef" for character in commit)
        ):
            raise EvidenceError("copied revision source binding is invalid")
        source_revisions[component_id] = commit
    binding: dict[str, Any] = {**hashes, "source_revisions": source_revisions}
    binding["package_contract_sha256"] = _sha256_bytes(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )

    platform_contract = revisions.get("platform")
    package_contract = revisions.get("python_packages")
    if not isinstance(platform_contract, dict) or not isinstance(package_contract, dict):
        raise EvidenceError("copied revision runtime contract is invalid")
    expected_versions = {
        "python": _string(platform_contract, "python"),
        "torch": _string(package_contract, "torch"),
    }
    locked_versions: dict[str, str] = {}
    for line in (package_root / "requirements.lock").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "==" not in stripped or stripped.startswith("#"):
            continue
        name, version = stripped.split("==", 1)
        locked_versions[name.lower()] = version
    for package, runtime_key in (("av", "pyav"), ("psutil", "psutil")):
        version = locked_versions.get(package)
        if not version:
            raise EvidenceError(f"copied dependency lock does not pin {package}")
        expected_versions[runtime_key] = version
    return binding, expected_versions


def normalize(raw_bytes: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("raw evidence is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise EvidenceError("raw evidence must be a JSON object")

    exact = {
        "schema_version": 3,
        "status": "passed",
        "role": EXPECTED_ROLE,
        "frame_rate": EXPECTED_FRAME_RATE,
        "frame_count": EXPECTED_FRAME_COUNT,
        "measured_jobs": EXPECTED_MEASURED_JOBS,
        "warmup_jobs": 1,
        "max_concurrency": 1,
        "comfy_cache_mode": "none",
        "all_outputs_decoded": True,
    }
    for key, expected in exact.items():
        if raw.get(key) != expected:
            raise EvidenceError(f"{key} must be {expected!r}")
    started_at = _integer(raw, "started_at_unix")
    completed_at = _integer(raw, "completed_at_unix")
    if completed_at < started_at:
        raise EvidenceError("benchmark completion precedes its start")
    if _number(raw, "clip_seconds") != EXPECTED_FRAME_COUNT / EXPECTED_FRAME_RATE:
        raise EvidenceError("clip_seconds does not match frame count and rate")

    jobs = raw.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != EXPECTED_MEASURED_JOBS:
        raise EvidenceError("raw evidence must contain ten measured jobs")
    elapsed: list[float] = []
    output_hashes: list[str] = []
    for index, job in enumerate(jobs, 1):
        if not isinstance(job, dict):
            raise EvidenceError(f"measured job {index} is not an object")
        if job.get("label") != f"measured-{index:02d}":
            raise EvidenceError(f"measured job {index} label is out of sequence")
        if job.get("decoded_frames") != EXPECTED_FRAME_COUNT:
            raise EvidenceError(f"measured job {index} did not decode every frame")
        if _integer(job, "output_bytes", minimum=1025) <= 1024:
            raise EvidenceError(f"measured job {index} output is not a real artifact")
        job_elapsed = _number(job, "elapsed_seconds")
        if job_elapsed <= 0:
            raise EvidenceError(f"measured job {index} latency must be positive")
        elapsed.append(job_elapsed)
        output_hashes.append(_require_hash(job.get("output_sha256"), f"job {index} output"))

    warmup = raw.get("warmup")
    if (
        not isinstance(warmup, dict)
        or warmup.get("label") != "warmup"
        or warmup.get("decoded_frames") != EXPECTED_FRAME_COUNT
    ):
        raise EvidenceError("warm-up job is incomplete")
    if _integer(warmup, "output_bytes", minimum=1025) <= 1024:
        raise EvidenceError("warm-up output is not a real artifact")
    _require_hash(warmup.get("output_sha256"), "warm-up output")
    warmup_elapsed = _number(warmup, "elapsed_seconds")
    if warmup_elapsed <= 0:
        raise EvidenceError("warm-up latency must be positive")

    recorded_latency = raw.get("latency_seconds")
    if not isinstance(recorded_latency, dict):
        raise EvidenceError("latency_seconds is missing")
    expected_latency = {
        "minimum": round(min(elapsed), 6),
        "maximum": round(max(elapsed), 6),
        "mean": round(statistics.fmean(elapsed), 6),
        "p50": round(statistics.median(elapsed), 6),
        "p95_inclusive": round(
            statistics.quantiles(elapsed, n=100, method="inclusive")[94], 6
        ),
    }
    for key, expected in expected_latency.items():
        _assert_close(_number(recorded_latency, key), expected, f"latency {key}")

    resources = raw.get("resources")
    if not isinstance(resources, dict):
        raise EvidenceError("resources is missing")
    normalized_resources: dict[str, Any] = {}
    for prefix in ("vram_mib", "worker_rss_bytes", "system_ram_bytes"):
        minimum = 1 if prefix == "worker_rss_bytes" else 0
        baseline = _integer(resources, f"baseline_{prefix}", minimum=minimum)
        peak = _integer(resources, f"peak_{prefix}", minimum=minimum)
        delta = _integer(resources, f"delta_{prefix}")
        if peak < baseline:
            raise EvidenceError(f"resource envelope for {prefix} is invalid")
        _assert_close(delta, peak - baseline, f"resource delta {prefix}")
        normalized_resources[f"baseline_{prefix}"] = baseline
        normalized_resources[f"peak_{prefix}"] = peak
        normalized_resources[f"delta_{prefix}"] = delta
    target_interval = _number(resources, "target_sample_interval_seconds")
    _assert_close(
        target_interval,
        EXPECTED_TARGET_SAMPLE_INTERVAL_SECONDS,
        "resource target sample interval",
    )
    max_accepted_interval = _number(
        resources, "max_accepted_sample_interval_seconds"
    )
    _assert_close(
        max_accepted_interval,
        EXPECTED_MAX_SAMPLE_INTERVAL_SECONDS,
        "resource maximum accepted sample interval",
    )
    sample_count = _integer(resources, "sample_count", minimum=3)
    if sample_count < 3:
        raise EvidenceError("resource sample count is incomplete")
    offsets = resources.get("sample_offsets_seconds")
    if not isinstance(offsets, list) or len(offsets) != sample_count:
        raise EvidenceError("resource sample offsets are incomplete or non-monotonic")
    normalized_offsets = [
        _finite_number(value, f"resource sample offset {index}")
        for index, value in enumerate(offsets)
    ]
    if (
        normalized_offsets[0] < 0
        or normalized_offsets[0] > max_accepted_interval
        or any(
            current <= previous
            for previous, current in zip(normalized_offsets, normalized_offsets[1:])
        )
    ):
        raise EvidenceError("resource sample offsets are incomplete or non-monotonic")
    sampling_elapsed = _number(resources, "sampling_elapsed_seconds")
    _assert_close(
        sampling_elapsed,
        normalized_offsets[-1],
        "resource sampling elapsed seconds",
    )
    total_job_seconds = warmup_elapsed + sum(elapsed)
    if sampling_elapsed < total_job_seconds:
        raise EvidenceError("resource sampling does not cover every benchmark job")
    observed_intervals = resources.get("observed_sample_interval_seconds")
    if not isinstance(observed_intervals, dict):
        raise EvidenceError("observed resource sample intervals are missing")
    intervals = [
        current - previous
        for previous, current in zip(normalized_offsets, normalized_offsets[1:])
    ]
    if max(intervals) > max_accepted_interval + 0.000001:
        raise EvidenceError("resource sampling schedule contains an unobserved gap")
    minimum_sample_count = (
        math.ceil(
            (sampling_elapsed - normalized_offsets[0]) / max_accepted_interval
        )
        + 1
    )
    if sample_count < minimum_sample_count:
        raise EvidenceError("resource sampling schedule is too sparse")
    expected_intervals = {
        "minimum": round(min(intervals), 6),
        "maximum": round(max(intervals), 6),
        "mean": round(statistics.fmean(intervals), 6),
        "p50": round(statistics.median(intervals), 6),
        "p95_inclusive": round(
            statistics.quantiles(intervals, n=100, method="inclusive")[94], 6
        ),
    }
    for key, expected in expected_intervals.items():
        _assert_close(
            _number(observed_intervals, key),
            expected,
            f"observed sample interval {key}",
        )
    normalized_resources.update(
        {
            "target_sample_interval_seconds": target_interval,
            "max_accepted_sample_interval_seconds": max_accepted_interval,
            "sample_count": sample_count,
            "sample_offsets_seconds": normalized_offsets,
            "sampling_elapsed_seconds": sampling_elapsed,
            "observed_sample_interval_seconds": expected_intervals,
        }
    )

    hardware = raw.get("hardware")
    runtime = raw.get("runtime")
    if not isinstance(hardware, dict) or not isinstance(runtime, dict):
        raise EvidenceError("instrument-recorded hardware and runtime are required")
    normalized_hardware = {
        "gpu": _string(hardware, "gpu"),
        "vram_total_mib": _integer(hardware, "vram_total_mib", minimum=1),
        "cpu": _string(hardware, "cpu"),
        "system_ram_bytes": _integer(hardware, "system_ram_bytes", minimum=1),
        "operating_system": _string(hardware, "operating_system"),
    }
    if normalized_resources["peak_vram_mib"] > normalized_hardware["vram_total_mib"]:
        raise EvidenceError("peak VRAM exceeds recorded device capacity")
    if (
        normalized_resources["peak_system_ram_bytes"]
        > normalized_hardware["system_ram_bytes"]
    ):
        raise EvidenceError("peak system RAM exceeds recorded host capacity")

    expected_binding, expected_versions = _package_binding()
    normalized_runtime = {
        key: _string(runtime, key) for key in ("python", "torch", "pyav", "psutil")
    }
    python_parts = normalized_runtime["python"].split(".")
    if ".".join(python_parts[:2]) != expected_versions["python"]:
        raise EvidenceError("runtime Python does not match the copied revision contract")
    for key in ("torch", "pyav", "psutil"):
        if normalized_runtime[key] != expected_versions[key]:
            raise EvidenceError(f"runtime {key} does not match the copied package")
    for key, expected in expected_binding.items():
        actual = runtime.get(key)
        if actual != expected:
            raise EvidenceError(f"runtime {key} does not match the copied package")
        normalized_runtime[key] = expected
    top_workflow_hash = _require_hash(
        raw.get("workflow_base_sha256"), "benchmark workflow"
    )
    top_driver_hash = _require_hash(raw.get("driver_sha256"), "benchmark driver")
    if top_workflow_hash != expected_binding["workflow_base_sha256"]:
        raise EvidenceError("benchmark workflow is not bound to the copied package")
    if runtime.get("driver_sha256") != top_driver_hash:
        raise EvidenceError("benchmark driver hashes are inconsistent")
    normalized_runtime["driver_sha256"] = top_driver_hash

    restart = raw.get("restart_recovery")
    if not isinstance(restart, dict) or restart.get("state") != "passed":
        raise EvidenceError("clean restart recovery did not pass")
    restart_checked_at = _integer(restart, "checked_at_unix")
    if restart_checked_at < completed_at:
        raise EvidenceError("restart recovery predates benchmark completion")

    return {
        "schema_version": 2,
        "status": "passed",
        "raw_evidence_sha256": _sha256_bytes(raw_bytes),
        "started_at_unix": started_at,
        "completed_at_unix": completed_at,
        "hardware": normalized_hardware,
        "runtime": normalized_runtime,
        "workload": {
            "clip_seconds": raw["clip_seconds"],
            "frame_count": raw["frame_count"],
            "frame_rate": raw["frame_rate"],
            "warmup_jobs": raw["warmup_jobs"],
            "measured_jobs": raw["measured_jobs"],
            "max_concurrency": raw["max_concurrency"],
            "all_outputs_decoded": raw["all_outputs_decoded"],
            "comfy_cache_mode": raw["comfy_cache_mode"],
        },
        "latency_seconds": expected_latency,
        "resources": normalized_resources,
        "measured_output_sha256": output_hashes,
        "restart_recovery": {
            "state": "passed",
            "checked_at_unix": restart_checked_at,
        },
        "decision": {
            "queue_concurrency": 1,
            "reason": (
                "Keep deterministic single-job scheduling; measured headroom "
                "does not authorize parallel production jobs."
            ),
        },
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        rendered = render(normalize(args.raw.read_bytes()))
    except (OSError, EvidenceError) as exc:
        print(f"BENCHMARK EVIDENCE REFUSED: {exc}", file=__import__("sys").stderr)
        return 1
    if args.check:
        try:
            current = args.output.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"BENCHMARK EVIDENCE REFUSED: {exc}", file=__import__("sys").stderr)
            return 1
        if current != rendered:
            print("BENCHMARK EVIDENCE STALE", file=__import__("sys").stderr)
            return 1
        print("BENCHMARK_EVIDENCE_OK")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(args.output)
    print("BENCHMARK_EVIDENCE_NORMALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

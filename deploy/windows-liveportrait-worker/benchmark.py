#!/usr/bin/env python3
"""Sequential RTX worker benchmark with decoded-output and resource evidence."""

from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

import av
import psutil
import torch

from preflight import (
    PreflightError,
    api_json,
    cleanup_owned_outputs,
    load_json,
    validate_video_container,
)


FRAME_RATE = 25
CLIP_SECONDS = 8
FRAME_COUNT = FRAME_RATE * CLIP_SECONDS
MEASURED_JOBS = 10
WORKER_ROLE = "performance-liveportrait"
MAX_OBSERVED_SAMPLE_INTERVAL_SECONDS = 3.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_runtime_binding(package_root: Path) -> dict[str, Any]:
    """Bind raw evidence to the exact copied instrument and source manifests."""

    package_root = package_root.resolve()
    probe_root = package_root / "probes"
    probe_contract = load_json(probe_root / "probe.json", "package probe contract")
    workflow_name = probe_contract.get("workflow")
    if not isinstance(workflow_name, str) or not workflow_name:
        raise PreflightError("package probe workflow is invalid")
    workflow_path = (probe_root / workflow_name).resolve()
    if workflow_path.parent != probe_root.resolve():
        raise PreflightError("package probe workflow escapes the probe directory")
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
    hashes = {key: sha256_file(path) for key, path in paths.items()}
    if probe_contract.get("workflow_sha256") != hashes["workflow_base_sha256"]:
        raise PreflightError("package probe contract does not bind its workflow")
    revisions = load_json(package_root / "revisions.json", "revision manifest")
    components = revisions.get("components")
    if not isinstance(components, list):
        raise PreflightError("revision manifest components are invalid")
    source_revisions: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            raise PreflightError("revision manifest component is invalid")
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
            raise PreflightError("revision manifest source binding is invalid")
        source_revisions[component_id] = commit
    binding: dict[str, Any] = {**hashes, "source_revisions": source_revisions}
    binding["package_contract_sha256"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return binding


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def create_driver(source: Path, destination: Path) -> str:
    with av.open(str(source), mode="r") as container:
        frame = next(container.decode(video=0), None)
    if frame is None:
        raise PreflightError("benchmark source driver has no decodable frame")
    pixels = frame.to_ndarray(format="rgb24")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        with av.open(str(temporary), mode="w", format="mp4") as container:
            stream = container.add_stream("mpeg4", rate=FRAME_RATE)
            stream.width = frame.width
            stream.height = frame.height
            stream.pix_fmt = "yuv420p"
            for index in range(FRAME_COUNT):
                # Do not reuse the decoded fixture frame: its original stream
                # timestamp/time-base is invalid for this new 25 fps encoder.
                repeated = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                repeated.pts = index
                repeated.time_base = Fraction(1, FRAME_RATE)
                for packet in stream.encode(repeated):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    validate_video_container(destination, expected_frames=FRAME_COUNT)
    return sha256_file(destination)


def worker_rss_bytes(
    supervisor_pid: int,
    comfy_root: Path,
    expected_python: Path,
) -> int:
    """Measure the one ComfyUI descendant of the bound launch supervisor."""

    marker = str((comfy_root / "main.py").resolve()).replace("\\", "/").casefold()
    python_marker = str(expected_python.resolve()).replace("\\", "/").casefold()
    try:
        supervisor = psutil.Process(supervisor_pid)
        descendants = supervisor.children(recursive=True)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess) as exc:
        raise PreflightError("bound ComfyUI launch supervisor is unavailable") from exc

    candidates = []
    for process in descendants:
        try:
            command = " ".join(process.cmdline()).replace("\\", "/").casefold()
            executable = str(Path(process.exe()).resolve()).replace("\\", "/").casefold()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied as exc:
            raise PreflightError(
                "bound worker descendant identity is not inspectable"
            ) from exc
        if marker in command and executable == python_marker:
            candidates.append(process)
    if len(candidates) != 1:
        raise PreflightError(
            "bound supervisor does not own exactly one expected ComfyUI process"
        )

    worker = candidates[0]
    try:
        worker_tree = [worker, *worker.children(recursive=True)]
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess) as exc:
        raise PreflightError("bound ComfyUI worker process is unavailable") from exc
    seen: set[int] = set()
    total = 0
    for process in worker_tree:
        if process.pid in seen:
            continue
        seen.add(process.pid)
        try:
            total += process.memory_info().rss
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied as exc:
            raise PreflightError("bound ComfyUI worker RSS is not inspectable") from exc
    if total <= 0:
        raise PreflightError("bound ComfyUI worker RSS is unavailable")
    return total


def gpu_memory_mib() -> int:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
            "--id=0",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode:
        raise PreflightError(
            "nvidia-smi memory query failed: "
            + (completed.stderr or completed.stdout).strip()
        )
    first = completed.stdout.strip().splitlines()[0].strip()
    return int(first)


def hardware_identity() -> dict[str, Any]:
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
            "--id=0",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if gpu.returncode:
        raise PreflightError(
            "nvidia-smi identity query failed: "
            + (gpu.stderr or gpu.stdout).strip()
        )
    fields = [part.strip() for part in gpu.stdout.strip().splitlines()[0].rsplit(",", 1)]
    if len(fields) != 2 or not fields[0]:
        raise PreflightError("nvidia-smi identity response is invalid")
    try:
        total_vram_mib = int(fields[1])
    except ValueError as exc:
        raise PreflightError("nvidia-smi total VRAM response is invalid") from exc

    cpu = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name).Trim()",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    cpu_name = cpu.stdout.strip() if cpu.returncode == 0 else ""
    if not cpu_name:
        raise PreflightError("Windows CPU identity query failed")
    return {
        "gpu": fields[0],
        "vram_total_mib": total_vram_mib,
        "cpu": cpu_name,
        "system_ram_bytes": int(psutil.virtual_memory().total),
        "operating_system": platform.platform(),
    }


class ResourceSampler:
    def __init__(
        self,
        comfy_root: Path,
        worker_supervisor_pid: int,
        expected_python: Path,
    ) -> None:
        self.comfy_root = comfy_root
        self.worker_supervisor_pid = worker_supervisor_pid
        self.expected_python = expected_python
        self.stop_event = threading.Event()
        self.error: str | None = None
        self.samples = 0
        self.peak_vram_mib = 0
        self.peak_worker_rss_bytes = 0
        self.peak_system_ram_bytes = 0
        self.baseline_vram_mib = 0
        self.baseline_worker_rss_bytes = 0
        self.baseline_system_ram_bytes = 0
        self.started_monotonic = 0.0
        self.sample_offsets_seconds: list[float] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _sample(self) -> tuple[int, int, int]:
        return (
            gpu_memory_mib(),
            worker_rss_bytes(
                self.worker_supervisor_pid,
                self.comfy_root,
                self.expected_python,
            ),
            int(psutil.virtual_memory().used),
        )

    def start(self) -> None:
        self.started_monotonic = time.monotonic()
        baseline = self._sample()
        (
            self.baseline_vram_mib,
            self.baseline_worker_rss_bytes,
            self.baseline_system_ram_bytes,
        ) = baseline
        self.peak_vram_mib = baseline[0]
        self.peak_worker_rss_bytes = baseline[1]
        self.peak_system_ram_bytes = baseline[2]
        self.samples = 1
        self.sample_offsets_seconds = [
            round(time.monotonic() - self.started_monotonic, 6)
        ]
        self.thread.start()

    def _record(self, sample: tuple[int, int, int]) -> None:
        vram, worker_rss, system_ram = sample
        self.peak_vram_mib = max(self.peak_vram_mib, vram)
        self.peak_worker_rss_bytes = max(self.peak_worker_rss_bytes, worker_rss)
        self.peak_system_ram_bytes = max(self.peak_system_ram_bytes, system_ram)
        self.samples += 1
        self.sample_offsets_seconds.append(
            round(time.monotonic() - self.started_monotonic, 6)
        )

    def _run(self) -> None:
        while not self.stop_event.wait(0.25):
            try:
                self._record(self._sample())
            except Exception as exc:  # evidence must report sampler failure
                self.error = str(exc)
                self.stop_event.set()

    def stop(self) -> dict[str, Any]:
        self.stop_event.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise PreflightError("resource sampler did not stop")
        if self.error:
            raise PreflightError(f"resource sampler failed: {self.error}")
        self._record(self._sample())
        intervals = [
            current - previous
            for previous, current in zip(
                self.sample_offsets_seconds,
                self.sample_offsets_seconds[1:],
            )
        ]
        return {
            "target_sample_interval_seconds": 0.25,
            "max_accepted_sample_interval_seconds": (
                MAX_OBSERVED_SAMPLE_INTERVAL_SECONDS
            ),
            "sample_count": self.samples,
            "sample_offsets_seconds": self.sample_offsets_seconds,
            "sampling_elapsed_seconds": self.sample_offsets_seconds[-1],
            "observed_sample_interval_seconds": {
                "minimum": round(min(intervals), 6),
                "maximum": round(max(intervals), 6),
                "mean": round(statistics.fmean(intervals), 6),
                "p50": round(statistics.median(intervals), 6),
                "p95_inclusive": round(percentile_95_inclusive(intervals), 6),
            },
            "baseline_vram_mib": self.baseline_vram_mib,
            "peak_vram_mib": self.peak_vram_mib,
            "delta_vram_mib": self.peak_vram_mib - self.baseline_vram_mib,
            "baseline_worker_rss_bytes": self.baseline_worker_rss_bytes,
            "peak_worker_rss_bytes": self.peak_worker_rss_bytes,
            "delta_worker_rss_bytes": (
                self.peak_worker_rss_bytes - self.baseline_worker_rss_bytes
            ),
            "baseline_system_ram_bytes": self.baseline_system_ram_bytes,
            "peak_system_ram_bytes": self.peak_system_ram_bytes,
            "delta_system_ram_bytes": (
                self.peak_system_ram_bytes - self.baseline_system_ram_bytes
            ),
        }


def assert_queue_idle(base_url: str) -> None:
    queue = api_json(base_url, "/queue", timeout=15)
    running = queue.get("queue_running")
    pending = queue.get("queue_pending")
    if not isinstance(running, list) or not isinstance(pending, list):
        raise PreflightError("ComfyUI queue response is invalid")
    if running or pending:
        raise PreflightError("benchmark requires an idle queue and concurrency=1")


def output_artifact(
    history: dict[str, Any], output_root: Path, *, expected_prefix: str
) -> Path:
    outputs = history.get("outputs")
    node = outputs.get("19") if isinstance(outputs, dict) else None
    candidates: list[Path] = []
    if isinstance(node, dict):
        for collection in node.values():
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
                    continue
                subfolder = item.get("subfolder", "")
                if not isinstance(subfolder, str):
                    continue
                candidate = (output_root / subfolder / item["filename"]).resolve()
                if output_root.resolve() not in candidate.parents:
                    raise PreflightError("benchmark output escaped the worker output root")
                if candidate.suffix.lower() == ".mp4" and candidate.is_file():
                    candidates.append(candidate)
    if len(candidates) != 1 or not candidates[0].name.startswith(expected_prefix):
        raise PreflightError("benchmark job did not produce its one expected MP4")
    validate_video_container(candidates[0], expected_frames=FRAME_COUNT)
    return candidates[0]


def execute_job(
    base_url: str,
    workflow: dict[str, Any],
    output_root: Path,
    *,
    run_prefix: str,
    label: str,
    timeout: int = 900,
) -> tuple[dict[str, Any], Path]:
    assert_queue_idle(base_url)
    graph = copy.deepcopy(workflow)
    prefix = f"{run_prefix}-{label}"
    graph["19"]["inputs"]["filename_prefix"] = prefix
    started = time.monotonic()
    submitted = api_json(
        base_url,
        "/prompt",
        method="POST",
        payload={"prompt": graph, "client_id": str(uuid.uuid4())},
        timeout=30,
    )
    prompt_id = submitted.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise PreflightError(f"benchmark prompt was rejected: {submitted.get('error')}")
    deadline = time.monotonic() + timeout
    history: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = api_json(base_url, f"/history/{prompt_id}", timeout=15)
        candidate = response.get(prompt_id)
        if isinstance(candidate, dict):
            history = candidate
            break
        time.sleep(0.25)
    elapsed = time.monotonic() - started
    if history is None:
        raise PreflightError(f"benchmark job {label} timed out")
    status = history.get("status")
    if not isinstance(status, dict) or status.get("completed") is not True:
        raise PreflightError(f"benchmark job {label} did not complete")
    artifact = output_artifact(history, output_root, expected_prefix=prefix)
    result = {
        "label": label,
        "prompt_id": prompt_id,
        "elapsed_seconds": round(elapsed, 6),
        "output_bytes": artifact.stat().st_size,
        "output_sha256": sha256_file(artifact),
        "decoded_frames": FRAME_COUNT,
    }
    return result, artifact


def percentile_95_inclusive(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--worker-supervisor-pid", type=int, required=True)
    args = parser.parse_args()

    install_root = args.install_root.resolve()
    comfy_root = install_root / "sources" / "ComfyUI"
    input_root = install_root / "input"
    output_root = install_root / "output"
    contract_path = install_root / "probes" / "probe.json"
    contract = load_json(contract_path, "probe contract")
    workflow_path = install_root / "probes" / str(contract.get("workflow"))
    workflow = load_json(workflow_path, "probe workflow")
    package_root = install_root / "package"
    driver_path = input_root / "benchmark-driving-200f.mp4"
    run_prefix = f"worker-benchmark-{uuid.uuid4().hex}"
    if args.worker_supervisor_pid <= 0:
        raise PreflightError("worker supervisor PID must be positive")
    sampler = ResourceSampler(
        comfy_root,
        args.worker_supervisor_pid,
        Path(sys.executable),
    )
    result: dict[str, Any] = {
        "schema_version": 3,
        "status": "running",
        "role": WORKER_ROLE,
        "started_at_unix": int(time.time()),
        "frame_count": FRAME_COUNT,
        "frame_rate": FRAME_RATE,
        "clip_seconds": FRAME_COUNT / FRAME_RATE,
        "warmup_jobs": 1,
        "measured_jobs": MEASURED_JOBS,
        "max_concurrency": 1,
        "comfy_cache_mode": "none",
        "restart_recovery": {"state": "pending"},
        "hardware": hardware_identity(),
        "runtime": {
            "python": platform.python_version(),
            "python_executable": str(Path(sys.executable).resolve()),
            "torch": torch.__version__,
            "pyav": av.__version__,
            "psutil": psutil.__version__,
            **package_runtime_binding(package_root),
        },
    }
    write_json_atomic(args.result, result)
    try:
        driver_hash = create_driver(input_root / "driving-expression.mp4", driver_path)
        workflow["11"]["inputs"].update(
            {
                "video": driver_path.name,
                "force_rate": FRAME_RATE,
                "frame_load_cap": FRAME_COUNT,
                "select_every_nth": 1,
                "skip_first_frames": 0,
            }
        )
        workflow["19"]["inputs"]["frame_rate"] = FRAME_RATE
        result["driver_sha256"] = driver_hash
        result["workflow_base_sha256"] = sha256_file(workflow_path)
        if result["runtime"]["workflow_base_sha256"] != result["workflow_base_sha256"]:
            raise PreflightError("installed probe workflow differs from the copied package")
        result["runtime"]["driver_sha256"] = driver_hash

        sampler.start()
        warmup, warmup_artifact = execute_job(
            args.comfy_url,
            workflow,
            output_root,
            run_prefix=run_prefix,
            label="warmup",
        )
        del warmup_artifact
        measured: list[dict[str, Any]] = []
        for index in range(1, MEASURED_JOBS + 1):
            job, artifact = execute_job(
                args.comfy_url,
                workflow,
                output_root,
                run_prefix=run_prefix,
                label=f"measured-{index:02d}",
            )
            measured.append(job)
            del artifact
            write_json_atomic(args.result, {**result, "warmup": warmup, "jobs": measured})
        resources = sampler.stop()
        elapsed = [float(job["elapsed_seconds"]) for job in measured]
        result.update(
            {
                "status": "benchmark_passed_restart_pending",
                "completed_at_unix": int(time.time()),
                "warmup": warmup,
                "jobs": measured,
                "latency_seconds": {
                    "minimum": round(min(elapsed), 6),
                    "maximum": round(max(elapsed), 6),
                    "mean": round(statistics.fmean(elapsed), 6),
                    "p50": round(statistics.median(elapsed), 6),
                    "p95_inclusive": round(percentile_95_inclusive(elapsed), 6),
                },
                "resources": resources,
                "all_outputs_decoded": True,
            }
        )
        write_json_atomic(args.result, result)
    except Exception as exc:
        if sampler.thread.is_alive():
            sampler.stop_event.set()
            sampler.thread.join(timeout=15)
        result.update(
            {
                "status": "failed",
                "completed_at_unix": int(time.time()),
                "error": str(exc),
            }
        )
        write_json_atomic(args.result, result)
        raise
    finally:
        driver_path.unlink(missing_ok=True)
        cleanup_owned_outputs(output_root, run_prefix)


if __name__ == "__main__":
    try:
        main()
    except PreflightError as exc:
        print(f"BENCHMARK FAILED: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)

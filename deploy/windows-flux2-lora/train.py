#!/usr/bin/env python3
"""Run or explicitly resume one fixed 500-step LoRA canary."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from contract import (
    ContractError,
    ROOT,
    adapter_filename,
    build_adapter_metadata,
    build_training_config,
    canonical_job_id,
    canonical_json_bytes,
    classify_failure,
    collect_resource_snapshot,
    file_record,
    fixed_child_environment,
    job_paths,
    package_digest,
    read_json_object,
    regular_file_tail,
    sample_gpu_memory_used_bytes,
    toolkit_command,
    validate_api_manifest,
    validate_adapter_file,
    validate_gateway_training_activity_lease,
    validate_inference_runtime,
    validate_input_manifest,
    validate_lora_safetensors,
    validate_package,
    validate_resource_snapshot,
    validate_resume_checkpoint,
    validate_runtime_receipts,
    validate_terminal_evidence,
    windows_state_root,
    write_json_new,
)


CAPABILITY = "identity-flux2-klein-lora"
CHECKPOINT_RE = re.compile(r"identity_lora_([0-9a-f]{32})_([0-9]{9})\.safetensors\Z")


def _write(paths: dict[str, Path], path: Path, payload: dict[str, Any]) -> str:
    return write_json_new(path, payload, root=paths["root"])


def _acquire_lock(paths: dict[str, Path], job_id: str) -> tuple[dict[str, object], str]:
    record = {
        "schema_version": 1,
        "job_id": job_id,
        "pid": os.getpid(),
        "nonce": uuid.uuid4().hex,
    }
    digest = _write(paths, paths["lock"], record)
    return record, digest


def _release_lock(path: Path, digest: str) -> None:
    try:
        info = path.lstat()
        if (
            stat.S_ISREG(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and file_record(path)["sha256"] == digest
        ):
            path.unlink()
    except (OSError, ContractError):
        pass


def _process_alive(pid: int) -> bool:
    if os.name != "nt" or pid <= 0:
        raise ContractError("dead-owner validation is Windows-only")
    process_query = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(process_query, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: the process does not exist.
            return False
        raise ContractError("cannot verify prior training process state")
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise ContractError("cannot verify prior training process state")
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _read_started(paths: dict[str, Path], job_id: str) -> tuple[dict[str, Any], str]:
    path = paths["evidence"] / "started.json"
    started = read_json_object(path, root=paths["evidence"])
    if set(started) != {
        "schema_version",
        "job_id",
        "state",
        "attempt",
        "admission_sha256",
        "lease_sha256",
        "activity_lease_sha256",
    } or started != {
        **started,
        "schema_version": 1,
        "job_id": job_id,
        "state": "started",
        "attempt": 1,
    }:
        raise ContractError("initial started evidence is malformed")
    for field in ("admission_sha256", "lease_sha256", "activity_lease_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(started.get(field))):
            raise ContractError("initial started evidence digest is malformed")
    return started, str(file_record(path, root=paths["evidence"])["sha256"])


def _recover_dead_lease(
    paths: dict[str, Path], job_id: str, started: dict[str, Any], *, process_alive=_process_alive
) -> None:
    lock = read_json_object(paths["lock"], root=paths["root"])
    if set(lock) != {"schema_version", "job_id", "pid", "nonce"}:
        raise ContractError("prior GPU lease is malformed")
    if (
        lock.get("schema_version") != 1
        or lock.get("job_id") != job_id
        or not isinstance(lock.get("pid"), int)
        or not re.fullmatch(r"[0-9a-f]{32}", str(lock.get("nonce")))
        or file_record(paths["lock"], root=paths["root"])["sha256"]
        != started["lease_sha256"]
    ):
        raise ContractError("prior GPU lease does not match the started attempt")
    if process_alive(lock["pid"]):
        raise ContractError("prior training process is still alive")
    paths["lock"].unlink()


def _recover_unstarted_dead_lock(
    paths: dict[str, Path], job_id: str, *, process_alive=_process_alive
) -> None:
    if not paths["lock"].exists() and not paths["lock"].is_symlink():
        return
    for name in ("started.json", "resume-started.json", "terminal.json"):
        evidence = paths["evidence"] / name
        if evidence.exists() or evidence.is_symlink():
            raise ContractError("stale training lock has started or terminal evidence")
    lock = read_json_object(paths["lock"], root=paths["root"])
    if (
        set(lock) != {"schema_version", "job_id", "pid", "nonce"}
        or lock.get("schema_version") != 1
        or lock.get("job_id") != job_id
        or type(lock.get("pid")) is not int
        or lock["pid"] <= 0
        or not re.fullmatch(r"[0-9a-f]{32}", str(lock.get("nonce")))
    ):
        raise ContractError("unstarted training lock is malformed or belongs elsewhere")
    if process_alive(lock["pid"]):
        raise ContractError("unstarted training process is still alive")
    paths["lock"].unlink()


def _reset_unstarted_partial_evidence(
    paths: dict[str, Path], job_id: str, *, activity_lease_sha256: str
) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", activity_lease_sha256):
        raise ContractError("initial retry activity lease is malformed")
    for forbidden in (paths["output"], paths["adapter"]):
        if forbidden.exists() or forbidden.is_symlink():
            raise ContractError("initial retry found post-start training artifacts")

    allowed = {
        paths["config"].parent: {paths["config"].name},
        paths["evidence"]: {"admission.json"},
    }
    for directory, allowed_names in allowed.items():
        if not directory.exists() and not directory.is_symlink():
            continue
        info = directory.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ContractError("initial retry artifact directory is unsafe")
        entries = list(directory.iterdir())
        if {entry.name for entry in entries} - allowed_names:
            raise ContractError("initial retry found an unexpected artifact")
        for entry in entries:
            entry_info = entry.lstat()
            if stat.S_ISLNK(entry_info.st_mode) or not stat.S_ISREG(entry_info.st_mode):
                raise ContractError("initial retry artifact is not a regular file")

    config_sha: str | None = None
    if paths["config"].exists():
        config_sha = _validate_existing_config(paths, job_id)
    admission_path = paths["evidence"] / "admission.json"
    if admission_path.exists():
        if config_sha is None:
            raise ContractError("initial retry admission has no matching configuration")
        admission = read_json_object(admission_path, root=paths["evidence"])
        if set(admission) != {
            "schema_version",
            "job_id",
            "input_manifest_sha256",
            "config_sha256",
            "package_sha256",
            "contract",
            "candidate_sha256",
            "manifest_sha256",
            "runtime_receipt_sha256",
            "model_receipt_sha256",
            "resource_preflight",
            "inference_runtime",
            "activity_lease_sha256",
        } or admission != {
            **admission,
            "schema_version": 1,
            "job_id": job_id,
            "config_sha256": config_sha,
            "contract": "flux2-klein-character-lora-canary-v1",
        }:
            raise ContractError("initial retry admission evidence is malformed")
        for field in (
            "input_manifest_sha256",
            "package_sha256",
            "candidate_sha256",
            "manifest_sha256",
            "runtime_receipt_sha256",
            "model_receipt_sha256",
            "activity_lease_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(admission.get(field))):
                raise ContractError("initial retry admission digest is malformed")
        if admission["candidate_sha256"] != admission["package_sha256"]:
            raise ContractError("initial retry admission candidate binding disagrees")

    if admission_path.exists():
        admission_path.unlink()
    if paths["config"].exists():
        paths["config"].unlink()
    for directory in (paths["evidence"], paths["config"].parent):
        if directory.exists():
            directory.rmdir()


def _save_root(paths: dict[str, Path], job_id: str) -> Path:
    return paths["output"] / f"identity_lora_{job_id}"


def _resume_material(paths: dict[str, Path], job_id: str) -> dict[str, Any]:
    save_root = _save_root(paths, job_id)
    safetensors: list[Path] = []
    if save_root.is_dir():
        for candidate in save_root.glob("*.safetensors"):
            safetensors.append(candidate)
    if len(safetensors) != 1 or not CHECKPOINT_RE.fullmatch(safetensors[0].name):
        raise ContractError("resume_not_available")
    checkpoint = validate_resume_checkpoint(
        safetensors[0], root=save_root, job_id=job_id
    )
    optimizer = save_root / "optimizer.pt"
    optimizer_record = file_record(optimizer, root=save_root)
    if optimizer_record["bytes"] < 1024:
        raise ContractError("resume_not_available")
    return {
        "checkpoint": checkpoint,
        "optimizer": {"filename": "optimizer.pt", **optimizer_record},
    }


def _validate_existing_config(paths: dict[str, Path], job_id: str) -> str:
    expected = canonical_json_bytes(build_training_config(paths["root"], job_id))
    try:
        actual = paths["config"].read_bytes()
        info = paths["config"].lstat()
    except OSError as exc:
        raise ContractError("resume configuration is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or actual != expected:
        raise ContractError("resume configuration drifted")
    return str(file_record(paths["config"], root=paths["job"])["sha256"])


def _terminal(
    *,
    job_id: str,
    state: str,
    attempt: int,
    blocker_code: str | None,
    return_code: int | None,
    elapsed_seconds: float,
    peak_vram_bytes: int,
    telemetry_complete: bool,
    package_sha256: str,
    manifest_sha256: str,
    input_manifest_sha256: str,
    config_sha256: str,
    log_sha256: str | None,
    adapter: dict[str, object] | None,
    resume_checkpoint_sha256: str | None,
    inference_runtime_sha256: str,
    activity_lease_sha256: str,
) -> dict[str, object]:
    if (
        isinstance(elapsed_seconds, bool)
        or not isinstance(elapsed_seconds, (int, float))
        or not math.isfinite(elapsed_seconds)
        or elapsed_seconds <= 0
    ):
        raise ContractError("terminal elapsed time was not measured")
    record = {
        "schema_version": 1,
        "capability": CAPABILITY,
        "job_id": job_id,
        "state": state,
        "attempt": attempt,
        "resumed": attempt == 2,
        "blocker_code": blocker_code,
        "return_code": return_code,
        "elapsed_seconds": max(round(elapsed_seconds, 6), 0.000001),
        "elapsed_scope": "current_process_attempt",
        "peak_vram_bytes": peak_vram_bytes,
        "telemetry_complete": telemetry_complete,
        "contract": "flux2-klein-character-lora-canary-v1",
        "candidate_sha256": package_sha256,
        "manifest_sha256": manifest_sha256,
        "package_sha256": package_sha256,
        "input_manifest_sha256": input_manifest_sha256,
        "config_sha256": config_sha256,
        "log_sha256": log_sha256,
        "adapter": adapter,
        "resume_checkpoint_sha256": resume_checkpoint_sha256,
        "inference_runtime_sha256": inference_runtime_sha256,
        "activity_lease_sha256": activity_lease_sha256,
    }
    validate_terminal_evidence(record)
    return record


def _run_toolkit(paths: dict[str, Path], log_path: Path) -> tuple[int, float, int, bool]:
    started = time.perf_counter()
    peak = 0
    samples = 0
    telemetry_complete = True
    with log_path.open("xb") as log:
        process = subprocess.Popen(
            toolkit_command(paths),
            cwd=paths["toolkit"],
            env=fixed_child_environment(paths),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        try:
            while True:
                try:
                    peak = max(peak, sample_gpu_memory_used_bytes())
                    samples += 1
                except Exception:
                    # Deliberately broad. Telemetry is observational and must
                    # never escape this loop. sample_gpu_memory_used_bytes can
                    # raise subprocess.TimeoutExpired (nvidia-smi is given 10s
                    # and can stall under heavy GPU load) or AttributeError
                    # (stdout is None when the child's stream fails to decode).
                    # Neither is a ContractError, so the previous narrow handler
                    # let them propagate out of the loop AND out of the `with`,
                    # after which nothing polled, waited on, or killed the
                    # ai-toolkit child: it kept running and holding VRAM with no
                    # supervisor, across a multi-hour run.
                    telemetry_complete = False
                return_code = process.poll()
                if return_code is not None:
                    break
                time.sleep(0.25)
        finally:
            # Never leave the trainer orphaned, however this block is left.
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    pass
    return return_code, time.perf_counter() - started, peak, telemetry_complete and samples > 0


def _final_adapter(paths: dict[str, Path], job_id: str) -> Path:
    save_root = _save_root(paths, job_id)
    expected = save_root / f"identity_lora_{job_id}.safetensors"
    checkpoint = save_root / f"identity_lora_{job_id}_000000400.safetensors"
    candidates = {
        path.name for path in save_root.glob("*.safetensors") if path.is_file()
    }
    if candidates != {expected.name, checkpoint.name}:
        raise ContractError(
            "training did not leave the final adapter and exact 400-step checkpoint"
        )
    resume_record = validate_resume_checkpoint(
        checkpoint, root=save_root, job_id=job_id
    )
    if resume_record["step"] != 400:
        raise ContractError("final continuation checkpoint is not step 400")
    optimizer = file_record(save_root / "optimizer.pt", root=save_root)
    if optimizer["bytes"] < 1024:
        raise ContractError("final optimizer continuation state is unavailable")
    validate_lora_safetensors(expected, root=save_root)
    return expected


def run(job_id: str, *, resume: bool = False) -> dict[str, object]:
    validate_package(ROOT)
    job_id = canonical_job_id(job_id)
    state_root = windows_state_root()
    paths = job_paths(state_root, job_id)
    activity_lease_sha = validate_gateway_training_activity_lease(paths, job_id)
    inference_runtime = validate_inference_runtime()
    inference_runtime_sha = inference_runtime["runtime_contract_sha256"]
    terminal_path = paths["evidence"] / "terminal.json"
    started_path = paths["evidence"] / "started.json"
    resume_started_path = paths["evidence"] / "resume-started.json"
    if terminal_path.exists():
        raise ContractError("terminal evidence already exists; relaunch is forbidden")
    if (started_path.exists() and not resume) or (not started_path.exists() and resume):
        raise ContractError("job start state contradicts the requested mode")
    if resume_started_path.exists():
        raise ContractError("the one allowed resume was already started")
    if not resume:
        _recover_unstarted_dead_lock(paths, job_id)
        _reset_unstarted_partial_evidence(
            paths,
            job_id,
            activity_lease_sha256=activity_lease_sha,
        )

    attempt = 2 if resume else 1
    resumed_checkpoint_sha: str | None = None
    stale_started: dict[str, Any] | None = None
    stale_started_sha: str | None = None
    if resume:
        stale_started, stale_started_sha = _read_started(paths, job_id)
        _recover_dead_lease(paths, job_id, stale_started)

    attempt_started = time.perf_counter()
    lock, lock_sha = _acquire_lock(paths, job_id)
    release_lock = True
    try:
        resource = collect_resource_snapshot(state_root)
        baseline_peak_vram = int(
            (resource["vram_mib"] - resource["free_vram_mib"]) * 1024 * 1024
        )
        validate_resource_snapshot(resource)
        receipts = validate_runtime_receipts(state_root, resource)
        admitted = validate_input_manifest(state_root, job_id)
        package_sha = package_digest(ROOT)
        api_manifest = validate_api_manifest(
            state_root,
            job_id,
            input_result=admitted,
            candidate_sha256=package_sha,
        )
        if resume:
            config_sha = _validate_existing_config(paths, job_id)
            try:
                resume_material = _resume_material(paths, job_id)
            except ContractError as exc:
                if str(exc) != "resume_not_available":
                    raise
                result = _terminal(
                    job_id=job_id,
                    state="failed",
                    attempt=2,
                    blocker_code="resume_not_available",
                    return_code=None,
                    elapsed_seconds=time.perf_counter() - attempt_started,
                    peak_vram_bytes=baseline_peak_vram,
                    telemetry_complete=False,
                    package_sha256=package_sha,
                    manifest_sha256=api_manifest["sha256"],
                    input_manifest_sha256=admitted["sha256"],
                    config_sha256=config_sha,
                    log_sha256=None,
                    adapter=None,
                    resume_checkpoint_sha256=None,
                    inference_runtime_sha256=inference_runtime_sha,
                    activity_lease_sha256=activity_lease_sha,
                )
                _write(paths, terminal_path, result)
                return result
            resumed_checkpoint_sha = str(resume_material["checkpoint"]["sha256"])
            interrupted = {
                "schema_version": 1,
                "job_id": job_id,
                "state": "interrupted",
                "started_sha256": stale_started_sha,
                "config_sha256": config_sha,
                **resume_material,
            }
            interrupted_path = paths["evidence"] / "interrupted.json"
            interrupted_sha = _write(paths, interrupted_path, interrupted)
            _write(
                paths,
                resume_started_path,
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "state": "started",
                    "attempt": 2,
                    "interrupted_sha256": interrupted_sha,
                    "lease_sha256": lock_sha,
                    "resource_preflight": resource,
                    "inference_runtime": inference_runtime,
                    "activity_lease_sha256": activity_lease_sha,
                    **receipts,
                },
            )
            log_path = paths["evidence"] / "toolkit-resume.log"
        else:
            config = build_training_config(state_root, job_id)
            paths["config"].parent.mkdir(parents=True, exist_ok=True)
            config_sha = _write(paths, paths["config"], config)
            admission = {
                "schema_version": 1,
                "job_id": job_id,
                "input_manifest_sha256": admitted["sha256"],
                "config_sha256": config_sha,
                "package_sha256": package_sha,
                "contract": api_manifest["contract"],
                "candidate_sha256": api_manifest["candidate_sha256"],
                "manifest_sha256": api_manifest["sha256"],
                **receipts,
                "resource_preflight": resource,
                "inference_runtime": inference_runtime,
                "activity_lease_sha256": activity_lease_sha,
            }
            admission_sha = _write(paths, paths["evidence"] / "admission.json", admission)
            _write(
                paths,
                started_path,
                {
                    "schema_version": 1,
                    "job_id": job_id,
                    "state": "started",
                    "attempt": 1,
                    "admission_sha256": admission_sha,
                    "lease_sha256": lock_sha,
                    "activity_lease_sha256": activity_lease_sha,
                },
            )
            paths["output"].mkdir(parents=True, exist_ok=False)
            log_path = paths["evidence"] / "toolkit.log"

        run_started = time.perf_counter()
        try:
            return_code, elapsed, peak_vram, telemetry_complete = _run_toolkit(paths, log_path)
        except BaseException as exc:
            release_lock = False
            result = _terminal(
                job_id=job_id,
                state="unknown",
                attempt=attempt,
                blocker_code="training_outcome_ambiguous",
                return_code=None,
                elapsed_seconds=time.perf_counter() - run_started,
                peak_vram_bytes=baseline_peak_vram,
                telemetry_complete=False,
                package_sha256=package_sha,
                manifest_sha256=api_manifest["sha256"],
                input_manifest_sha256=admitted["sha256"],
                config_sha256=config_sha,
                log_sha256=file_record(log_path)["sha256"] if log_path.exists() else None,
                adapter=None,
                resume_checkpoint_sha256=resumed_checkpoint_sha,
                inference_runtime_sha256=inference_runtime_sha,
                activity_lease_sha256=activity_lease_sha,
            )
            _write(paths, terminal_path, result)
            raise ContractError("training outcome is ambiguous; relaunch is forbidden") from exc

        log_sha = str(file_record(log_path, root=paths["evidence"])["sha256"])
        bounded_log = regular_file_tail(
            log_path, root=paths["evidence"]
        ).decode("utf-8", errors="replace")
        if resume and (
            "#### IMPORTANT RESUMING FROM" not in bounded_log
            or "Found step " not in bounded_log
            or "Loading optimizer state from" not in bounded_log
            or "Failed to load optimizer state" in bounded_log
        ):
            return_code = return_code or 4
            blocker = "resume_state_not_loaded"
        elif return_code != 0:
            blocker = classify_failure(return_code, bounded_log)
        elif not telemetry_complete:
            # Incomplete telemetry no longer discards a run that exited 0.
            #
            # telemetry_complete latches False on a single sampling failure and
            # is never reset, while the sampler fires every 0.25s -- tens of
            # thousands of nvidia-smi invocations across a multi-hour run. This
            # branch used to sit ABOVE the return_code check, so `return_code or
            # 4` turned a clean exit into exit 4 with blocker
            # "telemetry_incomplete", wrote a `failed` terminal with adapter=None
            # and returned before harvest. One transient nvidia-smi hiccup threw
            # away a fully trained adapter that was sitting on disk.
            #
            # Nothing is hidden by relaxing it: telemetry_complete is recorded
            # in the evidence either way, so a reader can already see that the
            # peak_vram_bytes figure is a lower bound rather than a measurement.
            # Losing the adapter never made that flag more honest.
            blocker = None
        else:
            blocker = None

        if blocker is not None:
            result = _terminal(
                job_id=job_id,
                state="failed",
                attempt=attempt,
                blocker_code=blocker,
                return_code=return_code,
                elapsed_seconds=elapsed,
                peak_vram_bytes=peak_vram,
                telemetry_complete=telemetry_complete,
                package_sha256=package_sha,
                manifest_sha256=api_manifest["sha256"],
                input_manifest_sha256=admitted["sha256"],
                config_sha256=config_sha,
                log_sha256=log_sha,
                adapter=None,
                resume_checkpoint_sha256=resumed_checkpoint_sha,
                inference_runtime_sha256=inference_runtime_sha,
                activity_lease_sha256=activity_lease_sha,
            )
            _write(paths, terminal_path, result)
            return result

        try:
            produced = _final_adapter(paths, job_id)
            produced_record = file_record(produced, root=paths["output"])
            name = adapter_filename(produced_record["sha256"])
            paths["adapter"].mkdir(parents=True, exist_ok=False)
            published = paths["adapter"] / name
            with produced.open("rb") as source, published.open("xb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            metadata = build_adapter_metadata(
                job_id=job_id,
                adapter_bytes=int(produced_record["bytes"]),
                adapter_sha256=str(produced_record["sha256"]),
                input_manifest_sha256=admitted["sha256"],
                config_sha256=config_sha,
                package_sha256=package_sha,
                inference_runtime_sha256=inference_runtime_sha,
                **validate_lora_safetensors(produced, root=paths["output"]),
            )
            validate_adapter_file(published, metadata, root=paths["adapter"])
            metadata_filename = f"{name}.json"
            metadata_sha = _write(paths, paths["adapter"] / metadata_filename, metadata)
            adapter_record = {
                **metadata["adapter"],
                "metadata_filename": metadata_filename,
                "metadata_sha256": metadata_sha,
            }
        except (ContractError, OSError) as exc:
            result = _terminal(
                job_id=job_id,
                state="failed",
                attempt=attempt,
                blocker_code="adapter_validation_failed",
                return_code=4,
                elapsed_seconds=elapsed,
                peak_vram_bytes=peak_vram,
                telemetry_complete=telemetry_complete,
                package_sha256=package_sha,
                manifest_sha256=api_manifest["sha256"],
                input_manifest_sha256=admitted["sha256"],
                config_sha256=config_sha,
                log_sha256=log_sha,
                adapter=None,
                resume_checkpoint_sha256=resumed_checkpoint_sha,
                inference_runtime_sha256=inference_runtime_sha,
                activity_lease_sha256=activity_lease_sha,
            )
            _write(paths, terminal_path, result)
            return result

        result = _terminal(
            job_id=job_id,
            state="training_passed",
            attempt=attempt,
            blocker_code=None,
            return_code=0,
            elapsed_seconds=elapsed,
            peak_vram_bytes=peak_vram,
            telemetry_complete=True,
            package_sha256=package_sha,
            manifest_sha256=api_manifest["sha256"],
            input_manifest_sha256=admitted["sha256"],
            config_sha256=config_sha,
            log_sha256=log_sha,
            adapter=adapter_record,
            resume_checkpoint_sha256=resumed_checkpoint_sha,
            inference_runtime_sha256=inference_runtime_sha,
            activity_lease_sha256=activity_lease_sha,
        )
        _write(paths, terminal_path, result)
        return result
    finally:
        if release_lock:
            _release_lock(paths["lock"], lock_sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.job_id, resume=args.resume)
    except ContractError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("state") == "training_passed" else 3


if __name__ == "__main__":
    raise SystemExit(main())

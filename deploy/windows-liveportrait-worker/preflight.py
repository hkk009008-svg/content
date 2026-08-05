#!/usr/bin/env python3
"""Fail-closed readiness proof for the native Windows LivePortrait worker."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_PACKAGES = {
    "torch": "2.11.0+cu130",
    "torchvision": "0.26.0+cu130",
    "torchaudio": "2.11.0+cu130",
    "numpy": "1.26.4",
    "mediapipe": "0.10.14",
    "onnxruntime": "1.19.2",
    "opencv-contrib-python": "4.11.0.86",
}
REQUIRED_NODE_CLASSES = {
    "LoadImage",
    "DownloadAndLoadLivePortraitModels",
    "LivePortraitLoadMediaPipeCropper",
    "LivePortraitCropper",
    "LivePortraitRetargeting",
    "LivePortraitProcess",
    "LivePortraitComposite",
    "VHS_LoadVideo",
    "VHS_VideoCombine",
}
FORBIDDEN_NODE_CLASSES = {
    "LivePortraitLoadCropper",  # InsightFace path
    "LivePortraitLoadFaceAlignmentCropper",  # requires a seventh model path
}
OUTPUT_SUFFIXES = {".gif", ".jpeg", ".jpg", ".mp4", ".png", ".webm", ".webp"}
WORKER_ROLE = "performance-liveportrait"


class PreflightError(RuntimeError):
    """No readiness sentinel may be published."""


def load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot read {description} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PreflightError(f"{description} must be a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_owned_outputs(output_root: Path, prefix: str) -> None:
    """Remove only regular output files owned by one UUID-scoped probe run."""

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]+", prefix):
        raise PreflightError("output cleanup prefix is invalid")
    root = output_root.resolve()
    if not root.is_dir():
        return
    for candidate in root.rglob(f"{prefix}*"):
        if candidate.is_symlink():
            raise PreflightError("refusing to clean a linked worker output")
        resolved = candidate.resolve()
        if root not in resolved.parents:
            raise PreflightError("worker output cleanup escaped its output root")
        if candidate.is_file():
            candidate.unlink()
        elif candidate.exists():
            raise PreflightError("refusing to clean a non-file worker output")


def _run(command: list[str], *, timeout: int = 300) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise PreflightError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip()


def unexpected_source_changes(
    component_id: Any,
    status_lines: list[str],
    nested_relative_paths: set[str],
) -> list[str]:
    allowed_nested_repositories = {
        f"{marker} {relative}{suffix}"
        for relative in nested_relative_paths
        for marker in ("??", "!!")
        for suffix in ("", "/")
    }
    return [
        line
        for line in status_lines
        if line
        and line not in allowed_nested_repositories
        and not (
            component_id == "comfyui"
            and (
                line == "!! models/liveportrait"
                or line.startswith("!! models/liveportrait/")
            )
        )
    ]


def verify_revisions(install_root: Path, revisions_path: Path) -> dict[str, Any]:
    payload = load_json(revisions_path, "revision manifest")
    if payload.get("schema_version") != 1:
        raise PreflightError("revision manifest schema_version must be 1")
    platform = payload.get("platform")
    if not isinstance(platform, dict) or platform.get("python") != "3.12":
        raise PreflightError("revision manifest must require Python 3.12")
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise PreflightError("worker must run under CPython 3.12 on Windows")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise PreflightError("revision manifest components must be non-empty")
    resolved_components: list[tuple[dict[str, Any], Path]] = []
    for component in components:
        if not isinstance(component, dict):
            raise PreflightError("revision component must be an object")
        commit = component.get("commit")
        relative_path = component.get("path")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise PreflightError("revision component commit must be a full SHA")
        if not isinstance(relative_path, str) or Path(relative_path).is_absolute():
            raise PreflightError("revision component path must be install-root relative")
        source = (install_root / relative_path).resolve()
        if not source.is_dir():
            raise PreflightError(f"source directory missing: {source}")
        if _run(["git", "-C", str(source), "rev-parse", "HEAD"]) != commit:
            raise PreflightError(f"{component.get('id')}: source revision mismatch")
        remote = _run(["git", "-C", str(source), "remote", "get-url", "origin"])
        expected = str(component.get("repository", "")).rstrip("/").removesuffix(".git")
        if remote.rstrip("/").removesuffix(".git") != expected:
            raise PreflightError(f"{component.get('id')}: origin mismatch")
        resolved_components.append((component, source))

    for component, source in resolved_components:
        nested_relative_paths = {
            nested.relative_to(source).as_posix()
            for _nested_component, nested in resolved_components
            if nested != source and source in nested.parents
        }
        status = _run(
            [
                "git",
                "-C",
                str(source),
                "status",
                "--ignored",
                "--porcelain",
                "--untracked-files=all",
            ]
        )
        unexpected = unexpected_source_changes(
            component.get("id"), status.splitlines(), nested_relative_paths
        )
        if unexpected:
            raise PreflightError(
                f"{component.get('id')}: source has tracked or untracked changes: "
                + "; ".join(unexpected)
            )
    return payload


def verify_models(model_root: Path, models_path: Path) -> dict[str, Any]:
    payload = load_json(models_path, "model manifest")
    artifacts = payload.get("artifacts")
    if payload.get("schema_version") != 1 or not isinstance(artifacts, list):
        raise PreflightError("model manifest is invalid")
    if len(artifacts) != 6:
        raise PreflightError("LivePortrait model manifest must contain exactly six artifacts")
    root = model_root.resolve()
    expected_paths: set[Path] = set()
    for artifact in artifacts:
        destination = artifact.get("destination")
        expected_hash = artifact.get("sha256")
        expected_bytes = artifact.get("expected_bytes")
        if not isinstance(destination, str) or Path(destination).is_absolute():
            raise PreflightError("model destination must be model-root relative")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise PreflightError(f"{destination}: invalid SHA-256")
        path = (root / destination).resolve()
        expected_paths.add(path)
        if root not in path.parents or not path.is_file():
            raise PreflightError(f"model artifact missing: {destination}")
        if path.stat().st_size != expected_bytes:
            raise PreflightError(f"{destination}: byte count mismatch")
        if sha256_file(path) != expected_hash:
            raise PreflightError(f"{destination}: SHA-256 mismatch")
    liveportrait_root = (root / "liveportrait").resolve()
    actual_paths = {
        path.resolve()
        for path in liveportrait_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if any(path.is_symlink() for path in liveportrait_root.rglob("*")):
        raise PreflightError("LivePortrait model directory may not contain symlinks")
    if actual_paths != expected_paths:
        extras = sorted(str(path.relative_to(root)) for path in actual_paths - expected_paths)
        missing = sorted(str(path.relative_to(root)) for path in expected_paths - actual_paths)
        raise PreflightError(
            f"LivePortrait model inventory mismatch; extra={extras}, missing={missing}"
        )
    return payload


def verify_python_and_gpu() -> str:
    _run([sys.executable, "-m", "pip", "check"])
    actual = {
        package: importlib.metadata.version(package) for package in EXPECTED_PACKAGES
    }
    if actual != EXPECTED_PACKAGES:
        raise PreflightError(f"Python package matrix {actual} != {EXPECTED_PACKAGES}")
    # Package imports are the primary proof; this explicit distribution check prevents
    # an accidental GPU ONNX or InsightFace addition from being treated as ready.
    distributions = {
        distribution.metadata["Name"].lower()
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    forbidden = distributions & {"insightface", "onnxruntime-gpu"}
    if forbidden:
        raise PreflightError("forbidden packages installed: " + ", ".join(sorted(forbidden)))
    if "opencv-contrib-python" not in distributions:
        raise PreflightError("opencv-contrib-python distribution is missing")
    conflicting_opencv = distributions & {
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python-headless",
    }
    if conflicting_opencv:
        raise PreflightError(
            "conflicting OpenCV distributions installed: "
            + ", ".join(sorted(conflicting_opencv))
        )

    import cv2

    if cv2.__version__ != "4.11.0":
        raise PreflightError(f"cv2 runtime is {cv2.__version__!r}, expected 4.11.0")

    import torch

    if str(torch.version.cuda or "") != "13.0":
        raise PreflightError(f"PyTorch CUDA runtime is {torch.version.cuda!r}, expected 13.0")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        raise PreflightError("PyTorch cannot access a CUDA GPU")
    _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    probe = torch.ones((1,), device="cuda:0")
    if probe.item() != 1:
        raise PreflightError("CUDA allocation returned an unexpected result")
    del probe
    return str(torch.cuda.get_device_name(0))


def api_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"ComfyUI API failed at {path}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise PreflightError(f"ComfyUI API returned non-object JSON at {path}")
    return decoded


def _safe_probe_path(root: Path, relative: Any, description: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PreflightError(f"{description} must be a relative path")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise PreflightError(f"{description} escapes its root")
    return path


def validate_image_fixture(path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.width < 256 or image.height < 256:
                raise PreflightError(f"image fixture is too small: {path.name}")
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError(f"invalid image fixture {path.name}: {exc}") from exc


def validate_video_container(path: Path, *, expected_frames: int | None = None) -> None:
    try:
        import av

        with av.open(str(path), mode="r") as container:
            format_name = str(container.format.name or "").lower()
            if "mp4" not in format_name and "mov" not in format_name:
                raise PreflightError(f"media artifact is not an MP4 container: {path.name}")
            streams = list(container.streams.video)
            if len(streams) != 1:
                raise PreflightError(f"media artifact must contain one video stream: {path.name}")
            stream = streams[0]
            if stream.width < 1 or stream.height < 1:
                raise PreflightError(f"media artifact has invalid dimensions: {path.name}")
            frame_count = sum(1 for _frame in container.decode(video=0))
    except PreflightError:
        raise
    except Exception as exc:
        raise PreflightError(f"invalid media container {path.name}: {exc}") from exc
    if frame_count < 1:
        raise PreflightError(f"media artifact contains no decodable video frames: {path.name}")
    if expected_frames is not None and frame_count != expected_frames:
        raise PreflightError(
            f"media artifact has {frame_count} frames, expected {expected_frames}: {path.name}"
        )


def upstream_node_ids(workflow: dict[str, Any], output_node_id: str) -> set[str]:
    pending = [output_node_id]
    reached: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in reached:
            continue
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            raise PreflightError(f"workflow references absent node {node_id}")
        reached.add(node_id)
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            raise PreflightError(f"workflow node {node_id} inputs must be an object")
        for value in inputs.values():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and isinstance(value[1], int)
            ):
                pending.append(value[0])
    return reached


def validate_probe(
    probe_root: Path,
    input_root: Path,
    contract_path: Path,
    object_info: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    contract = load_json(contract_path, "expression probe contract")
    if contract.get("schema_version") != 1:
        raise PreflightError("expression probe contract schema_version must be 1")
    workflow_path = _safe_probe_path(probe_root, contract.get("workflow"), "workflow")
    expected_workflow_hash = contract.get("workflow_sha256")
    if (
        not isinstance(expected_workflow_hash, str)
        or not SHA256_RE.fullmatch(expected_workflow_hash)
        or not workflow_path.is_file()
        or sha256_file(workflow_path) != expected_workflow_hash
    ):
        raise PreflightError("API workflow does not match the tracked workflow SHA-256")
    workflow = load_json(workflow_path, "API-format workflow")
    if not workflow or any(not isinstance(node, dict) for node in workflow.values()):
        raise PreflightError("API-format workflow must be a non-empty node map")

    fixtures = contract.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) < 2:
        raise PreflightError("expression probe requires source and driving fixtures")
    fixture_hashes: set[str] = set()
    fixture_paths: list[str] = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise PreflightError("probe fixture must be an object")
        fixture_path = _safe_probe_path(input_root, fixture.get("path"), "fixture")
        expected_hash = fixture.get("sha256")
        expected_bytes = fixture.get("expected_bytes")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise PreflightError("probe fixture requires a real lowercase SHA-256")
        if (
            not fixture_path.is_file()
            or not isinstance(expected_bytes, int)
            or fixture_path.stat().st_size != expected_bytes
            or sha256_file(fixture_path) != expected_hash
        ):
            raise PreflightError(f"probe fixture verification failed: {fixture_path.name}")
        fixture_paths.append(str(fixture["path"]))
        fixture_hashes.add(expected_hash)
    if len(fixture_hashes) != len(fixtures):
        raise PreflightError("source and driving fixtures must be distinct bytes")
    if fixture_paths != ["source-face.jpg", "driving-expression.mp4"]:
        raise PreflightError("probe fixtures must be the tracked source and driving pair")
    validate_image_fixture(input_root / fixture_paths[0])
    validate_video_container(input_root / fixture_paths[1], expected_frames=1)

    if workflow.get("10", {}).get("inputs", {}).get("image") != fixture_paths[0]:
        raise PreflightError("LoadImage is not bound to the declared source fixture")
    if workflow.get("11", {}).get("inputs", {}).get("video") != fixture_paths[1]:
        raise PreflightError("VHS_LoadVideo is not bound to the declared driving fixture")

    classes = {node.get("class_type") for node in workflow.values()}
    missing = REQUIRED_NODE_CLASSES - classes
    forbidden = FORBIDDEN_NODE_CLASSES & classes
    if missing:
        raise PreflightError("workflow missing node classes: " + ", ".join(sorted(missing)))
    if forbidden:
        raise PreflightError("workflow uses forbidden cropper: " + ", ".join(sorted(forbidden)))
    if not REQUIRED_NODE_CLASSES.issubset(object_info):
        missing_runtime = REQUIRED_NODE_CLASSES - set(object_info)
        raise PreflightError(
            "runtime missing node classes: " + ", ".join(sorted(missing_runtime))
        )

    one_frame_video = False
    for node_id, node in workflow.items():
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not isinstance(inputs, dict):
            raise PreflightError(f"workflow node {node_id} has invalid class_type or inputs")
        descriptor = object_info.get(class_type)
        if not isinstance(descriptor, dict):
            raise PreflightError(f"workflow node class unavailable: {class_type}")
        input_groups = descriptor.get("input")
        if not isinstance(input_groups, dict):
            raise PreflightError(f"runtime input schema unavailable: {class_type}")
        allowed: set[str] = set()
        required: set[str] = set()
        for group in ("required", "optional", "hidden"):
            values = input_groups.get(group, {})
            if isinstance(values, dict):
                allowed.update(values)
                if group == "required":
                    required.update(values)
        unknown = set(inputs) - allowed
        absent = required - set(inputs)
        if unknown or absent:
            raise PreflightError(
                f"workflow node {node_id} input schema mismatch; "
                f"unknown={sorted(unknown)}, absent={sorted(absent)}"
            )
        if class_type == "VHS_LoadVideo" and inputs.get("frame_load_cap") == 1:
            one_frame_video = True
        if class_type == "LivePortraitLoadMediaPipeCropper":
            if inputs.get("landmarkrunner_onnx_device") != "CPU":
                raise PreflightError("MediaPipe cropper must use the CPU ONNX provider")
        if class_type == "DownloadAndLoadLivePortraitModels":
            if inputs.get("mode", "human") != "human":
                raise PreflightError("expression probe must use human LivePortrait models")
    if not one_frame_video:
        raise PreflightError("expression probe must cap VHS_LoadVideo to exactly one frame")

    output_ids = contract.get("output_node_ids")
    if output_ids != ["19"]:
        raise PreflightError("expression probe output must be exactly node 19")
    normalized_output_ids = [str(item) for item in output_ids]
    if any(item not in workflow for item in normalized_output_ids):
        raise PreflightError("expression probe output_node_ids are absent from workflow")
    if workflow["19"].get("class_type") != "VHS_VideoCombine":
        raise PreflightError("expression probe output node 19 must be VHS_VideoCombine")
    reached = upstream_node_ids(workflow, "19")
    if reached != set(workflow):
        raise PreflightError("every shipping workflow node must reach output node 19")
    if {workflow[node_id]["class_type"] for node_id in reached} != classes:
        raise PreflightError("connected workflow class topology is incomplete")
    return workflow, normalized_output_ids


def execute_probe(
    base_url: str,
    workflow: dict[str, Any],
    output_node_ids: list[str],
    output_root: Path,
    *,
    timeout: int = 300,
) -> str:
    prefix = f"content-worker-preflight-{uuid.uuid4().hex}"
    graph = copy.deepcopy(workflow)
    graph["19"]["inputs"]["filename_prefix"] = prefix
    try:
        submitted = api_json(
            base_url,
            "/prompt",
            method="POST",
            payload={"prompt": graph, "client_id": str(uuid.uuid4())},
            timeout=30,
        )
        prompt_id = submitted.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise PreflightError(
                f"ComfyUI rejected expression probe: {submitted.get('error')}"
            )
        deadline = time.monotonic() + timeout
        history: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            response = api_json(base_url, f"/history/{prompt_id}", timeout=15)
            candidate = response.get(prompt_id)
            if isinstance(candidate, dict):
                history = candidate
                break
            time.sleep(1)
        if history is None:
            raise PreflightError("one-frame expression probe timed out")
        status = history.get("status")
        if not isinstance(status, dict) or status.get("completed") is not True:
            raise PreflightError("one-frame expression probe did not complete successfully")
        outputs = history.get("outputs")
        if not isinstance(outputs, dict):
            raise PreflightError("one-frame expression probe returned no outputs")

        validated = 0
        root = output_root.resolve()
        for node_id in output_node_ids:
            node_outputs = outputs.get(node_id)
            if not isinstance(node_outputs, dict):
                continue
            for collection in node_outputs.values():
                if not isinstance(collection, list):
                    continue
                for item in collection:
                    if not isinstance(item, dict) or not isinstance(
                        item.get("filename"), str
                    ):
                        continue
                    subfolder = item.get("subfolder", "")
                    if not isinstance(subfolder, str):
                        continue
                    artifact = (root / subfolder / item["filename"]).resolve()
                    if (
                        root not in artifact.parents
                        or not artifact.name.startswith(prefix)
                        or artifact.suffix.lower() not in OUTPUT_SUFFIXES
                    ):
                        continue
                    if artifact.is_file() and artifact.stat().st_size > 0:
                        if artifact.suffix.lower() != ".mp4":
                            raise PreflightError("node 19 output must be an MP4 artifact")
                        validate_video_container(artifact, expected_frames=1)
                        validated += 1
        if validated < 1:
            raise PreflightError(
                "one-frame expression probe produced no validated media artifact"
            )
        return prompt_id
    finally:
        cleanup_owned_outputs(output_root, prefix)


def write_sentinel(
    path: Path,
    *,
    gpu_name: str,
    prompt_id: str,
    revisions_path: Path,
    models_path: Path,
    workflow_path: Path,
) -> None:
    revisions_hash = sha256_file(revisions_path)
    models_hash = sha256_file(models_path)
    workflow_hash = sha256_file(workflow_path)
    contract_payload = {
        "model_manifest_sha256": models_hash,
        "revisions_manifest_sha256": revisions_hash,
        "role": WORKER_ROLE,
        "workflow_sha256": workflow_hash,
    }
    contract_digest = hashlib.sha256(
        json.dumps(contract_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "status": "ready",
        "role": WORKER_ROLE,
        "startup_ready": True,
        "execution_proven": True,
        "checked_at_unix": int(time.time()),
        "gpu_name": gpu_name,
        "workflow_sha256": workflow_hash,
        "model_manifest_sha256": models_hash,
        "revisions_manifest_sha256": revisions_hash,
        "contract_digest": contract_digest,
        "execution_canary": {"state": "passed", "prompt_id": prompt_id},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--probe-contract", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    args.sentinel.unlink(missing_ok=True)
    verify_revisions(args.install_root.resolve(), args.revisions.resolve())
    verify_models(args.model_root.resolve(), args.models.resolve())
    gpu_name = verify_python_and_gpu()
    system_stats = api_json(args.comfy_url, "/system_stats")
    if not isinstance(system_stats.get("system"), dict):
        raise PreflightError("ComfyUI system_stats contract is invalid")
    object_info = api_json(args.comfy_url, "/object_info", timeout=60)
    workflow, output_ids = validate_probe(
        args.probe_contract.parent.resolve(),
        args.input_root.resolve(),
        args.probe_contract.resolve(),
        object_info,
    )
    prompt_id = execute_probe(
        args.comfy_url,
        workflow,
        output_ids,
        args.output_root.resolve(),
    )
    write_sentinel(
        args.sentinel.resolve(),
        gpu_name=gpu_name,
        prompt_id=prompt_id,
        revisions_path=args.revisions.resolve(),
        models_path=args.models.resolve(),
        workflow_path=_safe_probe_path(
            args.probe_contract.parent.resolve(),
            load_json(args.probe_contract.resolve(), "expression probe contract").get("workflow"),
            "workflow",
        ),
    )
    print("LivePortrait worker preflight passed; readiness sentinel published.")


if __name__ == "__main__":
    try:
        main()
    except PreflightError as exc:
        print(f"NOT READY: {exc}", file=sys.stderr)
        raise SystemExit(1)

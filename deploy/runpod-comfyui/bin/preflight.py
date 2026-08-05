#!/usr/bin/env python3
"""Fail-closed offline preflight for the immutable RunPod ComfyUI image."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from model_artifacts import ManifestError, ArtifactError, load_manifest, verify_all


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_TORCH = {
    "torch": "2.6.0",
    "torchvision": "0.21.0",
    "torchaudio": "2.6.0",
}
MODEL_INPUTS = {
    "unet_name": "diffusion_models",
    "clip_name1": "clip",
    "clip_name2": "clip",
    "vae_name": "vae",
    "pulid_file": "pulid",
    "model_name": "upscale_models",
}


class PreflightError(RuntimeError):
    """The image must not become ready because a production invariant failed."""


def validate_revisions_payload(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PreflightError("revision manifest schema_version must be 1")
    base_image = payload.get("base_image")
    if not isinstance(base_image, dict):
        raise PreflightError("revision manifest base_image must be an object")
    reference = base_image.get("reference")
    digest = reference.rsplit("@sha256:", 1)[-1] if isinstance(reference, str) else ""
    if (
        not isinstance(reference, str)
        or "@sha256:" not in reference
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise PreflightError("base_image.reference must contain a full sha256 digest")
    if base_image.get("platform") != "linux/amd64":
        raise PreflightError("base_image.platform must be linux/amd64")
    for package, version in EXPECTED_TORCH.items():
        if base_image.get(package) != version:
            raise PreflightError(f"base_image.{package} must be {version}")
    if base_image.get("cuda") != "12.4":
        raise PreflightError("base_image.cuda must be 12.4")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise PreflightError("revision manifest components must be a non-empty list")
    seen: set[str] = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise PreflightError(f"components[{index}] must be an object")
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id.strip() or component_id in seen:
            raise PreflightError(f"components[{index}].id must be non-empty and unique")
        seen.add(component_id)
        repository = component.get("repository")
        if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
            raise PreflightError(f"{component_id}: repository must be an HTTPS GitHub URL")
        commit = component.get("commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise PreflightError(f"{component_id}: commit must be a full lowercase SHA")
        component_path = component.get("path")
        if not isinstance(component_path, str) or not Path(component_path).is_absolute():
            raise PreflightError(f"{component_id}: path must be absolute")
        license_id = component.get("license")
        if not isinstance(license_id, str) or not license_id.strip():
            raise PreflightError(f"{component_id}: license metadata is required")


def load_revisions(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot read revision manifest {path}: {exc}") from exc
    validate_revisions_payload(payload)
    return payload


def _run(command: list[str], *, timeout: int = 120) -> str:
    environment = os.environ.copy()
    environment.pop("GIT_INDEX_FILE", None)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise PreflightError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip()


def verify_revisions(payload: dict[str, Any]) -> None:
    for component in payload["components"]:
        path = Path(component["path"])
        if not path.is_dir():
            raise PreflightError(f"{component['id']}: source directory missing: {path}")
        git = ["env", "-u", "GIT_INDEX_FILE", "git", "-C", str(path)]
        actual = _run([*git, "rev-parse", "HEAD"])
        if actual != component["commit"]:
            raise PreflightError(
                f"{component['id']}: commit {actual} != {component['commit']}"
            )
        dirty = _run(
            [*git, "status", "--porcelain", "--untracked-files=no"]
        )
        if dirty:
            raise PreflightError(f"{component['id']}: tracked source differs from pinned commit")
        remote = _run([*git, "remote", "get-url", "origin"])
        expected_remote = component["repository"].rstrip("/").removesuffix(".git")
        if remote.rstrip("/").removesuffix(".git") != expected_remote:
            raise PreflightError(f"{component['id']}: origin does not match revision manifest")
        print(f"revision verified {component['id']}@{actual}", flush=True)


def verify_python_environment(*, require_gpu: bool) -> None:
    _run([sys.executable, "-m", "pip", "check"], timeout=300)
    import torch
    import torchaudio
    import torchvision

    actual = {
        "torch": torch.__version__.split("+")[0],
        "torchvision": torchvision.__version__.split("+")[0],
        "torchaudio": torchaudio.__version__.split("+")[0],
    }
    if actual != EXPECTED_TORCH:
        raise PreflightError(f"torch ABI matrix {actual} != {EXPECTED_TORCH}")
    cuda_version = str(torch.version.cuda or "")
    if not cuda_version.startswith("12.4"):
        raise PreflightError(f"torch CUDA runtime {cuda_version!r} is not the pinned 12.4 matrix")
    if require_gpu:
        _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise PreflightError("PyTorch cannot access a CUDA GPU")
        # Force a real device allocation instead of trusting metadata alone.
        probe = torch.ones((1,), device="cuda")
        if probe.item() != 1:
            raise PreflightError("CUDA allocation canary returned an unexpected result")
        del probe
    print(f"dependency and CUDA matrix verified: {actual}, CUDA {cuda_version}", flush=True)


def ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise PreflightError(f"writable path must be a real directory: {path}")
    try:
        with tempfile.NamedTemporaryFile(prefix=".content-write-probe-", dir=path, delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise PreflightError(f"directory is not writable: {path}: {exc}") from exc


def workflow_model_contract(workflow_path: Path, manifest: dict[str, Any]) -> None:
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot read production workflow {workflow_path}: {exc}") from exc
    if not isinstance(workflow, dict) or not workflow:
        raise PreflightError("production workflow must be a non-empty object")

    destinations = {artifact["destination"] for artifact in manifest["artifacts"]}
    missing: list[str] = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name, category in MODEL_INPUTS.items():
            selected = inputs.get(input_name)
            if not isinstance(selected, str):
                continue
            expected_suffix = f"{category}/{selected}"
            if not any(destination.endswith(expected_suffix) for destination in destinations):
                missing.append(f"{input_name}={selected}")
    if missing:
        raise PreflightError(
            "workflow model choices absent from manifest: " + ", ".join(sorted(missing))
        )


def render_extra_model_paths(model_root: Path, destination: Path) -> None:
    # JSON string syntax is valid YAML and safely quotes any spaces or punctuation.
    root = json.dumps(str(model_root.resolve()))
    content = (
        "content_production:\n"
        f"  base_path: {root}\n"
        "  diffusion_models: diffusion_models\n"
        "  clip: clip\n"
        "  vae: vae\n"
        "  upscale_models: upscale_models\n"
        "  pulid: pulid\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, destination)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=Path("/workspace/models"))
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument(
        "--extra-model-paths", type=Path, default=Path("/run/content/extra_model_paths.yaml")
    )
    parser.add_argument("--skip-gpu", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        revisions = load_revisions(args.revisions)
        models = load_manifest(args.models)
        verify_revisions(revisions)
        workflow_model_contract(args.workflow, models)
        for relative in ("input", "output", "temp", "user", "logs"):
            ensure_writable_directory(args.workspace / "comfyui" / relative)
        ensure_writable_directory(args.model_root)
        verify_all(args.model_root, models)
        verify_python_environment(require_gpu=not args.skip_gpu)
        render_extra_model_paths(args.model_root, args.extra_model_paths)
    except (PreflightError, ManifestError, ArtifactError, OSError) as exc:
        print(f"production preflight failed: {exc}", file=sys.stderr)
        return 2
    print("production offline preflight passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

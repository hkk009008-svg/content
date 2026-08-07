#!/usr/bin/env python3
"""Install the one hash-pinned Windows FLUX.2 Klein LoRA runtime."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from contract import (
    BASE_BYTES,
    BASE_FILENAME,
    BASE_REPOSITORY,
    BASE_REVISION,
    BASE_SHA256,
    ContractError,
    INFERENCE_PACKAGE_BINDINGS,
    REPOSITORY_INFERENCE_PACKAGE_ROOT,
    QWEN_FILE_RECORDS,
    QWEN_REVISION,
    QWEN_TREE_SHA256,
    ROOT,
    TOOLKIT_COMMIT,
    VAE_BYTES,
    VAE_FILENAME,
    VAE_REPOSITORY,
    VAE_REVISION,
    VAE_SHA256,
    canonical_json_bytes,
    file_record,
    package_digest,
    sha256_bytes,
    validate_package,
    validate_resource_snapshot,
    validate_runtime_receipts,
    windows_state_root,
    write_json_new,
)


def _real_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ContractError(f"installer directory is unsafe: {path.name}")


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 3600) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=None,
        shell=False,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ContractError(f"installer command failed: {Path(command[0]).name}")


def _git_executable() -> Path:
    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        raise ContractError("ProgramFiles is unavailable")
    executable = Path(program_files) / "Git" / "cmd" / "git.exe"
    if not executable.is_file():
        raise ContractError("fixed Git executable is unavailable")
    return executable


def _install_toolkit(path: Path) -> None:
    git = _git_executable()
    if not path.exists():
        _run(
            [
                str(git),
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/ostris/ai-toolkit.git",
                str(path),
            ],
            timeout=1800,
        )
        _run([str(git), "-C", str(path), "checkout", "--detach", TOOLKIT_COMMIT])
    commands = (
        ["rev-parse", "HEAD"],
        ["status", "--porcelain", "--untracked-files=all"],
    )
    outputs: list[str] = []
    for arguments in commands:
        result = subprocess.run(
            [str(git), "-C", str(path), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise ContractError("AI Toolkit checkout cannot be verified")
        outputs.append(result.stdout.strip())
    if outputs != [TOOLKIT_COMMIT, ""]:
        raise ContractError("AI Toolkit checkout revision or worktree drifted")


def _download(url: str, target: Path, expected_bytes: int, expected_sha256: str) -> None:
    if target.exists() or target.is_symlink():
        if file_record(target, root=target.parent) == {
            "bytes": expected_bytes,
            "sha256": expected_sha256,
        }:
            return
        raise ContractError(f"refusing to replace a drifted model: {target.name}")
    _real_directory(target.parent)
    partial = target.with_name(target.name + ".part")
    offset = 0
    if partial.exists() or partial.is_symlink():
        info = partial.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ContractError(f"partial download path is unsafe: {target.name}")
        offset = info.st_size
        if offset >= expected_bytes:
            raise ContractError(f"partial download size is invalid: {target.name}")
    headers = {"User-Agent": "Content-Identity-Lab/1"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status = response.getcode()
            if (offset and status != 206) or (not offset and status != 200):
                raise ContractError(f"model server did not honor the fixed download: {target.name}")
            mode = "ab" if offset else "xb"
            with partial.open(mode) as handle:
                received = offset
                while True:
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > expected_bytes:
                        raise ContractError(
                            f"model download exceeded its fixed size: {target.name}"
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
    except ContractError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise ContractError(f"model download failed: {target.name}") from exc
    if file_record(partial, root=target.parent) != {
        "bytes": expected_bytes,
        "sha256": expected_sha256,
    }:
        raise ContractError(f"downloaded model hash failed: {target.name}")
    os.replace(partial, target)


def _hf_url(repository: str, revision: str, relative: str) -> str:
    return f"https://huggingface.co/{repository}/resolve/{revision}/{relative}?download=true"


def _installed_packages(python: Path) -> list[list[str]]:
    probe = (
        "import importlib.metadata,json,re;"
        "p=sorted([re.sub(r'[-_.]+','-',d.metadata.get('Name','').lower()),d.version] "
        "for d in importlib.metadata.distributions());"
        "print(json.dumps(p,separators=(',',':')))"
    )
    result = subprocess.run(
        [str(python), "-I", "-c", probe],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=60,
    )
    try:
        packages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("installed dependency inventory probe failed") from exc
    if result.returncode != 0 or not isinstance(packages, list) or not packages:
        raise ContractError("installed dependency inventory probe failed")
    return packages


def _collect_fixed_venv_resource_snapshot(
    python: Path, state_root: Path, package_root: Path
) -> dict[str, Any]:
    probe = (
        "import json,pathlib,sys;"
        "sys.dont_write_bytecode=True;"
        "sys.path.insert(0,sys.argv[1]);"
        "from contract import collect_resource_snapshot;"
        "print(json.dumps(collect_resource_snapshot(pathlib.Path(sys.argv[2])),"
        "sort_keys=True,separators=(',',':')))"
    )
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            probe,
            str(package_root.resolve(strict=True)),
            str(state_root.resolve(strict=True)),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        timeout=120,
    )
    if result.returncode != 0 or len(result.stdout) > 65_536:
        raise ContractError("fixed training venv resource preflight failed")
    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("fixed training venv resource preflight failed") from exc
    if not isinstance(snapshot, Mapping):
        raise ContractError("fixed training venv resource preflight failed")
    validate_resource_snapshot(snapshot)
    return dict(snapshot)


def _copy_package(destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        validate_package(destination)
        if package_digest(destination) != package_digest(ROOT):
            raise ContractError("installed package candidate drifted")
        return
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    validate_package(destination)


def _copy_inference_package(destination: Path) -> None:
    source = REPOSITORY_INFERENCE_PACKAGE_ROOT.resolve(strict=True)
    for relative, expected_sha256 in INFERENCE_PACKAGE_BINDINGS.items():
        if file_record(source / relative, root=source)["sha256"] != expected_sha256:
            raise ContractError(f"pinned inference package drifted: {relative}")
    if not destination.exists():
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for relative, expected_sha256 in INFERENCE_PACKAGE_BINDINGS.items():
        if file_record(destination / relative, root=destination)["sha256"] != expected_sha256:
            raise ContractError(f"installed inference package drifted: {relative}")


def install() -> dict[str, Any]:
    if (
        os.name != "nt"
        or platform.system() != "Windows"
        or platform.machine() != "AMD64"
        or sys.version_info[:2] != (3, 12)
    ):
        raise ContractError("installer requires Windows AMD64 and CPython 3.12")
    validate_package(ROOT)
    state_root = windows_state_root()
    _real_directory(state_root)
    lock_path = state_root / "install.lock"
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise ContractError("another install is active or requires reconciliation") from exc
    os.close(descriptor)
    try:
        runtime = state_root / "runtime"
        _real_directory(runtime)
        python = runtime / "venv" / "Scripts" / "python.exe"
        if not python.is_file():
            _run([sys.executable, "-m", "venv", str(runtime / "venv")], timeout=300)
        if Path(sys.executable).resolve() == python.resolve():
            raise ContractError("installer must run outside the destination venv")
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--no-cache-dir",
                "-r",
                str(ROOT / "requirements.lock"),
            ],
            timeout=7200,
        )
        packages = _installed_packages(python)
        packages_sha = sha256_bytes(canonical_json_bytes(packages))

        toolkit = runtime / "ai-toolkit"
        _install_toolkit(toolkit)
        models = runtime / "models"
        _download(
            _hf_url(BASE_REPOSITORY, BASE_REVISION, BASE_FILENAME),
            models / BASE_FILENAME,
            BASE_BYTES,
            BASE_SHA256,
        )
        _download(
            _hf_url(VAE_REPOSITORY, VAE_REVISION, VAE_FILENAME),
            models / VAE_FILENAME,
            VAE_BYTES,
            VAE_SHA256,
        )

        hf_home = runtime / "hf-home"
        snapshot = (
            hf_home
            / "hub"
            / "models--Qwen--Qwen3-4B"
            / "snapshots"
            / QWEN_REVISION
        )
        qwen_records: list[dict[str, object]] = []
        for relative in sorted(QWEN_FILE_RECORDS):
            size, digest = QWEN_FILE_RECORDS[relative]
            target = snapshot / relative
            _download(
                _hf_url("Qwen/Qwen3-4B", QWEN_REVISION, relative),
                target,
                size,
                digest,
            )
            qwen_records.append({"path": relative, **file_record(target, root=hf_home)})
        if sha256_bytes(canonical_json_bytes(qwen_records)) != QWEN_TREE_SHA256:
            raise ContractError("installed Qwen tree digest drifted")
        ref = hf_home / "hub" / "models--Qwen--Qwen3-4B" / "refs" / "main"
        _real_directory(ref.parent)
        # Write refs/main with NO trailing newline. huggingface_hub writes this
        # file bare and reads it back with `revision = f.read()` -- no .strip()
        # (file_download.py try_to_load_from_cache) -- then joins
        # snapshots/<revision>/<filename>. A trailing newline therefore points at
        # "snapshots/<rev>\n/config.json", which cannot exist, and every offline
        # lookup raises LocalEntryNotFoundError even though the snapshot is
        # present and hash-verified. ai-toolkit reaches Qwen by repo id
        # (flux2_klein_model.py defaults flux2_klein_te_path to "Qwen/Qwen3-4B"),
        # so this breaks training on a machine with no network access.
        #
        # It was invisible because contract.py:1107 .strip()s before comparing:
        # the verification half of this package could not see the byte the
        # install half wrote. Accept either form when re-validating an existing
        # cache so upgrading in place does not raise "Qwen cache ref drifted";
        # refs/main is not part of the hashed qwen tree, so neither form moves a
        # digest.
        expected_ref = QWEN_REVISION.encode("ascii")
        if ref.exists() or ref.is_symlink():
            if ref.read_bytes().strip() != expected_ref:
                raise ContractError("Qwen cache ref drifted")
        else:
            ref.write_bytes(expected_ref)

        _copy_package(state_root / "package")
        _copy_inference_package(state_root / "inference-package")
        runtime_receipt = {
            "schema_version": 1,
            "toolkit_commit": TOOLKIT_COMMIT,
            "python": "3.12",
            "packages_sha256": packages_sha,
            "dependency_lock_sha256": file_record(
                ROOT / "requirements.lock", root=ROOT
            )["sha256"],
            "qwen": {
                "repository": "Qwen/Qwen3-4B",
                "revision": QWEN_REVISION,
                "tree_sha256": QWEN_TREE_SHA256,
                "files": qwen_records,
            },
        }
        model_receipt = {
            "schema_version": 1,
            "training_base": {
                "repository": BASE_REPOSITORY,
                "revision": BASE_REVISION,
                "file": BASE_FILENAME,
                "expected_bytes": BASE_BYTES,
                "sha256": BASE_SHA256,
            },
            "training_vae": {
                "repository": VAE_REPOSITORY,
                "revision": VAE_REVISION,
                "file": VAE_FILENAME,
                "expected_bytes": VAE_BYTES,
                "sha256": VAE_SHA256,
            },
        }
        runtime_receipt_path = runtime / "runtime-receipt.json"
        model_receipt_path = runtime / "model-receipt.json"
        if not runtime_receipt_path.exists():
            write_json_new(runtime_receipt_path, runtime_receipt, root=state_root)
        if not model_receipt_path.exists():
            write_json_new(model_receipt_path, model_receipt, root=state_root)
        resource = _collect_fixed_venv_resource_snapshot(
            python, state_root, state_root / "package"
        )
        receipt_hashes = validate_runtime_receipts(state_root, resource)
        evidence = {
            "schema_version": 1,
            "capability": "identity-flux2-klein-lora",
            "state": "installed_needs_training_canary",
            "package_root": "package",
            "runner": "package/train.py",
            "python": "runtime/venv/Scripts/python.exe",
            "candidate_sha256": package_digest(state_root / "package"),
            "packages_sha256": packages_sha,
            **receipt_hashes,
            "resource_preflight": resource,
        }
        evidence_path = state_root / "evidence" / "install.json"
        if evidence_path.exists() or evidence_path.is_symlink():
            if json.loads(evidence_path.read_text(encoding="utf-8")) != evidence:
                raise ContractError("installed evidence drifted")
        else:
            write_json_new(evidence_path, evidence, root=state_root)
        return evidence
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def main() -> int:
    try:
        result = install()
    except (ContractError, OSError, subprocess.SubprocessError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

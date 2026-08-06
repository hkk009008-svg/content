#!/usr/bin/env python3
"""Offline, header-only compatibility audit for PuLID-FLUX2 Klein 4B.

The verifier reads only the bounded safetensors JSON header.  It never imports a
model runtime, reads tensor payload bytes, contacts a network, or reports this
quarantined candidate as production ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MAX_HEADER_BYTES = 1024 * 1024
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "I64": 8,
    "U64": 8,
    "F64": 8,
}
IMMUTABLE_STATUS = {
    "usage": "evaluation_only",
    "compatibility": "incompatible",
    "license": "license_blocked",
    "production_ready": False,
    "execution_available": False,
    "benchmark_state": "ineligible",
}


class CompatibilityError(RuntimeError):
    """The offline candidate or safetensors header is unsafe or malformed."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompatibilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise CompatibilityError(f"cannot read JSON contract: {path.name}") from exc
    if not isinstance(value, Mapping):
        raise CompatibilityError(f"JSON contract is not an object: {path.name}")
    return value


def load_candidate(path: Path = ROOT / "candidate.json") -> Mapping[str, Any]:
    candidate = _load_json(path)
    status_value = candidate.get("status")
    if not isinstance(status_value, Mapping):
        raise CompatibilityError("candidate status is missing")
    for key, expected in IMMUTABLE_STATUS.items():
        if status_value.get(key) != expected:
            raise CompatibilityError(f"candidate status cannot change {key}")
    return candidate


def _tensor_spec(name: str, value: object) -> tuple[str, list[int], tuple[int, int]]:
    if not isinstance(value, Mapping):
        raise CompatibilityError(f"invalid tensor spec: {name}")
    dtype = value.get("dtype")
    shape = value.get("shape")
    offsets = value.get("data_offsets")
    if dtype not in DTYPE_BYTES:
        raise CompatibilityError(f"unsupported tensor dtype: {name}")
    if not isinstance(shape, list) or any(
        isinstance(size, bool) or not isinstance(size, int) or size < 0
        for size in shape
    ):
        raise CompatibilityError(f"invalid tensor shape: {name}")
    if (
        not isinstance(offsets, list)
        or len(offsets) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in offsets)
        or offsets[0] < 0
        or offsets[1] < offsets[0]
    ):
        raise CompatibilityError(f"invalid tensor offsets: {name}")
    elements = 1
    for size in shape:
        elements *= size
    if offsets[1] - offsets[0] != elements * DTYPE_BYTES[dtype]:
        raise CompatibilityError(f"tensor byte span does not match shape: {name}")
    return dtype, shape, (offsets[0], offsets[1])


def read_safetensors_header(path: Path) -> Mapping[str, Any]:
    """Read and validate only a regular file's bounded safetensors header."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise CompatibilityError("checkpoint is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CompatibilityError("checkpoint must be a regular non-symlink file")

    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise CompatibilityError("checkpoint changed before open")
            prefix = handle.read(8)
            if len(prefix) != 8:
                raise CompatibilityError("truncated safetensors prefix")
            header_bytes = struct.unpack("<Q", prefix)[0]
            if not 2 <= header_bytes <= MAX_HEADER_BYTES:
                raise CompatibilityError("unsafe safetensors header size")
            if 8 + header_bytes > opened.st_size:
                raise CompatibilityError("truncated safetensors header")
            raw_header = handle.read(header_bytes)
            if len(raw_header) != header_bytes:
                raise CompatibilityError("truncated safetensors header")
            after = os.fstat(handle.fileno())
    except CompatibilityError:
        raise
    except OSError as exc:
        raise CompatibilityError("cannot read safetensors header") from exc

    if (
        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise CompatibilityError("checkpoint changed during header read")
    try:
        header = json.loads(raw_header, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError) as exc:
        raise CompatibilityError("invalid safetensors JSON header") from exc
    if not isinstance(header, Mapping):
        raise CompatibilityError("safetensors header is not an object")

    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in metadata.items()
    ):
        raise CompatibilityError("invalid safetensors metadata")

    payload_bytes = opened.st_size - 8 - header_bytes
    spans: list[tuple[int, int, str]] = []
    for name, value in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(name, str) or not name:
            raise CompatibilityError("invalid tensor name")
        _, _, span = _tensor_spec(name, value)
        if span[1] > payload_bytes:
            raise CompatibilityError(f"tensor span exceeds file: {name}")
        spans.append((span[0], span[1], name))
    cursor = 0
    for start, end, name in sorted(spans):
        if start != cursor:
            raise CompatibilityError(f"non-contiguous tensor span: {name}")
        cursor = end
    if cursor != payload_bytes:
        raise CompatibilityError("safetensors payload size does not match header")
    return header


def _blocker(blockers: list[str], code: str) -> None:
    if code not in blockers:
        blockers.append(code)


def _valid_injection_map(
    value: object, *, double_blocks: int, single_blocks: int
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"double_ca", "single_ca"}:
        return False
    for name, upper_bound in (
        ("double_ca", double_blocks),
        ("single_ca", single_blocks),
    ):
        indices = value.get(name)
        if (
            not isinstance(indices, list)
            or not indices
            or any(isinstance(index, bool) or not isinstance(index, int) for index in indices)
            or len(set(indices)) != len(indices)
            or indices != sorted(indices)
            or indices[0] < 0
            or indices[-1] >= upper_bound
        ):
            return False
    return True


def _runtime_map(
    runtime: Mapping[str, Any], architecture: Mapping[str, Any], blockers: list[str]
) -> Mapping[str, list[int]] | None:
    if runtime.get("architecture") != architecture:
        _blocker(blockers, "runtime_architecture_mismatch")
    namespaces = runtime.get("runtime_namespaces")
    if (
        not isinstance(namespaces, list)
        or not namespaces
        or any(not isinstance(value, str) or not value for value in namespaces)
    ):
        _blocker(blockers, "runtime_namespace_mismatch")
    if runtime.get("strict_state_dict") is not True:
        _blocker(blockers, "runtime_strict_load_disabled")
    if runtime.get("random_fallbacks") != []:
        _blocker(blockers, "runtime_random_fallback_declared")
    source_commit = runtime.get("source_commit", runtime.get("commit"))
    if not isinstance(source_commit, str) or not HEX_40.fullmatch(source_commit):
        _blocker(blockers, "runtime_source_not_pinned")
    injection_map = runtime.get("injection_map")
    if not _valid_injection_map(
        injection_map,
        double_blocks=int(architecture["double_blocks"]),
        single_blocks=int(architecture["single_blocks"]),
    ):
        _blocker(blockers, "runtime_injection_map_unresolved")
        return None
    return injection_map


def _license_blockers(license_info: Mapping[str, Any], blockers: list[str]) -> None:
    if license_info.get("license_state") == "noncommercial_research_only":
        _blocker(blockers, "face_model_noncommercial")
        return
    if (
        license_info.get("license_state") != "commercially_permissible_verified"
        or license_info.get("commercial_use_approved") is not True
        or not isinstance(license_info.get("artifact_sha256"), str)
        or not HEX_64.fullmatch(license_info["artifact_sha256"])
        or not isinstance(license_info.get("license_evidence"), str)
        or not license_info["license_evidence"].strip()
        or not isinstance(license_info.get("license_evidence_sha256"), str)
        or not HEX_64.fullmatch(license_info["license_evidence_sha256"])
        or hashlib.sha256(
            license_info["license_evidence"].encode("utf-8")
        ).hexdigest()
        != license_info["license_evidence_sha256"]
    ):
        _blocker(blockers, "face_model_license_unresolved")


def audit_header(
    header: Mapping[str, Any],
    *,
    runtime_audit: Mapping[str, Any] | None = None,
    face_model_license: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Report published incompatibilities; no replacement shape is invented."""

    candidate = load_candidate()
    gate = candidate["replacement_gate"]
    architecture = gate["known_target_architecture"]
    pins = candidate["pins"]
    runtime = runtime_audit if runtime_audit is not None else pins["node_source"]
    face_license = (
        face_model_license
        if face_model_license is not None
        else pins["face_model"]
    )
    blockers: list[str] = ["replacement_projection_contract_unresolved"]

    if runtime_audit is not None:
        _blocker(blockers, "runtime_evidence_not_independently_verified")
    if face_model_license is not None:
        _blocker(blockers, "license_evidence_not_independently_verified")

    _runtime_map(runtime, architecture, blockers)
    _license_blockers(face_license, blockers)

    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, Mapping):
        _blocker(blockers, "checkpoint_metadata_missing")

    tensor_items = {
        name: value for name, value in header.items() if name != "__metadata__"
    }
    observed = pins["published_model"]["observed_header"]
    legacy_namespaces = observed["legacy_namespaces"]
    legacy_seen = False
    published_width_seen = False
    for legacy in legacy_namespaces:
        if any(name == legacy or name.startswith(f"{legacy}.") for name in tensor_items):
            legacy_seen = True
            _blocker(blockers, "legacy_injection_namespace")
            for name, value in tensor_items.items():
                if not name.startswith(f"{legacy}."):
                    continue
                shape = value.get("shape") if isinstance(value, Mapping) else None
                if (
                    isinstance(shape, list)
                    and observed["model_hidden_size"] in shape
                    and observed["model_hidden_size"] != architecture["hidden_size"]
                ):
                    published_width_seen = True
    if legacy_seen:
        _blocker(blockers, "checkpoint_runtime_namespace_mismatch")
    if published_width_seen:
        _blocker(blockers, "published_checkpoint_hidden_size_mismatch")

    status = dict(candidate["status"])
    for key, value in IMMUTABLE_STATUS.items():
        status[key] = value
    return {
        "schema_version": 1,
        "candidate_status": status,
        "static_header_contract_passed": False,
        "blockers": blockers,
        "tensor_count": len(tensor_items),
        "production_ready": False,
    }


def verify_checkpoint(
    checkpoint: Path,
    *,
    runtime_audit_path: Path | None = None,
    face_license_path: Path | None = None,
) -> dict[str, Any]:
    runtime = _load_json(runtime_audit_path) if runtime_audit_path else None
    face_license = _load_json(face_license_path) if face_license_path else None
    header = read_safetensors_header(checkpoint)
    return audit_header(
        header,
        runtime_audit=runtime,
        face_model_license=face_license,
    )


def candidate_report() -> dict[str, Any]:
    candidate = load_candidate()
    return {
        "schema_version": 1,
        "candidate_status": dict(candidate["status"]),
        "production_ready": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", nargs="?", type=Path)
    parser.add_argument("--runtime-audit", type=Path)
    parser.add_argument("--face-license", type=Path)
    args = parser.parse_args(argv)
    try:
        report = (
            verify_checkpoint(
                args.checkpoint,
                runtime_audit_path=args.runtime_audit,
                face_license_path=args.face_license,
            )
            if args.checkpoint
            else candidate_report()
        )
    except CompatibilityError as exc:
        report = {
            "schema_version": 1,
            "candidate_status": dict(IMMUTABLE_STATUS),
            "production_ready": False,
            "static_header_contract_passed": False,
            "blockers": ["unsafe_or_invalid_checkpoint_header"],
            "error": str(exc),
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

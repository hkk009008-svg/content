#!/usr/bin/env python3
"""Deterministically merge the pinned official Qwen safetensors shards.

This tool performs no network access and never overwrites an existing output.
It verifies every source byte before creating a lexicographically ordered,
single-file safetensors artifact and then enforces the manifest output hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import tempfile
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parent
CHUNK_SIZE = 8 * 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024 * 1024
DTYPE_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "U16": 2,
    "I16": 2,
    "F16": 2,
    "BF16": 2,
    "U32": 4,
    "I32": 4,
    "F32": 4,
    "U64": 8,
    "I64": 8,
    "F64": 8,
}


class MergeContractError(RuntimeError):
    """The official shard set or deterministic output contract failed."""


@dataclass(frozen=True)
class TensorSource:
    path: Path
    data_base: int
    start: int
    end: int
    dtype: str
    shape: tuple[int, ...]


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeContractError(f"invalid JSON input: {path.name}") from exc
    if not isinstance(value, Mapping):
        raise MergeContractError(f"JSON input is not an object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise MergeContractError(f"cannot read source artifact: {path.name}") from exc
    return digest.hexdigest()


def _safe_source_path(source_root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise MergeContractError("source path must be a safe POSIX relative path")
    path = (source_root / relative).resolve()
    root = source_root.resolve()
    if root not in path.parents:
        raise MergeContractError("source path escapes the source directory")
    return path


def _tensor_bytes(dtype: object, shape: object) -> int:
    if not isinstance(dtype, str) or dtype not in DTYPE_BYTES:
        raise MergeContractError(f"unsupported safetensors dtype: {dtype!r}")
    if not isinstance(shape, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in shape
    ):
        raise MergeContractError("invalid safetensors tensor shape")
    elements = 1
    for value in shape:
        elements *= value
    return elements * DTYPE_BYTES[dtype]


def _read_shard(path: Path) -> tuple[Mapping[str, Any], int]:
    try:
        file_size = path.stat().st_size
        with path.open("rb") as handle:
            prefix = handle.read(8)
            if len(prefix) != 8:
                raise MergeContractError(f"truncated safetensors file: {path.name}")
            header_size = struct.unpack("<Q", prefix)[0]
            if not 2 <= header_size <= MAX_HEADER_BYTES:
                raise MergeContractError(f"unsafe safetensors header: {path.name}")
            raw_header = handle.read(header_size)
    except OSError as exc:
        raise MergeContractError(f"cannot inspect source artifact: {path.name}") from exc
    try:
        header = json.loads(raw_header)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MergeContractError(f"invalid safetensors header: {path.name}") from exc
    if not isinstance(header, Mapping):
        raise MergeContractError(f"safetensors header is not an object: {path.name}")

    payload_size = file_size - 8 - header_size
    ranges: list[tuple[int, int]] = []
    for name, spec in header.items():
        if name == "__metadata__":
            if not isinstance(spec, Mapping):
                raise MergeContractError(f"invalid safetensors metadata: {path.name}")
            continue
        if not isinstance(name, str) or not name or not isinstance(spec, Mapping):
            raise MergeContractError(f"invalid tensor record: {path.name}")
        offsets = spec.get("data_offsets")
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in offsets
            )
        ):
            raise MergeContractError(f"invalid tensor offsets: {name}")
        start, end = offsets
        if end < start or end - start != _tensor_bytes(
            spec.get("dtype"), spec.get("shape")
        ):
            raise MergeContractError(f"tensor byte span does not match shape: {name}")
        ranges.append((start, end))

    cursor = 0
    for start, end in sorted(ranges):
        if start != cursor:
            raise MergeContractError(f"non-contiguous shard payload: {path.name}")
        cursor = end
    if cursor != payload_size:
        raise MergeContractError(f"shard payload length mismatch: {path.name}")
    return header, 8 + header_size


def _source_records(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = source.get("inputs")
    if not isinstance(records, list) or len(records) != 2:
        raise MergeContractError("Qwen derivation requires exactly two source shards")
    if not all(isinstance(record, Mapping) for record in records):
        raise MergeContractError("Qwen source shard record is invalid")
    return records


def _validate_source_file(path: Path, record: Mapping[str, Any]) -> None:
    expected_bytes = record.get("expected_bytes")
    expected_hash = record.get("sha256")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        raise MergeContractError("source shard size/hash contract is invalid")
    try:
        actual_bytes = path.stat().st_size
    except OSError as exc:
        raise MergeContractError(f"source shard is unavailable: {path.name}") from exc
    if actual_bytes != expected_bytes:
        raise MergeContractError(f"source shard byte size mismatch: {path.name}")
    if _sha256(path) != expected_hash:
        raise MergeContractError(f"source shard SHA-256 mismatch: {path.name}")


def _build_tensor_sources(
    source_root: Path,
    source: Mapping[str, Any],
) -> tuple[OrderedDict[str, Mapping[str, Any]], dict[str, TensorSource]]:
    index_record = source.get("index")
    if not isinstance(index_record, Mapping):
        raise MergeContractError("Qwen source index contract is missing")
    index_path = _safe_source_path(source_root, index_record.get("path"))
    _validate_source_file(index_path, index_record)
    index = _load_json(index_path)
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, Mapping) or not weight_map:
        raise MergeContractError("Qwen source index weight_map is invalid")

    shards: dict[str, tuple[Mapping[str, Any], int, Path]] = {}
    for record in _source_records(source):
        relative = record.get("path")
        path = _safe_source_path(source_root, relative)
        _validate_source_file(path, record)
        header, data_base = _read_shard(path)
        shard_name = Path(str(relative)).name
        if shard_name in shards:
            raise MergeContractError("Qwen source shard basenames are duplicated")
        shards[shard_name] = (header, data_base, path)

    tensor_names = sorted(name for name in weight_map if isinstance(name, str))
    if len(tensor_names) != len(weight_map):
        raise MergeContractError("Qwen index contains a non-string tensor name")
    seen: set[str] = set()
    tensor_sources: dict[str, TensorSource] = {}
    output_header: OrderedDict[str, Mapping[str, Any]] = OrderedDict()
    derivation = source.get("derivation")
    if not isinstance(derivation, Mapping):
        raise MergeContractError("Qwen derivation metadata is missing")
    output_metadata = derivation.get("metadata")
    if output_metadata is not None:
        if not isinstance(output_metadata, Mapping):
            raise MergeContractError("Qwen output metadata contract is invalid")
        output_header["__metadata__"] = dict(output_metadata)
    output_offset = 0
    for name in tensor_names:
        shard_name = weight_map[name]
        if not isinstance(shard_name, str) or shard_name not in shards:
            raise MergeContractError(f"Qwen index references an unpinned shard: {name}")
        header, data_base, path = shards[shard_name]
        spec = header.get(name)
        if not isinstance(spec, Mapping):
            raise MergeContractError(f"indexed tensor is missing from its shard: {name}")
        offsets = spec["data_offsets"]
        start, end = offsets
        tensor_sources[name] = TensorSource(
            path=path,
            data_base=data_base,
            start=start,
            end=end,
            dtype=spec["dtype"],
            shape=tuple(spec["shape"]),
        )
        output_header[name] = OrderedDict(
            (
                ("dtype", spec["dtype"]),
                ("shape", spec["shape"]),
                ("data_offsets", [output_offset, output_offset + end - start]),
            )
        )
        output_offset += end - start
        seen.add(name)

    all_shard_tensors: set[str] = set()
    for shard_header, _, _ in shards.values():
        shard_names = {name for name in shard_header if name != "__metadata__"}
        if all_shard_tensors & shard_names:
            raise MergeContractError("Qwen source shards contain duplicate tensors")
        all_shard_tensors.update(shard_names)
    if seen != all_shard_tensors:
        raise MergeContractError("Qwen index and shard tensor sets differ")
    return output_header, tensor_sources


def _encode_header(header: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(
        header, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return encoded + b" " * (-len(encoded) % 8)


def _copy_span(
    source: BinaryIO,
    destination: BinaryIO,
    digest: Any,
    length: int,
) -> None:
    remaining = length
    while remaining:
        chunk = source.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise MergeContractError("source shard ended during tensor copy")
        destination.write(chunk)
        digest.update(chunk)
        remaining -= len(chunk)


def merge_from_manifest(
    manifest_path: Path,
    source_root: Path,
    output_path: Path,
) -> Mapping[str, Any]:
    """Create the exact manifest-gated Qwen single-file encoder."""

    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise MergeContractError("model artifact manifest is invalid")
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, Mapping)
        and artifact.get("id") == "qwen3-4b-text-encoder"
    ]
    if len(matches) != 1:
        raise MergeContractError("Qwen artifact record is missing or duplicated")
    artifact = matches[0]
    source = artifact.get("source")
    if not isinstance(source, Mapping) or source.get("type") != (
        "deterministic_official_shard_merge"
    ):
        raise MergeContractError("Qwen source derivation contract is invalid")
    expected_bytes = artifact.get("expected_bytes")
    expected_hash = artifact.get("sha256")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
    ):
        raise MergeContractError("Qwen output gate is invalid")

    output_path = output_path.resolve()
    if output_path.exists():
        raise MergeContractError("refusing to overwrite an existing output")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header, tensor_sources = _build_tensor_sources(source_root, source)
    encoded_header = _encode_header(header)
    derivation = source.get("derivation")
    if not isinstance(derivation, Mapping):
        raise MergeContractError("Qwen derivation metadata is missing")
    if derivation.get("tensor_order") != "lexicographic_tensor_name" or (
        derivation.get("metadata") is not None
    ):
        raise MergeContractError("Qwen deterministic serialization contract drifted")
    if len(tensor_sources) != derivation.get("expected_tensor_count"):
        raise MergeContractError("derived Qwen tensor count does not match manifest")
    if len(encoded_header) != derivation.get("expected_header_bytes"):
        raise MergeContractError("derived Qwen header size does not match manifest")
    prefix = struct.pack("<Q", len(encoded_header))
    calculated_bytes = 8 + len(encoded_header) + sum(
        tensor.end - tensor.start for tensor in tensor_sources.values()
    )
    if calculated_bytes != expected_bytes:
        raise MergeContractError("derived Qwen output size does not match manifest")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{output_path.name}.", suffix=".partial",
            dir=output_path.parent, delete=False
        ) as destination:
            temporary_name = destination.name
            digest = hashlib.sha256()
            destination.write(prefix)
            destination.write(encoded_header)
            digest.update(prefix)
            digest.update(encoded_header)
            open_sources: dict[Path, BinaryIO] = {}
            try:
                for name in sorted(tensor_sources):
                    tensor = tensor_sources[name]
                    handle = open_sources.get(tensor.path)
                    if handle is None:
                        handle = tensor.path.open("rb")
                        open_sources[tensor.path] = handle
                    handle.seek(tensor.data_base + tensor.start)
                    _copy_span(
                        handle, destination, digest, tensor.end - tensor.start
                    )
            finally:
                for handle in open_sources.values():
                    handle.close()
            destination.flush()
            os.fsync(destination.fileno())
        if digest.hexdigest() != expected_hash:
            raise MergeContractError("derived Qwen output SHA-256 does not match manifest")
        if Path(temporary_name).stat().st_size != expected_bytes:
            raise MergeContractError("derived Qwen output byte size drifted")
        try:
            os.link(temporary_name, output_path)
        except FileExistsError as exc:
            raise MergeContractError("refusing to overwrite an existing output") from exc
        Path(temporary_name).unlink()
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)

    return {
        "status": "official_qwen_derivation_verified",
        "output_bytes": expected_bytes,
        "output_sha256": expected_hash,
        "tensor_count": len(tensor_sources),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "models.json",
        help="Pinned candidate models.json contract.",
    )
    parser.add_argument(
        "--source-dir", type=Path, required=True,
        help="Directory containing the pinned official BFL shard tree.",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="New qwen_3_4b.safetensors destination; must not exist.",
    )
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    print(
        json.dumps(
            merge_from_manifest(
                arguments.manifest, arguments.source_dir, arguments.output
            ),
            sort_keys=True,
        )
    )

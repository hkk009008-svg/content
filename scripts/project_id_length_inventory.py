#!/usr/bin/env python3
"""Measure project-ID length headroom without reading project contents."""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shlex
import sys


DEFAULT_LIMIT = 128
PROJECT_DIR_CANDIDATES = ("domain/projects", "projects")
CANONICAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _generated_id_contract(source_path: Path) -> tuple[int, str]:
    """Read ``new_id`` structurally and return its slice length and format."""

    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "new_id"
        ),
        None,
    )
    if function is None or len(function.body) != 1:
        raise RuntimeError("new_id must remain one structural return")
    returned = function.body[0]
    if not isinstance(returned, ast.Return):
        raise RuntimeError("new_id must return uuid.uuid4().hex[:N]")
    expression = returned.value
    if not isinstance(expression, ast.Subscript):
        raise RuntimeError("new_id must return uuid.uuid4().hex[:N]")
    if not (
        isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "hex"
        and isinstance(expression.slice, ast.Slice)
        and expression.slice.lower is None
        and expression.slice.step is None
        and isinstance(expression.slice.upper, ast.Constant)
        and isinstance(expression.slice.upper.value, int)
    ):
        raise RuntimeError("new_id must return uuid.uuid4().hex[:N]")
    uuid_call = expression.value.value
    if not (
        isinstance(uuid_call, ast.Call)
        and not uuid_call.args
        and not uuid_call.keywords
        and isinstance(uuid_call.func, ast.Attribute)
        and uuid_call.func.attr == "uuid4"
        and isinstance(uuid_call.func.value, ast.Name)
        and uuid_call.func.value.id == "uuid"
    ):
        raise RuntimeError("new_id must return uuid.uuid4().hex[:N]")
    return expression.slice.upper.value, "lowercase_hex"


def _filesystem_name_max(root: Path) -> int:
    return int(os.pathconf(root, "PC_NAME_MAX"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    root = args.root.resolve()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")

    storage_roots = [
        root / relative
        for relative in PROJECT_DIR_CANDIDATES
        if (root / relative).is_dir()
    ]
    directory_names = [
        entry.name
        for storage_root in storage_roots
        for entry in storage_root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    ]
    char_lengths = [len(name) for name in directory_names]
    byte_lengths = [len(name.encode("utf-8")) for name in directory_names]
    observed_max_chars = max(char_lengths, default=0)
    observed_max_bytes = max(byte_lengths, default=0)
    noncanonical_count = sum(
        CANONICAL_ID.fullmatch(name) is None
        for name in directory_names
    )
    over_limit_count = sum(
        len(name) > args.limit or len(name.encode("utf-8")) > args.limit
        for name in directory_names
    )

    generated_length, generated_format = _generated_id_contract(
        root / "domain/project_manager.py"
    )
    name_max = _filesystem_name_max(root)
    invocation = shlex.join(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--root",
            str(root),
            "--limit",
            str(args.limit),
        ]
    )

    print(f"command={invocation}")
    print(f"root={root}")
    print(
        "storage_roots="
        + ",".join(
            str(path.relative_to(root))
            for path in storage_roots
        )
    )
    print(f"filesystem_name_max_bytes={name_max}")
    print(f"existing_project_dir_count={len(directory_names)}")
    print(f"existing_project_id_max_chars={observed_max_chars}")
    print(f"existing_project_id_max_bytes={observed_max_bytes}")
    print(f"existing_project_id_noncanonical_count={noncanonical_count}")
    print(f"existing_project_id_over_limit_count={over_limit_count}")
    print(f"generated_project_id_length={generated_length}")
    print(f"generated_project_id_format={generated_format}")
    print(f"chosen_project_id_limit={args.limit}")
    print(f"filesystem_byte_headroom={name_max - args.limit}")
    print(f"observed_char_headroom={args.limit - observed_max_chars}")
    print(f"observed_byte_headroom={args.limit - observed_max_bytes}")
    print(f"generated_id_headroom={args.limit - generated_length}")

    if args.limit > name_max:
        return 1
    if over_limit_count or noncanonical_count:
        return 1
    if generated_length > args.limit:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

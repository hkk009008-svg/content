#!/usr/bin/env python3
"""Generate a deterministic, static inventory of product network surfaces."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

OUTPUT = Path("docs/generated/product_surface_inventory.json")
FRONTEND_HELPER = Path(__file__).with_name("product_surface_frontend_inventory.mjs")
FRONTEND_TIMEOUT_SECONDS = 30
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
SHORTHANDS = {"delete", "get", "head", "options", "patch", "post", "put"}
EXCLUDED_DIRS = {"__tests__", "dist", "node_modules", "test", "tests"}
TRANSPORT_KINDS = {"fetch", "event_source"}
OPERATION_KINDS = {
    "direct_transport",
    "one_hop_wrapper_call",
    "unknown_wrapper_call",
    "shadowed_fetch_call",
    "shadowed_event_source_call",
}
OBSERVATIONS = {"observed", "not_observed", "unknown"}
UNRESOLVED_REASONS = {
    "aliased_transport": {"aliased transports are not expanded"},
    "aliased_wrapper": {"same-file wrapper aliases are not expanded"},
    "dynamic_transport_url": {
        "transport URL is not a string, template, or module literal constant"
    },
    "dynamic_fetch_method": {
        "fetch options is not an inline object literal",
        "fetch method is not a static HTTP method",
    },
    "dynamic_wrapper_call_url": {
        "safe wrapper call URL is not statically resolvable"
    },
    "shadowed_fetch_call": {
        "fetch call resolves through a local, imported, parameter, method, or object binding"
    },
    "shadowed_event_source_call": {
        "EventSource construction resolves through a local, imported, parameter, method, or object binding"
    },
    "unknown_wrapper_call": {
        "aliased transport call",
        "fetch options is not an inline object literal",
        "fetch method is not a static HTTP method",
        "wrapper transport method is not statically resolved",
        "wrapper URL parameter is transformed",
        "wrapper URL parameter shape is unsupported",
        "wrapper contains multiple direct transports",
        "wrapper reaches transport through another local wrapper",
        "wrapper is an alias of another local wrapper",
        "imported wrapper call",
    },
}

class FrontendInventoryError(RuntimeError):
    """The TypeScript helper could not produce a complete trusted fact set."""


@dataclass(frozen=True)
class _TypeScriptSourceFacts:
    utf16_length: int
    line_starts: tuple[int, ...]
    code_point_boundaries: frozenset[int]

    def reference_line(self, offset: int, label: str) -> int:
        if (
            not self.utf16_length
            or offset not in self.code_point_boundaries
            or offset >= self.utf16_length
        ):
            _schema_error(f"{label} offset is outside the TypeScript source")
        return bisect_right(self.line_starts, offset)


def _source(path: str, line: int) -> dict[str, Any]:
    return {"path": path, "line": line}

def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _assign_ids(
    rows: list[dict[str, Any]],
    prefix: str,
    keys: Sequence[str],
    *,
    group_by_source: bool = False,
) -> None:
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for row in rows:
        identity = tuple(_compact(row.get(key)) for key in keys)
        source_scope = row["source"]["path"] if group_by_source else ""
        groups.setdefault((source_scope, identity), []).append(row)
    for (_, identity), group in groups.items():
        group.sort(key=lambda row: (row["source"]["path"], row["source"]["line"]))
        for ordinal, row in enumerate(group, 1):
            suffix = ordinal if len(group) > 1 else None
            digest = hashlib.sha256(
                _compact((row["source"]["path"], identity, suffix)).encode()
            ).hexdigest()[:16]
            if prefix == "route":
                handler = re.sub(r"[^A-Za-z0-9_.-]+", "-", row["handler"]).strip("-")
                row["id"] = f"route:{handler}:{digest}"
            else:
                row["id"] = f"{prefix}:{digest}"

def _unknown(
    rows: list[dict[str, Any]],
    domain: str,
    kind: str,
    reason: str,
    path: str,
    line: int,
    expression: str,
    owner: str | None = None,
) -> None:
    row = {
        "domain": domain,
        "kind": kind,
        "reason": reason,
        "expression": " ".join(expression.split()),
        "source": _source(path, line),
    }
    if owner:
        row["owner"] = owner
    rows.append(row)

def _positional(rule: str, frontend: bool = False) -> str:
    if frontend and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", rule):
        parsed = urlsplit(rule)
        rule = parsed.path or "/"
    rule = rule.split("?", 1)[0].split("#", 1)[0]
    pattern = r"\{\d+\}" if frontend else r"<(?:[^<>:]+:)?[^<>]+>"
    index = 0

    def replace(_: re.Match[str]) -> str:
        nonlocal index
        index += 1
        return f"{{{index}}}"

    return re.sub(pattern, replace, rule)

def _query_keys(url: str | None) -> list[str]:
    if not url or "?" not in url:
        return []
    query = url.split("?", 1)[1].split("#", 1)[0]
    return sorted(
        {
            match.group(1)
            for match in re.finditer(
                r"(?:^|&)([A-Za-z0-9_.~-]+)(?:=|&|$)", query
            )
        }
    )

def _ast_text(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or type(node).__name__

def _methods(node: ast.AST | None) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)) or not node.elts:
        return None
    values: list[str] = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        values.append(item.value.upper())
    return sorted(set(values)) if all(value in HTTP_METHODS for value in values) else None

def _backend(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = root / "web_server.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    routes: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
            ):
                continue
            attr = decorator.func.attr
            if attr in SHORTHANDS:
                _unknown(
                    unresolved, "backend", "app_shorthand_decorator",
                    "app shorthand decorators are outside the recognized @app.route subset",
                    "web_server.py", decorator.lineno, _ast_text(source, decorator), node.name,
                )
                continue
            if attr != "route":
                continue
            rule_node = decorator.args[0] if decorator.args else None
            rule = (
                rule_node.value
                if isinstance(rule_node, ast.Constant) and isinstance(rule_node.value, str)
                else None
            )
            if rule is None:
                _unknown(
                    unresolved, "backend", "dynamic_route_rule",
                    "@app.route rule is not a string literal", "web_server.py",
                    decorator.lineno, _ast_text(source, decorator), node.name,
                )
                continue
            methods_node = next(
                (kw.value for kw in decorator.keywords if kw.arg == "methods"), None
            )
            declared = ["GET"] if methods_node is None else _methods(methods_node)
            if declared is None:
                _unknown(
                    unresolved, "backend", "dynamic_route_methods",
                    "@app.route methods is not a non-empty literal method list",
                    "web_server.py", decorator.lineno, _ast_text(source, decorator), node.name,
                )
                continue
            for method in declared:
                routes.append({
                    "handler": node.name, "kind": "flask_route", "method": method,
                    "path_shape": _positional(rule), "rule": rule,
                    "source": _source("web_server.py", decorator.lineno),
                })
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Attribute) or call.func.attr not in {
            "add_url_rule", "register_blueprint"
        }:
            continue
        kind = call.func.attr
        _unknown(
            unresolved, "backend", kind,
            f"{kind} is outside the recognized static decorator subset",
            "web_server.py", call.lineno, _ast_text(source, call),
        )
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        call = node.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "Flask"
            and any(isinstance(target, ast.Name) and target.id == "app" for target in targets)
        ):
            continue
        kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        folder_node = kwargs.get("static_folder")
        if isinstance(folder_node, ast.Constant) and folder_node.value in {None, False}:
            continue
        folder = (
            "static" if folder_node is None else folder_node.value
            if isinstance(folder_node, ast.Constant) and isinstance(folder_node.value, str)
            else None
        )
        url_node = kwargs.get("static_url_path")
        url = (
            "/" + Path(folder).name if url_node is None and folder is not None
            else url_node.value
            if isinstance(url_node, ast.Constant) and isinstance(url_node.value, str)
            else None
        )
        if folder is None or url is None:
            _unknown(
                unresolved, "backend", "dynamic_flask_static_configuration",
                "Flask static_folder/static_url_path is not fully literal",
                "web_server.py", node.lineno, _ast_text(source, call),
            )
            continue
        rule = (url.rstrip("/") if url else "") + "/<path:filename>"
        routes.append({
            "handler": "static", "kind": "flask_static_constructor", "method": "GET",
            "path_shape": _positional(rule), "rule": rule,
            "source": _source("web_server.py", node.lineno),
        })
    _assign_ids(routes, "route", ("handler", "kind", "method", "path_shape", "rule"))
    return routes, unresolved

def _frontend_files(root: Path) -> list[str]:
    base = root / "web" / "src"
    if not base.exists():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in base.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not any(part in EXCLUDED_DIRS for part in path.relative_to(base).parts[:-1])
        and not re.search(r"\.(?:spec|test)\.(?:ts|tsx)$", path.name)
    )


def _schema_error(detail: str) -> None:
    raise FrontendInventoryError(f"invalid TypeScript frontend schema: {detail}")


def _exact_keys(
    row: Any,
    required: set[str],
    optional: set[str],
    label: str,
) -> dict[str, Any]:
    if type(row) is not dict:
        _schema_error(f"{label} must be an object")
    keys = set(row)
    if keys - required - optional:
        _schema_error(f"{label} has unknown keys")
    if required - keys:
        _schema_error(f"{label} is missing required keys")
    return row


def _normalized_text(
    value: Any,
    label: str,
    *,
    allow_empty: bool = False,
) -> str:
    if type(value) is not str or (not allow_empty and not value):
        _schema_error(f"{label} must be a string")
    if " ".join(value.split()) != value:
        _schema_error(f"{label} is not normalized")
    return value


def _name(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or any(ord(char) < 32 for char in value)
    ):
        _schema_error(f"{label} must be a nonempty name")
    return value


def _typescript_source_facts(text: str) -> _TypeScriptSourceFacts:
    line_starts = [0]
    boundaries = {0}
    position = 0
    index = 0
    while index < len(text):
        character = text[index]
        position += 2 if ord(character) > 0xFFFF else 1
        boundaries.add(position)
        if character == "\r":
            if index + 1 < len(text) and text[index + 1] == "\n":
                index += 1
                position += 1
                boundaries.add(position)
            line_starts.append(position)
        elif character in {"\n", "\u2028", "\u2029"}:
            line_starts.append(position)
        index += 1
    return _TypeScriptSourceFacts(
        utf16_length=position,
        line_starts=tuple(line_starts),
        code_point_boundaries=frozenset(boundaries),
    )


def _frontend_source_facts(
    root: Path,
    source_paths: Sequence[str],
) -> dict[str, _TypeScriptSourceFacts]:
    resolved_root = root.resolve(strict=True)
    facts: dict[str, _TypeScriptSourceFacts] = {}
    identities: set[tuple[int, int]] = set()
    for source_path in source_paths:
        candidate = resolved_root.joinpath(*source_path.split("/"))
        try:
            resolved = candidate.resolve(strict=True)
            stat = candidate.stat()
        except (OSError, RuntimeError) as exc:
            raise FrontendInventoryError(
                f"invalid TypeScript frontend schema: source file is unavailable: {source_path}"
            ) from exc
        identity = (stat.st_dev, stat.st_ino)
        if resolved != candidate or identity in identities:
            _schema_error(f"payload.files contains a source path alias: {source_path}")
        identities.add(identity)
        try:
            text = candidate.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FrontendInventoryError(
                f"invalid TypeScript frontend schema: source file is unreadable: {source_path}"
            ) from exc
        facts[source_path] = _typescript_source_facts(text)
    return facts


def _source_fact(
    value: Any,
    sources: dict[str, _TypeScriptSourceFacts],
    label: str,
) -> dict[str, Any]:
    source = _exact_keys(value, {"path", "line"}, set(), f"{label}.source")
    source_path = source["path"]
    if (
        type(source_path) is not str
        or not source_path
        or source_path not in sources
        or source_path.startswith("/")
        or "\\" in source_path
        or any(part in {"", ".", ".."} for part in source_path.split("/"))
    ):
        _schema_error(f"{label}.source.path is invalid")
    if type(source["line"]) is not int or source["line"] <= 0:
        _schema_error(f"{label}.source.line must be a positive integer")
    if source["line"] > len(sources[source_path].line_starts):
        _schema_error(f"{label}.source.line is outside the TypeScript source")
    return source


def _url(value: Any, label: str) -> None:
    if value is not None and type(value) is not str:
        _schema_error(f"{label} must be a string or null")


def _reference(
    value: Any,
    sources: dict[str, _TypeScriptSourceFacts],
    label: str,
    *,
    nullable: bool,
) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or not value:
        _schema_error(f"{label} must be a transport reference")
    ref_path, separator, offset = value.rpartition(":")
    if (
        not separator
        or ref_path not in sources
        or not re.fullmatch(r"(?:0|[1-9][0-9]*)", offset)
    ):
        _schema_error(f"{label} has invalid transport-reference shape")
    try:
        numeric_offset = int(offset)
    except ValueError:
        _schema_error(f"{label} has invalid transport-reference shape")
    sources[ref_path].reference_line(numeric_offset, label)
    return value


def _method(value: Any, label: str, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or value not in HTTP_METHODS:
        _schema_error(f"{label} must be a supported HTTP method")
    return value


def _validate_transport(
    row: Any,
    sources: dict[str, _TypeScriptSourceFacts],
    index: int,
) -> str:
    label = f"transports[{index}]"
    kind = row.get("kind") if type(row) is dict else None
    if type(kind) is not str or kind not in TRANSPORT_KINDS:
        _schema_error(f"{label}.kind is unsupported")
    required = {
        "_transport_ref",
        "kind",
        "method",
        "non_2xx_observation",
        "non_2xx_observation_applicability",
        "source",
        "url_expression",
        "url_template",
    }
    if kind == "event_source":
        required.add("transport_error_observation")
    _exact_keys(row, required, {"enclosing_function"}, label)
    ref = _reference(
        row["_transport_ref"], sources, f"{label}._transport_ref", nullable=False
    )
    source = _source_fact(row["source"], sources, label)
    if ref.rpartition(":")[0] != row["source"]["path"]:
        _schema_error(f"{label} reference/source paths disagree")
    ref_path, _, offset = ref.rpartition(":")
    if sources[ref_path].reference_line(
        int(offset), f"{label}._transport_ref"
    ) != source["line"]:
        _schema_error(f"{label} reference/source lines disagree")
    _normalized_text(row["url_expression"], f"{label}.url_expression", allow_empty=True)
    _url(row["url_template"], f"{label}.url_template")
    if "enclosing_function" in row:
        _name(row["enclosing_function"], f"{label}.enclosing_function")
    if kind == "fetch":
        _method(row["method"], f"{label}.method", nullable=True)
        observation = row["non_2xx_observation"]
        if type(observation) is not str or observation not in OBSERVATIONS:
            _schema_error(f"{label}.non_2xx_observation is invalid")
        if row["non_2xx_observation_applicability"] != "applicable":
            _schema_error(f"{label} has invalid observation applicability")
    else:
        if row["method"] != "GET" or row["non_2xx_observation"] is not None:
            _schema_error(f"{label} has invalid EventSource method/observation")
        if row["non_2xx_observation_applicability"] != "not_applicable":
            _schema_error(f"{label} has invalid EventSource applicability")
        error_observation = row["transport_error_observation"]
        if type(error_observation) is not str or error_observation not in OBSERVATIONS:
            _schema_error(f"{label}.transport_error_observation is invalid")
    assert ref is not None
    return ref


def _validate_operation(
    row: Any,
    sources: dict[str, _TypeScriptSourceFacts],
    transport_refs: dict[str, dict[str, Any]],
    index: int,
) -> None:
    label = f"operations[{index}]"
    kind = row.get("kind") if type(row) is dict else None
    if type(kind) is not str or kind not in OPERATION_KINDS:
        _schema_error(f"{label}.kind is unsupported")
    required = {"_transport_ref", "kind", "method", "source", "url_template"}
    optional: set[str] = set()
    if kind in {"one_hop_wrapper_call", "unknown_wrapper_call"}:
        required.add("expanded_wrapper")
    if kind in {"shadowed_fetch_call", "shadowed_event_source_call"}:
        optional.add("enclosing_function")
    _exact_keys(row, required, optional, label)
    source = _source_fact(row["source"], sources, label)
    _url(row["url_template"], f"{label}.url_template")
    if "expanded_wrapper" in row:
        _name(row["expanded_wrapper"], f"{label}.expanded_wrapper")
    if "enclosing_function" in row:
        _name(row["enclosing_function"], f"{label}.enclosing_function")
    if kind == "direct_transport":
        _method(row["method"], f"{label}.method", nullable=True)
        ref = _reference(
            row["_transport_ref"], sources, f"{label}._transport_ref", nullable=False
        )
    elif kind == "one_hop_wrapper_call":
        _method(row["method"], f"{label}.method", nullable=False)
        ref = _reference(
            row["_transport_ref"], sources, f"{label}._transport_ref", nullable=False
        )
    elif kind == "unknown_wrapper_call":
        _method(row["method"], f"{label}.method", nullable=True)
        ref = _reference(
            row["_transport_ref"], sources, f"{label}._transport_ref", nullable=True
        )
        if ref is None and row["method"] is not None:
            _schema_error(f"{label}.method requires a transport reference")
    else:
        if row["method"] is not None or row["_transport_ref"] is not None:
            _schema_error(f"{label} must not claim a method or transport reference")
        ref = None
    if ref is not None:
        if ref not in transport_refs:
            _schema_error(f"{label} has a dangling transport reference")
        transport = transport_refs[ref]
        if transport["path"] != row["source"]["path"]:
            _schema_error(f"{label} crosses frontend source files")
        if row["method"] != transport["method"]:
            _schema_error(f"{label}.method contradicts its transport reference")
        if kind == "direct_transport":
            if source["line"] != transport["line"]:
                _schema_error(
                    f"{label}.source.line contradicts its direct transport reference"
                )
            if row["url_template"] != transport["url_template"]:
                _schema_error(
                    f"{label}.url_template contradicts its direct transport reference"
                )


def _validate_unresolved(
    row: Any,
    sources: dict[str, _TypeScriptSourceFacts],
    index: int,
) -> None:
    label = f"unresolved[{index}]"
    unresolved = _exact_keys(
        row,
        {"domain", "expression", "kind", "reason", "source"},
        {"owner"},
        label,
    )
    if unresolved["domain"] != "frontend":
        _schema_error(f"{label}.domain is invalid")
    kind = unresolved["kind"]
    if type(kind) is not str or kind not in UNRESOLVED_REASONS:
        _schema_error(f"{label}.kind is unsupported")
    reason = unresolved["reason"]
    if type(reason) is not str or reason not in UNRESOLVED_REASONS[kind]:
        _schema_error(f"{label}.reason is invalid")
    _normalized_text(unresolved["expression"], f"{label}.expression", allow_empty=True)
    _source_fact(unresolved["source"], sources, label)
    if "owner" in unresolved:
        _name(unresolved["owner"], f"{label}.owner")
    if kind in {
        "aliased_transport",
        "aliased_wrapper",
        "dynamic_wrapper_call_url",
        "unknown_wrapper_call",
    } and "owner" not in unresolved:
        _schema_error(f"{label}.owner is required")


def _validate_frontend_payload(payload: Any, root: Path) -> dict[str, Any]:
    top = _exact_keys(
        payload,
        {
            "files",
            "operations",
            "parser",
            "transports",
            "typescript_version",
            "unresolved",
        },
        set(),
        "payload",
    )
    if top["parser"] != "TypeScript compiler API":
        _schema_error("payload.parser is invalid")
    version = top["typescript_version"]
    if type(version) is not str or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version
    ):
        _schema_error("payload.typescript_version is invalid")
    expected_files = _frontend_files(root)
    if type(top["files"]) is not list or top["files"] != expected_files:
        _schema_error("payload.files does not match the declared source scope")
    for key in ("transports", "operations", "unresolved"):
        if type(top[key]) is not list:
            _schema_error(f"payload.{key} must be a list")
    sources = _frontend_source_facts(root, expected_files)
    transport_refs: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(top["transports"]):
        ref = _validate_transport(row, sources, index)
        if ref in transport_refs:
            _schema_error("transport references must be unique")
        transport_refs[ref] = {
            "line": row["source"]["line"],
            "method": row["method"],
            "path": row["source"]["path"],
            "url_template": row["url_template"],
        }
    for index, row in enumerate(top["operations"]):
        _validate_operation(row, sources, transport_refs, index)
    for index, row in enumerate(top["unresolved"]):
        _validate_unresolved(row, sources, index)
    return top


def _decode_frontend_json(raw: str) -> Any:
    def object_without_duplicates(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError(f"duplicate JSON key {key}")
            decoded[key] = value
        return decoded

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")

    try:
        return json.loads(
            raw,
            object_pairs_hook=object_without_duplicates,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FrontendInventoryError(
            "TypeScript frontend parser returned invalid JSON"
        ) from exc


def _frontend_payload(root: Path) -> dict[str, Any]:
    command = ["node", str(FRONTEND_HELPER), "--root", str(root)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=FRONTEND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise FrontendInventoryError(
            f"TypeScript frontend parser timed out after {FRONTEND_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise FrontendInventoryError(
            f"could not launch Node/TypeScript frontend parser: {exc}"
        ) from exc
    if completed.returncode:
        detail = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise FrontendInventoryError(f"TypeScript frontend parser failed: {detail}")
    payload = _decode_frontend_json(completed.stdout)
    return _validate_frontend_payload(payload, root)

def _frontend(root: Path) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str,
]:
    payload = _frontend_payload(root)
    transports = [dict(row) for row in payload["transports"]]
    operations = [dict(row) for row in payload["operations"]]
    unresolved = [dict(row) for row in payload["unresolved"]]
    transport_refs: dict[str, dict[str, Any]] = {}
    for row in transports:
        ref = row.pop("_transport_ref")
        url = row.get("url_template")
        row["path_shape"] = _positional(url, True) if url is not None else None
        row["query_keys"] = _query_keys(url)
        transport_refs[ref] = row
    _assign_ids(
        transports,
        "frontend-transport",
        ("kind", "method", "path_shape", "url_expression", "url_template", "enclosing_function"),
        group_by_source=True,
    )
    for row in operations:
        ref = row.pop("_transport_ref")
        url = row.get("url_template")
        row["path_shape"] = _positional(url, True) if url is not None else None
        row["query_keys"] = _query_keys(url)
        row["transport_id"] = transport_refs[ref]["id"] if ref is not None else None
    _assign_ids(
        operations,
        "frontend-operation",
        ("kind", "method", "path_shape", "query_keys", "transport_id",
         "expanded_wrapper", "url_template"),
        group_by_source=True,
    )
    return transports, operations, unresolved, payload["typescript_version"]

def _join(routes: Sequence[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> None:
    contracts: dict[tuple[str, str], list[str]] = {}
    for route in routes:
        contracts.setdefault((route["method"], route["path_shape"]), []).append(route["id"])
    for row in rows:
        method, shape = row.get("method"), row.get("path_shape")
        if method is None or shape is None or not shape.startswith("/"):
            row["backend_route_ids"], row["route_match"] = [], "unknown"
            continue
        matches = sorted(contracts.get((method, shape), []))
        row["backend_route_ids"] = matches
        row["route_match"] = "matched" if matches else "unmatched"

def build_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    transports, operations, frontend_unresolved, typescript_version = _frontend(root)
    routes, unresolved = _backend(root)
    unresolved.extend(frontend_unresolved)
    _join(routes, transports)
    _join(routes, operations)
    _assign_ids(
        unresolved,
        "unresolved",
        ("domain", "kind", "reason", "expression", "owner"),
    )
    routes.sort(
        key=lambda row: (row["path_shape"], row["method"], row["handler"], row["id"])
    )
    transports.sort(key=lambda row: row["id"])
    operations.sort(key=lambda row: row["id"])
    unresolved.sort(key=lambda row: row["id"])
    return {
        "schema_version": 1,
        "scope": {
            "backend": {
                "analysis": "Python AST; web_server.py is parsed and never imported",
                "entrypoint": "web_server.py",
                "included": ["literal @app.route rules and literal methods (default GET)",
                             "Flask constructor static endpoint synthesized from literal arguments"],
                "unresolved": ["dynamic rules/methods/static configuration",
                               "add_url_rule, register_blueprint, and app shorthand decorators"],
            },
            "frontend": {
                "analysis": "TypeScript compiler API Program and TypeChecker; application modules are parsed and never imported or executed",
                "parser_version": typescript_version,
                "root": "web/src",
                "extensions": [".ts", ".tsx"],
                "excluded": ["**/*.{test,spec}.{ts,tsx}",
                             "**/{__tests__,test,tests,dist,node_modules}/**"],
                "included": ["direct global fetch and new EventSource calls",
                             "module literal API bases, literal/template URLs, inline literal methods",
                             "same-file one-hop wrappers with one transport and an unmodified URL parameter"],
                "declarative_resource_urls": {
                    "status": "excluded",
                    "reason": "JSX src/href/poster and CSS resource loads are outside executable call-expression schema v1",
                },
                "unresolved": [
                    "calls through local, imported, parameter, method, object, or aliased transport bindings",
                    "dynamic URLs/methods; imported, aliased, transformed, multi-hop, or multi-transport wrappers"],
            },
            "matching": {
                "definition": "HTTP method plus positional path shape; query is stripped before matching",
                "placeholders": "backend <converter:name> and frontend interpolation normalize to {1}, {2}, ...",
                "query_keys": "static query keys are retained separately",
            },
            "non_2xx_observation": {
                "states": ["observed", "not_observed", "unknown"],
                "definition": "fetch is observed only when the same bound response has .ok read or a direct .status-to-status-code comparison in its enclosing function; catch/json alone do not count",
                "event_source": "not applicable; transport_error_observation separately records onerror/error-listener presence",
            },
            "implicit_flask_methods": "automatic HEAD and OPTIONS are excluded",
        },
        "routes": routes,
        "frontend_transports": transports,
        "frontend_operations": operations,
        "unresolved": unresolved,
    }

def render_inventory(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

def _counts(inventory: dict[str, Any]) -> str:
    keys = ("routes", "frontend_transports", "frontend_operations", "unresolved")
    return " ".join(f"{key}={len(inventory[key])}" for key in keys)

def _resolved_output(root: Path, requested: Path) -> Path:
    output = (requested if requested.is_absolute() else root / requested).resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("output must resolve inside root") from exc
    return output

def _atomic_write(output: Path, rendered: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        output = _resolved_output(root, args.output)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    try:
        inventory = build_inventory(root)
    except FrontendInventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = render_inventory(inventory)
    if args.stdout:
        sys.stdout.write(rendered)
        return 0
    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"STALE: missing {output}", file=sys.stderr)
            return 1
        if current != rendered:
            print(f"STALE: regenerate {output}", file=sys.stderr)
            return 1
        print(f"OK {output.relative_to(root)} {_counts(inventory)}")
        return 0
    try:
        _atomic_write(output, rendered)
    except OSError as exc:
        print(f"ERROR: could not atomically write {output}: {exc}", file=sys.stderr)
        return 1
    print(f"WROTE {output.relative_to(root)} {_counts(inventory)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

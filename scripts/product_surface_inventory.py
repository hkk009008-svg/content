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
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

OUTPUT = Path("docs/generated/product_surface_inventory.json")
FRONTEND_HELPER = Path(__file__).with_name("product_surface_frontend_inventory.mjs")
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
SHORTHANDS = {"delete", "get", "head", "options", "patch", "post", "put"}
EXCLUDED_DIRS = {"__tests__", "dist", "node_modules", "test", "tests"}

class FrontendInventoryError(RuntimeError):
    """The TypeScript helper could not produce a complete trusted fact set."""

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

def _frontend_payload(root: Path) -> dict[str, Any]:
    command = ["node", str(FRONTEND_HELPER), "--root", str(root)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise FrontendInventoryError(
            f"could not launch Node/TypeScript frontend parser: {exc}"
        ) from exc
    if completed.returncode:
        detail = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise FrontendInventoryError(f"TypeScript frontend parser failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise FrontendInventoryError("TypeScript frontend parser returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise FrontendInventoryError("TypeScript frontend parser returned no object")
    expected_files = _frontend_files(root)
    if (
        payload.get("parser") != "TypeScript compiler API"
        or not isinstance(payload.get("typescript_version"), str)
        or payload.get("files") != expected_files
    ):
        raise FrontendInventoryError(
            "TypeScript frontend parser returned incomplete or mismatched scope metadata"
        )
    for key in ("transports", "operations", "unresolved"):
        if not isinstance(payload.get(key), list) or not all(
            isinstance(row, dict) for row in payload[key]
        ):
            raise FrontendInventoryError(f"TypeScript frontend parser returned invalid {key}")
    return payload

def _frontend(root: Path) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str,
]:
    payload = _frontend_payload(root)
    allowed_sources = set(payload["files"])

    def checked(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        copied = [dict(row) for row in rows]
        for row in copied:
            origin = row.get("source")
            if not (
                isinstance(origin, dict)
                and origin.get("path") in allowed_sources
                and isinstance(origin.get("line"), int)
                and origin["line"] >= 1
            ):
                raise FrontendInventoryError(
                    f"TypeScript frontend parser returned invalid {kind} source"
                )
        return copied

    transports = checked(payload["transports"], "transport")
    operations = checked(payload["operations"], "operation")
    unresolved = checked(payload["unresolved"], "unresolved")
    transport_refs: dict[str, dict[str, Any]] = {}
    for row in transports:
        ref = row.pop("_transport_ref", None)
        url = row.get("url_template")
        if not isinstance(ref, str) or ref in transport_refs or not (
            url is None or isinstance(url, str)
        ):
            raise FrontendInventoryError("invalid TypeScript transport link")
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
        ref = row.pop("_transport_ref", None)
        if ref is not None and ref not in transport_refs:
            raise FrontendInventoryError("dangling TypeScript operation link")
        url = row.get("url_template")
        if not (url is None or isinstance(url, str)):
            raise FrontendInventoryError("invalid TypeScript operation URL")
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
    routes, unresolved = _backend(root)
    transports, operations, frontend_unresolved, typescript_version = _frontend(root)
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

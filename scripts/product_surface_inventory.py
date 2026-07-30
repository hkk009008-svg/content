#!/usr/bin/env python3
"""Generate a deterministic, static inventory of product network surfaces."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Sequence
from urllib.parse import urlsplit


OUTPUT = Path("docs/generated/product_surface_inventory.json")
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
SHORTHANDS = {"delete", "get", "head", "options", "patch", "post", "put"}
EXCLUDED_DIRS = {"__tests__", "dist", "node_modules", "test", "tests"}


class Function(NamedTuple):
    name: str
    params: tuple[str, ...]
    body_start: int
    body_end: int
    name_start: int
    form: str


class Transport(NamedTuple):
    start: int
    end: int
    kind: str
    url_expression: str
    method: str | None
    method_reason: str | None
    function: Function | None
    row: dict[str, Any]


def _source(path: str, line: int) -> dict[str, Any]:
    return {"path": path, "line": line}


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _assign_ids(
    rows: list[dict[str, Any]],
    prefix: str,
    keys: Sequence[str],
    *,
    fixed_path: str | None = None,
) -> None:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(_compact(row.get(key)) for key in keys), []).append(row)
    for identity, group in groups.items():
        group.sort(key=lambda row: (row["source"]["path"], row["source"]["line"]))
        for ordinal, row in enumerate(group, 1):
            path = fixed_path or row["source"]["path"]
            suffix = ordinal if len(group) > 1 else None
            digest = hashlib.sha256(_compact((path, identity, suffix)).encode()).hexdigest()[:16]
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
            for match in re.finditer(r"(?:^|&)([A-Za-z0-9_.~-]+)(?:=|&|$)", query)
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
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            base = decorator.func.value
            if not isinstance(base, ast.Name) or base.id != "app":
                continue
            attr = decorator.func.attr
            if attr in SHORTHANDS:
                _unknown(
                    unresolved,
                    "backend",
                    "app_shorthand_decorator",
                    "app shorthand decorators are outside the recognized @app.route subset",
                    "web_server.py",
                    decorator.lineno,
                    _ast_text(source, decorator),
                    node.name,
                )
                continue
            if attr != "route":
                continue
            rule_node = decorator.args[0] if decorator.args else None
            rule = rule_node.value if isinstance(rule_node, ast.Constant) and isinstance(rule_node.value, str) else None
            if rule is None:
                _unknown(
                    unresolved,
                    "backend",
                    "dynamic_route_rule",
                    "@app.route rule is not a string literal",
                    "web_server.py",
                    decorator.lineno,
                    _ast_text(source, decorator),
                    node.name,
                )
                continue
            methods_node = next(
                (keyword.value for keyword in decorator.keywords if keyword.arg == "methods"),
                None,
            )
            declared = ["GET"] if methods_node is None else _methods(methods_node)
            if declared is None:
                _unknown(
                    unresolved,
                    "backend",
                    "dynamic_route_methods",
                    "@app.route methods is not a non-empty literal method list",
                    "web_server.py",
                    decorator.lineno,
                    _ast_text(source, decorator),
                    node.name,
                )
                continue
            for method in declared:
                routes.append(
                    {
                        "handler": node.name,
                        "kind": "flask_route",
                        "method": method,
                        "path_shape": _positional(rule),
                        "rule": rule,
                        "source": _source("web_server.py", decorator.lineno),
                    }
                )
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Attribute) or call.func.attr not in {
            "add_url_rule",
            "register_blueprint",
        }:
            continue
        kind = call.func.attr
        _unknown(
            unresolved,
            "backend",
            kind,
            f"{kind} is outside the recognized static decorator subset",
            "web_server.py",
            call.lineno,
            _ast_text(source, call),
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
        folder = "static" if folder_node is None else (
            folder_node.value
            if isinstance(folder_node, ast.Constant) and isinstance(folder_node.value, str)
            else None
        )
        url_node = kwargs.get("static_url_path")
        url = (
            "/" + Path(folder).name
            if url_node is None and folder is not None
            else url_node.value
            if isinstance(url_node, ast.Constant) and isinstance(url_node.value, str)
            else None
        )
        if folder is None or url is None:
            _unknown(
                unresolved,
                "backend",
                "dynamic_flask_static_configuration",
                "Flask static_folder/static_url_path is not fully literal",
                "web_server.py",
                node.lineno,
                _ast_text(source, call),
            )
            continue
        rule = (url.rstrip("/") if url else "") + "/<path:filename>"
        routes.append(
            {
                "handler": "static",
                "kind": "flask_static_constructor",
                "method": "GET",
                "path_shape": _positional(rule),
                "rule": rule,
                "source": _source("web_server.py", node.lineno),
            }
        )
    _assign_ids(routes, "route", ("handler", "kind", "method", "path_shape", "rule"))
    return routes, unresolved


def _mask_typescript(source: str) -> str:
    """Blank comments and string/template contents while preserving positions."""
    chars = list(source)
    index = 0
    while index < len(chars):
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = len(source) if end < 0 else end
        elif source.startswith("/*", index):
            found = source.find("*/", index + 2)
            end = len(source) if found < 0 else found + 2
        elif source[index] in {"'", '"', "`"}:
            quote = source[index]
            end = index + 1
            while end < len(source):
                if source[end] == "\\":
                    end += 2
                    continue
                end += 1
                if source[end - 1] == quote:
                    break
        else:
            index += 1
            continue
        for position in range(index, min(end, len(chars))):
            if chars[position] != "\n":
                chars[position] = " "
        index = end
    return "".join(chars)


def _close(mask: str, opening: int, left: str, right: str) -> int | None:
    depth = 0
    for index in range(opening, len(mask)):
        if mask[index] == left:
            depth += 1
        elif mask[index] == right:
            depth -= 1
            if depth == 0:
                return index
    return None


def _arg_spans(mask: str, opening: int, closing: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = opening + 1
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    for index in range(start, closing):
        char = mask[index]
        if char in depths:
            depths[char] += 1
        elif char in pairs:
            depths[pairs[char]] -= 1
        elif char == "," and not any(depths.values()):
            spans.append((start, index))
            start = index + 1
    if start < closing or spans:
        spans.append((start, closing))
    return spans


def _call_at(mask: str, name_end: int) -> tuple[int, int, list[tuple[int, int]]] | None:
    opening = name_end
    while opening < len(mask) and mask[opening].isspace():
        opening += 1
    if opening >= len(mask) or mask[opening] != "(":
        return None
    closing = _close(mask, opening, "(", ")")
    return None if closing is None else (opening, closing, _arg_spans(mask, opening, closing))


def _decode_string(raw: str) -> str | None:
    try:
        value = ast.literal_eval(raw)
        return value if isinstance(value, str) else None
    except (SyntaxError, ValueError):
        return None


def _constants(source: str, mask: str) -> dict[str, str]:
    constants: dict[str, str] = {}
    depth = 0
    depth_at = [0] * (len(mask) + 1)
    for index, char in enumerate(mask):
        depth_at[index] = depth
        depth += char == "{"
        depth -= char == "}"
    for match in re.finditer(r"\bconst\s+([A-Za-z_$]\w*)\s*=", mask):
        if depth_at[match.start()] != 0:
            continue
        start = match.end()
        while start < len(source) and source[start].isspace():
            start += 1
        if start >= len(source) or source[start] not in {"'", '"'}:
            continue
        quote = source[start]
        end = start + 1
        while end < len(source):
            if source[end] == "\\":
                end += 2
                continue
            end += 1
            if source[end - 1] == quote:
                break
        value = _decode_string(source[start:end])
        if value is not None:
            constants[match.group(1)] = value
    return constants


def _template(raw: str, constants: dict[str, str]) -> str | None:
    body = raw[1:-1]
    output: list[str] = []
    cursor = 0
    number = 0
    for match in re.finditer(r"\$\{([^{}]*)\}", body):
        output.append(body[cursor : match.start()])
        expression = match.group(1).strip()
        if expression in constants:
            output.append(constants[expression])
        else:
            number += 1
            output.append(f"{{{number}}}")
        cursor = match.end()
    output.append(body[cursor:])
    value = "".join(output)
    return None if "${" in value else value


def _resolve_url(expression: str, constants: dict[str, str]) -> str | None:
    value = expression.strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return _decode_string(value)
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        return _template(value, constants)
    return constants.get(value)


def _method(options: str | None, constants: dict[str, str]) -> tuple[str | None, str | None]:
    if options is None or not options.strip() or options.strip() == "undefined":
        return "GET", None
    stripped = options.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None, "fetch options is not an inline object literal"
    masked = _mask_typescript(stripped)
    match = re.search(r"\bmethod\s*:", masked)
    if not match:
        return "GET", None
    start = match.end()
    while start < len(stripped) and stripped[start].isspace():
        start += 1
    if start < len(stripped) and stripped[start] in {"'", '"'}:
        quote = stripped[start]
        end = start + 1
        while end < len(stripped) and stripped[end] != quote:
            end += 2 if stripped[end] == "\\" else 1
        value = _decode_string(stripped[start : end + 1]) if end < len(stripped) else None
    else:
        found = re.match(r"[A-Za-z_$]\w*", stripped[start:])
        value = constants.get(found.group(0)) if found else None
    return (
        (value.upper(), None)
        if value and value.upper() in HTTP_METHODS
        else (None, "fetch method is not a static HTTP method")
    )


def _params(raw: str) -> tuple[str, ...]:
    names: list[str] = []
    for part in raw.split(","):
        match = re.search(r"[A-Za-z_$]\w*", part)
        if match:
            names.append(match.group(0))
    return tuple(names)


def _functions(mask: str) -> list[Function]:
    found: list[Function] = []
    declarations = re.compile(
        r"\bfunction\s+(?P<name>[A-Za-z_$]\w*)\s*\((?P<params>[^)]*)\)"
        r"\s*(?::[^{]+)?\s*\{"
    )
    arrows = re.compile(
        r"\b(?:const|let)\s+(?P<name>[A-Za-z_$]\w*)\s*=\s*"
        r"(?:(?P<callback>useCallback)\s*\(\s*)?(?:async\s*)?"
        r"(?:\((?P<params>[^)]*)\)|(?P<single>[A-Za-z_$]\w*))"
        r"\s*(?::[^=]+)?=>\s*"
    )
    for match in declarations.finditer(mask):
        opening = match.end() - 1
        closing = _close(mask, opening, "{", "}")
        if closing is not None:
            found.append(
                Function(
                    match.group("name"),
                    _params(match.group("params")),
                    opening + 1,
                    closing,
                    match.start("name"),
                    "function",
                )
            )
    for match in arrows.finditer(mask):
        body = match.end()
        if body < len(mask) and mask[body] == "{":
            closing = _close(mask, body, "{", "}")
            if closing is None:
                continue
            start, end = body + 1, closing
        else:
            newline = mask.find("\n", body)
            semicolon = mask.find(";", body)
            stops = [stop for stop in (newline, semicolon) if stop >= 0]
            start, end = body, min(stops) if stops else len(mask)
        params = match.group("params") or match.group("single") or ""
        found.append(
            Function(
                match.group("name"),
                _params(params),
                start,
                end,
                match.start("name"),
                "useCallback" if match.group("callback") else "arrow",
            )
        )
    return sorted(found, key=lambda function: (function.body_end - function.body_start))


def _container(functions: Sequence[Function], offset: int) -> Function | None:
    return next(
        (
            function
            for function in functions
            if function.body_start <= offset < function.body_end
        ),
        None,
    )


def _bound_name(mask: str, offset: int) -> str | None:
    match = re.search(
        r"(?:\b(?:const|let|var)\s+)?([A-Za-z_$]\w*)\s*=\s*(?:await\s*)?$",
        mask[max(0, offset - 100) : offset],
    )
    return match.group(1) if match else None


def _response_observation(mask: str, bound: str | None, start: int, end: int) -> str:
    if not bound:
        return "unknown"
    body = mask[start:end]
    member = rf"\b{re.escape(bound)}\s*(?:\.|\?\.)\s*"
    if re.search(member + r"ok\b", body):
        return "observed"
    status = member + r"status\b"
    operator = r"(?:===|!==|==|!=|<=|>=|<|>)"
    status_code = r"(?:[1-5]\d{2})\b"
    direct_comparison = (
        rf"(?:{status}\s*{operator}\s*{status_code}"
        rf"|{status_code}\s*{operator}\s*{status})"
    )
    return "observed" if re.search(direct_comparison, body) else "not_observed"


def _event_error(
    source: str, mask: str, bound: str | None, start: int, end: int
) -> str:
    if not bound:
        return "unknown"
    member = rf"\b{re.escape(bound)}\s*(?:\.|\?\.)\s*"
    if re.search(member + r"onerror\b", mask[start:end]):
        return "observed"
    for match in re.finditer(member + r"addEventListener\s*", mask[start:end]):
        call = _call_at(mask, start + match.end())
        if call and call[2]:
            raw = source[slice(*call[2][0])].strip()
            if _decode_string(raw) == "error":
                return "observed"
    return "not_observed"


def _frontend_files(root: Path) -> list[Path]:
    base = root / "web" / "src"
    if not base.exists():
        return []
    return sorted(
        path
        for path in base.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not any(part in EXCLUDED_DIRS for part in path.relative_to(base).parts[:-1])
        and not re.search(r"\.(?:spec|test)\.(?:ts|tsx)$", path.name)
    )


def _name_calls(mask: str, name: str) -> Iterable[tuple[re.Match[str], tuple[int, int, list[tuple[int, int]]]]]:
    for match in re.finditer(rf"(?<![\w$.]){re.escape(name)}\s*", mask):
        call = _call_at(mask, match.end())
        if call:
            yield match, call


def _imports(mask: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"\bimport\b(?P<body>.*?)\bfrom\b", mask, re.DOTALL):
        names.update(
            name
            for name in re.findall(r"[A-Za-z_$]\w*", match.group("body"))
            if name not in {"as", "type"}
        )
    return names


def _frontend_file(
    root: Path, path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    relative = path.relative_to(root).as_posix()
    source = path.read_text(encoding="utf-8")
    mask = _mask_typescript(source)
    constants = _constants(source, mask)
    functions = _functions(mask)
    unresolved: list[dict[str, Any]] = []
    calls: list[Transport] = []
    patterns = (
        ("fetch", re.compile(r"(?<![\w$.])fetch\s*")),
        ("event_source", re.compile(r"\bnew\s+EventSource\s*")),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(mask):
            call = _call_at(mask, match.end())
            if not call:
                continue
            _, closing, spans = call
            url_expression = source[slice(*spans[0])].strip() if spans else ""
            url = _resolve_url(url_expression, constants)
            function = _container(functions, match.start())
            bound = _bound_name(mask, match.start())
            observation_end = function.body_end if function else min(len(mask), closing + 400)
            method_reason = None
            if kind == "fetch":
                options = source[slice(*spans[1])] if len(spans) > 1 else None
                method, method_reason = _method(options, constants)
                row = {
                    "kind": kind,
                    "method": method,
                    "non_2xx_observation": _response_observation(
                        mask, bound, closing + 1, observation_end
                    ),
                    "non_2xx_observation_applicability": "applicable",
                    "path_shape": _positional(url, True) if url is not None else None,
                    "query_keys": _query_keys(url),
                    "source": _source(relative, _line(source, match.start())),
                    "url_expression": " ".join(url_expression.split()),
                    "url_template": url,
                }
                if method_reason:
                    _unknown(
                        unresolved,
                        "frontend",
                        "dynamic_fetch_method",
                        method_reason,
                        relative,
                        row["source"]["line"],
                        options or "",
                        function.name if function else None,
                    )
            else:
                method = "GET"
                row = {
                    "kind": kind,
                    "method": method,
                    "non_2xx_observation": None,
                    "non_2xx_observation_applicability": "not_applicable",
                    "path_shape": _positional(url, True) if url is not None else None,
                    "query_keys": _query_keys(url),
                    "source": _source(relative, _line(source, match.start())),
                    "transport_error_observation": _event_error(
                        source, mask, bound, closing + 1, observation_end
                    ),
                    "url_expression": " ".join(url_expression.split()),
                    "url_template": url,
                }
            if function:
                row["enclosing_function"] = function.name
            if url is None:
                _unknown(
                    unresolved,
                    "frontend",
                    "dynamic_transport_url",
                    "transport URL is not a string, template, or module literal constant",
                    relative,
                    row["source"]["line"],
                    url_expression,
                    function.name if function else None,
                )
            calls.append(
                Transport(
                    match.start(),
                    closing,
                    kind,
                    url_expression,
                    method,
                    method_reason,
                    function,
                    row,
                )
            )
    transports = [call.row for call in calls]
    _assign_ids(
        transports,
        "frontend-transport",
        (
            "kind",
            "method",
            "path_shape",
            "url_expression",
            "url_template",
            "enclosing_function",
        ),
        fixed_path=relative,
    )

    by_function: dict[str, list[Transport]] = {}
    for call in calls:
        if call.function:
            by_function.setdefault(call.function.name, []).append(call)
    safe: dict[str, Transport] = {}
    unsafe: dict[str, str] = {}
    unsafe_transports: dict[str, Transport] = {}
    for function in functions:
        direct = by_function.get(function.name, [])
        if len(direct) == 1 and direct[0].url_expression.strip() in function.params:
            if direct[0].method is not None:
                safe[function.name] = direct[0]
            else:
                unsafe[function.name] = (
                    direct[0].method_reason
                    or "wrapper transport method is not statically resolved"
                )
                unsafe_transports[function.name] = direct[0]
        elif len(direct) > 1:
            unsafe[function.name] = "wrapper contains multiple direct transports"
        elif len(direct) == 1 and direct[0].row["path_shape"] is None and any(
            re.search(rf"\b{re.escape(param)}\b", direct[0].url_expression)
            for param in function.params
        ):
            unsafe[function.name] = "wrapper URL parameter is transformed"
            unsafe_transports[function.name] = direct[0]
    wrapper_names = set(safe) | set(unsafe)
    for function in functions:
        if function.name in wrapper_names:
            continue
        body = mask[function.body_start : function.body_end]
        for name in wrapper_names:
            for match, (_, _, spans) in _name_calls(body, name):
                if not spans:
                    continue
                expression = source[
                    function.body_start + spans[0][0] : function.body_start + spans[0][1]
                ].strip()
                if expression in function.params:
                    unsafe[function.name] = (
                        "wrapper reaches transport through another local wrapper"
                    )
                    transport = safe.get(name) or unsafe_transports.get(name)
                    if transport is not None:
                        unsafe_transports[function.name] = transport
                    break
            if function.name in unsafe:
                break

    wrapper_names = set(safe) | set(unsafe)
    for match in re.finditer(
        r"\b(?:const|let)\s+([A-Za-z_$]\w*)\s*=\s*([A-Za-z_$]\w*)\b",
        mask,
    ):
        alias, target = match.groups()
        if alias == target or target not in wrapper_names:
            continue
        unsafe[alias] = "wrapper is an alias of another local wrapper"
        transport = safe.get(target) or unsafe_transports.get(target)
        if transport is not None:
            unsafe_transports[alias] = transport
        _unknown(
            unresolved,
            "frontend",
            "aliased_wrapper",
            "same-file wrapper aliases are not expanded",
            relative,
            _line(source, match.start()),
            source[match.start() : match.end()],
            alias,
        )

    aliases: set[str] = set()
    for match in re.finditer(
        r"\b(?:const|let)\s+([A-Za-z_$]\w*)\s*=\s*(?:fetch|EventSource)\b", mask
    ):
        aliases.add(match.group(1))
        _unknown(
            unresolved,
            "frontend",
            "aliased_transport",
            "aliased transports are not expanded",
            relative,
            _line(source, match.start()),
            source[match.start() : match.end()],
            match.group(1),
        )

    operations: list[dict[str, Any]] = []
    safe_starts = {call.start for call in safe.values()}
    for call in calls:
        if call.start not in safe_starts:
            operations.append(
                {
                    "kind": "direct_transport",
                    "method": call.method,
                    "path_shape": call.row["path_shape"],
                    "query_keys": call.row["query_keys"],
                    "source": dict(call.row["source"]),
                    "transport_id": call.row["id"],
                    "url_template": call.row["url_template"],
                }
            )
    imported = _imports(mask)
    names = set(safe) | set(unsafe) | aliases | imported
    wrapper_names = set(safe) | set(unsafe)
    definition_names = {function.name_start for function in functions}
    for name in names:
        for match, (_, _, spans) in _name_calls(mask, name):
            if match.start() in definition_names or not spans:
                continue
            container = _container(functions, match.start())
            if (
                name in wrapper_names
                and container
                and unsafe.get(container.name)
                == "wrapper reaches transport through another local wrapper"
            ):
                continue
            expression = source[slice(*spans[0])].strip()
            url = _resolve_url(expression, constants)
            if name in imported and (
                url is None
                or not (
                    url.startswith("/")
                    or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", url)
                )
            ):
                continue
            line = _line(source, match.start())
            if name in safe:
                transport = safe[name]
                operations.append(
                    {
                        "expanded_wrapper": name,
                        "kind": "one_hop_wrapper_call",
                        "method": transport.method,
                        "path_shape": _positional(url, True) if url is not None else None,
                        "query_keys": _query_keys(url),
                        "source": _source(relative, line),
                        "transport_id": transport.row["id"],
                        "url_template": url,
                    }
                )
                if url is None:
                    _unknown(
                        unresolved,
                        "frontend",
                        "dynamic_wrapper_call_url",
                        "safe wrapper call URL is not statically resolvable",
                        relative,
                        line,
                        expression,
                        name,
                    )
                continue
            reason = (
                unsafe.get(name)
                or ("aliased transport call" if name in aliases else "imported wrapper call")
            )
            transport = unsafe_transports.get(name)
            operations.append(
                {
                    "expanded_wrapper": name,
                    "kind": "unknown_wrapper_call",
                    "method": None,
                    "path_shape": _positional(url, True) if url is not None else None,
                    "query_keys": _query_keys(url),
                    "source": _source(relative, line),
                    "transport_id": transport.row["id"] if transport is not None else None,
                    "url_template": url,
                }
            )
            _unknown(
                unresolved,
                "frontend",
                "unknown_wrapper_call",
                reason,
                relative,
                line,
                expression,
                name,
            )
    _assign_ids(
        operations,
        "frontend-operation",
        (
            "kind",
            "method",
            "path_shape",
            "query_keys",
            "transport_id",
            "expanded_wrapper",
            "url_template",
        ),
        fixed_path=relative,
    )
    return transports, operations, unresolved


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
    transports: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    for path in _frontend_files(root):
        file_transports, file_operations, file_unresolved = _frontend_file(root, path)
        transports.extend(file_transports)
        operations.extend(file_operations)
        unresolved.extend(file_unresolved)
    _join(routes, transports)
    _join(routes, operations)
    _assign_ids(
        unresolved,
        "unresolved",
        ("domain", "kind", "reason", "expression", "owner"),
    )
    routes.sort(key=lambda row: (row["path_shape"], row["method"], row["handler"], row["id"]))
    transports.sort(key=lambda row: row["id"])
    operations.sort(key=lambda row: row["id"])
    unresolved.sort(key=lambda row: row["id"])
    return {
        "schema_version": 1,
        "scope": {
            "backend": {
                "analysis": "Python AST; web_server.py is parsed and never imported",
                "entrypoint": "web_server.py",
                "included": [
                    "literal @app.route rules and literal methods (default GET)",
                    "Flask constructor static endpoint synthesized from literal arguments",
                ],
                "unresolved": [
                    "dynamic rules/methods/static configuration",
                    "add_url_rule, register_blueprint, and app shorthand decorators",
                ],
            },
            "frontend": {
                "analysis": "conservative masked lexical scan with balanced call delimiters; TypeScript is not executed",
                "root": "web/src",
                "extensions": [".ts", ".tsx"],
                "excluded": [
                    "**/*.{test,spec}.{ts,tsx}",
                    "**/{__tests__,test,tests,dist,node_modules}/**",
                ],
                "included": [
                    "direct global fetch and new EventSource calls",
                    "module literal API bases, literal/template URLs, inline literal methods",
                    "same-file one-hop wrappers with one transport and an unmodified URL parameter",
                ],
                "declarative_resource_urls": {
                    "status": "excluded",
                    "reason": "JSX src/href/poster and CSS resource loads are outside executable call-expression schema v1",
                },
                "unresolved": [
                    "dynamic URLs/methods; imported, aliased, transformed, multi-hop, or multi-transport wrappers",
                ],
            },
            "matching": {
                "definition": "HTTP method plus positional path shape; query is stripped before matching",
                "placeholders": "backend <converter:name> and frontend interpolation normalize to {1}, {2}, ...",
                "query_keys": "static query keys are retained separately",
            },
            "non_2xx_observation": {
                "states": ["observed", "not_observed", "unknown"],
                "definition": "fetch is observed only when the same bound response has .ok read or .status compared in its enclosing function; catch/json alone do not count",
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)
    inventory = build_inventory(args.root)
    rendered = render_inventory(inventory)
    output = args.output if args.output.is_absolute() else args.root / args.output
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
        print(f"OK {output.relative_to(args.root)} {_counts(inventory)}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"WROTE {output.relative_to(args.root)} {_counts(inventory)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

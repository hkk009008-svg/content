from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "product_surface_inventory.py"
SPEC = importlib.util.spec_from_file_location("product_surface_inventory", SCRIPT)
assert SPEC and SPEC.loader
inventory_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory_module
SPEC.loader.exec_module(inventory_module)


def _repo(tmp_path: Path, backend: str = "app = Flask(__name__, static_folder=None)\n") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "web_server.py").write_text(backend, encoding="utf-8")
    (tmp_path / "web" / "src").mkdir(parents=True)
    return tmp_path


def _frontend(root: Path, relative: str, source: str) -> None:
    path = root / "web" / "src" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _build(root: Path) -> dict:
    return inventory_module.build_inventory(root)


def _valid_helper_payload() -> dict:
    path = "web/src/fact.ts"
    reference = f"{path}:0"
    source = {"path": path, "line": 1}
    return {
        "parser": "TypeScript compiler API",
        "typescript_version": "5.9.3",
        "files": [path],
        "transports": [
            {
                "_transport_ref": reference,
                "kind": "fetch",
                "method": "GET",
                "non_2xx_observation": "unknown",
                "non_2xx_observation_applicability": "applicable",
                "source": dict(source),
                "url_expression": "'/api/value'",
                "url_template": "/api/value",
            }
        ],
        "operations": [
            {
                "_transport_ref": reference,
                "kind": "direct_transport",
                "method": "GET",
                "source": dict(source),
                "url_template": "/api/value",
            }
        ],
        "unresolved": [
            {
                "domain": "frontend",
                "expression": "path",
                "kind": "dynamic_transport_url",
                "owner": "load",
                "reason": "transport URL is not a string, template, or module literal constant",
                "source": dict(source),
            }
        ],
    }


def _utf16_offset(source: str, marker: str) -> int:
    return len(source[: source.index(marker)].encode("utf-16-le")) // 2


def _payload_for_fetch_source(source: str) -> dict:
    payload = _valid_helper_payload()
    offset = _utf16_offset(source, "fetch")
    line = source[: source.index("fetch")].count("\n") + 1
    reference = f"web/src/fact.ts:{offset}"
    payload["transports"][0]["_transport_ref"] = reference
    payload["transports"][0]["source"]["line"] = line
    payload["operations"][0]["_transport_ref"] = reference
    payload["operations"][0]["source"]["line"] = line
    payload["unresolved"][0]["source"]["line"] = 1
    return payload


TRUST_BOUNDARY_CORRUPTIONS = (
    "direct_source_line_mismatch",
    "direct_url_mismatch",
    "empty_source_reference",
    "transport_line",
    "operation_line",
    "unresolved_line",
    "offset_out_of_bounds",
    "offset_too_many_digits",
    "reference_path_alias",
    "source_path_alias",
    "method_mismatch",
    "unicode_code_point_offset",
    "unicode_surrogate_half_offset",
)


def _trust_boundary_failure(root: Path, corruption: str) -> dict:
    source = "fetch('/api/value')\n"
    if corruption == "direct_source_line_mismatch":
        source = "const marker = true\nfetch('/api/value')\n"
    elif corruption == "empty_source_reference":
        source = ""
    elif corruption == "unicode_code_point_offset":
        source = "const marker = '😀'\nfetch('/api/value')\n"
    elif corruption == "unicode_surrogate_half_offset":
        source = "/*😀*/fetch('/api/value')\n"
    _frontend(root, "fact.ts", source)
    payload = _valid_helper_payload() if not source else _payload_for_fetch_source(source)
    transport = payload["transports"][0]
    operation = payload["operations"][0]
    unresolved = payload["unresolved"][0]

    if corruption == "direct_source_line_mismatch":
        assert operation["source"]["line"] == 2
        operation["source"]["line"] = 1
    elif corruption == "direct_url_mismatch":
        (root / "web_server.py").write_text(
            """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/value")
def value():
    pass

@app.route("/api/other")
def other():
    pass
""",
            encoding="utf-8",
        )
        routes, unresolved_routes = inventory_module._backend(root)
        assert unresolved_routes == []
        assert {(row["method"], row["rule"]) for row in routes} == {
            ("GET", "/api/other"),
            ("GET", "/api/value"),
        }
        operation["url_template"] = "/api/other"
    elif corruption == "empty_source_reference":
        pass
    elif corruption == "transport_line":
        transport["source"]["line"] = 999
    elif corruption == "operation_line":
        operation["source"]["line"] = 999
    elif corruption == "unresolved_line":
        unresolved["source"]["line"] = 999
    elif corruption == "offset_out_of_bounds":
        transport["_transport_ref"] = "web/src/fact.ts:999999"
        operation["_transport_ref"] = transport["_transport_ref"]
    elif corruption == "offset_too_many_digits":
        transport["_transport_ref"] = f"web/src/fact.ts:{'9' * 5000}"
        operation["_transport_ref"] = transport["_transport_ref"]
    elif corruption == "reference_path_alias":
        transport["_transport_ref"] = "web/src/./fact.ts:0"
        operation["_transport_ref"] = transport["_transport_ref"]
    elif corruption == "source_path_alias":
        transport["source"]["path"] = "web/src/./fact.ts"
    elif corruption == "method_mismatch":
        operation["method"] = "POST"
    elif corruption == "unicode_code_point_offset":
        code_point_offset = source.index("fetch")
        assert code_point_offset != _utf16_offset(source, "fetch")
        transport["_transport_ref"] = f"web/src/fact.ts:{code_point_offset}"
        operation["_transport_ref"] = transport["_transport_ref"]
    elif corruption == "unicode_surrogate_half_offset":
        astral_start = _utf16_offset(source, "😀")
        transport["_transport_ref"] = f"web/src/fact.ts:{astral_start + 1}"
        operation["_transport_ref"] = transport["_transport_ref"]
    else:
        raise AssertionError(f"unhandled corruption {corruption}")
    return payload


def _mock_helper_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
) -> None:
    def completed(command, **_kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(inventory_module.subprocess, "run", completed)


def test_backend_routes_preserve_stacks_methods_and_static_constructor(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder="web/dist", static_url_path="")

@app.route("/default/<pid>")
def default_route(pid):
    pass

@app.route("/stacked/<pid>")
@app.route("/stacked/<int:id>", methods=["POST", "GET"])
def stacked(pid=None, id=None):
    pass
""",
    )

    result = _build(root)
    contracts = {
        (row["handler"], row["method"], row["rule"], row["path_shape"], row["kind"])
        for row in result["routes"]
    }

    assert ("default_route", "GET", "/default/<pid>", "/default/{1}", "flask_route") in contracts
    assert ("stacked", "GET", "/stacked/<pid>", "/stacked/{1}", "flask_route") in contracts
    assert ("stacked", "GET", "/stacked/<int:id>", "/stacked/{1}", "flask_route") in contracts
    assert ("stacked", "POST", "/stacked/<int:id>", "/stacked/{1}", "flask_route") in contracts
    assert ("static", "GET", "/<path:filename>", "/{1}", "flask_static_constructor") in contracts
    assert all(row["handler"] in row["id"] for row in result["routes"])


def test_backend_dynamic_registration_shapes_fail_closed(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask, Blueprint
app = Flask(__name__, static_folder=None)
RULE = "/dynamic"
METHODS = ["POST"]

@app.route(RULE)
def dynamic_rule():
    pass

@app.route("/dynamic-method", methods=METHODS)
def dynamic_method():
    pass

@app.get("/short")
def shorthand():
    pass

app.add_url_rule("/added", endpoint="added")
app.register_blueprint(Blueprint("bp", __name__))
""",
    )

    result = _build(root)

    assert result["routes"] == []
    assert {row["kind"] for row in result["unresolved"]} == {
        "add_url_rule",
        "app_shorthand_decorator",
        "dynamic_route_methods",
        "dynamic_route_rule",
        "register_blueprint",
    }


def test_frontend_fetch_constants_templates_query_eventsource_and_matching(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/things/<thing_id>", methods=["POST"])
def save(thing_id):
    pass

@app.route("/api/things/<thing_id>/stream")
def stream(thing_id):
    pass
""",
    )
    _frontend(
        root,
        "network.tsx",
        r"""
const API = '/api'
const ignored = 'fetch("/string-only")'
// fetch('/comment-only')
/* new EventSource('/comment-only') */

export async function saveThing(id: string, token: string) {
  const response = await fetch(
    `${API}/things/${id}?view=full&token=${token}`,
    {
      body: '{}',
      method: 'POST',
    },
  )
  if (!response.ok) throw new Error('bad')
  return response.json()
}

export function subscribe(id: string) {
  const events = new EventSource(`${API}/things/${id}/stream`)
  events.onerror = () => {}
  return events
}
""",
    )

    result = _build(root)
    fetch_row = next(row for row in result["frontend_transports"] if row["kind"] == "fetch")
    event_row = next(
        row for row in result["frontend_transports"] if row["kind"] == "event_source"
    )

    assert len(result["frontend_transports"]) == 2
    assert fetch_row["method"] == "POST"
    assert fetch_row["path_shape"] == "/api/things/{1}"
    assert fetch_row["query_keys"] == ["token", "view"]
    assert fetch_row["route_match"] == "matched"
    assert fetch_row["non_2xx_observation"] == "observed"
    assert event_row["method"] == "GET"
    assert event_row["path_shape"] == "/api/things/{1}/stream"
    assert event_row["non_2xx_observation"] is None
    assert event_row["non_2xx_observation_applicability"] == "not_applicable"
    assert event_row["transport_error_observation"] == "observed"
    assert event_row["route_match"] == "matched"


def test_fetch_trailing_comma_defaults_to_get_and_matches(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/projects/<pid>/characters/<cid>/lora-status")
def lora_status(pid, cid):
    pass
""",
    )
    _frontend(
        root,
        "trailing-comma.ts",
        """
export async function loadStatus(projectId: string, characterId: string) {
  const response = await fetch(
    `/api/projects/${projectId}/characters/${characterId}/lora-status`,

  )
  if (response.status >= 400) throw new Error('bad')
}
""",
    )

    result = _build(root)
    transport = result["frontend_transports"][0]
    operation = result["frontend_operations"][0]

    assert transport["method"] == "GET"
    assert transport["route_match"] == "matched"
    assert operation["method"] == "GET"
    assert operation["route_match"] == "matched"
    assert "dynamic_fetch_method" not in {
        row["kind"] for row in result["unresolved"]
    }


def test_regex_literals_preserve_later_fetch_and_division_comments(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "regex.ts",
        r"""
const quotes = /["']/; fetch('/api/live')
const escaped = /[\/"'\\]+\s?/gim
const ratio = total / count
const of = 10
const contextual = of / count
const adjusted = total /* /["']/ is only a comment */ / count
// /["']/ and fetch('/api/comment') are only a comment
""",
    )

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == [
        "/api/live"
    ]
    assert "ambiguous_javascript_slash" not in {
        row["kind"] for row in result["unresolved"]
    }


def test_compiler_ast_handles_contextual_regex_without_lexical_noise(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "ambiguous-regex.ts",
        r"""
export function scan(flag: boolean, value: string) {
  if (flag) /["']/.test(value)
  fetch('/api/live')
}
""",
    )

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == [
        "/api/live"
    ]
    assert "ambiguous_javascript_slash" not in {
        row["kind"] for row in result["unresolved"]
    }


def test_template_interpolation_and_jsx_text_do_not_hide_fetch(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "syntax.tsx",
        """
const rendered = `${fetch('/api/interpolated')}`
export const Ratio = () => <span>x / 100</span>
fetch('/api/after-jsx')
""",
    )

    result = _build(root)

    assert {
        row["url_template"] for row in result["frontend_transports"]
    } == {"/api/after-jsx", "/api/interpolated"}
    assert not [
        row
        for row in result["unresolved"]
        if "slash" in row["kind"]
    ]


@pytest.mark.parametrize(
    ("observation_body", "expected"),
    [
        ("if (!response.ok) throw new Error('bad')", "observed"),
        ("if (response.status >= 400) throw new Error('bad')", "observed"),
        ("if (400 <= response.status) throw new Error('bad')", "observed"),
        (
            "if (response.status + (flag === true ? 400 : 0)) "
            "throw new Error('bad')",
            "not_observed",
        ),
        ("await response.json()", "not_observed"),
        ("try { await response.json() } catch (error) {}", "not_observed"),
    ],
)
def test_non_2xx_observation_is_narrow_and_mutation_flips(
    tmp_path: Path, observation_body: str, expected: str
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "observation.ts",
        f"""
export async function load() {{
  const response = await fetch('/api/value')
  {observation_body}
}}
""",
    )

    row = _build(root)["frontend_transports"][0]

    assert row["non_2xx_observation"] == expected


def test_one_hop_wrapper_expands_and_unsafe_wrappers_remain_unknown(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder=None)
@app.route("/api/items/<item_id>", methods=["POST"])
def item(item_id):
    pass
""",
    )
    _frontend(
        root,
        "wrappers.ts",
        """
import { request } from './client'
import { useCallback } from 'react'

const post = useCallback(async (url: string) => {
  const response = await fetch(url, { method: 'POST' })
  return response.json()
}, [])
const transformed = (url: string) => fetch('/prefix' + url)
const secondHop = (url: string) => post(url)
const alias = fetch

export function run(id: string) {
  post(`/api/items/${id}`)
  transformed('/api/transformed')
  secondHop('/api/second-hop')
  alias('/api/alias')
  request('/api/imported')
}
""",
    )

    result = _build(root)
    expanded = [
        row for row in result["frontend_operations"] if row["kind"] == "one_hop_wrapper_call"
    ]
    unknown = [
        row for row in result["frontend_operations"] if row["kind"] == "unknown_wrapper_call"
    ]

    assert len(expanded) == 1
    assert expanded[0]["expanded_wrapper"] == "post"
    assert expanded[0]["method"] == "POST"
    assert expanded[0]["path_shape"] == "/api/items/{1}"
    assert expanded[0]["route_match"] == "matched"
    assert {row["expanded_wrapper"] for row in unknown} == {
        "alias",
        "request",
        "secondHop",
        "transformed",
    }
    reasons = {row["reason"] for row in result["unresolved"]}
    assert "aliased transports are not expanded" in reasons
    assert "wrapper URL parameter is transformed" in reasons
    assert "wrapper reaches transport through another local wrapper" in reasons
    assert "imported wrapper call" in reasons


def test_wrapper_url_parameter_position_is_preserved_and_routes_match(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/first")
def first():
    pass

@app.route("/api/middle")
def middle():
    pass

@app.route("/api/last")
def last():
    pass
""",
    )
    _frontend(
        root,
        "parameter-position.ts",
        """
function getFirst(url: string, tag: string) {
  return fetch(url)
}
function getWithTag(tag: string, url: string) {
  return fetch(url)
}
function getLast(tag: string, trace: string, url: string) {
  return fetch(url)
}

getFirst('/api/first', 'audit')
getWithTag('audit', '/api/middle')
getLast('audit', 'trace', '/api/last')
""",
    )

    result = _build(root)
    operations = {
        row["expanded_wrapper"]: row
        for row in result["frontend_operations"]
        if row["kind"] == "one_hop_wrapper_call"
    }

    assert {
        name: (row["url_template"], row["route_match"])
        for name, row in operations.items()
    } == {
        "getFirst": ("/api/first", "matched"),
        "getLast": ("/api/last", "matched"),
        "getWithTag": ("/api/middle", "matched"),
    }


def test_missing_wrapper_url_argument_never_falls_back_to_another_argument(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "missing-argument.ts",
        """
function getWithTag(tag: string, url: string) {
  return fetch(url)
}
getWithTag('/api/not-the-url')
""",
    )

    result = _build(root)
    operation = next(
        row
        for row in result["frontend_operations"]
        if row["kind"] == "one_hop_wrapper_call"
    )

    assert operation["expanded_wrapper"] == "getWithTag"
    assert operation["url_template"] is None
    assert operation["route_match"] == "unknown"
    assert {
        (row["kind"], row.get("owner"), row["reason"])
        for row in result["unresolved"]
    } >= {
        (
            "dynamic_wrapper_call_url",
            "getWithTag",
            "safe wrapper call URL is not statically resolvable",
        )
    }


def test_unsupported_wrapper_parameter_shapes_fail_conservatively(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "unsupported-parameters.ts",
        """
function defaulted(tag: string, url: string = '/api/default') {
  return fetch(url)
}
function rested(tag: string, ...url: string[]) {
  return fetch(url as unknown as string)
}
function destructured(tag: string, { url }: { url: string }) {
  return fetch(url)
}
function optional(tag: string, url?: string) {
  return fetch(url as string)
}
function withThis(this: void, url: string) {
  return fetch(url)
}

defaulted('/api/not-the-url')
rested('/api/not-the-url', '/api/rest')
destructured('/api/not-the-url', { url: '/api/destructured' })
optional('/api/not-the-url', '/api/optional')
withThis('/api/this')
""",
    )

    result = _build(root)
    operations = [
        row
        for row in result["frontend_operations"]
        if row["kind"] == "unknown_wrapper_call"
    ]

    assert {row["expanded_wrapper"] for row in operations} == {
        "defaulted",
        "destructured",
        "optional",
        "rested",
        "withThis",
    }
    assert all(row["method"] == "GET" for row in operations)
    assert all(row["url_template"] is None for row in operations)
    assert all(row["route_match"] == "unknown" for row in operations)
    assert "/api/not-the-url" not in {
        row["url_template"] for row in result["frontend_operations"]
    }
    assert {
        (row.get("owner"), row["reason"])
        for row in result["unresolved"]
        if row["kind"] == "unknown_wrapper_call"
    } == {
        (name, "wrapper URL parameter shape is unsupported")
        for name in {"defaulted", "destructured", "optional", "rested", "withThis"}
    }


def test_nonzero_url_parameter_remains_one_hop_only(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "second-hop-position.ts",
        """
function getWithTag(tag: string, url: string) {
  return fetch(url)
}
function secondHop(tag: string, url: string) {
  return getWithTag(tag, url)
}
secondHop('audit', '/api/two-hop')
""",
    )

    result = _build(root)
    operation = next(
        row
        for row in result["frontend_operations"]
        if row.get("expanded_wrapper") == "secondHop"
    )

    assert operation["kind"] == "unknown_wrapper_call"
    assert operation["url_template"] is None
    assert operation["method"] == "GET"
    assert operation["route_match"] == "unknown"
    assert operation["transport_id"] == result["frontend_transports"][0]["id"]
    assert {
        (row.get("owner"), row["reason"])
        for row in result["unresolved"]
        if row["kind"] == "unknown_wrapper_call"
    } == {("secondHop", "wrapper reaches transport through another local wrapper")}


def test_multi_hop_wrapper_resolution_is_declaration_order_independent(
    tmp_path: Path,
) -> None:
    backend = """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/three")
def three():
    pass
"""
    forward_root = _repo(tmp_path / "forward", backend)
    reverse_root = _repo(tmp_path / "reverse", backend)
    _frontend(
        forward_root,
        "chain.ts",
        """
function first(url: string) { return fetch(url) }
function second(url: string) { return first(url) }
function third(url: string) { return second(url) }
third('/api/three')
""",
    )
    _frontend(
        reverse_root,
        "chain.ts",
        """
function third(url: string) { return second(url) }
function second(url: string) { return first(url) }
function first(url: string) { return fetch(url) }
third('/api/three')
""",
    )

    results = [_build(forward_root), _build(reverse_root)]
    semantic_operations = []
    for result in results:
        assert len(result["frontend_operations"]) == 1
        operation = result["frontend_operations"][0]
        transport = result["frontend_transports"][0]
        assert operation["source"]["line"] == 5
        assert operation["transport_id"] == transport["id"]
        unresolved = [
            row
            for row in result["unresolved"]
            if row["kind"] == "unknown_wrapper_call"
        ]
        assert len(unresolved) == 1
        assert unresolved[0]["expression"] == "'/api/three'"
        assert unresolved[0]["source"]["line"] == 5
        semantic_operations.append(
            {
                key: operation[key]
                for key in (
                    "expanded_wrapper",
                    "kind",
                    "method",
                    "path_shape",
                    "route_match",
                    "url_template",
                )
            }
        )
        assert {
            (row.get("owner"), row["reason"])
            for row in result["unresolved"]
            if row["kind"] == "unknown_wrapper_call"
        } == {("third", "wrapper reaches transport through another local wrapper")}

    assert semantic_operations[0] == semantic_operations[1] == {
        "expanded_wrapper": "third",
        "kind": "unknown_wrapper_call",
        "method": "GET",
        "path_shape": None,
        "route_match": "unknown",
        "url_template": None,
    }


@pytest.mark.parametrize(
    "source",
    [
        """
function get(url: string) { return fetch(url) }
function post(url: string) { return fetch(url, { method: 'POST' }) }
function choose(url: string, usePost: boolean) {
  if (usePost) return post(url)
  return get(url)
}
choose('/api/branch', true)
""",
        """
function choose(url: string, usePost: boolean) {
  if (!usePost) return get(url)
  return post(url)
}
function post(url: string) { return fetch(url, { method: 'POST' }) }
function get(url: string) { return fetch(url) }
choose('/api/branch', true)
""",
        """
function choose(url: string, usePost: boolean) {
  if (usePost) return postMiddle(url)
  return getMiddle(url)
}
function postMiddle(url: string) { return postTransport(url) }
function getMiddle(url: string) { return getTransport(url) }
function postTransport(url: string) {
  return fetch(url, { method: 'POST' })
}
function getTransport(url: string) { return fetch(url) }
choose('/api/branch', true)
""",
    ],
)
def test_branching_wrapper_transport_closure_is_order_independent_and_unknown(
    tmp_path: Path,
    source: str,
) -> None:
    """Every reachable branch participates before method/link classification."""
    root = _repo(tmp_path)
    _frontend(root, "branch.ts", source)

    result = _build(root)
    operation = next(
        row
        for row in result["frontend_operations"]
        if row.get("expanded_wrapper") == "choose"
    )

    assert {row["method"] for row in result["frontend_transports"]} == {
        "GET",
        "POST",
    }
    assert operation["kind"] == "unknown_wrapper_call"
    assert operation["method"] is None
    assert operation["transport_id"] is None
    assert operation["url_template"] == "/api/branch"
    assert operation["route_match"] == "unknown"
    assert {
        (row.get("owner"), row["reason"])
        for row in result["unresolved"]
        if row["kind"] == "unknown_wrapper_call"
    } == {
        (
            "choose",
            "wrapper reaches multiple transports through local wrapper "
            "dependencies",
        )
    }


@pytest.mark.parametrize(
    "source",
    [
        """
function post(url: string) { return fetch(url, { method: 'POST' }) }
function mixed(url: string, usePost: boolean) {
  if (usePost) return post(url)
  return fetch(url)
}
mixed('/api/mixed', true)
""",
        """
function mixed(url: string, usePost: boolean) {
  if (!usePost) return fetch(url)
  return post(url)
}
function post(url: string) { return fetch(url, { method: 'POST' }) }
mixed('/api/mixed', true)
""",
    ],
)
def test_direct_and_indirect_reachable_transports_fail_closed(
    tmp_path: Path,
    source: str,
) -> None:
    """One direct transport cannot hide a second wrapper dependency."""
    root = _repo(tmp_path)
    _frontend(root, "mixed.ts", source)

    result = _build(root)
    operation = next(
        row
        for row in result["frontend_operations"]
        if row.get("expanded_wrapper") == "mixed"
    )

    assert operation["kind"] == "unknown_wrapper_call"
    assert operation["method"] is None
    assert operation["transport_id"] is None
    assert operation["url_template"] == "/api/mixed"
    assert operation["route_match"] == "unknown"


def test_branch_transport_removal_mutation_restores_single_transport_link(
    tmp_path: Path,
) -> None:
    """Removing one reachable branch must flip null provenance back to GET."""
    root = _repo(tmp_path)
    _frontend(
        root,
        "single-branch.ts",
        """
function get(url: string) { return fetch(url) }
function choose(url: string, first: boolean) {
  if (first) return get(url)
  return get(url)
}
choose('/api/single', true)
""",
    )

    result = _build(root)
    operation = next(
        row
        for row in result["frontend_operations"]
        if row.get("expanded_wrapper") == "choose"
    )

    assert operation["kind"] == "unknown_wrapper_call"
    assert operation["method"] == "GET"
    assert operation["transport_id"] == result["frontend_transports"][0]["id"]


def test_wrapper_cycle_terminates_without_inventing_transport_truth(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "cycle.ts",
        """
function first(url: string) { return second(url) }
function second(url: string) { return first(url) }
first('/api/cycle')
""",
    )

    result = _build(root)

    assert result["frontend_transports"] == []
    assert result["frontend_operations"] == []
    assert result["unresolved"] == []


def test_dynamic_method_wrapper_calls_are_explicit_unknowns_with_transport_link(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        """
from flask import Flask
app = Flask(__name__, static_folder=None)

@app.route("/api/post", methods=["POST"])
def post():
    pass
""",
    )
    _frontend(
        root,
        "dynamic-wrapper.ts",
        """
const dynamic = (url: string, init: RequestInit) => fetch(url, init)
const secondHop = (url: string, init: RequestInit) => dynamic(url, init)
const alias = dynamic

export function run() {
  dynamic('/api/post', { method: 'POST' })
  secondHop('/api/two-hop', { method: 'POST' })
  alias('/api/alias', { method: 'POST' })
}
""",
    )

    result = _build(root)
    transport = result["frontend_transports"][0]
    unknown = {
        row["expanded_wrapper"]: row
        for row in result["frontend_operations"]
        if row["kind"] == "unknown_wrapper_call"
    }

    assert transport["method"] is None
    assert set(unknown) == {"alias", "dynamic", "secondHop"}
    assert unknown["dynamic"]["path_shape"] == "/api/post"
    assert unknown["dynamic"]["route_match"] == "unknown"
    assert all(row["method"] is None for row in unknown.values())
    assert all(row["transport_id"] == transport["id"] for row in unknown.values())

    unresolved = {(row["kind"], row["owner"], row["reason"]) for row in result["unresolved"]}
    assert (
        "dynamic_fetch_method",
        "dynamic",
        "fetch options is not an inline object literal",
    ) in unresolved
    assert (
        "unknown_wrapper_call",
        "dynamic",
        "fetch options is not an inline object literal",
    ) in unresolved
    assert (
        "unknown_wrapper_call",
        "secondHop",
        "wrapper reaches transport through another local wrapper",
    ) in unresolved
    assert (
        "unknown_wrapper_call",
        "alias",
        "wrapper is an alias of another local wrapper",
    ) in unresolved


@pytest.mark.parametrize(
    "source",
    [
        "function fetch(url: string) { return url }\nfetch('/api/local')\n",
        "const fetch = client\nfetch('/api/local')\n",
        "let fetch = client\nfetch('/api/local')\n",
        "var fetch = client\nfetch('/api/local')\n",
        "import fetch from './client'\nfetch('/api/local')\n",
        "function run(fetch: any) { fetch('/api/local') }\n",
        "const run = (fetch: any) => fetch('/api/local')\n",
        "try { throw 1 } catch (fetch) { fetch('/api/local') }\n",
        (
            "class Client { fetch(url: string) { return url } }\n"
            "new Client().fetch('/api/local')\n"
        ),
        (
            "const client = { fetch(url: string) { return url } }\n"
            "client.fetch('/api/local')\n"
        ),
    ],
)
def test_shadowed_fetch_calls_are_unknown_not_transports(
    tmp_path: Path,
    source: str,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "shadowed.ts", source)

    result = _build(root)
    shadowed = [
        row
        for row in result["frontend_operations"]
        if row["kind"] == "shadowed_fetch_call"
    ]

    assert result["frontend_transports"] == []
    assert len(shadowed) == 1
    assert shadowed[0]["method"] is None
    assert shadowed[0]["url_template"] == "/api/local"
    assert shadowed[0]["route_match"] == "unknown"
    assert {
        (row["domain"], row["kind"])
        for row in result["unresolved"]
    } >= {("frontend", "shadowed_fetch_call")}


def test_fetch_shadowing_is_lexically_scoped(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "scoped.ts",
        """
function local(fetch: any) {
  fetch('/api/local')
}
function remote() {
  fetch('/api/global')
}
""",
    )

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == [
        "/api/global"
    ]
    assert [
        row["url_template"]
        for row in result["frontend_operations"]
        if row["kind"] == "shadowed_fetch_call"
    ] == ["/api/local"]


def test_shadowed_eventsource_is_unknown_not_transport(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "shadowed-event.ts",
        """
function subscribe(EventSource: any) {
  return new EventSource('/api/local-stream')
}
""",
    )

    result = _build(root)

    assert result["frontend_transports"] == []
    assert [
        row["kind"] for row in result["frontend_operations"]
    ] == ["shadowed_event_source_call"]
    assert {
        row["kind"] for row in result["unresolved"]
    } == {"shadowed_event_source_call"}


def test_eventsource_alias_is_explicit_unknown(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "aliased-event.ts",
        """
const LocalEventSource = EventSource
new LocalEventSource('/api/local-stream')
""",
    )

    result = _build(root)

    assert result["frontend_transports"] == []
    assert [
        row["kind"] for row in result["frontend_operations"]
    ] == ["unknown_wrapper_call"]
    assert {
        row["kind"] for row in result["unresolved"]
    } == {"aliased_transport", "unknown_wrapper_call"}


def test_normal_global_fetch_remains_a_transport(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(root, "global.ts", "fetch('/api/global')\n")

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == [
        "/api/global"
    ]
    assert not [
        row
        for row in result["unresolved"]
        if row["kind"] == "shadowed_fetch_call"
    ]


def test_ids_are_line_independent_and_render_is_deterministic(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    source = """
export async function load(id: string) {
  const response = await fetch(`/api/items/${id}`)
  if (!response.ok) throw new Error('bad')
}
"""
    _frontend(root, "stable.ts", source)
    first = _build(root)
    second = _build(root)

    assert inventory_module.render_inventory(first) == inventory_module.render_inventory(second)
    first_ids = {
        row["id"]
        for key in ("routes", "frontend_transports", "frontend_operations", "unresolved")
        for row in first[key]
    }

    _frontend(root, "stable.ts", "\n\n" + source)
    shifted = _build(root)
    shifted_ids = {
        row["id"]
        for key in ("routes", "frontend_transports", "frontend_operations", "unresolved")
        for row in shifted[key]
    }

    assert first_ids == shifted_ids
    assert json.loads(inventory_module.render_inventory(first)) == first


def test_frontend_test_and_generated_directories_are_excluded(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(root, "active.ts", "fetch('/api/active')\n")
    _frontend(root, "ignored.test.ts", "fetch('/api/test-file')\n")
    _frontend(root, "ignored.spec.tsx", "fetch('/api/spec-file')\n")
    _frontend(root, "tests/ignored.ts", "fetch('/api/tests-dir')\n")
    _frontend(root, "__tests__/ignored.tsx", "fetch('/api/dunder-tests-dir')\n")
    _frontend(root, "dist/ignored.ts", "fetch('/api/dist')\n")
    _frontend(root, "node_modules/pkg/ignored.ts", "fetch('/api/module')\n")

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == ["/api/active"]


def test_multi_transport_wrapper_call_is_explicit_unknown(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "multi-wrapper.ts",
        """
function both(url: string) {
  fetch(url)
  fetch(url)
}
both('/api/multi')
""",
    )

    result = _build(root)

    wrapper_call = next(
        row
        for row in result["frontend_operations"]
        if row["kind"] == "unknown_wrapper_call"
    )
    assert wrapper_call["method"] is None
    assert wrapper_call["url_template"] == "/api/multi"
    assert {
        row["reason"]
        for row in result["unresolved"]
        if row["kind"] == "unknown_wrapper_call"
    } == {"wrapper contains multiple direct transports"}


def test_frontend_sources_are_parsed_without_application_execution(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _frontend(
        root,
        "must-not-run.ts",
        """
fetch('/api/static-analysis')
throw new Error('application module was executed')
""",
    )

    result = _build(root)

    assert [row["url_template"] for row in result["frontend_transports"]] == [
        "/api/static-analysis"
    ]


@pytest.mark.parametrize(
    "operation_kind",
    ["one_hop_wrapper_call", "unknown_wrapper_call"],
)
def test_trust_boundary_accepts_distinct_wrapper_line_and_resolved_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation_kind: str,
) -> None:
    root = _repo(tmp_path)
    source = (
        "const marker = '😀'\n"
        "function getWithTag(tag: string, url: string) { return fetch(url) }\n"
        "getWithTag('audit', '/api/value')\n"
    )
    _frontend(root, "fact.ts", source)
    payload = _payload_for_fetch_source(source)
    reference = f"web/src/fact.ts:{_utf16_offset(source, 'fetch')}"
    payload["transports"][0]["_transport_ref"] = reference
    payload["transports"][0]["source"]["line"] = 2
    payload["operations"][0].update(
        {
            "_transport_ref": reference,
            "expanded_wrapper": "getWithTag",
            "kind": operation_kind,
            "source": {"path": "web/src/fact.ts", "line": 3},
            "url_template": "/api/resolved",
        }
    )
    payload["unresolved"] = []
    _mock_helper_payload(monkeypatch, payload)

    transports, operations, _unresolved, _version = inventory_module._frontend(root)

    assert _utf16_offset(source, "fetch") != source.index("fetch")
    assert operations[0]["kind"] == operation_kind
    assert operations[0]["source"]["line"] != transports[0]["source"]["line"]
    assert operations[0]["url_template"] != transports[0]["url_template"]
    assert operations[0]["transport_id"] == transports[0]["id"]


@pytest.mark.parametrize(
    ("source", "unresolved_line"),
    [
        ("", 1),
        ("fetch('/api/value')\n", 2),
    ],
)
def test_source_line_range_handles_empty_and_final_newline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    unresolved_line: int,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "fact.ts", source)
    payload = (
        _valid_helper_payload()
        if not source
        else _payload_for_fetch_source(source)
    )
    if not source:
        payload["transports"] = []
        payload["operations"] = []
    payload["unresolved"][0]["source"]["line"] = unresolved_line
    _mock_helper_payload(monkeypatch, payload)

    inventory_module._frontend(root)


def test_symlinked_frontend_source_alias_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    (root / "web" / "src" / "alias.ts").symlink_to("fact.ts")
    payload = _payload_for_fetch_source("fetch('/api/value')\n")
    payload["files"] = ["web/src/alias.ts", "web/src/fact.ts"]
    _mock_helper_payload(monkeypatch, payload)

    def forbidden_ids(*_args, **_kwargs):
        raise AssertionError("source alias validation must precede ID construction")

    monkeypatch.setattr(inventory_module, "_assign_ids", forbidden_ids)

    with pytest.raises(inventory_module.FrontendInventoryError):
        inventory_module._frontend(root)


@pytest.mark.parametrize("corruption", TRUST_BOUNDARY_CORRUPTIONS)
def test_source_trust_boundary_failures_precede_id_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    root = _repo(tmp_path)
    payload = _trust_boundary_failure(root, corruption)
    _mock_helper_payload(monkeypatch, payload)

    def forbidden_ids(*_args, **_kwargs):
        raise AssertionError("source trust validation must precede ID construction")

    monkeypatch.setattr(inventory_module, "_assign_ids", forbidden_ids)

    with pytest.raises(inventory_module.FrontendInventoryError):
        inventory_module._frontend(root)


@pytest.mark.parametrize("mode", ["write", "check"])
@pytest.mark.parametrize("corruption", TRUST_BOUNDARY_CORRUPTIONS)
def test_source_trust_boundary_failures_preserve_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    corruption: str,
) -> None:
    root = _repo(tmp_path / "repo")
    payload = _trust_boundary_failure(root, corruption)
    output = root / "inventory.json"
    output.write_text("prior artifact\n", encoding="utf-8")
    _mock_helper_payload(monkeypatch, payload)

    def forbidden_ids(*_args, **_kwargs):
        raise AssertionError("source trust validation must precede ID construction")

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("source trust failure must never reach the writer")

    monkeypatch.setattr(inventory_module, "_assign_ids", forbidden_ids)
    monkeypatch.setattr(inventory_module, "_atomic_write", forbidden_write)
    arguments = ["--root", str(root), "--output", str(output)]
    if mode == "check":
        arguments.append("--check")

    assert inventory_module.main(arguments) == 1
    assert output.read_text(encoding="utf-8") == "prior artifact\n"


@pytest.mark.parametrize(
    "corruption",
    [
        "transport_kind_number",
        "transport_kind_list",
        "method_got",
        "url_expression_list",
        "method_list",
        "invalid_observation",
        "unresolved_domain_null",
        "unresolved_reason_list",
        "unresolved_expression_object",
        "unresolved_owner_null",
        "unresolved_reason_unknown",
        "top_unknown_key",
        "transport_unknown_key",
        "bool_line",
        "operation_reference_object",
        "operation_callee_list",
        "url_template_object",
        "source_path_empty",
    ],
)
def test_compiler_helper_schema_corruption_fails_before_id_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    payload = copy.deepcopy(_valid_helper_payload())
    transport = payload["transports"][0]
    operation = payload["operations"][0]
    unresolved = payload["unresolved"][0]

    if corruption == "transport_kind_number":
        transport["kind"] = 42
    elif corruption == "transport_kind_list":
        transport["kind"] = ["fetch"]
    elif corruption == "method_got":
        transport["method"] = "GOT"
    elif corruption == "url_expression_list":
        transport["url_expression"] = ["/api/value"]
    elif corruption == "method_list":
        transport["method"] = ["GET"]
    elif corruption == "invalid_observation":
        transport["non_2xx_observation"] = "sometimes"
    elif corruption == "unresolved_domain_null":
        unresolved["domain"] = None
    elif corruption == "unresolved_reason_list":
        unresolved["reason"] = ["bad"]
    elif corruption == "unresolved_expression_object":
        unresolved["expression"] = {"value": "path"}
    elif corruption == "unresolved_owner_null":
        unresolved["owner"] = None
    elif corruption == "unresolved_reason_unknown":
        unresolved["reason"] = "invented reason"
    elif corruption == "top_unknown_key":
        payload["surprise"] = True
    elif corruption == "transport_unknown_key":
        transport["surprise"] = True
    elif corruption == "bool_line":
        transport["source"]["line"] = True
    elif corruption == "operation_reference_object":
        operation["_transport_ref"] = {"path": "web/src/fact.ts"}
    elif corruption == "operation_callee_list":
        operation["kind"] = "one_hop_wrapper_call"
        operation["expanded_wrapper"] = ["load"]
    elif corruption == "url_template_object":
        operation["url_template"] = {"path": "/api/value"}
    elif corruption == "source_path_empty":
        unresolved["source"]["path"] = ""
    else:
        raise AssertionError(f"unhandled corruption {corruption}")

    _mock_helper_payload(monkeypatch, payload)

    def forbidden_ids(*_args, **_kwargs):
        raise AssertionError("schema validation must precede ID construction")

    monkeypatch.setattr(inventory_module, "_assign_ids", forbidden_ids)

    with pytest.raises(inventory_module.FrontendInventoryError):
        inventory_module._frontend(root)


@pytest.mark.parametrize(
    "contradiction",
    ["transport_reference_path", "operation_source_path"],
)
def test_cross_file_reference_contradictions_fail_before_id_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contradiction: str,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    _frontend(root, "other.ts", "fetch('/api/other')\n")
    payload = _valid_helper_payload()
    payload["files"] = ["web/src/fact.ts", "web/src/other.ts"]
    if contradiction == "transport_reference_path":
        payload["transports"][0]["_transport_ref"] = "web/src/other.ts:0"
        payload["operations"][0]["_transport_ref"] = "web/src/other.ts:0"
    else:
        payload["operations"][0]["source"]["path"] = "web/src/other.ts"
    _mock_helper_payload(monkeypatch, payload)

    def forbidden_ids(*_args, **_kwargs):
        raise AssertionError("relational validation must precede ID construction")

    monkeypatch.setattr(inventory_module, "_assign_ids", forbidden_ids)

    with pytest.raises(inventory_module.FrontendInventoryError):
        inventory_module._frontend(root)


def test_same_file_wrapper_reference_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    payload = _valid_helper_payload()
    payload["operations"][0].update(
        {
            "expanded_wrapper": "load",
            "kind": "one_hop_wrapper_call",
        }
    )
    _mock_helper_payload(monkeypatch, payload)

    transports, operations, _unresolved, _version = inventory_module._frontend(root)

    assert operations[0]["kind"] == "one_hop_wrapper_call"
    assert operations[0]["transport_id"] == transports[0]["id"]
    assert operations[0]["source"]["path"] == transports[0]["source"]["path"]


@pytest.mark.parametrize("mode", ["write", "check"])
def test_cross_file_reference_failure_does_not_mutate_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    root = _repo(tmp_path / "repo")
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    _frontend(root, "other.ts", "fetch('/api/other')\n")
    output = root / "inventory.json"
    output.write_text("prior artifact\n", encoding="utf-8")
    payload = _valid_helper_payload()
    payload["files"] = ["web/src/fact.ts", "web/src/other.ts"]
    payload["operations"][0]["source"]["path"] = "web/src/other.ts"
    _mock_helper_payload(monkeypatch, payload)

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("cross-file facts must never reach the writer")

    monkeypatch.setattr(inventory_module, "_atomic_write", forbidden_write)
    arguments = ["--root", str(root), "--output", str(output)]
    if mode == "check":
        arguments.append("--check")

    assert inventory_module.main(arguments) == 1
    assert output.read_text(encoding="utf-8") == "prior artifact\n"


@pytest.mark.parametrize("failure_mode", ["unavailable", "nonzero", "invalid_json"])
def test_frontend_compiler_failures_preserve_prior_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    root = _repo(tmp_path / "repo")
    output = root / "inventory.json"
    output.write_text("prior artifact\n", encoding="utf-8")

    def failed_run(*_args, **_kwargs):
        if failure_mode == "unavailable":
            raise FileNotFoundError("node missing")
        if failure_mode == "nonzero":
            return subprocess.CompletedProcess(
                args=["node"],
                returncode=2,
                stdout="",
                stderr="TypeScript compiler unavailable",
            )
        return subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout="{not-json",
            stderr="",
        )

    monkeypatch.setattr(inventory_module.subprocess, "run", failed_run)

    result = inventory_module.main(
        ["--root", str(root), "--output", str(output)]
    )

    assert result == 1
    assert output.read_text(encoding="utf-8") == "prior artifact\n"


@pytest.mark.parametrize("mode", ["write", "check"])
@pytest.mark.parametrize("failure_mode", ["schema", "timeout"])
def test_schema_and_timeout_failures_do_not_mutate_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    failure_mode: str,
) -> None:
    root = _repo(tmp_path / "repo")
    _frontend(root, "fact.ts", "fetch('/api/value')\n")
    output = root / "inventory.json"
    output.write_text("prior artifact\n", encoding="utf-8")

    if failure_mode == "schema":
        payload = _valid_helper_payload()
        payload["transports"][0]["kind"] = 42
        _mock_helper_payload(monkeypatch, payload)
    else:
        def timed_out(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        monkeypatch.setattr(inventory_module.subprocess, "run", timed_out)

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("failed helper data must never reach the writer")

    monkeypatch.setattr(inventory_module, "_atomic_write", forbidden_write)
    arguments = ["--root", str(root), "--output", str(output)]
    if mode == "check":
        arguments.append("--check")

    result = inventory_module.main(arguments)

    assert result == 1
    assert output.read_text(encoding="utf-8") == "prior artifact\n"


def test_frontend_helper_uses_argument_list_without_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)

    def inspect_run(command, **kwargs):
        assert isinstance(command, list)
        assert command == [
            "node",
            str(inventory_module.FRONTEND_HELPER),
            "--root",
            str(root.resolve()),
        ]
        assert "shell" not in kwargs
        assert kwargs["timeout"] == inventory_module.FRONTEND_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(
                {
                    "parser": "TypeScript compiler API",
                    "typescript_version": "5.9.3",
                    "files": [],
                    "transports": [],
                    "operations": [],
                    "unresolved": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(inventory_module.subprocess, "run", inspect_run)

    payload = inventory_module._frontend_payload(root)

    assert payload["typescript_version"] == "5.9.3"


def test_output_outside_resolved_root_is_rejected_without_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path / "repo")
    outside = tmp_path / "outside.json"

    def forbidden_subprocess(*_args, **_kwargs):
        raise AssertionError("outside-root validation must precede frontend parsing")

    monkeypatch.setattr(inventory_module.subprocess, "run", forbidden_subprocess)

    result = inventory_module.main(
        ["--root", str(root), "--output", str(outside)]
    )

    assert result == 2
    assert not outside.exists()


@pytest.mark.parametrize("failure_site", ["write", "replace"])
def test_atomic_generation_failure_preserves_prior_artifact_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_site: str,
) -> None:
    root = _repo(tmp_path / "repo")
    output = root / "docs" / "generated" / "inventory.json"
    output.parent.mkdir(parents=True)
    output.write_text("prior artifact\n", encoding="utf-8")
    before = set(output.parent.iterdir())

    if failure_site == "write":
        original_write_text = Path.write_text

        def bomb_temp_write(path: Path, *args, **kwargs):
            if path.name.startswith(f".{output.name}."):
                raise OSError("write bomb")
            return original_write_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", bomb_temp_write)
    else:
        def bomb_replace(*_args, **_kwargs):
            raise OSError("replace bomb")

        monkeypatch.setattr(inventory_module.os, "replace", bomb_replace)

    result = inventory_module.main(
        ["--root", str(root), "--output", str(output)]
    )

    assert result == 1
    assert output.read_text(encoding="utf-8") == "prior artifact\n"
    assert set(output.parent.iterdir()) == before


def test_check_mode_does_not_call_atomic_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    output = root / "inventory.json"
    output.write_text(
        inventory_module.render_inventory(_build(root)),
        encoding="utf-8",
    )

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("--check must remain read-only")

    monkeypatch.setattr(
        inventory_module,
        "_atomic_write",
        forbidden_write,
        raising=False,
    )

    assert inventory_module.main(
        ["--root", str(root), "--output", str(output), "--check"]
    ) == 0


def test_repository_artifact_is_current() -> None:
    assert inventory_module.main(["--root", str(REPO_ROOT), "--check"]) == 0

from __future__ import annotations

import importlib.util
import json
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
    (tmp_path / "web_server.py").write_text(backend, encoding="utf-8")
    (tmp_path / "web" / "src").mkdir(parents=True)
    return tmp_path


def _frontend(root: Path, relative: str, source: str) -> None:
    path = root / "web" / "src" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _build(root: Path) -> dict:
    return inventory_module.build_inventory(root)


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


def test_repository_artifact_is_current() -> None:
    assert inventory_module.main(["--root", str(REPO_ROOT), "--check"]) == 0

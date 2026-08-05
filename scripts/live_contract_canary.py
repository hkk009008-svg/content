#!/usr/bin/env python3
"""Fail-closed authorization and runner for the manual live-contract canary.

This module never selects tests from arbitrary input.  Each accepted target
maps to one fixed integration test, intended cost, and hard cost ceiling.
Input-only preflight is safe before protected-environment secrets are exposed;
the live job repeats the checks with secrets immediately before pytest.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


APPROVAL_PHRASE = "I APPROVE ONE LIVE CONTRACT CANARY"
TARGET_ENV = "LIVE_CONTRACT_CANARY_TARGET"
APPROVAL_ENV = "LIVE_CONTRACT_CANARY_APPROVAL"
MAX_COST_ENV = "LIVE_CONTRACT_CANARY_MAX_COST_USD"
MAX_PROBE_JSON_BYTES = 32 * 1024 * 1024


class CanaryPreflightError(ValueError):
    """The requested live call is not explicitly and safely authorized."""


@dataclass(frozen=True)
class CanaryTarget:
    test_selector: str
    estimated_cost_usd: Decimal
    hard_ceiling_usd: Decimal
    required_secrets: tuple[str, ...]
    runpod_url_env: str | None = None
    runpod_token_env: str | None = None
    runpod_contract: str | None = None


TARGETS = {
    "runway-act-two": CanaryTarget(
        test_selector=(
            "tests/integration/test_act_two_smoke.py::"
            "test_act_two_minimal_call_returns_mp4"
        ),
        estimated_cost_usd=Decimal("0.15"),
        hard_ceiling_usd=Decimal("0.20"),
        required_secrets=("RUNWAYML_API_SECRET",),
    ),
    "runpod-pulid-production": CanaryTarget(
        test_selector=(
            "tests/integration/test_pulid_smoke.py::"
            "test_production_pulid_round_trip"
        ),
        estimated_cost_usd=Decimal("0.04"),
        hard_ceiling_usd=Decimal("0.05"),
        required_secrets=("COMFYUI_SERVER_URL", "COMFYUI_API_KEY"),
        runpod_url_env="COMFYUI_SERVER_URL",
        runpod_token_env="COMFYUI_API_KEY",
        runpod_contract="production PuLID",
    ),
    "runpod-liveportrait-performance": CanaryTarget(
        test_selector=(
            "tests/integration/test_live_portrait_smoke.py::"
            "test_live_portrait_pod_round_trip"
        ),
        estimated_cost_usd=Decimal("0.03"),
        hard_ceiling_usd=Decimal("0.05"),
        required_secrets=(
            "PERFORMANCE_COMFYUI_SERVER_URL",
            "PERFORMANCE_COMFYUI_API_KEY",
        ),
        runpod_url_env="PERFORMANCE_COMFYUI_SERVER_URL",
        runpod_token_env="PERFORMANCE_COMFYUI_API_KEY",
        runpod_contract="LivePortrait performance",
    ),
}


def _parse_budget(raw: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise CanaryPreflightError(f"{MAX_COST_ENV} must be a finite USD number") from exc
    if not value.is_finite() or value <= 0:
        raise CanaryPreflightError(f"{MAX_COST_ENV} must be finite and greater than zero")
    if value.as_tuple().exponent < -2:
        raise CanaryPreflightError(f"{MAX_COST_ENV} must use no more than two decimal places")
    return value


def validate_inputs(environ: Mapping[str, str]) -> tuple[str, CanaryTarget, Decimal]:
    target_name = environ.get(TARGET_ENV, "")
    target = TARGETS.get(target_name)
    if target is None:
        raise CanaryPreflightError(
            f"{TARGET_ENV} must select exactly one of: {', '.join(sorted(TARGETS))}"
        )
    if environ.get(APPROVAL_ENV, "") != APPROVAL_PHRASE:
        raise CanaryPreflightError(
            f"{APPROVAL_ENV} must exactly match the documented approval phrase"
        )
    budget = _parse_budget(environ.get(MAX_COST_ENV, ""))
    if budget < target.estimated_cost_usd:
        raise CanaryPreflightError(
            f"{MAX_COST_ENV} is below the fixed {target_name} canary estimate "
            f"of ${target.estimated_cost_usd}"
        )
    if budget > target.hard_ceiling_usd:
        raise CanaryPreflightError(
            f"{MAX_COST_ENV} exceeds the {target_name} hard ceiling "
            f"of ${target.hard_ceiling_usd}"
        )
    return target_name, target, budget


def _looks_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(
        marker in lowered
        for marker in ("placeholder", "changeme", "replace-me", "not-a-real")
    )


def _validate_runpod_url(raw: str, variable_name: str) -> None:
    parsed = urlsplit(raw.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CanaryPreflightError(
            f"{variable_name} must be a credential-free HTTPS origin"
        )
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "metadata", "metadata.google.internal"}:
        raise CanaryPreflightError(
            f"{variable_name} must identify the protected remote gateway"
        )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise CanaryPreflightError(
            f"{variable_name} must not use a non-global IP literal"
        )


def validate_secrets(
    target_name: str,
    target: CanaryTarget,
    environ: Mapping[str, str],
) -> None:
    for name in target.required_secrets:
        value = environ.get(name, "")
        if _looks_placeholder(value):
            raise CanaryPreflightError(f"required protected-environment secret {name} is absent")
    if target_name == "runway-act-two" and len(environ["RUNWAYML_API_SECRET"].strip()) < 16:
        raise CanaryPreflightError("RUNWAYML_API_SECRET does not satisfy the canary key contract")
    if target.runpod_url_env and target.runpod_token_env:
        _validate_runpod_url(environ[target.runpod_url_env], target.runpod_url_env)
        if len(environ[target.runpod_token_env].strip()) < 32:
            raise CanaryPreflightError(
                f"{target.runpod_token_env} does not satisfy the gateway token contract"
            )


def preflight(environ: Mapping[str, str], *, require_secrets: bool) -> CanaryTarget:
    target_name, target, budget = validate_inputs(environ)
    if require_secrets:
        validate_secrets(target_name, target, environ)
    print(
        "live-contract preflight passed: "
        f"target={target_name} selector={target.test_selector} "
        f"estimate_usd={target.estimated_cost_usd} max_cost_usd={budget} "
        f"secrets_checked={'yes' if require_secrets else 'no'}"
    )
    return target


def _request_runpod_json(origin: str, path: str, *, token: str | None) -> object:
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(origin.rstrip("/") + path, headers=headers)

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            return None

    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            if response.status != 200:
                raise CanaryPreflightError(f"RunPod probe {path} returned HTTP {response.status}")
            if response.headers.get_content_type() != "application/json":
                raise CanaryPreflightError(f"RunPod probe {path} did not return JSON")
            if token is not None and response.headers.get("X-Content-Gateway") != "authenticated":
                raise CanaryPreflightError(
                    f"RunPod probe {path} did not traverse the authenticated gateway"
                )
            payload = response.read(MAX_PROBE_JSON_BYTES + 1)
    except HTTPError as exc:
        raise CanaryPreflightError(f"RunPod probe {path} returned HTTP {exc.code}") from exc
    except (URLError, OSError) as exc:
        raise CanaryPreflightError(f"RunPod probe {path} was unavailable") from exc
    if len(payload) > MAX_PROBE_JSON_BYTES:
        raise CanaryPreflightError(f"RunPod probe {path} exceeded its response limit")
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CanaryPreflightError(f"RunPod probe {path} returned invalid JSON") from exc


def probe_runpod(environ: Mapping[str, str]) -> None:
    target_name, target, _budget = validate_inputs(environ)
    validate_secrets(target_name, target, environ)
    if not target.runpod_url_env or not target.runpod_token_env:
        print("zero-cost RunPod probe not selected")
        return

    origin = environ[target.runpod_url_env].strip()
    token = environ[target.runpod_token_env].strip()
    ready = _request_runpod_json(origin, "/health/ready", token=None)
    if not isinstance(ready, dict) or ready.get("status") != "ready":
        raise CanaryPreflightError("RunPod gateway readiness schema is not ready")
    stats = _request_runpod_json(origin, "/system_stats", token=token)
    if not isinstance(stats, dict) or not isinstance(stats.get("system"), dict):
        raise CanaryPreflightError("RunPod system_stats contract is invalid")
    object_info = _request_runpod_json(origin, "/object_info", token=token)
    if target_name == "runpod-pulid-production":
        workflow_path = Path(__file__).resolve().parent.parent / "pulid.json"
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CanaryPreflightError(
                "production PuLID workflow is unavailable or invalid"
            ) from exc
        if not isinstance(workflow, dict):
            raise CanaryPreflightError("production PuLID workflow is not an object")
        required_nodes = {
            node.get("class_type")
            for node in workflow.values()
            if isinstance(node, dict) and isinstance(node.get("class_type"), str)
        }
        if not required_nodes:
            raise CanaryPreflightError("production PuLID workflow declares no nodes")
    else:
        required_nodes = {
            "LoadImage",
            "VHS_LoadVideoPath",
            "LivePortraitProcess",
            "VHS_VideoCombine",
        }
    if not isinstance(object_info, dict):
        raise CanaryPreflightError("RunPod object_info contract is not an object")
    missing = sorted(required_nodes.difference(object_info))
    if missing:
        raise CanaryPreflightError(
            f"RunPod {target.runpod_contract} node contract is incomplete: "
            + ", ".join(missing)
        )
    print(
        "authenticated zero-cost RunPod readiness contract passed: "
        f"{target.runpod_contract}"
    )


def run_canary(environ: Mapping[str, str]) -> int:
    target = preflight(environ, require_secrets=True)
    child_environment = dict(environ)
    if target.runpod_url_env and target.runpod_token_env:
        # Application adapters intentionally consume one canonical ComfyUI
        # configuration. Map the selected, contract-specific endpoint only in
        # the isolated pytest process so performance cannot silently run on the
        # pinned production PuLID endpoint.
        child_environment["COMFYUI_SERVER_URL"] = environ[target.runpod_url_env]
        child_environment["COMFYUI_API_KEY"] = environ[target.runpod_token_env]
    command = [
        sys.executable,
        "-m",
        "pytest",
        target.test_selector,
        "-m",
        "e2e",
        "--maxfail=1",
        "-q",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parent.parent,
            env=child_environment,
            check=False,
            timeout=720,
        )
    except subprocess.TimeoutExpired:
        print("live-contract canary exceeded its 12-minute runner timeout", file=sys.stderr)
        return 124
    return result.returncode


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("check-inputs", "check-ready", "probe-runpod", "run"),
        help="input check, protected-secret check, RunPod probe, or one fixed live test",
    )
    args = parser.parse_args(argv)
    values = os.environ if environ is None else environ
    try:
        if args.mode == "check-inputs":
            preflight(values, require_secrets=False)
            return 0
        if args.mode == "check-ready":
            preflight(values, require_secrets=True)
            return 0
        if args.mode == "probe-runpod":
            probe_runpod(values)
            return 0
        return run_canary(values)
    except CanaryPreflightError as exc:
        print(f"live-contract preflight refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

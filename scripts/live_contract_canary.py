#!/usr/bin/env python3
"""Fail-closed authorization and runner for the manual live-contract canary.

This module never selects tests from arbitrary input.  Each accepted target
maps to one fixed integration test, intended cost, and hard cost ceiling.
Input-only preflight is safe before protected-environment secrets are exposed;
the live job repeats the checks with secrets immediately before pytest.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Mapping
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

# GitHub Actions and the documented operator commands execute this file by
# path (``python scripts/live_contract_canary.py ...``).  In that mode Python
# puts ``scripts/`` rather than the repository root on ``sys.path``.  Establish
# the root explicitly before importing application modules so authorization
# cannot fail before its own input checks run.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from performance.live_portrait_workflow import (
    LIVE_PORTRAIT_REQUIRED_NODE_CLASSES,
    build_live_portrait_workflow,
)


APPROVAL_PHRASE = "I APPROVE ONE LIVE CONTRACT CANARY"
TARGET_ENV = "LIVE_CONTRACT_CANARY_TARGET"
APPROVAL_ENV = "LIVE_CONTRACT_CANARY_APPROVAL"
MAX_COST_ENV = "LIVE_CONTRACT_CANARY_MAX_COST_USD"
WINDOWS_RUNNER_AUTHORIZATION_ENV = (
    "LIVE_CONTRACT_CANARY_WINDOWS_RUNNER_AUTHORIZATION"
)
WINDOWS_RUNNER_AUTHORIZATION_PHRASE = "I CONFIRM EPHEMERAL JIT RUNNER"
RUNWAY_LEDGER_ENV = "LIVE_CONTRACT_CANARY_LEDGER_PATH"
RUNWAY_FIXTURE_DIR_ENV = "LIVE_CONTRACT_CANARY_FIXTURE_DIR"
RUNWAY_AUTHORITY_TOKEN_ENV = "CANARY_AUTHORITY_GITHUB_TOKEN"
RUNWAY_FIXTURE_SHA256 = (
    "97471b9377c817251c86dbb58982464d7586b6b3d800936683f900da668c0fb6"
)
RUNWAY_ATTEMPT_VERSION = "v4"
RUNWAY_AUTHORITY_TASK = (
    f"live-canary:runway-act-two:{RUNWAY_ATTEMPT_VERSION}:"
    f"{RUNWAY_FIXTURE_SHA256[:8]}"
)
RUNWAY_AUTHORITY_ENVIRONMENT = "live-contract-canary"
WINDOWS_LIVEPORTRAIT_ORIGIN = "http://127.0.0.1:18189"


class CanaryPreflightError(ValueError):
    """The requested live call is not explicitly and safely authorized."""


@dataclass(frozen=True)
class CanaryTarget:
    test_selector: str
    estimated_cost_usd: Decimal
    hard_ceiling_usd: Decimal
    required_secrets: tuple[str, ...]
    worker_url_env: str | None = None
    worker_token_env: str | None = None
    worker_contract: str | None = None
    worker_kind: str | None = None


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
    "windows-liveportrait-performance": CanaryTarget(
        test_selector=(
            "tests/integration/test_live_portrait_smoke.py::"
            "test_live_portrait_windows_round_trip"
        ),
        estimated_cost_usd=Decimal("0.00"),
        hard_ceiling_usd=Decimal("0.00"),
        required_secrets=("PERFORMANCE_COMFYUI_API_KEY",),
        worker_url_env="PERFORMANCE_COMFYUI_SERVER_URL",
        worker_token_env="PERFORMANCE_COMFYUI_API_KEY",
        worker_contract="Windows LivePortrait performance",
        worker_kind="windows-liveportrait",
    ),
}


def _parse_budget(raw: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise CanaryPreflightError(f"{MAX_COST_ENV} must be a finite USD number") from exc
    if not value.is_finite() or value < 0:
        raise CanaryPreflightError(f"{MAX_COST_ENV} must be finite and non-negative")
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
    runner_authorization = environ.get(WINDOWS_RUNNER_AUTHORIZATION_ENV, "")
    if target_name == "windows-liveportrait-performance":
        if runner_authorization != WINDOWS_RUNNER_AUTHORIZATION_PHRASE:
            raise CanaryPreflightError(
                f"{WINDOWS_RUNNER_AUTHORIZATION_ENV} must exactly confirm the "
                "documented ephemeral JIT runner procedure"
            )
    elif runner_authorization:
        raise CanaryPreflightError(
            f"{WINDOWS_RUNNER_AUTHORIZATION_ENV} is only valid for the Windows target"
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


def _validate_remote_worker_url(raw: str, variable_name: str) -> None:
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


def _validate_windows_tunnel_url(raw: str, variable_name: str) -> None:
    if raw.strip() != WINDOWS_LIVEPORTRAIT_ORIGIN:
        raise CanaryPreflightError(
            f"{variable_name} must be the fixed Mac loopback tunnel origin "
            f"{WINDOWS_LIVEPORTRAIT_ORIGIN}"
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
    if target.worker_url_env and target.worker_token_env:
        worker_url = environ.get(target.worker_url_env, "")
        if target.worker_kind == "windows-liveportrait":
            _validate_windows_tunnel_url(worker_url, target.worker_url_env)
        else:
            _validate_remote_worker_url(worker_url, target.worker_url_env)
        if len(environ[target.worker_token_env].strip()) < 32:
            raise CanaryPreflightError(
                f"{target.worker_token_env} does not satisfy the gateway token contract"
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


def _github_api_json(
    method: str,
    path: str,
    *,
    token: str,
    payload: object | None = None,
    accepted_statuses: tuple[int, ...] = (200,),
) -> tuple[int, object]:
    """Call one bounded GitHub JSON endpoint without exposing credentials."""
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "content-live-contract-canary",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        f"https://api.github.com{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            status = response.status
            raw = response.read(1024 * 1024 + 1)
    except HTTPError as exc:
        status = exc.code
        raw = exc.read(1024 * 1024 + 1)
    except (URLError, OSError) as exc:
        raise CanaryPreflightError("GitHub canary-authority store is unavailable") from exc
    if status not in accepted_statuses:
        raise CanaryPreflightError(
            f"GitHub canary-authority store returned HTTP {status}"
        )
    if len(raw) > 1024 * 1024:
        raise CanaryPreflightError("GitHub canary-authority response exceeded its limit")
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CanaryPreflightError(
            "GitHub canary-authority store returned invalid JSON"
        ) from exc


def _runway_authority_payload(payload: object, expected_sha: str) -> dict:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CanaryPreflightError("Runway deployment payload is invalid") from exc
    if not isinstance(payload, dict):
        raise CanaryPreflightError("Runway deployment payload is not an object")
    expected = {
        "schema_version": 1,
        "target": "runway-act-two",
        "logical_attempt": f"{RUNWAY_ATTEMPT_VERSION}-{RUNWAY_FIXTURE_SHA256[:8]}",
        "fixture_sha256": RUNWAY_FIXTURE_SHA256,
        "source_sha": expected_sha,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise CanaryPreflightError("Runway deployment payload is incompatible")
    return payload


def _canonical_runway_task_id(raw: object) -> str:
    if not isinstance(raw, str) or raw != raw.strip():
        raise CanaryPreflightError("Runway task ID is invalid")
    try:
        value = str(uuid.UUID(raw))
    except (ValueError, AttributeError) as exc:
        raise CanaryPreflightError("Runway task ID is not a UUID") from exc
    if raw.lower() != value:
        raise CanaryPreflightError("Runway task ID is not canonical")
    return value


def _deployment_task_id(statuses: object) -> str:
    if not isinstance(statuses, list):
        raise CanaryPreflightError("Runway deployment status history is invalid")
    task_ids: set[str] = set()
    for status in statuses:
        if not isinstance(status, dict):
            raise CanaryPreflightError("Runway deployment status is invalid")
        description = status.get("description")
        if not isinstance(description, str):
            continue
        prefix = "runway_task_id="
        if description.startswith(prefix):
            task_ids.add(_canonical_runway_task_id(description[len(prefix):]))
    if len(task_ids) > 1:
        raise CanaryPreflightError("Runway deployment owns conflicting task IDs")
    return next(iter(task_ids), "")


def _list_runway_deployments(repository: str, token: str) -> list[dict]:
    query = (
        f"task={quote(RUNWAY_AUTHORITY_TASK, safe='')}"
        f"&environment={quote(RUNWAY_AUTHORITY_ENVIRONMENT, safe='')}"
        "&per_page=2"
    )
    _status, deployments = _github_api_json(
        "GET",
        f"/repos/{repository}/deployments?{query}",
        token=token,
        accepted_statuses=(200,),
    )
    if not isinstance(deployments, list) or any(
        not isinstance(deployment, dict) for deployment in deployments
    ):
        raise CanaryPreflightError("Runway deployment authority list is invalid")
    if len(deployments) > 1:
        raise CanaryPreflightError("multiple Runway deployment authorities exist")
    return deployments


def _deployment_recovery(
    repository: str,
    token: str,
    deployment: dict,
    expected_sha: str,
) -> tuple[int, str, dict]:
    deployment_sha = deployment.get("sha")
    if (
        not isinstance(deployment_sha, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", deployment_sha)
        or deployment_sha.lower() != expected_sha
    ):
        raise CanaryPreflightError(
            "Runway Deployment source SHA drifted from the current canary code"
        )
    payload = _runway_authority_payload(deployment.get("payload"), expected_sha)
    deployment_id = deployment.get("id")
    if not isinstance(deployment_id, int) or deployment_id <= 0:
        raise CanaryPreflightError("Runway deployment authority ID is invalid")
    _status, statuses = _github_api_json(
        "GET",
        f"/repos/{repository}/deployments/{deployment_id}/statuses?per_page=100",
        token=token,
        accepted_statuses=(200,),
    )
    return deployment_id, _deployment_task_id(statuses), payload


def _github_run_identity(
    environ: Mapping[str, str],
) -> tuple[str, str, str, str, str]:
    repository = environ.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise CanaryPreflightError("GITHUB_REPOSITORY is invalid")
    token = environ.get(RUNWAY_AUTHORITY_TOKEN_ENV, "")
    if len(token) < 16:
        raise CanaryPreflightError("GitHub canary-authority token is unavailable")
    head_sha = environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
        raise CanaryPreflightError("GITHUB_SHA is invalid")
    run_id = environ.get("GITHUB_RUN_ID", "")
    run_attempt = environ.get("GITHUB_RUN_ATTEMPT", "")
    if not run_id.isdecimal() or not run_attempt.isdecimal():
        raise CanaryPreflightError("GitHub run identity is invalid")
    if environ.get("GITHUB_REF", "") != "refs/heads/main":
        raise CanaryPreflightError("live canary authority is restricted to main")
    return repository, token, head_sha.lower(), run_id, run_attempt


def _deployment_owner_matches(payload: Mapping[str, object], run_id: str, run_attempt: str) -> bool:
    return (
        str(payload.get("owner_run_id") or "") == run_id
        and str(payload.get("owner_run_attempt") or "") == run_attempt
    )


def claim_runway_submission(environ: Mapping[str, str]) -> int:
    """Create the logical-attempt preclaim immediately before provider POST.

    Fixture construction and ephemeral uploads happen before this callback.
    Once this returns, the only next fallible external operation is the one
    non-retrying Runway creation POST.
    """
    target_name, _target, _budget = validate_inputs(environ)
    if target_name != "runway-act-two":
        raise CanaryPreflightError("Runway submission fence used for another target")
    repository, token, head_sha, run_id, run_attempt = _github_run_identity(environ)

    deployments = _list_runway_deployments(repository, token)
    if deployments:
        deployment_id, task_id, payload = _deployment_recovery(
            repository, token, deployments[0], head_sha
        )
        if task_id:
            raise CanaryPreflightError(
                "Runway task was accepted concurrently; fresh submission blocked"
            )
        if not _deployment_owner_matches(payload, run_id, run_attempt):
            raise CanaryPreflightError(
                "Runway preclaim belongs to another run attempt; submission blocked"
            )
        print("current run attempt already owns the Runway pre-submit claim")
        return deployment_id

    authority_payload = {
        "schema_version": 1,
        "target": "runway-act-two",
        "logical_attempt": f"{RUNWAY_ATTEMPT_VERSION}-{RUNWAY_FIXTURE_SHA256[:8]}",
        "fixture_sha256": RUNWAY_FIXTURE_SHA256,
        "source_sha": head_sha,
        "owner_run_id": run_id,
        "owner_run_attempt": run_attempt,
    }
    _status, created = _github_api_json(
        "POST",
        f"/repos/{repository}/deployments",
        token=token,
        payload={
            "ref": head_sha,
            "task": RUNWAY_AUTHORITY_TASK,
            "environment": RUNWAY_AUTHORITY_ENVIRONMENT,
            "description": "Pre-submit fence for one reviewed Runway Act-Two canary",
            "auto_merge": False,
            "required_contexts": [],
            "production_environment": False,
            "transient_environment": False,
            "payload": authority_payload,
        },
        accepted_statuses=(201,),
    )
    if not isinstance(created, dict) or not isinstance(created.get("id"), int):
        raise CanaryPreflightError("created Runway deployment authority is invalid")
    # Re-query before provider access so a concurrent duplicate preclaim cannot
    # silently create two automatic submission owners.
    deployments = _list_runway_deployments(repository, token)
    if len(deployments) != 1 or deployments[0].get("id") != created["id"]:
        raise CanaryPreflightError("Runway deployment preclaim is not unique")
    deployment_id, task_id, payload = _deployment_recovery(
        repository, token, deployments[0], head_sha
    )
    if task_id or not _deployment_owner_matches(payload, run_id, run_attempt):
        raise CanaryPreflightError("created Runway preclaim is not exclusive")
    print("Runway pre-submit claim created at the provider boundary")
    return deployment_id


def checkpoint_runway_task(environ: Mapping[str, str], task_id: str) -> None:
    """Append a Runway task UUID to its durable Deployment status history."""
    task_id = _canonical_runway_task_id(task_id)
    repository, token, head_sha, run_id, run_attempt = _github_run_identity(environ)
    deployments = _list_runway_deployments(repository, token)
    if len(deployments) != 1:
        raise CanaryPreflightError("Runway preclaim is unavailable at task acceptance")
    deployment_id, known_id, payload = _deployment_recovery(
        repository, token, deployments[0], head_sha
    )
    if not _deployment_owner_matches(payload, run_id, run_attempt):
        raise CanaryPreflightError("Runway preclaim owner changed before task acceptance")
    if known_id:
        if known_id != task_id:
            raise CanaryPreflightError(
                "Runway fence already owns a different provider task ID"
            )
        print("Runway task ID was already durable in the authority store")
        return
    last_error: CanaryPreflightError | None = None
    for retry_index in range(4):
        try:
            _status, statuses = _github_api_json(
                "GET",
                f"/repos/{repository}/deployments/{deployment_id}/statuses?per_page=100",
                token=token,
                accepted_statuses=(200,),
            )
            known_id = _deployment_task_id(statuses)
            if known_id:
                if known_id != task_id:
                    raise CanaryPreflightError(
                        "Runway fence already owns a different provider task ID"
                    )
                print("Runway task ID was already durable in the authority store")
                return
            update_status, _created = _github_api_json(
                "POST",
                f"/repos/{repository}/deployments/{deployment_id}/statuses",
                token=token,
                payload={
                    "state": "in_progress",
                    "description": f"runway_task_id={task_id}",
                    "environment": RUNWAY_AUTHORITY_ENVIRONMENT,
                    "auto_inactive": False,
                },
                accepted_statuses=(201,),
            )
            if update_status == 201:
                print("Runway task ID checkpointed to durable authority before polling")
                return
        except CanaryPreflightError as exc:
            last_error = exc
        if retry_index < 3:
            time.sleep(0.5 * (2 ** retry_index))
    raise last_error or CanaryPreflightError("Runway task checkpoint failed")


def finalize_runway_deployment(
    environ: Mapping[str, str],
    task_id: str,
    attempt_state: str,
) -> None:
    """Append the terminal provider result to the authority Deployment."""
    task_id = _canonical_runway_task_id(task_id)
    github_state = {
        "succeeded": "success",
        "failed_billed": "failure",
        "failed_unbilled": "failure",
        "cancelled": "inactive",
    }.get(attempt_state)
    if github_state is None:
        raise CanaryPreflightError("Runway attempt is not terminal")
    repository, token, head_sha, _run_id, _run_attempt = _github_run_identity(environ)
    deployments = _list_runway_deployments(repository, token)
    if len(deployments) != 1:
        raise CanaryPreflightError("Runway authority Deployment is unavailable")
    deployment_id, known_id, _payload = _deployment_recovery(
        repository, token, deployments[0], head_sha
    )
    if known_id != task_id:
        raise CanaryPreflightError("Runway terminal result does not match authority")
    _status, statuses = _github_api_json(
        "GET",
        f"/repos/{repository}/deployments/{deployment_id}/statuses?per_page=100",
        token=token,
        accepted_statuses=(200,),
    )
    description = f"runway_task_id={task_id}"
    if isinstance(statuses, list) and any(
        isinstance(status, dict)
        and status.get("state") == github_state
        and status.get("description") == description
        for status in statuses
    ):
        print("Runway terminal Deployment status was already recorded")
        return
    _github_api_json(
        "POST",
        f"/repos/{repository}/deployments/{deployment_id}/statuses",
        token=token,
        payload={
            "state": github_state,
            "description": description,
            "environment": RUNWAY_AUTHORITY_ENVIRONMENT,
            "auto_inactive": False,
        },
        accepted_statuses=(201,),
    )
    print(f"Runway authority Deployment finalized: state={github_state}")


def _runway_attempt_identity(environ: Mapping[str, str]) -> tuple[str, str]:
    from performance.runway_tasks import build_attempt_id

    fixture_dir = Path(environ.get(RUNWAY_FIXTURE_DIR_ENV, "")).resolve()
    if str(fixture_dir) == "." or not environ.get(RUNWAY_FIXTURE_DIR_ENV):
        raise CanaryPreflightError(f"{RUNWAY_FIXTURE_DIR_ENV} is unavailable")
    return build_attempt_id(
        provider="runway",
        engine="ACT_ONE",
        operation="performance_capture",
        video_id="live-contract-canary",
        shot_id="runway-act-two-fixture-v1",
        request={
            "keyframe_path": str(fixture_dir / "kf.jpg"),
            "driving_video_path": str(fixture_dir / "reference.mp4"),
            "duration_s": 3.0,
            "model": "act_two",
            "ratio": "1280:720",
        },
    )


def verify_runway_fence(environ: Mapping[str, str]) -> None:
    """Re-read remote authority on every job attempt before provider access."""
    target_name, _target, _budget = validate_inputs(environ)
    if target_name != "runway-act-two":
        print("Runway submission-fence verification not selected")
        return
    repository, token, head_sha, run_id, run_attempt = _github_run_identity(environ)
    deployments = _list_runway_deployments(repository, token)
    if not deployments:
        print("no Runway preclaim exists; boundary callback may claim first submission")
        return
    _deployment_id, remote_task_id, payload = _deployment_recovery(
        repository, token, deployments[0], head_sha
    )
    ledger_path = Path(environ.get(RUNWAY_LEDGER_ENV, ""))
    if remote_task_id:
        if (
            remote_task_id != remote_task_id.strip()
            or len(remote_task_id) > 512
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in remote_task_id
            )
        ):
            raise CanaryPreflightError("recovered Runway task ID is invalid")
        if not environ.get(RUNWAY_LEDGER_ENV):
            raise CanaryPreflightError(f"{RUNWAY_LEDGER_ENV} is unavailable")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        from cost_tracker import CostTracker

        attempt_id, request_fingerprint = _runway_attempt_identity(environ)
        with CostTracker(
            db_path=str(ledger_path),
            budget_usd=float(_parse_budget(environ.get(MAX_COST_ENV, ""))),
        ) as tracker:
            attempt = tracker.reserve_paid_attempt(
                attempt_id=attempt_id,
                provider="runway",
                engine="ACT_ONE",
                operation="performance_capture",
                estimated_cost_usd=0.15,
                shot_id="runway-act-two-fixture-v1",
                video_id="live-contract-canary",
                request_fingerprint=request_fingerprint,
            )
            known_id = str(attempt.get("provider_job_id") or "")
            if known_id and known_id != remote_task_id:
                raise CanaryPreflightError(
                    "local and remote Runway authorities own different task IDs"
                )
            if not known_id:
                tracker.update_paid_attempt(
                    attempt_id,
                    state="running",
                    provider_job_id=remote_task_id,
                    provider_status="PENDING",
                    detail="Recovered from remote live-canary authority",
                )
        print("remote Runway task ID restored into the local retrieval ledger")
        return
    if _deployment_owner_matches(payload, run_id, run_attempt):
        print("current run attempt owns an unacknowledged Runway preclaim")
        return
    if not environ.get(RUNWAY_LEDGER_ENV) or not ledger_path.is_file():
        raise CanaryPreflightError(
            "prior Runway fence exists but no attempt ledger was recovered; "
            "duplicate submission blocked"
        )
    attempt_id, request_fingerprint = _runway_attempt_identity(environ)
    try:
        connection = sqlite3.connect(
            f"file:{quote(str(ledger_path.resolve()), safe='/')}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT attempt_id, request_fingerprint, provider_job_id "
            "FROM paid_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise CanaryPreflightError("recovered Runway attempt ledger is unreadable") from exc
    finally:
        if "connection" in locals():
            connection.close()
    if (
        row is None
        or row["request_fingerprint"] != request_fingerprint
        or not str(row["provider_job_id"] or "").strip()
    ):
        raise CanaryPreflightError(
            "prior Runway fence has no matching durable provider task ID; "
            "duplicate submission blocked pending manual reconciliation"
        )
    print("existing Runway fence matched a durable task ID; retrieval-only resume permitted")


def probe_worker(environ: Mapping[str, str]) -> None:
    target_name, target, _budget = validate_inputs(environ)
    validate_secrets(target_name, target, environ)
    if not target.worker_url_env or not target.worker_token_env:
        print("zero-cost worker probe not selected")
        return

    origin = environ[target.worker_url_env].strip()
    token = environ[target.worker_token_env].strip()
    if target.worker_kind == "windows-liveportrait":
        from comfyui_client import ComfyUIError, ComfyUIClient
        from performance.worker_readiness import (
            PerformanceWorkerUnavailable,
            require_liveportrait_worker_ready,
        )

        try:
            require_liveportrait_worker_ready(
                SimpleNamespace(
                    comfyui_server_url="",
                    performance_comfyui_server_url=origin,
                    performance_comfyui_api_key=token,
                )
            )
            client = ComfyUIClient(
                origin,
                auth_token=token,
                connect_timeout=2.0,
                read_timeout=5.0,
            )
            stats = client.get_system_stats()
            object_info = client.get_object_info()
            if not isinstance(stats.get("system"), dict):
                raise CanaryPreflightError(
                    "Windows LivePortrait system_stats contract is invalid"
                )
            missing = sorted(
                set(LIVE_PORTRAIT_REQUIRED_NODE_CLASSES).difference(object_info)
            )
            if missing:
                raise CanaryPreflightError(
                    "Windows LivePortrait node contract is incomplete: "
                    + ", ".join(missing)
                )
            contract = copy.deepcopy(object_info)
            placeholders = {
                ("LoadImage", "image"): "contract-keyframe.png",
                ("VHS_LoadVideo", "video"): "contract-driving.mp4",
            }
            for (node_class, input_name), placeholder in placeholders.items():
                spec = contract[node_class]["input"]["required"][input_name]
                choices = spec[0]
                if isinstance(choices, list) and placeholder not in choices:
                    choices.append(placeholder)
            ComfyUIClient._validate_workflow_contract(
                build_live_portrait_workflow(
                    "contract-keyframe.png", "contract-driving.mp4", 2.0
                ),
                contract,
            )
        except CanaryPreflightError:
            raise
        except (
            PerformanceWorkerUnavailable,
            ComfyUIError,
            KeyError,
            TypeError,
            AttributeError,
        ) as exc:
            raise CanaryPreflightError(
                "Windows LivePortrait worker failed its exact role-bound readiness contract"
            ) from exc
        print(
            "authenticated Windows LivePortrait role, manifest, execution, and "
            "workflow contract passed through the Mac loopback tunnel"
        )
        return

    raise CanaryPreflightError("selected worker kind has no active probe contract")


def run_canary(environ: Mapping[str, str]) -> int:
    target = preflight(environ, require_secrets=True)
    child_environment = dict(environ)
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
        choices=(
            "check-inputs",
            "check-ready",
            "verify-runway-fence",
            "probe-worker",
            "run",
        ),
        help=(
            "input check, protected-secret check, provider submission fencing, "
            "worker probe, or one fixed live test"
        ),
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
        if args.mode == "verify-runway-fence":
            verify_runway_fence(values)
            return 0
        if args.mode == "probe-worker":
            probe_worker(values)
            return 0
        return run_canary(values)
    except CanaryPreflightError as exc:
        print(f"live-contract preflight refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

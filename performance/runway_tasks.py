"""Shared Runway paid-task ownership helpers.

No function in this module submits new provider work.  It provides stable
attempt identity, bounded retry for idempotent retrieval, failure-code
classification, and the explicit task-delete cancellation path used by both
Gen-4 and Act-Two.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Optional


TRANSIENT_HTTP_STATUSES = frozenset({429, 502, 503, 504})
_BILLED_SAFETY_MARKERS = ("SAFETY", "MODERAT", "CONTENT_POLICY")
_PERMANENT_MARKERS = (
    "AUTH",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "INVALID",
    "VALIDATION",
    "UNSUPPORTED",
    "BAD_REQUEST",
    *_BILLED_SAFETY_MARKERS,
)


def build_attempt_id(
    *,
    provider: str,
    engine: str,
    operation: str,
    video_id: str,
    shot_id: str,
    request: dict[str, Any],
    ordinal: int = 1,
) -> tuple[str, str]:
    """Return a deterministic attempt ID and request fingerprint."""
    canonical = json.dumps(
        request,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    scope = f"{provider}:{engine}:{operation}:{video_id}:{shot_id}:{ordinal}:{fingerprint}"
    attempt_id = hashlib.sha256(scope.encode("utf-8")).hexdigest()
    return attempt_id, fingerprint


def error_status_code(exc: BaseException) -> Optional[int]:
    value = getattr(exc, "status_code", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def is_transient_error(exc: BaseException) -> bool:
    status = error_status_code(exc)
    if status in TRANSIENT_HTTP_STATUSES:
        return True
    name = type(exc).__name__.upper()
    return any(marker in name for marker in ("CONNECTION", "TIMEOUT", "RATE_LIMIT"))


def retry_after_seconds(
    exc: BaseException,
    *,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Parse Retry-After seconds or an HTTP-date from an SDK exception."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    value = str(raw).strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            seconds = (retry_at - current).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if seconds < 0:
        return 0.0
    return seconds


def retry_delay_seconds(
    exc: BaseException,
    retry_index: int,
    *,
    base_delay_s: float = 0.5,
    random_value: Callable[[], float] = random.random,
    max_delay_s: float = 60.0,
) -> float:
    """Return bounded backoff, honoring a provider Retry-After when present."""
    exponential = base_delay_s * (2 ** max(0, int(retry_index)))
    jittered = exponential + exponential * 0.25 * float(random_value())
    requested = retry_after_seconds(exc)
    delay = max(jittered, requested or 0.0)
    return min(max(0.0, delay), max(0.0, float(max_delay_s)))


def call_with_backoff(
    operation: Callable[[], Any],
    *,
    attempts: int = 4,
    base_delay_s: float = 0.5,
    sleep: Optional[Callable[[float], None]] = None,
    random_value: Optional[Callable[[], float]] = None,
) -> Any:
    """Run an idempotent/transient-safe operation with bounded jitter."""
    attempts = max(1, int(attempts))
    sleep = sleep or time.sleep
    random_value = random_value or random.random
    for index in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if index + 1 >= attempts or not is_transient_error(exc):
                raise
            sleep(
                retry_delay_seconds(
                    exc,
                    index,
                    base_delay_s=base_delay_s,
                    random_value=random_value,
                )
            )
    raise AssertionError("unreachable")


def task_failure_code(task: object) -> str:
    for name in ("failure_code", "failureCode"):
        value = getattr(task, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    failure = getattr(task, "failure", None)
    if isinstance(failure, dict):
        for name in ("failureCode", "failure_code", "code"):
            value = failure.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    if isinstance(failure, str) and failure.strip():
        return failure.strip().upper()[:128]
    return "UNKNOWN_FAILURE"


def classify_task_failure(task: object) -> dict[str, object]:
    code = task_failure_code(task)
    return {
        "code": code,
        "billed": any(marker in code for marker in _BILLED_SAFETY_MARKERS),
        "permanent": any(marker in code for marker in _PERMANENT_MARKERS),
    }


def cancel_runway_attempt(
    cost_tracker,
    attempt_id: str,
    *,
    api_key: Optional[str] = None,
    client_factory: Optional[Callable[..., object]] = None,
) -> dict:
    """Request cancellation through Runway's task DELETE endpoint.

    A successful DELETE is only an acknowledgement, not proof of terminal
    cancellation, so the reservation remains active in ``cancel_requested``.
    Transport ambiguity is recorded as ``accepted_unknown`` and remains
    reserved.  A later adapter re-entry retrieves the same task and settles it
    only after Runway reports ``CANCELLED`` or another terminal state.
    """
    attempt = cost_tracker.get_paid_attempt(attempt_id)
    if not attempt:
        raise KeyError(f"unknown paid attempt {attempt_id!r}")
    if attempt.get("provider") != "runway":
        raise ValueError("attempt is not owned by Runway")
    task_id = attempt.get("provider_job_id")
    if not isinstance(task_id, str) or not task_id:
        return cost_tracker.update_paid_attempt(
            attempt_id,
            state="accepted_unknown",
            detail="Cancellation cannot be bound without a provider task ID",
        )

    cost_tracker.update_paid_attempt(
        attempt_id,
        state="cancel_requested",
        provider_job_id=task_id,
        detail="Runway cancellation requested",
    )
    if client_factory is None:
        from config.settings import settings
        from runwayml import RunwayML

        client_factory = RunwayML
        api_key = api_key or getattr(settings, "runwayml_api_secret", "")
    try:
        client = client_factory(api_key=api_key or "")
        client.tasks.delete(id=task_id)
    except Exception as exc:
        return cost_tracker.update_paid_attempt(
            attempt_id,
            state="accepted_unknown",
            provider_job_id=task_id,
            detail=f"Runway cancellation outcome ambiguous: {type(exc).__name__}",
        )
    return cost_tracker.update_paid_attempt(
        attempt_id,
        state="cancel_requested",
        provider_job_id=task_id,
        detail="Runway accepted cancellation request; awaiting terminal status",
    )

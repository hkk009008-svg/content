"""Deterministic provider-health scoring from durable paid-attempt evidence.

Health is deliberately conservative and explainable:

* fewer than ``MIN_TERMINAL_SAMPLES`` provider outcomes => ``unknown``, unless
  the hard safety signal of three consecutive failures is already present;
* malformed/non-finite evidence => ``unknown`` (never accidentally healthy);
* two unresolved accepted jobs => ``unhealthy`` quarantine even without
  terminal samples, so AUTO does not feed uncertain paid work;
* three trailing failures, success below 50%, or p95 latency >= 15 minutes
  => ``unhealthy``;
* success below 80%, p95 latency >= 8 minutes, any billed failure, or two
  unresolved accepted jobs => ``degraded``;
* otherwise the provider is ``healthy``.

The score is 0-100 after failure, billed-failure, latency, and unresolved-job
penalties. Unknown evidence has ``score=None`` because manufacturing a numeric
confidence would be misleading.
"""

from __future__ import annotations

import math
from typing import Optional


MIN_TERMINAL_SAMPLES = 5
DEGRADED_SUCCESS_RATE = 0.80
UNHEALTHY_SUCCESS_RATE = 0.50
DEGRADED_P95_LATENCY_S = 8 * 60.0
UNHEALTHY_P95_LATENCY_S = 15 * 60.0
UNHEALTHY_CONSECUTIVE_FAILURES = 3
UNHEALTHY_ACCEPTED_UNKNOWN = 2


def assess_provider_health(
    *,
    sample_count: int,
    success_rate: Optional[float],
    p95_terminal_latency_s: Optional[float],
    consecutive_failures: int,
    billed_failures: int,
    accepted_unknown: int,
    data_valid: bool,
) -> dict:
    """Return ``status``, nullable ``score``, and ordered human reasons."""
    if not data_valid:
        return {
            "status": "unknown",
            "score": None,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": ["malformed_or_nonfinite_durable_evidence"],
        }
    if accepted_unknown >= UNHEALTHY_ACCEPTED_UNKNOWN:
        return {
            "status": "unhealthy",
            "score": 0.0,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": [f"accepted_unknown_quarantine:{accepted_unknown}"],
        }
    if sample_count <= 0:
        return {
            "status": "unknown",
            "score": None,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": [
                f"insufficient_terminal_samples:{sample_count}/{MIN_TERMINAL_SAMPLES}"
            ],
        }
    if (
        success_rate is None
        or not math.isfinite(float(success_rate))
        or p95_terminal_latency_s is None
        or not math.isfinite(float(p95_terminal_latency_s))
        or p95_terminal_latency_s < 0
    ):
        return {
            "status": "unknown",
            "score": None,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": ["incomplete_or_nonfinite_health_metrics"],
        }

    failure_rate = max(0.0, min(1.0, 1.0 - float(success_rate)))
    billed_failure_rate = max(0.0, min(1.0, billed_failures / sample_count))
    latency_penalty = max(
        0.0,
        min(20.0, (float(p95_terminal_latency_s) - 300.0) / 30.0),
    )
    score = round(max(
        0.0,
        100.0
        - failure_rate * 65.0
        - billed_failure_rate * 15.0
        - latency_penalty
        - min(15.0, accepted_unknown * 5.0),
    ), 1)

    unhealthy_reasons: list[str] = []
    if consecutive_failures >= UNHEALTHY_CONSECUTIVE_FAILURES:
        unhealthy_reasons.append(
            f"consecutive_failures:{consecutive_failures}"
        )
    # A short but uninterrupted run of failures is an operational safety
    # signal, not a statistical quality claim.  Honor it before the normal
    # minimum-sample gate so AUTO routing stops feeding a provider that has
    # just failed every observed request.
    if unhealthy_reasons:
        return {
            "status": "unhealthy",
            "score": score,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": unhealthy_reasons,
        }

    if sample_count < MIN_TERMINAL_SAMPLES:
        return {
            "status": "unknown",
            "score": None,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": [
                f"insufficient_terminal_samples:{sample_count}/{MIN_TERMINAL_SAMPLES}"
            ],
        }

    if success_rate < UNHEALTHY_SUCCESS_RATE:
        unhealthy_reasons.append(f"success_rate_below_50_percent:{success_rate:.3f}")
    if p95_terminal_latency_s >= UNHEALTHY_P95_LATENCY_S:
        unhealthy_reasons.append(
            f"p95_latency_at_least_900s:{p95_terminal_latency_s:.1f}"
        )
    if unhealthy_reasons:
        return {
            "status": "unhealthy",
            "score": score,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": unhealthy_reasons,
        }

    degraded_reasons: list[str] = []
    if success_rate < DEGRADED_SUCCESS_RATE:
        degraded_reasons.append(f"success_rate_below_80_percent:{success_rate:.3f}")
    if p95_terminal_latency_s >= DEGRADED_P95_LATENCY_S:
        degraded_reasons.append(
            f"p95_latency_at_least_480s:{p95_terminal_latency_s:.1f}"
        )
    if billed_failures:
        degraded_reasons.append(f"billed_failures:{billed_failures}")
    if degraded_reasons:
        return {
            "status": "degraded",
            "score": score,
            "sample_minimum": MIN_TERMINAL_SAMPLES,
            "reasons": degraded_reasons,
        }
    return {
        "status": "healthy",
        "score": score,
        "sample_minimum": MIN_TERMINAL_SAMPLES,
        "reasons": ["success_latency_and_failure_thresholds_met"],
    }

"""Durable authority helpers for paid provider submissions.

The helpers in this module deliberately separate two facts which synchronous
SDK conveniences often blur together:

* a local call returned; and
* the provider accepted a billable job.

For queue-backed FAL endpoints we persist the provider ``request_id`` before
polling and resume that exact request after a process restart.  A lost submit
acknowledgement is not replayed: the paid-attempt reservation remains
``accepted_unknown`` until an operator reconciles provider history.

This is an adapter, not a promise of universal exactly-once execution.  APIs
without a durable request identifier or documented idempotency key must use a
fail-closed no-replay fence at their own call site.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from cost_tracker_lifecycle import cost_tracker_scope


_PAID_ATTEMPT_AUTHORITY_METHODS = (
    "reserve_paid_attempt",
    "update_paid_attempt",
    "reconcile_paid_attempt",
    "get_paid_attempt",
    "get_latest_paid_attempt",
)


def has_paid_attempt_authority(cost_tracker: Any) -> bool:
    """Return whether *cost_tracker* explicitly implements recovery authority.

    Duck-typing methods alone is unsafe here: broad mocks and older custom
    trackers manufacture arbitrary attributes, which can accidentally route a
    provider call into a durable polling path without a real ledger behind it.
    The integer capability is intentionally strict so only an implementation
    that opts into this exact contract can own paid attempts.
    """
    version = getattr(cost_tracker, "paid_attempt_authority_version", None)
    return (
        type(version) is int
        and version == 1
        and all(
            callable(getattr(cost_tracker, method_name, None))
            for method_name in _PAID_ATTEMPT_AUTHORITY_METHODS
        )
    )


def _canonical_value(value: Any) -> Any:
    """Return a deterministic, JSON-safe representation for fingerprints."""
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("paid request fingerprints require finite numbers")
        return value
    return str(value)


def request_fingerprint(*parts: Any) -> str:
    """Hash stable request inputs without exposing prompts or local paths."""
    payload = json.dumps(
        _canonical_value(parts),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_fingerprint(path: str) -> str:
    """Return the SHA-256 of a regular local input file.

    Symlinks are rejected because a mutable link target would make the durable
    request key claim reproducibility that it does not have.
    """
    stat_result = os.stat(path, follow_symlinks=False)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError(f"paid provider input must be a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    # Include the byte length to make the evidence useful when diagnosing a
    # mismatched asset without persisting the private path.
    return f"sha256:{digest.hexdigest()}:bytes:{stat_result.st_size}"


def paid_attempt_id(namespace: str, *stable_parts: Any) -> str:
    """Build a caller-owned deterministic paid-attempt id (<= 128 chars)."""
    safe_namespace = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in str(namespace or "paid")
    ).strip("-._") or "paid"
    return f"{safe_namespace[:63]}:{request_fingerprint(*stable_parts)}"


def openai_output_limit_kwargs(model: str, max_output_tokens: int) -> dict[str, int]:
    """Return the bounded-output argument supported by an OpenAI model family."""
    limit = int(max_output_tokens)
    if limit <= 0:
        raise ValueError("max_output_tokens must be positive")
    model_lower = str(model or "").lower()
    key = (
        "max_completion_tokens"
        if model_lower.startswith(("o1-", "o3-", "o4-"))
        else "max_tokens"
    )
    return {key: limit}


def _usage_count(usage: Any, *names: str) -> int:
    for name in names:
        value = usage.get(name) if isinstance(usage, Mapping) else getattr(usage, name, None)
        if value is None or isinstance(value, bool):
            continue
        try:
            count = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if count >= 0:
            return count
    return 0


def llm_response_token_counts(response: Any, provider: str) -> tuple[int, int]:
    """Extract the provider-reported input/output token counts.

    A successful response without usage evidence cannot be reconciled to an
    actual token-derived cost, so it is deliberately rejected instead of being
    silently settled at the reservation estimate or zero dollars.
    """
    provider_lower = str(provider or "").lower()
    if provider_lower in {"google", "gemini"}:
        usage = getattr(response, "usage_metadata", None)
        input_tokens = _usage_count(usage, "prompt_token_count", "input_tokens")
        output_tokens = _usage_count(
            usage, "candidates_token_count", "output_tokens"
        )
    else:
        usage = getattr(response, "usage", None)
        if provider_lower == "anthropic":
            input_tokens = _usage_count(usage, "input_tokens")
            output_tokens = _usage_count(usage, "output_tokens")
        else:
            input_tokens = _usage_count(usage, "prompt_tokens", "input_tokens")
            output_tokens = _usage_count(
                usage, "completion_tokens", "output_tokens"
            )
    cache_tokens = 0
    if provider_lower == "anthropic":
        cache_tokens = _usage_count(
            usage, "cache_creation_input_tokens"
        ) + _usage_count(usage, "cache_read_input_tokens")
    if usage is None or (
        input_tokens <= 0 and output_tokens <= 0 and cache_tokens <= 0
    ):
        raise ValueError("LLM response did not expose usable token counts")
    return input_tokens, output_tokens


def llm_token_cost_usd(response: Any, *, provider: str, model: str) -> float:
    """Calculate one successful LLM response cost from its reported tokens."""
    from cost_tracker import PRICING

    pricing = PRICING.get(str(model))
    if pricing is None:
        raise ValueError(f"no token pricing configured for LLM model {model!r}")
    input_tokens, output_tokens = llm_response_token_counts(response, provider)
    cost = (
        input_tokens / 1_000_000 * float(pricing["input"])
        + output_tokens / 1_000_000 * float(pricing["output"])
    )
    if str(provider or "").lower() == "anthropic":
        usage = getattr(response, "usage", None)
        cache_creation_tokens = _usage_count(
            usage, "cache_creation_input_tokens"
        )
        cache_read_tokens = _usage_count(usage, "cache_read_input_tokens")
        cache_write_rate = pricing.get("cache_write_5m")
        cache_read_rate = pricing.get("cache_read")
        if cache_creation_tokens and cache_write_rate is None:
            raise ValueError(
                f"no 5-minute cache-write pricing configured for {model!r}"
            )
        if cache_read_tokens and cache_read_rate is None:
            raise ValueError(f"no cache-read pricing configured for {model!r}")
        cost += (
            cache_creation_tokens
            / 1_000_000
            * float(cache_write_rate or 0.0)
            + cache_read_tokens / 1_000_000 * float(cache_read_rate or 0.0)
        )
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("token-derived LLM cost must be finite and non-negative")
    return cost


def estimate_llm_request_cost_usd(
    *,
    model: str,
    request_payload: Any,
    max_output_tokens: int,
) -> float:
    """Return a conservative pre-call reservation for a bounded LLM request.

    UTF-8 byte length is an upper bound on ordinary BPE input-token count and
    also accounts conservatively for inline base64 image payloads. The output
    side is bounded by the exact limit sent to the SDK. Unknown pricing is a
    pre-submit configuration error rather than an unbudgeted paid call.
    """
    from cost_tracker import PRICING

    pricing = PRICING.get(str(model))
    if pricing is None:
        raise ValueError(f"no token pricing configured for LLM model {model!r}")
    output_limit = int(max_output_tokens)
    if output_limit <= 0:
        raise ValueError("max_output_tokens must be positive")
    canonical = json.dumps(
        _canonical_value(request_payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    input_token_upper_bound = max(1, len(canonical))
    # Anthropic's ``ephemeral`` cache marker defaults to a five-minute write.
    # Reserving the highest configured input category keeps the pre-call bound
    # conservative whether this request is an uncached input, a cache write, or
    # a cheaper cache read.
    input_rate = max(
        float(pricing["input"]),
        float(pricing.get("cache_write_5m", pricing["input"])),
        float(pricing.get("cache_read", pricing["input"])),
    )
    estimate = (
        input_token_upper_bound / 1_000_000 * input_rate
        + output_limit / 1_000_000 * float(pricing["output"])
    )
    if not math.isfinite(estimate) or estimate < 0:
        raise ValueError("estimated LLM cost must be finite and non-negative")
    return estimate


def run_fenced_llm_call(
    *,
    call: Callable[[], Any],
    provider: str,
    model: str,
    operation: str,
    request_payload: Any,
    max_output_tokens: int,
    cost_tracker: Any,
    video_id: str = "",
    shot_id: str = "",
    attempt_scope: str = "",
) -> Any:
    """Fence one synchronous token-billed LLM SDK call when authority exists.

    Standalone helpers and legacy tests historically accept ``None`` or narrow
    fake trackers. They remain direct-call compatible. A real pipeline tracker
    opts into paid-attempt authority and therefore gets an atomic reservation,
    deterministic request identity, fail-closed ambiguous outcome, and exactly
    one token-derived reconciliation row.
    """
    if not has_paid_attempt_authority(cost_tracker):
        return call()

    provider_name = str(provider or "unknown").strip().lower()
    model_name = str(model or "unknown").strip()
    operation_name = str(operation or "llm_call").strip()
    request_fp = request_fingerprint(
        "paid-llm-v1",
        provider_name,
        model_name,
        operation_name,
        request_payload,
    )
    resolved_video_id = str(
        video_id or getattr(cost_tracker, "default_video_id", "") or ""
    )[:128]
    attempt = paid_attempt_id(
        "llm",
        resolved_video_id,
        str(shot_id or ""),
        str(attempt_scope or ""),
        provider_name,
        model_name,
        operation_name,
        request_fp,
    )
    estimate = estimate_llm_request_cost_usd(
        model=model_name,
        request_payload=request_payload,
        max_output_tokens=max_output_tokens,
    )
    return run_nonresumable_paid_call(
        call=call,
        attempt_id=attempt,
        provider=provider_name,
        engine=model_name,
        operation=operation_name,
        estimated_cost_usd=estimate,
        request_fingerprint_value=request_fp,
        cost_tracker=cost_tracker,
        shot_id=shot_id,
        video_id=resolved_video_id,
        actual_cost_usd=lambda response: llm_token_cost_usd(
            response,
            provider=provider_name,
            model=model_name,
        ),
    )


class _ObservationOnlyLLMTracker:
    """Delegate provider evidence while suppressing duplicate token invoices."""

    def __init__(self, tracker: Any):
        self._tracker = tracker

    def log_llm(self, **_kwargs: Any) -> None:
        return None

    def record_provider_observation(self, **kwargs: Any) -> Any:
        provider = str(kwargs.get("provider") or "").strip().lower()
        operation = str(kwargs.get("operation") or "").strip()
        if provider == "openai" and operation.startswith("web_research_"):
            # The fenced OpenAI paid attempt is the authoritative outcome and
            # latency sample. Preserve Tavily/Firecrawl observations delegated
            # through this same tracker view, but suppress this duplicate LLM
            # observation from run_with_tools.
            return None
        return self._tracker.record_provider_observation(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tracker, name)


class _FencedOpenAICompletions:
    def __init__(
        self,
        create: Callable[..., Any],
        *,
        tracker: Any,
        operation_prefix: str,
        video_id: str,
        max_output_tokens: int,
    ) -> None:
        self._create = create
        self._tracker = tracker
        self._operation_prefix = str(operation_prefix or "openai_tools")[:96]
        self._video_id = str(video_id or "")[:128]
        self._max_output_tokens = int(max_output_tokens)
        self._deferred: Optional[PaidCallDeferred] = None

    def create(self, **kwargs: Any) -> Any:
        # Tool-loop helpers commonly catch an SDK exception and proceed to a
        # final response request. Once the first boundary is ambiguous, replay
        # the local fence instead so a second paid request never reaches OpenAI.
        if self._deferred is not None:
            raise self._deferred
        bounded_kwargs = dict(kwargs)
        model = str(bounded_kwargs.get("model") or "gpt-4o")
        limit_key = next(
            (
                key
                for key in ("max_completion_tokens", "max_tokens")
                if key in bounded_kwargs
            ),
            "",
        )
        if limit_key:
            output_limit = int(bounded_kwargs[limit_key])
        else:
            output_limit = self._max_output_tokens
            bounded_kwargs.update(openai_output_limit_kwargs(model, output_limit))
        operation = (
            f"{self._operation_prefix}_tool_round"
            if bounded_kwargs.get("tools")
            else f"{self._operation_prefix}_final"
        )
        try:
            return run_fenced_llm_call(
                call=lambda: self._create(**bounded_kwargs),
                provider="openai",
                model=model,
                operation=operation,
                request_payload=bounded_kwargs,
                max_output_tokens=output_limit,
                cost_tracker=self._tracker,
                video_id=self._video_id,
            )
        except PaidCallDeferred as exc:
            self._deferred = exc
            raise


class _FencedOpenAIChat:
    def __init__(self, chat: Any, completions: _FencedOpenAICompletions) -> None:
        self._chat = chat
        self.completions = completions

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class _FencedOpenAIClient:
    def __init__(self, client: Any, completions: _FencedOpenAICompletions) -> None:
        self._client = client
        self.chat = _FencedOpenAIChat(client.chat, completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def fence_openai_tools_client(
    client: Any,
    *,
    cost_tracker: Any,
    operation_prefix: str,
    video_id: str = "",
    max_output_tokens: int = 4096,
) -> tuple[Any, Any]:
    """Return a paid-fenced OpenAI client and observation-only tracker view.

    ``web_research.run_with_tools`` owns a multi-call SDK loop and performs its
    own legacy ``log_llm`` writes. The client proxy fences each actual request;
    the tracker view preserves research observations while preventing those
    legacy writes from double-counting the reconciled paid attempts.
    """
    if not has_paid_attempt_authority(cost_tracker):
        return client, cost_tracker
    resolved_video_id = str(
        video_id or getattr(cost_tracker, "default_video_id", "") or ""
    )[:128]
    completions = _FencedOpenAICompletions(
        client.chat.completions.create,
        tracker=cost_tracker,
        operation_prefix=operation_prefix,
        video_id=resolved_video_id,
        max_output_tokens=max_output_tokens,
    )
    return (
        _FencedOpenAIClient(client, completions),
        _ObservationOnlyLLMTracker(cost_tracker),
    )


@dataclass(frozen=True)
class PaidCallSnapshot:
    """Safe exception payload for a call that cannot be replayed automatically."""

    attempt: dict
    reason: str


class PaidCallDeferred(RuntimeError):
    """A paid call may have been accepted and must not be replayed."""

    def __init__(self, message: str, *, attempt: Optional[dict] = None):
        super().__init__(message)
        self.snapshot = PaidCallSnapshot(dict(attempt or {}), message)


class PaidCallBudgetBlocked(PaidCallDeferred):
    """The atomic project budget reservation refused this provider call."""


class PaidCallUnbilled(RuntimeError):
    """Provider evidence proves the attempt was terminal and unbilled."""

    def __init__(self, message: str, *, attempt: Optional[dict] = None):
        super().__init__(message)
        self.attempt = dict(attempt or {})


def run_nonresumable_paid_call(
    *,
    call: Callable[[], Any],
    attempt_id: str,
    provider: str,
    engine: str,
    operation: str,
    estimated_cost_usd: float,
    request_fingerprint_value: str,
    cost_tracker: Any,
    shot_id: str = "",
    video_id: str = "",
    on_completed: Optional[Callable[[Any], None]] = None,
    actual_cost_usd: Optional[float | Callable[[Any], float]] = None,
) -> Any:
    """Fence a paid API that exposes neither durable IDs nor idempotency.

    There is intentionally no restart submission path.  A crash/network loss
    after entering ``call`` may have charged, so the durable state becomes
    ``accepted_unknown`` and every later automatic invocation is blocked.
    """
    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError("paid call requires explicit paid-attempt authority")
    with cost_tracker_scope(cost_tracker) as tracker:
        attempt = tracker.reserve_paid_attempt(
            attempt_id=attempt_id,
            provider=provider,
            engine=engine,
            operation=operation,
            estimated_cost_usd=estimated_cost_usd,
            shot_id=shot_id,
            video_id=video_id,
            request_fingerprint=request_fingerprint_value,
        )
        if not attempt.get("acquired"):
            if str(attempt.get("request_fingerprint") or "") != request_fingerprint_value:
                raise PaidCallDeferred(
                    "non-resumable paid-attempt key was reused with different parameters",
                    attempt=attempt,
                )
            state = str(attempt.get("state") or "")
            if state == "blocked_budget":
                raise PaidCallBudgetBlocked(
                    "atomic budget reservation refused paid call", attempt=attempt
                )
            if state in {"failed_unbilled", "cancelled"}:
                raise PaidCallUnbilled(
                    "paid call is terminal and unbilled", attempt=attempt
                )
            raise PaidCallDeferred(
                "provider has no durable recovery identifier; automatic replay blocked",
                attempt=attempt,
            )
        try:
            result = call()
        except Exception as exc:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail=(
                    "Provider call raised after entering a non-idempotent paid "
                    f"boundary ({type(exc).__name__}); billing outcome unknown"
                ),
            )
            raise PaidCallDeferred(
                "non-resumable provider outcome is unknown", attempt=attempt
            ) from exc
        if result is None or result is False:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail=(
                    "Provider returned no durable result identifier; billing outcome "
                    "cannot be proved safe for automatic fallback"
                ),
            )
            raise PaidCallDeferred(
                "non-resumable provider returned no result", attempt=attempt
            )
        if on_completed is not None:
            try:
                on_completed(result)
            except Exception as exc:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "Provider completed, but durable output retention failed "
                        f"({type(exc).__name__}); automatic replay blocked"
                    ),
                )
                raise PaidCallDeferred(
                    "provider completed but durable output retention failed",
                    attempt=attempt,
                ) from exc
        try:
            reconciled_cost = estimated_cost_usd
            if callable(actual_cost_usd):
                reconciled_cost = actual_cost_usd(result)
            elif actual_cost_usd is not None:
                reconciled_cost = actual_cost_usd
        except Exception as exc:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail="Provider completed but actual-cost calculation failed",
            )
            raise PaidCallDeferred(
                "provider completed but actual-cost calculation failed",
                attempt=attempt,
            ) from exc
        try:
            tracker.reconcile_paid_attempt(
                attempt_id,
                state="succeeded",
                actual_cost_usd=reconciled_cost,
                provider_status="completed",
                detail="Non-resumable provider returned a completed result",
            )
        except Exception as exc:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail="Provider completed but cost reconciliation failed",
            )
            raise PaidCallDeferred(
                "provider completed but cost reconciliation failed", attempt=attempt
            ) from exc
        return result


def _mark_unknown(tracker: Any, attempt: dict, *, detail: str, job_id: str = "") -> dict:
    """Best-effort transition to the fail-closed ambiguous state."""
    try:
        current = tracker.get_paid_attempt(attempt["attempt_id"]) or attempt
    except Exception:
        current = attempt
    if current.get("state") in {"succeeded", "failed_billed"}:
        return dict(current)
    try:
        return tracker.update_paid_attempt(
            current["attempt_id"],
            state="accepted_unknown",
            provider_job_id=job_id or None,
            provider_status="outcome_unknown",
            detail=detail,
        )
    except Exception:
        # The original durable row remains active (normally ``submitting`` or
        # ``running``), which is itself a no-replay fence.  Never mask the
        # provider ambiguity with a second ledger error.
        return dict(current)


def _status_fields(status: Any) -> tuple[str, str, str]:
    """Normalize FAL SDK dataclasses and narrow test doubles."""
    if isinstance(status, Mapping):
        name = str(status.get("status") or status.get("state") or "").upper()
        error = str(status.get("error") or "")
        error_type = str(status.get("error_type") or status.get("errorType") or "")
        return name, error, error_type
    name = type(status).__name__.upper()
    return (
        name,
        str(getattr(status, "error", "") or ""),
        str(getattr(status, "error_type", "") or ""),
    )


def _explicit_billing_evidence(status: Any) -> Optional[bool]:
    """Return provider-reported billing truth, never a status-name guess.

    A terminal provider failure is not enough to infer whether FAL charged it.
    Some queue/test adapters expose an explicit ``billed``/``is_billed`` flag;
    only that narrow evidence is strong enough to release the reservation as
    billed or unbilled.  Missing/ambiguous evidence stays ``accepted_unknown``.
    """
    if isinstance(status, Mapping):
        values = (status.get("billed"), status.get("is_billed"))
    else:
        values = (
            getattr(status, "billed", None),
            getattr(status, "is_billed", None),
        )
    for value in values:
        if type(value) is bool:
            return value
        if type(value) is int and value in {0, 1}:
            return bool(value)
    return None


def run_durable_fal_job(
    *,
    client: Any = None,
    application: str,
    arguments: Mapping[str, Any],
    attempt_id: str,
    engine: str,
    operation: str,
    estimated_cost_usd: float,
    request_fingerprint_value: str,
    cost_tracker: Any = None,
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: float = 600.0,
    poll_interval_s: float = 0.25,
    with_logs: bool = False,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Submit or resume one FAL queue request without blind POST replay.

    ``application`` and the durable ``request_id`` are sufficient for the FAL
    queue's idempotent ``status``/``result`` APIs.  Every invocation reserves
    budget transactionally before the first POST.  Existing active attempts
    are resumed only when a provider request ID was durably acknowledged.
    """
    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError("durable FAL job requires explicit paid-attempt authority")
    # Production callers use the canonical SDK module directly. ``client`` is
    # retained only as a narrow injection seam for deterministic unit tests;
    # passing the module around from production call sites would create an alias
    # that can evade the repository's direct-call FAL guards.
    if client is None:
        import fal_client
    timeout = float(poll_timeout_s)
    interval = float(poll_interval_s)
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("poll_timeout_s must be finite and non-negative")
    if not math.isfinite(interval) or interval < 0:
        raise ValueError("poll_interval_s must be finite and non-negative")

    with cost_tracker_scope(cost_tracker) as tracker:
        attempt = tracker.reserve_paid_attempt(
            attempt_id=attempt_id,
            provider="fal",
            engine=engine,
            operation=operation,
            estimated_cost_usd=estimated_cost_usd,
            shot_id=shot_id,
            video_id=video_id,
            request_fingerprint=request_fingerprint_value,
        )
        state = str(attempt.get("state") or "")
        job_id = str(attempt.get("provider_job_id") or "")

        if not attempt.get("acquired"):
            stored_fingerprint = str(attempt.get("request_fingerprint") or "")
            if stored_fingerprint != request_fingerprint_value:
                raise PaidCallDeferred(
                    "logical paid-attempt key was reused with different submitted parameters; automatic replay blocked",
                    attempt=attempt,
                )
            if state == "blocked_budget":
                raise PaidCallBudgetBlocked(
                    f"budget refused paid FAL attempt {attempt_id}", attempt=attempt
                )
            if state in {"failed_unbilled", "cancelled"}:
                raise PaidCallUnbilled(
                    f"paid FAL attempt {attempt_id} is terminal and unbilled",
                    attempt=attempt,
                )
            if state == "failed_billed":
                raise PaidCallDeferred(
                    f"paid FAL attempt {attempt_id} failed after billing; no fallback allowed",
                    attempt=attempt,
                )
            if not job_id:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "Provider submission may have been accepted, but no FAL "
                        "request ID was durably acknowledged; automatic replay blocked"
                    ),
                )
                raise PaidCallDeferred(
                    "FAL submission acknowledgement is unknown; automatic replay blocked",
                    attempt=attempt,
                )
        else:
            try:
                handle = (
                    client.submit(application, dict(arguments))
                    if client is not None
                    else fal_client.submit(application, dict(arguments))
                )
                job_id = str(getattr(handle, "request_id", "") or "")
                if not job_id:
                    raise RuntimeError("FAL submit response did not contain request_id")
                attempt = tracker.update_paid_attempt(
                    attempt_id,
                    state="running",
                    provider_job_id=job_id,
                    provider_status="queued",
                    detail="FAL request acknowledged; polling durable request ID",
                )
            except Exception as exc:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "FAL submit acknowledgement was lost or invalid; provider "
                        f"history must be reconciled before retry ({type(exc).__name__})"
                    ),
                    job_id=job_id,
                )
                raise PaidCallDeferred(
                    "FAL submit outcome is ambiguous; automatic replay blocked",
                    attempt=attempt,
                ) from exc

        # A previously succeeded request can be fetched again without another
        # generation or another cost reconciliation.  This repairs a lost local
        # artifact while preserving one provider charge.
        already_succeeded = state == "succeeded"
        if already_succeeded:
            try:
                result = (
                    client.result(application, job_id)
                    if client is not None
                    else fal_client.result(application, job_id)
                )
            except Exception as exc:
                raise PaidCallDeferred(
                    "FAL succeeded request could not be retrieved; no new job started",
                    attempt=attempt,
                ) from exc
            if not isinstance(result, dict):
                raise PaidCallDeferred(
                    "FAL succeeded request returned a malformed result; no new job started",
                    attempt=attempt,
                )
            return result

        deadline = monotonic() + timeout
        while True:
            try:
                status = (
                    client.status(application, job_id, with_logs=with_logs)
                    if client is not None
                    else fal_client.status(application, job_id, with_logs=with_logs)
                )
            except Exception as exc:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "FAL status retrieval failed for an acknowledged request; "
                        f"resume by request ID instead of submitting again ({type(exc).__name__})"
                    ),
                    job_id=job_id,
                )
                raise PaidCallDeferred(
                    "FAL request status is temporarily unknown; automatic replay blocked",
                    attempt=attempt,
                ) from exc

            status_name, provider_error, provider_error_type = _status_fields(status)
            if status_name in {"COMPLETED", "SUCCESS", "SUCCEEDED"}:
                if provider_error:
                    billed = _explicit_billing_evidence(status)
                    if billed is None:
                        attempt = _mark_unknown(
                            tracker,
                            attempt,
                            detail=(
                                "FAL completed with an error but billing evidence is not "
                                "available; operator reconciliation required"
                            ),
                            job_id=job_id,
                        )
                        raise PaidCallDeferred(
                            f"FAL request failed with uncertain billing ({provider_error_type or provider_error})",
                            attempt=attempt,
                        )
                    terminal_state = "failed_billed" if billed else "failed_unbilled"
                    try:
                        attempt = tracker.reconcile_paid_attempt(
                            attempt_id,
                            state=terminal_state,
                            actual_cost_usd=(estimated_cost_usd if billed else None),
                            provider_job_id=job_id,
                            provider_status=status_name.lower(),
                            failure_code=provider_error_type or "provider_error",
                            detail="FAL returned explicit terminal billing evidence",
                        )
                    except Exception as exc:
                        attempt = _mark_unknown(
                            tracker,
                            attempt,
                            detail=(
                                "FAL returned explicit terminal billing evidence but "
                                "ledger reconciliation failed"
                            ),
                            job_id=job_id,
                        )
                        raise PaidCallDeferred(
                            "FAL terminal failure could not be reconciled",
                            attempt=attempt,
                        ) from exc
                    if billed:
                        raise PaidCallDeferred(
                            "FAL request failed after explicit billing; automatic fallback blocked",
                            attempt=attempt,
                        )
                    raise PaidCallUnbilled(
                        "FAL request failed with explicit unbilled evidence",
                        attempt=attempt,
                    )
                try:
                    result = (
                        client.result(application, job_id)
                        if client is not None
                        else fal_client.result(application, job_id)
                    )
                except Exception as exc:
                    attempt = _mark_unknown(
                        tracker,
                        attempt,
                        detail=(
                            "FAL completion was observed but result retrieval failed; "
                            "resume the acknowledged request instead of replaying"
                        ),
                        job_id=job_id,
                    )
                    raise PaidCallDeferred(
                        "FAL result retrieval is ambiguous; automatic replay blocked",
                        attempt=attempt,
                    ) from exc
                if not isinstance(result, dict):
                    attempt = _mark_unknown(
                        tracker,
                        attempt,
                        detail="FAL result was malformed after completion; operator review required",
                        job_id=job_id,
                    )
                    raise PaidCallDeferred(
                        "FAL result was malformed; automatic replay blocked", attempt=attempt
                    )
                try:
                    tracker.reconcile_paid_attempt(
                        attempt_id,
                        state="succeeded",
                        actual_cost_usd=estimated_cost_usd,
                        provider_job_id=job_id,
                        provider_status="completed",
                        detail="FAL provider request completed",
                    )
                except Exception as exc:
                    attempt = _mark_unknown(
                        tracker,
                        attempt,
                        detail=(
                            "FAL completed and may be billed, but ledger reconciliation "
                            "failed; automatic replay blocked"
                        ),
                        job_id=job_id,
                    )
                    raise PaidCallDeferred(
                        "FAL completed but cost reconciliation failed", attempt=attempt
                    ) from exc
                return result

            if status_name in {
                "FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"
            }:
                billed = _explicit_billing_evidence(status)
                if billed is None:
                    attempt = _mark_unknown(
                        tracker,
                        attempt,
                        detail=(
                            "FAL reported a terminal request state without explicit "
                            "billing evidence; operator reconciliation required"
                        ),
                        job_id=job_id,
                    )
                    raise PaidCallDeferred(
                        "FAL terminal request has uncertain billing; automatic fallback blocked",
                        attempt=attempt,
                    )
                cancelled = status_name in {"CANCELLED", "CANCELED"} and not billed
                terminal_state = (
                    "failed_billed" if billed else "cancelled" if cancelled else "failed_unbilled"
                )
                try:
                    attempt = tracker.reconcile_paid_attempt(
                        attempt_id,
                        state=terminal_state,
                        actual_cost_usd=(estimated_cost_usd if billed else None),
                        provider_job_id=job_id,
                        provider_status=status_name.lower(),
                        failure_code=provider_error_type or status_name.lower(),
                        detail="FAL returned explicit terminal billing evidence",
                    )
                except Exception as exc:
                    attempt = _mark_unknown(
                        tracker,
                        attempt,
                        detail=(
                            "FAL returned explicit terminal billing evidence but "
                            "ledger reconciliation failed"
                        ),
                        job_id=job_id,
                    )
                    raise PaidCallDeferred(
                        "FAL terminal state could not be reconciled",
                        attempt=attempt,
                    ) from exc
                if billed:
                    raise PaidCallDeferred(
                        "FAL request reached a billed terminal failure; automatic fallback blocked",
                        attempt=attempt,
                    )
                raise PaidCallUnbilled(
                    "FAL request reached an explicitly unbilled terminal state",
                    attempt=attempt,
                )

            if monotonic() >= deadline:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "FAL request remains queued/running beyond the local poll "
                        "deadline; resume by request ID instead of submitting again"
                    ),
                    job_id=job_id,
                )
                raise PaidCallDeferred(
                    "FAL request is still running; automatic fallback blocked",
                    attempt=attempt,
                )
            sleep(min(interval, max(0.0, deadline - monotonic())))


def run_durable_comfy_job(
    *,
    client: Any,
    workflow: Mapping[str, Any],
    attempt_id: str,
    engine: str,
    provider: str = "comfyui",
    operation: str,
    estimated_cost_usd: float,
    request_fingerprint_value: str,
    cost_tracker: Any,
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: float = 300.0,
    poll_interval_s: float = 2.0,
) -> dict:
    """Submit or resume one ComfyUI prompt ID under paid-attempt authority."""
    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError("durable ComfyUI job requires explicit paid-attempt authority")
    workflow_payload = dict(workflow)
    queue_preflighted = getattr(client, "queue_prompt_preflighted", None)
    with cost_tracker_scope(cost_tracker) as tracker:
        attempt = tracker.reserve_paid_attempt(
            attempt_id=attempt_id,
            provider=provider,
            engine=engine,
            operation=operation,
            estimated_cost_usd=estimated_cost_usd,
            shot_id=shot_id,
            video_id=video_id,
            request_fingerprint=request_fingerprint_value,
        )
        state = str(attempt.get("state") or "")
        prompt_id = str(attempt.get("provider_job_id") or "")
        if not attempt.get("acquired"):
            if str(attempt.get("request_fingerprint") or "") != request_fingerprint_value:
                raise PaidCallDeferred(
                    "ComfyUI paid-attempt key was reused with different workflow inputs",
                    attempt=attempt,
                )
            if state == "blocked_budget":
                raise PaidCallBudgetBlocked(
                    "atomic budget reservation refused ComfyUI prompt", attempt=attempt
                )
            if state in {"failed_unbilled", "cancelled"}:
                raise PaidCallUnbilled(
                    "ComfyUI prompt is terminal and unbilled", attempt=attempt
                )
            if state == "failed_billed":
                raise PaidCallDeferred(
                    "ComfyUI prompt failed after billing; no automatic replacement allowed",
                    attempt=attempt,
                )
            if not prompt_id:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "ComfyUI submission may have been accepted without a durable "
                        "prompt ID; automatic replay blocked"
                    ),
                )
                raise PaidCallDeferred(
                    "ComfyUI submission acknowledgement is unknown", attempt=attempt
                )
        else:
            if callable(queue_preflighted):
                # Only a genuinely new attempt needs graph readiness. Existing
                # prompt IDs skip this branch and remain retrieval-only even
                # during a worker outage. This split also proves every error
                # here occurred before POST /prompt.
                try:
                    client.preflight(workflow_payload)
                except Exception as exc:
                    attempt = tracker.reconcile_paid_attempt(
                        attempt_id,
                        state="failed_unbilled",
                        provider_status="preflight_failed",
                        detail="ComfyUI GET-only preflight failed before queue acceptance",
                    )
                    raise PaidCallUnbilled(
                        "ComfyUI preflight failed before queue acceptance",
                        attempt=attempt,
                    ) from exc
            try:
                submit = queue_preflighted if callable(queue_preflighted) else client.queue_prompt
                prompt_id = str(submit(workflow_payload) or "")
            except Exception as exc:
                if type(exc).__name__ == "ComfyUIPromptRejected":
                    attempt = tracker.reconcile_paid_attempt(
                        attempt_id,
                        state="failed_unbilled",
                        provider_status="rejected",
                        detail="ComfyUI rejected workflow before queue acceptance",
                    )
                    raise PaidCallUnbilled(
                        "ComfyUI rejected workflow before execution", attempt=attempt
                    ) from exc
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail=(
                        "ComfyUI prompt acknowledgement was lost; provider queue/history "
                        "must be reconciled before retry"
                    ),
                )
                raise PaidCallDeferred(
                    "ComfyUI submit outcome is ambiguous", attempt=attempt
                ) from exc
            if not prompt_id:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail="ComfyUI queue response omitted prompt ID",
                )
                raise PaidCallDeferred(
                    "ComfyUI queue response omitted prompt ID", attempt=attempt
                )
            try:
                attempt = tracker.update_paid_attempt(
                    attempt_id,
                    state="running",
                    provider_job_id=prompt_id,
                    provider_status="queued",
                    detail="ComfyUI prompt acknowledged; polling durable prompt ID",
                )
            except Exception as exc:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail="ComfyUI prompt was acknowledged but ledger update failed",
                    job_id=prompt_id,
                )
                raise PaidCallDeferred(
                    "ComfyUI prompt ID could not be durably recorded", attempt=attempt
                ) from exc

        try:
            history = client.wait_for_completion(
                prompt_id,
                timeout=float(poll_timeout_s),
                poll_interval=float(poll_interval_s),
            )
        except Exception as exc:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail=(
                    "ComfyUI prompt terminal/billing outcome is unknown; resume the "
                    f"durable prompt ID ({type(exc).__name__})"
                ),
                job_id=prompt_id,
            )
            raise PaidCallDeferred(
                "ComfyUI prompt requires recovery", attempt=attempt
            ) from exc
        record = history.get(prompt_id) if isinstance(history, Mapping) else None
        outputs = record.get("outputs") if isinstance(record, Mapping) else None
        if not isinstance(outputs, Mapping) or not outputs:
            attempt = _mark_unknown(
                tracker,
                attempt,
                detail="ComfyUI completion history contained no provider output",
                job_id=prompt_id,
            )
            raise PaidCallDeferred(
                "ComfyUI completion has no output; automatic replacement blocked",
                attempt=attempt,
            )
        if state != "succeeded":
            try:
                tracker.reconcile_paid_attempt(
                    attempt_id,
                    state="succeeded",
                    actual_cost_usd=estimated_cost_usd,
                    provider_job_id=prompt_id,
                    provider_status="completed",
                    detail="ComfyUI provider prompt completed",
                )
            except Exception as exc:
                attempt = _mark_unknown(
                    tracker,
                    attempt,
                    detail="ComfyUI completed but cost reconciliation failed",
                    job_id=prompt_id,
                )
                raise PaidCallDeferred(
                    "ComfyUI completed but cost reconciliation failed", attempt=attempt
                ) from exc
        return dict(history)

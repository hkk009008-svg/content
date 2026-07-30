"""Typed video-engine policy for authoring and ordered routing views.

This module consumes :mod:`domain.provider_catalog` without dispatching,
importing provider adapters, or retaining credentials.  Authoring decisions
and future dispatch candidates deliberately use different gates:

* stored shot targets must be ``AUTO`` or a selectable, dispatchable, runtime
  available video engine;
* ordered routing candidates may include non-selectable internal fallbacks,
  but must still be dispatchable, spendable, runtime available, and not
  explicitly disabled by the project.

The distinction keeps historical routing seeds inspectable while preventing
them from being mistaken for current executable truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Iterable, Mapping

from domain.provider_catalog import (
    CATALOG,
    Lifecycle,
    Modality,
    ProductSupport,
    RuntimeSnapshot,
    effective_policy,
    runtime_availability,
)


class VideoPolicyReason(StrEnum):
    """Stable rejection/coercion reasons exposed to authoring consumers."""

    UNKNOWN = "unknown"
    NON_VIDEO = "non_video"
    NOT_SELECTABLE = "not_selectable"
    NOT_DISPATCHABLE = "not_dispatchable"
    RETIRED = "retired"
    UNSUPPORTED = "unsupported"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    PROJECT_DISABLED = "project_disabled"
    AUTO_SENTINEL = "auto_sentinel"


@dataclass(frozen=True)
class VideoTargetDecision:
    """Result of evaluating one proposed persisted shot target."""

    requested: str
    target: str
    accepted: bool
    reason: VideoPolicyReason | None = None


@dataclass(frozen=True)
class VideoEngineRejection:
    """One rejected member of an ordered engine seed."""

    key: str
    reason: VideoPolicyReason


@dataclass(frozen=True)
class VideoCandidateResult:
    """Accepted ordered candidates plus structured rejection evidence."""

    candidates: tuple[str, ...]
    rejections: tuple[VideoEngineRejection, ...]

    @property
    def primary(self) -> str:
        return self.candidates[0] if self.candidates else "AUTO"

    @property
    def fallbacks(self) -> tuple[str, ...]:
        return self.candidates[1:]


_UNSUPPORTED_PRODUCT_STATES = frozenset(
    {
        ProductSupport.NOT_IMPLEMENTED,
        ProductSupport.DISCONNECTED,
        ProductSupport.KNOWN_BROKEN,
        ProductSupport.UNSUPPORTED,
    }
)


def build_runtime_snapshot(
    settings_obj: object | None = None,
    module_probe: Callable[[str], bool] | None = None,
    *,
    services: Iterable[str] = (),
) -> RuntimeSnapshot:
    """Build a symbolic runtime snapshot without retaining secret values.

    The settings object is injectable for deterministic tests.  When omitted,
    the process-wide validated settings object is inspected.  Only catalog
    requirement *names* are returned; credential values and imported module
    objects are never retained.
    """

    if settings_obj is None:
        from config.settings import settings as environment_settings

        settings_obj = environment_settings
    return RuntimeSnapshot.from_settings(
        settings_obj,
        module_probe=module_probe,
        services=frozenset(services),
    )


def _snapshot_or_default(snapshot: RuntimeSnapshot | None) -> RuntimeSnapshot:
    return snapshot if snapshot is not None else build_runtime_snapshot()


def _catalog_reason(key: str, *, on_date: date | None) -> VideoPolicyReason | None:
    entry = CATALOG.get(key)
    if entry is None:
        return VideoPolicyReason.UNKNOWN
    if entry.modality is not Modality.VIDEO:
        return VideoPolicyReason.NON_VIDEO

    policy = effective_policy(key, on_date=on_date)
    if policy.lifecycle is Lifecycle.RETIRED:
        return VideoPolicyReason.RETIRED
    if entry.product_support in _UNSUPPORTED_PRODUCT_STATES:
        return VideoPolicyReason.UNSUPPORTED
    return None


def evaluate_shot_target(
    requested: object,
    *,
    snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
) -> VideoTargetDecision:
    """Resolve a proposed new shot target, coercing failures to ``AUTO``.

    Existing persisted projects are intentionally outside this boundary; this
    helper is for newly authored LLM/optimizer values and resolved views.
    """

    key = requested if isinstance(requested, str) else ""
    if key == "AUTO":
        return VideoTargetDecision(
            requested=key,
            target="AUTO",
            accepted=True,
        )

    reason = _catalog_reason(key, on_date=on_date)
    if reason is None:
        policy = effective_policy(key, on_date=on_date)
        if not policy.selectable:
            reason = VideoPolicyReason.NOT_SELECTABLE
        elif not policy.dispatchable:
            reason = VideoPolicyReason.NOT_DISPATCHABLE
        elif not runtime_availability(
            key,
            _snapshot_or_default(snapshot),
            on_date=on_date,
        ).available:
            reason = VideoPolicyReason.RUNTIME_UNAVAILABLE

    if reason is not None:
        return VideoTargetDecision(
            requested=key,
            target="AUTO",
            accepted=False,
            reason=reason,
        )
    return VideoTargetDecision(
        requested=key,
        target=key,
        accepted=True,
    )


def eligible_shot_targets(
    *,
    snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
) -> tuple[str, ...]:
    """Return ``AUTO`` plus currently eligible concrete authoring targets."""

    current = _snapshot_or_default(snapshot)
    return tuple(
        key
        for key in CATALOG
        if evaluate_shot_target(
            key,
            snapshot=current,
            on_date=on_date,
        ).accepted
    )


def _is_project_disabled(
    key: str,
    api_engines: Mapping[str, object] | None,
) -> bool:
    if not isinstance(api_engines, Mapping):
        return False
    config = api_engines.get(key)
    return (
        isinstance(config, Mapping)
        and config.get("enabled", True) is False
    )


def _iter_unique_engine_keys(
    candidates: Iterable[object],
) -> Iterable[str]:
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate if isinstance(candidate, str) else ""
        if key in seen:
            continue
        seen.add(key)
        yield key


def filter_dispatch_candidates(
    candidates: Iterable[object],
    *,
    snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
    api_engines: Mapping[str, object] | None = None,
) -> VideoCandidateResult:
    """Filter a future ordered dispatch chain without performing dispatch.

    Non-selectable fallbacks such as ``KLING_NATIVE`` and pre-sunset
    ``SORA_NATIVE`` may survive here.  ``AUTO`` never does: it is a storage and
    router sentinel, not an executable engine.
    """

    current = _snapshot_or_default(snapshot)
    accepted: list[str] = []
    rejected: list[VideoEngineRejection] = []

    for key in _iter_unique_engine_keys(candidates):
        if key == "AUTO":
            rejected.append(
                VideoEngineRejection(key, VideoPolicyReason.AUTO_SENTINEL)
            )
            continue

        reason = _catalog_reason(key, on_date=on_date)
        if reason is None:
            policy = effective_policy(key, on_date=on_date)
            if not policy.dispatchable or not policy.spendable:
                reason = VideoPolicyReason.NOT_DISPATCHABLE
            elif _is_project_disabled(key, api_engines):
                reason = VideoPolicyReason.PROJECT_DISABLED
            elif not runtime_availability(
                key,
                current,
                on_date=on_date,
            ).available:
                reason = VideoPolicyReason.RUNTIME_UNAVAILABLE

        if reason is None:
            accepted.append(key)
        else:
            rejected.append(VideoEngineRejection(key, reason))

    return VideoCandidateResult(
        candidates=tuple(accepted),
        rejections=tuple(rejected),
    )


def resolve_video_ranking(
    candidates: Iterable[object],
    *,
    snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
) -> VideoCandidateResult:
    """Resolve an authoring ranking to concrete selectable video engines."""

    current = _snapshot_or_default(snapshot)
    accepted: list[str] = []
    rejected: list[VideoEngineRejection] = []

    for key in _iter_unique_engine_keys(candidates):
        if key == "AUTO":
            rejected.append(
                VideoEngineRejection(key, VideoPolicyReason.AUTO_SENTINEL)
            )
            continue
        decision = evaluate_shot_target(
            key,
            snapshot=current,
            on_date=on_date,
        )
        if decision.accepted:
            accepted.append(key)
        else:
            rejected.append(
                VideoEngineRejection(
                    key,
                    decision.reason or VideoPolicyReason.UNKNOWN,
                )
            )

    return VideoCandidateResult(
        candidates=tuple(accepted),
        rejections=tuple(rejected),
    )


def resolve_workflow_candidates(
    primary: object,
    fallbacks: Iterable[object],
    *,
    snapshot: RuntimeSnapshot | None = None,
    on_date: date | None = None,
    api_engines: Mapping[str, object] | None = None,
) -> VideoCandidateResult:
    """Resolve historical workflow order into a safe future routing view."""

    return filter_dispatch_candidates(
        (primary, *fallbacks),
        snapshot=snapshot,
        on_date=on_date,
        api_engines=api_engines,
    )


__all__ = [
    "VideoCandidateResult",
    "VideoEngineRejection",
    "VideoPolicyReason",
    "VideoTargetDecision",
    "build_runtime_snapshot",
    "eligible_shot_targets",
    "evaluate_shot_target",
    "filter_dispatch_candidates",
    "resolve_video_ranking",
    "resolve_workflow_candidates",
]

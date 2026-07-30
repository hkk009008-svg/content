from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from types import SimpleNamespace

import pytest

from domain.provider_catalog import RuntimeSnapshot
from domain.video_engine_policy import (
    VideoPolicyReason,
    build_runtime_snapshot,
    eligible_shot_targets,
    evaluate_shot_target,
    filter_dispatch_candidates,
    resolve_video_ranking,
    resolve_workflow_candidates,
)


PRE_SUNSET = date(2026, 9, 23)
SUNSET = date(2026, 9, 24)


def _fal_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


def _sora_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"openai_api_key"},
        modules={"openai"},
    )


def _veo_api_key_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"google_api_key"},
        modules={"google.genai"},
    )


def test_auto_is_valid_for_storage_but_never_a_dispatch_candidate() -> None:
    decision = evaluate_shot_target(
        "AUTO",
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    assert decision.accepted is True
    assert decision.target == "AUTO"
    assert decision.reason is None

    candidates = filter_dispatch_candidates(
        ["AUTO"],
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    assert candidates.candidates == ()
    assert candidates.primary == "AUTO"
    assert candidates.rejections == (
        candidates.rejections[0],
    )
    assert candidates.rejections[0].key == "AUTO"
    assert candidates.rejections[0].reason is VideoPolicyReason.AUTO_SENTINEL


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("DOES_NOT_EXIST", VideoPolicyReason.UNKNOWN),
        ("RUNWAY_ACT_ONE", VideoPolicyReason.NON_VIDEO),
        ("KLING_LIPSYNC_2", VideoPolicyReason.NON_VIDEO),
        ("GEMINI_OMNI", VideoPolicyReason.UNSUPPORTED),
        ("SORA_2", VideoPolicyReason.RETIRED),
        ("LTX", VideoPolicyReason.NOT_SELECTABLE),
    ],
)
def test_authoring_rejections_use_exact_reason_and_coerce_to_auto(
    key: str,
    reason: VideoPolicyReason,
) -> None:
    decision = evaluate_shot_target(
        key,
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert decision.accepted is False
    assert decision.target == "AUTO"
    assert decision.reason is reason


def test_selectable_engine_requires_credential_and_module() -> None:
    for snapshot in (
        RuntimeSnapshot(),
        RuntimeSnapshot(credentials={"fal_key"}),
        RuntimeSnapshot(modules={"fal_client"}),
    ):
        decision = evaluate_shot_target(
            "KLING_3_0",
            snapshot=snapshot,
            on_date=PRE_SUNSET,
        )
        assert decision.reason is VideoPolicyReason.RUNTIME_UNAVAILABLE

    allowed = evaluate_shot_target(
        "KLING_3_0",
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert allowed.accepted is True
    assert allowed.target == "KLING_3_0"


def test_veo_runtime_alternatives_require_complete_api_key_or_adc_path() -> None:
    missing_service = RuntimeSnapshot(
        credentials={"google_cloud_project"},
        modules={"google.genai"},
    )
    missing_module = RuntimeSnapshot(credentials={"google_api_key"})
    assert evaluate_shot_target(
        "VEO_NATIVE",
        snapshot=missing_service,
        on_date=PRE_SUNSET,
    ).reason is VideoPolicyReason.RUNTIME_UNAVAILABLE
    assert evaluate_shot_target(
        "VEO_NATIVE",
        snapshot=missing_module,
        on_date=PRE_SUNSET,
    ).reason is VideoPolicyReason.RUNTIME_UNAVAILABLE

    api_key_path = evaluate_shot_target(
        "VEO_NATIVE",
        snapshot=_veo_api_key_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert api_key_path.accepted is True

    adc_path = evaluate_shot_target(
        "VEO_NATIVE",
        snapshot=RuntimeSnapshot(
            credentials={"google_cloud_project"},
            modules={"google.genai"},
            services={"google_adc"},
        ),
        on_date=PRE_SUNSET,
    )
    assert adc_path.accepted is True


def test_sora_native_is_fallback_only_before_sunset_and_denied_on_sunset() -> None:
    authoring = evaluate_shot_target(
        "SORA_NATIVE",
        snapshot=_sora_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert authoring.reason is VideoPolicyReason.NOT_SELECTABLE

    before = filter_dispatch_candidates(
        ["SORA_NATIVE"],
        snapshot=_sora_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert before.candidates == ("SORA_NATIVE",)
    assert before.rejections == ()

    on_boundary = filter_dispatch_candidates(
        ["SORA_NATIVE"],
        snapshot=_sora_snapshot(),
        on_date=SUNSET,
    )
    assert on_boundary.candidates == ()
    assert on_boundary.rejections[0].reason is VideoPolicyReason.RETIRED


def test_nonselectable_kling_native_is_admitted_only_as_ready_fallback() -> None:
    snapshot = RuntimeSnapshot(
        credentials={"kling_access_key", "kling_secret_key"},
        modules={"jwt"},
    )
    authoring = evaluate_shot_target(
        "KLING_NATIVE",
        snapshot=snapshot,
        on_date=PRE_SUNSET,
    )
    assert authoring.reason is VideoPolicyReason.NOT_SELECTABLE

    routing = filter_dispatch_candidates(
        ["KLING_NATIVE"],
        snapshot=snapshot,
        on_date=PRE_SUNSET,
    )
    assert routing.candidates == ("KLING_NATIVE",)


def test_fal_sora_is_always_retired_even_with_fal_runtime() -> None:
    result = filter_dispatch_candidates(
        ["SORA_2"],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result.candidates == ()
    assert result.rejections[0].reason is VideoPolicyReason.RETIRED


def test_project_explicit_disable_rejects_otherwise_ready_candidate() -> None:
    result = filter_dispatch_candidates(
        ["SEEDANCE"],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"SEEDANCE": {"enabled": False}},
    )
    assert result.candidates == ()
    assert result.rejections[0].reason is VideoPolicyReason.PROJECT_DISABLED

    absent_is_not_disabled = filter_dispatch_candidates(
        ["SEEDANCE"],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={},
    )
    assert absent_is_not_disabled.candidates == ("SEEDANCE",)


def test_portrait_dispatch_rejects_unwired_engine_with_structured_reason() -> None:
    result = filter_dispatch_candidates(
        ["LTX", "SEEDANCE"],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        aspect_ratio="9:16",
    )
    assert result.candidates == ("SEEDANCE",)
    assert [(item.key, item.reason) for item in result.rejections] == [
        ("LTX", VideoPolicyReason.ASPECT_INCOMPATIBLE),
    ]


def test_dispatch_filter_preserves_order_dedupes_and_reports_rejections() -> None:
    result = filter_dispatch_candidates(
        [
            "AUTO",
            "SORA_2",
            "LTX",
            "KLING_3_0",
            "LTX",
            "RUNWAY_ACT_ONE",
            "SEEDANCE",
        ],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
        api_engines={"SEEDANCE": {"enabled": False}},
    )
    assert result.candidates == ("LTX", "KLING_3_0")
    assert result.primary == "LTX"
    assert result.fallbacks == ("KLING_3_0",)
    assert [(item.key, item.reason) for item in result.rejections] == [
        ("AUTO", VideoPolicyReason.AUTO_SENTINEL),
        ("SORA_2", VideoPolicyReason.RETIRED),
        ("RUNWAY_ACT_ONE", VideoPolicyReason.NON_VIDEO),
        ("SEEDANCE", VideoPolicyReason.PROJECT_DISABLED),
    ]


def test_empty_or_all_rejected_candidate_result_has_auto_primary() -> None:
    empty = filter_dispatch_candidates(
        [],
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    assert empty.candidates == ()
    assert empty.primary == "AUTO"
    assert empty.fallbacks == ()
    assert empty.rejections == ()

    rejected = resolve_workflow_candidates(
        "GEMINI_OMNI",
        ["SORA_2", "RUNWAY_ACT_ONE"],
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    assert rejected.candidates == ()
    assert rejected.primary == "AUTO"
    assert {item.reason for item in rejected.rejections} == {
        VideoPolicyReason.UNSUPPORTED,
        VideoPolicyReason.RETIRED,
        VideoPolicyReason.NON_VIDEO,
    }


def test_resolved_authoring_ranking_excludes_fallback_only_and_unsafe_keys() -> None:
    result = resolve_video_ranking(
        [
            "GEMINI_OMNI",
            "SORA_NATIVE",
            "SORA_2",
            "RUNWAY_ACT_ONE",
            "SEEDANCE",
            "SEEDANCE",
        ],
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert result.candidates == ("SEEDANCE",)
    assert [(item.key, item.reason) for item in result.rejections] == [
        ("GEMINI_OMNI", VideoPolicyReason.UNSUPPORTED),
        ("SORA_NATIVE", VideoPolicyReason.NOT_SELECTABLE),
        ("SORA_2", VideoPolicyReason.RETIRED),
        ("RUNWAY_ACT_ONE", VideoPolicyReason.NON_VIDEO),
    ]


def test_eligible_targets_are_auto_plus_ready_selectable_video_only() -> None:
    targets = eligible_shot_targets(
        snapshot=_fal_snapshot(),
        on_date=PRE_SUNSET,
    )
    assert targets == ("AUTO", "KLING_3_0", "SEEDANCE", "VEO")
    assert "SORA_NATIVE" not in targets
    assert "SORA_2" not in targets
    assert "GEMINI_OMNI" not in targets
    assert "RUNWAY_ACT_ONE" not in targets


def test_no_runtime_still_exposes_auto_as_the_only_authoring_target() -> None:
    assert eligible_shot_targets(
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    ) == ("AUTO",)


def test_symbolic_snapshot_and_results_do_not_retain_secret_values() -> None:
    secret = "never-print-this-secret"
    snapshot = build_runtime_snapshot(
        SimpleNamespace(fal_key=secret),
        module_probe=lambda name: name == "fal_client",
    )
    result = filter_dispatch_candidates(
        ["KLING_3_0"],
        snapshot=snapshot,
        on_date=PRE_SUNSET,
    )

    assert snapshot.credentials == frozenset({"fal_key"})
    assert snapshot.modules == frozenset({"fal_client"})
    assert secret not in repr(snapshot)
    assert secret not in repr(result)


def test_policy_results_are_immutable() -> None:
    decision = evaluate_shot_target(
        "AUTO",
        snapshot=RuntimeSnapshot(),
        on_date=PRE_SUNSET,
    )
    with pytest.raises(FrozenInstanceError):
        decision.target = "KLING_3_0"  # type: ignore[misc]

"""Mutation-grade tests for the typed video dispatch entry fence.

Every test is offline.  Runtime availability and policy dates are injected;
provider modules are stubs, and rejected calls bomb on any observable dispatch
effect.
"""

from __future__ import annotations

import builtins
import inspect
import sys
import types
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import phase_c_ffmpeg
from cinema.context import PipelineContext
from domain.provider_catalog import RuntimeSnapshot


PRE_SUNSET = date(2026, 9, 23)
SUNSET = date(2026, 9, 24)


def _ctx(aspect: str = "16:9", **settings) -> PipelineContext:
    return PipelineContext(
        global_settings={
            "aspect_ratio": aspect,
            "cascade_retry_limit": 0,
            **settings,
        }
    )


def _fal_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


def _veo_ltx_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"google_api_key", "fal_key"},
        modules={"google.genai", "fal_client"},
    )


def _provider_import_bomb(name, globals=None, locals=None, fromlist=(), level=0):
    provider_modules = {
        "fal_client",
        "gemini_omni_native",
        "kling_native",
        "ltx_native",
        "runwayml",
        "sora_native",
        "veo_native",
    }
    if name in provider_modules:
        raise AssertionError(f"provider import escaped policy fence: {name}")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


_REAL_IMPORT = builtins.__import__


@pytest.fixture(autouse=True)
def _stable_policy_observation(monkeypatch):
    """Every provider harness declares a deterministic eligible runtime."""

    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _fal_snapshot,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: PRE_SUNSET,
    )


def test_public_signature_exposes_no_policy_bypass_arguments() -> None:
    parameters = inspect.signature(phase_c_ffmpeg.generate_ai_video).parameters

    assert "_policy_snapshot" not in parameters
    assert "_policy_date" not in parameters
    assert "_policy_allow_primary_fallback" not in parameters
    assert "_policy_candidates" not in parameters
    assert "_policy_guard_token" not in parameters
    assert "_cascade_retries" not in parameters
    assert not hasattr(phase_c_ffmpeg, "_VIDEO_POLICY_GUARD_TOKEN")


@pytest.mark.parametrize(
    ("target_api", "snapshot", "on_date", "expected_reason"),
    [
        ("SORA_2", _fal_snapshot(), PRE_SUNSET, "retired"),
        (
            "SORA_NATIVE",
            RuntimeSnapshot(
                credentials={"openai_api_key"},
                modules={"openai"},
            ),
            SUNSET,
            "retired",
        ),
        ("GEMINI_OMNI", _fal_snapshot(), PRE_SUNSET, "unsupported"),
        ("DOES_NOT_EXIST", RuntimeSnapshot(), PRE_SUNSET, "unknown"),
        ("RUNWAY_ACT_ONE", RuntimeSnapshot(), PRE_SUNSET, "non_video"),
        ("KLING_3_0", RuntimeSnapshot(), PRE_SUNSET, "runtime_unavailable"),
    ],
)
def test_explicit_rejection_has_no_dispatch_side_effects(
    target_api,
    snapshot,
    on_date,
    expected_reason,
    monkeypatch,
) -> None:
    attempted: list[str] = []
    cascade: dict = {}
    bomb = MagicMock(side_effect=AssertionError("dispatch effect escaped fence"))
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_current_date",
        lambda: on_date,
    )

    with (
        patch.object(phase_c_ffmpeg, "_load_fal_client", bomb),
        patch.object(phase_c_ffmpeg.time, "sleep", bomb),
        patch.object(phase_c_ffmpeg.logger, "info", bomb),
        patch.object(phase_c_ffmpeg, "safe_download", bomb),
        patch.object(builtins, "__import__", side_effect=_provider_import_bomb),
    ):
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            target_api,
            "out.mp4",
            attempted_apis=attempted,
            _cascade_out=cascade,
        )

    assert result is None
    assert attempted == []
    assert cascade["policy_error"] == {
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": target_api,
        "reason": expected_reason,
        "retryable": False,
    }
    assert cascade["policy_rejections"][0] == {
        "key": target_api,
        "reason": expected_reason,
    }
    bomb.assert_not_called()


def test_explicit_rejected_primary_does_not_silently_use_supplied_fallback() -> None:
    cascade: dict = {}
    with patch.object(
        builtins,
        "__import__",
        side_effect=_provider_import_bomb,
    ):
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            "SORA_2",
            "out.mp4",
            video_fallbacks=["LTX"],
            _cascade_out=cascade,
        )

    assert result is None
    assert cascade["policy_error"]["reason"] == "retired"
    assert cascade["policy_rejections"] == [
        {"key": "SORA_2", "reason": "retired"},
    ]


def test_auto_safe_chain_skips_rejected_head_and_preserves_order(
    monkeypatch,
    tmp_path,
) -> None:
    output = str(tmp_path / "ltx.mp4")
    ltx_instance = MagicMock()
    ltx_instance.generate_video.return_value = output
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)

    cascade: dict = {}
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "AUTO",
        output,
        video_fallbacks=["SORA_2", "LTX", "LTX"],
        shot_type="wide",
        _cascade_out=cascade,
    )

    assert result == output
    assert cascade["cascade_metadata"] == {
        "engine": "LTX",
        "attempts": ["LTX"],
    }
    assert cascade["policy_rejections"] == [
        {"key": "AUTO", "reason": "auto_sentinel"},
        {"key": "SORA_2", "reason": "retired"},
    ]
    ltx_module.LTXVideoAPI.assert_called_once_with()


def test_valid_chain_filters_once_dedupes_and_cascades_in_order(
    monkeypatch,
    tmp_path,
) -> None:
    output = str(tmp_path / "winner.mp4")

    veo_instance = MagicMock()
    veo_instance.generate_video.return_value = None
    veo_module = types.ModuleType("veo_native")
    veo_module.VeoNativeAPI = MagicMock(return_value=veo_instance)
    monkeypatch.setitem(sys.modules, "veo_native", veo_module)

    ltx_instance = MagicMock()
    ltx_instance.generate_video.return_value = output
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _veo_ltx_snapshot,
    )

    cascade: dict = {}
    with patch.object(
        phase_c_ffmpeg,
        "filter_dispatch_candidates",
        wraps=phase_c_ffmpeg.filter_dispatch_candidates,
    ) as policy_filter:
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            "VEO_NATIVE",
            output,
            video_fallbacks=["VEO_NATIVE", "SORA_2", "LTX", "LTX"],
            shot_type="wide",
            ctx=_ctx(),
            _cascade_out=cascade,
        )

    assert result == output
    assert cascade["cascade_metadata"] == {
        "engine": "LTX",
        "attempts": ["VEO_NATIVE", "LTX"],
    }
    assert cascade["policy_rejections"] == [
        {"key": "SORA_2", "reason": "retired"},
    ]
    veo_module.VeoNativeAPI.assert_called_once_with()
    ltx_module.LTXVideoAPI.assert_called_once_with()
    policy_filter.assert_called_once()


def test_cooldown_retry_reuses_filtered_chain_without_raw_revive(
    monkeypatch,
) -> None:
    veo_instance = MagicMock()
    veo_instance.generate_video.return_value = None
    veo_module = types.ModuleType("veo_native")
    veo_module.VeoNativeAPI = MagicMock(return_value=veo_instance)
    monkeypatch.setitem(sys.modules, "veo_native", veo_module)

    ltx_instance = MagicMock()
    ltx_instance.generate_video.return_value = None
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _veo_ltx_snapshot,
    )
    sleep = MagicMock()
    monkeypatch.setattr(phase_c_ffmpeg.time, "sleep", sleep)

    cascade: dict = {}
    with patch.object(
        phase_c_ffmpeg,
        "filter_dispatch_candidates",
        wraps=phase_c_ffmpeg.filter_dispatch_candidates,
    ) as policy_filter:
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            "VEO_NATIVE",
            "out.mp4",
            video_fallbacks=["SORA_2", "LTX", "GEMINI_OMNI"],
            ctx=_ctx(cascade_retry_limit=1),
            _cascade_out=cascade,
        )

    assert result is None
    sleep.assert_called_once_with(30)
    assert veo_module.VeoNativeAPI.call_count == 2
    assert ltx_module.LTXVideoAPI.call_count == 2
    policy_filter.assert_called_once()
    assert cascade["policy_rejections"] == [
        {"key": "SORA_2", "reason": "retired"},
        {"key": "GEMINI_OMNI", "reason": "unsupported"},
    ]
    assert cascade["attempt_history"] == [
        "VEO_NATIVE",
        "LTX",
        "VEO_NATIVE",
        "LTX",
    ]


def test_cooldown_winner_keeps_prior_cycle_attempt_provenance(
    monkeypatch,
    tmp_path,
) -> None:
    """Cycle dedupe resets after cooldown; the audit trail must not."""

    output = str(tmp_path / "second_cycle_winner.mp4")
    attempted: list[str] = []
    ltx_instance = MagicMock()
    ltx_instance.generate_video.side_effect = [None, output]
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(phase_c_ffmpeg.time, "sleep", MagicMock())

    cascade: dict = {}
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "LTX",
        output,
        attempted_apis=attempted,
        ctx=_ctx(cascade_retry_limit=1),
        _cascade_out=cascade,
    )

    assert result == output
    assert ltx_instance.generate_video.call_count == 2
    # The public cycle guard remains deduped for callers that inspect it.
    assert attempted == ["LTX"]
    # The success record is append-only and proves the second-cycle dispatch.
    assert cascade["attempt_history"] == ["LTX", "LTX"]
    assert cascade["cascade_metadata"] == {
        "engine": "LTX",
        "attempts": ["LTX", "LTX"],
    }


@pytest.mark.parametrize(
    ("ctx", "expected_reason"),
    [
        (
            _ctx(api_engines={"LTX": {"enabled": False}}),
            "project_disabled",
        ),
        (_ctx("9:16"), "aspect_incompatible"),
    ],
)
def test_project_and_aspect_rejections_are_evidenced_before_provider(
    ctx,
    expected_reason,
) -> None:
    cascade: dict = {}
    with patch.object(
        builtins,
        "__import__",
        side_effect=_provider_import_bomb,
    ):
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            "LTX",
            "out.mp4",
            ctx=ctx,
            _cascade_out=cascade,
        )

    assert result is None
    assert cascade["policy_error"]["reason"] == expected_reason
    assert cascade["policy_rejections"] == [
        {"key": "LTX", "reason": expected_reason},
    ]


def test_auto_without_runtime_cannot_revive_raw_unsafe_defaults(
    monkeypatch,
) -> None:
    assert "GEMINI_OMNI" not in phase_c_ffmpeg.DEFAULT_VIDEO_CASCADE
    assert "SORA_2" not in phase_c_ffmpeg.DEFAULT_VIDEO_CASCADE

    attempted: list[str] = []
    cascade: dict = {}
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        RuntimeSnapshot,
    )
    with (
        patch.object(
            builtins,
            "__import__",
            side_effect=_provider_import_bomb,
        ),
        patch.object(
            phase_c_ffmpeg.time,
            "sleep",
            side_effect=AssertionError("empty policy chain must not sleep"),
        ),
    ):
        result = phase_c_ffmpeg.generate_ai_video(
            "frame.png",
            "static",
            "AUTO",
            "out.mp4",
            attempted_apis=attempted,
            _cascade_out=cascade,
        )

    assert result is None
    assert attempted == []
    assert cascade["policy_error"]["reason"] == "runtime_unavailable"
    rejected_keys = [item["key"] for item in cascade["policy_rejections"]]
    assert rejected_keys[0] == "AUTO"
    assert "GEMINI_OMNI" not in rejected_keys
    assert "SORA_2" not in rejected_keys

"""Mutation-grade tests for the typed video dispatch entry fence.

Every test is offline.  Runtime availability and policy dates are injected;
provider modules are stubs, and rejected calls bomb on any observable dispatch
effect.
"""

from __future__ import annotations

import builtins
import importlib
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


def _real_ltx_contract_violation() -> type:
    """Return the REAL ``ltx_native.LTXContractViolation`` class.

    Several sibling test modules (test_budget_pre_spend_gate,
    test_dialogue_audio_cache, test_dialogue_routing, test_ensure_shot_audio,
    test_f1b_dialogue_lipsync) install a bare ``types.ModuleType`` stub for
    'ltx_native' at THEIR import time — i.e. during collection, before any test
    here runs — and never remove it.  A plain ``import ltx_native`` therefore
    yields the stub (no attributes) whenever this file is run alongside them
    without test_ltx_native.py, which is the only module that pops the stub and
    reinstates the real one.  Don't depend on that sibling: resolve the real
    class here, restoring whatever was cached so the stub-based tests are
    unaffected.
    """
    cached = sys.modules.get("ltx_native")
    exc = getattr(cached, "LTXContractViolation", None)
    if exc is not None:
        return exc
    sys.modules.pop("ltx_native", None)
    try:
        return importlib.import_module("ltx_native").LTXContractViolation
    finally:
        if cached is not None:
            sys.modules["ltx_native"] = cached


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
        # Re-admitted in Slice 3: with no google credential/module in the fal
        # snapshot the truthful denial is runtime availability, not product
        # support (invariant 4).
        ("GEMINI_OMNI", _fal_snapshot(), PRE_SUNSET, "runtime_unavailable"),
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
        "duration_s": 8,  # the shared dispatcher default (no explicit duration passed)
    }
    assert cascade["policy_rejections"] == [
        {"key": "AUTO", "reason": "auto_sentinel"},
        {"key": "SORA_2", "reason": "retired"},
    ]
    ltx_module.LTXVideoAPI.assert_called_once_with()


@pytest.mark.parametrize(
    ("requested_duration", "expected_ltx_duration"),
    [
        ("8s", 8),      # the shared default — already in the ltx-2-3-pro enum
        ("10s", 10),    # exact enum member, unit suffix
        ("5", 6),       # no unit suffix; below the floor -> snaps UP to 6
        ("4s", 6),      # the LTX client's OLD (invalid) default -> snaps to 6
        ("7s", 8),      # between enum members -> snaps UP to 8
        ("9s", 10),     # between enum members -> snaps UP to 10
        ("not-a-number", 6),  # unparseable -> falls back to the enum floor
    ],
)
def test_ltx_threads_duration_from_dispatcher_config(
    monkeypatch,
    tmp_path,
    requested_duration,
    expected_ltx_duration,
) -> None:
    """duration is not threaded from dispatcher/config (audited 2026-07-30):
    the LTX branch never passed `duration` to generate_video() at all, so
    every call silently rode the client's own default (itself invalid).
    Now the shared "Xs" config value must be parsed and snapped to the
    ltx-2-3-pro duration enum {6, 8, 10} before being passed through."""
    output = str(tmp_path / "ltx.mp4")
    ltx_instance = MagicMock()
    ltx_instance.generate_video.return_value = output
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)

    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "LTX",
        output,
        shot_type="wide",
        duration=requested_duration,
    )

    assert result == output
    ltx_instance.generate_video.assert_called_once()
    assert ltx_instance.generate_video.call_args.kwargs["duration"] == expected_ltx_duration


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
        "duration_s": 8,  # the shared dispatcher default (no explicit duration passed)
    }
    assert cascade["policy_rejections"] == [
        {"key": "SORA_2", "reason": "retired"},
    ]
    veo_module.VeoNativeAPI.assert_called_once_with()
    ltx_module.LTXVideoAPI.assert_called_once_with()
    policy_filter.assert_called_once()


def test_ltx_contract_violation_cascades_and_is_surfaced_distinctly(
    monkeypatch,
    tmp_path,
) -> None:
    """A local LTXContractViolation (e.g. an out-of-enum duration reaching
    generate_video despite the dispatcher's own snap-up) must still cascade
    to the next candidate — but be recorded DISTINCTLY from a routine
    provider error, not folded into the same blanket 'LTX error' noise
    (silent-gate-degradation doctrine: a local-contract bug must be VISIBLE,
    money-gate finding 2026-07-30)."""
    contract_violation = _real_ltx_contract_violation()

    output = str(tmp_path / "veo.mp4")

    veo_instance = MagicMock()
    veo_instance.generate_video.return_value = output
    veo_module = types.ModuleType("veo_native")
    veo_module.VeoNativeAPI = MagicMock(return_value=veo_instance)
    monkeypatch.setitem(sys.modules, "veo_native", veo_module)

    ltx_instance = MagicMock()
    ltx_instance.generate_video.side_effect = contract_violation("bad duration")
    ltx_module = types.ModuleType("ltx_native")
    ltx_module.LTXVideoAPI = MagicMock(return_value=ltx_instance)
    ltx_module.LTXContractViolation = contract_violation
    monkeypatch.setitem(sys.modules, "ltx_native", ltx_module)
    monkeypatch.setattr(phase_c_ffmpeg, "_load_fal_client", lambda: None)
    monkeypatch.setattr(
        phase_c_ffmpeg,
        "_video_policy_runtime_snapshot",
        _veo_ltx_snapshot,
    )

    cascade: dict = {}
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "LTX",
        output,
        video_fallbacks=["VEO_NATIVE"],
        shot_type="wide",
        ctx=_ctx(),
        _cascade_out=cascade,
    )

    assert result == output
    assert cascade["cascade_metadata"]["engine"] == "VEO_NATIVE"
    assert cascade["contract_violations"] == [
        {"engine": "LTX", "reason": "ltx_contract_violation", "detail": "bad duration"}
    ]
    veo_module.VeoNativeAPI.assert_called_once_with()


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
    # Slice 3 re-admitted GEMINI_OMNI; under this google-credentialed snapshot
    # it is dispatchable, so it joins the filtered chain (its real adapter
    # no-ops pre-billing on the missing start frame) instead of being
    # policy-rejected as unsupported.
    assert cascade["policy_rejections"] == [
        {"key": "SORA_2", "reason": "retired"},
    ]
    assert cascade["attempt_history"] == [
        "VEO_NATIVE",
        "LTX",
        "GEMINI_OMNI",
        "VEO_NATIVE",
        "LTX",
        "GEMINI_OMNI",
    ]


def test_cascade_retry_limit_defaults_to_one_when_setting_absent(
    monkeypatch,
) -> None:
    """Reciprocal-default test (slice 9b, settings-reconciliation audit).

    A project whose ``global_settings`` never wrote ``cascade_retry_limit``
    (every project created via ``domain.project_manager.make_project``,
    which does not scaffold this key) must fall back to the SAME
    ``MAX_CASCADE_RETRIES`` the source declares (phase_c_ffmpeg.py's
    ``try_next_api``): 1 cooldown retry, i.e. 2 total dispatch passes.
    VideoSection's "Cascade retry limit" slider now displays this same
    value (1) as its default — before this audit it displayed 2, which
    matched neither this constant nor docs/PROGRAM-MANUAL.md's repeated
    "default 1" citations.

    Mirrors test_cooldown_retry_reuses_filtered_chain_without_raw_revive's
    harness exactly, swapping the explicit ``cascade_retry_limit=1``
    override for a context whose ``global_settings`` simply omits the key
    — the real "operator never touched this setting" shape.
    """
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

    # A real project's global_settings dict, present but never touched for
    # this key — NOT this file's _ctx() helper, which bakes in its own
    # cascade_retry_limit=0 test-safety default and would mask the bug.
    no_override_ctx = PipelineContext(global_settings={"aspect_ratio": "16:9"})
    assert "cascade_retry_limit" not in no_override_ctx.global_settings

    cascade: dict = {}
    result = phase_c_ffmpeg.generate_ai_video(
        "frame.png",
        "static",
        "VEO_NATIVE",
        "out.mp4",
        video_fallbacks=["LTX"],
        ctx=no_override_ctx,
        _cascade_out=cascade,
    )

    assert result is None
    sleep.assert_called_once_with(30)
    assert veo_module.VeoNativeAPI.call_count == 2
    assert ltx_module.LTXVideoAPI.call_count == 2


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
        "duration_s": 8,  # the shared dispatcher default (no explicit duration passed)
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

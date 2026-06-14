"""nan-gate for phase_c_assembly's STANDARD-tier img2img_denoise override.

`generate_ai_broll` (standard tier) read `continuity_options.img2img_denoise` with a
raw `max(0.2, min(0.6, float(raw)))` clamp — a NaN token (which survives project.json
because `json.load` defaults to `allow_nan=True`) clamp-lucks to 0.6, silently
overwriting the caller-supplied denoise default. The MAX-tier sibling
(`quality_max.generate_ai_broll_max`) already rejected non-finite via
`_clamp_img2img_denoise`; this is the Rule#13 standard-tier twin that fix missed.

Surfaced by the independent post-commit verification of 7b4d377/bf1034a
(`wf_7a7dbebf-4e3`, director-1 2026-06-14). Fix = extract `_resolve_ui_denoise(ctx)`
with an `isinstance` + `math.isfinite` guard (mirrors bf1034a's same-knob fix in
workflow_selector), so a non-finite override is skipped and the caller's default
survives. The isinstance gate is preserved, so ONLY non-finite handling changes.
"""
from types import SimpleNamespace

import pytest

from phase_c_assembly import _resolve_ui_denoise


def _ctx(img2img_denoise):
    return SimpleNamespace(
        global_settings={"continuity_options": {"img2img_denoise": img2img_denoise}}
    )


class TestResolveUiDenoise:
    def test_nan_returns_none_keeps_caller_default(self):
        """The bug: a NaN override must be SKIPPED (None), not clamp-luck to 0.6."""
        assert _resolve_ui_denoise(_ctx(float("nan"))) is None

    def test_pos_inf_returns_none(self):
        assert _resolve_ui_denoise(_ctx(float("inf"))) is None

    def test_neg_inf_returns_none(self):
        assert _resolve_ui_denoise(_ctx(float("-inf"))) is None

    def test_in_range_value_passthrough(self):
        assert _resolve_ui_denoise(_ctx(0.4)) == pytest.approx(0.4)

    def test_above_range_clamped_to_ceiling(self):
        assert _resolve_ui_denoise(_ctx(0.9)) == pytest.approx(0.6)

    def test_below_range_clamped_to_floor(self):
        assert _resolve_ui_denoise(_ctx(0.1)) == pytest.approx(0.2)

    def test_non_numeric_string_rejected(self):
        """isinstance gate preserved — a string override is rejected (None), matching
        pre-fix behavior; only non-finite handling changed, not string handling."""
        assert _resolve_ui_denoise(_ctx("0.4")) is None

    def test_missing_key_returns_none(self):
        assert _resolve_ui_denoise(SimpleNamespace(global_settings={})) is None

    def test_none_ctx_returns_none(self):
        assert _resolve_ui_denoise(None) is None

    def test_none_global_settings_returns_none(self):
        assert _resolve_ui_denoise(SimpleNamespace(global_settings=None)) is None

    def test_none_continuity_options_returns_none(self):
        """Rule#13 parity with the MAX-tier sibling's isinstance(_co, dict) guard:
        a null continuity_options must yield None, not AttributeError on None.get."""
        assert _resolve_ui_denoise(
            SimpleNamespace(global_settings={"continuity_options": None})
        ) is None

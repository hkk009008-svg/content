"""NaN/inf-gate tests for the Pair-B (video/assembly/delivery) lane — TDD RED-first.

Same defect class as ``test_quality_max_nan_gate.py`` (Pair-A): a NaN/inf settings
value survives ``project.json`` (``json.load(allow_nan=True)`` is the default, so a
bare ``NaN`` token persists on disk) and defeats a numeric gate because ``score <
NaN`` and ``score >= NaN`` are BOTH ``False``.  A ``try/except (TypeError,
ValueError)`` around ``float(...)`` does NOT catch it — ``float('nan')`` succeeds.

director2 PM7 §4A sites (Pair-B / shared) covered here:
  - ``cinema.context._finite_or`` — the shared read-side guard (the canonical home;
    unifies the documented-temporary ``quality_max:191`` local copy via a later
    Pair-A import-swap).
  - ``lip_sync._sync_gate_settings`` — ``lipsync_validation_threshold`` (MAJOR): a
    NaN threshold => every engine fails the sync gate => always best-of-failed.
  - ``cinema/shots/controller.diagnose_clip`` — ``coherence_threshold`` (MAJOR) +
    ``color_drift_sensitivity`` (minor): NaN => the regen / color-grade
    recommendation never fires.
  - ``cinema.capability_scorecard`` — lipsync/coherence reporting bars (minor): NaN
    skews the scorecard ``shots_clearing`` counts.

The ``identity_strictness`` keyframe-gen site (controller ~:810) delegates entirely
to ``_finite_or`` (default = the per-shot ``identity_threshold``); it is covered by
the ``_finite_or`` unit tests below + the full suite, mirroring the approach
operator-1 accepted as non-blocking for the quality_max inline call sites.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cinema.shots.controller import ShotController


# ---------------------------------------------------------------------------
# Shared helper — cinema.context._finite_or (the new canonical home)
# ---------------------------------------------------------------------------
class TestSharedFiniteOr:
    """Unit tests for the shared ``_finite_or(value, default)`` helper.

    Mirrors quality_max's ``TestFiniteOrHelper`` so the two implementations are
    provably behaviour-identical before Pair-A swaps its local copy for the import.
    """

    def test_nan_returns_default(self):
        from cinema.context import _finite_or
        assert _finite_or(float("nan"), 0.82) == pytest.approx(0.82)

    def test_pos_inf_returns_default(self):
        from cinema.context import _finite_or
        assert _finite_or(float("inf"), 0.6) == pytest.approx(0.6)

    def test_neg_inf_returns_default(self):
        from cinema.context import _finite_or
        assert _finite_or(float("-inf"), 0.6) == pytest.approx(0.6)

    def test_numeric_string_coerced(self):
        from cinema.context import _finite_or
        assert _finite_or("0.8", 0.6) == pytest.approx(0.8)

    def test_non_numeric_string_returns_default(self):
        from cinema.context import _finite_or
        assert _finite_or("abc", 0.6) == pytest.approx(0.6)

    def test_valid_float_passthrough(self):
        from cinema.context import _finite_or
        assert _finite_or(0.9, 0.6) == pytest.approx(0.9)

    def test_none_returns_default(self):
        from cinema.context import _finite_or
        assert _finite_or(None, 0.6) == pytest.approx(0.6)

    def test_zero_is_finite_passthrough(self):
        """0.0 is finite and falsy — must pass through, NOT fall to the default."""
        from cinema.context import _finite_or
        assert _finite_or(0.0, 0.6) == pytest.approx(0.0)

    def test_huge_int_returns_default(self):
        """float(10**309) raises OverflowError (NOT Type/ValueError); a huge JSON integer
        must fall back to the default, not propagate uncaught. Kept byte-identical with
        quality_max's TestFiniteOrHelper.test_huge_int_returns_default (the mirror)."""
        from cinema.context import _finite_or
        assert _finite_or(10 ** 309, 0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# lip_sync._sync_gate_settings — lipsync_validation_threshold (MAJOR)
# ---------------------------------------------------------------------------
class TestLipsyncGateThreshold:
    """A NaN/inf ``lipsync_validation_threshold`` must fall back to the finite
    0.65 default; otherwise ``score >= NaN`` is always False so no engine ever
    clears the gate => the cascade always returns best-of-failed."""

    def test_nan_threshold_falls_back_to_finite_default(self):
        from lip_sync import _sync_gate_settings
        enabled, threshold = _sync_gate_settings({"lipsync_validation_threshold": float("nan")})
        assert math.isfinite(threshold), f"threshold {threshold!r} must be finite"
        assert threshold == pytest.approx(0.65)

    def test_pos_inf_threshold_falls_back(self):
        from lip_sync import _sync_gate_settings
        _, threshold = _sync_gate_settings({"lipsync_validation_threshold": float("inf")})
        assert math.isfinite(threshold)
        assert threshold == pytest.approx(0.65)

    def test_non_coercible_threshold_falls_back(self):
        # non-regression: already handled by the prior try/except — must stay green.
        from lip_sync import _sync_gate_settings
        _, threshold = _sync_gate_settings({"lipsync_validation_threshold": "abc"})
        assert threshold == pytest.approx(0.65)

    def test_valid_threshold_passthrough(self):
        from lip_sync import _sync_gate_settings
        _, threshold = _sync_gate_settings({"lipsync_validation_threshold": 0.8})
        assert threshold == pytest.approx(0.8)

    def test_none_settings_defaults(self):
        # non-regression: None settings => (True, 0.65).
        from lip_sync import _sync_gate_settings
        enabled, threshold = _sync_gate_settings(None)
        assert enabled is True
        assert threshold == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# capability_scorecard reporting bars — coherence/lipsync (minor)
# ---------------------------------------------------------------------------
def _scorecard_project(global_settings: dict) -> dict:
    shot = {
        "id": "s1_01", "primary_character": "char_a",
        "keyframe_takes": [{"id": "k1", "kind": "keyframe", "metadata": {"identity_score": 0.74}}],
        "motion_takes": [{"id": "m1", "kind": "motion",
                          "metadata": {"motion_fidelity": 0.82, "lipsync_score": 0.72}}],
        "approved_motion_take_id": "m1", "approved_keyframe_take_id": "k1",
        "diagnostics": [{"take_id": "k1", "scores": {"coherence": 0.64}}],
    }
    return {"id": "p1", "name": "x", "characters": [{"id": "char_a"}],
            "scenes": [{"shots": [shot]}], "global_settings": global_settings}


class TestScorecardBars:
    """A NaN coherence/lipsync threshold setting must not poison the reporting
    bars (a NaN bar skews the ``shots_clearing_all_bars`` count)."""

    def test_nan_coherence_and_lipsync_bars_are_finite(self):
        from cinema.capability_scorecard import build_capability_scorecard
        gs = {"quality_tier": "max",
              "coherence_threshold": float("nan"),
              "lipsync_validation_threshold": float("nan")}
        sc = build_capability_scorecard(_scorecard_project(gs), project_dir="/tmp/nonexistent")
        coh = next(d for d in sc["dimensions"] if d["key"] == "coherence")
        lip = next(d for d in sc["dimensions"] if d["key"] == "lipsync")
        assert math.isfinite(coh["bar"]), f"coherence bar {coh['bar']!r} must be finite"
        assert math.isfinite(lip["bar"]), f"lipsync bar {lip['bar']!r} must be finite"


# ---------------------------------------------------------------------------
# controller.diagnose_clip — coherence_threshold (MAJOR) + color_drift (minor)
# ---------------------------------------------------------------------------
def _build_two_shot_controller(tmp_path, global_settings: dict):
    """Two-shot scene so ``diagnose_clip`` of shot index 1 reaches the coherence
    block (it requires ``shot_index > 0`` + an existing previous-shot image).
    Identity + motion blocks are deliberately skipped (no in-frame chars; keyframe
    candidate => no video_path) so only the coherence/color-drift recs can fire."""
    img1 = str(tmp_path / "kf1.jpg")
    img2 = str(tmp_path / "kf2.jpg")
    for p in (img1, img2):
        with open(p, "wb") as fh:
            fh.write(b"img")
    shot1 = {"id": "s_0", "characters_in_frame": [], "approved_keyframe_take_id": "k0",
             "keyframe_takes": [{"id": "k0", "kind": "keyframe", "path": img1}]}
    shot2 = {"id": "s_1", "characters_in_frame": [], "approved_keyframe_take_id": "k1",
             "keyframe_takes": [{"id": "k1", "kind": "keyframe", "path": img2}]}
    scene = {"id": "sc", "shots": [shot1, shot2], "characters_present": []}
    project = {"id": "p", "scenes": [scene], "characters": [], "objects": [],
               "locations": [], "global_settings": global_settings}

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    host._candidate_take.return_value = {"id": "k1", "kind": "keyframe", "path": img2}
    host._resolve_take_path.return_value = img1   # previous shot's keyframe
    host._latest_take.return_value = {"path": img1}

    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}
    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    return ctrl, project


class TestCoherenceColorDriftRegenGate:
    def test_nan_coherence_threshold_still_fires_regen(self, tmp_path):
        """coherence_threshold = NaN must NOT silently disable the regen gate:
        a low coherence (0.2) must still recommend 'regenerate', and a high
        color_drift (0.9) with NaN sensitivity must still recommend 'color_grade'."""
        gs = {"coherence_check_enabled": True,
              "coherence_threshold": float("nan"),
              "color_drift_sensitivity": float("nan")}
        ctrl, _ = _build_two_shot_controller(tmp_path, gs)
        coh_obj = SimpleNamespace(overall_coherence_score=0.2, color_drift=0.9)
        with patch("coherence_analyzer.assess_coherence", return_value=coh_obj):
            result = ctrl.diagnose_clip("s_1")
        tools = {r["tool"] for r in result.get("recommendations", [])}
        assert "regenerate" in tools, f"NaN coherence floor disabled the regen gate; recs={result.get('recommendations')}"
        assert "color_grade" in tools, f"NaN color_drift sensitivity disabled the drift gate; recs={result.get('recommendations')}"

    def test_valid_threshold_does_not_overfire(self, tmp_path):
        """non-regression: a finite floor with HIGH coherence must NOT fire the
        regen gate (proves the fix didn't make the gate always-on)."""
        gs = {"coherence_check_enabled": True,
              "coherence_threshold": 0.6,
              "color_drift_sensitivity": 0.3}
        ctrl, _ = _build_two_shot_controller(tmp_path, gs)
        coh_obj = SimpleNamespace(overall_coherence_score=0.95, color_drift=0.05)
        with patch("coherence_analyzer.assess_coherence", return_value=coh_obj):
            result = ctrl.diagnose_clip("s_1")
        tools = {r["tool"] for r in result.get("recommendations", [])}
        assert "regenerate" not in tools
        assert "color_grade" not in tools

    def test_invalid_coherence_result_is_not_recorded_as_clean_score(self, tmp_path, caplog):
        """Production-path pin: an invalid analyzer result must not become
        clean-looking coherence/color_drift scores in diagnose_clip.
        """
        gs = {
            "coherence_check_enabled": True,
            "coherence_threshold": 0.6,
            "color_drift_sensitivity": 0.3,
        }
        ctrl, _ = _build_two_shot_controller(tmp_path, gs)
        coh_obj = SimpleNamespace(
            overall_coherence_score=0.0,
            color_drift=0.0,
            valid=False,
            error="cannot read current_image: '/broken.png'",
        )

        with patch("coherence_analyzer.assess_coherence", return_value=coh_obj):
            with caplog.at_level("WARNING"):
                result = ctrl.diagnose_clip("s_1")

        scores = result.get("scores", {})
        assert "coherence" not in scores
        assert "color_drift" not in scores
        assert not {
            rec.get("tool") for rec in result.get("recommendations", [])
        }.intersection({"color_grade", "regenerate"})
        assert result.get("coherence_error") == "cannot read current_image: '/broken.png'"
        assert any(
            rec.levelname == "WARNING" and "coherence" in rec.getMessage().lower()
            for rec in caplog.records
        ), "invalid coherence must be observable at WARNING level"

    def test_invalid_coherence_result_is_not_passed_to_deep_advisory(self, tmp_path):
        """The same invalid coherence object must not reach ChiefDirector as a real score."""
        gs = {
            "coherence_check_enabled": True,
            "coherence_threshold": 0.6,
            "color_drift_sensitivity": 0.3,
            "advisory": {"deep_enabled": True},
        }
        ctrl, _ = _build_two_shot_controller(tmp_path, gs)
        coh_obj = SimpleNamespace(
            overall_coherence_score=0.0,
            color_drift=0.0,
            lighting_consistency=0.0,
            composition_similarity=0.0,
            recommendations=[],
            valid=False,
            error="cannot read current_image: '/broken.png'",
        )
        fake_settings = SimpleNamespace(anthropic_api_key="test-key", openai_api_key="")
        mock_cd_instance = MagicMock()
        mock_cd_instance.evaluate_generation_quality.return_value = {
            "diagnosis": "",
            "prompt_mutation": "",
            "mutation_focus": "",
            "decision": "KEEP",
            "visual_findings": "",
        }
        mock_cd_class = MagicMock(return_value=mock_cd_instance)

        with patch("coherence_analyzer.assess_coherence", return_value=coh_obj), \
             patch("config.settings.settings", fake_settings), \
             patch("llm.chief_director.ChiefDirector", mock_cd_class):
            result = ctrl.diagnose_clip("s_1", deep=True)

        assert result.get("coherence_error") == "cannot read current_image: '/broken.png'"
        assert mock_cd_instance.evaluate_generation_quality.called
        call_kwargs = mock_cd_instance.evaluate_generation_quality.call_args.kwargs
        assert call_kwargs["coherence_result"] is None

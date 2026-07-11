"""Stomp-simulation pins: operator-facing warnings must reach stderr.

The TF/Keras import chain — loaded whenever ``from deepface import DeepFace``
executes (identity/validator.py, domain/character_manager.py,
domain/continuity_engine.py, phase_c_vision.py) — inserts a blanket
('ignore', None, Warning, None, 0) filter at the FRONT of the global
warnings.filters. From that moment every bare ``warnings.warn(...)`` in the
process is invisible to operators, even under ``-W error``. ``pytest.warns``
stays green because it installs its own filter context — tests pass while
production is silent (the invisible-green class; ADR-066, verified
2026-07-11). Load-bearing operator warnings must therefore ALSO print to
stderr (the dual-channel pattern; reference implementation:
identity/validator._resolve_embed_model, pinned in
tests/unit/test_identity_embed_model.py on the P5 branch).

Each stomp test here simulates the TF filter with
``warnings.simplefilter("ignore")`` and asserts the message reaches stderr.
The warn-channel tests pin that the dual-channel refactor kept
``warnings.warn`` alive for the sites that had no existing pytest.warns
coverage (CI ``-W error`` runs and pytest.warns consumers rely on it).
"""
import sys
import warnings
from unittest.mock import MagicMock, patch

import pytest

from cost_tracker import CostTracker


def _tracker() -> CostTracker:
    return CostTracker(db_path=":memory:", budget_usd=None)


def _insert_poisoned_spend(tracker: CostTracker, video_id: str) -> None:
    """Write a non-finite cost row directly — log() coerces NaN/inf, so the
    poisoned-persistence path can only be reached via raw SQL (pre-fix DBs)."""
    tracker.conn.execute(
        "INSERT INTO cost_log (timestamp, provider, model, operation, cost_usd, video_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-07-11T00:00:00+00:00", "p", "m", "op", float("inf"), video_id),
    )
    tracker.conn.commit()


class TestCostTrackerStompSurvival:
    """cost_tracker.py — all four money-lane warnings are gate-degradation
    signals (cost-spent-nan-poison, unknown-model/API $0.00 undercount,
    fail-closed rehydrate); silently losing them is the money-loss class."""

    def test_nan_cost_coercion_reaches_stderr(self, capsys):
        tracker = _tracker()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # simulate the TF stomp
            tracker.log(provider="p", model="m", operation="op", cost_usd=float("nan"))
        err = capsys.readouterr().err
        assert "Non-finite cost_usd" in err, (
            "NaN-coercion warning silenced by an ignore-all warnings filter — "
            "it must also print to stderr"
        )
        # Behavior unchanged: coerced to 0.0, gate stays alive.
        assert tracker.spent_usd == pytest.approx(0.0)

    def test_unknown_llm_model_reaches_stderr(self, capsys):
        tracker = _tracker()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tracker.log_llm(
                model="totally-unknown-model-xyz", operation="op",
                input_tokens=5, output_tokens=5,
            )
        err = capsys.readouterr().err
        assert "Unknown model" in err

    def test_unknown_api_reaches_stderr(self, capsys):
        tracker = _tracker()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tracker.record_api_call("TOTALLY_UNKNOWN_API_XYZ")
        err = capsys.readouterr().err
        assert "Unknown API" in err

    def test_rehydrate_nonfinite_spend_reaches_stderr(self, capsys):
        tracker = _tracker()
        _insert_poisoned_spend(tracker, "vid-poison")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tracker.rehydrate_spent_usd_from_video("vid-poison")
        err = capsys.readouterr().err
        assert "Non-finite persisted spend" in err
        # Behavior unchanged: gate fails closed on poisoned persistence.
        assert tracker.spent_usd == float("inf")


class TestEnsembleStompSurvival:
    """llm/ensemble.py — a swallowed log_llm failure is uncounted LLM spend
    (the llmensemble-cost-uncounted CRITICAL family): the budget gate
    under-reads for the rest of the run."""

    def _ensemble_with_failing_tracker(self):
        from llm.ensemble import LLMEnsemble
        # __init__ wires API clients; _log_llm_usage touches only
        # self.cost_tracker, so skip construction.
        ens = object.__new__(LLMEnsemble)
        ens.cost_tracker = MagicMock()
        ens.cost_tracker.log_llm.side_effect = RuntimeError("db locked")
        return ens

    def test_cost_record_failure_reaches_stderr(self, capsys):
        ens = self._ensemble_with_failing_tracker()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ens._log_llm_usage("some-model", "op", 5, 5)
        err = capsys.readouterr().err
        assert "Failed to record LLM usage" in err

    def test_cost_record_failure_still_warns(self):
        ens = self._ensemble_with_failing_tracker()
        with pytest.warns(UserWarning, match="Failed to record LLM usage"):
            ens._log_llm_usage("some-model", "op", 5, 5)


class TestAlignmentStompSurvival:
    """audio/dialogue.py — the write-only sidecar notice (compute burned for
    no output while forced_alignment_enabled is on) must stay visible;
    warn-channel pin lives in tests/unit/test_alignment_warning.py."""

    def test_write_only_notice_reaches_stderr(self, tmp_path, capsys):
        import audio.dialogue as dialogue

        fake = MagicMock()
        fake.words = [MagicMock()]
        fake.provider = "whisper"

        def _settings(ctx, key, default=None):
            if key == "forced_alignment_enabled":
                return True
            return default if default is not None else "English"

        with patch.object(dialogue, "get_project_setting", side_effect=_settings), \
             patch("audio.alignment.align_audio_to_text", return_value=fake), \
             patch("audio.alignment.save_alignment_json", return_value=None):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dialogue._maybe_save_alignment(str(tmp_path / "out.mp3"))
        err = capsys.readouterr().err
        assert "no consumer" in err


class TestValidatorSiblingPin:
    """identity/validator._resolve_embed_model's STRUCTURAL warning is still
    bare on this branch; its dual-channel fix + real pin live on
    claude/clever-jepsen-d8074d (fd423ae5, ADR-066 — merge to main owed).
    Strict xfail per R-VERIFY-TIER(B): the moment that commit lands, this
    XPASSes strictly and CI forces the pin's removal (the pin in
    tests/unit/test_identity_embed_model.py takes over). Deliberately placed
    in THIS file — fd423ae5 does not touch it, so no merge conflict."""

    @pytest.mark.xfail(
        strict=True,
        reason="validator dual-channel fix is on claude/clever-jepsen-d8074d "
               "(fd423ae5, ADR-066); remove this pin when it lands on main",
    )
    def test_validator_structural_warning_reaches_stderr(self, monkeypatch, capsys):
        import identity.validator as v
        # config/__init__ re-exports the instance as `config.settings`,
        # shadowing the submodule on attribute access — go via sys.modules.
        settings_mod = sys.modules["config.settings"]

        class _S:
            identity_embed_model = "Buffalo_L"

        monkeypatch.setattr(settings_mod, "settings", _S())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert v._resolve_embed_model() == "Buffalo_L"
        err = capsys.readouterr().err
        assert "STRUCTURAL" in err and "Buffalo_L" in err


class TestWarnChannelPreserved:
    """The dual-channel refactor must not drop warnings.warn for the sites
    that previously had no pytest.warns pin (Unknown-API and the alignment
    notice are already pinned in their own files)."""

    def test_nan_cost_coercion_still_warns(self):
        tracker = _tracker()
        with pytest.warns(UserWarning, match="Non-finite cost_usd"):
            tracker.log(provider="p", model="m", operation="op", cost_usd=float("nan"))

    def test_unknown_llm_model_still_warns(self):
        tracker = _tracker()
        with pytest.warns(UserWarning, match="Unknown model"):
            tracker.log_llm(
                model="totally-unknown-model-xyz", operation="op",
                input_tokens=5, output_tokens=5,
            )

    def test_rehydrate_nonfinite_spend_still_warns(self):
        tracker = _tracker()
        _insert_poisoned_spend(tracker, "vid-poison")
        with pytest.warns(UserWarning, match="Non-finite persisted spend"):
            tracker.rehydrate_spent_usd_from_video("vid-poison")

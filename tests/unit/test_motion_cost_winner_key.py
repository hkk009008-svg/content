"""Regression: the motion cost record keys on the cascade WINNER, not the
requested primary (money-gate review 2026-07-11).

Before the fix, ``_finalize_motion_take`` recorded ``record_api_call(target_api)``
— so a SEEDANCE win behind a $0.50 KLING_NATIVE primary accumulated $0.50 while
fal billed $1.21-2.42, defeating both the pre-spend check and the post-hoc
``is_over_budget()`` gate (runaway-spend vector during a primary outage). The
fix mirrors the lipsync winner-keyed record: key on
``take["cascade_metadata"]["engine"]`` and, for SEEDANCE (per-second billed,
shot-type-dependent duration), pass an explicit duration-aware ``cost_usd``.

These tests call the unbound method with a MagicMock self — everything before
step 8 (validation, RIFE, mutation, checkpoint) is out of scope here.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _run_finalize(take_extra: dict, target_api: str = "KLING_NATIVE", shot_type: str = "action"):
    from cinema.shots.controller import ShotController

    mock_self = MagicMock()
    mock_self.cost_tracker.is_over_budget.return_value = False
    mock_self.project = {"id": "vid-test"}
    mock_self._maybe_auto_rife.return_value = "/tmp/out.mp4"

    take = {"id": "take1", "metadata": {}}
    take.update(take_extra)

    ShotController._finalize_motion_take(
        mock_self,
        scene={"id": "scene1"},
        shot={"id": "shot1"},
        take=take,
        video_path="/tmp/out.mp4",
        source_image="/tmp/src.png",
        target_api=target_api,
        cc={},
        settings={},
        resolved_shot_type=shot_type,
    )
    return mock_self


class TestMotionCostWinnerKey:
    def test_cascade_winner_key_and_duration_aware_cost(self):
        """SEEDANCE wins behind a KLING_NATIVE primary on an action shot →
        the record must carry SEEDANCE (not the primary) and the 8s cost
        (1.51/5s × 8s = 2.416), not the flat per-5s figure."""
        mock_self = _run_finalize({"cascade_metadata": {"engine": "SEEDANCE"}})
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call is not None, "cost record never happened"
        assert call.args[0] == "SEEDANCE", (
            f"cost recorded under {call.args[0]!r} — the cascade winner's key "
            f"must be used, not the requested primary"
        )
        assert call.kwargs.get("cost_usd") == pytest.approx(2.416), (
            f"8s action SEEDANCE clip must record duration-aware cost; got "
            f"{call.kwargs.get('cost_usd')}"
        )

    def test_seedance_portrait_records_4s_cost(self):
        """Portrait shots request 4s → cost 1.51/5 × 4 = 1.208."""
        mock_self = _run_finalize(
            {"cascade_metadata": {"engine": "SEEDANCE"}}, shot_type="portrait"
        )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "SEEDANCE"
        assert call.kwargs.get("cost_usd") == pytest.approx(1.208)

    def test_no_cascade_metadata_falls_back_to_target_api(self):
        """Primary won directly (no cascade_metadata) → record under
        target_api with the default table lookup (no cost_usd override)."""
        mock_self = _run_finalize({})
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "KLING_NATIVE"
        assert "cost_usd" not in call.kwargs, (
            f"non-SEEDANCE record must use the table default; got {call.kwargs}"
        )

    def test_non_seedance_winner_keys_winner_without_override(self):
        """A non-SEEDANCE cascade winner still keys on the winner."""
        mock_self = _run_finalize({"cascade_metadata": {"engine": "LTX"}})
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "LTX"
        assert "cost_usd" not in call.kwargs


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

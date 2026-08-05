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

from unittest.mock import MagicMock, patch

import pytest


def _run_finalize(
    take_extra: dict,
    target_api: str = "KLING_NATIVE",
    shot_type: str = "action",
    video_path: str = "/tmp/out.mp4",
):
    from cinema.shots.controller import ShotController

    mock_self = MagicMock()
    mock_self.cost_tracker.is_over_budget.return_value = False
    mock_self.project = {"id": "vid-test"}
    mock_self._maybe_auto_rife.return_value = video_path
    # Artifact indexing has its own focused suite. This cost-only fixture must
    # still implement the current two-value finalization contract.
    mock_self._finalize_take_artifact_version.side_effect = (
        lambda _shot_id, _kind, stored_take: (stored_take, None)
    )
    # Bind the REAL cost helpers — a MagicMock _motion_cost_kwargs unpacks
    # as empty kwargs and silently drops the duration-aware cost under test.
    mock_self._motion_cost_kwargs = (
        lambda engine, st, video_path="", cascade_metadata=None: (
            ShotController._motion_cost_kwargs(
                mock_self, engine, st, video_path, cascade_metadata
            )
        )
    )
    mock_self._record_billed_rejects = (
        lambda *a, **k: ShotController._record_billed_rejects(mock_self, *a, **k)
    )

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

    def test_ltx_winner_records_true_dispatched_duration(self):
        """LTX wins with the dispatcher's true duration in cascade_metadata →
        the record threads duration_seconds so CostTracker bills 0.06/s × 8s
        (fix-S4-money: the 8s shared default otherwise under-records ~33%
        against the flat 6s-floor table figure)."""
        mock_self = _run_finalize(
            {"cascade_metadata": {"engine": "LTX", "duration_s": 8}}
        )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "LTX"
        assert call.kwargs.get("duration_seconds") == 8

    def test_ltx_winner_records_provider_job_id_for_idempotency(self):
        """A recovered LTX result may be observed repeatedly; the exact
        provider job ID must reach CostTracker so only one invoice is logged."""
        mock_self = _run_finalize(
            {
                "cascade_metadata": {
                    "engine": "LTX",
                    "duration_s": 8,
                    "job_id": "job-winner-123",
                }
            }
        )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "LTX"
        assert call.kwargs.get("duration_seconds") == 8
        assert call.kwargs.get("provider_job_id") == "job-winner-123"

    def test_ltx_winner_without_duration_metadata_uses_flat_floor(self):
        """LTX win with no duration_s in metadata → no duration kwarg; the
        conservative flat table floor applies (never crash, never $0)."""
        mock_self = _run_finalize({"cascade_metadata": {"engine": "LTX"}})
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "LTX"
        assert "duration_seconds" not in call.kwargs

    def test_non_seedance_winner_keys_winner_without_override(self):
        """A non-SEEDANCE cascade winner still keys on the winner."""
        mock_self = _run_finalize({"cascade_metadata": {"engine": "LTX"}})
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "LTX"
        assert "cost_usd" not in call.kwargs

    def test_non_ltx_provider_job_id_reaches_cost_tracker(self):
        """The idempotency key is provider-generic, not LTX-specific."""
        mock_self = _run_finalize({
            "cascade_metadata": {
                "engine": "VEO_NATIVE",
                "job_id": "operations/veo-job-123",
            }
        })
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "VEO_NATIVE"
        assert call.kwargs.get("provider_job_id") == "operations/veo-job-123"


class TestGeminiOmniDurationProbeCost:
    """GEMINI_OMNI has no structured duration kwarg (duration is
    prompt-inferred/variable on this API) — unlike SEEDANCE's shot-type
    table lookup, the winner-path fix ffprobes the actual downloaded mp4.
    Fails open to the flat $0.56 table estimate on any probe error, a
    missing file, or a non-positive duration reading (never crash the
    finalize step, never record a $0.00 cost)."""

    def test_gemini_omni_winner_records_duration_aware_cost(self):
        """A real (existing) file + a mocked 7.3s probe reading records
        cost_usd = round(0.56/5.0*7.3, 4), not the flat $0.56 figure."""
        with patch(
            "cinema.shots.controller._probe_duration", return_value=7.3
        ) as mock_probe, patch(
            "cinema.shots.controller.os.path.exists", return_value=True
        ):
            mock_self = _run_finalize(
                {"cascade_metadata": {"engine": "GEMINI_OMNI"}},
                video_path="/tmp/gemini_out.mp4",
            )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "GEMINI_OMNI"
        assert call.kwargs.get("cost_usd") == pytest.approx(round(0.56 / 5.0 * 7.3, 4))
        mock_probe.assert_called_once_with("/tmp/gemini_out.mp4")

    def test_gemini_omni_probe_failure_falls_back_to_flat_table(self):
        """ffprobe raising (missing binary, corrupt file, malformed JSON —
        _probe_duration uses subprocess check=True) must NOT crash the
        finalize step; the record falls back to the flat table price."""
        with patch(
            "cinema.shots.controller._probe_duration", side_effect=RuntimeError("boom")
        ), patch("cinema.shots.controller.os.path.exists", return_value=True):
            mock_self = _run_finalize(
                {"cascade_metadata": {"engine": "GEMINI_OMNI"}},
                video_path="/tmp/gemini_out.mp4",
            )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "GEMINI_OMNI"
        assert "cost_usd" not in call.kwargs, (
            f"probe failure must fall back to the flat table default; got {call.kwargs}"
        )

    def test_gemini_omni_missing_file_falls_back_to_flat_table(self):
        """video_path pointing at a nonexistent file must skip the probe
        entirely (no subprocess call against a path that can't exist)."""
        with patch("cinema.shots.controller._probe_duration") as mock_probe:
            mock_self = _run_finalize(
                {"cascade_metadata": {"engine": "GEMINI_OMNI"}},
                video_path="/tmp/definitely_does_not_exist_gemini_omni_test.mp4",
            )
        call = mock_self.cost_tracker.record_api_call.call_args
        assert call.args[0] == "GEMINI_OMNI"
        assert "cost_usd" not in call.kwargs
        mock_probe.assert_not_called()

    def test_gemini_omni_reject_uses_flat_table_not_probe(self):
        """A GEMINI_OMNI billed-but-rejected attempt (another engine won)
        must NOT be probed — the shared output path may already have been
        overwritten by a later cascade hop, so probing it would misattribute
        the wrong engine's duration. The reject stays on the flat table
        price (deliberate winner-only scope, see plan risk note)."""
        with patch("cinema.shots.controller._probe_duration") as mock_probe:
            mock_self = _run_finalize({
                "cascade_metadata": {
                    "engine": "LTX",
                    "billed_attempts": ["GEMINI_OMNI", "LTX"],
                }
            })
        calls = mock_self.cost_tracker.record_api_call.call_args_list
        by_op = {c.kwargs.get("operation"): c for c in calls}
        assert "motion_generation_rejected" in by_op
        reject_call = by_op["motion_generation_rejected"]
        assert reject_call.args[0] == "GEMINI_OMNI"
        assert "cost_usd" not in reject_call.kwargs
        mock_probe.assert_not_called()


class TestBilledButRejectedRecording:
    """A provider bills once it returns a video; rejects (download fail /
    aspect backstop) previously accumulated $0 (money-gate finding
    2026-07-11). The dispatch notes billed attempts; the finalize record
    subtracts one winner occurrence and records the rest."""

    def test_rejected_attempt_recorded_alongside_winner(self):
        """KLING_3_0 billed then rejected, SEEDANCE won → two records: the
        winner (motion_generation) and the reject (motion_generation_rejected)."""
        mock_self = _run_finalize({
            "cascade_metadata": {
                "engine": "SEEDANCE",
                "billed_attempts": ["KLING_3_0", "SEEDANCE"],
            }
        })
        calls = mock_self.cost_tracker.record_api_call.call_args_list
        by_op = {c.kwargs.get("operation"): c for c in calls}
        assert "motion_generation" in by_op and "motion_generation_rejected" in by_op, (
            f"expected winner + reject records; got {calls}"
        )
        assert by_op["motion_generation"].args[0] == "SEEDANCE"
        assert by_op["motion_generation_rejected"].args[0] == "KLING_3_0"
        # Non-SEEDANCE reject uses the flat table figure (no override).
        assert "cost_usd" not in by_op["motion_generation_rejected"].kwargs

    def test_duplicate_winner_attempts_record_one_reject(self):
        """Retry pass can bill the same engine twice for one win — exactly
        one occurrence is the winner; the other is a duration-aware reject."""
        mock_self = _run_finalize({
            "cascade_metadata": {
                "engine": "SEEDANCE",
                "billed_attempts": ["SEEDANCE", "SEEDANCE"],
            }
        })
        calls = mock_self.cost_tracker.record_api_call.call_args_list
        rejected = [c for c in calls if c.kwargs.get("operation") == "motion_generation_rejected"]
        assert len(rejected) == 1, f"expected exactly one reject record; got {calls}"
        assert rejected[0].args[0] == "SEEDANCE"
        # SEEDANCE rejects carry the duration-aware cost like the winner does.
        assert rejected[0].kwargs.get("cost_usd") == pytest.approx(2.416)

    def test_no_billed_attempts_records_winner_only(self):
        """Clean primary win → exactly one record."""
        mock_self = _run_finalize({
            "cascade_metadata": {"engine": "SEEDANCE", "billed_attempts": ["SEEDANCE"]}
        })
        calls = mock_self.cost_tracker.record_api_call.call_args_list
        assert len(calls) == 1 and calls[0].kwargs.get("operation") == "motion_generation"

    def test_total_failure_helper_records_all_attempts(self):
        """Exhausted cascade with billed attempts (winner=None) → every
        attempt recorded as a reject (the generate_motion_take early-return
        path calls this helper before bailing)."""
        from cinema.shots.controller import ShotController
        mock_self = MagicMock()
        mock_self.project = {"id": "vid-test"}
        mock_self._motion_cost_kwargs.return_value = {}
        ShotController._record_billed_rejects(
            mock_self, ["SEEDANCE", "KLING_3_0"], None, "shot1", "action"
        )
        calls = mock_self.cost_tracker.record_api_call.call_args_list
        assert [c.args[0] for c in calls] == ["SEEDANCE", "KLING_3_0"]
        assert all(c.kwargs.get("operation") == "motion_generation_rejected" for c in calls)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

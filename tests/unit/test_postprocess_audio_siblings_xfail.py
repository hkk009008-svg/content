"""Postprocess-audio sibling coverage from the §3 completeness sweep.

``test_performance_take_as_final_metadata_is_resolved`` is now the live
regression for the fixed `perf-take-meta` row: performance takes approved as final
must expose their embedded-audio metadata to assembly.

``test_best_take_lipsync_credits_successful_postprocess_lipsync`` is now the live
regression for the fixed `lipsync-veto` row: a successful manual `lip_sync`
postprocess variant with `dialogue_audio_in_clip=True` must be visible to the
auto-approve final gate.

The storyboard-batch F1b sibling is now pinned in
``test_f2b_storyboard_mode.py``: dialogue-purpose shots are ineligible for the
batch and fall through to normal per-shot generation.
"""

from __future__ import annotations


def test_performance_take_as_final_metadata_is_resolved():
    """A performance take approved as the shot's final take must have its metadata
    (audio flags) seen by the assembler, exactly like a motion/postprocess take."""
    from cinema_pipeline import CinemaPipeline

    shot = {
        "approved_final_take_id": "take_perf",
        "motion_takes": [],
        "postprocess_variants": [],
        "performance_takes": [
            {"id": "take_perf", "kind": "performance",
             "metadata": {"has_dialogue": True, "audio_embedded": True}},
        ],
    }
    meta = CinemaPipeline._approved_take_metadata(shot)
    assert meta.get("audio_embedded") is True


def test_best_take_lipsync_does_not_credit_unmeasured_postprocess_audio():
    """A produced audio track is not evidence that lip sync was measurable."""
    from cinema.auto_approve import _best_take_lipsync

    takes = [
        {"id": "motion", "metadata": {"has_dialogue": True, "lipsync_score": 0.0}},
        {"id": "pp_lipsync", "metadata": {"action": "lip_sync", "dialogue_audio_in_clip": True}},
    ]
    score = _best_take_lipsync(takes)
    assert score == 0.0


def test_best_take_lipsync_credits_measured_postprocess_lipsync():
    from cinema.auto_approve import _best_take_lipsync

    takes = [
        {"id": "motion", "metadata": {"has_dialogue": True, "lipsync_score": 0.0}},
        {
            "id": "pp_lipsync",
            "metadata": {
                "action": "lip_sync",
                "dialogue_audio_in_clip": True,
                "lipsync_score": 0.9,
                "lipsync_validation_state": "PASS",
            },
        },
    ]
    assert _best_take_lipsync(takes) == 0.9

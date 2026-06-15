"""Postprocess-audio sibling coverage from the §3 completeness sweep.

``test_performance_take_as_final_metadata_is_resolved`` is the live regression
for the fixed `perf-take-meta` row: performance takes approved as final must
expose their embedded-audio metadata to assembly.  The `lipsync-veto` sibling is
also a live regression for the auto-approve subsystem.

Two further siblings (capability_scorecard blind-spot — MINOR, advisory display;
storyboard-batch F1b lipsync-skip — MAJOR, needs the _run_storyboard_scene
integration harness) are labeled test-infeasible-this-turn in the handoff rather
than pinned here.
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


def test_best_take_lipsync_credits_successful_postprocess_lipsync():
    """A successful postprocess lip_sync correction must lift the shot's lipsync gate
    score above the failed base motion take's 0.0 — otherwise the auto-approve 'final'
    gate vetoes a shot the operator already fixed."""
    from cinema.auto_approve import _best_take_lipsync

    takes = [
        {"id": "motion", "metadata": {"has_dialogue": True, "lipsync_score": 0.0}},
        {"id": "pp_lipsync", "metadata": {"action": "lip_sync", "dialogue_audio_in_clip": True}},
    ]
    score = _best_take_lipsync(takes)
    # Regression: the postprocess fix must be visible to the final gate.
    assert score >= 0.8

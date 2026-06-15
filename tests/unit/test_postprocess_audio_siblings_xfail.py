"""R-VERIFY-TIER(B) debt pins — out-of-scope audio-flag siblings surfaced by the
§3 completeness sweep (operator2 wf_69ba3ee7) and left UNFIXED in commit 1eec3cd.

Each is an agent-confirmed defect adjacent to the §3 audio-flag-propagation family
but in a DIFFERENT subsystem (auto-approve gate / review-approval + assembler take
resolution).  Per CLAUDE.md R-VERIFY-TIER(B), an agent-confirmed defect not fixed
this session ships an ``xfail(strict=True)`` pin so CI — not the next session's
agents — re-verifies, and the pin flips to a hard failure the moment the underlying
behavior is corrected (prompting removal of the pin).

director2 disposition is owed on the fix shape for both (reported in the §3
verification-report).  Two further siblings (capability_scorecard blind-spot —
MINOR, advisory display; storyboard-batch F1b lipsync-skip — MAJOR, needs the
_run_storyboard_scene integration harness) are labeled test-infeasible-this-turn in
the handoff rather than pinned here.
"""

from __future__ import annotations

import pytest


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


@pytest.mark.xfail(
    strict=True,
    reason="sibling wf_69ba3ee7 S2 (MAJOR): _best_take_lipsync (cinema/auto_approve.py:502) "
    "credits lipsync_score and audio_embedded but NOT dialogue_audio_in_clip, and a "
    "postprocess lip_sync variant carries no lipsync_score — so a shot whose sync was "
    "FIXED by a manual lip_sync correction is still vetoed on the base motion take's "
    "0.0 score. Fix = credit dialogue_audio_in_clip as a pass OR write lipsync_score "
    "onto the lip_sync postprocess variant (validate_lipsync_quality). director2 "
    "disposition owed (auto-approve subsystem, not §3's assembler scope).",
)
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
    # Today: returns 0.0 (the postprocess fix is invisible to the gate) → fails (xfail).
    assert score >= 0.8

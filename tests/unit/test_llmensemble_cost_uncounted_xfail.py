"""R-VERIFY-TIER(B) pin — llmensemble-cost-uncounted (W2:CRITICAL, money).

ROW: llmensemble-cost-uncounted
FILE: llm/ensemble.py:146 (competitive_generate) + domain/scene_decomposer.py:759
BUG: competitive_decompose_scene() accepts a gate-connected ``cost_tracker`` but on
  its SUCCESS path builds a bare ``LLMEnsemble()`` (scene_decomposer.py:759) and calls
  competitive_generate() WITHOUT threading the tracker.  LLMEnsemble has no
  cost-tracking at all (grep: zero cost_tracker/log_llm/log_api/record_api_call in the
  487-line module; usage is read at :286-293 only to print a cache diagnostic).  The
  tracker is forwarded ONLY to the fallback decompose_scene calls (:776/:809/:844) — so
  a SUCCESSFUL competitive run (the DEFAULT path; ``competitive_generation`` defaults
  True at cinema_pipeline.py:1017) leaks every LLM call.  ~3 LLM calls/scene (2
  candidates gpt-4o + claude-sonnet + 1 judge), scaling with scene count, invisible to
  PipelineCore.cost_tracker.spent_usd (write cost_tracker.py:306 / gate read :472).
  Same money-loss gate-source-mismatch family as costtracker-perf-uncounted (W1
  CRITICAL) and charmgr-cost-fresh-instance (W2).
  Confirmed: operator2 flag + coordinator wf_fb8c0c61-b18 (money-gate-reviewer +
  lane-v reachability + adversarial refuter — unanimous CONFIRM/CRITICAL; refuter
  failed to refute on all fronts).

FIX (not landed): thread the gate-connected cost_tracker into the LLMEnsemble that
  competitive_decompose_scene constructs (and have LLMEnsemble record per-call spend on
  it) — mirror the audio-T5 injection pattern.  After the fix the tracker reaches the
  ensemble -> this xpasses (strict=True) -> the lane converts/removes the pin.

NON-VACUITY + FLIP-CORRECT: the pin spies the LLMEnsemble that scene_decomposer builds
  and captures whether the gate-connected cost_tracker reaches EITHER its constructor OR
  competitive_generate().  Today scene_decomposer builds ``LLMEnsemble()`` with no
  tracker -> captured is None -> XFAIL.  After the threading fix the spy sees the shared
  tracker -> XPASS.  Deliberately DECOUPLED from token-math / log_llm internals: the
  recording SITE is undecided and EnsembleResult carries no usage, so a spend-assert pin
  would be shape-coupled to the unwritten fix (the lipsync-postproc-costkey mis-shape
  trap).  That the threaded tracker is actually USED to record spend is verified at
  operator Lane V via mutation, not pinned here.
"""

import unittest.mock as mock

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:CRITICAL:llmensemble-cost-uncounted llm/ensemble.py:146 + "
        "domain/scene_decomposer.py:759: competitive_decompose_scene builds a bare "
        "LLMEnsemble() on the success path and never threads the gate-connected "
        "cost_tracker; LLMEnsemble has zero cost-tracking; ~3 LLM calls/scene leak, "
        "invisible to the budget gate. Fix = thread the shared tracker into the "
        "ensemble (audio-T5 pattern); then the tracker reaches the ensemble and this "
        "xpasses."
    ),
)
def test_competitive_decompose_threads_tracker_into_ensemble(tmp_path):
    """The gate-connected cost_tracker must reach the competitive LLMEnsemble.

    Spies the LLMEnsemble scene_decomposer constructs and asserts the shared tracker
    reaches its constructor or competitive_generate(). Today neither happens (bare
    ``LLMEnsemble()``) -> XFAIL. After the threading fix -> XPASS.
    """
    import domain.scene_decomposer as sd
    from llm.ensemble import EnsembleResult
    from cost_tracker import CostTracker

    shared = CostTracker(db_path=str(tmp_path / "shared.db"), budget_usd=100.0)
    assert shared.spent_usd == 0.0, "precondition: shared tracker starts at $0"

    captured = {"init": "UNSET", "gen": "UNSET"}

    canned = EnsembleResult(
        winner_index=0,
        winner_content=[
            {
                "prompt": "a cinematic test shot",
                "camera": "zoom_in_slow",
                "visual_effect": "cinematic_glow",
                "target_api": "AUTO",
                "scene_foley": "ambient room tone",
                "characters_in_frame": ["c1"],
                "action_context": "standing",
            }
        ],
        scores=[1.0],
        reasoning="canned",
        candidates=[None],
        models_used=["gpt-4o"],
        judge_model="claude-sonnet-4-6",
    )

    class _SpyEnsemble:
        def __init__(self, *args, **kwargs):
            captured["init"] = kwargs.get("cost_tracker")

        def competitive_generate(self, *args, **kwargs):
            captured["gen"] = kwargs.get("cost_tracker")
            return canned

    # Safety net: if the success path ever falls back, do NOT touch the network.
    def _no_network_fallback(*args, **kwargs):
        return []

    scene = {
        "id": "s1",
        "title": "T",
        "action": "walks in",
        "duration_seconds": 5,
        "mood": "neutral",
    }
    characters = [{"id": "c1", "name": "Alice", "physical_traits": "tall"}]
    location = {"description": "a sunlit room"}
    global_settings = {"color_palette": "natural cinematic"}

    with mock.patch.object(sd, "LLMEnsemble", _SpyEnsemble), mock.patch.object(
        sd, "decompose_scene", _no_network_fallback
    ):
        sd.competitive_decompose_scene(
            scene,
            characters,
            location,
            global_settings,
            cost_tracker=shared,
        )

    threaded = (captured["init"] is shared) or (captured["gen"] is shared)
    assert threaded, (
        "gate-connected cost_tracker never reached the competitive LLMEnsemble "
        f"(init={captured['init']!r}, gen={captured['gen']!r}) — competitive planning "
        "spend is invisible to the budget gate"
    )

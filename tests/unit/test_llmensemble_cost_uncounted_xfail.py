"""Regression tests — llmensemble-cost-uncounted (W2:CRITICAL, money).

ROW: llmensemble-cost-uncounted
FILE: llm/ensemble.py:146 (competitive_generate) + domain/scene_decomposer.py:759
BUG FIXED: competitive_decompose_scene() accepts a gate-connected ``cost_tracker`` and
  must thread it into the success-path LLMEnsemble. LLMEnsemble must then record
  candidate/judge LLM token usage through ``CostTracker.log_llm()`` so the budget gate's
  in-process ``spent_usd`` accumulator sees planning spend.
"""

import types
import unittest.mock as mock


def test_competitive_decompose_threads_tracker_into_ensemble(tmp_path):
    """The gate-connected cost_tracker must reach the competitive LLMEnsemble.

    Spies the LLMEnsemble scene_decomposer constructs and asserts the shared tracker reaches
    its constructor or competitive_generate().
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

    # competitive_decompose_scene also calls research_engine.research_cinematography
    # (Tavily web search → api.tavily.com) for optional research context, independent
    # of LLMEnsemble/decompose_scene. Stub it so the test stays fully offline.
    with mock.patch.object(sd, "LLMEnsemble", _SpyEnsemble), mock.patch.object(
        sd, "decompose_scene", _no_network_fallback
    ), mock.patch("research_engine.research_cinematography", return_value=None):
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


def test_ensemble_openai_usage_records_on_shared_tracker(tmp_path):
    """A successful ensemble LLM call must move CostTracker.spent_usd."""
    from cost_tracker import CostTracker
    from llm.ensemble import LLMEnsemble

    shared = CostTracker(db_path=str(tmp_path / "shared.db"), budget_usd=100.0)
    ensemble = LLMEnsemble.__new__(LLMEnsemble)
    ensemble.cost_tracker = shared

    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=500_000),
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": true}'))],
    )
    create = mock.Mock(return_value=response)
    ensemble.openai_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )

    model, content = ensemble._generate_openai(
        "gpt-4o",
        "system",
        "user",
        json_mode=True,
        operation="llm_ensemble_candidate",
    )

    assert (model, content) == ("gpt-4o", '{"ok": true}')
    assert shared.spent_usd > 0.0


def test_prompt_optimizer_constructs_ensemble_with_shared_tracker(tmp_path, monkeypatch):
    """The default-on prompt optimizer sibling must thread the shared tracker too."""
    import llm.ensemble as ensemble_module
    from cost_tracker import CostTracker
    from llm.prompt_optimizer import optimize_shot_prompt

    shared = CostTracker(db_path=str(tmp_path / "shared.db"), budget_usd=100.0)
    captured = {"settings": "UNSET", "cost_tracker": "UNSET"}

    class _SpyEnsemble:
        def __init__(self, settings=None, cost_tracker=None):
            captured["settings"] = settings
            captured["cost_tracker"] = cost_tracker

        def competitive_generate(self, *args, **kwargs):
            from llm.ensemble import EnsembleResult

            return EnsembleResult(
                winner_index=0,
                winner_content={
                    "image_prompt": "a woman stands alone in an empty corridor",
                    "video_prompt": "slow dolly-in",
                    "purpose": "static_portrait",
                    "shot_type": "portrait",
                    "suggested_image_api": "FLUX_DEV",
                    "suggested_video_api": "AUTO",
                    "suggested_lipsync": None,
                    "negative_constraints": "plastic skin",
                    "identity_anchor": "Jane: dark hair, pale skin",
                    "camera": "85mm f/1.4",
                    "lighting": "cold rim light",
                    "color_palette": "cold blue",
                    "reasoning": "static portrait, character lead",
                },
                scores=[1.0],
                reasoning="canned",
                candidates=[None],
                models_used=["gpt-4o"],
                judge_model="claude-sonnet-4-6",
            )

    monkeypatch.setattr(ensemble_module, "LLMEnsemble", _SpyEnsemble)

    optimize_shot_prompt(
        user_input="a woman stands in a corridor",
        global_settings={"music_mood": "noir"},
        cost_tracker=shared,
    )

    assert captured["settings"] == {"music_mood": "noir"}
    assert captured["cost_tracker"] is shared

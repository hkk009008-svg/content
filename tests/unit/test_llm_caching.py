"""Verify cache_control is set on the system block for LLM calls.

We don't test that caching saves money (Anthropic's server-side concern);
we test that our outgoing requests opt into caching correctly. If
cache_control disappears from the system block in a future refactor,
this test catches it.

Covers the call sites in llm/ensemble.py:
  - _generate_anthropic (called by _generate_single with a claude-* model)
  - _judge (also calls _generate_anthropic with a literal system string)

Task A.3 will make these tests pass by converting the bare string system
parameter to a list of content blocks with cache_control={'type': 'ephemeral'}.
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch


def _make_fake_response() -> MagicMock:
    """Return a mock that looks like an Anthropic messages.create response."""
    block = MagicMock()
    block.text = "ok"
    # _generate_anthropic checks hasattr(block, 'text') and block.type
    block.type = "text"
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


def test_ensemble_system_block_has_cache_control():
    """The system message must be a list with cache_control={'type': 'ephemeral'}.

    Currently FAILS (red phase) because _generate_anthropic passes system as a
    bare string. Task A.3 will make this pass.
    """
    # anthropic/openai are lazy-imported inside LLMEnsemble.__init__, so we
    # patch them at the SDK module level (not at llm.ensemble.anthropic, which
    # doesn't exist yet as a module-level name).
    with patch("anthropic.Anthropic") as mock_anthropic_cls, \
         patch("openai.OpenAI"):
        fake_anthropic_client = MagicMock()
        fake_anthropic_client.messages.create.return_value = _make_fake_response()
        mock_anthropic_cls.return_value = fake_anthropic_client

        from llm.ensemble import LLMEnsemble
        ensemble = LLMEnsemble()

        # _generate_single routes to _generate_anthropic when model starts with "claude"
        ensemble._generate_single(
            model="claude-sonnet-4-20250514",
            system_prompt="You are a cinema director.",
            user_prompt="Write a short scene.",
        )

    assert fake_anthropic_client.messages.create.called, (
        "messages.create was never called — check that the model name routes to _generate_anthropic"
    )

    call_kwargs = fake_anthropic_client.messages.create.call_args.kwargs
    system_block = call_kwargs.get("system")

    # Anthropic accepts system as a string or a list of content blocks.
    # cache_control is only valid on the list form.
    assert isinstance(system_block, list), (
        f"system must be a list of content blocks to use cache_control; "
        f"got {type(system_block).__name__!r}: {system_block!r}"
    )
    assert len(system_block) >= 1, "system block list must not be empty"

    first_block = system_block[0]
    assert first_block.get("type") == "text", (
        f"first system block must be type=text; got {first_block!r}"
    )
    assert "cache_control" in first_block, (
        f"first system block missing cache_control; got keys {list(first_block.keys())}"
    )
    assert first_block["cache_control"] == {"type": "ephemeral"}, (
        f"cache_control must be {{'type': 'ephemeral'}}; got {first_block['cache_control']!r}"
    )


def test_judge_system_block_has_cache_control():
    """The _judge method's literal system string must also use cache_control.

    _judge calls _generate_anthropic directly with a hardcoded system string.
    Task A.3 will make this pass at the same time as the above test.
    """
    with patch("anthropic.Anthropic") as mock_anthropic_cls, \
         patch("openai.OpenAI"):
        fake_anthropic_client = MagicMock()
        # _judge parses the response as JSON — return something parseable
        judge_block = MagicMock()
        judge_block.text = '{"scores": [7.0, 8.0], "winner": 1, "reasoning": "B is better"}'
        judge_block.type = "text"
        judge_response = MagicMock()
        judge_response.content = [judge_block]
        judge_response.stop_reason = "end_turn"
        fake_anthropic_client.messages.create.return_value = judge_response
        mock_anthropic_cls.return_value = fake_anthropic_client

        from llm.ensemble import LLMEnsemble
        ensemble = LLMEnsemble()

        # _judge with a claude judge model calls _generate_anthropic internally.
        # Provide two candidates so the judge path (not the auto-win path) is exercised.
        ensemble._judge(
            candidates=["candidate A", "candidate B"],
            models=["gpt-4o", "claude-sonnet-4-20250514"],
            system_prompt="Pick the best cinema script.",
            judge_model="claude-sonnet-4-20250514",
        )

    assert fake_anthropic_client.messages.create.called, (
        "messages.create was never called from _judge — check judge_model routing"
    )

    call_kwargs = fake_anthropic_client.messages.create.call_args.kwargs
    system_block = call_kwargs.get("system")

    assert isinstance(system_block, list), (
        f"_judge system must be a list of content blocks; "
        f"got {type(system_block).__name__!r}: {system_block!r}"
    )
    assert len(system_block) >= 1, "system block list must not be empty"

    first_block = system_block[0]
    assert first_block.get("type") == "text", (
        f"first system block must be type=text; got {first_block!r}"
    )
    assert "cache_control" in first_block, (
        f"_judge system block missing cache_control; got keys {list(first_block.keys())}"
    )
    assert first_block["cache_control"] == {"type": "ephemeral"}, (
        f"cache_control must be {{'type': 'ephemeral'}}; got {first_block['cache_control']!r}"
    )

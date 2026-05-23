"""Verify cache_control is set on the system block for LLM calls.

We don't test that caching saves money (Anthropic's server-side concern);
we test that our outgoing requests opt into caching correctly. If
cache_control disappears from the system block in a future refactor,
this test catches it.

Covers all three production Anthropic call sites:
  - llm/ensemble.py:_generate_anthropic (via _generate_single with claude-* model)
  - llm/ensemble.py:_judge (also calls _generate_anthropic with literal system)
  - llm/chief_director.py:_call_llm (uses build_anthropic_system_blocks directly)

Post-A.3 follow-up: the chief_director test was added after the cross-cutting
review flagged that the third call site was unprotected by tests.
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch


def _make_fake_response(text: str = "ok") -> MagicMock:
    """Return a mock that looks like an Anthropic messages.create response.

    Args:
        text: The text content of the single content block in the response.
              Defaults to "ok" for generic calls; callers that need parseable
              JSON (e.g. the judge path) should pass the appropriate string.
    """
    block = MagicMock()
    block.text = text
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

    Patching notes: autospec=True is used so that any call to the mocked SDK
    with a wrong signature surfaces as a test error rather than silently
    succeeding. If a future SDK version makes autospec too restrictive (e.g.
    heavily dynamic __init__), fall back to spec=True and document here.
    """
    # anthropic/openai are lazy-imported inside LLMEnsemble.__init__, so we
    # patch them at the SDK module level (not at llm.ensemble.anthropic, which
    # doesn't exist yet as a module-level name).
    with patch("anthropic.Anthropic", autospec=True) as mock_anthropic_cls, \
         patch("openai.OpenAI", autospec=True):
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
    # Check only the type semantic — Anthropic may extend cache_control with
    # additional fields (e.g. ttl) and we must not break on those additions.
    assert first_block["cache_control"].get("type") == "ephemeral", (
        f"cache_control type must be 'ephemeral'; got {first_block['cache_control']!r}"
    )
    # Verify the text content survived the wrap (guards against A.3 accidentally
    # stripping text while converting to the list-of-blocks structure).
    assert first_block.get("text"), "first system block must have non-empty text"
    assert isinstance(first_block["text"], str), (
        f"first system block text must be str; got {type(first_block['text']).__name__}"
    )


def test_chief_director_system_block_has_cache_control():
    """ChiefDirector._call_llm must also pass cache_control on the system block.

    This is the third Anthropic call site in the codebase. It uses
    build_anthropic_system_blocks() directly (rather than routing through
    LLMEnsemble), so a regression here wouldn't be caught by the two
    ensemble-targeted tests above.

    Mock strategy: same `patch("anthropic.Anthropic", autospec=True)` as the
    ensemble tests, PLUS we patch `llm.chief_director.settings` so the lazy
    `_init_client` sees a truthy `anthropic_api_key` and constructs the mock
    client. Without that, _init_client returns None and _call_llm silently
    returns "" before reaching messages.create.
    """
    with patch("anthropic.Anthropic", autospec=True) as mock_anthropic_cls, \
         patch("llm.chief_director.settings") as mock_settings:
        mock_settings.anthropic_api_key = "fake-test-key"
        mock_settings.openai_api_key = None  # force the anthropic branch

        fake_anthropic_client = MagicMock()
        fake_anthropic_client.messages.create.return_value = _make_fake_response()
        mock_anthropic_cls.return_value = fake_anthropic_client

        from llm.chief_director import ChiefDirector
        cd = ChiefDirector(project={"id": "test"})
        cd._call_llm("You are ChiefDirector evaluating.", "user prompt here")

    assert fake_anthropic_client.messages.create.called, (
        "messages.create was never called — check that the anthropic_api_key "
        "patch made _init_client return a client"
    )

    call_kwargs = fake_anthropic_client.messages.create.call_args.kwargs
    system_block = call_kwargs.get("system")

    assert isinstance(system_block, list), (
        f"chief_director system must be a list of content blocks; "
        f"got {type(system_block).__name__!r}: {system_block!r}"
    )
    assert len(system_block) >= 1, "system block list must not be empty"

    first_block = system_block[0]
    assert first_block.get("type") == "text", (
        f"first system block must be type=text; got {first_block!r}"
    )
    assert "cache_control" in first_block, (
        f"chief_director system block missing cache_control; "
        f"got keys {list(first_block.keys())}"
    )
    # Check only the type semantic — Anthropic may extend cache_control with
    # additional fields (e.g. ttl) and we must not break on those additions.
    assert first_block["cache_control"].get("type") == "ephemeral", (
        f"cache_control type must be 'ephemeral'; got {first_block['cache_control']!r}"
    )
    # Verify the text content survived the wrap.
    assert first_block.get("text"), "first system block must have non-empty text"
    assert isinstance(first_block["text"], str), (
        f"first system block text must be str; got {type(first_block['text']).__name__}"
    )


def test_judge_system_block_has_cache_control():
    """The _judge method's literal system string must also use cache_control.

    _judge calls _generate_anthropic directly with a hardcoded system string.
    Task A.3 will make this pass at the same time as the above test.

    Patching notes: autospec=True is used so that any call to the mocked SDK
    with a wrong signature surfaces as a test error rather than silently
    succeeding. If a future SDK version makes autospec too restrictive (e.g.
    heavily dynamic __init__), fall back to spec=True and document here.
    """
    with patch("anthropic.Anthropic", autospec=True) as mock_anthropic_cls, \
         patch("openai.OpenAI", autospec=True):
        fake_anthropic_client = MagicMock()
        # _judge parses the response as JSON — pass parseable text via helper.
        judge_text = '{"scores": [7.0, 8.0], "winner": 1, "reasoning": "B is better"}'
        fake_anthropic_client.messages.create.return_value = _make_fake_response(text=judge_text)
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
    # Check only the type semantic — Anthropic may extend cache_control with
    # additional fields (e.g. ttl) and we must not break on those additions.
    assert first_block["cache_control"].get("type") == "ephemeral", (
        f"cache_control type must be 'ephemeral'; got {first_block['cache_control']!r}"
    )
    # Verify the text content survived the wrap (guards against A.3 accidentally
    # stripping text while converting to the list-of-blocks structure).
    assert first_block.get("text"), "first system block must have non-empty text"
    assert isinstance(first_block["text"], str), (
        f"first system block text must be str; got {type(first_block['text']).__name__}"
    )

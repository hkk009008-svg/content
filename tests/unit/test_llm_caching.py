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


def test_ensemble_constructor_timeouts():
    """All three LLMEnsemble clients must be constructed with explicit timeouts.

    - anthropic.Anthropic: timeout=120.0 (seconds, SDK default unit)
    - openai.OpenAI: timeout=120.0 (seconds, SDK default unit)
    - google.genai.Client: http_options with timeout=120_000 (milliseconds per
      google-genai SDK; verified installed: google-genai 2.6.0, HttpOptions.timeout
      is documented in milliseconds)

    Mocking strategy:
      - anthropic/openai: same patch("anthropic.Anthropic") / patch("openai.OpenAI")
        used in the caching tests above.
      - google.genai.Client: patched at "google.genai.Client" (module-level attribute).
        We also patch llm.ensemble.env_settings so gemini_api_key is truthy,
        triggering the conditional import + Client construction.
      - google.genai.types.HttpOptions: patched so we can capture the call args
        without requiring the full SDK to construct a real HttpOptions object.
    """
    import types as stdlib_types

    fake_env = stdlib_types.SimpleNamespace(
        anthropic_api_key="fake-anthropic",
        openai_api_key="fake-openai",
        gemini_api_key="fake-gemini",
        google_api_key="",
    )

    mock_http_options_instance = MagicMock()
    mock_http_options_cls = MagicMock(return_value=mock_http_options_instance)
    mock_genai_client_cls = MagicMock()

    with (
        patch("anthropic.Anthropic", autospec=True) as mock_anthropic_cls,
        patch("openai.OpenAI", autospec=True) as mock_openai_cls,
        patch("llm.ensemble.env_settings", fake_env),
        patch("google.genai.Client", mock_genai_client_cls),
        patch("google.genai.types.HttpOptions", mock_http_options_cls),
    ):
        import importlib
        import llm.ensemble
        importlib.reload(llm.ensemble)
        from llm.ensemble import LLMEnsemble
        LLMEnsemble()

    # Anthropic: timeout=120.0 (float seconds)
    assert mock_anthropic_cls.called, "anthropic.Anthropic constructor was not called"
    anthropic_kwargs = mock_anthropic_cls.call_args.kwargs
    assert anthropic_kwargs.get("timeout") == 120.0, (
        f"anthropic.Anthropic must be constructed with timeout=120.0; "
        f"got timeout={anthropic_kwargs.get('timeout')!r}"
    )

    # OpenAI: timeout=120.0 (float seconds)
    assert mock_openai_cls.called, "openai.OpenAI constructor was not called"
    openai_kwargs = mock_openai_cls.call_args.kwargs
    assert openai_kwargs.get("timeout") == 120.0, (
        f"openai.OpenAI must be constructed with timeout=120.0; "
        f"got timeout={openai_kwargs.get('timeout')!r}"
    )

    # Gemini: HttpOptions constructed with timeout=120_000 (milliseconds)
    assert mock_http_options_cls.called, (
        "google.genai.types.HttpOptions was not called — "
        "check that the gemini_api_key patch triggered the genai.Client branch"
    )
    http_options_kwargs = mock_http_options_cls.call_args.kwargs
    assert http_options_kwargs.get("timeout") == 120_000, (
        f"HttpOptions must be constructed with timeout=120_000 (ms); "
        f"got timeout={http_options_kwargs.get('timeout')!r}"
    )

    # genai.Client must receive the http_options instance
    assert mock_genai_client_cls.called, "google.genai.Client was not called"
    genai_kwargs = mock_genai_client_cls.call_args.kwargs
    assert genai_kwargs.get("http_options") is mock_http_options_instance, (
        f"genai.Client must be constructed with http_options=<HttpOptions instance>; "
        f"got http_options={genai_kwargs.get('http_options')!r}"
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

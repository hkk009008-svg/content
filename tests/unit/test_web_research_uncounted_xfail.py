"""R-VERIFY-TIER(B) pin — web_research-uncounted (W2:MAJOR, money).

BUG: web_research.run_with_tools() (web_research.py:122) constructs a fresh
throwaway CostTracker() inside the function at lines 172 and 212.  It accepts
no ``cost_tracker`` parameter, so the caller cannot supply the shared instance
that the budget gate reads.  Planning LLM spend from scene_decomposer.py:569
and dialogue_writer.py:101 — which both call run_with_tools() once per scene —
is therefore invisible to budget enforcement; cost scales with scene count and
is silently lost.

FIX (not landed): thread a ``cost_tracker`` parameter through run_with_tools()
and its callers (mirror the audio-T5 pattern).  When the fix lands:
  - run_with_tools(..., cost_tracker=shared_tracker) stops raising TypeError
  - the shared tracker's spent_usd > 0 after the call
  - this xfail flips XPASS (strict=True) -> delete this pin.
"""
import types
import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MAJOR:web-research-uncounted web_research.py:122,172,212: "
        "run_with_tools() has no cost_tracker param and constructs throwaway "
        "CostTracker() at lines 172 and 212; caller-supplied tracker never "
        "accumulates planning LLM spend.  Fix = add cost_tracker kwarg and "
        "route log_llm calls onto it (audio-T5 pattern); then this xpasses."
    ),
)
def test_run_with_tools_routes_spend_onto_shared_tracker(tmp_path):
    """run_with_tools must accept a cost_tracker and accumulate spend on it.

    A caller-supplied CostTracker is passed as ``cost_tracker``.  After the
    call, shared_tracker.spent_usd must be > 0, proving that the LLM spend
    landed on the shared instance rather than a fresh throwaway.

    Today (bug live): run_with_tools() raises TypeError because the param does
    not exist.  The xfail guard catches that failure.

    After the fix: the param is accepted, log_llm is called on the passed
    tracker, and spent_usd reflects the token cost.
    """
    from cost_tracker import CostTracker
    import web_research as wr

    # --- Minimal mock OpenAI client -------------------------------------------
    # Simulates a Phase-2-only path (no tools configured in test env) returning
    # a response with nonzero token usage so log_llm records nonzero cost.
    usage_obj = types.SimpleNamespace(prompt_tokens=500, completion_tokens=200)
    content_obj = types.SimpleNamespace(content="Research complete.")
    choice_obj = types.SimpleNamespace(message=content_obj)
    response_obj = types.SimpleNamespace(usage=usage_obj, choices=[choice_obj])

    class _FakeCompletions:
        def create(self, **kwargs):
            return response_obj

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    mock_client = _FakeClient()

    # --- Shared CostTracker (the one the budget gate reads) -------------------
    db = str(tmp_path / "test_cost.db")
    shared_tracker = CostTracker(db_path=db, budget_usd=100.0)
    assert shared_tracker.spent_usd == 0.0, "precondition: tracker starts at zero"

    # --- Call run_with_tools with the shared tracker --------------------------
    # BUG TODAY: this raises TypeError because the param does not exist.
    # AFTER FIX: the call succeeds and spend lands on shared_tracker.
    wr.run_with_tools(
        client=mock_client,
        model="gpt-4o",
        system_prompt="You are a researcher.",
        user_prompt="Research cinematic lighting.",
        cost_tracker=shared_tracker,  # the param that does not exist yet
    )

    # FIXED behaviour: the shared tracker accumulated the LLM spend.
    # gpt-4o is priced in PRICING so 500 input + 200 output tokens > $0.
    assert shared_tracker.spent_usd > 0.0, (
        "run_with_tools did not route its LLM spend onto the supplied "
        "cost_tracker; spent_usd is still 0.0 (web-research-uncounted bug)"
    )

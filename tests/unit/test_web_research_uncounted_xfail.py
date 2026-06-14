"""Regression test (was the R-VERIFY-TIER(B) xfail pin) — web_research-uncounted (W2:MAJOR, money).

BUG (now FIXED): web_research.run_with_tools() (web_research.py:122) constructed a
fresh throwaway CostTracker() inside the function at lines 172 and 212.  It accepted
no ``cost_tracker`` parameter, so the caller could not supply the shared instance
that the budget gate reads.  Planning LLM spend from scene_decomposer.py:569,
dialogue_writer.py:101 and style_director.py:105 — called once per scene/project —
was therefore invisible to budget enforcement; cost scaled with scene count and
was silently lost.

FIX (LANDED): threaded a ``cost_tracker`` parameter through run_with_tools() and
its callers (audio-T5 pattern: cinema_pipeline.py passes self.cost_tracker through
decompose_scene / competitive_decompose_scene / generate_dialogue /
generate_style_rules).  run_with_tools now routes log_llm onto
``(cost_tracker or CostTracker())``.  The strict-xfail pin XPASSED on the fix and
was converted to this live regression test (asserts the spend lands on the shared
tracker).
"""
import types


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

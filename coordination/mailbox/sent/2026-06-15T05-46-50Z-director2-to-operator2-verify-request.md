# Director2 → Operator2: Lane V request - llmensemble 4b81b31 and product-oracle repair c8c0d40

**When:** 2026-06-15T05:46:50Z · **From:** director2 (online)

Implementation commits:
- 4b81b31 fix(money): thread llm ensemble costs
- c8c0d40 fix(campaign): read product oracle artifacts from HEAD

Review target 1: llmensemble-cost-uncounted
- R-BRIEF: docs/superpowers/briefs/2026-06-15-llmensemble-cost-uncounted.md
- Scope: shared CostTracker threads into competitive_decompose_scene LLMEnsemble and the default-on prompt_optimizer sibling; LLMEnsemble records candidate/judge token usage through CostTracker.log_llm.
- Local evidence: tests/unit/test_llmensemble_cost_uncounted_xfail.py -> 3 passed; nearby money/ensemble suite -> 114 passed, 2 expected unknown-model warnings; ci_smoke OK.
- Operator2 checks requested: former strict xfail is live, shared tracker reaches ensemble, usage moves spent_usd, prompt_optimizer sibling is folded, no cross-cutting lock needed.

Review target 2: product-oracle FIX-5 repair after operator2 FAIL
- Prior FAIL: 3b21d74 / event 2026-06-15T05-38-17Z found git ls-tree did not discover logs/product-oracle-*.json and content validation read the mutable worktree.
- Repair: c8c0d40 lists committed logs/ entries and filters product-oracle names in Python; repo-owned artifact content is read via git show HEAD:<path>.
- Local evidence: tests/unit/test_wave_gate_check.py::test_wave2_discovers_valid_committed_product_oracle_artifact tests/unit/test_wave_gate_check.py::test_wave2_reads_committed_product_oracle_artifact_not_worktree -q -> 2 passed; tests/unit/test_wave_gate_check.py -q -> 13 passed; exact former --runxfail selector -> 1 passed; ci_smoke OK.
- Live gate evidence: scripts/wave_gate_check.py 2 still exits 1 as expected because Wave 2 lacks the real committed product-oracle artifact and has other open blockers; this repair only fixes committed-artifact discovery/content validation.

Please run independent Lane V. For the product-oracle target, verify against the two IMPORTANT findings in your FAIL report. For the money target, use the money-gate-reviewer lens if available.

Cursor at send: 2026-06-15T05:43:18Z

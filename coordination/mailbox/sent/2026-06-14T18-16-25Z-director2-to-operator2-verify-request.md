# Director2 → Operator2: web_research-uncounted f5a95ec — Lane V + money-gate-reviewer (impl != verifier)

**When:** 2026-06-14T18:16:25Z · **From:** director2 (online)

**Pair-B Wave-2 fix landed for independent verification (Lane V).** impl=director2 — you verify (Rule #9, impl != verifier). Read the §7 stub-contract spec (`docs/superpowers/specs/2026-06-15-wave2-stub-contract.md`) first.

## Row
`web_research-uncounted` (W2:MAJOR, money) — `web_research.py:122`. Same gate-source-mismatch family as costtracker-perf-uncounted / charmgr-cost-fresh-instance.

## Commit
`f5a95ec` (LOCAL, not pushed — 1 ahead of origin). Files: web_research.py, domain/scene_decomposer.py, domain/dialogue_writer.py, llm/style_director.py, cinema_pipeline.py, tests/unit/test_web_research_uncounted_xfail.py, ARCHITECTURE.md.

## Fix (audio-T5 pattern; verified sibling cinema_pipeline.py:552)
- `run_with_tools` (web_research.py): + `cost_tracker` kwarg; both throwaway `CostTracker().log_llm` sites (:176,:218 post-edit) -> `(cost_tracker or CostTracker()).log_llm`.
- `decompose_scene` / `competitive_decompose_scene` / `generate_dialogue` / `generate_style_rules`: accept + forward `cost_tracker` (kw-default None, backward-compat).
- `cinema_pipeline.py`: pass `self.cost_tracker` (property -> `_core.cost_tracker`, gate-connected) at all 6 planning call sites (513/521 dialogue, 961 style, 1020 competitive, 1026/1028/1048 decompose).

## Pin
`test_web_research_uncounted_xfail.py` — was strict-xfail; XPASSED on the fix; I converted it to a live regression test (asserts spend lands on the shared tracker). Verify non-vacuity by mutating the fix off (e.g. drop the kwarg forward) -> the regression test should go RED.

## Scope boundary (please scope-match, don't FAIL the deferral)
PIPELINE path only = pure Pair-B lane, NO lock. The 3 planning HTTP endpoints (web_server.py 1438/1479/1520) call these same functions but (a) are cross-cutting (W2-web_server.py.lock) and (b) have only conditional budget context (pre-run setup). DEFERRED to the web_server.py lock batch (with the http-* rows). This is an intentional director scope call, surfaced — not an incomplete fix.

## Suite / smoke
Full unit suite 2490p / 0f / 28xf (the +1 pass = converted regression). ci_smoke OK (I fixed 2 ARCHITECTURE.md anchors my new lines shifted: competitive_decompose_scene 624->626, _assemble_final 1323->1324).

## Reviewers to run
`lane-v-verifier` (cold-context, re-derive from diff + fresh test run) + `money-gate-reviewer` (gate-source-mismatch + silent-gate-degradation families). On GO -> coordinator reconciles open->verified; push is user-gated.

## Heads-up finding (separate row, not this fix)
The `lipsync-postproc-costkey` pin (`test_discovery_cost_xfail.py::test_postprocess_lipsync_costkey_resolves_nonzero`) is MIS-SHAPED: it calls `record_api_call("syncsov3")` directly with the bare name and asserts spent>0, but the correct fix is at the CALL SITE (controller.py prefixes `LIPSYNC_`). A correct fix will NOT flip that pin. Flagging for the coordinator/next director2 — that row needs a pin rework (call-site faithful), and its controller call site is deep (likely test-infeasible to invoke directly).

Cursor at send: 2026-06-14T17:42:12Z

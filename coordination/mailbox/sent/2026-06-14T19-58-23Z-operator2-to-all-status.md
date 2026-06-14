# Operator2 → All: operator2 wrapping (handoff) — web_research NITS shipped (77b97b9); lipsync/remux/charmgr queue CARRIED not in-flight

**When:** 2026-06-14T19:58:23Z · **From:** operator2 (online)

**operator2 WRAPPING (handoff) — verify queue CARRIED, not in-flight.** Don't wait on me for lipsync/remux this session; next operator2 picks them up.

**Shipped:** Lane V `web_research-uncounted` `f5a95ec` → **NITS** (`77b97b9`, report `18-44-02Z`). Core fix sound + gate-connected + non-vacuous. Two follow-ups owed to **director2/coordinator** before reconcile:
- **NIT-1 (one line, in-scope):** `scene_decomposer.py:844` `except`-fallback missing `cost_tracker=` (sibling of the threaded `:776`/`:809`).
- **NEW ROW (candidate-CRITICAL):** `LLMEnsemble.competitive_generate` primary-path leak — `llm/ensemble.py` zero cost tracking; DEFAULT competitive path, ~3 LLM calls/scene, no pin. **Do NOT reconcile `web_research-uncounted` to verified until this row is filed** (else the default-path leak is masked). money-gate=CRITICAL / lane-v=MAJOR.

**CARRIED to next operator2:** Lane V `lipsync-syncnet-nan` `1d30581` (vr 18:34Z) + `audio-remux-notimeout` `f108565` (vr 18:38Z); ratify `charmgr-cost-fresh-instance` provisional-CRITICAL (R-VERIFY-TIER); re-verify the `:844` nit-fix (§6c) → GO.

Detail: `docs/HANDOFF-operator2-2026-06-15-web-research-NITS-llmensemble-candidate-crit-row-queue-3.md`. Cursor at 18:19:13Z (2 verify-requests left unread = the owed queue).

Cursor at send: 2026-06-14T18:19:13Z

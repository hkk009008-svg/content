# Coordinator → All: Wave-2 ONLINE + triage map + 2 PROVISIONAL CRITICAL upgrades + idgate co-sign routing

**When:** 2026-06-14T18:19:13Z · **From:** coordinator (Session-12, online) · **Kind:** coordination

Coordinator is ONLINE (user "continue as coordinator" + "wave-2"). Reconciled the live tree; pushed the docs/logs stack (`eabda0f..dd6377a`, origin now `dd6377a`+). **Authored ZERO production code.** Trust git, not this prose.

## 1. User direction: campaign = WAVE-2 hardening
Realism (ADR-024 Route-B) is **PARKED** — director-1's sweep already banked the finding (Route A dead, man needs a LoRA). No pod burn authorized. **⚠ POD 07ed667 LEFT UP + BILLING — surfaced to the user to stop.** If you can stop it, do; otherwise it's user-gated.

## 2. Wave-2 triage map delivered — `logs/discovery-wf_f57f0d89-bc2.json`
Read-only workflow (`wf_f57f0d89-bc2`, 16 agents) verified ALL 26 open rows at HEAD, checked xfail-pin non-vacuity, clustered into **13 batches** with lock + co-sign routing + execution order. Highlights:
- **Execution order:** A2-idgate (CRITICAL) → B6-money-fresh-instance (charmgr CRITICAL) → B2-lipsync-veto (W2-auto_approve.py.lock) → B3-http-cluster (W2-web_server.py.lock, **after** auto_approve released; lexicographic) → A1-lora-decouple → … (full list in the discovery log).
- **Lock note:** auto_approve.py.lock < web_server.py.lock; acquire in lexicographic order, hold none while waiting (§6b). `coordination/locks/` is empty (no active claims) — exercise the claim/release flow when B2/B3 dispatch.

## 3. ⚠ TWO PROVISIONAL CRITICAL UPGRADES (MAJOR→CRITICAL) — coordinator-flagged, awaiting lane-operator ratification (R-VERIFY-TIER)
Campaign goes **0 → 2 provisional open CRITICAL**. Inventory updated; evidence + cited call paths in the discovery log.
- **`idgate-failopen` → CRITICAL.** Structural identity gate-bypass: on prod cloud `DEEPFACE_AVAILABLE=False` so the vision-LLM fallback is the PRIMARY identity path; any Anthropic API error → `default_pass` 0.7 PASSES every standard threshold (portrait .70/medium .65/wide .55/action .60) → forged `passed=True`. no-api-key path :260-263 identical. Existing pin tests only the observability half.
- **`charmgr-cost-fresh-instance` → CRITICAL.** Byte-identical to W1 CRITICAL `costtracker-perf-uncounted`: throwaway `CostTracker()` spend ($0.08-$0.40/char) escapes the gated accumulator; reachable via `POST /api/projects/<pid>/characters` without a running pipeline; `budget_usd=None` so the throwaway's own gate is dead too.

## 4. idgate-failopen co-sign routing (CROSS-LANE Tier-A) — coordinator routes
**Pair-A director** authors the brief (identity-gate policy = Pair-A content); **director2 (Pair-B)** must land a mailbox `verification-report` co-sign BEFORE dispatch (phase_c_vision.py is a §6b Pair-B module). Co-sign scope MUST cover: (a) ack severity now CRITICAL (gate-bypass, not just observability); (b) ratify the policy (fail-closed vs pass-with-warning on transient API error); (c) confirm fix covers both print sites :352/:262 + the no-api-key path :260-263.

## 5. Data-integrity flags folded into the inventory
- **`http-addchar-float-unguarded` scope INCOMPLETE (Rule#13):** 4 unguarded `float()` sites, not 2 — `api_add_character:567`, `api_add_object:1053`, `api_update_character:696`, `api_update_object:1154`. Brief MUST cover all 4 + isfinite NaN/inf guard or the pin passes vacuously.
- **`coherence-silent` caller-side MAJOR half** (`controller.py:2266-2270`, coh.valid never checked → color_grade suppression) has NO own row + NO pin. A4 brief must expand scope or file a new row.
- file:line drifts corrected (has-char-lora-hole :1006→:1060, secondary-lora-hole :1114→:1119) + others listed in the discovery log.

## 6. Reconciliation
- **`web_research-uncounted` → FIXED** (`f5a95ec`, director2). operator2 Lane V REQUESTED (`5438877`) — GO pending; I'll reconcile → verified on the operator GO. (My B6 batch — being executed organically; good.)
- Wave-1 stays MET 8/8. Wave-2 gate UNMET `{open:26, verified:2}`.

## 7. ⚠ PROCESS: ci_smoke flickering RED — ARCHITECTURE.md anchors lagging fast quality_max.py churn
The A1-lora-decouple refactor (quality_max.py) is moving def lines faster than the ARCHITECTURE.md anchors are being updated → `ci_smoke.py` is RED at HEAD (`_inject_secondary_loras` 579→607, `_assemble_max_prompt` 493→517, `_inject_secondary_faceswap` 637→665). **Per R-START, update the ARCHITECTURE.md anchors IN THE SAME COMMIT that moves the def** (or a `docs:` prep commit) — otherwise the wave cannot cleanly close on a green gate. Coordinator will NOT whack-a-mole anchors mid-burst; lane owners fix-on-touch. `.venv/bin/python scripts/check_doc_claims.py --fix` is the tool.

Cursor at send: read through 2026-06-14T18:19:13Z (consumed director-1 17:42Z, operator2 17:40Z, director2→operator2 web_research verify-request).

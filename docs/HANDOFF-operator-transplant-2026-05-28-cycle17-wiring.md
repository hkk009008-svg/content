# Operator Handoff — Context Transplant 2026-05-28 cycle-17 WIRING + GitNexus audit

**From:** Operator-seat (cycle-17 Phase-1 close → joint wire-all-unwired task → GitNexus phantom-rule audit)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `23ba766` == local; **23 commits ahead of origin** (push user-gated); tree clean.
**Supersedes:** [HANDOFF-operator-transplant-2026-05-28-cycle17-phase1.md](HANDOFF-operator-transplant-2026-05-28-cycle17-phase1.md) (Phase-1 close) as the current operator pickup doc.
**Companion docs:** [BRIEF-comprehensive-test-v2.0-2026-05-28.md](BRIEF-comprehensive-test-v2.0-2026-05-28.md) · [divergence-ledger.md](divergence-ledger.md) · [TIER-F-AUDIT-cycle17-2026-05-28.md](TIER-F-AUDIT-cycle17-2026-05-28.md) · [CLAUDE.md](../CLAUDE.md) Rules #1-#16.

---

## TL;DR (2 min)
Since Phase-1 close, two big threads ran, both with the director concurrent:

1. **Joint "wire all implemented-but-unwired features"** (user-directed to both seats). Built the **true-complete inventory** (~34 items; coverage caveat closed), **converged a partition** with the director, and wired the operator's clean share. **`img2img_denoise` + `intent_notes` are now fully wired** (end-to-end). The rest of the operator's share is **user-decisions, not wires** (see §A). The director is grinding their controller.py-centric cluster (dialogue done; storyboard F2 closing the toggles; image-routing/upscale/cost-cluster next).

2. **GitNexus phantom-rule audit** (user: "is this true?" → "yes, draft the fix"). Verified that the protocol's most-mandated discipline (`MUST gitnexus_impact`) **has 0 tool calls across 67 sessions** and was **never even configured** — plus a 2nd phantom (the auto-refresh hook doesn't exist). **Proposal staged to director** (`23ba766`) to fix it. **OPEN — director to ship** (protocol-layer; not operator's to edit). User leans Option A (remove the integration, codify grep/Read).

**Baseline:** pytest `1103` passed / 3 skipped; §15 smoke OK (verified clean tree at handoff). **GPU/pod still DOWN** → Phase-2 Tier C / C-D4 pod-apply / Tier D still PARKED.

---

## §A. Joint wire-all-unwired task

### The complete inventory (~34 items; both audits' caveat closed)
Two operator sweeps (exhaustive + deeper) + the director's `suggested_video_api` find. Full detail in the mailbox convergence event `2026-05-28T08-43-31Z` + the deeper-pass net-new (img2img_denoise, intent_notes, _build_transition_prompt, CascadeMetadata diagnostics). Headline categories: 8 inert `api_engines` toggles · Suno V5 · Topaz upscale · HiDream/SD3_5_LARGE/SUPIR/CCSR engines · cost-attribution cluster (lipsync/LLM/native-motion + provider_for) · ~12 dead utils · img2img_denoise · intent_notes · evaluate_generation_quality (B2).

### Converged partition (director-consented `21ad506`)
- **Operator (disjoint clean files):** `intent_notes` (prompt_optimizer) · `img2img_denoise` (workflow_selector/phase_c_assembly/quality_max) · research fns · B2 disposition.
- **Director (controller.py-centric):** dialogue (F1a/F1b) · storyboard (F2a/F2b) · image-engine routing (C3 HiDream/C1 SD3_5_LARGE) · `evaluate_generation_quality` call-site · upscale dispatch (Topaz/SUPIR/CCSR) · the 8 `api_engines` toggles · `_build_transition_prompt` · cost-attribution cluster.
- **Joint/larger:** cost cluster, `validate_lora_quality` (~100 LoC stub).
- Cross-seat split convention: e.g. intent_notes — operator did prompt_optimizer param+incorporation, director did the controller.py:416 one-liner.

### Operator wiring — DONE
| Item | Commits | Status |
|---|---|---|
| `img2img_denoise` (all 3 paths) | `585554a` (std+prod, impl) + `c721aa9` (max-tier, operator) | ✅ wired + 131 tests |
| `intent_notes` (end-to-end) | `8f887f1` (operator prompt-side) + `2e565f4` (director call-site) | ✅ wired + 34 tests |

### Operator remaining — NOT wires; need USER decisions (the honest finding)
- **B2 `evaluate_generation_quality`** — dead 171-LOC post-gen quality evaluator; wiring = a **per-generation LLM eval cost** + call-site in director's controller.py. **User decision: wire-with-cost vs leave-dead.** (Director consented operator flags it; flagged — awaiting user.)
- **research fns (3):** `research_location_visual` = wireable in principle but needs a "location reference image" slot in the image-gen flow that doesn't exist (build-out, not a wire); `scrape_technique_reference` = no URL source; `research_trending_topics` = no ideation phase. **Recommend: leave all 3 as future-feature stubs OR build out research_location_visual — user call.** (Per the agreed nuance: don't fabricate artificial call-sites.)
- **Realization:** "wire all" largely RESOLVED — the cleanly-wireable operator items are wired; the remainder is half-built features needing build-out decisions (user) + the director's in-progress cluster.

### Director cluster progress (for context; watch + Lane V)
`a7c5816`→`933c794`→`561ad6b` dialogue F1a/F1b · `51e6886`→`f9af2de`→`8354c9a` storyboard F2a/F2b (**`f9af2de` closed F-A.1 storyboard_mode toggle**) · `2e565f4` intent_notes call-site · `9d52019` api_engines defaults note. **Still coming:** rest of the 8 toggles, image-routing (C3/C1), upscale (Topaz/SUPIR/CCSR), cost cluster.

### Lane V history (operator's high-value role — KEEP DOING)
- **#14** C-D4 setup_runpod.sh (elected) → director closed F1+F2 (`e82524c`, Rule #15).
- **#18** on director's F1a → caught a **CRITICAL** (dialogue_close_up resolved to KLING_NATIVE, not VEO_NATIVE — F1a was a no-op for the main dialogue case; self-review missed it; operator traced the ranking + confirmed). Director fixed (`561ad6b`). **#18.5** re-pass → ✅ clean.
- Operator Lane Bs (img2img, intent_notes) self-reviewed (small, test-covered).
- **Pending Lane V (not yet done):** director's `f9af2de`/`8354c9a` (F2b storyboard) + `2e565f4` (intent_notes call-site — verify it's `intent_notes=shot.get("intent_notes","")` at controller.py:416). Low-priority but the role caught a real CRITICAL — keep it up as the cluster lands.

---

## §B. GitNexus phantom-rule audit — OPEN (director to ship)

**Verified** (`23ba766` proposal has the full ADR-013-compliant evidence): `gitnexus_*` MCP tool calls = **0 across 67 sessions** (calibrated vs `"name":"Bash"`=4482); **never configured** (no `.mcp.json`/settings/dep); the "PostToolUse auto-refresh hook" CLAUDE.md claims is **also phantom** (no hook); the 77MB `.gitnexus` index is **246 commits stale**; the mandate block (`CLAUDE.md:1-101` + `AGENTS.md:1-101`) is **auto-injected by `npx gitnexus`** itself. grep/Read carried all 67 sessions. §10 unwired-feature pattern in the protocol layer.

**Proposed fix (drafted in the proposal):** **Option A (recommended + user-leaning):** delete the auto-gen blocks + stale index + (optionally) the gitnexus skills, stop running `analyze`, replace with a hand-authored "grep callers + Read before editing" note (the de-facto method). **Option B:** configure the MCP server + wire it for real (bigger lift). **Option C** unstable (block regenerates).

**Status: OPEN.** This is a **cross-cutting protocol change → director ships** `CLAUDE.md`/`AGENTS.md` + authors the ADR (`DECISIONS.md` director-only). Operator drafted; **user endorsed surfacing + leans A/C.** Next operator: if the director hasn't shipped it, it's still pending; the proposal `2026-05-28T10-02-08Z` has everything. A `memory-candidate` (the meta-lesson: docs drift toward aspiration; `mcp__server__tool` naming makes usage grep-auditable) is also recommended but director-owned.

---

## What's OPEN (cold-start priorities)
1. **GitNexus proposal** — director to ship (Option A); operator drafted. If shipped, verify CLAUDE.md/AGENTS.md no longer mandate dead tools.
2. **B2 + research fns** — user decisions (wire-with-cost / build-out / leave-stub). Operator flagged; awaiting user.
3. **Director cluster Lane V** — keep Lane-V'ing director feat/fix commits as the cluster lands (the role caught the F1a CRITICAL).
4. **PARKED (GPU/pod down):** Phase-2 Tier C-rerun · C-D4 pod-apply + A9.5 re-probe · Tier D.
5. **Push** — 23 commits ahead of origin; user-gated.

## Cold-start checklist
```bash
cat STATE.md                                              # machine truth
# Rule #8: if STATE.md shows operator unread ≥1, surface + process first.
.venv/bin/python scripts/ci_smoke.py                      # expect OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1   # expect 1103 passed, 3 skipped
git log --oneline -15
git rev-list --count origin/main..HEAD                    # 23 (push user-gated)
cat coordination/mailbox/seen/operator.txt                # T09:32:41Z
ls coordination/mailbox/sent/ | sort | tail -8
```
**Read order:** STATE.md → mailbox unread → THIS doc → the `23ba766` GitNexus proposal → the `08:43:31Z` convergence (inventory+partition) → divergence-ledger → CLAUDE.md.
**Pre-Write/commit discipline (Rules #4+#7):** director is concurrent + parallel-editing controller.py/motion_render/phase_c. **ALWAYS surgical-stage (named files only; never `git add -A`)** — their WIP is often live in the tree. Re-run `git log -5` + `ls mailbox/sent | tail -3` before any state-asserting Write/commit.

## Mailbox + cursor
| Cursor | Value |
|---|---|
| operator.txt | **T09:32:41Z** (consumed director consent `21ad506`) |
| director.txt | T09:23:20Z (per their last event) |
No unread operator events at handoff. Director's recent activity is code commits (not mailbox events). Latest operator sends: `09:43:57Z` (intent_notes arg + img2img done), `10:02:08Z` (GitNexus proposal).

## Metrics
- **Pytest:** `1103`/3 (was 973 cycle-16 → 1005 Phase-1 → grew with dialogue/storyboard/img2img/intent_notes tests). §15 smoke OK.
- **Subagents this session:** ~13 (3 Phase-1 implementers + Phase-1 Lane Vs + C-D4 LV + exhaustive sweep + deeper sweep + director-wire Lane V #18/#18.5 + img2img/intent_notes implementers).
- **23 commits ahead of origin** (push user-gated). GPU work parked.

---
Signed,
Operator-seat — 2026-05-28 cycle-17 wiring + GitNexus audit: joint wire-all task (inventory ~34 + converged partition; operator wired img2img_denoise + intent_notes end-to-end; B2/research = user decisions); Lane V #18 caught the F1a dialogue CRITICAL (director fixed 561ad6b, #18.5 ✅); GitNexus phantom-rule verified (0 calls/67 sessions, never configured) + correction proposal staged (`23ba766`, director to ship, user leans A). HEAD `23ba766`, 23 ahead, tree clean. GPU parked. Cursor T09:32:41Z.

# Operator Handoff — Context Transplant 2026-05-28 cycle-17 POST-MID

**From:** Operator-seat (cold-pickup → Lane V #19 → user B2/research decisions → research_location_visual Part 1 → director re-sync)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `d28474e`; **0 ahead of origin** (`origin/main == d28474e` — user pushed everything); tree clean except untracked `docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md` + `logs/`.
**Supersedes:** [HANDOFF-operator-transplant-2026-05-28-cycle17-wiring.md](HANDOFF-operator-transplant-2026-05-28-cycle17-wiring.md) as the current operator pickup doc.
**Companion docs:** [HANDOFF-director-transplant-2026-05-28-cycle17-mid.md](HANDOFF-director-transplant-2026-05-28-cycle17-mid.md) (director pickup — **partially superseded; director is ACTIVE and has shipped past it**) · [BRIEF-comprehensive-test-v2.0-2026-05-28.md](BRIEF-comprehensive-test-v2.0-2026-05-28.md) · [DECISIONS.md](../DECISIONS.md) ADR-016/017 · [CLAUDE.md](../CLAUDE.md) Rules #1-#16.

---

## TL;DR (2 min)
Cold-picked-up at `7bded26` (both seats had transplanted). Did the operator loop: cleared the pending Lane V, surfaced two user decisions, shipped one of them. **Mid-session the director came back online** and ran a doc-backlog-clear + started their sweep — caught via the Rule #7 pre-commit re-verify, NOT by assumption (I'd wrongly read the transplant handoff as "offline"). No conflicts (git serialized on disjoint files). Net this session:

1. **Lane V #19** on storyboard F2b (`b906704..8354c9a`) → 2 MINOR-advisory findings → director disposed both (F2b-1 → ADR-017 cost policy; F2b-2 `/tmp` collision → fixed `ca9f090` via Rule #15). The cold second-opinion caught a real (narrow) one again.
2. **`intent_notes`** call-site verified clean (Lane A) — closed.
3. **User decided B2 + research fns** (via AskUserQuestion): B2 = wire flag-gated GPU-back (director cluster); research_location_visual = BUILD.
4. **`research_location_visual` Part 1 SHIPPED** (`8376784` + ARCH §7.7.4 `f55e376`): flag-gated research→download→persist into existing `reference_images` slot, default-off, 8 tests. **Part 2 (GPU-gated consumption) handed to director.**
5. Director shipped **GitNexus phantom-rule removal** (`00736ea`/ADR-016, Option A) — the OPEN item is CLOSED; **the `gitnexus_*` mandate + counter-bump sub-protocol are GONE from CLAUDE.md/AGENTS.md** (method is now grep/Read). I consented to the counter-bump bullet removal (Rule #11).

**Baseline:** pytest **`1117 passed / 3 skipped`** (verified at `d28474e`: `1117 passed, 3 skipped ... in 28.91s`); §15 smoke **OK**. **GPU/pod still DOWN** → Phase-2 Tier C / C-D4 pod-apply / Tier D PARKED.

---

## §A. What this operator session shipped
| Item | Commit(s) | Status |
|---|---|---|
| Lane V #19 verification-report (storyboard F2b) | `f848fe2` | ✅ director disposed both findings |
| research_location_visual **Part 1** (flag-gated fetch→download→persist) | `8376784` (impl) | ✅ 8 tests, 1117/3, smoke OK; self-reviewed |
| ARCH §7.7.4 doc-sync (Lane D) for Part 1 | `f55e376` | ✅ |
| Coordination reply (ACK closures + Rule #11 consent + relay user decisions) | `934b7eb` | ✅ |

**research_location_visual — the refined finding (the cycle17-wiring handoff premise was STALE):** the `reference_images` SLOT already exists (`domain/location_manager.py`, populated via upload); the canonical research-wiring pattern already exists (`research_cinematography` @ `scene_decomposer.py:503`/`style_director.py:47`/`music.py:303`); the REAL gap is the gen-time CONSUMER — `get_location_reference` is dead; a location influences gen today via `prompt_fragment` text + seed only. So Part 1 was a real *wire* (mirroring the upload-storage shape), and **Part 2 = build the consumer** (IP-Adapter/img2img conditioning, GPU-gated, director's image-gen cluster).

**Two Part-1 follow-ups handed to director (Part-2 owner):** (1) **on-switch coherence** — the `location_research` flag default is declared in `api_engine_defaults` (`/api/config`) but read at runtime from `project["global_settings"]["location_research"]`; the settings-save path must target `global_settings` for opt-in to work e2e (ARCH §7.7.4 records this). (2) **nit** — `_download_url_to_file` has no response-size cap + hardcoded `.jpg` ext.

## §B. Concurrent director activity (landed this session — context, watch + Lane V)
`00736ea` GitNexus removal/ADR-016 · `ca9f090` F2b-2 fix (Rule #15) · `c0d5543` ADR-017 (storyboard B-integrate + F2b-1 cost policy) · `fbeda3c` director decision event (T10:49:19Z) · **`d28474e` feat(image-routing) — wire optimizer `suggested_image_api`→HiDream gate (C3; `controller.py` +5 / new 79-line test). ← NOT YET LANE-V'd.**
Director's remaining sweep (their words): upscale dispatch (Topaz/SUPIR/CCSR), the 8 inert api_engine toggles, `_build_transition_prompt`, cost-attribution cluster. + GPU validation (pod down).

---

## What's OPEN (cold-start priorities)
1. **Lane V on `d28474e`** (director's image-routing C3 HiDream feat) — the top pending operator item; fresh director `feat`, not yet independently reviewed. Coalesce with any further image-routing/upscale commits per Rule #9 CC-1 if they've landed.
2. **Keep Lane-V'ing the director's sweep** as it lands (upscale / toggles / `_build_transition_prompt` / cost cluster). The role caught F2b-2 + (cycle-17 earlier) the F1a dialogue CRITICAL — high value.
3. **B2 wire + research_location_visual Part 2** — USER-decided, director-cluster + GPU-back (NOT operator-actionable solo). B2 = adaptive-retry brain, cost is **per-FAILURE** not per-gen (`chief_director.py:355` early-ACCEPT). Part-1 follow-ups ride with Part 2.
4. **PARKED (GPU/pod down):** Phase-2 Tier C-rerun · C-D4 pod-apply + A9.5 re-probe · Tier D.
5. **Push** — currently 0 ahead (user pushes periodically); re-check `git rev-list --count origin/main..HEAD` — push is user-gated.

## Cold-start checklist
```bash
cat STATE.md                                              # machine truth (hook-derived; may miscount mailbox — verify vs filesystem)
# Rule #8: if STATE.md shows operator unread ≥1, surface FIRST, then verify against the cursor (it counts your OWN outbound too — filesystem wins).
.venv/bin/python scripts/ci_smoke.py                      # expect OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1   # expect 1117 passed, 3 skipped
git log --oneline -15
git rev-list --count origin/main..HEAD                    # push user-gated
cat coordination/mailbox/seen/operator.txt                # T10:49:19Z
ls coordination/mailbox/sent/ | sort | tail -8
```
**Read order:** STATE.md → mailbox unread → THIS doc → director's `2026-05-28T10-49-19Z` decision (already consumed; for context) → my `2026-05-28T11-03-16Z` coordination → DECISIONS.md ADR-016/017 → CLAUDE.md.

**⚠️ Two standing cautions:**
- **Director is ACTIVE + concurrent.** Do NOT assume "offline" from a transplant handoff — this session's lesson: I dispatched + committed under a stale "offline" read; **Rule #7 pre-commit re-verify** is what caught it. ALWAYS `git log -5` + `ls mailbox/sent | tail` immediately before any dispatch/state-asserting Write/commit. Surgical-stage named files ONLY (never `git add -A`) — director parallel-edits `controller.py`/`motion_render.py`/`web_server.py`.
- **GitNexus is GONE** (ADR-016, `00736ea`): no `gitnexus_*` mandate, no counter-bump sub-protocol, no `.gitnexus` index, no skills. The CLAUDE.md "impact analysis before editing" method is now **grep callers + Read**. If your loaded CLAUDE.md still shows the GitNexus block, it's a stale in-context copy — trust the file on disk.

## Mailbox + cursor
| Cursor | Value |
|---|---|
| operator.txt | **T10:49:19Z** (consumed director's GitNexus/memory/Lane-V-19 decision) |
| director.txt | T10:24:19Z-ish (per their last event; they consumed through my `10-24-58Z` Lane V #19) |
No unread operator events at handoff. Latest operator sends: `11-03-16Z` (coordination reply). Director's recent activity is code commits (`d28474e`), not mailbox events.

## Metrics
- **Pytest:** `1117`/3 (1103 at pickup → +F2b/intent already in → +8 location-research → +6 image-routing). §15 smoke OK.
- **Subagents this session:** 3 (Lane V #19 spec + code-quality reviewers; research_location_visual Part-1 implementer).
- **0 ahead of origin** at handoff (user pushed through `d28474e`). GPU work parked.

---
Signed,
Operator-seat — 2026-05-28 cycle-17 post-MID: cold-pickup; Lane V #19 (both findings director-disposed); intent_notes verified; user decided B2 (wire flag-gated GPU-back) + research_location_visual (BUILD → Part 1 shipped `8376784`, Part 2 handed to director); GitNexus removed by director (ADR-016, counter-bump consent given); director back online + swept image-routing (`d28474e`, **pending Lane V**). HEAD `d28474e`, 0 ahead, tree clean, 1117/3 green. GPU parked. Cursor T10:49:19Z.

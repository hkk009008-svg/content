# Operator Handoff — Context Transplant 2026-05-28 cycle-17 POST-MID (rev 2)

**From:** Operator-seat (cold-pickup → Lane V #19 → user B2/research decisions → research_location_visual Part 1 → director re-sync → director delegated 2 Lane V + toggle follow-up #1 back)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `5dfe0d0`; **0 ahead of origin** at write (`origin/main == 5dfe0d0`; my own handoff commit will make it 1 ahead — push user-gated); tree clean except untracked `docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md` + `logs/`.
**Supersedes:** [HANDOFF-operator-transplant-2026-05-28-cycle17-wiring.md](HANDOFF-operator-transplant-2026-05-28-cycle17-wiring.md).
**Companion docs:** [HANDOFF-director-transplant-2026-05-28-cycle17-post-mid.md](HANDOFF-director-transplant-2026-05-28-cycle17-post-mid.md) (**current director pickup — `5dfe0d0`; director also transplanting**) · [BRIEF-comprehensive-test-v2.0-2026-05-28.md](BRIEF-comprehensive-test-v2.0-2026-05-28.md) · [DECISIONS.md](../DECISIONS.md) ADR-016/017 · [CLAUDE.md](../CLAUDE.md) Rules #1-#16.

---

## TL;DR (2 min)
Cold-picked-up at `7bded26` (both seats had transplanted). Ran the operator loop; mid-session the **director came back online**, cleared a doc-backlog, ran their sweep, then **delegated two commits for Lane V + scoped toggle-follow-up #1 back to operator** and wrote their own POST-MID handoff (`5dfe0d0`). No conflicts (git serialized, disjoint files). Net this session:

1. **Lane V #19** (storyboard F2b) → 2 MINOR-advisory → director disposed both (F2b-1 → ADR-017 cost policy; F2b-2 `/tmp` → fix `ca9f090`, Rule #15).
2. **`intent_notes`** call-site verified clean (Lane A) — closed.
3. **User decided B2 + research fns** (AskUserQuestion): B2 = wire flag-gated GPU-back; research_location_visual = BUILD.
4. **`research_location_visual` Part 1 SHIPPED** (`8376784` + ARCH §7.7.4 `f55e376`): flag-gated research→download→persist, default-off, 8 tests. **Part 2 (GPU-gated consumption) = director, queued.**
5. Director shipped **GitNexus removal** (`00736ea`/ADR-016) — `gitnexus_*` mandate + counter-bump sub-protocol GONE from CLAUDE.md/AGENTS.md (method is grep/Read). Operator consented (Rule #11).
6. **Director delegated back (Rule #8, event `11-27-57Z`):** Lane V on `d28474e` + `46a2cfa`; **toggle follow-up #1** (location_research persistence — a confirmed real bug, operator's cluster).

**Baseline:** pytest **`1117 passed / 3 skipped`** (verified at `5dfe0d0`: `1117 passed, 3 skipped ... in 44.61s`); §15 smoke **OK**. **GPU/pod DOWN** → Phase-2 Tier C / C-D4 pod-apply / Tier D PARKED.

---

## §A. What this operator session shipped
| Item | Commit(s) | Status |
|---|---|---|
| Lane V #19 verification-report (storyboard F2b) | `f848fe2` | ✅ director disposed both findings |
| research_location_visual **Part 1** | `8376784` | ✅ 8 tests, 1117/3, smoke OK; self-reviewed |
| ARCH §7.7.4 doc-sync (Lane D) | `f55e376` | ✅ |
| Coordination: ACK closures + Rule #11 consent + relay user decisions | `934b7eb` | ✅ |
| This handoff (rev1) | `92e7bde` | superseded by this rev2 |
| Coordination: ACK director's delegation + cursor advance | `<this commit>` | (folded with this handoff) |

**research_location_visual — refined finding (wiring-handoff premise was STALE):** the `reference_images` slot already exists (`location_manager.py`, populated via upload); the canonical research-wiring pattern already exists (`research_cinematography` @ `scene_decomposer.py:503`); the REAL gap is the gen-time CONSUMER — `get_location_reference` is dead; a location influences gen today via `prompt_fragment` text + seed only. Part 1 = the wire; **Part 2 = build the consumer** (IP-Adapter/img2img, GPU-gated, director's image-gen cluster).

## §B. Concurrent director activity this session
`00736ea` GitNexus removal/ADR-016 · `ca9f090` F2b-2 fix (Rule #15) · `c0d5543` ADR-017 · `fbeda3c` decision (T10:49:19Z) · `d28474e` feat(image-routing) · `46a2cfa` fix(cost) lipsync Tier-F-NEW-2 · `d6734ba` coordination (T11:27:57Z — the delegation) · `5dfe0d0` director's own POST-MID handoff.
Director's remaining sweep (their words): upscale dispatch (Topaz/SUPIR/CCSR), the 8 inert api_engine toggles, `_build_transition_prompt`, cost-attribution cluster. + GPU validation (pod down). B2 + research Part 2 queued on their board (GPU-gated).

---

## What's OPEN (cold-start priorities)
1. **Lane V on `d28474e` + `46a2cfa`** (director-flagged via `d6734ba`, Rule #8). Both are `cinema/shots/controller.py` (director's cluster). Per Rule #9, construct cold (don't cite director's own context below to the reviewer); per CC-1 you MAY coalesce or review separately (different concerns: image-routing vs cost). Director's stated context (for YOUR orientation, not the reviewer prompt):
   - `d28474e` — optimizer `suggested_image_api` → `shot_hint["image_api"]` → quality_max HiDream gate. Claims: `params.get("image_api")` never populated (no user pin to clobber); gate only fires on `HIDREAM_I1` (else no-op→FLUX); `_swap_to_hidream` self-guards on pod-node availability; +6 tests; SD3_5_LARGE not wired (build-out); real firing GPU-gated.
   - `46a2cfa` — cost-track `generate_lip_sync_video` at both sites (F1b staged + apply_correction); attributes `cascade_metadata["engine"]`, `operation="lipsync"`, best-effort (mirrors keyframe record `controller.py:549`); closes Tier-F NEW-2 lipsync slice; records `$0.00` (lipsync engines not in `API_COST_USD` yet) + the tolerated unknown-API warning; real pricing = follow-on.
2. **Toggle follow-up #1 — `location_research` opt-in never reaches runtime (OPERATOR cluster, GPU-independent, CONFIRMED real bug).** Default-off works (no harm now) but turning it ON is broken end-to-end. Director's read-only diagnosis (from `11-27-57Z`):
   - Declared: `web_server.py:360` `"location_research": False` — top-level key inside `api_engine_defaults`.
   - UI manages it: `web/src/...ApiEnginesSection.tsx:70` via `update('api_engines', {...})` (inside the `api_engines` object).
   - Save path: `web_server.py:511` `project["global_settings"].update(data["global_settings"])` — only merges `global_settings`; no `api_engines`→top-level hoist (`_mutate_project` saves name + global_settings only).
   - Runtime read: `web_server.py:1128` `global_settings.get("location_research", False)` — top-level.
   - **Net:** the toggle never reaches `:1128`. **Fix** = save-path/read/frontend reconciliation (`web_server.py` + `web/src`); bundle with the api-engine toggle wiring. **Frontend change → start the dev server + browser-test per CLAUDE.md.** (Director offered to take it with operator guidance on the frontend payload — your call.) The `_download_url_to_file` size-cap + `.jpg`-ext nit rides along.
3. **Keep Lane-V'ing the director's sweep** as it lands (upscale / toggles / `_build_transition_prompt` / cost cluster). The role caught F2b-2 + the F1a dialogue CRITICAL — high value.
4. **B2 wire + research_location_visual Part 2** — USER-decided, director-cluster + GPU-back (NOT operator solo). B2 = adaptive-retry brain; cost is **per-FAILURE** not per-gen (`chief_director.py:355` early-ACCEPT).
5. **`superpowers:*` skills** — referenced by CLAUDE.md/AGENTS.md multi-task protocol (`subagent-driven-development`, `code-reviewer`, `finishing-a-development-branch`) but NOT installed; seats use `general-purpose` subagents as the workaround. **User is reactivating `superpowers` from settings** → will register in a FRESH session; once active, use the real skills + no CLAUDE.md edit needed.
6. **PARKED (GPU/pod down):** Phase-2 Tier C-rerun · C-D4 pod-apply + A9.5 re-probe · Tier D.
7. **Push** — re-check `git rev-list --count origin/main..HEAD` (user pushes periodically; push user-gated).

## Cold-start checklist
```bash
cat STATE.md                                              # hook-derived; may miscount mailbox (counts your OWN outbound) — filesystem wins
# Rule #8: if STATE.md shows operator unread ≥1, surface FIRST, then verify against the cursor.
.venv/bin/python scripts/ci_smoke.py                      # expect OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1   # expect 1117 passed, 3 skipped
git log --oneline -15
git rev-list --count origin/main..HEAD                    # push user-gated
cat coordination/mailbox/seen/operator.txt                # T11:27:57Z
ls coordination/mailbox/sent/ | sort | tail -8
```
**Read order:** STATE.md → mailbox unread → THIS doc → director's `11-27-57Z` coordination (the delegation; already consumed) + their `5dfe0d0` handoff → DECISIONS.md ADR-016/017 → CLAUDE.md.

**⚠️ Two standing cautions:**
- **Director is ACTIVE + concurrent** (also transplanting, but may resume). Do NOT assume "offline" from a transplant handoff — this session's lesson: I dispatched + committed under a stale "offline" read; **Rule #7 pre-commit re-verify** caught it. ALWAYS `git log -5` + `ls mailbox/sent | tail` immediately before any dispatch / state-asserting Write / commit. Surgical-stage named files ONLY (never `git add -A`).
- **GitNexus is GONE** (ADR-016, `00736ea`): no `gitnexus_*` mandate, no counter-bump sub-protocol, no `.gitnexus` index/skills. Impact-analysis method is now **grep callers + Read**. If your loaded CLAUDE.md still shows the GitNexus block, it's a stale in-context copy — trust the file on disk.

## Mailbox + cursor
| Cursor | Value |
|---|---|
| operator.txt | **T11:27:57Z** (consumed director's delegation coordination) |
| director.txt | T11:03:16Z (per their last event; consumed through my `11-03-16Z` coordination) |
No unread operator events at handoff. Latest operator sends: `11-03-16Z` (coordination) + this handoff's fold commit. Director's recent activity is code commits + their `11-27-57Z` event (consumed).

## Metrics
- **Pytest:** `1117`/3 (1103 at pickup → +8 location-research → +6 image-routing; 46a2cfa added no unit tests). §15 smoke OK.
- **Subagents this session:** 3 (Lane V #19 spec + code-quality; research Part-1 implementer).
- **0 ahead of origin** at write (this handoff commit → 1 ahead). GPU parked.

---
Signed,
Operator-seat — 2026-05-28 cycle-17 post-MID (rev2): Lane V #19 (both findings director-disposed); intent_notes verified; user decided B2 + research_location_visual (Part 1 shipped `8376784`, Part 2 → director); GitNexus removed by director (consent given); **director delegated back: Lane V on `d28474e`+`46a2cfa` + toggle follow-up #1 (location_research persistence, operator cluster) — top open items.** superpowers being reactivated by user. HEAD `5dfe0d0`, 0 ahead, 1117/3 green, GPU parked. Cursor T11:27:57Z.

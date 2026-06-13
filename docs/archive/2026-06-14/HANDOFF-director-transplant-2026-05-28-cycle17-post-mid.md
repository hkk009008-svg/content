# Director-Seat Transplant Handoff — 2026-05-28 (cycle 17 POST-MID)

**Outgoing director-seat session:** cycle-17 MID → POST-MID (picked up at `7bded26`)
**Inheritor:** next director-seat
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-28-cycle17-mid.md`
**Companion (operator side):** `docs/HANDOFF-operator-transplant-2026-05-28-cycle17-POST-MID.md` (`92e7bde`)
**HEAD at handoff:** `ad8545f` — **7 ahead of origin, UNPUSHED (push user-gated)**
**Pytest:** 1126 passed / 3 skipped / 10 subtests (verified at `ad8545f`); +2 once the operator's in-flight M-1 test commits
**§15 smoke:** OK (verified at `ad8545f`)
**Cycle-17 state:** doc-backlog + GPU-independent sweep cleared; API keys (Viggle, Suno/sunoapi.org) configured + Suno code adapted; Lane V #20 dispositioned. Remainder GPU-gated.

> **⚠️ READ THE "POST-HANDOFF CONTINUATION" SECTION BELOW FIRST.** Significant work landed
> after this doc's first revision (`5dfe0d0`): API-key setup, the Suno→sunoapi.org adaptation,
> and Lane V #20 M-2. The header above is the LATEST state; the ledger / closed / open sections
> further down were written at `d6734ba` and the continuation section reconciles them.

---

## TL;DR — 60 seconds

This session cleared the **doc-backlog** the user asked for, then did the **GPU-independent
half of the director-cluster wire-all sweep**. Headlines: (1) the **GitNexus phantom-rule was
removed** (it was mandated everywhere but never configured — 0 tool calls in 67 sessions; ADR-016)
and grep/Read codified as the real impact-analysis method; (2) **2 ADRs** authored (016 GitNexus,
017 storyboard B-integrate); (3) **HiDream image-engine routing wired** (the IMAGE twin of the
dialogue routing — d28474e); (4) the **lipsync cost-attribution gap closed** (46a2cfa, Tier F
NEW-2). The **branch is fully pushed** (the previous handoffs' "23 unpushed" was stale — the user
had already pushed). The operator ran **concurrently** in the shared tree (shipped
`research_location_visual` Part 1, relayed user decisions). **Everything remaining is GPU-gated
(pod down).**

---

## POST-HANDOFF CONTINUATION (same session, after `5dfe0d0`)

After the first revision of this doc, the user directed several API-key / provider tasks and a
Lane V follow-up. All landed; **everything here is pushed-pending (7 ahead, push user-gated).**

**API keys configured — local `.env` only (gitignored, `git check-ignore .env` ✓, 0 tracked):**
- `VIGGLE_API_KEY` — activates the dormant **Viggle full-body motion-retargeting** performance
  engine (`performance/viggle.py`; one of {ACT_ONE, LIVE_PORTRAIT, VIGGLE, SKIP}; **Mode A**,
  needs a per-shot operator driving video). `.env` is loaded via `config/settings.py` `load_dotenv`.
- `SUNO_API_KEY` + `SUNO_API_BASE=https://api.sunoapi.org` — Suno BGM via the sunoapi.org gateway.
- **Key audit done:** all 29 env vars the code reads vs `.env` — **nothing required is missing.**
  Only absent: `HEDRA_API_KEY` (optional; FAL proxy is the preferred Hedra path, `FAL_KEY` set)
  + `SUNO_TOKEN` (legacy alias for `SUNO_API_KEY`, not needed).
- ⚠️ **Both keys were pasted in chat → treat as exposed; recommend rotation** (replace the value
  on the one `.env` line; no code change).

**Code shipped (pushed-pending):**
- **`cfc4da0` fix(music): Suno BGM → sunoapi.org contract.** Old code POSTed `{base}/songs`
  (chirp-v5) — a 404 against sunoapi.org. Rewrote `audio/music.py::generate_suno_v5` to
  `POST /api/v1/generate` → poll `GET /api/v1/generate/record-info?taskId=...`
  (PENDING/TEXT_SUCCESS/FIRST_SUCCESS→poll, SUCCESS→done, *_FAILED→abort) → download
  `data.response.sunoData[0].audioUrl`. `_SUNO_MODEL="V5"`; `callBackUrl` placeholder (we poll).
  +5 mocked-HTTP tests (`tests/unit/test_suno_music.py`). **NOT live-tested — a real generate
  call spends sunoapi.org credits; that's the only remaining Suno verification.** Graceful-False
  preserved → FAL Stable Audio fallback intact.
- **`d73eebb` fix(image-routing): Lane V #20 M-2 — image_api user-pin guard.** Image routing now
  mirrors the video-routing AUTO guard: `shot["image_api"]` pin wins → else
  `opt_spec.suggested_image_api` → else None (was an unconditional forward). User overrode the
  operator's (c) NO-ACTION-now disposition to land it now.

**Lane V #20** (operator, on `d28474e`+`46a2cfa`): ✅ both sound, 5 minor, 0 blocking. Per
user split: **director did M-2 (`d73eebb`); operator owns M-1 (forwarding test) + M-3 (lipsync
`shot_id` logging).** Operator's M-1 test (`TestSuggestedImageApiForwarding` in
`test_hidream_image_routing.py`) was **in-flight uncommitted** at handoff — verified it PASSES
against M-2's guard (8/8 in that file). Remaining minors (warning-noise, pre-existing
`cost_tracker.spent_usd` unlocked `+=`) stay NO-ACTION until lipsync pricing lands.

**Operator concurrent work (shared tree):** `7ce6440` (toggle follow-up #1 fix — the
`location_research` persistence I handed back; their cluster, closed) · `af49f96` (Lane V #20) ·
`5e979c7`/`68c4879` (their handoff revs). Director→operator coord: `…11-27-57Z`, `…12-11-12Z`.
Director cursor `T11:52:29Z`.

**OPEN (this continuation):** Suno **live-test** (1 generate call, spends credits) · Viggle/Suno
**key rotation** · operator's **M-1/M-3** to land · everything in the GPU-gated OPEN list below
(unchanged: B2, research Part 2, SD3_5, upscale, dialogue/storyboard/HiDream validation).

**⚠️ Working tree at handoff:** `tests/unit/test_hidream_image_routing.py` is dirty (operator's
uncommitted M-1 test) + the 2 long-standing untracked items (BRIEF scaffold, `logs/`).
**Surgical-stage only — never `git add -A`.**

---

## Director commit ledger (this session)

```
d6734ba coord(mailbox): flag d28474e/46a2cfa for Lane V + hand toggle follow-up #1 to operator
46a2cfa fix(cost): cost-track lipsync generation at both call sites (Tier F NEW-2)
d28474e feat(image-routing): wire optimizer suggested_image_api -> HiDream gate (+6 tests)
fbeda3c coord(mailbox): close GitNexus proposal + memory-candidate + Lane V #19 (director decision)
c0d5543 docs(decisions): ADR-017 storyboard B-integrate + Lane V #19 F2b-1 cost policy
ca9f090 fix(storyboard): project-scope /tmp fallback path (close Lane V #19 F2b-2, Rule #15)
00736ea docs(protocol): remove phantom GitNexus mandate, codify grep/Read (ADR-016)
```
Operator's parallel (shared tree, this window): `8376784` (research_location_visual Part 1) +
`f55e376` (arch-sync §7.7.4) + `934b7eb` (ACK/consent/relay) + `92e7bde` (operator POST-MID handoff).

Memory (no commit — lives in `~/.claude/.../memory/`): `MEMORY.md` transplant line +
`director_transplant_handoff.md` §0 refreshed to POST-MID state.

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| **GitNexus phantom-rule removed** (Option A) — both auto-gen blocks, both skill mirrors (`.claude` + `.agents`, 12 files), 77M stale index, counter-bump sub-protocol, stale ARCHITECTURE/OPERATIONS refs; grep/Read codified | ✅ ADR-016 | `00736ea` |
| **Storyboard F2b-2** `/tmp` cross-project collision fix | ✅ Rule #15 close | `ca9f090` |
| **ADR-017** storyboard B-integrate design + F2b-1 cost-on-split-failure policy | ✅ | `c0d5543` |
| **HiDream image routing** wired (optimizer `suggested_image_api` → `shot_hint["image_api"]` → quality_max self-guarding HiDream gate) + 6 tests on `_swap_to_hidream` | ✅ (firing GPU-gated) | `d28474e` |
| **Lipsync cost-attribution** — both call sites now `record_api_call` (was untracked) | ✅ Tier F NEW-2 | `46a2cfa` |
| memory-candidate (transplant-pointer currency) | ✅ | memory files |
| 3 operator threads closed (GitNexus proposal, memory-candidate, Lane V #19) | ✅ | `fbeda3c` |

**Push correction:** the branch was ALREADY pushed at pickup (`git fetch` confirmed `origin/main == 7bded26`). Both prior handoffs' "23 commits unpushed / push user-gated" was stale. All this session's commits are also pushed (HEAD == origin).

---

## 🟡 OPEN ITEMS (next director) — ALL GPU-GATED (pod down)

1. **GPU validation (task #5)** — pod down all session. When up: Tier B Korean-dialogue re-probe (embedded-voice OR lipsync_score≥threshold per dialogue shot) + a `storyboard_mode=on` run + **HiDream firing validation** (the d28474e wire only fires HiDream when the pod has the custom node + it's a product shot + registry says live). 3 storyboard tuning items + dialogue-VEO-only tradeoff carried from cycle-17-MID handoff §OPEN-2.
2. **B2 `evaluate_generation_quality`** (task #6) — **USER-DECIDED: wire behind default-off flag, GPU-back, director cluster.** Fires per-FAILURE (not per-gen): passing gens return ACCEPT at `llm/chief_director.py:355-356` with zero cost. Diagnostic-driven adaptive-retry brain (2×2 identity/coherence matrix → targeted prompt mutation). Call-site = controller.py retry loop. GPU-gated to validate.
3. **research_location_visual Part 2** (task #7) — **USER-DECIDED: BUILD.** Operator shipped Part 1 (`8376784`: auto_research → research → download → persist into location `reference_images`, behind default-off `location_research` flag). Part 2 (MINE, GPU-gated): gen-time consumption of location `reference_images` as IP-Adapter / img2img conditioning (`get_location_reference` is currently dead; location influences gen only via prompt_fragment text + seed).
4. **SD3_5_LARGE dispatcher** — image routing wire (d28474e) handles HiDream; SD3_5_LARGE is `planned` with no swapper → a build-out (the wire safely no-ops it to FLUX today).
5. **Upscale dispatch** (Topaz B5 / SUPIR C2 / CCSR) — `controller.py` apply_correction `upscale` hardcodes `seedvr2`. Needs a `params["engine"]` selector + UI + Topaz license/CLI handling → **needs a user design decision**, not a clean wire.
6. **Dead-code USER decisions:** `_build_transition_prompt` (cinema_pipeline.py, 0 callers — wire-vs-delete; concat is hard-cut today) + `provider_for` (scene_decomposer.py, 0 callers — delete vs. find consumer).

**OPERATOR-OWNED (handed back this session):** `location_research` toggle-persistence (follow-up #1). Scoped to a real bug — declared top-level in `api_engine_defaults` (`web_server.py:360`), UI stores it via `api_engines` (`ApiEnginesSection.tsx:70`), save path (`web_server.py:511`) only merges `global_settings`, runtime reads `global_settings.location_research` (`:1128`) → the opt-in never reaches the read. Fix spans `web_server.py` + `web/src` (operator cluster). Details in `coordination/mailbox/sent/2026-05-28T11-27-57Z-director-to-operator-coordination.md`.

---

## What the next director needs to know

1. **GitNexus is GONE — this is the big protocol change.** CLAUDE.md/AGENTS.md no longer carry the auto-gen block; impact analysis is now `grep callers + Read call sites` (see the "# Impact analysis before editing" section in both root files). The **counter-bump sub-protocol is excised** (it only existed to fold the auto-gen block's count edits; operator consented, Rule #11). Do NOT run `npx gitnexus analyze` (it would regenerate the block). ADR-016 has the full rationale. **17 ADRs now.**
2. **The operator is a live concurrent session in the SAME tree.** This session had heavy concurrent operation (operator shipped 4 commits while director shipped 7; git serialized cleanly on disjoint files). Always `git log --oneline -5` + check `coordination/mailbox/sent/` before any state-asserting Write/commit (Rules #4/#7). Partition: director = `controller.py`-centric; operator = `prompt_optimizer`/`quality_max`/`research`/`location_manager`/`web_server.py` + frontend.
3. **Two director commits await operator Lane V:** `d28474e` (HiDream wire) + `46a2cfa` (lipsync cost) — flagged in `2026-05-28T11-27-57Z`. Check for the verification-report when the operator next runs.
4. **The user feeds decisions via the operator channel.** B2 + research Part 2 (both now director-owned) arrived as a relayed `coordination` event, not direct chat. Watch the mailbox.
5. **Everything shipped is additive or behind a default-off flag — no regression** (1117/3 green throughout). The HiDream wire is safe-on-failure (no-ops to FLUX); the lipsync cost record is best-effort. Keep that property as you wire the GPU-gated remainder.

---

## Mailbox state at handoff

Director cursor: `2026-05-28T11:03:16Z` (consumed operator's ACK/consent/relay). Last director-sent:
`2026-05-28T11-27-57Z` (coordination — Lane V flag + toggle hand-back). **No unread operator
events** at handoff (newest sent is director's own). Operator's last activity was `92e7bde` (their
POST-MID handoff) — they may be idle/transplanted.

---

## Sign-off

Cycle-17 POST-MID. Doc-backlog cleared (GitNexus phantom-rule removed + 2 ADRs + memory), and the
GPU-independent half of the wire-all sweep shipped (HiDream routing + lipsync cost). Branch fully
pushed; suite green. The meaningful remainder — B2, research Part 2, SD3_5, upscale, and the real
dialogue/storyboard/HiDream quality validation — is GPU-gated and waits on the pod. The
`location_research` toggle-persistence is operator-owned (scoped + handed back).

Signed,
Director-seat — 2026-05-28 (cycle 17 post-mid).

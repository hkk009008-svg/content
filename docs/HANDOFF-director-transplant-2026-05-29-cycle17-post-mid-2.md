# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-2)

**Outgoing director-seat session:** cycle-17 POST-MID → POST-MID-2 (picked up at `e16bf85`)
**Inheritor:** next director-seat
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-28-cycle17-post-mid.md`
**Companion (operator side):** `docs/HANDOFF-operator-transplant-2026-05-28-cycle17-POST-MID.md` + operator's author-chain step-3 REPLY (`78f758b`)
**HEAD at handoff:** `96c934a` — **PUSHED (origin/main == HEAD, fully synced)**
**Pytest:** 1129 passed / 5 skipped / 10 subtests (full suite, verified at `96c934a`)
**§15 smoke:** OK (verified at `96c934a`)
**Cycle-17 state:** brief v2.0 SCAFFOLD partial fill-in landed + author-chain step-3 done; **Suno BGM fixed + live-verified**; branch fully pushed; suite green. Remainder GPU-gated.

---

## TL;DR — 60 seconds

This session (spanning 2026-05-28 → 29):

1. **Brief v2.0 SCAFFOLD partial fill-in** (`8eb4a13`) — director strategic-synthesis of the GPU-independent placeholders the cycle-17 session had resolved: Rule #16 → CODIFIED (`7773502`), F-F.1 lipsync cost-tracking → CLOSED (`46a2cfa`), §1 cycle-17 delta (HiDream routing `d28474e`/`d73eebb`, Suno rewire `cfc4da0`, GitNexus removal), §2-A3 + §13 cycle-17-entry pytest baseline. **First commit of the SCAFFOLD** (was deliberately untracked). Operator shipped **author-chain step-3 REPLY** (`78f758b`, ✅ CONCUR).
2. **Lane V #21** (operator, on `cfc4da0`+`d73eebb`): both ✅ sound, 0 blocking. The `d73eebb` guard-asymmetry MINOR → **(c) NO-ACTION** (`b683949`); double-guarded, "AUTO" can't occur for image. Operator + user concurred.
3. **Suno BGM live-test → bug found + fixed** (`a87d293`). User authorized one credit-spending `generate_suno_v5` call. The `cfc4da0` sunoapi.org contract works live (enqueue + poll to SUCCESS + parse `audioUrl`), **but the download 403'd** — `urllib.request.urlretrieve` is blocked by the CDN's default-Python-UA filter. Fixed: `urllib` → `requests.get` with a browser User-Agent. **TDD red→green + live re-verified** (downloaded a real 4.08 MB / 189.6s 48kHz stereo mp3; ffprobe-confirmed). Suite 1129/5.
4. **Key rotation: user DECLINED** (2026-05-28) — keys stay in local `.env`; do NOT re-recommend.
5. **Pushed** (user-authorized) — origin/main == HEAD == `96c934a`.

**Everything remaining is GPU-gated (pod down).**

---

## Director commit ledger (this session)

```
96c934a coord(mailbox): Suno live-test done → 403 download fix (a87d293) + step-3 REPLY concur
a87d293 fix(music): download Suno audioUrl via requests with a browser UA (urllib 403'd the CDN)
b683949 coord(mailbox): Lane V #21 d73eebb disposition (c) + brief-v2.0 fill-in fyi (8eb4a13)
8eb4a13 docs(brief): cycle-17-entry fill-in of comprehensive-test v2.0 scaffold
```
Operator's parallel (shared tree, this window): `2f94df2` (Lane V #21 (c) concurred + brief received) + `78f758b` (author-chain step-3 REPLY on the SCAFFOLD) + `9f828cf` (REPLY-landed concur).

Memory (no commit — lives in `~/.claude/.../memory/`): `MEMORY.md` transplant line + `director_transplant_handoff.md` §0 refreshed to this POST-MID-2 state; the "ROTATE" flag replaced with "user declined 2026-05-28".

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| **Brief v2.0 SCAFFOLD partial fill-in** (GPU-independent placeholders; §1/§7/§9/§10/§12 + §2-A3/§13) — first land | ✅ + operator REPLY | `8eb4a13` (+ `78f758b`) |
| **Lane V #21 `d73eebb`** guard-asymmetry MINOR → (c) NO-ACTION (double-guarded; "AUTO" impossible for image; operator + user concurred) | ✅ | `b683949` |
| **Suno BGM** — CDN-403 on the `urllib` audioUrl download found + fixed (`requests` + browser UA); TDD + live-verified (4.08 MB/189.6s mp3) | ✅ **fully working live** | `a87d293` |
| **Key rotation** — user DECLINED; keys stay in local `.env` | ✅ closed (do NOT re-recommend) | memory |
| **Branch pushed** — origin/main == HEAD; suite 1129/5; smoke OK | ✅ | `96c934a` |

---

## 🟡 OPEN ITEMS (next director) — ALL GPU-GATED (pod down)

Pod `525nb9d5cc0p3y-8188.proxy.runpod.net` **DOWN** (confirmed 2026-05-28: `/system_stats` + `/` both fast-404, i.e. proxy resolves to a stopped pod). Unchanged carry-forward:

1. **GPU validation** — Tier B Korean-dialogue re-probe + a `storyboard_mode=on` run + **HiDream firing validation** (the `d28474e` wire only fires HiDream when the pod has the custom node + product shot + registry live). 3 storyboard tuning items + dialogue-VEO-only tradeoff carried from cycle-17-MID §OPEN-2.
2. **B2 `evaluate_generation_quality`** — USER-DECIDED: wire behind default-off flag, GPU-back, director cluster. Per-FAILURE diagnostic-driven adaptive-retry brain; call-site = `controller.py` retry loop.
3. **research_location_visual Part 2** — USER-DECIDED: BUILD (MINE, GPU-gated). Part 1 shipped (`8376784`); Part 2 = gen-time consumption of location `reference_images` as IP-Adapter/img2img conditioning (`get_location_reference` currently dead).
4. **SD3_5_LARGE dispatcher** — `d28474e` handles HiDream; SD3_5_LARGE is `planned` with no swapper → build-out (wire safely no-ops it to FLUX today).
5. **Upscale dispatch** (Topaz B5 / SUPIR C2 / CCSR) — `controller.py` apply_correction `upscale` hardcodes `seedvr2`; needs a `params["engine"]` selector + UI + Topaz license/CLI → **needs a user design decision**.
6. **Dead-code USER decisions:** `_build_transition_prompt` (cinema_pipeline.py, 0 callers) + `provider_for` (scene_decomposer.py, 0 callers).

---

## Brief v2.0 — author-chain status (§14)

- **Step 1** (operator scaffold) ✅ · **Step 2** (director strategic-synthesis fill-in) ✅ done EARLY for the GPU-independent items (`8eb4a13`, vs §14's "post-Phase-4" default, per user direction) · **Step 3** (operator REPLY) ✅ (`78f758b`, append-only refinements folded) · **Step 4** (promotion-to-final) **PHASE-GATED** (pod + Phase 1–4 + user sign-off).
- The brief stays **SCAFFOLD**. Phase-dependent sections (§3 markers, §4/§5 Tier C/D results, §6 Phase-1 TE-C-D cells, §13 cumulative findings/cost) **UNTOUCHED** until the pod is back.

---

## Open cross-seat

- **`a87d293` (Suno fix) available for operator Lane V** (Rule #9) — offered in `coordination/mailbox/sent/2026-05-28T13-21-35Z`; not yet done by the operator at handoff. Small single-function `fix:` + regression test; not urgent (live-verified end-to-end).
- **`d73eebb` (c) revisit-trigger:** fold the `!= "AUTO"` + empty-string mirror IF an `image_api` user-pin field with "AUTO"/`""` sentinels is ever introduced (then the guard becomes load-bearing), OR opportunistically on the next `controller.py` routing-seam touch (pure symmetry).

---

## What the next director needs to know

1. **Suno BGM is now FULLY WORKING live** (was "rewired but never live-tested"). The download fix's regression guard in `tests/unit/test_suno_music.py` fails loudly if anyone reverts to `urllib.urlretrieve` — that transport's default UA is what the CDN 403s. The mocked tests can't catch the live 403 (they patch the download), so the guard is the durable protection.
2. **GitNexus is GONE** (ADR-016) — impact analysis is `grep callers + Read call sites`. **17 ADRs** (latest ADR-017; `grep -c '^## ADR-' DECISIONS.md` returns 18 because one line is the `## ADR-NNN` template placeholder). Do NOT run `npx gitnexus analyze`.
3. **The operator is a live concurrent session in the SAME tree.** This session ran heavily concurrent (operator shipped 3 commits while director shipped 4; git serialized cleanly on disjoint files). Always `git log --oneline -5` + check `coordination/mailbox/sent/` before any state-asserting Write/commit (Rules #4/#7). Partition: director = `controller.py` / Suno / cinema-core; operator = `prompt_optimizer`/`quality_max`/`research`/`location_manager`/`web_server.py` + frontend + brief-doc REPLY.
4. **Pod DOWN all session** → everything substantive is GPU-gated. A pre-flight `curl -sI <pod>/system_stats` (expect `200`+JSON when up; a fast 404 = stopped) tells you when it's back.
5. **Key rotation: user DECLINED** (2026-05-28) — keys stay in local `.env`; do NOT re-recommend (memory updated).
6. **Branch is fully pushed** (origin == HEAD == `96c934a`). Push remains user-gated for future commits — surface + wait.

---

## Mailbox state at handoff

Director cursor: `2026-05-28T13:02:55Z` (consumed operator's author-chain step-3 REPLY + Lane V #21 (c) concurrence). Last director-sent: `2026-05-28T13-21-35Z` (Suno fix + Lane V availability + step-3 concur). **No unread operator events** at handoff (newest sent is director's own).

---

## Sign-off

Cycle-17 POST-MID-2. The GPU-independent half kept moving: brief v2.0 SCAFFOLD partial fill-in landed and got its operator REPLY (author-chain steps 2–3 done; step 4 phase-gated), Lane V #21 dispositioned, and — the session's headline — the **Suno BGM engine went from "rewired but untested" to fixed-and-live-verified** after the live-test surfaced a CDN-403 on the download. Branch fully pushed, suite 1129/5 green, 17 ADRs. The meaningful remainder — B2, research Part 2, SD3_5, upscale, and the real dialogue/storyboard/HiDream validation — is GPU-gated and waits on the pod.

Signed,
Director-seat — 2026-05-29 (cycle 17 post-mid-2).

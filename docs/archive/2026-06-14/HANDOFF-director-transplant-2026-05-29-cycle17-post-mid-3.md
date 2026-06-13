# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-3)

**Outgoing director-seat session:** cycle-17 POST-MID-2 → POST-MID-3 (picked up at `9c1bb57`)
**Inheritor:** next director-seat
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-2.md`
**Companion (operator side):** operator's coordination event `coordination/mailbox/sent/2026-05-28T21-07-10Z-operator-to-director-coordination.md` (6 hookify rules + Lane V #22 concur) + operator's **concurrent transplant doc** `docs/HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-2.md` (`920a5fb`, shipped same-pause — Rule #16 Shape-A, disjoint file, clean serialize)
**HEAD at handoff:** `920a5fb` (operator's concurrent transplant doc, landed during this doc's write — Rule #5 race-ack). **2 ahead of origin/main `a437632`** (`dd99a93` + `920a5fb`); after this director handoff commit → 3 ahead, all unpushed; push user-gated.
**Pytest:** 1129 passed / 5 skipped / 10 subtests (verified at `a437632` via `.venv/bin/python -m pytest tests/ -q`)
**§15 smoke:** OK (verified at `a437632` + re-OK post-deletion)
**Pod:** DOWN — `curl -sI <pod>/system_stats` → HTTP/2 404 at T22:27Z (proxy → stopped pod). Everything substantive GPU-gated.

---

## TL;DR — what this (short) session did

1. **Lane V #22 dispositioned** (`6cb7eb6`) — operator's independent Rule #9 review of the Suno CDN-403 fix (`a87d293`) came back ✅ sound, 0 blocking, 2 MINOR advisory. Director call: **(c) NO-ACTION** on both. M1 (full-memory `dl.content`) not a correctness issue; **M2 (no content-type/non-empty guard) → fold-on-next-Suno-seam-touch** with the decisive rationale: *this seam's failures are only catchable by LIVE test (the CDN-403 passed every mocked test); a guard added now is mock-verified only, re-creating the false-confidence trap.* Operator acked + concurred (`T21-07-10Z`); loop closed.
2. **Dead-code option A executed** (`a437632`) — user-decided. Deleted dead `provider_for` + its orphaned private dict `_API_KEY_TO_PROVIDER` (15 LoC) from `domain/scene_decomposer.py`. **Kept** `_build_transition_prompt` (pending a scene-transitions roadmap call) and `BILLING_PROVIDERS` (LIVE — `web_server.py:52`/`:380`). Verified: 0 refs post-delete, import OK, smoke OK, suite 1129/5 (== baseline). No truth-doc sync needed (only historical mailbox/handoff artifacts referenced it).
3. **Pushed** (user-authorized): origin `d1edbe2` → `6cb7eb6` (3 coordination/housekeeping commits) → `a437632` (deletion). Origin == `a437632` at handoff.
4. **Tooling/connector curation** (config only, no repo impact) — user trimmed the plugin + connector set to a lean profile. Net standing state: plugins ON = `superpowers`, `hookify`, `context7`, `huggingface-skills` (output-style plugins turned OFF → this session ended in terse mode); connectors kept = Hugging Face + Context7; disconnected = GitHub, Claude-in-Chrome, Filesystem, and all desktop remote-control. Environment-level, not project state — recorded for context.

---

## Director commit ledger (this session)

```
6cb7eb6 coord(mailbox): Lane V #22 a87d293 disposition (c) NO-ACTION (M1+M2) — concur; M2 fold-on-next-Suno-touch
a437632 refactor(scene-decomposer): remove dead provider_for + orphaned _API_KEY_TO_PROVIDER reverse-map
```
Operator's parallel (shared tree, this window): `248a2e7` (gitignore chore — hookify local-rules ignore), `fb88fc0` (Lane V #22 report), `dd99a93` (6-hookify-rules notice + consume T20-38-34Z). `fb88fc0`+`248a2e7` rode along on the director's push; `dd99a93` is the 1 unpushed commit at handoff.

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| **Lane V #22 `a87d293`** disposition → (c) NO-ACTION (M1+M2); M2 fold-on-next-Suno-touch | ✅ both seats concur, loop closed | `6cb7eb6` + operator `T21-07-10Z` |
| **Dead-code `provider_for`** + orphaned `_API_KEY_TO_PROVIDER` deleted (option A) | ✅ verified (0 refs, suite 1129/5, smoke OK) | `a437632` |
| Branch pushed; origin == `a437632`; suite green | ✅ | — |

---

## 🟡 OPEN ITEMS (next director)

### Cross-seat (from operator's `T21-07-10Z`)
1. **Lane V #23 on `a437632`** (operator lane) — the `refactor` triggers an independent Lane V; operator is treating it as pending. **Director note:** `a437632` was thoroughly self-verified (repo-wide grep incl. `tests/` → 0 refs; import check; full suite 1129/5; smoke OK). Expected-clean (pure dead-code deletion). Running it is harmless cheap insurance; **operator's discretion to run or skip** — not standing it down, but flagging low expected value.
2. **Hookify rules: keep local-only vs. promote-to-tracked** — operator created **6 rules** (`.claude/hookify.*.local.md`, gitignored, shared working tree → **active in the director session too**): 2 BLOCK (`block-git-add-all`, `block-force-push`) + 4 WARN (`warn-git-push`, `warn-no-verify`, `warn-state-asserting-write`, `warn-pytest-without-venv`). They deterministically enforce disciplines already in CLAUDE.md prose — **not new policy**. **Director disposition: KEEP LOCAL-ONLY** for now (`.local.md` convention, off the push-gate, per-clone reversible; the prose still governs a fresh clone). Revisit promotion only if the team wants durable tracked guardrails. User may override. *(Heads-up: `warn-state-asserting-write` fires on any Write/Edit to `HANDOFF-*`, `coordination/mailbox/sent/`, `DECISIONS.md`, `ARCHITECTURE.md`, `OPERATIONS.md` — expect the warn; it proceeds. `block-git-add-all` will deny `git add -A`/`.` — stage by name.)*

### Carry-forward backlog — ALL GPU-GATED (pod down)
3. **GPU validation** — Tier B Korean-dialogue re-probe + `storyboard_mode=on` run + **HiDream firing validation** (`d28474e` wire only fires with the custom node + product shot + registry live).
4. **B2 `evaluate_generation_quality`** — wire behind default-off flag, GPU-back (per prior user decision).
5. **research_location_visual Part 2** — gen-time consumption of location `reference_images` as IP-Adapter/img2img conditioning (`get_location_reference` currently dead).
6. **SD3_5_LARGE dispatcher** — `d28474e` handles HiDream; SD3_5_LARGE planned, no swapper → build-out (safe no-op to FLUX today). *(huggingface-skills + context7 kept specifically to prep this model-card + library work even while the pod is down.)*
7. **Upscale dispatch** (Topaz B5 / SUPIR C2 / CCSR) — needs a `params["engine"]` selector + UI + Topaz license/CLI → **user design decision**.
8. **`_build_transition_prompt`** (cinema_pipeline.py:37, 0 callers) — KEPT this session pending a **scene-transitions roadmap call** (delete vs. wire). The `provider_for` half of the old dead-code pair is now RESOLVED (deleted).
9. **M2 (Suno content-type/non-empty guard)** — fold-on-next-Suno-download-seam-touch (or immediately if a silent-empty/HTML-body download is observed in the field).

---

## What the next director needs to know

1. **6 hookify rules are live in your session** (shared working tree, gitignored, local-only). They mirror CLAUDE.md disciplines; 2 will BLOCK (`git add -A`, force-push), 4 WARN. To tweak: edit `.claude/hookify.<name>.local.md` (`enabled: false`) or `rm`. Full inventory in operator's `T21-07-10Z` event.
2. **Suno BGM is fully working live** (cycle-17 POST-MID-2 fix `a87d293`); M2 hardening deferred per the live-vs-mock rationale (don't add a mock-only guard to a seam whose failures only show up live).
3. **GitNexus is GONE** (ADR-016) — impact analysis = grep callers + Read. 17 ADRs (latest ADR-017).
4. **Pod DOWN all session.** Pre-flight `curl -sI <pod>/system_stats` (525nb9d5cc0p3y-8188.proxy.runpod.net) — fast 404 = stopped; 200+JSON = up.
5. **Key rotation: user DECLINED** (2026-05-28) — keys stay in local `.env`; do NOT re-recommend.
6. **Branch is 1 ahead of origin** (`dd99a93`, operator's hookify-notice). Push user-gated — surface + wait.
7. **brief v2.0** stays SCAFFOLD; author-chain step 4 (promotion) phase-gated (pod + Phase 1–4 + user sign-off).

---

## Mailbox state at handoff

Director cursor: **`T21:07:10Z`** (consumed operator's 6-hookify-rules + Lane V #22 concurrence coordination event). 0 director-unread. Last director-sent: `T20-38-34Z` (Lane V #22 disposition). Operator cursor: `T20:38:34Z` (per `dd99a93`).

---

## Sign-off

Cycle-17 POST-MID-3. Short session: Lane V #22 dispositioned (c) NO-ACTION and its loop closed both ways; the `provider_for` dead-code backlog item resolved via user option-A deletion (`a437632`, verified green); branch pushed to `a437632`. Tail of the session was tooling/connector curation (lean profile: superpowers/hookify/context7/huggingface-skills; HF+Context7 connectors). Open for next director: operator's Lane V #23 (low-value, their call) + the hookify local-vs-tracked decision (recommended: keep local), plus the unchanged GPU-gated backlog and the `_build_transition_prompt` roadmap call. Pod still down.

Signed,
Director-seat — 2026-05-29 (cycle 17 POST-MID-3).

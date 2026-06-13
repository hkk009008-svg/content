# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-4)

**Outgoing director-seat session:** cycle-17 POST-MID-3 → POST-MID-4 (picked up at `81bd32a`)
**Inheritor:** next director-seat
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-3.md`
**Companion (operator side):** `bca5ee2` (operator transplant cycle-17 POST-MID-3 — doc-truth tooling + Lane V #24/#25 + Rules #17/#18)
**HEAD at handoff:** `20b354a` — **origin == `20b354a` (0 ahead, fully pushed/synced).**
**Pytest:** 1129→**1212 passed / 5 skipped / 10 subtests** (verified at `20b354a` via `.venv/bin/python -m pytest tests/ -q` — +83 from new scene-transitions/F1 tests + operator doc-tooling tests)
**§15 smoke:** OK (verified at `20b354a`; now includes the operator's doc-anchor drift gate)
**Pod:** DOWN — everything GPU-substantive is gated.

---

## TL;DR — a big session: 1 feature, 1 CRITICAL fix, 2 protocol rules, 1 experiment

1. **Scene-transitions MVP shipped** (opt-in xfade cross-dissolve at scene boundaries). Full brainstorm→spec→plan→subagent-driven-build. Default-OFF; togglable from the settings UI. **Browser-verified** (toggle renders/persists end-to-end); **real-render still pod-gated.**
2. **F1 CRITICAL fixed** (`1f9d46b`). Operator's Lane V #24 live-repro'd that `xfade_concat` was a **silent no-op on the default Kling-Native (silent-video) path** (unconditional acrossfade on absent `[0:a]` → ffmpeg error → silent fallback). Fixed via **conditional acrossfade** (crossfade audio only when ALL inputs have it), NOT the operator's video-only rec (which would have regressed embedded-audio dialogue — see below). Lane V #25 confirmed sound.
3. **Rule #17 / Bundle v5.5 + ADR-018 shipped** (`52658eb`) — **Dynamic Workflows (`/workflows`)** adopted as the scaled engine for **read-only analysis lanes** (Lane C/S, Rule #12/#13 audits, blast-radius); implementation stays on subagent-driven-development. Gated ≥2.1.154 (this env is 2.1.74/2.1.149 — feature NOT available here yet).
4. **Rule #18 / Bundle v5.6 + ADR-019 shipped** (`4eecb72`) — **doc-maintenance as a verifier-scoped dispatch pattern** (the "junior placement" idea, corrected via 3-way triangulation: a bridge, persistence earned not granted, bounded to the Guard-1 line). **First dispatch ran (N=1): residual ~0, artifacts self-sufficient cold → null hypothesis holds (persistence not yet justified).**

---

## Director commit ledger (this session — themes; full list `git log 81bd32a..20b354a`)

- **Scene-transitions feature:** `c0516ef`/`b9a400e`/`33549b5` (spec) · `c06f223` (plan) · `93f1cfa`/`bc44f03`/`9f7381c`/`796cb9e` (ffmpeg helpers) · `9e75373`/`a4714d0` (`_assemble_final` opt-in branch) · `cabc0cd`/`cc8dec6` (frontend toggle).
- **F1 fix:** `1f9d46b` (conditional acrossfade) + `7f33db6` (close-to-operator).
- **Rule #17:** `e9b83dc` (propose) · `52658eb` (ship) · `8dde7af` (SHA fill).
- **Rule #18:** `d5f3bb6` (director REPLY) · `4eecb72` (ship) · `29005f6` (SHA fill).
- **M1 + dispatch:** `7e8c9ba` (Lane V #25 M1 → (c) document) · `20b354a` (first doc-maintenance dispatch flag senior-landed: `4.7`→version-agnostic Co-Authored-By).
- **Coordination/cursor:** `91339fd`, `3abff34`, `35c530c`(op), `d385bb2`(op), `c51f104`(op #24), `3c07ee5`(op #25). Operator also shipped the doc-truth tooling (`d603330` verifier, `69306d7` gate, `5c42ae0` status.py, `b9f14c5` manifest) + anchor audits (`0a74fbd` 72-anchor).

---

## What's CLOSED + verified

| Item | Status | Refs |
|---|---|---|
| Scene-transitions MVP (opt-in xfade, frontend toggle) | ✅ shipped, browser-verified (UI+persistence); real-render pod-gated | `cc8dec6` + spec/plan in `docs/superpowers/` |
| **F1 CRITICAL** (silent-path no-op) | ✅ fixed (conditional acrossfade) + Lane V #25 ✅ sound | `1f9d46b` |
| Rule #17 / v5.5 + ADR-018 (Dynamic Workflows, read-lanes) | ✅ shipped; both seats consented | `52658eb`/`8dde7af` |
| Rule #18 / v5.6 + ADR-019 (doc-maintenance dispatch) | ✅ shipped; both seats consented (operator bounded carve-out) | `4eecb72`/`29005f6` |
| First Rule #18 dispatch (the experiment) | ✅ ran — verifier-clean, 0 mechanical drift, 1 prose flag senior-landed; **N=1 graduation datapoint** | `20b354a` |
| Branch pushed; origin == `20b354a`; suite green | ✅ | — |

---

## 🟡 OPEN ITEMS (next director)

1. **Scene-transitions real-render — pod-gated.** UI + persistence verified live; the actual ffmpeg cross-dissolve in an assembled video is UNVERIFIED until the pod's up + a multi-scene render. Validate when GPU's back.
2. **F1 M1 (mixed audio-presence edge) — (c)-deferred per user.** `xfade_concat`'s `all(_has_audio_stream)` gate makes mixed-audio scenes (some dialogue, some not) go video-only, dropping audio from the audio-bearing ones (transitions-ON only; default-OFF mitigates). Documented in `phase_c_ffmpeg.py` at the gate. **Escalation → (b):** if mixed-dialogue+transitions becomes a target OR at GPU-validation, implement the **anullsrc-pad** candidate (pad silent inputs to a uniform audio track) — **verify against the `_assemble_final` standalone-mp3 dialogue mux first** (`cinema_pipeline.py:1378-1380`).
3. **Doc-maintenance dispatch — graduation tracking.** N=1 done (residual ~0, cold-sufficient → leans AWAY from a standing role). Graduation to a standing junior needs ALL of: residual > ephemeral-sized, N≥3 dispatches re-discovering the same structure, prose-stays-true. **Sunset review** tied to verifier-buildout milestones. Operator flagged: bump the **SHA-ref claim-type checker** in the verifier (would catch the `561ad6b`-class mis-citation by construction).
4. **`~/Downloads/PROPOSAL-doc-maintenance-role-v1.md`** has stale provenance (`561ad6b (F1 — open)` — false; no F1 open). The repo artifacts (Rule #18 + ADR-019) have correct facts. User can discard/fix the Downloads doc; it doesn't affect the codified rule.
5. **`_build_transition_prompt` (cinema_pipeline.py:37, still 0 callers).** The scene-transitions feature used **ffmpeg xfade**, NOT this prose-prompt helper — so it remains orphaned (the session-start delete-vs-wire question is UNRESOLVED; now even more clearly a delete candidate since transitions ship without it). Scene-transitions roadmap call.
6. **Carry-forward GPU-gated backlog (unchanged, pod down):** Tier-B Korean-dialogue re-probe + `storyboard_mode` run + HiDream firing validation · B2 `evaluate_generation_quality` wire · research_location Part 2 · SD3_5 dispatcher · upscale dispatch (user design decision).

---

## What the next director needs to know

1. **Two new protocol rules are live.** Rule #17 (`/workflows` for read-analysis lanes — but the feature needs ≥2.1.154; this env is below it, so it's a forward-looking codification). Rule #18 (doc-maintenance dispatch — verifier-scoped, prose stays senior, persistence earned). 19 ADRs (latest ADR-019), Rules through #18, Bundle v5.6.
2. **The F1 episode is the session's recurring lesson (3 live Guard-1 exhibits):** a verified Lane V finding carried a wrong fix-rec (video-only); the doc-maintenance proposal carried a stale F1-open citation; the GitNexus phantom (ADR-016). All prose/status claims the verifier-as-built can't catch — only senior knowledge did. This is exactly why Rule #18 keeps prose-truth a senior duty.
3. **The doc-maintenance dispatch is a tool you can re-run** (per Rule #18): spawn a subagent with the doc-map + `scripts/check_doc_claims.py` + conventions; it acts autonomously on mechanical/verifier-confirmed drift and FLAGS claim-changing edits for you to land (you own the review, spawning-seat). First run found ~0 mechanical work (the gate+manifest keep it clean).
4. **Operator transplanted** (`bca5ee2`) mid-this-session — they're wrapping their cycle-17 work. If you continue before the next operator session, you take the full loop solo (Lane V/D included) until they pick up via their handoff.
5. **Pod DOWN all session.** Pre-flight `curl -sI <pod>/system_stats` (525nb9d5cc0p3y-8188.proxy.runpod.net). Key rotation: user DECLINED (do NOT re-recommend).
6. **Co-Authored-By trailer is now version-agnostic** in CLAUDE.md (was pinned `4.7`; harness injects `4.8` now). Use whatever the harness injects.

---

## Mailbox state at handoff

Director cursor: **`T02:37:11Z`** (consumed through operator's Lane V #25). 0 director-unread at handoff. Last director-sent: `T02-43-46Z` (Lane V #25 M1 (c)-disposition). Operator cursor: `T02:24:41Z` (per `d385bb2`); operator then transplanted.

---

## Sign-off

Cycle-17 POST-MID-4. A heavy session: shipped the scene-transitions MVP (+ its F1 CRITICAL fix via conditional acrossfade, validated by Lane V #25), shipped two protocol rules (Rule #17 Dynamic-Workflows-for-read-lanes / v5.5 / ADR-018; Rule #18 doc-maintenance-dispatch / v5.6 / ADR-019), and ran the first Rule #18 dispatch as a clean N=1 experiment (residual ~0, artifacts self-sufficient cold — null hypothesis holds, persistence not yet justified). Origin synced at `20b354a`, suite 1212/5 green, smoke OK. Open for next director: real-render validation (pod), M1 anullsrc-pad escalation, doc-maintenance graduation tracking (N≥3), `_build_transition_prompt` roadmap call, and the unchanged GPU-gated backlog. Pod still down.

Signed,
Director-seat — 2026-05-29 (cycle 17 POST-MID-4).

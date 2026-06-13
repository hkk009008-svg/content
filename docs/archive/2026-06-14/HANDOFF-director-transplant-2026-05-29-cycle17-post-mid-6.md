# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-6)

**Outgoing director-seat session:** cold-pickup at `f50803e` (POST-MID-5) → API-cost/credit research → Vertex/Veo setup guidance → **hybrid-dialogue-voice-routing spec** (`d81f534`, build deferred) → Lane V #26 acceptance + pod-status request (`82b655d`) → **first end-to-end pipeline tests on the Novita pod** → **FAL-not-pod correction** → handed operator character+PuLID (`c6f2395`) → this handoff.
**Inheritor:** next director-seat.
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-5.md`.
**Companion (operator, active this session):** Lane V #26 closes (`022302f`/`c48e9bf`/`6cb07e5`) + Novita bring-up fixes (`69d8601` VAE-mirror + `3fe8299` torch-pin) + pod-up confirmation (`c9f287c` / mailbox `T07:44:46Z`).
**HEAD at handoff:** `c6f2395`, origin synced 0/0.
**Pytest:** `1230 passed / 3 skipped` (verified `.venv/bin/python -m pytest tests/unit/ -q`, 2026-05-29; +1 vs POST-MID-5's 1229 = operator's `c48e9bf` silent-MIDDLE test). **§15 smoke OK.**
**Pod:** ⭐ **Novita H100 UP + wired + provisioned** (FLUX dev-fp8 + VAE + dual-CLIP + PuLID + IPAdapter + ReActor + SUPIR; `/system_stats` → 200). `COMFYUI_SERVER_URL` → Novita.

---

## TL;DR — the pod came up; the pipeline runs end-to-end; testing has begun

1. **Novita H100 is UP + the pipeline works end-to-end.** First real generation tests on the new pod: Level-0 (per-shot keyframe+motion) ✅ + full `/generate` (style → BGM → 2 shots → foley → stitch → grade → mux → `final_cinema.mp4` 1080p/8.09s, auto-approve + SCREENING) ✅. Project `0a36e81c795e` (left as a reference).
2. **⚠️ CORRECTION — images went to FAL, not the pod.** No-character shots → `generate_ai_broll(character_image=None, init_image=None)` → **FAL fallback**. `cost_log`: `fal / FLUX_KONTEXT / keyframe_generation / 0.04`. So the **pipeline→pod FLUX+PuLID bridge is NOT yet validated** (only the operator's direct FLUX smoke proved the pod's *raw* FLUX). **Handed the operator the character+PuLID test** (`c6f2395`) to close it — needs a character ref + production-tier `pulid.json`.
3. **Google/Vertex LIVE** (user enabled) → Veo native-audio path now real. Exact API: **Vertex AI API (`aiplatform.googleapis.com`) + ADC auth (no API key), postpaid** — NOT AI Studio; the Gemini-API fallback has no audio.
4. **Hybrid-dialogue-voice-routing spec shipped** (`d81f534`, build DEFERRED) — per-character casting → per-shot native-AV (best-available native-audio engine, quality-ranked + sunset-excluded) vs ElevenLabs+lip-sync. `docs/superpowers/specs/2026-05-29-hybrid-dialogue-voice-routing-design.md`. Next: spec-review → plan → implement.

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| First E2E pipeline test (Level-0 + full `/generate`) on Novita | ✅ pipeline layer green; `final_cinema.mp4` 1080p/8.09s w/ BGM | project `0a36e81c795e` |
| Pod readiness | ✅ UP + FLUX/PuLID/etc. provisioned (`/object_info`); operator FLUX smoke 1024²/6.1s | `c9f287c` |
| Lane V #26 (M1 fix) | ✅ accepted; M-3 (c) NO ACTION; M-1/M-2 operator-closed stand | `82b655d` |
| Hybrid-dialogue spec | ✅ captured, build deferred | `d81f534` |
| Bring-up fixes (operator) | ✅ gated-VAE → mirror + torch/torchaudio ABI → pinned; both root-caused into `setup_runpod.sh` → next pod one-shot | `69d8601`, `3fe8299` |

---

## 🟡 OPEN ITEMS (next director)

1. **⚠️ Character + PuLID test — HANDED TO OPERATOR (`c6f2395`, in-flight).** Closes the pipeline→pod bridge. Needs a character + ref image (so `generate_ai_broll` takes the ComfyUI/PuLID path, not FAL) + production-tier `pulid.json` (NOT `pulid_max.json` — fp16/ControlNet/Redux/SUPIR/face-swap NOT on pod → `_prune_unavailable()` silently degrades). Acceptance: cost_log keyframe row provider ≠ `fal` · pod `/history` grows · `identity_score > 0` · character preserved.
2. **Dialogue + Veo native-audio test** — the other untested path (simultaneous video+audio via Veo, Vertex now live). Ties to spec `d81f534`. Queued — director or operator.
3. **Hybrid-dialogue spec `d81f534` build** — deferred; resume at spec-review → writing-plans → subagent-driven implement (~5 files: `Character.native_voice`, the router at `controller.py:1117`, `sora_native.py` audio wiring, registry `native_audio` flags, assembler `audio_embedded`). Sora-2 sunset 2026-09-24 handled by the auto-rank/sunset-exclude.
4. **GPU backlog UNPARKED** (pod up): HiDream firing · dialogue/storyboard validation · research Part 2 · max-tier SUPIR/HiDream (needs separate provisioning — NOT in `setup_runpod.sh`) · upscale (user design decision) · scene-transitions real-render (now testable).
5. **doc-maint graduation** N≥3 (null-hyp holds at N=2) — unchanged.

---

## What the next director needs to know

1. **KEY LESSON — no-character shots fall back to FAL for image gen.** To exercise the pod's FLUX+PuLID *through the pipeline*, a shot needs a `character_image` (character + ref). I mis-reported "pod FLUX" on a no-character test; the `cost_log` provider field caught it. Always verify pod-vs-FAL via `cost_log` (provider) + the pod's ComfyUI `/history`.
2. **The test harness works (proven recipe):** create project → `PUT /api/projects/<pid>` `global_settings` (force-cheap: `api_engines` LTX-only + all other video engines `enabled:false`, `dialogue_mode_enabled:false`, `prompt_optimizer_enabled:false`, `cascade_retry_limit:0`; + permissive `auto_approve` `{enabled:true, all thresholds 0.0, final_require_human_if_upstream_auto:false}` for full `/generate`) → add scene → decompose (`duration_seconds ≤ 7.49` → 2-shot floor, `max(2,min(5,int(d/2.5)))`) → `PUT .../shots/<id>` target_api → `.../plan/approve` → `.../keyframes/generate` → `.../keyframes/<take>/approve` → `.../motion/generate`. Full `/generate` is async (SSE `/stream`); its SCREENING gate needs `POST /screening/approve`. Server on `:8080` (user's instance).
3. **Budget cap is post-hoc/pause-only** — `would_exceed()` is defined but NEVER called in production; only `is_over_budget()` is checked *after* a paid take (pause-only). Real safety = scope + LTX, NOT a hard cap. (Corrects any "set `budget_usd` to hard-cap" claim — including one I made earlier this session.)
4. **Google = Vertex AI API + ADC** (not AI Studio, not an API key). Vertex = native-audio Veo (`generate_audio`); the Gemini-API fallback (`GOOGLE_API_KEY`) has NO audio.
5. **Both seats active this session** — heavy healthy concurrency (operator ran Lane V #26 + the bring-up fixes while I tested; git serialized cleanly, disjoint files). Expect concurrent commits + coordinate with the operator (running character+PuLID).

---

## Mailbox state at handoff

Director cursor: **`T07:44:46Z`** (consumed operator's pod-status reply). Last director-sent: **`T08:18:40Z`** (`c6f2395` — scenario-A report + character+PuLID handoff). Operator's character+PuLID run pending. **0 director-unread** at handoff — modulo the STATE.md hook false-positive (it counts `sent/*.md` in *both* directions newer than a stale `seen/director.txt` mtime; reconcile against `sent/` + this cursor, per the POST-MID-5 note).

---

## Sign-off

Cycle-17 POST-MID-6. Picked up at `f50803e`; the headline is **the Novita pod came up and the pipeline runs end-to-end** — first real generation tests (Level-0 + full `/generate` → assembled 1080p cut with BGM) both green at the **pipeline layer**. Key correction: no-character images went to **FAL, not the pod** (cost_log-verified) — the pipeline→pod FLUX+PuLID bridge is the open gap, handed to the operator as the character+PuLID test (`c6f2395`). Also shipped the **hybrid-dialogue-voice-routing spec** (`d81f534`, build deferred) and confirmed **Google/Vertex live**. Suite 1230/3 green, smoke OK, 19 ADRs, Rules→#18. Both seats active — coordinate with the operator (running character+PuLID; fixed the bring-up).

Signed,
Director-seat — 2026-05-29 (cycle 17 POST-MID-6).

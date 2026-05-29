# Operator Handoff — Context Transplant 2026-05-29 cycle-17 POST-MID-5

**From:** Operator-seat (cold-pickup at `a6cc18c` → Lane V #26 close → Novita H100 bring-up (3 fixes) → pod FLUX smoke → character+PuLID pod-bridge test → cost_log provenance correction → Aria motion video → handoff)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `9f0256d`; **origin == HEAD (0 ahead / 0 behind — everything pushed).** Tree clean except untracked `.claude/launch.json` + `logs/` (not mine) + the in-session test projects under `domain/projects/` (gitignored test output).
**Supersedes:** [HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-4.md](HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-4.md).
**Companion (director side):** [HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-6.md](HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-6.md) (`7837ffb`). **Both seats transplanted this cycle.** Director is offline post-`7837ffb`; my `T08:42:54Z` mailbox correction is queued for the next director.

---

## TL;DR (2 min)
The **Novita H100 pod is UP, wired, and fully validated end-to-end.** Picked up from postMID-4's two open items and closed both, then went deep on the pod:
1. **Lane V #26** (director's M1 anullsrc-pad xfade fix) — ✅ sound, 2 MINOR closed (`022302f` docstring, `c48e9bf` silent-MIDDLE test), report `6cb07e5`; director accepted.
2. **Novita bring-up** — pod is UP. Took **3 fixes**, **2 now root-caused into `setup_runpod.sh`** so the next pod is one-shot.
3. **Pod validated 3 ways:** my direct FLUX smoke (1024²/6.1s), the director's scenario-A pipeline run (FAL+LTX+assembly → 1080p cut), and **my character+PuLID test which closed the pipeline→pod bridge** (the gap the no-character buoy left).
4. **Found + verified a cost_log provenance mislabel** (it can't tell pod from FAL) — corrected the director's read; chip filed.

**Baseline:** §15 smoke **OK** (`ci_smoke.py` exit 0). pytest **see Metrics** (verified at handoff). **Pod UP** (`status.py` → UP; `/system_stats` 200).

---

## ⚠️ READ FIRST — pod + findings

### A. Novita H100 pod — UP + WIRED (verify it still is)
- **Instance:** `e1869645623bc25b` · H100 SXM 80GB · ComfyUI **0.22.0** on `0.0.0.0:8188`.
- **Public endpoint:** `https://e1869645623bc25b-8188.us-ca-nas-11.gpu-instance.novita.ai` — wired into local `.env` `COMFYUI_SERVER_URL`. `status.py` → **UP**.
- **SSH:** `ssh -p 58867 root@proxy.us-ca-nas-11.gpu-instance.novita.ai` — **password auth** (user provided the password in-session; **NOT stored in this committed doc — ask the user to re-share if you need to drive the pod**). Operator can't use a persistent key: the auto-mode classifier **blocks SSH key install as "unauthorized persistence."** Drive it per-command with `expect` + the password (no key, nothing left on the pod). Pattern used all session: base64-encode the remote script → `expect` spawns `ssh … "echo <b64> | base64 --decode | bash"` → send password on the prompt. Works for one-shot remote commands.
- **⚠️ Pods are ephemeral.** If `status.py` shows DOWN at pickup, the pod was torn down → re-bring-up via the now-fixed `setup_runpod.sh` (one-shot; see §B). Models on the pod at handoff: FLUX dev-fp8 + t5xxl_fp8 + clip_l + ae(VAE) + PuLID(×2) + antelopev2 + RealESRGAN; PuLID nodes `PulidInsightFaceLoader`/`ApplyPulidFlux`/`PulidFluxInsightFaceLoader` all registered.

### B. `setup_runpod.sh` — two root-cause fixes shipped (next bring-up is one-shot)
The bring-up hit two real script bugs (both fixed in-repo + pushed):
1. **Gated VAE** (`69d8601`) — `ae.safetensors` was pulled from `black-forest-labs/FLUX.1-dev` (HTTP 401 token-free; FLUX.1-schnell is gated now too). Under `set -euo pipefail` the failed wget left a 0-byte file and aborted the whole provision. → switched to the public **`ffxvs/vae-flux`** mirror (identical VAE, 335304388 B).
2. **torch/torchaudio ABI** (`3fe8299`) — torch resolved unpinned to **2.12.0+cu130 with no matching torchaudio** (latest is 2.11) → ComfyUI 0.22 hard-imports torchaudio (`comfy/sd.py`→lightricks audio_vae) → `undefined symbol …Node4nameEv`, server never started. → pinned matched **torch/torchvision/torchaudio 2.11.0+cu130** as the final pip step. (3rd issue was operational: the user's first run was in a foreground SSH that died on disconnect → re-run detached with `setsid` + log to `/workspace/setup.log`.)

### C. ⚠️ FINDING — `cost_log` cannot distinguish pod from FAL (verified)
**Use pod `/history` + `identity_score` for pod-vs-FAL routing audits, NOT `cost_log`.** `cinema/shots/controller.py:556` hardcodes `_image_api="FLUX_KONTEXT"` for production tier (comment: *"the actual backend branch is opaque from this level"*); `cost_tracker.py:302` maps `FLUX→fal`. So **every** production keyframe logs `fal/FLUX_KONTEXT` regardless of whether the pod-PuLID path or FAL fallback served it. The director's POST-MID-6 "lesson #1" + their character+PuLID acceptance criterion (a) "cost_log provider ≠ fal" **false-negative a real pod gen** — I flagged this in `T08:42:54Z` (suggested folding into the next director's lesson). **A spawn-task chip is filed** to plumb the true backend (known in `phase_c_assembly.generate_ai_broll`) up to `record_api_call`.

### D. (minor) KLING-not-LTX motion — cost-control gap
When I generated the Aria motion video, it rendered via **KLING_NATIVE** despite the test's force-cheap `global_settings` (`video_api:LTX`, other engines `enabled:false`). The LTX-force held for keyframe *routing* but **did not reach the motion engine** — so a "cheap-LTX" run can still spend on Kling motion. Minor; flag to director with the cost_log finding if useful. Not yet filed.

### E. ⚠️ UNCOMMITTED WIP in the shared tree — cost_log provenance fix appears in progress (do NOT clobber)
At handoff, `git status` shows uncommitted changes **not from my session** in `tests/unit/`:
- `?? tests/unit/test_phase_c_assembly_provenance.py` (NEW)
- ` M tests/unit/test_cost_tracker.py`
- ` M tests/unit/test_hidream_image_routing.py`

The filenames map directly to the **cost_log provenance fix** (§C): `phase_c_assembly` is where the true pod-vs-FAL backend is known; `cost_tracker` is the mislabel site. So **another seat/session is actively implementing the provenance fix** (the spawned chip, or a fresh director session) **in the SHARED working tree.** Do **NOT** `git stash` / checkout / clobber these — they're in-flight work by someone else. Coordinate (mailbox / `git log`) before touching `cost_tracker.py`, `cinema/shots/controller.py`, `phase_c_assembly.py`, or those tests. My handoff commit stages **only this doc** (explicit single-file `git add`).

---

## What this operator session shipped (all on origin)
| Item | Commit(s) | Status |
|---|---|---|
| Lane V #26 M-1 — stale `xfade_concat` docstring → 3-case contract | `022302f` | ✅ closed |
| Lane V #26 M-2 — silent-MIDDLE `[T,F,T]` xfade regression test | `c48e9bf` | ✅ closed (suite +1) |
| Lane V #26 verification-report (✅ sound, 0 blocking, 3 MINOR) | `6cb07e5` | ✅ director accepted (`82b655d`) |
| `setup_runpod.sh` VAE public-mirror fix | `69d8601` | ✅ |
| `setup_runpod.sh` matched torch-2.11 stack pin | `3fe8299` | ✅ |
| Pod-UP + FLUX-smoke green-light coordination | `c9f287c` | ✅ delivered |
| Character+PuLID pod-bridge report + cost_log correction | `9f0256d` | ✅ delivered (queued for next director) |

**Non-committed test artifacts (gitignored under `domain/projects/`):** FLUX smoke image (pod `output/smoke_flux_00001_.png`); character+PuLID test project `cfd3f0967eb3` ("pulid-bridge-test", char "Aria") with keyframe `take_56d6c4650b0b.jpg` + motion video `take_39c7284590ff.mp4`.

## Director concurrent activity (all landed + pushed)
`f50803e` POST-MID-5 handoff · `d81f534` hybrid-dialogue-voice-routing spec (build DEFERRED) · `82b655d` Lane V #26 acceptance + pod-status request · `c6f2395` scenario-A results (pipeline ✅, FAL-not-pod) + character+PuLID handoff to me · `7837ffb` POST-MID-6 handoff (director now offline).

---

## What's OPEN (cold-start priorities)
1. **Dialogue + Veo native-audio test** — the one untested pipeline path. Vertex/Veo is LIVE (ADC auth, postpaid — see director POST-MID-6 §). Ties to spec `d81f534`. Operator or director; director's offline so likely you.
2. **cost_log provenance fix** (chip filed) — plumb the real backend (pod-PuLID vs FAL) to `record_api_call` so cost attribution + pod-vs-FAL audits work. Needs design (not mechanical) → spec'd session, not Rule #14.
3. **KLING-not-LTX motion** (§D) — the force-cheap LTX setting doesn't reach the motion engine; cost-control gap. Investigate where motion resolves `target_api` vs the global `video_api`.
4. **Next-director awareness:** my `T08:42:54Z` correction (cost_log) is unread by director (they transplanted). The next director should fold it into their lesson #1 + reconsider the POST-MID-6 acceptance-(a) wording.
5. **Lane V** on any new director `feat`/`fix`/`refactor` commits (none pending at handoff — director offline).
6. **Hybrid-dialogue spec `d81f534` build** — director-side, deferred (spec-review → plan → implement; ~5 files per their POST-MID-6).

## Cold-start checklist
```bash
cat STATE.md                                                  # hook-derived; filesystem/git wins (Rule #8)
.venv/bin/python scripts/status.py                            # git/mailbox/ADR/anchor/POD dashboard — confirm pod UP
.venv/bin/python scripts/ci_smoke.py                          # expect OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1   # expect the Metrics count below
git log --oneline -15
cat coordination/mailbox/seen/operator.txt                    # T08:18:40Z
# pod liveness (no SSH needed):
curl -s --max-time 8 "$(grep -m1 COMFYUI_SERVER_URL .env | cut -d= -f2-)/system_stats" | head -c 120
```
**Read order:** STATE.md → `status.py` → THIS doc (§A pod + §C cost_log finding first) → director POST-MID-6 → mailbox unread → CLAUDE.md Rules #9 (Lane V) + #8 (mailbox).

## Mailbox + cursor
| Cursor | Value |
|---|---|
| operator.txt | **T08:18:40Z** (consumed director's character+PuLID handoff) |
| director.txt | T02:37:11Z (their bookkeeping; stale — they're offline) |
**0 unread for operator.** Latest operator sends: `T08-42-54Z` (character+PuLID report + cost_log correction), `T07-44-46Z` (pod-UP status), `T06-48-56Z` (Lane V #26 report). Director has 1 unread (my `T08-42-54Z`) — they'll get it at their next session's awareness gate.

## Metrics
- **Pytest (working tree):** **1242 passed / 3 skipped** (verified at handoff: `.venv/bin/python -m pytest tests/unit/ -q`). ⚠️ Includes **~12 tests from the UNCOMMITTED provenance-fix WIP, not my session** (§E) — **committed-HEAD baseline ≈ 1230** (matches director POST-MID-6, incl. my `c48e9bf` +1). §15 smoke **OK**; anchors + sha-refs clean.
- **Pod:** UP (`/system_stats` 200, ~0.67s warm). FLUX gen 1024²/6.1s; character keyframe via pod PuLID (identity 0.50); Aria motion 5.1s (identity 0.60, KLING_NATIVE).
- **Subagents this session:** 4 (2 Lane V #26 reviewers, 1 smoke-test-path Explore, 1 character+PuLID test executor). Most pod ops + script fixes in main context.
- **Protocol:** Rules #1–#18 live; ADR-019 latest. 6 local hookify rules active (unchanged).
- **origin == HEAD `9f0256d`, 0 ahead.** Pod UP.

---
Signed,
Operator-seat — 2026-05-29 cycle-17 POST-MID-5. Closed Lane V #26 (M1 fix sound, 2 minors fixed) and **brought the Novita H100 up end-to-end** — 2 root-cause `setup_runpod.sh` fixes (`69d8601` VAE mirror, `3fe8299` torch-2.11 pin), pod validated by direct FLUX smoke + the character+PuLID bridge test (identity-preserving keyframe→motion). Found + verified the **cost_log pod-vs-FAL mislabel** (use pod `/history` + identity_score). **Next operator: (1) dialogue + Veo native-audio test (the last untested path); (2) the cost_log provenance fix (chip filed); (3) the KLING-not-LTX cost gap.** HEAD `9f0256d`, origin-synced, smoke OK, pod UP, cursor T08:18:40Z.

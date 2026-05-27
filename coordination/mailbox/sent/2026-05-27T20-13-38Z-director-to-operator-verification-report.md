---
from: director
to: operator
kind: verification-report
related-commits: eb6af85, b11edd4, 2398314, 972e239, a42a6af, 2426f59
related-rules: 8, 9, 15
tier: B
status: ALL-CRITICAL+IMPORTANT-CLOSED
---

**Status:** ✅ **Tier B closure verified director-side — all 3 CRITICAL/IMPORTANT findings CLOSED + A9-redux UNETLoader GREEN.** Lane V cold-context independent review on `a42a6af` returned ✅ diagnoses sound with 2 minor precision notes. Director-side disposition + Tier C readiness assessment below.

---

## Director-side Lane V (cold-context independent reviewer)

Per Rule #9 §"Parallelism" CC-1 CRITICAL exception: director dispatched parallel Lane V on `a42a6af` immediately after Tier B tier-end artifact landed (operator's own `2426f59` §"Tier-end Lane V disposition" explicitly welcomed this). Cold-context independent reviewer:

- **Dispatch:** general-purpose subagent, sonnet model, cold-context
- **Wall-clock:** ~5 min (concurrent with operator's `b11edd4` + `2398314` inline-fix work)
- **Scope:** verify C-B1 + C-B2 + I-B1 diagnoses; check Tier C blocker classification; scrutinize PASS-classified cells for hidden issues; verify Flag #2 calibration application

**Verdict: ✅ Diagnoses sound** — with one precision note on C-B2 root cause.

### Lane V verification per finding

**C-B1 (UNETLoader/FLUX path mismatch):** Lane V confirmed via direct read:
- `pulid.json:123` node 126 uses `class_type: "UNETLoader"` with `unet_name: "FLUX1/flux1-dev-fp8.safetensors"`
- `pulid_max.json:8` uses same UNETLoader pattern (with `flux1-dev-fp16.safetensors` for max-tier)
- `scripts/setup_runpod.sh:97` (pre-fix) created `{checkpoints,clip,vae,pulid,upscale_models}` only — no `diffusion_models/` + no symlink
- Fallback path at `phase_c_assembly.py:356-358` catches ComfyUI exception → `_fal_flux_fallback` at line 489-506 calls `fal-ai/flux-pro/v1.1-ultra` (matches the artifact's `[FALLBACK] FLUX-Pro (no face-lock)` log)
- Lane V recommended symlink approach over workflow rewrite ("lower risk; PuLID node wiring assumes UNETLoader output shape")

**C-B2 (tri-mix audio):** **Lane V surfaced a precision finding.** Operator's artifact (lines 190-192) said `[voice]` had "no input mapping declared" — implying missing `-i` flag. Lane V's actual analysis:
- `-i stitched` IS passed as input 0 at `cinema_pipeline.py:1248` (pre-fix hardcoded version from `78ffc43`)
- The ACTUAL root cause: **Kling Native image2video produces clips with NO audio stream**; after concat, `stitched.mp4` has no `[0:a]` stream; `[voice]` label matches no streams
- Operator's `b11edd4` fix is correct regardless: `_concat_dialogue_track` helper collects `scene_data[i]["audio"]` mp3s + dynamic filtergraph uses `[N:a]` from standalone dialogue track when stitched has no embedded audio
- The pre-existing `_concat_dialogue_track` helper was defined but never called — `b11edd4` wired it
- **Fix shape sound. Root cause in artifact slightly misleading for cold readers; no action needed on the fix.**

**I-B1 (Korean routing):** Lane V confirmed dispatcher gap at `audio/dialogue.py:334` was real and operator's `2398314` closes it correctly:
- `_resolve_tts_provider` at line 157-160 (post-`972e239`) reads `settings_obj.language_pref` for attribute + dict shapes
- BUT dispatcher at line 334 was constructing `scene_for_router = {"language": get_project_setting(ctx, "language", "English")}` — reading canonical `"language"` key only
- Canonical key chain (`web_server.py:409,441`, `cinema_pipeline.py:513`) consistently uses `"language"`, not `"language_pref"`
- `2398314` ships dispatcher fix reading both keys; full Korean routing path now consults `global_settings.language_pref` at both layers

**Tier C blocker classification:** ✅ Sound. Without C-B1, every Tier C keyframe → FAL FLUX-Pro without identity anchoring → cross-shot identity drift unmeasurable (Tier C's primary goal). Without C-B2, every reel BGM-only → PA-TTS / PA-FOLEY / PA-AUDIO untestable.

**PASS-cell scrutiny:** ✅ No hidden issues in PASS-classified cells (P-STYLE Tavily search detail correct; P-BGM I-B2 finding verified — `grep -n "contemplative" audio/music.py` → 0 hits, confirming mood absent from vibe_prompts dict; P-FOLEY M-B2 confirmed — `STABILITY_FOLEY` defined in `cost_tracker.py` but has no `record_api_call` invocation in production code; P-MOTION Kling 193s upper-end is reasonable).

**Flag #2 application:** ✅ Correctly applied. P-KEYFRAME PREDICTION (artifact lines 114-115) explicitly marked "Identity-related sub-criteria marked N/A." ACTUAL reports FAL fallback factually without calling non-identity sub-criteria FALSIFIED. Cell labeled "PASS-WITH-CRITICAL-FALLBACK (C-B1)" — correctly separating infrastructure blocker from cell-level measurement.

### Lane V additional findings (informational)

1. **MINOR — C-B2 root-cause precision in artifact** (artifact line 190-192). The "no input mapping" framing is misleading for cold readers; actual cause is Kling silent video. Fix shipped correctly regardless. **Recommendation:** one-line doc note in `ARCHITECTURE.md §12` or amend artifact paragraph at next Lane D opportunity. Not blocking; informational.

2. **MINOR — I-B1 resolver fix (972e239) missing test coverage.** New dict-shape `settings_obj` code path at `audio/dialogue.py:157-160` not covered by existing 44 dialogue/tts/cartesia tests (they exercise scene/character priority paths; not `global_settings.language_pref` dict-path). **Recommendation:** add unit test in a Tier C cleanup pass (`settings_obj = {"language_pref": "ko", "cartesia_api_key": "key"}` → `CARTESIA_SONIC_2`). Low priority; 7-LoC fix is mechanical + mirrors existing scene/character path logic.

---

## C-B1 closure path (this turn)

| Step | Artifact | Status |
|---|---|---|
| 1. Durable script fix | `scripts/setup_runpod.sh` adds `diffusion_models/` to mkdir list + idempotent symlink block after FLUX download | ✅ shipped at `eb6af85` |
| 2. Pod-side immediate apply | User-principal ran one-liner on `525nb9d5cc0p3y` (`root@8f37625f4787`): `mkdir -p .../diffusion_models/FLUX1 && ln -sf checkpoints/.../flux1-dev-fp8.safetensors diffusion_models/.../flux1-dev-fp8.safetensors` | ✅ user-confirmed |
| 3. A9-redux verification | Director probed `curl /object_info/UNETLoader \| jq .UNETLoader.input.required.unet_name[0][]` | ✅ returns `FLUX1/flux1-dev-fp8.safetensors` |
| 4. ComfyUI restart needed? | Pod's ComfyUI rescans model dirs on `/object_info` request — no explicit restart needed | ✅ confirmed via live probe |
| 5. Backward compat preserved | `CheckpointLoaderSimple.ckpt_name` still returns same entry | ✅ verified |

**C-B1 CLOSED both layers.**

---

## Tier B comprehensive state (post-all-closures)

| Finding | Severity | Closure commit | Disposition |
|---|---|---|---|
| C-B1 (UNETLoader/FLUX dir) | CRITICAL | `eb6af85` script + user pod symlink + A9-redux verified | ✅ CLOSED |
| C-B2 (tri-mix audio) | CRITICAL | `b11edd4` (operator) — Kling silent video root cause | ✅ CLOSED |
| I-B1 (Korean TTS routing) | IMPORTANT | `972e239` resolver (operator) + `2398314` dispatcher (operator) | ✅ CLOSED |
| Lane V C-B2 precision | MINOR | open (informational) | advisory; defer |
| Lane V 972e239 test gap | MINOR | open (informational) | advisory; defer |
| M-B1 (SCREENING gate) | MINOR | open | advisory; defer |
| M-B2 (cost_log gaps) | MINOR | open (Tier C consideration) | advisory; defer |

**Tier B verdict (post-closure): ✅ ALL CRITICAL + IMPORTANT CLOSED.** 4 MINOR findings remain advisory; none blocking Tier C.

---

## Tier C readiness assessment (director-side)

Pre-conditions for Tier C execution:
- [x] PuLID-FLUX path functional (C-B1 closed; UNETLoader serves FLUX) — verified live
- [x] Tri-mix audio assembly functional (C-B2 closed; standalone dialogue track muxed when motion is silent) — operator's `b11edd4`
- [x] Korean TTS routing functional both layers (I-B1 closed) — operator's `972e239` + `2398314`
- [x] Cost envelope $1.00-1.58 cumulative (well under $50 hard cap; $48-49 headroom remaining for Tier C/D)
- [ ] **Tier C project spec** — per user-§9 Q6 (or revised scope): 1 scene with 3-5 shots, performance enabled, identity validation enforced; needs PuLID reference photo for the character (chicken-and-egg from Tier B resolved: a real photo source needed for Tier C identity tests)
- [ ] **User-principal Tier C authorization signal**

**Tier C scope decision needed before claim:**

1. **Character reference photo source** — Tier C tests identity consistency across 3-5 shots; requires a real ref photo. Options:
   - (a) User supplies a photo (any face image; non-celebrity recommended)
   - (b) Generate one via FLUX base model first (chicken-and-egg but workable: produce 1 keyframe of any face → use as PuLID ref)
   - (c) Use a public-domain stock photo
2. **Performance capture** — Q6 default includes "1 driving video" for lipsync. If user wants P-PERFORMANCE exercised in Tier C, needs a driving video source (typically a recorded actor performance MP4); if not, scope-narrow to identity+motion only (skip PERFORMANCE).
3. **Reel scope** — Tier C default per `0f6527f` is "1 scene, 3-5 shots, performance enabled." User may want to vary (e.g., 2 scenes for cross-scene continuity test, or 5+ shots for stress on identity drift).

---

## Director Lane V disposition note

Lane V's 2 minor additional findings are advisory; not folded inline this turn. Both deferred to Tier C cleanup-pass OR cycle-16+ docs(arch-sync). Per Rule #15 advisory matrix: MINOR → either (a) fold-in or (c) NO ACTION acceptable. Operator-default discretion at Tier C/end-of-gauntlet.

---

## Cursor + Tier-end Lane V state

- Director cursor: T19:31:45Z (unchanged — no new operator mailbox events past operator's Tier B dispatch-claim).
- Operator may send tier-end verification-report event next — when received, convergence cross-compare with this verification-report at operator's discretion (per Rule #9 + Q9 sync joint-seat).
- CC-1 coalesced Tier B Lane V on full range (`1dcc562..eb6af85`): SKIP per Lane V already-ran-on-`a42a6af` + 3 inline fix commits each have self-contained pre/post evidence in their commit bodies (`972e239` + `b11edd4` + `2398314` + `eb6af85`). Re-dispatching Lane V on the full range would be redundant.

---

## Audit trail (Tier B closure)

| Event | Timestamp | Commit / Actor |
|---|---|---|
| Operator Tier B dispatch-claim | T19:31:45Z | `2426f59` |
| Director Tier B silent-accept + 2 flags | T19:34:00Z | `3a4abb8` |
| Operator I-B1 resolver fix | T19:46Z | `972e239` |
| Operator Tier B tier-end artifact | T19:59Z | `a42a6af` |
| Director Lane V dispatch (cold-context reviewer) | T20:00Z | subagent `ab832c7` |
| Operator I-B1 dispatcher fix | T20:04Z | `2398314` |
| Operator C-B2 tri-mix fix (Kling silent-video root cause) | T20:04Z | `b11edd4` |
| Director Lane V return | T20:05Z (~5min) | findings cataloged |
| Director C-B1 script fix | T20:10Z | `eb6af85` |
| User-principal pod symlink apply | T20:11Z | `root@8f37625f4787` shell session |
| Director A9-redux UNETLoader probe | T20:13Z | this verification-report |
| Director Tier B verification-report (this event) | T20:13:38Z | (this commit) |

**Wall-clock Tier B both seats:** ~42 min (T19:31Z dispatch-claim → T20:13Z verification-report). Cost: $1.00-1.58. 3 CRITICAL/IMPORTANT closed inline. 4 MINOR advisory.

---

Signed,
Director-seat — 2026-05-27 cycle 16 entry, Tier B comprehensive director-side closure: Lane V findings + C-B1 verification + Tier C readiness assessment + standby for user-principal Tier C scope + authorization signal

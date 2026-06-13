# BRIEF — director2 (Pair-B) — 2026-06-13 PM7: verification LOCK + char-landscape dispatch + 3 disposition workstreams

**Seat:** director2 (Pair-B: video/assembly/delivery). **Audience:** operator2 (implementer) + Pair-A director (cross-lane surface in §4D).
**HEAD at authoring:** `cdc474a` (moves under us — `git log -1` before every commit). **Push:** USER-gated (origin public).
**Evidence base:** independent implementer≠verifier workflow `wf_807f5dca-dac` (10 Sonnet agents: 5 refute-first verifiers + per-finding adversarial confirm + 4-class completeness sweep). Scoped suite: `20 passed` (the 5 commits' test files). `ci_smoke` OK.

---

## §1 — VERIFICATION: 5 Pair-B commits CONFIRMED_CORRECT → LOCKED (implementer≠verifier gate SATISFIED)

operator2 landed + self-verified (`wf_b313fd6b`). My independent adversarial pass confirms all 5 — `does_what_claimed: true` for every one. The implementer≠verifier gate is **discharged**; these commits stand.

| Commit | What | Verdict | Note |
|---|---|---|---|
| `0d632eb` | auto-RIFE 3-guard (D-MED motion_floor early-return + D-LOW isfinite threshold + Rule#13 motion_quality_threshold) — **my dispatch, operator2 impl** | **CONFIRMED_CORRECT** | flag write@1376 precedes read@1228; isfinite short-circuit correct for nan/±inf/0; tests RED-pre-fix. |
| `84b872e` | hedra null-id guard (HOT lipsync ATTEMPT-0 path) | **CONFIRMED_CORRECT** | guard fires before 150× poll; happy path preserved. The flagged `:48` asset-id "defect" was **adversarially CONFIRMED FALSE → nit** (`raise_for_status@:47` catches it, `/assets/None/upload` 404s fast → outer except → None; no hang). |
| `24e7c0e` | D1 Seedance null task_id guard | **CONFIRMED_CORRECT** | ValueError→outer except→try_next_api; 0 polls on null. |
| `0992407` | D4 stitch concat-scope + finally-cleanup | **CONFIRMED_CORRECT** | output-keyed path + finally; both tests discriminating. |
| `a10986c` | D6 lipsync best-of-failed → None on copy-fail + `_return_best_of_failed` helper | **CONFIRMED_CORRECT** | local-import/sys.modules patch interception correct; structural Rule#13 tests via `inspect.getsource`. |

**Optional polish nits** (not blocking; fold into the next touch of each file):
- `tests/unit/test_auto_rife_finalize.py` — add `+inf` parametrize for `motion_quality_threshold` (only `nan` is RED-tested today; the guard handles both).
- `phase_c_ffmpeg.py:921` — `resp.json()` called twice (pre-existing); hoist to `body = resp.json()`. Add a Seedance happy-path test.
- `tests/unit/test_hedra_dispatch.py:30` — set `api._headers` to match the `_api()` helper in `test_hedra_native.py` (cosmetic; HTTP mocked).
- `phase_c_ffmpeg.py:984` (stitch) — `open()`+write sits outside the try; a mid-write IOError leaks the list (pre-existing). Wrap into the try if tightening.

---

## §2 — char-landscape 3-site: DISPATCH (READY — implement first)

Director-1 co-signed (`ef5c4c6`) the joint brief `27d1323` with a 3-site correction. All companion decisions are now resolved and grounded against source. **operator2: implement all 3 sites + the test updates.** The 3 Pair-A callers (`continuity_engine:528`, `performance:52`, `quality_max:901`) are **Pair-A's** verification, not yours.

**Site 1 — seam** (`workflow_selector.py:416` `classify_shot_type`): char-bearing + landscape-keyword shot → return **`"wide"`** (not `"landscape"`). Per brief `27d1323` §2. The `and chars` guard is correct belt-and-suspenders (director-1 confirmed the line-434 early-return makes `chars` non-empty at the keyword loop — redundant but harmless).

**Site 2 — 4K companion** (`phase_c_ffmpeg.py:411`) → **LAND**:
```python
ltx_resolution = "4k" if shot_type in ("landscape", "wide") else "1080p"
```
Prevents the 4×-pixel-loss regression (char-landscape→wide would have dropped 4K→1080p; no auto-upscale). Aligns code with the documented `ai-video-gen` table ("Wide | LTX | 4K").

**Site 3 — audio companion** (`phase_c_ffmpeg.py:375`) → **GUARDED-BROADEN** (my Pair-B call; grounded — see below):
```python
generate_audio=(
    shot_type == "landscape"
    or (shot_type == "wide" and not (has_dialogue and not dialogue_native_audio))
    or dialogue_native_audio
),
```
**Why guarded, not blanket:** I verified `has_dialogue` is an in-scope, production-populated parameter of `generate_ai_video` (def `phase_c_ffmpeg.py:56`, param line 71; the prod caller `controller.py:1700` passes `has_dialogue=has_dialogue`; recursion sites `:180/:228` forward it; `dialogue_native_audio = has_dialogue and voice_mode=="native"` at `controller.py:1676`). So the overlay-dialogue exclusion `not (has_dialogue and not dialogue_native_audio)` is real, not degenerate. This:
- char-landscape→wide, **no dialogue** → `generate_audio=True` → ambient bed preserved ✓ (fixes director-1's silent-clip regression)
- char-landscape→wide, **overlay dialogue** → `generate_audio=False` → silent clip for TTS overlay ✓ (NO double-voice — director-1's caution honored)
- **native dialogue** (any shot_type) → `True` via `dialogue_native_audio` ✓
- genuine `landscape` → **unchanged** (deliberately not touched — keeps blast radius to the routing fix; the latent overlay-dialogue-on-genuine-landscape double-voice is a separate Pair-B follow-up, not this dispatch).
- The 2 non-prod callers (`scripts/_phase3_portrait_preflight.py:181`, `scripts/_veo_recheck.py:57`) may omit `has_dialogue` — benign (worst case: ambient on a preflight clip). No action.

**Test plan:**
- `tests/unit/test_workflow_selector.py:177-191` — the existing parametrized `test_keyword_routes_to_bucket` has 8 landscape keywords on char-bearing shots asserting `"landscape"`; these **break** → update to assert `"wide"`. (This is an UPDATE to an existing test, not just a new RED.)
- New: LTX path, `shot_type="wide"` → `resolution="4k"` (Site 2).
- New: Site 3 truth table — (wide, no-dialogue)→`generate_audio=True`; (wide, overlay-dialogue)→`False`; (wide, native-dialogue)→`True`; (medium, native-dialogue)→`True`.

---

## §3 — Audio-sibling FAMILY fix (fix_with_brief; my flag-propagation design call resolved)

operator-1 reported (`4ad4c21`) 2 audio-loss siblings of the RIFE class. The sweep **confirms** them and finds no new audio-*strip* sites. But grounding revealed the issue is broader than re-mux: it's a **postprocess-variant audio-flag-propagation defect** affecting the whole family.

**Root cause (verified):** `make_take` (`project_manager.py:147-155`) mints a variant with `metadata` only — no audio-flag slot. The shared postprocess call site (`controller.py:2326`) and every action branch (`:2333-2436`) set `variant["path"]` but **never** set `audio_embedded`/`dialogue_audio_in_clip`. The assembler (`cinema_pipeline.py:734-744`) counts a take as embedded only if `_approved_take_metadata` has those flags; `all_shots_embedded` False → it generates + muxes scene-TTS. So:
- **audio-stripping** actions (upscale `lip_sync.py:969`, face_swap `phase_c_vision.py:80` + FaceFusion fallback `:89-101`) → silent clip + no flag → TTS substitution → **wrong voice** (operator-1's finding).
- **audio-preserving** actions (color_grade `-c:a copy`, speed `atempo`) → clip keeps audio but variant unflagged → TTS muxed **on top** → **latent double-voice** (director2-derived; **operator2 must verify RED-first** — confirm a color_grade/speed variant on a dialogue take double-tracks before/after).

**Fix shape (two parts — re-mux is necessary-not-sufficient, per operator-1):**

1. **Re-mux** in the 2 stripping transforms — mirror `lip_sync._restore_audio_track` (`:817`). After download:
   ```
   ffmpeg -i <cloud_output> -i <source_video> -map 0:v:0 -map 1:a:0? -c copy -shortest <remuxed>
   ```
   Best-effort: on re-mux success → output carries audio; on failure → leave video-only (degrades to today's behavior, not worse). FaceFusion CLI fallback needs the same.

2. **Flag-propagation** at the shared call site (`controller.py` ~`:2436`, after the variant path exists, before store):
   ```python
   if base_take and _output_has_audio(variant["path"]):   # ffprobe audio-stream probe — reuse existing helper if present
       _bm = base_take.get("metadata", {})
       if _bm.get("audio_embedded"):
           variant["metadata"]["audio_embedded"] = True
       if _bm.get("dialogue_audio_in_clip"):
           variant["metadata"]["dialogue_audio_in_clip"] = True
   ```
   This makes the **whole family** correct by construction: re-muxed strippers + audio-preserving actions inherit the flag (no TTS substitution / no double-voice); failed-remux strippers stay unflagged (TTS fills — degraded, acceptable).

**Caveat for operator2:** grep for an existing ffprobe audio-stream helper (don't add a new probe if one exists). Rule#13-audit all `:2333-2436` action branches. TDD each: stripping→remux→flag; preserving→flag (double-voice fix); failed-remux→no flag.

---

## §4 — Settings-validation (nan-gate) batch (fix_with_brief) — the sweep's headline class

Beyond the 2 fixed in `0d632eb`, the sweep found **4 major + 5 minor** unguarded numeric-threshold gates where a NaN/±inf settings value silently disables a gate (`score < NaN` always False) or always-passes (`+inf`). Recommend **one shared helper** + a batch, not piecemeal.

**Shared helper** (operator2 to place in a common settings util):
```python
def _finite_or(value, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default
```

**4A — operator2 (Pair-B / shared sites):**
| Site | Sev | Effect of NaN |
|---|---|---|
| `lip_sync.py:493` lipsync_validation_threshold | **MAJOR** | every engine fails the sync gate → always best-of-failed (also flagged by the `0d632eb` verifier's Rule#13). `import math` not yet in lip_sync.py. |
| `cinema/shots/controller.py:2228` coherence_threshold | **MAJOR** | `overall_coherence < NaN` always False → coherence-regen gate never fires. |
| `cinema/shots/controller.py:773` identity_strictness | **MAJOR** | (identity-adjacent — apply the isfinite guard; **Pair-A: sanity-check the fallback default** before land.) |
| `cinema/shots/controller.py:2223` color_drift_sensitivity | minor | drift gate. |
| `cinema/capability_scorecard.py:131/135` lipsync_bar/coherence_bar | minor | **reporting only** — NaN skews scorecard counts, no blocking gate. |

**4B — already fixed** (`0d632eb`): `controller.py:1216` (auto_rife) + `:1356` (motion floor). No action.

**4D — CROSS-LANE → Pair-A director (surfaced via mailbox):** `quality_max.py` is Pair-A's lane (active PuLID work — do not let Pair-B edit it; collision risk). The sweep found 4 NOVEL major/minor sites there, same `_finite_or` helper applies:
- `quality_max.py:1069` regen_floor — **MAJOR**: NaN → `needs_regenerate` never fires → **identity floor silently bypassed for character shots with low ArcFace** (a capability regression in Pair-A's domain — the highest-value nan-gate find).
- `quality_max.py:1067` halt_composite + `:1068` halt_arc — **MAJOR**: halt loop never early-exits → burns full N-budget.
- `quality_max.py:1086` identity_threshold — minor: corrupts rolling-history `passed` flag → skews `get_adaptive_pulid_weight`.

---

## §5 — tmpfile cleanup-hardening batch (fix_with_brief; LOW priority — leaks, not output-correctness)

All minor (disk leak / potential clobber on concurrent same-project assembly), none affect rendered output. Batch when convenient:
- `audio/dialogue.py:685-687` (operator2's item A) — cleanup of concat_list+silence_file is **inside the try**, skipped on ffmpeg `CalledProcessError@:695`. Move to `finally`.
- `lip_sync.py:307 / :618` (**NOVEL**) — stash `.tmp` candidates from failed engines never cleaned on early-return success.
- `cinema_pipeline.py:1270` `_concat_foley_track` + `:1306` `_concat_dialogue_track` (**NOVEL**) — fixed-name lists in `temp_dir`, no cleanup, exception swallowed → clobber risk across concurrent same-project assemblies.
- `cinema_pipeline.py:1406` `_concat_copy` (**NOVEL**) — `concat_list_{tag}.txt` never cleaned; disk accumulation (not clobber, tag varies).
- `phase_c_ffmpeg.py:984` (D4 nit) — write-phase leak (see §1 nits).

---

## §6 — Priority order for operator2
1. **char-landscape 3-site** (§2) — correctness (zero-identity char shots); co-signed, ready.
2. **audio-sibling family** (§3) — wrong-voice on dialogue takes; verify the double-voice angle RED-first.
3. **nan-gate batch** (§4A) — `_finite_or` + Pair-B/shared sites.
4. **tmpfile batch** (§5) — leaks; lowest.
Optional §1 nits folded opportunistically.

**Standing forward backlog (⭐#2, principal-gated — NOT in this dispatch):** SyncNet→pixel-diff scorer redesign + loud-gate WARNING; Suno reconnect (blocked on the `suno_api_base` principal decision); silence-trim DEFER doc-fix. These are the headline items and need the principal's steer (see the PM2 handoff §"Decisions for the principal").

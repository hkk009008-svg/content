# Director transplant handoff — 2026-06-09: MAX-TIER pod validation COMPLETE + 9:16 portrait latents validated

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-09-portrait-LIVE-on-main.md`
(its #1 pickup — operator cold Lane V on lip_sync `dd78208` — is CLOSED ✅ SAFE this
session by the operator, see "Operator parallel work" below).

## Ground truth (verified this wrap)

- **HEAD == `e5a810c`** (this handoff commit) — local **ahead 2** of origin/feat `5214bf0` (push USER-gated). Director's ONLY repo commit this session = this handoff; all prior work was pod gens + reads.
- **Rule #5 race-ack:** intervening **`4d68c86`** = operator `fix(tooling)` (doc-verifier positional symbol-anchor binding) landed in the shared tree DURING this handoff write; `read-tree HEAD` picked it up so this commit sits on top. Operator may still be live.
- **origin/feat == `5214bf0`** (pushed); `4d68c86` + `e5a810c` are local/unpushed.
- **origin/main == `1870e59` GREEN** (portrait 9:16 + lip_sync M-1-twin live).
- gate OPEN `["16:9","9:16"]` (`cinema/aspect.py:25`).
- **§15 ci_smoke OK** at `5214bf0`.
- **suite: 1935 passed / 0 failed** at `5214bf0` (re-run this wrap; session-start was 1923/0 at `62918c3`; +12 from operator's `3fa29c9` `status.py mailbox-unread` CLI tests).
- `claude --version` **2.1.169** (Rule #17 ≥2.1.154 hard-gate SATISFIED).

## What director did this session (NO repo commits — all pod validation + analysis)

### 1. Post-roadmap reassessment (Rule #17 workflow `wf_198f53fe-7aa`, read-only)
6 cold investigators + synthesis, citations spot-checked 6/6. **5 ranked next-directions** (see "Open roadmap" below). 13 carry-forwards verified CLOSED (incl. Sonnet-retirement, vision MIME bug, F5 visual_findings FE render [MEMORY.md was STALE — it IS rendered `ReviewStage.tsx:825-828`], LLM client timeouts, most STRATEGIC_REVIEW P0/P1).

### 2. MAX-TIER pod validation (#1 reassessment lever) — EXECUTED on live Novita pod
- **Pod**: Novita `07ed667185a895bb` / SSH proxy `35.164.116.189:38597`, **RTX 6000 Ada, 47 GB VRAM**. Access saga: key auth rejected by Novita proxy (console-registered keys only); password rate-limited after many attempts. ComfyUI brought up by USER (`python main.py --listen`); director drove validation via **HTTPS gateway + production code** (`generate_ai_broll_max`), no SSH needed.
- **`/object_info` probe: 1106 node classes; ALL 13 critical custom nodes present** — `SUPIR_model_loader_v2`/`SUPIR_sample`/`SUPIR_decode`, `ApplyPulidFlux`, `FaceDetailer`, `ReActorFaceSwap`, `OptimalStepsScheduler`, `SamplerCustomAdvanced`.
- **DOC CONTRADICTION RESOLVED**: hires-fix Pass-2 is **WIRED and FIRES** on the real pod (dry-run prep: node 18 created @ denoise 0.40/18 steps, `901.sigmas→["18",0]`; SUPIR/FaceDetailer/ReActor/PuLID all active; SaveImage←node 950 4K master). → `docs/pipeline_status.toml` hires_fix `status="stubbed"` (+ "always pruned by `_inject_post_passes`") is **FALSE**; `ARCHITECTURE.md §8.3` "wired" is **correct**. (`_inject_post_passes` never prunes 900/901/902; only availability-pruning does, and all classes are present.)
- **Gen runs** (real production path, fp16, N capped via `get_max_quality_params` wrap; ref `domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg`; evidence in `/tmp/*.png` — EPHEMERAL):
  - N=1 baseline (hires 0.40, SUPIR cfg 4.0): **4K 3840×2160, arc 0.831**, 8.5 min.
  - Sweep (same seed 741305880): supir_off `arc 0.847`; **hires 0.25 `arc 0.477` — DISINTEGRATED** (image shatters); hires 0.55 `arc 0.837`; **SUPIR cfg 2.0 `arc 0.851` (BEST + faster)**.
  - Clean-bg confirm (clean-backdrop prompt + neg-prompt + SUPIR cfg 2.0): **4K, arc 0.829, background fixed**.
  - **9:16 portrait** (forced aspect via `cinema.context.get_project_setting` patch): **2160×3840 PORTRAIT, arc 0.866, transpose validated** (no distortion) → closes the long-parked on-pod 9:16 latent validation.
- **Key findings**: (a) **SUPIR cfg 2.0 > 4.0** (better identity, faster, same polish); (b) **hires-denoise has a cliff** — 0.40/0.55 safe, **0.25 catastrophic**; (c) the **background smear is base-FLUX/prompt, NOT a post-pass** — fixed by explicit backdrop prompt + people-exclusion negative; (d) minor recurring neck/collarbone artifact (a `deformed/elongated neck` negative term would help).

## PENDING follow-ups — #1 PICKUP cluster (director-lane, evidence-backed, NO pod needed)

These were produced by this session's validation but NOT landed (user said "handoff"). Each via TDD/commit, cite the runs above (ADR-013):
1. **doc-truth**: `docs/pipeline_status.toml` hires_fix `status="stubbed"`→`wired`/validated (+ drop the "always pruned" note); resolve in `ARCHITECTURE.md`'s favor.
2. **code**: SUPIR `supir_cfg_scale` default **4.0→2.0** in `workflow_selector.py` `MAX_QUALITY_TEMPLATES` — sweep-proven identity+speed win.
3. **code**: hires_fix_denoise validation floor **0.2→0.40** at `quality_max.py:118` (`"hires_fix_denoise": ("numeric", float, 0.2, 0.6)`) — the 0.25 disintegration proves 0.2 floor is unsafe.
4. **prompt guidance**: clean-background recipe (explicit backdrop + people-exclusion negative) into `docs/PROGRAM-MANUAL.md` §5 capability playbook.
5. (optional) `_accept_or_reject` / probe **fail-open** hardening — `quality_max.py:282` (`/object_info` fail → "assume all-available" → no pruning → silent production-tier fallback on a degraded pod) + `phase_c_ffmpeg.py:1318-1320`. Reliability ADR (see Open roadmap #5).

## Open roadmap (reassessment `wf_198f53fe-7aa` — the other 4 directions)

2. **Multi-char identity gate** (capability, M, director) — every live identity gate scores only `chars[0]`; `validate_multi_identity` (`domain/continuity_engine.py:118`) has ZERO production callers; `controller.py:1069` passes `[chars_in_frame[0]]`. 2+ char shots drift silently. Part (a) wiring; part (b) per-region identity injection = design fork → brainstorm/spec.
3. **Video-gen timeouts** (reliability, S–M, director) — `fal_client.subscribe` untimed at `phase_c_ffmpeg.py:469/540/636/702`; Seedance poll GET `:816` untimed (POST `:807` IS); all `urlretrieve` untimed; no `socket.setdefaulttimeout`. Unbounded hangs.
4. **`STRATEGIC_REVIEW-2026-06-09` successor** (doc, M, director) — 05-24 review stale (its own 6-mo signal fired); P1-2 monolith REGRESSED `cinema_pipeline.py` 1011→1669 LOC; P2-1 `competitive_generation=True` unconditional (`project_manager.py:327`); P4 product Qs (vendor sprawl, multi-user, console) open.
5. **`_accept_or_reject` portrait fail-open ADR** (reliability, S) — `phase_c_ffmpeg.py:1318-1320` fail-opens on probe failure (documented net-not-primary); + the probe fail-open in #5 above.

## Operator parallel work (reconciled — operator was LIVE during my pod session, NOTHING OWED, offline)

- **lip_sync Lane V on `dd78208` → ✅ SAFE** (prior handoff's #1 pickup CLOSED).
- `5214bf0` `docs(manual)` lip_sync anchor sweep; `feaa1d2` operator wrap; `83ea503` coord.
- Protocol upgrades (user-directed, Rule #17 `wf_9c032336-468`): **`3fa29c9`** `chore(tooling)` `status.py mailbox-unread <seat>` (Rule #20.1 live-recompute instrument; TDD 5 tests) + **`884c452`** `docs(protocol-log)` Candidate #9 filed N=1 ("no volatile counts in `current_task`").

## OPEN director requests from operator (Rule #8 — 3 unread processed this wrap; cursor → `2026-06-09T05-43-35Z`)

- **① (HIGHEST LEVERAGE) — discharge the OVERDUE v5.6 Rule #17 retro** (`CLAUDE.md:1716` C4 mandates it "at v5.6") **+ fix VERIFIED-STALE `CLAUDE.md:1728-1729`** — it claims workflows unavailable (`2.1.74`/`2.1.149` < `2.1.154`); ACTUAL `claude --version` **2.1.169**, feature used **~18× this arc** (17 director `wf_*` incl. my `wf_198f53fe-7aa` + 1 operator `wf_627fd99b-61e`). Per ADR-013 fix the stale claim **in the same commit** as the retro. Director-lane, no proposal cycle. Retro datapoint: operator's first workflow-use + my Lane V both held (3 cold lenses reached the Rule #13 angle; R-OP-1 spot-check held) — frame as **~18-run ARC, not N=1**.
- **③ — advisory amendment to Rule #20.1** (operator-drafted): "live recompute SHOULD use `scripts/status.py mailbox-unread <seat>` (`3fa29c9`) over hand-rolled `ls|awk` (two sharp edges proven 2026-06-09)". Advisory, not MUST. Ship via proposal→REPLY or counter-refine.

## POD — needs USER action

**Pod is still UP (metered).** Director cannot deallocate a Novita billed instance from here (no Novita API creds; SSH rate-limited; an SSH `shutdown` wouldn't stop the lease). **USER must terminate the instance in the Novita console** to stop billing.

## Operational notes

🔑 `env -u GIT_INDEX_FILE` for pytest+smoke; pathspec commits (`-m` before `--`, `git add` new files); `git read-tree HEAD` after Workflow/peer-commit. Pod validation drove the production path via the HTTPS gateway (`settings.comfyui_server_url` from `.env`) — no SSH needed once ComfyUI serves. Validation drivers + images are in `/tmp/` (EPHEMERAL — arc scores/dims captured above are the durable record).

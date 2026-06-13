# Operator Handoff — Context Transplant 2026-05-29 cycle-17 POST-MID-4

**From:** Operator-seat (cold-pickup at `7e8c9ba`/`bca5ee2` → SHA-ref checker build → d90036b finding → doc-maintenance dispatch N=2 → ARCHITECTURE.md §16/§17 sync → Novita GPU bring-up assist → handoff)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `a2798ad`; **origin == HEAD (0 ahead / 0 behind — everything pushed)** at write-time. Tree clean except untracked `.claude/launch.json` + `logs/` (not mine).
**Supersedes:** [HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-3.md](HANDOFF-operator-transplant-2026-05-29-cycle17-postMID-3.md).
**Companion docs:** [CLAUDE.md](../CLAUDE.md) Rules #1–#18 · [DECISIONS.md](../DECISIONS.md) ADR-019 · [ARCHITECTURE.md](../ARCHITECTURE.md) (§16/§17 synced this session).

> **⚠️ POST-WRITE RECONCILIATION (director shipped 2 commits during this Write — Rule #5/#7 race-ack; corrections override the body below):**
> - **Lane V #26 (⚠️A / open #1) is director-INVITED, operator-DISCRETION — NOT a mandatory "#1 task."** Director's `T06-17-07Z` event explicitly leaves it "your call": the M1 fix `7d15180..a2798ad` is a small fully-TDD'd slice with a **real-ffmpeg integration test** (RED pre-fix → GREEN) and **no `cinema_pipeline.py` change** — the #25 standalone-mp3 caveat resolved *structurally* (voice source keys on dialogue-mp3 existence at `cinema_pipeline.py:1362`, not on stitch audio). Cold second-opinion is valuable but not blocking. → **Novita bring-up (⚠️B) is the clearer live priority.**
> - **Open #5 DECISIONS.md flag → CLOSED at `1aff64e`** — director *relocated* the `ADR-NNN` template to the true bottom (Guard-1: it's the intentional template, stranded between ADR-015/016 when ADR-016..019 were appended after it; moved, not pruned). ADR headers now contiguous 001-019.
> - **Operator cursor advanced `T03:28:28Z` → `T06:17:07Z`** (consumed the director's M1-close / doc-maint-ack / DECISIONS event). Director cursor → `T04:47:48Z`. **0 unread both directions.** (Supersedes the Mailbox + cursor section below.)
> - HEAD moved `a2798ad` → `5b11256` (+ `1aff64e`) → this handoff. Body "at write-time" values stand; trust `git log` at pickup.

---

## TL;DR (2 min)
Built and shipped the **SHA-ref checker** (the handoff's OPEN #2 verifier-buildout) — Tier-2 commit-SHA citation verifier in `check_doc_claims.py` (`af6d69f`). On its **first live run it caught a real multi-session-old drift**: CLAUDE.md cited orphaned v4-ship SHA `d90036b` (6×); director closed it → `7da49ed` at `435efd2`. Then ran the **first operator Rule #18 doc-maintenance dispatch** (N=2, read-only): verifier-covered surfaces all clean, 0 mechanical, **3 claim-changing ARCHITECTURE.md §16/§17 stale-facts corrected** at `e726976` (0-hallucination dispatch). Graduation null-hypothesis HOLDS (ephemeral suffices; N<3). Then pivoted to **assisting the user's Novita GPU pod bring-up** (see ⚠️ below — IN-FLIGHT).

**Baseline:** pytest **1229 passed / 3 skipped** (verified at handoff; director's M1 fix added 6 tests). §15 smoke **OK** (`ci_smoke.py` exit 0 at handoff — anchors/sha/manifest gates all clean). **GPU pod DOWN but bring-up actively in progress on Novita.**

---

## ⚠️ READ FIRST — two LIVE items the next operator must pick up

### A. Lane V #26 is TRIGGERED and PENDING (operator obligation, not yet dispatched)
Director shipped the **F1 M1 mixed-audio fix** as a `fix`+`refactor` pair while I was on the Novita assist — Lane V was triggered but the user said "handoff" before I dispatched it. **This is your #1 task.**
- **Commits to review (coalesce per Rule #9 v4.1 CC-1 — tightly coupled, same xfade contract surface):**
  - `7d15180` `refactor(ffmpeg): _build_xfade_filtergraph include_audio -> audio_flags (behavior-preserving)` — phase_c_ffmpeg.py +25/−12 + tests
  - `a2798ad` `fix(ffmpeg): close Lane V #25 M1 — anullsrc-pad mixed-audio xfade_concat (preserve embedded audio)` — phase_c_ffmpeg.py +63/−19 + test_xfade_transitions.py +81
- **Why operator is the right reviewer:** this is the EXACT path prior operator Lane V #24 (F1 CRITICAL, live-repro'd) + #25 (M1 flagged, anullsrc-pad direction suggested) covered. You have inherited context; dispatch a cold independent reviewer anyway (Rule #9 — don't contaminate the prompt with #24/#25 findings).
- **Verification angle (Rule #9 emphasis):** the M1 edge was "mixed audio-presence inputs drop audio." Verify the anullsrc-pad approach: (a) silent inputs padded so EVERY input has an audio track → uniform acrossfade, (b) **does NOT interfere with the standalone-mp3 voice mux** for silent-engine dialogue scenes (`cinema_pipeline.py:1378-1380` was the #25 hedge — verify it, don't re-assert). GPU still down → likely code+repro verification, not end-to-end.
- Range: `e726976..a2798ad` (skips the docs(spec)/docs(plan) commits 6831a35/d230579/b39ee2d which are design, not code).

### B. Novita GPU pod bring-up — IN-FLIGHT (user driving on the pod, operator guides)
The user is replacing the DOWN RunPod pod with a **Novita H100 SXM 80GB** instance to restore ComfyUI image-gen.
- **Instance:** ID `e1869645623bc25b` · GPU H100 SXM 80GB · 22 vCPU / 150 GB RAM · template `novitalabs/pytorch:2.4.0-cuda12.4-ubuntu22.04` (✅ cu124 matches H100 sm_90 — no torch reinstall) · On-Demand Secure Cloud.
- **SSH:** `ssh -p 58867 root@proxy.us-ca-nas-11.gpu-instance.novita.ai` — **operator CANNOT drive it** (no key in the non-interactive Bash shell → `Permission denied (publickey)` on probe). User drives interactively; operator guides + verifies.
- **Status at handoff:** user is ON the pod (`root@e1869645623bc25b:/workspace#`), about to run (repo is **PUBLIC** → token-free):
  ```bash
  cd /workspace && df -h /workspace          # need ≥50 GB free first
  git clone https://github.com/hkk009008-svg/content.git && cd content
  bash scripts/setup_runpod.sh
  ```
- **`setup_runpod.sh` = PRODUCTION-tier provisioning** (`scripts/setup_runpod.sh`, 369 lines, provider-portable): installs ComfyUI + cubiq PuLID + balazik ComfyUI-PuLID-Flux + InsightFace/antelopev2, downloads FLUX-dev-fp8 + t5xxl_fp8 + clip_l + ae + PuLID + RealESRGAN (~20 GB), launches ComfyUI on `0.0.0.0:8188`, self-checks PuLID nodes via `/object_info`. **Does NOT install SUPIR/HiDream** (max-tier is a separate follow-on).
- **Next steps after bootstrap completes (operator guides):**
  1. Confirm script tail shows `OK: PulidInsightFaceLoader registered` / `OK: ApplyPulidFlux registered`.
  2. Sanity: on pod, `python -c "import torch;print(torch.__version__,torch.version.cuda,torch.cuda.is_available())"` → expect `2.4.x 12.4 True` (the script's unpinned `pip install torch` *should* no-op on cu124 image, but verify).
  3. Expose Novita **port 8188** (HTTP) → get the public endpoint URL.
  4. Set `COMFYUI_SERVER_URL=https://<novita-8188-endpoint>` in the **local** `.env`.
  5. Verify: `curl "$COMFYUI_SERVER_URL/object_info" | head -c 200` (JSON) + `.venv/bin/python scripts/status.py` → pod flips **DOWN → UP**.
- **Once pod is UP:** the entire image-gen backlog (HiDream firing, dialogue/storyboard/HiDream validation, scene-transitions end-to-end incl. the new M1 fix, B2 wire) unparks.

### C. (carry-forward) 6 local hookify rules ACTIVE
Unchanged from POST-MID-3. `.claude/hookify.*.local.md` (gitignored, shared WT): `block-git-add-all`, `block-force-push`, `warn-git-push`, `warn-no-verify`, `warn-state-asserting-write` (this Write tripped it — expected), `warn-pytest-without-venv`. `warn` surfaces user-side, not in your tool result.

---

## What this operator session shipped (all on origin)
| Item | Commit(s) | Status |
|---|---|---|
| **SHA-ref checker** (Tier-2: resolve + reachable + quoted-subject) + `--sha-refs`/`--show-subjects` + ci_smoke WARN gate + 11 tests | `af6d69f` | ✅ 45 verifier tests green; caught real drift on first run; **OPEN #2 done** for the SHA-ref claim-type |
| **d90036b finding** → mailboxed to director | `03fb5f0` | director closed at `435efd2` (d90036b→7da49ed 6×, Guard-1 re-verified) |
| **Doc-maint dispatch N=2** (Rule #18, read-only) → 3 ARCHITECTURE.md §16/§17 stale-facts corrected | `e726976` | ✅ §16 count 737→1223, skip-lines :197,221→:203,232, §17 5 orphans→load-bearing; **OPEN #1 done** |
| **Coord event** (doc-maint notice + N=2 graduation datapoint + DECISIONS.md:503 flag) + cursor → T03:28:28Z | `31f67d9` | ✅ delivered to director |

## Director concurrent activity (all landed + pushed)
`6911477` ARCHITECTURE §9.7 arch-sync · `1dc72d2` director POST-MID-4 handoff · `20b354a` version-agnostic Co-Authored-By trailer · `7682c12` delete dead `_build_transition_prompt` + re-anchor −29 (resolved the transient ARCHITECTURE anchor drift) · `435efd2` d90036b→7da49ed fix · `d2b71a4` d90036b-close coordination · **`6831a35`+`d230579`+`b39ee2d` xfade M1 design+spec-R2+plan · `7d15180`+`a2798ad` the M1 refactor+fix (→ your Lane V #26).**

---

## What's OPEN (cold-start priorities)
1. **Lane V #26 on `7d15180`+`a2798ad`** (the M1 anullsrc-pad fix) — TRIGGERED, not yet dispatched. See ⚠️A. **#1 task.**
2. **Novita pod bring-up** — IN-FLIGHT. See ⚠️B. Finish bootstrap → wire COMFYUI_SERVER_URL → pod UP.
3. **ARCHITECTURE.md §16 test count minor-drift:** I set it to **1223**; director's `a2798ad` added 6 tests → actual now **1229**. Bundle the bump into your Lane V #26 / a Lane D pass on the ffmpeg change (ARCHITECTURE §9.7 may also want an M1-fix sync). *This is exactly why the §16-count check is a priority next verifier-buildout claim-type (see #4) — pinned counts drift commit-by-commit.*
4. **Verifier-buildout (continues the Rule #18 bridge-sunset).** SHA-ref claim-type DONE (`af6d69f`). Next automatable types the N=2 dispatch flagged: **§16-test-count-vs-pytest** + **§17-orphan-caller-grep** — both would push doc-maintenance residual → ~0 on those claim-types.
5. **DECISIONS.md:503 `## ADR-NNN — <placeholder>`** — lingering template between ADR-015/016. Flagged to director (DECISIONS.md is strategic-seat-default); their discretion.
6. **GPU-gated backlog (unparks once Novita pod UP):** HiDream firing, B2 wire, SD3_5 dispatcher, max-tier (SUPIR/HiDream — NOT in setup_runpod.sh, separate provisioning), upscale, dialogue/storyboard/HiDream validation, scene-transitions end-to-end (incl. the new M1 fix).

## Cold-start checklist
```bash
cat STATE.md                                                  # hook-derived; filesystem/git wins (Rule #8)
.venv/bin/python scripts/status.py                            # git/mailbox/ADR/anchor/pod dashboard
.venv/bin/python scripts/ci_smoke.py                          # expect OK (anchor + sha + manifest gates)
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1   # expect 1229 passed, 3 skipped
.venv/bin/python scripts/check_doc_claims.py --sha-refs       # NEW this session — expect "no drift"
git log --oneline -12
git fetch origin main && git rev-list --count origin/main..HEAD   # expect 0 unless new work
cat coordination/mailbox/seen/operator.txt                    # T03:28:28Z
```
**Read order:** STATE.md → `status.py` → THIS doc (⚠️A + ⚠️B first) → mailbox unread → CLAUDE.md Rules #9 (Lane V) + #18 (doc-maint).

## Mailbox + cursor
| Cursor | Value |
|---|---|
| operator.txt | **T03:28:28Z** (consumed director's d90036b-close event) |
| director.txt | T02:37:11Z (their file not-bumped; their close event body claimed T03:24:58Z — director's bookkeeping, harmless) |
**0 unread for operator.** Director shows unread=2 (my `03-24-58Z` finding [already acted on @435efd2] + `04-47-48Z` doc-maint notice [fresh]). Latest operator sends: `T04-47-48Z` (doc-maint dispatch notice), `T03-24-58Z` (d90036b finding).

## Metrics
- **Pytest:** `1229 passed / 3 skipped` (verified at handoff). §15 smoke **OK** (`ci_smoke.py` exit 0). Anchors clean, `--sha-refs` clean.
- **New tooling shipped:** SHA-ref checker (`check_sha_refs`/`audit_sha_refs` + 11 tests; ci_smoke SHA WARN gate). Verifier now covers line-anchors + manifest-symbols + **SHA-refs**.
- **Doc-maint dispatch:** N=2 (read-only); 0 hallucinations (all 3 findings R-OP-1 re-verified before landing); graduation null-hypothesis holds.
- **Subagents this session:** 1 (the doc-maintenance dispatch). Most work (SHA-ref build via TDD, ARCHITECTURE fixes, Novita assist) in main context.
- **Protocol:** Rules #1–#18 live; 20 ADR slots (ADR-019 latest + 1 `ADR-NNN` placeholder to prune). 6 local hookify rules active.
- **origin == HEAD `a2798ad`, 0 ahead** at write-time. GPU pod DOWN, **Novita bring-up in progress.**

---
Signed,
Operator-seat — 2026-05-29 cycle-17 POST-MID-4. SHA-ref checker shipped (`af6d69f`, caught orphaned `d90036b` first run → director closed `435efd2`); first operator doc-maint dispatch (Rule #18 N=2) corrected ARCHITECTURE §16/§17 (`e726976`, 0-hallucination); graduation null-hypothesis reinforced. **Next operator: (1) Lane V #26 on the M1 ffmpeg fix `7d15180`+`a2798ad` — triggered, undispatched; (2) finish the Novita H100 pod bring-up — user is mid-bootstrap on the pod.** HEAD `a2798ad`, origin-synced, 1229/3 green, smoke OK, cursor T03:28:28Z, pod DOWN (Novita bring-up live).

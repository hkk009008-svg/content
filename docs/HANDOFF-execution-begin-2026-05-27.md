# Execution Begin Handoff — 2026-05-27

**From:** Director-seat (cycle-15 entry end-of-session post-pod-restart-completion + A5/A9 GREEN + brief v1.0 SHIP)
**To:** Whoever starts the test gauntlet — director-seat OR operator-seat OR both (synchronous joint per Q9)
**Purpose:** Focused begin-testing pickup. **NOT** a substrate transplant handoff — that's at [HANDOFF-director-transplant-2026-05-27-cycle15.md](HANDOFF-director-transplant-2026-05-27-cycle15.md) (`dd2e84e`) + operator-side at [HANDOFF-operator-transplant-2026-05-27-cycle15.md](HANDOFF-operator-transplant-2026-05-27-cycle15.md) (`120d087`). Read those for cycle-15-entry state. **This doc is the first-mile execution-kickoff guide.**

---

## TL;DR — what's ready, what's gated

**🟢 Pod is fully serving + brief is v1.0 + .env is updated. The ONLY remaining gate is user-principal execution authorization.**

| Item | Status | Evidence |
|---|---|---|
| RunPod pod `525nb9d5cc0p3y` | 🟢 RUNNING | `curl -sI "https://525nb9d5cc0p3y-8188.proxy.runpod.net/object_info"` → HTTP/2 200 |
| ComfyUI version | 🟢 0.22.0 | `/system_stats` confirms |
| GPU | 🟢 NVIDIA RTX 6000 Ada (48GB VRAM, 47.4GB free) | `/system_stats devices[0]` |
| Host RAM | 🟢 540GB total, 466GB free | `/system_stats system.ram_*` |
| PyTorch | 🟢 2.4.1+cu118 (matches pod CUDA runtime) | verified post-pin |
| Required PuLID-FLUX nodes | 🟢 4/4 registered (ApplyPulidFlux, PulidFluxModelLoader, PulidFluxInsightFaceLoader, PulidFluxEvaClipLoader) | `/object_info` keys |
| IPAdapter nodes | 🟢 3/3 (IPAdapter, IPAdapterUnifiedLoader, IPAdapterModelLoader) | same |
| FLUX core nodes (built-in) | 🟢 7/7 (KSampler, CheckpointLoaderSimple, CLIPTextEncode, FluxGuidance, EmptyLatentImage, VAEDecode, VAELoader) | same |
| Total ComfyUI node classes | 🟢 867 | `/object_info` length |
| FLUX checkpoint | 🟢 `FLUX1/flux1-dev-fp8.safetensors` (~24GB) | `/object_info/CheckpointLoaderSimple` |
| FLUX VAE | 🟢 `ae.safetensors` | `/object_info/VAELoader` |
| PuLID weights | 🟢 `pulid_flux_v0.9.1.safetensors` (~1.1GB) | `/object_info/PulidFluxModelLoader` |
| EVA-CLIP | 🟢 `EVA02_CLIP_L_336_psz14_s6B.pt` (~2GB) | downloaded to `/workspace/ComfyUI/models/clip/` |
| InsightFace antelopev2 | 🟢 unzipped at `/workspace/ComfyUI/models/insightface/models/antelopev2/` | manual unzip during deploy |
| Local `.env` | 🟢 `COMFYUI_SERVER_URL=https://525nb9d5cc0p3y-8188.proxy.runpod.net` | this commit |
| Brief | 🟢 v1.0 SHIP | this commit; status line in `docs/BRIEF-comprehensive-test-2026-05-27.md` line 17 |
| Pre-flight A1-A4 (Tier A static) | ⏳ NOT YET RUN — Tier A dry-run first | unit tests / smoke / tsc / lint not re-run this session post-edits |
| Pre-flight A5 (HTTP head) | 🟢 200 | this session |
| Pre-flight A6-A8 (env keys / docs / OPERATIONS) | ⏳ NOT YET RUN — Tier A includes these | |
| Pre-flight A9 (ComfyUI deeper probe) | 🟢 verified manually this session (4-of-4 PuLID-Flux + 7-of-7 FLUX core + 3-of-3 IPAdapter + checkpoints + VAE) | brief §3 A9 lines 256-273; class name `PulidFluxInsightFaceLoader` corrected at v1.0 SHIP |
| **User-principal execution authorization** | 🔴 PENDING | only remaining gate |

**Test count baseline at handoff: 925 pass / 3 skip / 0 fail. §15 smoke OK. HEAD: `dd2e84e` (pre-this-commit; will be cycle-15-close + v1.0 commit when shipped).**

---

## How to begin testing — first 30 minutes

**These are the literal steps to go from "pod is ready" to "Tier A is GREEN and Tier B can start". No `Agent` dispatches required — all steps are direct commands.**

### Step 1 — verify currency at session start (~2 min)

Per Rule #7 pre-commit re-verify + Candidate #7 carry-forward inheritance:

```bash
# 1. State snapshot
git log --oneline -5
git rev-parse HEAD            # should be near dd2e84e + this commit
cat STATE.md                  # gitignored local; regenerated on HEAD move

# 2. Pod still reachable + still ready?
POD_URL=$(grep '^COMFYUI_SERVER_URL=' .env | cut -d= -f2)
curl -sI "$POD_URL/object_info" --max-time 10 | head -1
# Expected: HTTP/2 200

# 3. Test baseline still green?
.venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
# Expected: 925 passed, 3 skipped, 0 failed

# 4. §15 smoke
.venv/bin/python scripts/ci_smoke.py
# Expected: OK
```

**If any fails**, do NOT proceed — diagnose first. Most common: pod stopped (RunPod console → Start); test baseline shifted (recent commit broke something — `git log` + bisect).

### Step 2 — Tier A pre-flight (substrate verification; ~30 min; $0)

Run the brief's full pre-flight A1-A9 block (`docs/BRIEF-comprehensive-test-2026-05-27.md` §3 lines ~201-276). The session that re-runs A9 should use the **v1.0-corrected node names** (PuLID with single capital P, not all-caps PuLID).

For each Ax, capture output as a comment in this doc OR in a separate `docs/test-cells/A-<UTC-ts>.md`. Per §1.5 operational discipline.

Tier A passes ⇒ Tier B unblocks.

### Step 3 — request user-principal execution authorization

Before Tier B (real generation costs), surface to user-principal:

> "Tier A pre-flight is GREEN. Brief v1.0 ready. Pod `525nb9d5cc0p3y` reachable. Estimated Tier B + C + D budget per cycle-15 close: $15-25 base + re-runs, $50 hard cap (user-§9 Q6). Per Q9 synchronous joint, both seats should be available concurrently for execution. **Authorize Tier B start?**"

User confirms ⇒ proceed.

### Step 4 — Tier B (single-shot probe; ~$3-7; ~15-30 min)

Create the fresh minimal project per user-§9 Q6:
- 1-2 scenes
- 1 character (with PuLID identity reference photo)
- 1 location
- 1 dialogue line
- N≥1 shot in each scene

Run the pipeline end-to-end on the minimal project. Capture per-cell PREDICTION vs ACTUAL per brief §4 predictive harness format. Cell artifacts at `docs/test-cells/<cell-id>-<UTC-ts>.md` per §1.5 telemetry convention.

Surface findings per cell: PASS / MINOR / MAJOR / FALSIFIED. INSIGHT-only subjective signals NOT classified into pass/fail (per v0.9.1 F-11 tightening).

### Step 5 — Tier C (full reel; deferred to next-session-start; ~$8-15; ~1-2 hours)

After Tier B clean → user re-authorizes Tier C → multi-shot reel on the same minimal project (or extended project) → 5-10 shots × keyframe + motion + assembly → screening gate → final reel.

### Step 6 — Tier D (parameter sweep; optional; ~$1-5; ~1 hour)

Per cell artifact convention. Inline `tune:` / `prompt:` / `fix:` commits per user-§9 Q8.

---

## Cost + budget reminders (user-§9 answers)

| Limit | Value | Source |
|---|---|---|
| Hard ceiling | $50 USD | Q6 user-principal |
| Soft warning trigger | $40 (auto-STOP per §1 authority precedence) | brief §1 |
| Tier scope | Tier B + C + D (no Surface A+B per Q7 — deferred to later cycle) | Q5+Q7 user-principal |
| Sample project | Fresh minimal (~$3-7) | Q6 user-principal |
| Adjustment commits | Inline per-finding (Rule #15 advisory matrix) | Q8 user-principal |
| Joint execution model | Synchronous (both seats observe real-time) | Q9 user-principal |
| Timing | Cycle 16+ (no cycle-15 alignment pressure) | Q5 user-principal |

`cost_tracker.py` enforces the $50 ceiling at pipeline level. If invocation approaches $40, STOP signal fires.

---

## Risks + things to watch during execution

**HIGH-watch:**

- **Pod state** — RunPod bills by the second. If you pause between Tier B and C, **stop the pod** in RunPod console (Start/Stop button). Models persist on `/workspace` volume across stop/start. On re-start, ComfyUI deps in container were wiped — **MUST re-run the manual pin block from cycle-15 close** before ComfyUI will start:
  ```bash
  pip install --ignore-installed blinker
  pip install --upgrade --force-reinstall torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu118
  pip install -r /workspace/ComfyUI/requirements.txt
  pip install --upgrade --force-reinstall torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu118
  ```
  Sequence matters: requirements.txt may bump torch; final pin re-asserts. Then restart ComfyUI:
  ```bash
  pkill -9 -f "main.py" 2>/dev/null; sleep 3
  cd /workspace/ComfyUI
  nohup python main.py --listen 0.0.0.0 --port 8188 > /workspace/comfyui.log 2>&1 &
  sleep 90 && curl -s http://127.0.0.1:8188/system_stats | head -3
  ```

- **PuLID-FLUX is the load-bearing identity path.** Brief uses `pulid.json` workflow at `phase_c_assembly.generate_ai_broll`. If keyframe generation produces identity-drift outputs, first check PuLID weights are being loaded (`/object_info/PulidFluxModelLoader` should list `pulid_flux_v0.9.1.safetensors`; not the SDXL file).

- **ReActor failed to import** (torch 2.4.1 doesn't expose `torch.distributed.tensor.device_mesh` which was added in torch 2.5+). This is **NON-BLOCKING** for the gauntlet — ReActor is for face-swap, not used in the brief's main flows. `quality_max.py:_probe_node_availability` prunes it gracefully. Workflows that explicitly invoke ReActor (none in production tier; possibly in max-tier face-swap shot types) would degrade — surface as a finding if observed.

**MEDIUM-watch:**

- **Pre-existing test failures masking new ones.** Baseline 925/3/0 — verify at session start; if a new failure appears, distinguish it from baseline before classifying as cycle-16 regression.

- **Cost overrun risk** in Tier B/C: motion generation (Veo via Vertex if invoked) is $0.50-1.00 per 5s clip. A 5-10 shot Tier C reel can hit $5-10 in motion alone. `cost_tracker` enforces ceiling; surface immediately if approaching.

- **PuLID memory peaks** during keyframe generation: 48GB VRAM is plenty for `pulid_flux_v0.9.1` (which uses ~12-18GB peak), but if max-tier (SUPIR + N=8 best-of) is invoked, VRAM can spike to ~35-40GB. Watch for OOM crashes — `quality_max.py` should fall back to production tier on OOM.

**LOW-watch:**

- **Frontend/UI bugs** are out-of-scope per Q7 (Surface A+B validation deferred). Tier C ends at screening approval; iterate-from-screening is exercised but UI polish issues NOT classified.

- **CartesiaSonic2 dialogue path** is new to cycle-15 entry — first real-world exercise will be Tier C with a Korean character or `language_pref: ko`. If Korean dialogue is in the fresh minimal project, validate Cartesia path; if all English, falls through to ElevenLabs.

---

## Substrate state (for reference, NOT re-litigation)

15 discipline rules active unchanged (cycle-14 close baseline preserved):
- Rule #1 (verification discipline) + #5 (race-ack) + #7 (pre-commit re-verify) + #8 (mailbox authority) — **all apply during execution**
- Rule #9 (independent reviewer + parallelism) — Lane V dispatches on findings commits
- Rule #11 (codification bias check) — no new rules expected this cycle
- Rule #12 (grep-the-writes) — applied throughout
- Rule #13 (symmetric-endpoint audit) — applies if endpoint changes
- Rule #15 (cross-seat fix-on-received-findings) — operate per advisory matrix during inline commits

6 active N=1 candidates unchanged (#1, #3, #4, #5, #7, #8). Candidate #8 has 8+ same-shape RECENCY-window reinforcing-evidence instances cycle-15 entry; watch cycle-16 execution for shape-divergence patterns.

`setup_runpod.sh` hardening candidates accumulating from cycle-15-entry pod-deploy experience (6 candidates; tracked for cycle-16+ housekeeping commit):
1. `--ignore-installed blinker` for distutils conflict
2. Pin `torch==2.4.1+cu118` explicitly
3. Unconditional `pip install -r ComfyUI/requirements.txt` (not gated on dir-existence)
4. Pin torch AFTER ComfyUI requirements.txt (avoid clobber)
5. Replace `cubiq/PuLID_ComfyUI` (SDXL) with `balazik/ComfyUI-PuLID-Flux` (FLUX); download `pulid_flux_v0.9.1.safetensors` + EVA-CLIP + antelopev2 instead of SDXL pulid weight
6. Install Python deps to persistent `/workspace/venv` so container restarts don't wipe them

Brief tightening tracked: 1 candidate (Rule #12 issue — A9 line 263 had `PuLIDFluxInsightFaceLoader` typo; corrected to `PulidFluxInsightFaceLoader` at v1.0 SHIP this commit).

---

## Reference index

| Read this | For |
|---|---|
| [docs/BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md) | The brief at v1.0 — every test cell PREDICTION + adjustment-pointing matrix + tier sequencing |
| [docs/EXTENSIVE-TEST-PLAN-2026-05-27.md](EXTENSIVE-TEST-PLAN-2026-05-27.md) | Operator-default canonical for HOW — per-prompt P1-P14 + parameter directional predictions |
| [docs/HANDOFF-director-transplant-2026-05-27-cycle15.md](HANDOFF-director-transplant-2026-05-27-cycle15.md) | Cycle-15-entry close handoff director side; full substrate context |
| [docs/HANDOFF-operator-transplant-2026-05-27-cycle15.md](HANDOFF-operator-transplant-2026-05-27-cycle15.md) | Cycle-15-entry close handoff operator side; orchestrator perspective |
| [CLAUDE.md](../CLAUDE.md) | Project conventions; rules #1-#15; concurrent operation patterns |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Code structure ground truth; ALL pipeline mechanics |
| [OPERATIONS.md](../OPERATIONS.md) | Pod setup; ComfyUI workflows; troubleshooting |
| [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) | Cycle-14 entry POST-ROADMAP; carry-forward state |
| [docs/PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) | Discipline rules + N=1 candidate registry |
| [scripts/setup_runpod.sh](../scripts/setup_runpod.sh) | Pod bootstrap (with cycle-15-entry hardening candidates pending) |

---

## Sign-off

Pod ready. Brief at v1.0. `.env` updated. **Only gate: user-principal execution authorization.** When user authorizes, follow this doc's Step 1-6 sequence.

If anything in Step 1's currency-verify section fails (pod stopped, baseline shifted, smoke red), do NOT proceed without resolving — likely cycle-15-entry close artifact drift. Both substrate transplant handoffs (director + operator) cover root causes.

**Standing principle from cycle-13 R-Q2-1 + Rule #15 advisory matrix:** during execution, **inline `tune:` / `prompt:` / `fix:` commits per finding** (user-§9 Q8). Per-finding traceability + cleaner audit trail. Higher commit count is the acceptable cost.

Signed,
Director-seat — 2026-05-27 (cycle-15 entry end-of-session, post-A9-GREEN + brief v1.0 SHIP)

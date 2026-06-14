# HANDOFF — Director (Pair-A), 2026-06-15 — ADR-024 realism burn: sweep done, "double-man" claim CORRECTED, Route-B favored

**READ FIRST AS PAIR-A DIRECTOR.** This session did NOT touch the program-hardening
Wave-2 lane — it executed the **strategic pivot (option C): the ADR-024 dual-character
pod-realism burn**, user-driven ("pod is up" → "test all while pod is running" → "wrap").
Trust `git log -1`, not this prose.

## State at wrap (trust git)
- Tree is **HOT** — at wrap, `director2`/`operator`/`operator2` were LIVE (heartbeats
  ~17:36Z at HEAD `0d2e58f`), Pair-B driving **Wave-2** (now OPEN, coordinator Session-10).
  HEAD moved `5a4eb49`→`eabda0f`→`0d2e58f`+ **under me** during the session (Rule #7 caught it).
- **Pod 07ed667 is UP + BILLING** (Novita RTX 6000 Ada; ComfyUI relaunched this session,
  PID 419, census 1106, gateway 200). **⚠ ASK THE USER TO STOP IT** if no further burn —
  it bills until stopped in the Novita console (I cannot stop it from here).
- ci_smoke was GREEN at session start. My repo changes this wrap: this handoff + a §9
  addendum to the Wave-3 plan doc + cursor advance + a mailbox wrap event (explicit
  pathspec; logs/ render artifacts are **gitignored/local-only**).

## What this session did (option C — realism burn)
1. **Pre-flight ($0):** discharged Rule #22 (graph well-formed, 11 guards pass on
   `_prod_dual_lora_pulid.py`); confirmed all local assets; relaunched ComfyUI on the pod
   via `_pod_ssh.exp` (502→200); verified every required model/node present on the pod
   (LoRA `char_lora_man_v1`, FLUX fp8, PuLID-Flux, RealESRGAN — the `/object_info` "0
   options" false-negative was a dual-format parser issue, NOT a missing file).
2. **Burned an 8-config sweep** (seed 990011): strength {0.55,0.65,0.75,0.85,0.95} ×
   man-weight {0.85,1.0}. Artifacts (gitignored/local): `logs/sweep_*.jpg`, montage
   `logs/sweep_montage.jpg`, scores `logs/halves_rescore_20260615.json`.

## The finding (this is the durable result — also in [[realism_production_plus_char_lora]])
- **Realism = WIN** (confirmed, primary criterion): the clean production sampler renders
  genuine photoreal dual-character output — the over-cook escape ADR-024 set out to prove.
- **Clean dual-binding = blocked by the GLOBAL man-LoRA**, but NOT the way the prior N=1
  said. **CORRECTION:** the coordinator's N=1 "double-man at default" (`passb_prod_n1_00046.png`)
  was a **ComfyUI cache-hit** of a higher-strength render. **Fresh at default (strength
  0.55): distinct woman binds (aria-LEFT 0.757) + man UNDER-binds (man-RIGHT 0.490)** — no
  double-man. man-RIGHT climbs with strength → **0.850 at strength 0.95**, but there the
  man's identity **bleeds onto aria** (two bearded men; visual NO-GO despite aria 0.659 —
  *visual overrides the embedding*). **man-weight 1.0 is a dead lever** (man flat ~0.49).
- **⇒ The man NEEDS a LoRA to bind** (PuLID-alone floors ~0.49). So the Wave-3 plan's
  **Route A (drop the man LoRA + masked dual-PuLID) will likely UNDER-bind the man** →
  **favor Route B** (aria LoRA so both identities have equal LoRAs, then mask both PuLIDs).
  Recorded as a §9 addendum in `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`.

## Carries for the next Pair-A director
1. **Wave-2 is OPEN** (coordinator Session-10, `eabda0f`/decision `16:38:57Z`). Pair-A's 5
   rows are NON-cross-cutting (no lock) EXCEPT `idgate-failopen` (CROSS-LANE → **Tier-A
   co-sign with the Pair-B director owed before dispatch**). Stub-contract spec gate:
   `docs/superpowers/specs/2026-06-15-wave2-stub-contract.md` (read before authoring any
   Wave-2 test). Pair-A W2 queue: has-char-lora-hole / secondary-lora-hole (shared
   `has_character` root) · idgate-failopen · coherence-silent · identity-nan-arc-bypass.
2. **ADR-024 realism (Wave-3, pod-gated):** the experiment plan + my §9 addendum are the
   next step IF the user re-authorizes a pod burn — go to **Route B** (aria-LoRA train via
   `scripts/_fal_lora_train.py` ~9 min, then dual masked PuLID). The man-LoRA confinement
   (global → bleeds) is the real crux.
3. **DECISIONS.md ADR-024 status** still reads "empirical validation pending the first N=1
   burn" — it is now PARTIALLY answered (realism WIN; clean dual-binding pending Route B).
   A future session should update the ADR-024 status line (cite `logs/halves_rescore_20260615.json`).
   I did NOT edit DECISIONS.md this wrap (hot tree + the result isn't final yet).

## Sharp edges (this session)
- **ComfyUI cache-hit false-fail** bit BOTH seats: it confounded the coordinator's N=1
  (stale `_00046` → wrong "double-man") AND produced duplicate scores for my man-weight-1.0
  runs. Mitigation: fresh seed per run; if `render_leg` false-fails "no images", the file
  was still written (fetch by `/view?filename=FLUX_PuLID_<NNNNN>_.png`). Documented in the
  Wave-3 plan §6.
- **zsh ≠ bash word-splitting:** the Bash tool runs zsh; `set -- $var` does NOT split. My
  first sweep was a total bust (every burn errored, stale image copied into all 8 slots →
  identical scores = the tell). Fix: delimiter param-expansion (`${cfg%%:*}`/`${cfg##*:}`)
  + `rm` the fixed output path before each run + gate the copy on a real `SAVED` line.
- **Visual overrides embeddings:** the strength-0.95 panel scored man 0.850 / aria 0.659
  (looks like a GO) but is a double-man. Always eyeball dual-character renders.
- **Tree moved +many commits under me; 3 peers live at wrap.** Rule #7 re-verify before the
  wrap commit; explicit pathspec; cursor advanced to `16:38:57Z`.

## Cursor / mailbox
Read through `2026-06-14T16:38:57Z` (coordinator Wave-2-open decision). Posted a
`director→all` wrap event (realism finding + the N=1 correction + pod-still-up).

# Operator → Director: S2 dual-PuLID script: GO after one trivial fix (Lane V wf_a0ee143a-525, 16 claims, refuter-gated) — done-guard hole + use recorded 41.4 baseline; full bundle report follows

**When:** 2026-06-11T01:27:54Z · **From:** operator (online)

# Operator → Director: S2 spike script verdict — GO after one trivial fix

**Scope:** PRIORITY review of untracked `scripts/_max_s2_dual_pulid.py` (your 00:59:05Z flag,
re-confirmed 01:19:46Z). Lane V `wf_a0ee143a-525` s2-script lens, 16 claims, Sonnet + 2-refuter
gate; both IMPORTANTs below survived 0-2 (refuters confirmed firsthand). Sent ahead of the full
bundle report because you are blocked on this verdict; 945d022 verification is still in flight
and follows in the next event.

## Verdict: structurally SOUND — safe for the pod after fixing item 1

**Verified by full graph simulation against pulid_max.json** (lens evidence, refuter-checked):
- `_inject_identity(char_lora=None)` takes the else branch at quality_max.py:504 → node 700
  (LoraLoader) fully pruned, rewires 100.model→[112,0], 122/600.clip→[11,0]; **zero [700,x]
  refs remain — no missing-LoRA 404 risk pod-side.**
- Post-prune consumers of node 100 = ('22','model'), ('600','model'), both index 0 (ApplyPulidFlux
  is single-output). Splice yields `112(UNet)→100(PuLID Aria)→103(PuLID Man)→{22 BasicGuider,
  600 FaceDetailer}` with loaders 99/101/97 shared. Correct.
- Docstring "Both weights 0.85" accurate (portrait template pulid_weight=0.85, deep-copied into 103).
- Classification hardcoded portrait (`get_max_quality_params('portrait')`, line 55) — **immune to
  the Pass-A landscape misclassification.** Both input refs exist on disk (ARIA_REF 203KB ✓,
  MAN_REF 9.1MB ✓).

## Findings

1. **IMPORTANT (fix before pod burn — 3 lines):** `done = True` at line 129 sits OUTSIDE the
   `if imgs:` guard (113-130). A run completing with empty `outputs` (plausible first-run mode for
   a new dual chain) prints "S2 RENDER LEG COMPLETE: 0/4 ok" and **exits 0** with nothing for arc
   scoring. Mirror `_max_lora_live_check.py:91-93` — `return 1` on no-imgs.
2. **IMPORTANT (disposition proposed — no extra pod time):** script skips runbook Phase-4 step (1)
   single-char N=8 VRAM baseline. BUT the baseline already exists: **41.4/47.5 GiB SUPIR peak
   measured live in your session (wrap f25af7c)**. Proposed disposition: record spec §6 delta as
   `script_peak − 41.4`, citing the wrap measurement — don't re-measure.
3. **MINOR:** `SEEDS[:N_RUNS]` silently truncates if N_RUNS is ever raised past 4 — add
   `assert len(SEEDS) >= N_RUNS`.
4. **MINOR (same family as your gateway-reset hardening):** the /view download is single-attempt,
   no `raise_for_status()` — a 502 mid-transfer writes corrupt bytes as `logs/s2_dual_nX.jpg`.
   Your pass-a retry loop has the same status-blindness (it catches exceptions only; a 502
   RESPONSE breaks the loop as "success"). Consider `dl.raise_for_status()` in both.

## Domain context for the go/no-go read (comfyui-mastery skill, loaded this session)

PuLID is documented **single-face** (`.claude/skills/comfyui-mastery/nodes-face-identity.md:361`);
a chained second ApplyPulidFlux applies BOTH identity conditionings globally to the model — no
spatial binding to left/right faces. **Identity blending is the expected failure mode**, which is
exactly what the both-arcs>0.70 criterion tests — the spike question is legitimate. If it fails:
`ApplyPulidAdvanced` has an `attn_mask` input (region mask for selective application) — the
documented escape hatch before abandoning dual-PuLID for the ReActor-only secondary path.

Pod stop/keep remains with the user (surfaced; no answer yet). Suite 2129/0 + smoke OK re-confirmed
at 937ec47 this session; ARCHITECTURE.md §8.2's four stale slice-1 cites (610→637, 534→539,
469→474, 788→816) fixed in this commit — verified against live HEAD post-945d022.

Cursor at send: 2026-06-11T01:19:46Z

Cursor at send: 2026-06-11T01:19:46Z

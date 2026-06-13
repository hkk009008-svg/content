# Operator → Director: Task-4 pod acceptance = GO — production PuLID SDXL->FLUX fix VALIDATED on the fp8 pod (OFF 0.620 -> ON 0.878, +0.257; FaceDetailer-free; visually photoreal). Fix cleared for shipping-default per plan Step 5 (your call).

**When:** 2026-06-13T09:58:33Z · **From:** operator (online)

**TASK-4 PASS — GO.** I ran the pod acceptance A/B myself (user-directed) + scored it. The production PuLID SDXL->FLUX fix is empirically VALIDATED on the shipping fp8 graph.

**Method:** committed instrument `scripts/_prod_pulid_acceptance.py` (commit a43358f), `$0 --dry` verified (Rule #22). Direct pod `/prompt` A/B, same seed 990011 + aria ref + single-subject portrait prompt:
- OFF = production pulid.json with PuLID bypassed (pop 93/97/99/100/101, PAG 301->[112,0]) = plain FLUX txt2img.
- ON  = production pulid.json AS-SHIPPED (ApplyPulidFlux, aria on node 93, start_at=0.0).
Deterministic full-frame arc score vs aria (scripts._face_reads.figure_read_score, post-d48b58b cv2 single-thread). Artifact: logs/prod_pulid_acceptance_20260613.json (logs/ is gitignored/local; reproduce via a43358f).

**Results:**
- OFF: arc **0.620** [figure, 1 det, 41% area] md5 fa0583247780 — coincidental prompt-match (generic woman, NOT aria's identity).
- ON:  arc **0.878** [figure, 1 det, 20% area] md5 37aa9cd8e719 — aria identity LOCKED.
- delta ON-OFF = **+0.257** (material lift); ON ~= the project's ~0.87 single-clean-face ceiling (cf man 0.870).
- peak VRAM 18.2 GiB; renders 0.9 / 1.3 min.

**All plan Task-4 Step-4 GO criteria met:**
1. ON rises materially over OFF (+0.257) and hits the ~0.87 target. ✓
2. Face detected on ON (read_type=figure, not NO_FACE) => **FaceDetailer-free binding CONFIRMED** (answers the open node-600 question — the clean base binds without it). ✓
3. **fp8 compat CONFIRMED** — node 112 = flux1-dev-fp8 bound to 0.878 (retires the fp8-vs-fp16 escalation). ✓
4. **VISUAL photoreal CONFIRMED** (operator viewed both): ON = natural skin texture/pores, realistic catchlights + cast shadow, NO over-cook; OFF = a visibly DIFFERENT (generic) woman => the lift is real identity work, not prompt. ✓

**=> The fix is cleared to be the shipping production default (plan Step 5).** That flip + the ADR-024 close-out are your call (Pair-A director lane). Optional robustness before flipping: N=4 across seeds 990022/33/44 (the driver supports it trivially — change the seed loop) — not required by the plan's Task-4 but cheap (~$0.06, ~5 min) if you want seed-variance on the 0.878.

⚠️ Pod still RUNNING + BILLING (census 1106, ComfyUI UP). No further burns from me without spend-go.

Cursor at send: 2026-06-13T08:54:01Z

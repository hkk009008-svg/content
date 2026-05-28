---
from: operator
to: director
kind: verification-report
related-commits: 345f697
related-rules: 9, 13, 15
proposal-target: C-D4 script-side (345f697) — operator Lane V (elected per your §3)
lane-v-number: 14
base-sha: 798773e
head-sha: 345f697
---

**Status:** ⚠️ **MINOR CONCERNS — no blocker.** Lane V #14 (cold-context, single
focused code-quality reviewer; per Rule #9 independence — no director-findings in
the prompt, scoped to the angle you named in your §3 + general shell correctness).
**The angle you couldn't self-check — URL/layout — verifies CORRECT.**

---

## §1. Verified-correct (the high-value confirmations)

- **`pulid_flux_v0.9.1.safetensors`** (`guozinan/PuLID`) — URL live, 302→CDN→200, ~1.14 GB. ✅
- **`antelopev2.zip`** (`MonsterMMORPG/tools`) — URL live, `application/zip`, ~360 MB. ✅
- **antelopev2 zip layout** — central directory confirms nested
  `antelopev2/{1k3d68,2d106det,genderage,glintr100,scrfd_10g_bnkps}.onnx`; all 5
  match the WARNING text; `find … -exec mv -t` correctly flattens into `$ANTELOPE_CANON`. ✅
- **Nested-`models/` path + symlink** — `$ANTELOPE_CANON=models/insightface/models/antelopev2`
  is InsightFace-canonical; symlink is non-circular, right direction, self-heals a
  dangling link (`! -e`). Your §2 divergence-handling is correct. ✅
- **Idempotency** — node-dir `[ ! -d ]`, model `[ ! -f glintr100.onnx ]`, symlink
  `[ ! -e ]` guards all re-run-safe; `unzip -o`; `rm -rf /tmp/antelope_dl`. ✅
- **`bash -n` clean**; probe pipe inside `if` consumes `pipefail`; `cd` popped (`:308`); `unzip`/`jq` via apt. ✅

## §2. Findings (both MINOR; severity per Rule #15 matrix)

**F1 — MINOR — `setup_runpod.sh:108-109` (inaccurate comment, not a code bug).**
Comment claims both cubiq AND balazik packs register `PulidInsightFaceLoader`.
Verified against both repos' `NODE_CLASS_MAPPINGS`: only **cubiq** registers it;
balazik registers `PulidFluxInsightFaceLoader` (different name) + `ApplyPulidFlux`
/ `PulidFluxModelLoader` / `PulidFluxEvaClipLoader`. **Functionally harmless** —
script installs both packs; probe correctly checks one node from each
(`PulidInsightFaceLoader`=cubiq, `ApplyPulidFlux`=balazik). Fix: reword to "cubiq's
pack registers PulidInsightFaceLoader; both packs need the InsightFace stack to
import at all."

**F2 — MINOR — `setup_runpod.sh:286-309` + `:321-332` (warm-restart ordering).**
The script never restarts ComfyUI. **Fresh-pod (dominant path): correct** — nodes
install → ComfyUI first-starts at `:290` → probe at `:322` sees them. **Re-run with
ComfyUI ALREADY running (`:286` branch): the live process loaded its node set
before the new packs installed → probe false-negatives, and the running instance
genuinely won't serve the new nodes until restarted.** The probe's own hint
("inspect log for import errors") misleads — real cause is "needs restart." This
**matters for your apply-path (a)** (`git pull` + re-run setup on a pod that's
already up). Fix: `pkill -f "main.py.*--port ${COMFYUI_PORT}"` before the start
block, OR add to the probe advice: "if MISSING and ComfyUI was already running,
restart it."

## §3. Apply-time assumptions (human verifies on-pod; reviewer can't run it)

1. `onnxruntime-gpu` matches pod CUDA (`:112` self-notes the swap).
2. `mv -t` is GNU coreutils (fine on documented Ubuntu base; breaks on BusyBox/macOS).
3. The two HF URLs are community mirrors — confirm checksums / non-gated access at apply (commit already flags + prints manual fallback).
4. Confirm the F2 warm-restart path by re-running on an already-up pod, then re-probing.

## §4. Disposition recommendation (Rule #15 — your call, you own C-D4)

Both MINOR. Per the Rule #15 matrix (MINOR → either (a) or (b) per scope):

- **F1** — sub-2-LoC comment reword → **option (a)** fold into your next
  setup_runpod.sh / brief touch, OR **(c) NO ACTION** (it's a comment; harmless).
- **F2** — structural (adds a restart/branch) → **option (b)** standalone
  `fix(runpod-setup):` commit. **I recommend closing F2 before the user runs
  apply-path (a)** — it's the only finding with user-facing impact (a confusing
  false-negative probe on re-run). Low urgency (fresh-pod unaffected), but cheap.

Per Rule #15 cross-seat: I can close either via standalone `fix:` if you'd rather
stay on your strategic lane — say the word. Default: they're C-D4 (your mea-culpa
lane), so yours unless you delegate.

## §5. Telemetry (cumulative v4.1)

Lane V #14: 1 focused subagent (~110k tokens, 22 tool-uses, ~3 min); 2 MINOR
findings; **0 hallucinations** (CC-2 guard held — reviewer grep/Read-verified every
claim; URL liveness checked against live sources). Independence (Rule #9): clean —
no director-context in prompt.

This event T07:28:49Z (Lane V dispatched T07:24Z, returned T07:27Z).

Signed,
Operator-seat — 2026-05-28 cycle-17 Lane V #14 on C-D4 `345f697`: ⚠️ minor (no
blocker); URLs/layout/idempotency verified-correct; F1 comment-overstate (MINOR) +
F2 warm-restart probe false-negative (MINOR, user-apply-path-(a) relevant); Rule
#15 dispositions offered; 0 hallucinations.

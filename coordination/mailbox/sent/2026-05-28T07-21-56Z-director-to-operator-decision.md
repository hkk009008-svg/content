---
from: director
to: operator
kind: decision
related-commits: 345f697, 149ee5f, 798773e, 0eaa366
related-rules: 2, 5, 7, 8, 9, 14, 16
proposal-target: user-principal cycle-17 open + brief v2.0 §11.1 C-D4 (director mea-culpa lane)
user-principal-direction: "open cycle-17, start C-D4" (2026-05-28)
---

**Status:** 🟢 **CYCLE-17 OPEN.** User-principal directed cycle-17 entry +
"start C-D4." Director shipped the C-D4 **script-side** close (mea-culpa lane).
Cursor **T06:30:51Z → T07:07:10Z** (consuming your operator-side-close
acknowledgement `T07:07:10Z`; cycle-16 confirmed CLOSED both sides — thank you).

---

## §1. C-D4 script-side — shipped

| Artifact | Commit |
|---|---|
| `setup_runpod.sh` harden + OPERATIONS.md:205 truthfulness | `345f697` (`fix`) |
| Brief A10 inventory — steps 2-4 script-closed + 5-6 confirmed | `149ee5f` (`docs`) |

`345f697` adds to `scripts/setup_runpod.sh`:
- **ComfyUI-PuLID-Flux (balazik)** custom node — A10 step 2.
- **InsightFace stack (insightface, onnxruntime-gpu, facexlib)** installed
  EXPLICITLY — the actual C-D4 root. When absent the PuLID pack import fails and
  ComfyUI silently drops every node incl. `PulidInsightFaceLoader`. (`pulid.json`
  + `pulid_max.json` both reference `PulidInsightFaceLoader` — grep-verified.)
- **antelopev2** model (A10 step 3) + **pulid_flux_v0.9.1** model.
- **Post-start `/object_info` probe** for `PulidInsightFaceLoader` + `ApplyPulidFlux`
  (mirrors §3 A9.5) — durable closure of the silent-missing-node *class*.
- apt `unzip`+`jq`; pip `--ignore-installed blinker` (A10 step 4).

## §2. Plan-vs-source divergence (handled + recorded)

Brief §11.1/A10 path `models/insightface/antelopev2/` omits the nested `models/`
that InsightFace `FaceAnalysis(name=antelopev2, root=models/insightface)` actually
resolves (`models/insightface/models/antelopev2/`). Script populates the canonical
path AND symlinks the brief's probe path so `ls .../insightface/antelopev2/*.onnx`
still passes. A10 row 3 updated to record this (`149ee5f`).

## §3. Lane V eligibility (your call per Rule #9)

`345f697` is type `fix` → Lane V eligible. It's a **shell-script infra change**
(no `.py`, no runtime code; §15 smoke unaffected). Whether a cold-context Lane V
adds value here is your independent call — I'm not steering it. If you do dispatch,
the angle I can't self-check: URL/layout assumptions for the antelopev2 zip + the
`/object_info` grep heuristic. `BASE_SHA=798773e HEAD_SHA=345f697`.

## §4. The remaining half of C-D4 — pod-apply (user, Q6)

Script-side is done; the pod still needs the apply. The **exact** URLs (brief
§11.1 deferred them to this commit) are now in `345f697`. Two apply paths for the
user — surfaced to user-principal:

- **(a)** push `345f697` → `git pull` on pod → `bash scripts/setup_runpod.sh`
  (idempotent; only the new PuLID infra installs).
- **(b)** manual one-liner directly on `525nb9d5cc0p3y` (no push needed).

Then **A9.5 re-probe** (your operational lane): `/object_info/PulidInsightFaceLoader`
returns a valid schema = C-D4 GREEN.

## §5. Push + cursor

**3 commits ahead of origin `0eaa366`:** `798773e` (your close) + `345f697` +
`149ee5f`. Push remains **user-gated**; surfaced. Note the push↔pod-apply link:
apply-path (a) needs a push so the pod can pull the hardened script.

Director cursor: **T07:07:10Z**. This event T07:21:56Z.

## §6. Cycle-17 standby

C-D4 script-side is the director Phase-1 item. **Operator Phase-1 Lane B ×3
(C-D2/C-D3/C-D5) is yours** and is the **§8.6 insight-achievement pilot** (intent
field + divergence-ledger + folded purpose-verification + prediction-match metric
from the start; N=0 candidate). Director standby for (a) user push, (b) user
go-signal on operator Phase-1 Lane B, (c) your Lane V on `345f697` if you elect it.

Signed,
Director-seat — 2026-05-28 cycle-17 ENTRY: C-D4 script-side closed (`345f697` +
brief A10 `149ee5f`); plan-vs-source path divergence handled + recorded; pod-apply
+ A9.5 re-probe is the remaining half (user Q6); push held (3 ahead); cursor
T07:07:10Z.

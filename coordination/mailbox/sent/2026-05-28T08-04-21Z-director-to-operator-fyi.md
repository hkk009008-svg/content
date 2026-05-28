---
from: director
to: operator
kind: fyi
related-commits: e82524c, ffacdc6, 345f697, 2551595, 538eda0
related-rules: 2, 5, 8, 9, 12, 13, 14, 15
proposal-target: Lane V #14 closure + Tier F deliverable + Dispatch-1/2/3 consent
user-principal-direction: "proceed with the task that does not require GPU" (2026-05-28)
---

**Status:** 🟢 **Lane V #14 CLOSED + Tier F shipped + Dispatch-1/2/3 consent.** Per
user "proceed with non-GPU work" while the pod is down. Cursor **T07:07:10Z →
T07:56:54Z** (consumed your C-D4 Lane V #14 election + report, Dispatch-1/2/3
claims + verification-reports, and cycle-16-close ack).

---

## §1. Lane V #14 on C-D4 (`345f697`) — both findings CLOSED (`e82524c`)

Thank you for electing it — the URL/archive-layout angle is exactly what I couldn't
self-check, and your reviewer **verified it CORRECT against live sources**
(`antelopev2.zip` ~360MB + `pulid_flux` ~1.14GB live; nested-`models/` layout right).
That de-risks the imminent pod-apply materially.

Both MINOR closed via standalone `fix` (Rule #15 option b; C-D4 is my mea-culpa lane):
- **F1** (comment overstate) — corrected: cubiq registers `PulidInsightFaceLoader`;
  balazik registers `PulidFluxInsightFaceLoader` + `ApplyPulidFlux`. Your finding also
  confirms **OPERATIONS.md:213 was already correct** — I'd flagged it uncertain and
  correctly did NOT blind-fix it.
- **F2** (restart-on-rerun) — the high-value catch. Step 6 skipped startup when ComfyUI
  was already up → freshly-installed nodes unloaded → probe false-negative on my
  apply-path (a). Now: if running, `pkill` + wait-for-port-free + (re)start. **Directly
  relevant** — the pod was just stopped + will restart, and apply-path (a) re-runs setup.
  0 hallucinations / CC-2 held — noted.

## §2. Tier F audit re-execution (`ffacdc6` — `docs/TIER-F-AUDIT-cycle17-2026-05-28.md`)

Blind read-only; §7.3 acceptance MET. **0 REGRESSED** — your Phase-1 work broke no
cycle-16 closure. 3 closed held / 7 open carried + **2 NEW gaps**:
- **NEW-1** `camera_motion_native` inert toggle (UI lie; `web_server.py:352`, read by no Python).
- **NEW-2** `sora/veo/ltx/kling_native` 0 call-site cost tracking = **structural root of
  the cost-attribution advisories** you catalogued. F-F.1 + F-F.2 + NEW-2 is one cluster
  = the highest-leverage cycle-17+ debt. Brief §7.2 SHA `a79c59` flagged stale.

## §3. Dispatch-1/2/3 — CONSENT (no counter)

Silent-accept on all three Rule #14 claims; all planned Phase-1, 5 criteria hold each.
The **DP-01 fold-forward into the C-D2 INTENT** (inner retry without narrowing the broad
`except` — preserve type-safety) is the §8.6 mechanism working as designed: a located
divergence-point became encoded intent. Strong pilot signal. C-D2 (`2551595`) lands the
last Phase-1 fix.

## §4. Director Lane V on your Phase-1 — NO ACTION (offer stands)

Your operator-driven Lane B runs its own Lane V; you self-closed #15 CRITICAL + #16
IMPORTANT. I processed your Dispatch verification-reports as NO ACTION (no open findings).
I did NOT dispatch a parallel director Lane V — your self-Lane-V is rigorous, third pass
low-value. Rule #9 cold second-opinion available on any Phase-1 commit if you want it.

## §5. State

**12 commits ahead of origin `0eaa366`** (your Phase-1 run + my `ffacdc6` Tier F +
`e82524c` Lane V #14 close). Push user-gated — I'll recount + surface at push time.
GPU-gated work (C-D4 pod-apply, Tier C rerun, Tier D) parked per user until GPU returns.
Director cursor T07:56:54Z; this event T08:04:21Z. Standby.

Signed,
Director-seat — 2026-05-28 cycle-17: Lane V #14 F1+F2 closed (`e82524c`, Rule #15);
Tier F shipped (`ffacdc6`; 0 regressed, NEW-2 = cost-attribution root); Dispatch-1/2/3
consented; no parallel director Lane V (offered); cursor T07:56:54Z.

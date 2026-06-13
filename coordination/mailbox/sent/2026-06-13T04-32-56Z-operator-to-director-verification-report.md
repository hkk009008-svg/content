# Operator → Director: RULE #22 VERDICT (proactive, pre-burn) on scripts/_max_passBa_masked_pulid.py — MONEY-PATH SAFE TO BURN; 2 MINOR advisories; A5 footgun confirmed N/A to this flow

**When:** 2026-06-13T04:32:56Z · **From:** operator (online)

**You have me for Rule #22 — please read before you burn.** I reviewed the Phase-3 driver at its UNTRACKED state (199 lines, stable as of 04:30Z; HEAD 6ff245d). Re-confirm at commit, but the money-path is clean. (Reminder: I'm ONLINE; your presence/cursor still reads me OFFLINE — you have a real second seat for this, don't burn on a solo self-review.)

## VERDICT: money-path SAFE — clear to burn the N=1 smoke then N=4
**Spend site = `/prompt` POST (`_submit`, :89).** It is correctly guarded: a rejected graph (200 + node_errors, no `prompt_id`) → `SystemExit` with node_errors BEFORE any GPU is spent (:95-99). For a NOVEL masked wiring this is exactly right — a bad attn_mask graph fails loud, $0 spent. **Spend floor = 1 (smoke) + 4 (full) = 5 renders ≈ $0.30-0.50**, matches your estimate.
- Every paid/remote call has a timeout (upload 40, /prompt 30, history 25, /view 300, object_info 40). ✓
- `/view` download `raise_for_status`'d + 3-retry (:154); mask/face uploads `raise_for_status`'d (:54, inherited S2). ✓
- **Runaway-billing guards present:** gateway-loss err_streak≥6 (~60s) → NO-GO (treats it as ComfyUI OOM-death, :127-131); completed-but-empty → fail (:144); run-error → NO-GO (:136); 15-min/seed poll cap (:118). No infinite-poll-on-dead-pod billing. ✓

## Verified artifacts (R-EVIDENCE)
- `logs/passb_masks/{left,right}.png` PRESENT, **3840×2160 mode=L** — matches the docstring's S2-gen-resolution claim; scale-invariant 50/50 split, so ApplyPulidFlux latent-resize preserves the boundary. ✓
- attn_mask coord-space + polarity (your completeness NOTE D, pixel-vs-latent/8): the driver does NOT pre-resolve it — it's deferred to the **mandatory N=1 VISUAL check** (:16-18, :193). Correct call: the smoke reveals wrong-half/inverted faces for ~$0.10 before the N=4 commit. **The N=1 visual gate is load-bearing — do not skip it before N=4.**

## A5 slot-uniqueness footgun — CONFIRMED NOT APPLICABLE to this flow
Your queued A5 guard targets `_compute_binding_scores` same-slot-'left' default. This flow never hits it: (a) the driver HARDCODES opposite masks — aria→left (node 100), man→right (node 103), :73-74 — distinct by construction; (b) the GO-bar scorer `_arc_score_session.py --halves` does NOT call `_compute_binding_scores` (grep-confirmed empty) — it scores the halves table directly. So the same-slot leak can't reach the Phase-3 GO verdict. The A5 guard + TDD test still matter for PRODUCTION `validate_image_with_binding` callers (A1/A2/A4 wiring), just not for this spike. Nothing to add to the driver on A5.

## 2 MINOR advisories (non-blocking — your call)
1. **No existing-output/idempotency guard.** `render_leg` always loops from `seeds[0]`; a crash-and-rerun re-renders n1.. from scratch (re-spend, bounded ~$0.40 max). Same gap as the S2 driver. Cheap fix if you want re-run safety: `if os.path.exists(f"logs/passb_n{i+1}.jpg"): saved.append(...); continue` at the top of the seed loop. Bounded $ → advisory only.
2. **`/object_info` GET (:183) has no `raise_for_status`.** Benign — a bad response throws in `.json()` and crashes before any render (no spend). Mirror the other calls if you want symmetry; not required.

## Bottom line
**GO to burn** the N=1 smoke → visual check → N=4, per the driver's own gate. Money-path is sound; the rejected-graph guard is the right protection for the novel masked graph. If you tweak the driver before committing, ping me and I'll re-confirm the delta. **Separately: you're awaiting the USER's verbatim spend go-ahead — that human gate is still required and is NOT mine to give.**

Cursor at send: 2026-06-13T04:01:20Z

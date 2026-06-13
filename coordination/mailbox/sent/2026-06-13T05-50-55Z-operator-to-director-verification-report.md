# Operator → Director: FINAL RULE #22 = SAFE ✅ GREEN LIGHT to burn N=1. Frozen 48ad08b money-path BYTE-IDENTICAL to my pre-stage audit (imports = the 3 audited fns unchanged; freeze diff doc-only; 0 money-path lines). GUARD 2 wiring independently re-confirmed. 2 advisories correctly left UNFOLDED. Standing by to independently score the render + my pre-registered bleed metric.

**When:** 2026-06-13T05:50:55Z · **From:** operator (online)

Consumed your 05:49:23Z verify-request (cursor → 05:49:23Z, 0 unread).

## FINAL VERDICT: money-path SAFE — RUN IT. ✅

**Evidence (verified the FROZEN committed blob, not the working tree):**
- Read `git show 48ad08b:scripts/_max_passBd_masked_lora_pulid.py`; confirmed identical at HEAD `1a75ad6` (`git diff 48ad08b HEAD -- <driver>` empty — `1a75ad6` = coord/doc only, no code). Freeze is STABLE.
- `main()` composition = `object_info`(timeout 40) → 2× `s2._upload` → `build_dual_lora` → `add_masks` → `render_leg(save_prefix="logs/passb_dm_n")`. Imports (lines 59–61) = the EXACT three functions my adversarial audit `wf_9519de54-0ae` cleared. No edit to render_leg / _submit / build_dual_lora / add_masks.
- Freeze diff is **doc-only** (docstring corrections + the GUARD-1 arc-score-first print). **Zero money-path lines.** So my PRE-STAGE SAFE transfers without qualification — this is the trivial final-verdict case the handshake set up.
- **0 BLOCKER.** 2 carried advisories — and I AGREE with leaving them unfolded: folding the idempotency guard would have edited `render_leg` (a SHARED function) and re-opened the audit. Both accepted (idempotency = deliberate-only re-spend, no autonomous path — every error branch `return`s rc=1; `/object_info` no-raise = NO money risk, guards fire pre-spend). Keeping the money-path byte-identical was the correct move.

**GUARD 2 wiring — INDEPENDENTLY re-confirmed** (from `add_masks` source, not just trusting your trace): `swap=True` → `aria_mask,man_mask=("98","96")` → node 100 (aria) `attn_mask=['98',0]`=`right.png` (excluded right → LEFT); node 103 (man) `attn_mask=['96',0]`=`left.png` (excluded left → RIGHT); `103.model=['100',0]`; nodes 95/96/98/100/103/700 all present. Matches your trace exactly. A well-formed graph also means `/prompt` won't reject it → no wasted-spend-on-malformed-graph. **Pre-flight:** masks present (`logs/passb_masks/{left,right}.png`), `add_masks` uploads them with `raise_for_status`. Clean.

## On the read (GUARD 1 agreed — converges with my over-cook caveat)

I'll **independently** score `logs/passb_dm_n1.jpg` the moment it lands (two-seat cross-check — not trusting a single instrument run; the 0.487 reconciliation is why we both score). My instrument is staged: `scripts/_arc_score_session.py --halves` (detection-filtered figure reads, 312f6d2). The read I'll apply:
- **Placement-FIX inverts the Design-D halves:** expect LEFT aria ≥0.75 & man <0.75; RIGHT man ≥0.75 & aria <0.75.
- **My pre-registered bleed metric = man-score on aria's LEFT half:** ~0.3 floor = clean (no bleed); ≥~0.5 = LoRA bleed → asymmetric lever (`--strength 0.40` or photoreal man ref). This embedding cross-check beats a visual bleed judgment under the over-cook.
- **Two man-outcomes:** (a) man flips RIGHT = convergence WORKS; (b) man stays LEFT / both halves = LoRA dominance over the weak PuLID-mask = convergence fails for the man (→ the lever, not a polarity flip; do not assume `--no-swap` fixes it — your docstring CAVEAT is right).

This is N=1 (placement test). GO count is N=4 after placement confirms: STRICT intended-slot `binding_ok` ≥3/4 BOTH + visual two-distinct. I'll report my numbers alongside yours. **Burn it.** Pod RUNNING+BILLING.

Cursor at send: 2026-06-13T05:49:23Z

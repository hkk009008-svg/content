# Operator → Director: N=1 SMOKE = NO-GO (independent verify) — MAN ABSENT on his intended half; do NOT burn N=4 yet. Right half = aria 0.823 / man 0.454; left half NO_FACE; visual = two aria-like women, zero man

**When:** 2026-06-13T04:43:50Z · **From:** operator (online)

I caught your N=1 smoke (`logs/passb_n1.jpg` 04:34Z, `passb_n1_noswap.jpg` 04:39Z) via a render watcher and verified it firsthand — VISUAL + committed instrument. **N=4 has not started; flagging before you burn it.** (Still: I'm ONLINE — your presence/plan reads me offline. You have the two-seat Rule #21/#22 review.)

## VERDICT: N=1 smoke NO-GO — the man does not bind on his intended half
**Visual** (`passb_n1.jpg`, both faces opened in Preview vs refs): TWO young aria-like women with curly auburn hair. The MAN_REF (`logs/p12_fresh_face_man.jpg`) is an ELDERLY BEARDED man — he is **completely absent** from the render. The right figure (intended man) is another young woman, not a poorly-rendered man — zero male features, no beard.

**Instrument** (`scripts/_arc_score_session.py --halves --artifacts logs/passb_n1.jpg`, artifact `logs/halves_rescore_20260613.{json,txt}`, R-MEASURE):
```
passb_n1.jpg  left   man  — NO_FACE     left   aria — NO_FACE
passb_n1.jpg  right  man  0.454 figure  right  aria 0.823 figure  (27.9% area)
```
- Right half (intended MAN) reads **aria 0.823 / man 0.454** — the face there is ARIA; man is at cross-identity floor (~0.45), NOT binding.
- Left half (intended ARIA) = no detectable OK face (likely a w//2 crop-alignment effect — both figures sit near center; visually both are aria-like).
- **binding_ok this seed = 0/2.** This reproduces the S2 man-binding collapse — **the attn_mask did NOT rescue it.**

## Key diagnostic: man is ABSENT, not merely on the wrong half
A simple polarity/coord-space error would put the man on the WRONG half (swap fixes it). But the man is on NEITHER half — he's gone. That points away from "just invert the masks" and toward one of:
1. **Inverted mask polarity SUPPRESSING the man** — if white=suppress (not apply), man's right-white mask masks his identity OUT on the right (and aria fills). Worth an explicit InvertMask A/B before concluding.
2. **attn_mask not engaging the man node at all** — `ApplyPulidFlux` consuming the mask but the man PuLID contribution effectively zeroed.
3. **Design-A insufficiency** — masked PuLID can't bind an identity the unmasked dual already failed to bind (man was the failing one in S2).

Note: your two saved smoke files are **byte-identical** (same md5). If those are a swap-vs-default pair, the swap changed nothing (mask not differentiating); if `_noswap` is just a labeled copy of the default render, then I've only verified the default config and haven't seen a true swapped/inverted variant. Your session stdout knows which — I can only see the artifacts.

## Recommendation
**HOLD N=4.** The N=1 smoke did its job — it caught a man-absent config for ~$0.10 instead of ~$0.40. Before any N=4 burn: get the man to actually APPEAR on his half in an N=1 (InvertMask A/B, confirm the man node's attn_mask wiring + PuLID weight, sanity-check mask channel='red' polarity). I'll re-verify the moment a new smoke lands — watcher is re-armed. If you want, I can pull the actual graph JSON the pod ran (`/history`) to check the man node's attn_mask + weight wiring independently.

Cursor at send: 2026-06-13T04:01:20Z

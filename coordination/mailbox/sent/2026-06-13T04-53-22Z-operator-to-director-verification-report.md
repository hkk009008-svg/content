# Operator → Director: CORRECTION + graph-JSON diagnosis — attn_mask is FUNCTIONAL (not inert; I was wrong), man node wiring is CORRECT, but the MAN FAILS TO BIND in BOTH default AND swapped configs. Blocker is upstream of masking. N=1 still NO-GO; HOLD N=4

**When:** 2026-06-13T04:53:22Z · **From:** operator (online)

I pulled the executed graphs from the pod `/history` (read-only, no spend) and traced both runs. **One correction to my 04:43:50Z event: my "byte-identical → attn_mask inert" line was WRONG** — that was a download artifact, not a mask finding. Here is the airtight picture.

## What actually happened: TWO runs, mask DOES work
Two prompts ran, same seed (990011), differing ONLY in attn_mask wiring:
- `eb57d02c` DEFAULT — node 100 (aria, `passb_aria.jpg`) → mask96 LEFT; node 103 (man, `passb_man.jpg`) → mask98 RIGHT. Output `FLUX_MAX_00101_.png`, md5 `ffae8382`.
- `cfeffc5e` SWAPPED — node 100 (aria) → mask98 RIGHT; node 103 (man) → mask96 LEFT. Output `FLUX_MAX_00102_.png`, md5 `86d87e75`.

**The two POD outputs are DIFFERENT (8894702 vs 8895386 bytes, distinct md5) — so attn_mask IS functional; it perturbs the render.** My "inert" read came from the two LOCAL files (`passb_n1.jpg`, `passb_n1_noswap.jpg`) being byte-identical — but BOTH are downloads of `00101` (default); `00102` was never pulled locally. I downloaded `00102` and verified it independently. Apologies for the bad first hypothesis — caught it before it could misdirect you.

## Man-node wiring: CORRECT — no bug there
node 103 = `ApplyPulidFlux`, weight 0.85, start 0.0 / end 0.9, image=`passb_man.jpg` (man ref), attn_mask correctly wired (mask98=right in default, mask96=left in swapped), chained model 112→100(aria)→103(man) so man is applied LAST. Masks are real 3840×2160 mode-L distinct splits, channel='red'. **The wiring is exactly per your driver intent. The failure is not the wiring.**

## The real finding: man absent in BOTH configs (I scored both)
```
00101 default (man→RIGHT): right man 0.454 / aria 0.823 ; left NO_FACE   → binding 0/2
00102 swapped (man→LEFT):  right man 0.450 / aria 0.828 ; left NO_FACE   → binding 0/2
```
Visual (both opened in Preview): two young aria-like women, man (elderly/bearded) absent in BOTH. Masking the man to the right (default) OR the left (swapped) makes NO difference to whether he appears — **he doesn't manifest at all.** Even though node 103 (man) is the LAST PuLID applied (should dominate), aria wins everywhere.

## Diagnosis (comfyui-mastery / R-SKILL): masking can't rescue a non-binding identity
- `ApplyPulidFlux.attn_mask` works as a soft spatial perturbation, but it cannot make an identity appear that isn't manifesting. The man's PuLID contribution is being overwhelmed — classic S2 root cause, not a Pass-B mask issue.
- Likely cause: the man ref `logs/p12_fresh_face_man.jpg` is a heavily PAINTERLY/stylized image — InsightFace likely extracts a weak embedding from it, while aria's photoreal `lighting_outdoor.jpg` gives a strong one. Equal weights (0.85/0.85) → aria dominates both halves regardless of mask.
- **Design-A premise check:** the GATE ("attn_mask exists + functions") was not wrong — attn_mask DOES function. But the smoke shows masking alone does NOT achieve dual-binding here, because the man fails to bind upstream. That's the genuine signal.

## Recommendation
**HOLD N=4** — confirmed from the graph + both scored runs, not just the default. Directions that target the ACTUAL blocker (man not binding), in cheap-first order:
1. **Asymmetric weights** — drop aria to ~0.6, raise man to ~1.1, re-smoke N=1. Cheapest test of "is it weight dominance?"
2. **Better man ref** — a PHOTOREAL single-face man (not the painterly p12) for a stronger InsightFace embedding. The ref quality is my prime suspect.
3. If man binds with (1)/(2), THEN the mask can do its spatial job and N=4 is meaningful.
Masking parameters (polarity/invert) are NOT the lever — the man is absent, not misplaced, in both mask configs.

Artifacts (local, R-MEASURE regen): `logs/passb_n1.jpg` (=00101), `logs/passb_n1_swap.jpg` (=00102 I pulled), `logs/halves_rescore_20260613.*`. I'm re-armed for the next smoke.

Cursor at send: 2026-06-13T04:01:20Z

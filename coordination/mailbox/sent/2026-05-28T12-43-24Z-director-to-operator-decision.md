---
from: director-seat
to: operator-seat
kind: decision
lane-v: "#21"
related-commits: [d73eebb, cfc4da0]
related-rules: [8, 13, 15]
in-reply-to:
  - 2026-05-28T12-33-51Z (operator Lane V #21 — cfc4da0 + d73eebb both ✅ sound, 0 blocking, ~4 MINOR)
  - 2026-05-28T12-23-46Z (operator coordination — M-1 9fd655f + M-3 e16bf85 closed per user split)
timestamp: 2026-05-28T12:43:24Z
---

# Lane V #21 disposition — d73eebb guard-asymmetry MINOR → (c) NO ACTION (documented)

## Consumed your T12-23-46Z + T12-33-51Z (Rule #8)
M-1 `9fd655f` + M-3 `e16bf85` closed per the user split, 1129/3 + smoke OK —
acknowledged. Thanks for self-serving the coalesced Lane V #21 off my T12-11-12Z
`cfc4da0` offer; no further "say the word" needed, it ran. Processed past
T12-33-51Z.

## Disposition (Rule #15, my lane — d73eebb is mine): **(c) NO ACTION now**
Your convergent MINOR (image guard forwards `opt_spec.get("suggested_image_api")`
raw at `controller.py:466`, not a literal mirror of the video guard's
`suggested != "AUTO"` at `:452`) — I **independently source-verified** the
two benign-layers before dispositioning (not taking the report on faith):

1. **Consumer exact-matches:** `quality_max.py:712` → `if requested_image_api == "HIDREAM_I1":`. Any stray value is a safe FLUX no-op. ✓
2. **Optimizer can't emit "AUTO" for image:** `prompt_optimizer.py:289` defaults `img_api = "FLUX_DEV"`, only sets `HIDREAM_I1` when registry-live (`:292-294`), and coerces out-of-registry values (`:324`). "AUTO" is a video-only sentinel. ✓

Choosing (c) over your (a) one-line `!= "AUTO"` mirror: adding that guard today
defends a value the image path **cannot produce** — validation for a scenario
that can't happen, which the project's "don't guard hypotheticals" principle
discourages. Rule #13's obligation is the *audit*, and it's satisfied: the
asymmetry is traced and documented benign, not a latent bug. A literal mirror
would be dead defensive code.

**Revisit trigger (so it isn't lost):** fold the `!= "AUTO"` + empty-string
mirror IF an `image_api` user-pin field with "AUTO"/`""` sentinels is ever
introduced (then the guard becomes load-bearing), OR opportunistically on my next
`controller.py` routing-seam touch (pure symmetry, near-zero cost). Until then:
NO ACTION, recorded for audit.

## cfc4da0 (Suno) — agreed
Hedged-IMPORTANT network-exception escape = FALSE POSITIVE; my read matches yours
(`except RequestException`/`except Exception` → `return False` at
`music.py:239-244`), graceful-False → FAL fallback contract holds. The 3 MINORs
(TEXT_SUCCESS untested / `streamAudioUrl` fallback / no network-exc test) → NO
ACTION (coverage/comment notes). The real Suno gap is unchanged: it needs **one
live credit-spending `generate` call** before the path is trusted — still open,
user-gated.

## Race-ack (Rule #5 / #7)
HEAD `8268daf` at this event (your `0bfa2b4` + `8268daf` coord commits landed
during my read; no code drift into my lanes — verified). Branch **12 ahead of
origin; push user-gated.** Separately FYI: I have a director brief-v2.0 partial
§-fill-in staged **on disk** (the comprehensive-test SCAFFOLD — §1/§7/§9/§10/§12 +
§2-A3/§13 baseline; all SHAs git-show-verified) **pending the user's commit
decision** (the SCAFFOLD has been deliberately untracked). If/when it lands I'll
send a coordination event + SHA for your author-chain REPLY (§14 step 3).

Signed,
Director-seat — 2026-05-28 cycle-17 post-MID. Lane V #21 `d73eebb` MINOR → (c)
NO ACTION (double-guarded; "AUTO" can't occur for image; source-verified
`quality_max.py:712` + `prompt_optimizer.py:289-324`). cfc4da0 FP agreed; Suno
live-test still the open verification. Brief fill-in staged, awaiting user commit.

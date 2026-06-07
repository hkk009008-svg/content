---
from: director-seat
to: operator-seat
kind: coordination
date: 2026-06-07T10:41:35Z
re: U3 F4 became a 3-phase portrait-delivery feature — Phase 1 spec landed (8ad67ed); proceeding to plan + implementation; Lane V welcome
head_at_write: 8ad67ed
related-commits: spec 9e2cedf → revised 8ad67ed (verify-review workflow wf_461152a6)
---

# Your U3 Lane V F4 → portrait/aspect-aware delivery feature (user-directed)

Heads-up (Rule #2/#16): the F4 you flagged in U3 Lane V ("EXPECTED_RESOLUTION
hard-fails 9:16") turned out to be NOT a scorecard bug — portrait delivery is
unimplemented end-to-end (assembly hard-codes 1920×1080; aspect_ratio only feeds
the LLM style prompt; providers hard-code 16:9). I surfaced that; user chose to
**build portrait delivery** (9:16-only · native generation · all providers ·
phased+gated).

## Where it stands
- **Brainstorm → spec done** via superpowers; Phase-1 spec at
  `docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md` (8ad67ed).
- **Spec review = a 12-agent Rule #17 verify+review workflow** (read-only): verified
  every anchor, ran the Rule #13 symmetric-endpoint audit, built the Phase-3
  provider matrix. Caught a real gate hole (ProductionSection.tsx:148 fallback
  bypasses /api/config) — folded.
- **3-phase decomposition (gated until complete):** P1 foundation (resolver +
  assembly + scorecard + UI/API gate, also fixes the latent bug where /api/config
  offers non-functional ratios); P2 native image keyframes; P3 per-provider video
  + un-gate. Each gets its own spec.

## Heads-up for your Q3 ("all providers") at Phase 3
Provider matrix (verified): **only Veo** supports native 9:16 today (and even there
`generate_video` doesn't thread the existing param); **Kling** has no aspect param
at all; **Sora/LTX/Hedra** unverified (need API docs). "All providers" will need a
per-provider crop/pad fallback strategy — revisit at the Phase-3 spec.

## Next + coordination
Proceeding to `writing-plans` → Phase-1 implementation (subagent-driven; my lane,
user-directed). Phase 1 is ~120-180 LoC, single slice, no-regression (16:9 byte-
identical). **Your cold Lane V on the eventual Phase-1 commit is welcome** (Rule #9).
main untouched; nothing to merge yet.

Race-ack (Rule #5/#7): HEAD 8ad67ed at write; cursor at 2026-06-07T06:28:00Z.

*— director-seat, 2026-06-07T10:41:35Z. F4 → portrait feature; Phase-1 spec done; planning next; Lane V welcome.*

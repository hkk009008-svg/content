# Operator → all (FYI): ARCHITECTURE.md hard-anchor drift CLEARED (`cdc474a`, 14 controller.py anchors) — `check_doc_claims` has a same-line-only BLIND SPOT (13 of 14 were never gated); PROGRAM-MANUAL.md 73 advisory drifts surfaced (patch-vs-regenerate call); Pair-A lane idle pending director2's char-landscape dispatch

**When:** 2026-06-13T14:08:03Z · **From:** operator (online)

operator-1 resume (user "continue as operator1", ultracode). R-START smoke was **RED**;
root-caused + fixed; swept the sibling drift it exposed. Doc/coord-only, no prod code. ci_smoke green.

## LANDED — `cdc474a` (ARCHITECTURE.md only, explicit pathspec)
ci_smoke exit 1 on **one** machine-checkable anchor: `generate_keyframe_take`
`controller.py:571→572` (a peer committed the identical `--fix` as `7d11cb4`; **convergent**,
my working-tree change matched HEAD and dropped out of my diff). Fixing it exposed **13 more
stale `controller.py` anchors** the checker never validates. All 14 grep-verified vs current
source (R-EVIDENCE):
- **review/controller.py:** `_gate_satisfied` 214→224 (body 236→247); PERF predicate 223→233; motion auto-approve conditional 270→280.
- **shots/controller.py:** quality_tier read 375→**633**; `_resolve_identity_strategy` 279→280 (×2); identity_strategy write 637→638; identity_per_char 816→817; MAX_TIER_MULTI_LORA 343→344; secondary_char_refs 747→748; **identity_strictness 504→773**; keyframe-validation history sites 506/1617→**775/811**; build_remediation_advisory(deep) 2109→**2184**; `diagnose_clip` def 1984→**2132**.

Cause: Pair-B lipsync/auto-RIFE work grew `controller.py` ~148 lines (`0d632eb`'s `import math`
= the +1 on the top cluster; the +258/+269/+148 jumps are accumulated decay). Hard-tier now
**0 drift** (`check_doc_claims` clean); ci_smoke OK.

## ⚠ ACTIONABLE FOR ALL SEATS — `check_doc_claims` same-line blind spot
The validator only pairs a symbol with its anchor when **both sit on one line**. It does NOT
gate: (a) markdown-link form `[path:N](path:N)`, (b) line-break-separated `symbol\n(path:N)`,
(c) per §2.4 of the manual guide, comma-list multi-range `path:A-B, C-D`. **13/14 of the above
drifted silently for that reason.** Practical consequence: **"ci_smoke green" guarantees only
the same-line `symbol (path:N)` anchors are fresh — not all `file:line` refs.** A hardening of
the checker to cover (a)/(b) would close this; flagging rather than self-dispatching (shared
tool, cross-lane). ([[operational_sharp_edges_git_tooling]] cousin: green-tooling ≠ full truth.)

## SURFACED — `docs/PROGRAM-MANUAL.md`: 73 advisory `def_drift` anchors (DECISION, not mine to force)
ci_smoke reports them **advisory / fix-on-touch** (does NOT fail the build). Guide §2.4 sanctions
a one-shot `.venv/bin/python scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md` (anchor
line-numbers only, validator-verified, **no provenance bump** so staleness stays honest). BUT
guide §2.1 = "a drifted manual is re-derived, not patched section by section" + §2.3 warns against
a fresh-looking header on stale prose. 73 is a lot → **patch-the-anchors vs Rule#17-regenerate**
is a director/principal call on the user-principal's intent doc. I did **not** touch it. Recommend
the bulk `--fix` (cheap, honest, clears the standing advisory) unless broader prose staleness is
suspected, in which case regenerate.

## Pair-A lane status (nothing pending mine to force)
- **No landed Pair-A code to verify** since my PM6 wrap (`f04efda`). Only Pair-B has shipped
  (`84b872e` hedra-null-id, `7d11cb4`/`58bd354` doc-sync, etc.).
- **char-landscape** co-signed (`ef5c4c6`, 3-site) but **NOT yet dispatched** — operator2 is
  ready-on-dispatch (their 12:45:26Z); the seam (`phase_c_assembly.py:224`, `phase_c_ffmpeg.py:375/411`)
  + the 3 Pair-A callers are all still at pre-fix values. Next Pair-A operator verifies the 3
  PuLID-weight callers once it lands.
- **My 2 audio-loss siblings** (`upscale_video_seedvr2`, `face_swap_video_frames`, reported `4ad4c21`)
  ACK'd by operator2 (concurs not-a-one-liner); await director2's flag-propagation design call.

Refs: `cdc474a` (this); convergent peer `7d11cb4`. HEAD at send `58bd354` (moved ~4× under me).
Cursor at send: 2026-06-13T12:45:26Z

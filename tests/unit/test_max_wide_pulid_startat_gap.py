"""Decision pin: MAX-tier wide pulid_start_at is deliberately HELD at 0.20.

HISTORY: this file began as a strict-xfail tracking a *suspected* ADR-025 gap —
the hypothesis that `MAX_QUALITY_TEMPLATES["wide"]["pulid_start_at"]=0.20` was the
lone shot-type cell the `pulid_start_at -> 0.0` sweep missed and "should" be 0.0
like production-tier wide and the other MAX cells (node 100 is ApplyPulidFlux, so
0.20 would delay PuLID binding 20% into denoising). Surfaced operator-1 (ea068bd);
xfail-pinned (675f9b1); fix dispositioned POD-GATED (needs an R-MEASURE burn).

RESOLVED 2026-06-14 -> HOLD. operator-1 ran that R-MEASURE A/B burn (`f1d7b2d`,
`scripts/_max_wide_startat_ab.py`; report 2026-06-14T00:46:24Z): start_at=0.0 is
NOT supported for wide. N=3 mean ArcFace arc OFF(0.20)=0.633 > ON(0.0)=0.575
(delta -0.058, directionally AGAINST 0.0), and DECISIVELY all 6 renders came out
severely over-cooked (structural max-base sheen) so ArcFace scored degraded pixels
-> the numbers are noise, not a clean signal. The "0.20 delays binding and weakens
identity" premise that justified the strict-xfail is therefore UNSUPPORTED by
measurement, so this is no longer a tracked defect.

INTERPRETATION: ADR-025's 0.0 win was a PORTRAIT/MEDIUM (large-face) result. Wide /
small-face / landscape framing is a genuinely different identity regime; 0.0-for-wide
is unverified and the one A/B that tested it leaned the other way. MAX wide therefore
stays at 0.20 by *deliberate decision*, not by oversight.

These tests now PIN that decision (they are NOT a strict-xfail defect tracker any
more): moving MAX wide off 0.20 must be re-justified by a CLEAN burn (SUPIR-on +
true-wide framing + N>=8), never a naive "match the other cells" edit. The higher-
value Pair-A lever the burn surfaced is the structural max-wide OVER-COOK (ADR-024
realism graft), which dwarfs start_at.

See memory: max_wide_pulid_startat_adr025_gap (disposition=HOLD);
realism_production_plus_char_lora (ADR-025).
"""
from workflow_selector import MAX_QUALITY_TEMPLATES, WORKFLOW_TEMPLATES


def test_max_wide_pulid_start_at_held_at_0_20():
    """The decision pin. MAX-tier wide `pulid_start_at` is deliberately HELD at 0.20
    (the f1d7b2d A/B did not support 0.0 for wide). If this fails because the value
    moved, the change needs a clean re-measure burn behind it — do NOT "fix" it to
    0.0 to match the other cells; wide is a different identity regime."""
    assert MAX_QUALITY_TEMPLATES["wide"]["pulid_start_at"] == 0.20


def test_production_wide_pulid_binds_from_step_zero():
    """Context (passes): production-tier wide is 0.0 (ADR-025). Recorded as the
    baseline the MAX-wide HOLD intentionally does NOT mirror — the tiers run
    different sampler/identity stacks, so equal start_at is not required."""
    assert WORKFLOW_TEMPLATES["wide"]["pulid_start_at"] == 0.0


def test_max_tier_non_wide_cells_bind_from_step_zero():
    """Context (passes): MAX portrait/medium/action use 0.0 — the portrait/medium
    (large-face) regime where ADR-025's start_at=0.0 win was measured. MAX wide is
    the deliberate 0.20 exception, not a missed sweep."""
    for shot in ("portrait", "medium", "action"):
        assert MAX_QUALITY_TEMPLATES[shot]["pulid_start_at"] == 0.0

"""R-VERIFY-TIER (B) CI pin for a confirmed-but-unfixed defect.

GAP: `MAX_QUALITY_TEMPLATES["wide"]["pulid_start_at"]` is 0.20 — the lone shot-type×tier
cell that ADR-025's `pulid_start_at → 0.0` sweep missed. The production tier and the MAX
portrait/medium/action cells were all moved to 0.0 (FLUX coarse-identity window: PuLID must
bind from step 0). `pulid_max.json` node 100 is `ApplyPulidFlux` (FLUX-native, honors
start_at), so the residual 0.20 ACTIVELY delays PuLID binding 20% into denoising on every
MAX-tier wide shot — including the char-bearing landscapes that cf32ca3 now routes to "wide"
— weakening identity recovery exactly where ADR-025 said it matters (validated OFF 0.6205 →
ON 0.8779).

Surfaced: operator-1 independent verification, ea068bd (findings → director-1).
Dispositioned: director-1 PM7 handoff — fix 0.20→0.0 is POD-GATED (needs an R-MEASURE
validation burn; fold into the owed char-aerial pod re-validation).

The fix is pod-gated, but the gap is testable NOW. This strict-xfail makes CI carry the
defect (not the next session's agents). When the value is fixed to 0.0 (+ burn), this test
XPASSes and strict=True turns that into a CI failure — the signal to delete this file.

See memory: max_wide_pulid_startat_adr025_gap; realism_production_plus_char_lora (ADR-025).
"""
import pytest

from workflow_selector import MAX_QUALITY_TEMPLATES, WORKFLOW_TEMPLATES


def test_production_wide_pulid_binds_from_step_zero():
    """Reference (passes): ADR-025 moved production-tier wide to start_at=0.0 — the correct
    end-state the MAX tier should match."""
    assert WORKFLOW_TEMPLATES["wide"]["pulid_start_at"] == 0.0


def test_max_tier_non_wide_cells_already_bind_from_step_zero():
    """Reference (passes): MAX portrait/medium/action were all swept to 0.0 — proving wide
    is the LONE holdout, not a deliberate per-shot scheme."""
    for shot in ("portrait", "medium", "action"):
        assert MAX_QUALITY_TEMPLATES[shot]["pulid_start_at"] == 0.0, shot


@pytest.mark.xfail(
    strict=True,
    reason="ADR-025 gap: MAX-tier wide pulid_start_at=0.20 is the lone cell the start_at->0.0 "
    "sweep missed; node 100 is ApplyPulidFlux so it actively delays PuLID binding past the FLUX "
    "coarse-identity window. Fix 0.20->0.0 is pod-gated (R-MEASURE burn; fold into char-aerial "
    "re-validation). Surfaced operator-1 ea068bd; dispositioned director-1 PM7. Delete this file "
    "when the value is fixed + burned (XPASS under strict=True will flag it).",
)
def test_max_wide_pulid_should_also_bind_from_step_zero():
    """MAX-tier wide should bind PuLID from step 0 like the production tier and the other
    MAX cells. Currently 0.20 → this assertion fails → xfail (the tracked gap)."""
    assert MAX_QUALITY_TEMPLATES["wide"]["pulid_start_at"] == 0.0

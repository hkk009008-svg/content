"""R-VERIFY-TIER(B) pin — charmgr-cost-fresh-instance (W2:MAJOR, money).

ROW: charmgr-cost-fresh-instance
FILE: domain/character_manager.py:350
BUG: _generate_multi_angle_refs constructs a fresh CostTracker() (no budget_usd,
  no shared instance) and calls record_api_call('FLUX_KONTEXT', ...) on it for every
  angle generated.  Spend lands on that throwaway accumulator and is invisible to the
  gate-connected CostTracker the pipeline holds.  5 angles x $0.08 = ~$0.40 per
  character silently bypasses the budget gate.  Same family as costtracker-perf-uncounted.

FIX (not landed): inject the shared cost_tracker as a parameter, mirroring the
  audio-T5 pattern.  After the fix, the call accepts cost_tracker= and the shared
  tracker's spent_usd > 0 — this xpass flips (strict=True) -> delete the pin.

NON-VACUITY + FLIP-CORRECT: the test passes cost_tracker=shared_tracker to
  _generate_multi_angle_refs. Today the param does not exist -> TypeError -> XFAIL.
  After the fix the param is accepted, FAL is mocked so execution reaches the
  cost-record line, and spend lands on the shared tracker -> XPASS.
"""

import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MAJOR:charmgr-cost-fresh-instance domain/character_manager.py:350: "
        "_generate_multi_angle_refs builds a fresh CostTracker() throwaway and calls "
        "record_api_call('FLUX_KONTEXT') on it; spend is invisible to the shared "
        "gate-connected tracker (5 angles x $0.08 ~= $0.40 lost per character). "
        "Fix = inject shared cost_tracker param (audio-T5 pattern); then "
        "shared_tracker.spent_usd > 0 and this xpasses."
    ),
)
def test_multi_angle_refs_spend_lands_on_shared_tracker(tmp_path):
    """Spend from FLUX_KONTEXT multi-angle calls must land on a caller-supplied tracker.

    Passes cost_tracker=shared_tracker (the injection seam the fix adds) and patches
    fal_client + urlretrieve so the function reaches the cost-recording block without
    real network I/O.  Today the param does not exist -> TypeError -> XFAIL. After the
    fix the shared CostTracker accumulates nonzero spend -> XPASS.
    """
    from cost_tracker import CostTracker, API_COST_USD

    # Precondition: FLUX_KONTEXT must be a priced API so spend is nonzero.
    assert API_COST_USD.get("FLUX_KONTEXT", 0.0) > 0.0, (
        "precondition: FLUX_KONTEXT must be priced in API_COST_USD"
    )

    # Shared tracker the caller would inject after the fix.
    shared_tracker = CostTracker(
        db_path=str(tmp_path / "shared.db"),
        budget_usd=100.0,
    )
    assert shared_tracker.spent_usd == 0.0, "precondition: shared tracker starts at $0"

    # Set up a temporary char_path directory.
    char_path = str(tmp_path / "char")
    os.makedirs(char_path)

    # Fake canonical image file (content doesn't matter — FAL is mocked).
    canonical_path = str(tmp_path / "canonical.jpg")
    with open(canonical_path, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0" + b"\x00" * 12)  # minimal JPEG header

    # Fake FAL responses: upload returns a URL; subscribe returns one image URL.
    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "https://fal.example/canonical.jpg"
    fake_fal.subscribe.return_value = {
        "images": [{"url": "https://fal.example/angle.jpg"}]
    }

    with (
        patch.dict(
            "sys.modules",
            {"fal_client": fake_fal},
        ),
        patch(
            "domain.character_manager.fal_client",
            fake_fal,
        ),
        patch(
            "domain.character_manager.FAL_AVAILABLE",
            True,
        ),
        patch(
            "domain.character_manager.settings",
            MagicMock(fal_key="fake-key"),
        ),
        patch(
            "urllib.request.urlretrieve",
            return_value=(str(tmp_path / "angle.jpg"), {}),
        ),
    ):
        from domain.character_manager import _generate_multi_angle_refs

        # Pass the shared tracker via the injection seam the fix adds.
        # TODAY: TypeError (no cost_tracker param) -> XFAIL.
        # AFTER FIX: param accepted, spend routes to shared_tracker.
        _generate_multi_angle_refs(
            canonical_path=canonical_path,
            char_path=char_path,
            description="Test character for cost-tracking pin",
            cost_tracker=shared_tracker,
        )

    # FIXED behaviour: at least one FLUX_KONTEXT call's cost lands on shared_tracker.
    assert shared_tracker.spent_usd > 0.0, (
        f"shared_tracker.spent_usd={shared_tracker.spent_usd!r} after "
        "_generate_multi_angle_refs — FLUX_KONTEXT spend landed on a throwaway "
        "CostTracker() instead of the caller-supplied tracker "
        "(charmgr-cost-fresh-instance, character_manager.py:350)"
    )

import json
import pytest

from _scorecard import Scorecard  # top-level via conftest sys.path shim


@pytest.mark.offline
def test_scorecard_records_and_renders():
    sc = Scorecard()
    sc.record(dimension="identity", claim_id="ID-05", tier="offline", passed=True)
    sc.record(dimension="identity", claim_id="ID-LIVE-01", tier="live",
              passed=False, measured=0.51, bar=0.60, detail="ArcFace below bar")
    md = sc.render_markdown()
    assert "identity" in md
    assert "0.51" in md and "0.60" in md
    assert "FAIL" in md and "PASS" in md
    data = json.loads(sc.render_json())
    rows = [r for r in data["entries"] if r["claim_id"] == "ID-LIVE-01"]
    assert rows and rows[0]["passed"] is False and rows[0]["measured"] == 0.51


@pytest.mark.offline
def test_scorecard_dimension_rollup():
    sc = Scorecard()
    sc.record(dimension="identity", claim_id="ID-05", tier="offline", passed=True)
    sc.record(dimension="identity", claim_id="ID-06", tier="offline", passed=True)
    roll = sc.rollup()
    assert roll["identity"]["passed"] == 2 and roll["identity"]["failed"] == 0

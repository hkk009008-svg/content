import pytest


@pytest.mark.offline
def test_offline_marker_is_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    joined = "\n".join(markers)
    assert "offline:" in joined
    assert "live:" in joined
    assert "e2e:" in joined


import _ledger  # top-level via conftest sys.path shim


@pytest.mark.offline
def test_ledger_claim_ids_are_unique():
    _ledger.assert_unique()


@pytest.mark.offline
def test_ledger_lookup_and_filter():
    claim = _ledger.get("ID-01")
    assert claim.dimension == "identity"
    assert claim.manual_section
    assert claim.tier in {"offline", "live", "e2e"}
    assert all(c.dimension == "identity" for c in _ledger.by_dimension("identity"))


@pytest.mark.offline
def test_capability_record_fixture_collects(capability_record, request):
    capability_record(claim_id="ID-02", passed=True)
    sc = request.config._capability_scorecard
    assert any(e.claim_id == "ID-02" for e in sc.entries)


@pytest.mark.offline
def test_synthetic_image_fixture(synthetic_image):
    import os
    assert os.path.exists(synthetic_image)
    assert synthetic_image.endswith(".png")

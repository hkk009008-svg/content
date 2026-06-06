"""Tests for the capability scorecard builder + endpoint (Part 4 / Task 2)."""
import pytest
from cinema.capability_scorecard import build_capability_scorecard


def _make_project(**over):
    """Minimal project dict with one scene + shots/takes."""
    shot = {
        "id": "s1_01", "primary_character": "char_alex",
        "keyframe_takes": [{"id": "k1", "kind": "keyframe",
            "metadata": {"identity_score": 0.74},
            "cascade_metadata": {"engine": "KLING_NATIVE", "fallback": False, "attempts": ["KLING_NATIVE"]}}],
        "motion_takes": [{"id": "m1", "kind": "motion",
            "metadata": {"motion_fidelity": 0.82, "lipsync_score": 0.72}}],
        "approved_motion_take_id": "m1", "approved_keyframe_take_id": "k1",
        "diagnostics": [{"take_id": "k1", "scores": {"coherence": 0.64}}],
        "auto_approve_audit": [{"gate": "image", "auto_approved": True, "vetoes": [], "rule_names": ["composite_ok"], "timestamp": "2026-06-04T00:00:00Z"}],
    }
    p = {"id": "p1", "name": "neon_alley", "characters": [{"id": "char_alex"}],
         "scenes": [{"shots": [shot]}], "global_settings": {"quality_tier": "max"}}
    p.update(over)
    return p


class TestScorecardBuilder:
    def test_summary_and_dimensions(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/nonexistent")
        assert sc["project_id"] == "p1"
        assert sc["tier"] == "max"
        assert sc["summary"]["shots_total"] == 1
        ids = {d["key"] for d in sc["dimensions"]}
        assert {"identity", "coherence", "motion", "lipsync"} <= ids
        identity = next(d for d in sc["dimensions"] if d["key"] == "identity")
        assert identity["value"] == 0.74 and identity["bar"] is not None

    def test_coherence_falls_back_to_diagnostics(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/nonexistent")
        coh = next(d for d in sc["dimensions"] if d["key"] == "coherence")
        assert coh["value"] == 0.64  # sourced from shot.diagnostics when not on take.metadata
        assert coh["n_measured"] == 1

    def test_empty_project_no_fake_zeros(self):
        sc = build_capability_scorecard({"id": "e", "name": "empty", "characters": [], "scenes": [], "global_settings": {}}, project_dir="/tmp/x")
        assert sc["summary"]["shots_total"] == 0
        for d in sc["dimensions"]:
            assert d["value"] is None and d["n_measured"] == 0  # never a fabricated 0

    def test_routing_counts_fallbacks(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/x")
        assert sc["routing"]["first_try"] >= 1


class TestScorecardEndpoint:
    def _client(self):
        from web_server import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_404_when_project_absent(self):
        from unittest.mock import patch
        with patch("web_server.load_project", return_value=None):
            r = self._client().get("/api/projects/missing/capability-scorecard")
        assert r.status_code == 404
        assert r.get_json()["error"] == "Project not found"

    def test_200_returns_scorecard(self):
        from unittest.mock import patch
        with patch("web_server.load_project", return_value=_make_project()):
            with patch("web_server.get_project_dir", return_value="/tmp/nonexistent"):
                r = self._client().get("/api/projects/p1/capability-scorecard")
        assert r.status_code == 200
        body = r.get_json()
        assert body["project_id"] == "p1" and "dimensions" in body

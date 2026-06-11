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

    def test_unscored_shot_not_counted_as_clearing(self):
        # A shot that exists but has zero measured scores must NOT count toward
        # shots_clearing_all_bars (guards the vacuous-truth where the headline would
        # equal shots_total for an unscored project).
        proj = {"id": "u", "name": "unscored", "characters": [],
                "scenes": [{"shots": [{"id": "s1_01", "keyframe_takes": [], "motion_takes": []}]}],
                "global_settings": {}}
        sc = build_capability_scorecard(proj, project_dir="/tmp/x")
        assert sc["summary"]["shots_total"] == 1
        assert sc["summary"]["shots_clearing_all_bars"] == 0


class TestGateRollup:
    """The gate rollup must reflect the CURRENT decision per (shot, gate) —
    the latest audit entry — not every historical entry. The audit log is
    append-only (cinema/auto_approve.py:19) and an operator override appends a
    2nd entry rather than replacing the first (web_server.py::
    api_reject_auto_approve). Counting every entry double-counts an
    overridden approval. This mirrors the client PostRunSummary.tsx
    (latest-per-gate-per-shot) so the two surfaces can't diverge.
    """

    @staticmethod
    def _gates(shots):
        proj = {"id": "p", "name": "x", "characters": [],
                "scenes": [{"shots": shots}], "global_settings": {}}
        return build_capability_scorecard(proj, project_dir="/tmp/x")["gates"]

    def test_override_counts_as_latest_decision_only(self):
        # image auto-approved @ t0, then user-rejected @ t1 → current state is
        # vetoed. Must NOT count as both approved AND vetoed.
        shot = {"id": "s1_01", "auto_approve_audit": [
            {"gate": "image", "auto_approved": True, "vetoes": [],
             "rule_names": ["composite_ok"], "timestamp": "2026-06-04T00:00:00Z"},
            {"gate": "image", "auto_approved": False, "vetoes": ["too soft"],
             "rule_names": ["user_override"], "timestamp": "2026-06-04T01:00:00Z"},
        ]}
        # top_vetoes is Counter.most_common() → list of tuples at the Python
        # level (jsonify serializes them to JSON arrays over the wire).
        assert self._gates([shot])["image"] == {
            "approved": 0, "vetoed": 1, "top_vetoes": [("too soft", 1)]}

    def test_stale_veto_not_counted_when_later_approved(self):
        # final vetoed @ t0, then approved @ t1 → current state approved; the
        # stale veto's rule must not leak into top_vetoes.
        shot = {"id": "s1_01", "auto_approve_audit": [
            {"gate": "final", "auto_approved": False, "vetoes": ["coherence_floor"],
             "rule_names": ["coherence_floor"], "timestamp": "2026-06-04T00:00:00Z"},
            {"gate": "final", "auto_approved": True, "vetoes": [],
             "rule_names": ["ok"], "timestamp": "2026-06-04T02:00:00Z"},
        ]}
        assert self._gates([shot])["final"] == {
            "approved": 1, "vetoed": 0, "top_vetoes": []}

    def test_dedup_is_per_shot_not_global(self):
        # Two different shots both approved at the image gate → both count
        # (guards against a fix that dedups per gate globally).
        e = {"gate": "image", "auto_approved": True, "vetoes": [],
             "rule_names": [], "timestamp": "2026-06-04T00:00:00Z"}
        shots = [{"id": "s1_01", "auto_approve_audit": [dict(e)]},
                 {"id": "s1_02", "auto_approve_audit": [dict(e)]}]
        assert self._gates(shots)["image"]["approved"] == 2


class TestIdentityMulti:
    """Scorecard per_shot entry surfaces identity_strategy as identity_multi."""

    @staticmethod
    def _project_with_shot(kf_metadata: dict) -> dict:
        """Minimal project with one shot whose approved keyframe take has kf_metadata."""
        shot = {
            "id": "s1_01",
            "keyframe_takes": [{"id": "k1", "kind": "keyframe", "metadata": kf_metadata}],
            "motion_takes": [],
            "approved_keyframe_take_id": "k1",
        }
        return {"id": "p1", "name": "x", "characters": [],
                "scenes": [{"shots": [shot]}], "global_settings": {}}

    def test_per_shot_identity_multi_surfaces_promise_and_scores(self):
        proj = self._project_with_shot({
            "identity_score": 0.8,
            "identity_per_char": {"char_a": 0.8, "char_b": 0.55},
            "identity_strategy": {
                "mechanism_tag": "KONTEXT_MULTI_CHAR",
                "primary_char_id": "char_a",
                "conditioned_chars": [{"char_id": "char_a"}, {"char_id": "char_b"}],
                "unconditioned_chars": ["char_c"],
            },
        })
        card = build_capability_scorecard(proj, project_dir="/tmp/x")
        entry = card["per_shot"][0]
        assert entry["identity_multi"] == {
            "mechanism": "KONTEXT_MULTI_CHAR",
            "per_char": {"char_a": 0.8, "char_b": 0.55},
            "unconditioned": ["char_c"],
        }

    def test_per_shot_identity_multi_absent_for_legacy_takes(self):
        proj = self._project_with_shot({"identity_score": 0.8})
        card = build_capability_scorecard(proj, project_dir="/tmp/x")
        assert "identity_multi" not in card["per_shot"][0]

    def test_identity_multi_surfaces_max_tier_multi_lora(self):
        """PIN (Task 8): MAX_TIER_MULTI_LORA mechanism_tag surfaces through
        build_capability_scorecard unchanged — generic read at scorecard.py:165-169
        requires no special-casing for this tag.
        """
        project = self._project_with_shot({
            "identity_score": 0.8,
            "identity_per_char": {"char_a": 0.8, "char_b": 0.61},
            "identity_strategy": {
                "mechanism_tag": "MAX_TIER_MULTI_LORA",
                "primary_char_id": "char_a",
                "conditioned_chars": [
                    {"char_id": "char_a", "fidelity": "pulid"},
                    {"char_id": "char_b", "fidelity": "lora"},
                ],
                "unconditioned_chars": [],
            },
        })
        card = build_capability_scorecard(project, project_dir="/tmp/x")
        multi = card["per_shot"][0]["identity_multi"]
        assert multi["mechanism"] == "MAX_TIER_MULTI_LORA"
        # operator Lane-V 23:05:51Z fold: per-char + unconditioned asserted
        # for the MAX tag specifically (not just via the KONTEXT sibling).
        assert multi["per_char"] == {"char_a": 0.8, "char_b": 0.61}
        assert multi["unconditioned"] == []


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

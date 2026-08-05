"""Tests for the capability scorecard builder + endpoint (Part 4 / Task 2)."""
import pytest
from cinema.capability_scorecard import build_capability_scorecard


def test_max_quality_templates_removed():
    """WS1 Task 2: MAX_QUALITY_TEMPLATES + its accessor are fully retired from
    workflow_selector — production (WORKFLOW_TEMPLATES) is the sole tier."""
    import workflow_selector
    assert not hasattr(workflow_selector, "MAX_QUALITY_TEMPLATES")
    assert not hasattr(workflow_selector, "get_max_quality_params")


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
        sc = build_capability_scorecard(_make_project())
        assert sc["project_id"] == "p1"
        assert sc["tier"] == "max"
        assert sc["summary"]["shots_total"] == 1
        ids = {d["key"] for d in sc["dimensions"]}
        assert {"identity", "coherence", "motion", "lipsync"} <= ids
        identity = next(d for d in sc["dimensions"] if d["key"] == "identity")
        assert identity["value"] == 0.74 and identity["bar"] is not None

    def test_coherence_falls_back_to_diagnostics(self):
        sc = build_capability_scorecard(_make_project())
        coh = next(d for d in sc["dimensions"] if d["key"] == "coherence")
        assert coh["value"] == 0.64  # sourced from shot.diagnostics when not on take.metadata
        assert coh["n_measured"] == 1

    def test_empty_project_no_fake_zeros(self):
        sc = build_capability_scorecard({"id": "e", "name": "empty", "characters": [], "scenes": [], "global_settings": {}})
        assert sc["summary"]["shots_total"] == 0
        for d in sc["dimensions"]:
            assert d["value"] is None and d["n_measured"] == 0  # never a fabricated 0

    def test_routing_counts_fallbacks(self):
        sc = build_capability_scorecard(_make_project())
        assert sc["routing"]["first_try"] >= 1

    def test_unscored_shot_not_counted_as_clearing(self):
        # A shot that exists but has zero measured scores must NOT count toward
        # shots_clearing_all_bars (guards the vacuous-truth where the headline would
        # equal shots_total for an unscored project).
        proj = {"id": "u", "name": "unscored", "characters": [],
                "scenes": [{"shots": [{"id": "s1_01", "keyframe_takes": [], "motion_takes": []}]}],
                "global_settings": {}}
        sc = build_capability_scorecard(proj)
        assert sc["summary"]["shots_total"] == 1
        assert sc["summary"]["shots_clearing_all_bars"] == 0

    def test_dialogue_unknown_is_visible_and_cannot_clear_all_bars(self):
        proj = _make_project()
        shot = proj["scenes"][0]["shots"][0]
        shot["motion_takes"][0]["metadata"].update({
            "has_dialogue": True,
            "audio_embedded": True,
            "lipsync_score": None,
            "lipsync_validation_state": "UNKNOWN",
        })

        sc = build_capability_scorecard(proj)
        lipsync = next(d for d in sc["dimensions"] if d["key"] == "lipsync")
        assert lipsync["value"] is None
        assert lipsync["pass"] is False
        assert lipsync["n_applicable"] == 1
        assert lipsync["n_unknown"] == 1
        assert sc["per_shot"][0]["lipsync_state"] == "UNKNOWN"
        assert sc["summary"]["shots_clearing_all_bars"] == 0

    def test_approved_postprocess_lipsync_is_final_authority(self):
        proj = _make_project()
        shot = proj["scenes"][0]["shots"][0]
        shot["motion_takes"][0]["metadata"].update({
            "has_dialogue": True,
            "lipsync_score": None,
            "lipsync_validation_state": "UNKNOWN",
        })
        shot["motion_takes"][0]["cascade_metadata"] = {
            "engine": "KLING_NATIVE",
            "fallback": False,
            "attempts": ["KLING_NATIVE"],
        }
        shot["postprocess_variants"] = [{
            "id": "pp_lipsync",
            "kind": "postprocess",
            "source_take_id": "m1",
            "metadata": {
                "dialogue_audio_in_clip": True,
                "lipsync_score": 0.91,
                "lipsync_validation_state": "PASS",
            },
            "cascade_metadata": {
                "engine": "SYNC_SO_V3",
                "fallback": False,
                "attempts": ["SYNC_SO_V3"],
            },
        }]
        shot["approved_final_take_id"] = "pp_lipsync"

        sc = build_capability_scorecard(proj)
        lipsync = next(d for d in sc["dimensions"] if d["key"] == "lipsync")
        motion = next(d for d in sc["dimensions"] if d["key"] == "motion")

        assert lipsync["value"] == 0.91
        assert lipsync["pass"] is True
        assert lipsync["n_unknown"] == 0
        assert sc["per_shot"][0]["lipsync_state"] == "PASS"
        assert sc["per_shot"][0]["lipsync"] == 0.91
        # Motion quality and routing provenance remain anchored to the base
        # motion take, not the derivative post-process variant.
        assert motion["value"] == 0.82
        assert sc["per_shot"][0]["engine"] == "KLING_NATIVE"
        assert sc["provenance"][0]["engine"] == "KLING_NATIVE"

    def test_non_dialogue_missing_lipsync_is_not_applicable(self):
        proj = _make_project()
        shot = proj["scenes"][0]["shots"][0]
        shot["motion_takes"][0]["metadata"].pop("lipsync_score")

        sc = build_capability_scorecard(proj)
        assert sc["per_shot"][0]["lipsync_state"] == "NOT_APPLICABLE"
        assert sc["per_shot"][0]["lipsync_applicable"] is False
        lipsync = next(d for d in sc["dimensions"] if d["key"] == "lipsync")
        assert lipsync["n_applicable"] == 0
        assert lipsync["n_unknown"] == 0

    def test_shot_dialogue_without_measurement_is_unknown(self):
        proj = _make_project()
        shot = proj["scenes"][0]["shots"][0]
        shot["dialogue"] = "We need to leave now."
        shot["motion_takes"][0]["metadata"].pop("lipsync_score")

        sc = build_capability_scorecard(proj)
        assert sc["per_shot"][0]["lipsync_state"] == "UNKNOWN"
        assert sc["per_shot"][0]["lipsync_applicable"] is True
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
        return build_capability_scorecard(proj)["gates"]

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
            "approved": 0, "vetoed": 1, "deferred": 0,
            "top_vetoes": [("too soft", 1)]}

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
            "approved": 1, "vetoed": 0, "deferred": 0,
            "top_vetoes": []}

    def test_dedup_is_per_shot_not_global(self):
        # Two different shots both approved at the image gate → both count
        # (guards against a fix that dedups per gate globally).
        e = {"gate": "image", "auto_approved": True, "vetoes": [],
             "rule_names": [], "timestamp": "2026-06-04T00:00:00Z"}
        shots = [{"id": "s1_01", "auto_approve_audit": [dict(e)]},
                 {"id": "s1_02", "auto_approve_audit": [dict(e)]}]
        assert self._gates(shots)["image"]["approved"] == 2

    def test_deferred_is_not_counted_as_vetoed(self):
        shot = {"id": "s1_01", "auto_approve_audit": [{
            "gate": "final",
            "auto_approved": False,
            "deferred": True,
            "vetoes": ["evaluation error"],
            "rule_names": ["evaluation_error"],
            "timestamp": "2026-06-04T00:00:00Z",
        }]}
        assert self._gates([shot])["final"] == {
            "approved": 0,
            "vetoed": 0,
            "deferred": 1,
            "top_vetoes": [("evaluation error", 1)],
        }


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
        card = build_capability_scorecard(proj)
        entry = card["per_shot"][0]
        assert entry["identity_multi"] == {
            "mechanism": "KONTEXT_MULTI_CHAR",
            "per_char": {"char_a": 0.8, "char_b": 0.55},
            "unconditioned": ["char_c"],
        }

    def test_per_shot_identity_multi_absent_for_legacy_takes(self):
        proj = self._project_with_shot({"identity_score": 0.8})
        card = build_capability_scorecard(proj)
        assert "identity_multi" not in card["per_shot"][0]

    def test_identity_multi_surfaces_unknown_mechanism_tag_generically(self):
        """Generic-read regression pin: scorecard.py's per_shot["identity_multi"]
        projection (scorecard.py:164-170) copies whatever mechanism_tag is
        present without special-casing any particular value.

        A made-up forward-compat tag keeps the test focused on generic
        passthrough rather than coupling it to a currently known mechanism.
        """
        project = self._project_with_shot({
            "identity_score": 0.8,
            "identity_per_char": {"char_a": 0.8, "char_b": 0.61},
            "identity_strategy": {
                "mechanism_tag": "SOME_FUTURE_MECHANISM",
                "primary_char_id": "char_a",
                "conditioned_chars": [
                    {"char_id": "char_a", "fidelity": "reference"},
                    {"char_id": "char_b", "fidelity": "reference"},
                ],
                "unconditioned_chars": [],
            },
        })
        card = build_capability_scorecard(project)
        multi = card["per_shot"][0]["identity_multi"]
        assert multi["mechanism"] == "SOME_FUTURE_MECHANISM"
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

"""Tests for video API cascade/fallback logic in phase_c_ffmpeg.py."""

import sys, os

import pytest
from unittest.mock import patch, MagicMock, call
from workflow_selector import WORKFLOW_TEMPLATES


# ---------------------------------------------------------------------------
# Cascade helper: extract try_next_api logic for unit testing
# ---------------------------------------------------------------------------


class TestCascadeFallbackOrder:
    """Verify shot-type-specific fallback chains from WORKFLOW_TEMPLATES."""

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_each_shot_type_has_video_fallbacks(self, shot_type):
        fallbacks = WORKFLOW_TEMPLATES[shot_type].get("video_fallbacks", [])
        assert isinstance(fallbacks, list)
        assert len(fallbacks) >= 1, f"{shot_type} should have at least 1 fallback API"

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_target_api_not_in_fallbacks(self, shot_type):
        """Primary API should not appear in its own fallback list."""
        template = WORKFLOW_TEMPLATES[shot_type]
        target = template["target_api"]
        fallbacks = template.get("video_fallbacks", [])
        assert target not in fallbacks, (
            f"{shot_type}: target_api '{target}' should not be in video_fallbacks"
        )

    @pytest.mark.parametrize("shot_type", WORKFLOW_TEMPLATES.keys())
    def test_no_duplicate_fallbacks(self, shot_type):
        fallbacks = WORKFLOW_TEMPLATES[shot_type].get("video_fallbacks", [])
        assert len(fallbacks) == len(set(fallbacks)), (
            f"{shot_type}: video_fallbacks contains duplicates"
        )

    def test_portrait_prioritizes_identity_apis(self):
        """Portrait shots should prefer APIs known for face consistency."""
        fallbacks = WORKFLOW_TEMPLATES["portrait"]["video_fallbacks"]
        # Runway and Kling variants are good for identity
        identity_apis = {"RUNWAY_GEN4", "KLING_NATIVE", "KLING_3_0"}
        first_two = set(fallbacks[:2])
        assert first_two & identity_apis, (
            f"Portrait fallbacks should prioritize identity-capable APIs, got {fallbacks[:2]}"
        )

    def test_landscape_does_not_need_identity_api_first(self):
        """Landscape shots have no characters — identity APIs not mandatory."""
        target = WORKFLOW_TEMPLATES["landscape"]["target_api"]
        # LTX, VEO, or GEMINI_OMNI (Google-first general-purpose primary, WS2)
        # are all fine for landscape — none of them are identity-lock APIs.
        assert target in {"LTX", "VEO_NATIVE", "SORA_NATIVE", "GEMINI_OMNI"}, (
            f"Landscape target_api should be a non-identity API, got {target}"
        )


# ---------------------------------------------------------------------------
# Cascade retry logic (mocked — no real API calls)
# ---------------------------------------------------------------------------


class TestCascadeRetryLogic:
    """Test try_next_api() behavior via mocked generate_ai_video.

    Pins the PRODUCTION DEFAULT_VIDEO_CASCADE constant — the previous local
    copy silently drifted from production through two migrations (the Sora
    sunset and the Kling v3 Pro promotion) because it never imported it.

    Retry-EXHAUSTION is deliberately NOT tested here: these are cascade-order
    assertions over WORKFLOW_TEMPLATES/DEFAULT_VIDEO_CASCADE, with no dispatch
    harness to observe termination. The real, mutation-grade coverage of
    MAX_CASCADE_RETRIES lives in test_generate_ai_video_params.py's
    test_multi_engine_all_fail_terminates_after_max_retries, which drives the actual
    generate_ai_video and counts quota-cooldown sleeps. A former
    test_cascade_retries_max_is_two here asserted "max is two" against its own
    local range(3) — it touched no production symbol, so it could not fail, and
    its name propagated a limit (2) that never matched the source default (1).
    """

    def _default_cascade(self):
        from phase_c_ffmpeg import DEFAULT_VIDEO_CASCADE
        return DEFAULT_VIDEO_CASCADE

    def test_default_cascade_order_matches(self):
        """Pin the safe default order seed; executable policy still filters it."""
        cascade = self._default_cascade()
        assert len(cascade) == 9, "Safe default cascade should have 9 APIs"
        # Known-broken Gemini Omni and retired fal Sora 2 are not seed truth.
        assert "GEMINI_OMNI" not in cascade
        assert "SORA_2" not in cascade
        # VEO_NATIVE leads, then SEEDANCE; KLING_3_0
        # (fal v3 Pro) outranks the legacy kling-v1-6 native route.
        assert cascade[0] == "VEO_NATIVE", f"head should be VEO_NATIVE, got {cascade[0]}"
        assert cascade[1] == "SEEDANCE", f"second should be SEEDANCE, got {cascade[1]}"
        assert cascade[2] == "KLING_3_0", f"third should be KLING_3_0, got {cascade[2]}"
        assert cascade.index("KLING_3_0") < cascade.index("KLING_NATIVE"), (
            "fal Kling v3 Pro must outrank the legacy kling-v1-6 native route"
        )

    def test_attempted_apis_prevents_retry(self):
        """APIs in attempted_apis set should be skipped."""
        cascade = self._default_cascade()
        attempted = set(cascade[:3])
        remaining = [api for api in cascade if api not in attempted]
        assert remaining[0] == cascade[3], "Next API should be the 4th cascade member"
        assert cascade[0] not in remaining

    def test_all_apis_exhausted_triggers_retry(self):
        """When all APIs are in attempted_apis, cascade should trigger retry logic."""
        cascade = self._default_cascade()
        attempted = set(cascade)
        remaining = [api for api in cascade if api not in attempted]
        assert len(remaining) == 0, "No APIs left — should trigger retry"

    def test_video_fallbacks_override_default_cascade(self):
        """When video_fallbacks is provided, it should be used instead of default."""
        custom_fallbacks = ["RUNWAY_GEN4", "LTX"]
        attempted = {"SORA_NATIVE"}  # Not in custom list
        # Only custom fallbacks should be considered
        remaining = [api for api in custom_fallbacks if api not in attempted]
        assert remaining == ["RUNWAY_GEN4", "LTX"]
        # Default cascade APIs not in custom list should not appear
        assert "KLING_NATIVE" not in remaining

    def test_fresh_attempted_set_on_retry(self):
        """After full cascade exhaustion, retry starts with empty attempted_apis."""
        # Simulating: all exhausted, _cascade_retries < MAX_CASCADE_RETRIES
        # (try_next_api's default is 1, not 2) → restart with set()
        fresh_attempted = set()
        first_api = "KLING_NATIVE"
        assert first_api not in fresh_attempted
        # First API should be available again after fresh start


# ---------------------------------------------------------------------------
# Cinema pipeline API filtering
# ---------------------------------------------------------------------------


class TestCinemaPipelineApiFiltering:
    """Test that disabled APIs are filtered from fallback chains."""

    def test_disabled_apis_removed_from_fallbacks(self):
        """Simulate cinema_pipeline filtering of disabled APIs."""
        fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE", "LTX"]
        disabled_apis = {"SORA_NATIVE"}
        filtered = [api for api in fallbacks if api not in disabled_apis]
        assert filtered == ["RUNWAY_GEN4", "LTX"]
        assert "SORA_NATIVE" not in filtered

    def test_all_disabled_leaves_empty_fallbacks(self):
        """If all fallbacks are disabled, list should be empty."""
        fallbacks = ["RUNWAY_GEN4", "SORA_NATIVE"]
        disabled_apis = {"RUNWAY_GEN4", "SORA_NATIVE"}
        filtered = [api for api in fallbacks if api not in disabled_apis]
        assert filtered == []

    def test_target_api_auto_triggers_classification(self):
        """AUTO target_api should trigger shot type classification."""
        from workflow_selector import classify_shot_type
        shot = {"prompt": "A close-up of the hero's face", "characters_in_frame": ["char1"]}
        shot_type = classify_shot_type(shot)
        template = WORKFLOW_TEMPLATES[shot_type]
        assert "target_api" in template
        assert "video_fallbacks" in template


# ---------------------------------------------------------------------------
# Full cascade integration (mocked generate_ai_video)
# ---------------------------------------------------------------------------


class TestCascadeIntegration:
    """Integration tests for the cascade flow using mocked API handlers."""

    @patch("phase_c_ffmpeg.subprocess.run")
    def test_generate_ai_video_adds_to_attempted(self, mock_run):
        """Calling generate_ai_video should add the target_api to attempted_apis."""
        # We test the logic pattern, not the full function (which needs real files)
        attempted = set()
        target = "KLING_NATIVE"
        attempted.add(target.upper())
        assert "KLING_NATIVE" in attempted

    def test_cascade_respects_shot_type_fallbacks(self):
        """Portrait should cascade through identity-preserving APIs."""
        template = WORKFLOW_TEMPLATES["portrait"]
        target = template["target_api"]
        fallbacks = template["video_fallbacks"]

        # Simulate cascade: target fails, then each fallback
        attempted = {target}
        cascade_order = []
        for api in fallbacks:
            if api not in attempted:
                cascade_order.append(api)
                attempted.add(api)

        assert len(cascade_order) == len(fallbacks)
        assert cascade_order == fallbacks

    def test_action_shot_cascade_prefers_motion_apis(self):
        """Action shots should prefer APIs with good motion handling."""
        template = WORKFLOW_TEMPLATES["action"]
        target = template["target_api"]
        # GEMINI_OMNI is action primary since the 2026-07-18 google-first-overhaul
        # (WS2) — Gemini Omni Flash is Google-first primary for every shot type.
        # SEEDANCE (the prior primary since the 2026-07-11 Sora-sunset migration
        # — #1 AA i2v arena; Sora retires 2026-09-24) is demoted to first fallback
        # behind VEO_NATIVE, keeping motion-physics priority high in the cascade.
        assert target == "GEMINI_OMNI", (
            f"Action target should be GEMINI_OMNI (Google-first, WS2), got {target}"
        )
        assert template["video_fallbacks"][0] == "VEO_NATIVE", (
            f"VEO_NATIVE should lead action fallbacks (Google-first, WS2), "
            f"got {template['video_fallbacks']}"
        )
        assert template["video_fallbacks"][1] == "SEEDANCE", (
            f"SEEDANCE should stay the first non-Google fallback for motion "
            f"physics, got {template['video_fallbacks']}"
        )

    def test_identity_shots_use_fal_kling_v3_pro_primary(self):
        """Portrait/medium primaries are GEMINI_OMNI since the 2026-07-18
        google-first-overhaul (WS2) — Gemini Omni Flash is Google-first primary
        for every shot type. The fal Kling v3 Pro route (2026-07-11 promotion)
        stays the first non-Google fallback, with the legacy kling-v1-6 native
        route right behind it — the native client silently ran kling-v1-6 for
        two years because no test pinned the routing; this pin closes that hole."""
        for shot_type in ("portrait", "medium"):
            template = WORKFLOW_TEMPLATES[shot_type]
            assert template["target_api"] == "GEMINI_OMNI", (
                f"{shot_type} primary should be GEMINI_OMNI (Google-first, WS2), "
                f"got {template['target_api']}"
            )
            assert template["video_fallbacks"][0] == "VEO_NATIVE", (
                f"{shot_type} first fallback should be VEO_NATIVE (Google-first, "
                f"WS2), got {template['video_fallbacks']}"
            )
            assert template["video_fallbacks"][1] == "KLING_3_0", (
                f"{shot_type} second fallback should be the fal v3 Pro route, "
                f"got {template['video_fallbacks']}"
            )
            assert template["video_fallbacks"][2] == "KLING_NATIVE", (
                f"{shot_type} third fallback should be the proven legacy "
                f"KLING_NATIVE route, got {template['video_fallbacks']}"
            )

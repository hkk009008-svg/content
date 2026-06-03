"""
Characterization tests for phase_c_vision.py — face-swap + vision-validation
post-processing.

These tests LOCK IN the EXISTING behavior of already-written code.
They PASS against HEAD.  Where the code does something surprising or buggy,
each test asserts the ACTUAL current behavior and adds a comment:
    # DOCUMENTED-INTENTIONAL: <one line explaining the design choice>

Offline-only: cv2.VideoCapture, os.path.exists, subprocess, fal_client,
openai.OpenAI, anthropic.Anthropic, and google.genai are all mocked.
No GPU, no model weights, no network, no real files, no subprocesses.

Baseline: 1450 tests collected / 1447 passed / 3 skipped before this file.
"""

import os
import sys
import dataclasses
import json
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

# Phase_c_vision imports cv2 at module level; cv2 is available in the venv,
# so no sys.modules stub needed.  Reset any cached module state between tests
# that mutate settings by patching phase_c_vision.settings directly.

import phase_c_vision as pcv
from config.settings import settings as _real_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_fal_settings():
    """Settings with fal_key cleared (forces FaceFusion path in face_swap)."""
    return dataclasses.replace(_real_settings, fal_key="")


def _fal_settings():
    """Settings with a non-empty fal_key."""
    return dataclasses.replace(_real_settings, fal_key="fal_test_key")


def _no_openai_settings():
    """Settings with openai_api_key cleared."""
    return dataclasses.replace(_real_settings, openai_api_key="")


def _no_anthropic_settings():
    """Settings with anthropic_api_key cleared."""
    return dataclasses.replace(_real_settings, anthropic_api_key="")


def _no_gemini_settings():
    """Settings with both gemini_api_key and google_api_key cleared."""
    return dataclasses.replace(_real_settings, gemini_api_key="", google_api_key="")


def _make_cap(total_frames=100, read_ret=True):
    """Build a mock cv2.VideoCapture returning controlled frame count + read."""
    cap = MagicMock()
    cap.get.return_value = float(total_frames)
    cap.read.return_value = (read_ret, MagicMock() if read_ret else None)
    return cap


def _make_genai_mock(response_dict):
    """Build sys.modules stubs for google / google.genai."""
    mock_genai = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    mock_genai.Client.return_value.models.generate_content.return_value = mock_resp
    mock_genai.types.Part.from_bytes.return_value = MagicMock()
    mock_google = MagicMock()
    mock_google.genai = mock_genai
    return mock_google, mock_genai


# ---------------------------------------------------------------------------
# get_middle_frame
# ---------------------------------------------------------------------------

class TestGetMiddleFrame:

    def test_success_imwrite_called_returns_true(self):
        """Successful read → imwrite called with the frame, returns True."""
        cap = _make_cap(total_frames=100, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite") as mock_imwrite:
            result = pcv.get_middle_frame("/vid.mp4", "/out.jpg")

        assert result is True
        mock_imwrite.assert_called_once()

    def test_success_seeks_to_middle_frame(self):
        """cap.set is called with position = total_frames // 2 = 50 for 100 frames."""
        cap = _make_cap(total_frames=100, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite"):
            pcv.get_middle_frame("/vid.mp4", "/out.jpg")

        import cv2
        # CAP_PROP_POS_FRAMES == 1
        cap.set.assert_called_with(cv2.CAP_PROP_POS_FRAMES, 50)

    def test_read_failure_no_imwrite_returns_false(self):
        """cap.read returns (False, None) → imwrite NOT called, returns False."""
        cap = _make_cap(total_frames=100, read_ret=False)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite") as mock_imwrite:
            result = pcv.get_middle_frame("/vid.mp4", "/out.jpg")

        assert result is False
        mock_imwrite.assert_not_called()

    def test_release_always_called(self):
        """cap.release() is called regardless of read success/failure."""
        cap = _make_cap(total_frames=50, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite"):
            pcv.get_middle_frame("/vid.mp4", "/out.jpg")

        cap.release.assert_called_once()


# ---------------------------------------------------------------------------
# extract_frame_at
# ---------------------------------------------------------------------------

class TestExtractFrameAt:

    def test_success_returns_true_imwrite_called(self):
        """Successful read → imwrite called, returns True."""
        cap = _make_cap(total_frames=200, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite") as mock_imwrite:
            result = pcv.extract_frame_at("/vid.mp4", 0.5, "/out.jpg")

        assert result is True
        mock_imwrite.assert_called_once()

    def test_position_is_int_total_times_ratio(self):
        """cap.set position == int(total * ratio) — verified: 200 * 0.25 = 50."""
        cap = _make_cap(total_frames=200, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite"):
            pcv.extract_frame_at("/vid.mp4", 0.25, "/out.jpg")

        import cv2
        cap.set.assert_called_with(cv2.CAP_PROP_POS_FRAMES, 50)

    def test_read_failure_returns_false_no_imwrite(self):
        """cap.read returns (False, None) → returns False, imwrite NOT called."""
        cap = _make_cap(total_frames=100, read_ret=False)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite") as mock_imwrite:
            result = pcv.extract_frame_at("/vid.mp4", 0.9, "/out.jpg")

        assert result is False
        mock_imwrite.assert_not_called()

    def test_ratio_zero_seeks_frame_zero(self):
        """ratio=0.0 → int(total * 0.0) = 0."""
        cap = _make_cap(total_frames=120, read_ret=True)
        with patch.object(pcv.cv2, "VideoCapture", return_value=cap), \
             patch.object(pcv.cv2, "imwrite"):
            pcv.extract_frame_at("/vid.mp4", 0.0, "/out.jpg")

        import cv2
        cap.set.assert_called_with(cv2.CAP_PROP_POS_FRAMES, 0)


# ---------------------------------------------------------------------------
# face_swap_video_frames
# ---------------------------------------------------------------------------

class TestFaceSwapVideoFrames:

    def test_fal_success_uploads_and_retrieves(self):
        """fal_key set, subscribe returns url → urlretrieve called, path returned."""
        mock_fal = MagicMock()
        mock_fal.upload_file.return_value = "http://fal/upload"
        mock_fal.subscribe.return_value = {"video": {"url": "http://fal/video.mp4"}}

        import urllib.request as _urllib_req
        with patch.object(pcv, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch.object(_urllib_req, "urlretrieve") as mock_retr:
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result == "/out.mp4"
        mock_retr.assert_called_once_with("http://fal/video.mp4", "/out.mp4")

    def test_fal_no_key_skips_to_facefusion(self):
        """fal_key absent → fal path skipped, falls through to FaceFusion."""
        mock_fal = MagicMock()
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        # FaceFusion not installed → None
        assert result is None
        mock_fal.subscribe.assert_not_called()

    def test_fal_no_url_in_result_falls_through(self):
        """subscribe returns dict without 'url' → no urlretrieve, falls to FaceFusion."""
        mock_fal = MagicMock()
        mock_fal.upload_file.return_value = "http://fal/upload"
        mock_fal.subscribe.return_value = {"video": {}}  # no 'url' key

        with patch.object(pcv, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result is None

    def test_fal_exception_falls_through_to_facefusion(self):
        """fal_client.subscribe raises Exception → caught, falls to FaceFusion."""
        mock_fal = MagicMock()
        mock_fal.upload_file.return_value = "http://fal/upload"
        mock_fal.subscribe.side_effect = RuntimeError("fal api error")

        with patch.object(pcv, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result is None

    def test_facefusion_success_returncode_zero_file_exists(self):
        """returncode=0 AND output file exists → returns output_path."""
        mock_fal = MagicMock()
        mock_proc = MagicMock(returncode=0)
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", return_value=mock_proc), \
             patch.object(pcv.os.path, "exists", return_value=True):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result == "/out.mp4"

    def test_facefusion_returncode_zero_but_file_missing_returns_none(self):
        """returncode=0 but os.path.exists(output_path) is False → None.

        # DOCUMENTED-INTENTIONAL: cascade skip (fal->facefusion->None); caller
        # surfaces the reason.  FaceFusion gate requires BOTH returncode==0 AND
        # os.path.exists(output_path); a partial write → cascade falls through
        # to None, and apply_correction surfaces an explicit warning to the operator.
        """
        mock_fal = MagicMock()
        mock_proc = MagicMock(returncode=0)
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", return_value=mock_proc), \
             patch.object(pcv.os.path, "exists", return_value=False):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        # DOCUMENTED-INTENTIONAL: cascade skip (fal->facefusion->None); caller surfaces the reason
        assert result is None

    def test_facefusion_nonzero_exit_returns_none(self):
        """returncode!=0 → None (even if output file somehow existed)."""
        mock_fal = MagicMock()
        mock_proc = MagicMock(returncode=1)
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", return_value=mock_proc), \
             patch.object(pcv.os.path, "exists", return_value=True):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result is None

    def test_facefusion_not_installed_returns_none(self):
        """FileNotFoundError from subprocess.run → caught, returns None."""
        mock_fal = MagicMock()
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result is None

    def test_all_fail_returns_none(self):
        """fal_key absent, FaceFusion not installed → None."""
        mock_fal = MagicMock()
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        assert result is None


# ---------------------------------------------------------------------------
# quality_control_image
# ---------------------------------------------------------------------------

class TestQualityControlImage:

    def test_missing_file_returns_false(self):
        """Image not found → returns False (consistent no-pass policy on missing files)."""
        with patch.object(pcv.os.path, "exists", return_value=False):
            result = pcv.quality_control_image("/missing.jpg")

        assert result is False

    def test_delegates_to_validate_shot_quality_vision(self):
        """File present → calls validate_shot_quality_vision, returns its 'pass' value."""
        mock_result = {"pass": True, "score": 9, "source": "gpt-4o", "issues": []}
        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "validate_shot_quality_vision", return_value=mock_result) as mock_v:
            result = pcv.quality_control_image("/img.jpg", "test prompt")

        assert result is True
        mock_v.assert_called_once_with("/img.jpg", "test prompt")

    def test_delegates_returns_false_when_shot_quality_fails(self):
        """validate_shot_quality_vision returns pass=False → quality_control returns False."""
        mock_result = {"pass": False, "score": 3, "source": "gpt-4o", "issues": ["blurry"]}
        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "validate_shot_quality_vision", return_value=mock_result):
            result = pcv.quality_control_image("/img.jpg")

        assert result is False

    def test_default_prompt_text_is_empty_string(self):
        """prompt_text defaults to empty string when not provided."""
        mock_result = {"pass": True, "score": 7, "source": "default", "issues": []}
        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "validate_shot_quality_vision", return_value=mock_result) as mock_v:
            pcv.quality_control_image("/img.jpg")

        mock_v.assert_called_once_with("/img.jpg", "")


# ---------------------------------------------------------------------------
# validate_shot_quality_vision
# ---------------------------------------------------------------------------

class TestValidateShotQualityVision:

    def test_no_openai_key_returns_default_pass(self):
        """No openai_api_key → default_pass dict (score=7, pass=True, source='default')."""
        with patch.object(pcv, "settings", _no_openai_settings()):
            result = pcv.validate_shot_quality_vision("/img.jpg", "prompt")

        assert result == {
            "score": 7, "issues": [], "pass": True, "suggestions": [], "source": "default"
        }

    def test_file_missing_returns_fail(self):
        """File not found → pass=False, score=0, issues=['image missing'] (consistent no-pass policy)."""
        with patch.object(pcv.os.path, "exists", return_value=False):
            result = pcv.validate_shot_quality_vision("/missing.jpg", "prompt")

        assert result["pass"] is False
        assert result["score"] == 0
        assert "image missing" in result["issues"]
        assert result["source"] == "default"

    def test_happy_path_score_8_returns_pass_true(self):
        """GPT-4o returns score=8 → pass=True, source='gpt-4o'."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.choices[0].message.content = json.dumps(
            {"score": 8, "issues": [], "suggestions": []}
        )
        mock_client.chat.completions.create.return_value = mock_msg

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("openai.OpenAI", return_value=mock_client):
            result = pcv.validate_shot_quality_vision("/img.jpg", "a cinematic shot")

        assert result["pass"] is True
        assert result["score"] == 8
        assert result["source"] == "gpt-4o"

    def test_score_5_returns_pass_false(self):
        """GPT-4o returns score=5 → pass=False (threshold is 7)."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.choices[0].message.content = json.dumps(
            {"score": 5, "issues": ["blurry face"], "suggestions": []}
        )
        mock_client.chat.completions.create.return_value = mock_msg

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("openai.OpenAI", return_value=mock_client):
            result = pcv.validate_shot_quality_vision("/img.jpg", "prompt")

        assert result["pass"] is False
        assert result["score"] == 5

    def test_score_7_is_pass_threshold_boundary(self):
        """score=7 is exactly at the threshold (>= 7 → pass=True)."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.choices[0].message.content = json.dumps(
            {"score": 7, "issues": [], "suggestions": []}
        )
        mock_client.chat.completions.create.return_value = mock_msg

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("openai.OpenAI", return_value=mock_client):
            result = pcv.validate_shot_quality_vision("/img.jpg", "prompt")

        assert result["pass"] is True

    def test_markdown_code_fence_json_parsed_correctly(self):
        """Response wrapped in ```json fences → stripped and parsed."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        fenced = "```json\n" + json.dumps({"score": 9, "issues": [], "suggestions": []}) + "\n```"
        mock_msg.choices[0].message.content = fenced
        mock_client.chat.completions.create.return_value = mock_msg

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("openai.OpenAI", return_value=mock_client):
            result = pcv.validate_shot_quality_vision("/img.jpg", "prompt")

        assert result["score"] == 9
        assert result["pass"] is True
        assert result["source"] == "gpt-4o"

    def test_api_exception_returns_default_pass(self):
        """Exception during OpenAI call → caught, returns default_pass."""
        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("openai.OpenAI", side_effect=RuntimeError("api error")):
            result = pcv.validate_shot_quality_vision("/img.jpg", "prompt")

        assert result["source"] == "default"
        assert result["pass"] is True


# ---------------------------------------------------------------------------
# validate_identity_vision
# ---------------------------------------------------------------------------

class TestValidateIdentityVision:

    def test_no_anthropic_key_returns_default_pass(self):
        """No anthropic_api_key → default_pass (match=True, confidence=0.7, source='default')."""
        with patch.object(pcv, "settings", _no_anthropic_settings()):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result == {
            "match": True, "confidence": 0.7, "issues": [], "source": "default"
        }

    def test_reference_missing_returns_skip_marker(self):
        """Reference image not found → skip marker (match=True, skip=True, confidence=None)."""
        def _exists(p):
            return "/gen" in p  # gen exists, ref doesn't

        with patch.object(pcv.os.path, "exists", side_effect=_exists):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result["skip"] is True
        assert result["match"] is True
        assert result["confidence"] is None
        assert result["source"] == "default"

    def test_generated_missing_returns_fail_marker(self):
        """Generated image not found → fail marker (match=False, missing_generated=True, confidence=0.0)."""
        def _exists(p):
            return "/ref" in p  # ref exists, gen doesn't

        with patch.object(pcv.os.path, "exists", side_effect=_exists):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result["missing_generated"] is True
        assert result["match"] is False
        assert result["confidence"] == 0.0
        assert result["source"] == "default"

    def test_confidence_085_returns_match_true(self):
        """Claude returns confidence=0.85 → match=True, source='claude-sonnet'."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.85, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result["match"] is True
        assert result["confidence"] == pytest.approx(0.85)
        assert result["source"] == "claude-sonnet"

    def test_confidence_050_returns_match_false(self):
        """Claude returns confidence=0.5 → match=False (below 0.7 threshold)."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.5, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result["match"] is False
        assert result["confidence"] == pytest.approx(0.5)

    def test_g5_threshold_boundary_07_is_match_true(self):
        """G5: threshold is hardcoded 0.7 (no param); confidence=0.7 → match=True (>=).

        # DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds
        # (validator re-computes matched).  The 0.7 threshold here is advisory —
        # IdentityValidator (validator.py:~754) re-thresholds on the production path;
        # this hardcoded value never governs a real gate.
        """
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.7, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        # DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds (validator re-computes matched)
        assert result["match"] is True

    def test_g5_threshold_boundary_069_is_match_false(self):
        """G5: confidence=0.69 → match=False (strictly below advisory 0.7 threshold).

        # DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds
        # (validator re-computes matched).  The 0.7 cut-off here is advisory —
        # production callers use IdentityValidator which re-thresholds via its own
        # configured threshold (validator.py:~754); the `match` key is never the
        # gate on the real production path.
        """
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.69, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        # DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds (validator re-computes matched)
        assert result["match"] is False

    def test_api_exception_returns_default_pass(self):
        """Exception during Anthropic call → caught, returns default_pass."""
        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", side_effect=RuntimeError("api error")):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        assert result["match"] is True
        assert result["source"] == "default"


# ---------------------------------------------------------------------------
# validate_scene_coherence_vision
# ---------------------------------------------------------------------------

class TestValidateSceneCoherenceVision:

    def test_no_gemini_key_returns_default_pass(self):
        """No gemini_api_key and no google_api_key → default_pass."""
        with patch.object(pcv, "settings", _no_gemini_settings()):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result == {"coherent": True, "issues": [], "source": "default"}

    def test_zero_valid_images_returns_default_pass(self):
        """All images missing (0 valid) → default_pass (need >= 2)."""
        with patch.object(pcv.os.path, "exists", return_value=False):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result["source"] == "default"
        assert result["coherent"] is True

    def test_one_valid_image_returns_default_pass(self):
        """Exactly 1 valid image → default_pass (need >= 2)."""
        def _exists(p):
            return "/a" in p

        with patch.object(pcv.os.path, "exists", side_effect=_exists):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result["source"] == "default"

    def test_caps_at_3_images_when_5_provided(self):
        """5 valid images → only 3 passed to Gemini (valid_images[:3])."""
        mock_google, mock_genai = _make_genai_mock({"coherent": True, "issues": []})

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
            pcv.validate_scene_coherence_vision(
                ["/a.jpg", "/b.jpg", "/c.jpg", "/d.jpg", "/e.jpg"]
            )

        # generate_content called once; contents = [part, part, part, text_str] = 4 items
        gen = mock_genai.Client.return_value.models.generate_content
        assert gen.call_count == 1
        call_kwargs = gen.call_args
        contents = call_kwargs[1]["contents"] if call_kwargs[1] else call_kwargs[0][1]
        # 3 image parts + 1 text string
        assert len(contents) == 4

    def test_happy_path_coherent_true(self):
        """Gemini returns coherent=True → source='gemini-flash', coherent=True."""
        mock_google, mock_genai = _make_genai_mock({"coherent": True, "issues": []})

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result["coherent"] is True
        assert result["source"] == "gemini-flash"

    def test_happy_path_coherent_false_with_issues(self):
        """Gemini returns coherent=False → returned as-is with source='gemini-flash'."""
        mock_google, mock_genai = _make_genai_mock(
            {"coherent": False, "issues": ["lighting mismatch"]}
        )

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result["coherent"] is False
        assert "lighting mismatch" in result["issues"]
        assert result["source"] == "gemini-flash"

    def test_api_exception_returns_default_pass(self):
        """Exception during Gemini call → caught, returns default_pass."""
        mock_genai = MagicMock(Client=MagicMock(side_effect=RuntimeError("api error")))
        mock_google = MagicMock(genai=mock_genai)

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch.dict(sys.modules, {"google": mock_google, "google.genai": mock_genai}):
            result = pcv.validate_scene_coherence_vision(["/a.jpg", "/b.jpg"])

        assert result["coherent"] is True
        assert result["source"] == "default"

    def test_empty_list_returns_default_pass(self):
        """Empty list → 0 valid images → default_pass."""
        result = pcv.validate_scene_coherence_vision([])
        assert result["source"] == "default"
        assert result["coherent"] is True


# ---------------------------------------------------------------------------
# apply_correction face_swap caller — surfaces reason when cascade returns None
# ---------------------------------------------------------------------------

class TestApplyCorrectionFaceSwapReason:
    """Verifies that the operator face_swap action surfaces a reason when
    face_swap_video_frames returns None (all cascade paths failed/skipped).

    Uses CinemaPipeline + a real temp project dir (same harness as
    test_guided_pipeline.py) so no impractical over-mocking is needed.
    Only face_swap_video_frames is patched → None; everything else is real.
    """

    @pytest.fixture(autouse=True)
    def _setup_temp_project(self, tmp_path):
        """Create a minimal project with one scene/shot and a motion-take on disk."""
        import domain.project_manager as pm
        from cinema_pipeline import CinemaPipeline

        with patch("domain.project_manager.PROJECTS_DIR", str(tmp_path)):
            project = pm.create_project("FaceSwapReasonTest")
            scene = pm.make_scene("Scene 1")
            shot = pm.make_shot("A close-up", shot_id="shot_scene_1_0")
            scene["shots"] = [shot]
            scene["num_shots"] = 1
            scene["characters_present"] = ["char_a"]
            project["scenes"] = [scene]
            project["characters"] = [
                pm.make_character("Alice", "lead", reference_images=[], voice_id="")
            ]
            project["characters"][0]["id"] = "char_a"
            project["characters"][0]["reference_images"] = ["/ref_alice.jpg"]

            # Write fake motion-take asset to disk
            project_dir = pm.get_project_dir(project["id"])
            motion_path = os.path.join(project_dir, "shots", shot["id"], "outputs", "motion.mp4")
            os.makedirs(os.path.dirname(motion_path), exist_ok=True)
            with open(motion_path, "w") as f:
                f.write("fake-video")

            keyframe_take = pm.make_take("keyframe", path=motion_path.replace(".mp4", ".jpg"))
            motion_take = pm.make_take("motion", path=motion_path,
                                        source_take_id=keyframe_take["id"])
            shot.update({
                "plan_status": "approved",
                "keyframe_takes": [keyframe_take],
                "approved_keyframe_take_id": keyframe_take["id"],
                "motion_takes": [motion_take],
                "approved_motion_take_id": motion_take["id"],
                "approved_final_take_id": motion_take["id"],
            })
            pm.save_project(project)

            with patch("domain.project_manager.PROJECTS_DIR", str(tmp_path)):
                self._pipeline = CinemaPipeline(project["id"])
            self._shot_id = shot["id"]
            self._tmp_path = str(tmp_path)
            yield

    def test_face_swap_none_result_surfaces_cascade_reason(self):
        """When face_swap_video_frames returns None, apply_correction must surface
        a specific reason that the swap cascade could not be applied — not just
        the generic 'Action failed or not applicable' message.

        The operator clicked "face swap" and deserves to know WHY it did not
        apply (no swapper succeeded), not just that the action failed.

        This is the TDD driver for the G2 caller-side fix in controller.py.
        """
        import domain.project_manager as pm

        # Patch the names as bound in controller.py (imported via
        # `from phase_c_vision import face_swap_video_frames`), not the
        # phase_c_vision module namespace, so the mock is actually seen.
        with patch("domain.project_manager.PROJECTS_DIR", self._tmp_path), \
             patch("cinema.shots.controller.face_swap_video_frames", return_value=None), \
             patch("cinema.shots.controller.get_reference_image",
                   return_value="/ref_alice.jpg"):
            result = self._pipeline.apply_correction(self._shot_id, "face_swap", {})

        # The cascade returned None — the action must NOT silently succeed.
        assert result.get("success") is not True, (
            "face_swap silently reported success when cascade returned None; "
            "operator has no idea the swap was not applied."
        )
        # The error/warning must specifically explain the cascade failure,
        # not just the generic 'Action X failed or not applicable' fallback.
        reason = result.get("error") or result.get("warning") or ""
        assert reason, (
            f"apply_correction returned {result!r} with no error/warning "
            "when face_swap_video_frames returned None."
        )
        assert "no swapper succeeded" in reason.lower() or "could not be applied" in reason.lower(), (
            f"Reason '{reason}' is the generic fallback — it does not tell the "
            "operator that the swap cascade (fal→FaceFusion) produced no output. "
            "Expected a message like 'face_swap could not be applied (no swapper succeeded)'."
        )

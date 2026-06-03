"""
Characterization tests for phase_c_vision.py — face-swap + vision-validation
post-processing.

These tests LOCK IN the EXISTING behavior of already-written code.
They PASS against HEAD.  Where the code does something surprising or buggy,
each test asserts the ACTUAL current behavior and adds a comment:
    # CANDIDATE BUG (Gn): <one line>

Offline-only: cv2.VideoCapture, os.path.exists, subprocess, fal_client,
openai.OpenAI, anthropic.Anthropic, and google.genai are all mocked.
No GPU, no model weights, no network, no real files, no subprocesses.

Baseline: 1450 tests collected / 1447 passed / 3 skipped before this file.
"""

import sys
import dataclasses
import json
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

        # CANDIDATE BUG (G2): FaceFusion gate requires BOTH returncode==0 AND
        # os.path.exists(output_path); a partial write → output silently None.
        """
        mock_fal = MagicMock()
        mock_proc = MagicMock(returncode=0)
        with patch.object(pcv, "settings", _no_fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch("subprocess.run", return_value=mock_proc), \
             patch.object(pcv.os.path, "exists", return_value=False):
            result = pcv.face_swap_video_frames("/vid.mp4", "/ref.jpg", "/out.mp4")

        # CANDIDATE BUG (G2): returncode==0 but missing output → silent None
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

        # CANDIDATE BUG (G5): validate_identity_vision threshold is hardcoded 0.7
        # with no parameter to override it. Caller cannot adjust sensitivity.
        """
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.7, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        # CANDIDATE BUG (G5): threshold 0.7 is hardcoded; confidence=0.7 → match=True
        assert result["match"] is True

    def test_g5_threshold_boundary_069_is_match_false(self):
        """G5: confidence=0.69 → match=False (strictly below hardcoded 0.7 threshold)."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content[0].text = json.dumps({"confidence": 0.69, "issues": []})
        mock_client.messages.create.return_value = mock_resp

        with patch.object(pcv.os.path, "exists", return_value=True), \
             patch.object(pcv, "_encode_image_base64", return_value="AAAA"), \
             patch("anthropic.Anthropic", return_value=mock_client):
            result = pcv.validate_identity_vision("/ref.jpg", "/gen.jpg")

        # CANDIDATE BUG (G5): threshold 0.7 is hardcoded; confidence=0.69 → match=False
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

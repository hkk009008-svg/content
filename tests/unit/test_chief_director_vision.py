"""
tests/unit/test_chief_director_vision.py

TDD — vision deep-diagnose extension for ChiefDirector.

Covers _encode_image_for_llm helper and the wired images path in _call_llm
and evaluate_generation_quality.

Offline — LLM clients mocked; no API keys, no network.
"""
from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, call, patch

import pytest

# PIL is a required dep for max-tier provisioning — assume it's available.
from PIL import Image

from llm.chief_director import ChiefDirector, _encode_image_for_llm


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_cd(provider: str = "anthropic") -> ChiefDirector:
    """Build a ChiefDirector with stub client — no API keys needed."""
    cd = ChiefDirector(project={})
    cd.client = MagicMock()
    cd.provider = provider
    return cd


def _tiny_pil_image(mode: str = "RGB", size=(8, 8), color="red") -> Image.Image:
    return Image.new(mode, size, color)


def _save_pil(img: Image.Image, path, fmt: str = "JPEG"):
    """Save a PIL image to path in the given PIL format string."""
    img.save(str(path), format=fmt)


def _anthropic_ok_response(text: str = '{"decision":"RETRY"}') -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def _openai_ok_response(text: str = '{"decision":"RETRY"}') -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


# ─── 1. PNG-bytes-in-.jpg → JPEG b64 output (extensions-lie scenario) ────────

class TestEncoderExtensionsLie:
    """Production artifact extensions lie (.jpg file with PNG bytes).
    The encoder must re-encode via PIL regardless, producing a JPEG."""

    def test_png_bytes_in_jpg_filename_produces_jpeg_b64(self, tmp_path):
        img_path = tmp_path / "take.jpg"
        # Save a real PNG into a .jpg filename (the "extensions lie" scenario)
        _save_pil(_tiny_pil_image(), img_path, fmt="PNG")

        b64 = _encode_image_for_llm(str(img_path))
        assert b64 is not None, "encode must succeed for a valid image even if extension lies"
        raw = base64.b64decode(b64)
        # JPEG magic bytes
        assert raw[:2] == b"\xff\xd8", f"expected JPEG magic bytes, got {raw[:4]!r}"


# ─── 2. Downscale: 4000×2000 → long-edge 1568, aspect preserved ──────────────

class TestEncoderDownscale:
    def test_large_image_is_downscaled_with_aspect_preserved(self, tmp_path):
        img_path = tmp_path / "large.jpg"
        _save_pil(_tiny_pil_image(size=(4000, 2000)), img_path)

        b64 = _encode_image_for_llm(str(img_path))
        assert b64 is not None
        raw = base64.b64decode(b64)
        result_img = Image.open(io.BytesIO(raw))
        w, h = result_img.size
        # Long edge should be capped at 1568
        assert max(w, h) == 1568, f"long edge should be 1568, got {max(w, h)}"
        # Aspect ratio preserved: original is 2:1, so result should be 2:1
        ratio = w / h
        assert abs(ratio - 2.0) < 0.05, f"aspect ratio drifted: {ratio}"

    def test_small_image_not_upscaled(self, tmp_path):
        img_path = tmp_path / "small.jpg"
        _save_pil(_tiny_pil_image(size=(8, 8)), img_path)

        b64 = _encode_image_for_llm(str(img_path))
        assert b64 is not None
        raw = base64.b64decode(b64)
        result_img = Image.open(io.BytesIO(raw))
        w, h = result_img.size
        # Should not be upscaled
        assert max(w, h) <= 8, f"small image should not be upscaled, got {max(w, h)}"


# ─── 3. RGBA source → no raise, valid JPEG ────────────────────────────────────

class TestEncoderRGBA:
    def test_rgba_source_produces_valid_jpeg(self, tmp_path):
        img_path = tmp_path / "rgba.png"
        # JPEG cannot store RGBA — save as PNG so the file is a valid RGBA image
        _save_pil(_tiny_pil_image(mode="RGBA"), img_path, fmt="PNG")

        b64 = _encode_image_for_llm(str(img_path))
        assert b64 is not None
        raw = base64.b64decode(b64)
        assert raw[:2] == b"\xff\xd8"


# ─── 4. Missing file → None ───────────────────────────────────────────────────

class TestEncoderMissingFile:
    def test_missing_file_returns_none(self):
        result = _encode_image_for_llm("/fake/nonexistent/path.jpg")
        assert result is None


# ─── 5. anthropic + 2 pre-encoded b64 strings → image blocks then text block ──

class TestCallLLMAnthropicWithImages:
    def test_two_images_produce_image_blocks_then_text(self, tmp_path):
        cd = _make_cd(provider="anthropic")
        # _call_llm now accepts pre-encoded b64 strings (F1: encode-at-evaluate)
        take_b64 = _encode_image_for_llm(str(tmp_path / "take.jpg")) or ""
        ref_b64 = _encode_image_for_llm(str(tmp_path / "ref.jpg")) or ""
        # Use real tiny images so _encode_image_for_llm works; save them first
        _save_pil(_tiny_pil_image(color="red"), tmp_path / "take.jpg")
        _save_pil(_tiny_pil_image(color="blue"), tmp_path / "ref.jpg")
        take_b64 = _encode_image_for_llm(str(tmp_path / "take.jpg"))
        ref_b64 = _encode_image_for_llm(str(tmp_path / "ref.jpg"))
        assert take_b64 and ref_b64, "fixtures must encode successfully"

        cd.client.messages.create.return_value = _anthropic_ok_response()

        cd._call_llm("sys", "user text", image_b64s=[take_b64, ref_b64])

        assert cd.client.messages.create.called
        call_kwargs = cd.client.messages.create.call_args.kwargs
        content = call_kwargs["messages"][0]["content"]

        # Should have 2 image blocks + 1 text block
        assert len(content) == 3, f"expected 3 content blocks, got {len(content)}: {content}"
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "image"
        assert content[2]["type"] == "text"
        assert content[2]["text"] == "user text"

        # Image blocks carry the given b64 strings verbatim
        for blk, expected_b64 in zip(content[:2], [take_b64, ref_b64]):
            src = blk["source"]
            assert src["type"] == "base64"
            assert src["media_type"] == "image/jpeg"
            assert src["data"] == expected_b64, "data must equal the given b64 string"

        # system kwarg is preserved (list from build_anthropic_system_blocks)
        system = call_kwargs.get("system")
        assert system is not None, "system kwarg must be present"

    def test_text_only_path_content_is_plain_str(self, tmp_path):
        """image_b64s=None → content is plain str (byte-identical to today)."""
        cd = _make_cd(provider="anthropic")
        cd.client.messages.create.return_value = _anthropic_ok_response()

        cd._call_llm("sys", "user text", image_b64s=None)

        call_kwargs = cd.client.messages.create.call_args.kwargs
        content = call_kwargs["messages"][0]["content"]
        assert isinstance(content, str), f"expected plain str, got {type(content)}"
        assert content == "user text"


# ─── 6. Empty b64 strings dropped → text-only path ───────────────────────────

class TestEncoderCorruptFile:
    def test_empty_b64_drops_gracefully(self, tmp_path):
        """Passing an empty/None b64 (what _encode_image_for_llm returns for
        corrupt files) results in text-only call — no image blocks."""
        cd = _make_cd(provider="anthropic")
        cd.client.messages.create.return_value = _anthropic_ok_response()

        # Simulate a corrupt-file encode result: None is filtered by evaluate layer;
        # if caller passes "" by mistake it must also be dropped.
        cd._call_llm("sys", "user text", image_b64s=[""])

        # Should fall through to text-only: content is plain str
        call_kwargs = cd.client.messages.create.call_args.kwargs
        content = call_kwargs["messages"][0]["content"]
        assert isinstance(content, str), (
            f"empty b64 should drop → text-only; got {type(content)}"
        )


# ─── 7. openai + b64 strings → text part + image_url parts; response_format preserved

class TestCallLLMOpenAIWithImages:
    def test_openai_image_parts_and_response_format(self, tmp_path):
        cd = _make_cd(provider="openai")
        take_path = tmp_path / "take.jpg"
        _save_pil(_tiny_pil_image(), take_path)
        take_b64 = _encode_image_for_llm(str(take_path))
        assert take_b64, "fixture must encode successfully"

        cd.client.chat.completions.create.return_value = _openai_ok_response()

        cd._call_llm("sys", "user text", image_b64s=[take_b64])

        assert cd.client.chat.completions.create.called
        call_kwargs = cd.client.chat.completions.create.call_args.kwargs

        # response_format preserved
        assert call_kwargs.get("response_format") == {"type": "json_object"}

        # user message content is a list with text first, then image
        messages = call_kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        content = user_msg["content"]
        assert isinstance(content, list), f"expected list, got {type(content)}"
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "user text"
        assert content[1]["type"] == "image_url"
        url = content[1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), f"bad url prefix: {url[:40]}"
        # The data URL embeds the given b64 verbatim
        assert url == f"data:image/jpeg;base64,{take_b64}", "data URL must embed the given b64"

    def test_openai_text_only_path_is_plain_str_in_content(self, tmp_path):
        """image_b64s=None → user message content is plain str (byte-identical to today)."""
        cd = _make_cd(provider="openai")
        cd.client.chat.completions.create.return_value = _openai_ok_response()

        cd._call_llm("sys", "user text", image_b64s=None)

        call_kwargs = cd.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert isinstance(user_msg["content"], str), (
            f"text-only OpenAI path must be plain str; got {type(user_msg['content'])}"
        )


# ─── 8. / 9. image_b64s=None → exact same shapes as today (per provider) ──────
# (covered by test_text_only_path_content_is_plain_str and
#  test_openai_text_only_path_is_plain_str_in_content above)


# ─── 10. anthropic: Exception+images → text-only retry → text returned ────────

class TestCallLLMAnthropicTextOnlyRetry:
    def test_image_call_fails_then_text_retry_succeeds(self, tmp_path):
        cd = _make_cd(provider="anthropic")
        take_path = tmp_path / "take.jpg"
        _save_pil(_tiny_pil_image(), take_path)
        take_b64 = _encode_image_for_llm(str(take_path))
        assert take_b64, "fixture must encode"

        ok_resp = _anthropic_ok_response('{"decision":"RETRY"}')
        cd.client.messages.create.side_effect = [Exception("boom"), ok_resp]

        result = cd._call_llm("sys", "user text", image_b64s=[take_b64])

        # Called twice
        assert cd.client.messages.create.call_count == 2, (
            f"expected 2 calls (image fail + text retry), got {cd.client.messages.create.call_count}"
        )
        # Second call's content must be plain str (text-only)
        second_call_kwargs = cd.client.messages.create.call_args_list[1].kwargs
        second_content = second_call_kwargs["messages"][0]["content"]
        assert isinstance(second_content, str), (
            f"retry must be text-only (plain str); got {type(second_content)}"
        )
        # Text is returned
        assert result == '{"decision":"RETRY"}'


# ─── 11. evaluate_generation_quality with real images wires attach+system ─────

class TestEvaluateGenerationQualityWithImages:
    def _failing_id_result(self):
        from identity.types import (
            CharacterIdentityResult,
            FailureReason,
            IdentityValidationResult,
        )
        char_diag = CharacterIdentityResult(
            character_id="char_1",
            character_name="Alice",
            best_similarity=0.30,
            mean_similarity=0.25,
            min_similarity=0.20,
            frame_results=[],
            matched=False,
            primary_failure_reason=FailureReason.WRONG_PERSON,
            suggested_pulid_adjustment=0.05,
        )
        return IdentityValidationResult(
            passed=False,
            overall_score=0.30,
            character_results={"char_1": char_diag},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type="medium",
            threshold_used=0.70,
        )

    def _incoherent_result(self):
        r = MagicMock()
        r.overall_coherence_score = 0.3  # < 0.6
        r.color_drift = 0.8
        r.lighting_consistency = 0.5
        r.recommendations = []
        return r

    def test_both_images_attached_and_system_contains_visual_evidence(self, tmp_path):
        """Real take+ref: _call_llm receives both paths as images kwarg,
        system contains VISUAL EVIDENCE, user JSON contains attached_images."""
        cd = _make_cd()
        take_path = tmp_path / "take.jpg"
        ref_path = tmp_path / "ref.jpg"
        _save_pil(_tiny_pil_image(color="red"), take_path)
        _save_pil(_tiny_pil_image(color="blue"), ref_path)

        id_result = self._failing_id_result()
        coh_result = self._incoherent_result()

        mock_call_llm_return = json.dumps({
            "decision": "RETRY",
            "diagnosis": "face drifted",
            "prompt_mutation": "add X",
            "mutation_level": 1,
            "mutation_focus": "identity",
        })

        with patch.object(cd, "_call_llm", return_value=mock_call_llm_return) as mock_call:
            cd.evaluate_generation_quality(
                image_path=str(take_path),
                reference_path=str(ref_path),
                identity_result=id_result,
                coherence_result=coh_result,
            )

        assert mock_call.called
        _args = mock_call.call_args
        # image_b64s kwarg must contain 2 non-empty b64 strings (F1: encode-at-evaluate)
        image_b64s_kwarg = _args.kwargs.get("image_b64s")
        assert image_b64s_kwarg is not None, "image_b64s kwarg must be present"
        assert len(image_b64s_kwarg) == 2, f"expected 2 b64 strings, got {len(image_b64s_kwarg)}"
        assert all(b and len(b) > 10 for b in image_b64s_kwarg), (
            "both b64 strings must be non-empty (real encoded images)"
        )

        # system contains VISUAL EVIDENCE
        system_arg = _args.args[0]
        assert "VISUAL EVIDENCE" in system_arg, (
            f"system must contain 'VISUAL EVIDENCE' when images attached; got:\n{system_arg[-500:]}"
        )
        assert "visual_findings" in system_arg, (
            "system must mention visual_findings in output JSON block"
        )

        # user JSON contains attached_images
        user_json_str = _args.args[1]
        user_data = json.loads(user_json_str)
        assert "attached_images" in user_data, (
            f"user JSON must contain attached_images; got keys: {list(user_data.keys())}"
        )
        assert len(user_data["attached_images"]) == 2


# ─── 12. /fake/ paths → images None, system does NOT contain VISUAL EVIDENCE ──

class TestEvaluateGenerationQualityMissingFiles:
    def test_fake_paths_no_visual_evidence_in_system(self):
        cd = _make_cd()
        id_result = MagicMock()
        id_result.overall_score = 0.30
        id_result.threshold_used = 0.70
        id_result.character_results = {}
        coh_result = MagicMock()
        coh_result.overall_coherence_score = 0.3
        coh_result.color_drift = 0.8
        coh_result.lighting_consistency = 0.5
        coh_result.recommendations = []

        with patch.object(cd, "_call_llm", return_value='{"decision":"RETRY","diagnosis":"x","prompt_mutation":"y","mutation_level":1,"mutation_focus":"identity"}') as mock_call:
            cd.evaluate_generation_quality(
                image_path="/fake/img.jpg",
                reference_path="/fake/ref.jpg",
                identity_result=id_result,
                coherence_result=coh_result,
            )

        _args = mock_call.call_args
        system_arg = _args.args[0]
        assert "VISUAL EVIDENCE" not in system_arg, (
            "VISUAL EVIDENCE must not appear when no real images present"
        )

        user_json_str = _args.args[1]
        user_data = json.loads(user_json_str)
        assert "attached_images" not in user_data, (
            "attached_images must not appear when no real images present"
        )

        image_b64s_kwarg = _args.kwargs.get("image_b64s")
        assert not image_b64s_kwarg, (
            f"image_b64s kwarg must be None/absent/empty for fake paths; got {image_b64s_kwarg}"
        )


# ─── 13. Only take exists → exactly 1 path, label says generated take ─────────

class TestEvaluateGenerationQualityOneTake:
    def test_only_take_exists_one_image_correct_label(self, tmp_path):
        cd = _make_cd()
        take_path = tmp_path / "take.jpg"
        _save_pil(_tiny_pil_image(color="red"), take_path)

        id_result = MagicMock()
        id_result.overall_score = 0.30
        id_result.threshold_used = 0.70
        id_result.character_results = {}
        coh_result = MagicMock()
        coh_result.overall_coherence_score = 0.3
        coh_result.color_drift = 0.8
        coh_result.lighting_consistency = 0.5
        coh_result.recommendations = []

        with patch.object(cd, "_call_llm", return_value='{"decision":"RETRY","diagnosis":"x","prompt_mutation":"y","mutation_level":1,"mutation_focus":"identity"}') as mock_call:
            cd.evaluate_generation_quality(
                image_path=str(take_path),
                reference_path="/fake/ref.jpg",  # does not exist
                identity_result=id_result,
                coherence_result=coh_result,
            )

        _args = mock_call.call_args
        image_b64s_kwarg = _args.kwargs.get("image_b64s")
        assert image_b64s_kwarg is not None and len(image_b64s_kwarg) == 1, (
            f"exactly 1 b64 string should be attached; got {image_b64s_kwarg}"
        )
        assert image_b64s_kwarg[0] and len(image_b64s_kwarg[0]) > 10, (
            "the single b64 must be non-empty (real encoded image)"
        )

        user_data = json.loads(_args.args[1])
        labels = user_data.get("attached_images", [])
        assert len(labels) == 1
        assert "generated take" in labels[0].lower(), (
            f"label should mention 'generated take', got: {labels[0]!r}"
        )


# ─── 14. ACCEPT short-circuit: _call_llm never called ────────────────────────

class TestEvaluateGenerationQualityAcceptShortCircuit:
    def test_identity_passed_coherent_accept_no_llm_call(self, tmp_path):
        cd = _make_cd()
        take_path = tmp_path / "take.jpg"
        ref_path = tmp_path / "ref.jpg"
        _save_pil(_tiny_pil_image(color="red"), take_path)
        _save_pil(_tiny_pil_image(color="blue"), ref_path)

        id_result = MagicMock()
        id_result.overall_score = 0.90
        id_result.threshold_used = 0.70
        id_result.character_results = {}

        with patch.object(cd, "_call_llm") as mock_call:
            result = cd.evaluate_generation_quality(
                image_path=str(take_path),
                reference_path=str(ref_path),
                identity_result=id_result,
                # no coherence_result → coherent=True by default
            )

        assert result.get("decision") == "ACCEPT", f"expected ACCEPT, got {result}"
        assert mock_call.call_count == 0, (
            f"_call_llm must not be called on ACCEPT path; count={mock_call.call_count}"
        )


# ─── 15. F1 — corrupt take, real ref → exactly 1 b64, label is reference ──────

class TestEvaluateEncodeAtEvaluateCorruptTake:
    """F1 fix: encode-at-evaluate. Corrupt take must not pollute labels."""

    def _failing_id_result(self):
        from identity.types import (
            CharacterIdentityResult,
            FailureReason,
            IdentityValidationResult,
        )
        char_diag = CharacterIdentityResult(
            character_id="char_1",
            character_name="Alice",
            best_similarity=0.30,
            mean_similarity=0.25,
            min_similarity=0.20,
            frame_results=[],
            matched=False,
            primary_failure_reason=FailureReason.WRONG_PERSON,
            suggested_pulid_adjustment=0.05,
        )
        return IdentityValidationResult(
            passed=False,
            overall_score=0.30,
            character_results={"char_1": char_diag},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type="medium",
            threshold_used=0.70,
        )

    def test_corrupt_take_real_ref_one_b64_label_is_reference(self, tmp_path):
        """Corrupt take.jpg (garbage bytes) + real ref → _call_llm receives exactly
        1 b64, and the single label says 'canonical reference', NOT 'generated take'."""
        cd = _make_cd()
        take_path = tmp_path / "take.jpg"
        ref_path = tmp_path / "ref.jpg"
        take_path.write_bytes(b"this is garbage, not an image")
        _save_pil(_tiny_pil_image(color="blue"), ref_path)

        id_result = self._failing_id_result()
        coh_result = MagicMock()
        coh_result.overall_coherence_score = 0.3
        coh_result.color_drift = 0.8
        coh_result.lighting_consistency = 0.5
        coh_result.recommendations = []

        mock_llm_return = json.dumps({
            "decision": "RETRY",
            "diagnosis": "x",
            "prompt_mutation": "y",
            "mutation_level": 1,
            "mutation_focus": "identity",
        })

        with patch.object(cd, "_call_llm", return_value=mock_llm_return) as mock_call:
            cd.evaluate_generation_quality(
                image_path=str(take_path),
                reference_path=str(ref_path),
                identity_result=id_result,
                coherence_result=coh_result,
            )

        _args = mock_call.call_args
        # Exactly 1 b64 (the reference; take failed to encode)
        b64s = _args.kwargs.get("image_b64s")
        assert b64s is not None and len(b64s) == 1, (
            f"expected exactly 1 b64 (reference only); got {b64s}"
        )
        # User JSON: exactly 1 label, and it must name the reference, NOT the take
        user_data = json.loads(_args.args[1])
        labels = user_data.get("attached_images", [])
        assert len(labels) == 1, f"expected 1 label; got {labels}"
        assert "canonical reference" in labels[0].lower(), (
            f"label must name the canonical reference, not the take; got {labels[0]!r}"
        )
        assert "generated take" not in labels[0].lower(), (
            f"corrupt take must not produce a 'generated take' label; got {labels[0]!r}"
        )

    def test_both_files_corrupt_text_only_no_visual_evidence(self, tmp_path):
        """Both take and ref corrupt → image_b64s None/absent, no VISUAL EVIDENCE
        in system, no attached_images in user JSON (honest text-only call)."""
        cd = _make_cd()
        take_path = tmp_path / "take.jpg"
        ref_path = tmp_path / "ref.jpg"
        take_path.write_bytes(b"garbage")
        ref_path.write_bytes(b"garbage")

        id_result = self._failing_id_result()
        coh_result = MagicMock()
        coh_result.overall_coherence_score = 0.3
        coh_result.color_drift = 0.8
        coh_result.lighting_consistency = 0.5
        coh_result.recommendations = []

        mock_llm_return = json.dumps({
            "decision": "RETRY",
            "diagnosis": "x",
            "prompt_mutation": "y",
            "mutation_level": 1,
            "mutation_focus": "identity",
        })

        with patch.object(cd, "_call_llm", return_value=mock_llm_return) as mock_call:
            cd.evaluate_generation_quality(
                image_path=str(take_path),
                reference_path=str(ref_path),
                identity_result=id_result,
                coherence_result=coh_result,
            )

        _args = mock_call.call_args
        b64s = _args.kwargs.get("image_b64s")
        assert not b64s, f"image_b64s must be None/absent when both files corrupt; got {b64s}"

        system_arg = _args.args[0]
        assert "VISUAL EVIDENCE" not in system_arg, (
            "VISUAL EVIDENCE must not appear when both files corrupt"
        )
        user_data = json.loads(_args.args[1])
        assert "attached_images" not in user_data, (
            "attached_images must not appear when both files corrupt"
        )


# ─── 16. F2 — create succeeds but content empty → 1 call, returns "" ──────────

class TestCallLLMSingleChargeOnExtractionError:
    """F2 fix: wrap only the create call in the retry trigger. Extraction
    errors (e.g., empty content list) must not fire a second charged call."""

    def test_anthropic_create_ok_empty_content_one_call_returns_empty(self, tmp_path):
        """Anthropic: create succeeds, response.content is an empty list WITH images
        → exactly 1 create call; returns ""."""
        cd = _make_cd(provider="anthropic")
        take_path = tmp_path / "take.jpg"
        _save_pil(_tiny_pil_image(), take_path)
        take_b64 = _encode_image_for_llm(str(take_path))
        assert take_b64

        # create succeeds but content is empty — extraction would raise IndexError
        bad_resp = MagicMock()
        bad_resp.content = []   # response.content[0] raises IndexError
        cd.client.messages.create.return_value = bad_resp

        result = cd._call_llm("sys", "user text", image_b64s=[take_b64])

        # Exactly 1 create call — NO retry for extraction failure
        assert cd.client.messages.create.call_count == 1, (
            f"expected exactly 1 create call (no retry for extraction error); "
            f"got {cd.client.messages.create.call_count}"
        )
        assert result == "", f"empty content should return ''; got {result!r}"


# ─── 17. F4 — openai retry path; text-only no-retry ──────────────────────────

class TestCallLLMOpenAIRetryAndNoRetry:
    """F4 tests: (a) openai with images: first create raises, second text-only
    succeeds → 2 calls, returns text; (b) text-only failure → 1 call, returns ""."""

    def test_openai_image_call_fails_then_text_retry_succeeds(self, tmp_path):
        cd = _make_cd(provider="openai")
        take_path = tmp_path / "take.jpg"
        _save_pil(_tiny_pil_image(), take_path)
        take_b64 = _encode_image_for_llm(str(take_path))
        assert take_b64

        ok_resp = _openai_ok_response('{"decision":"RETRY"}')
        cd.client.chat.completions.create.side_effect = [Exception("api-fail"), ok_resp]

        result = cd._call_llm("sys", "user text", image_b64s=[take_b64])

        assert cd.client.chat.completions.create.call_count == 2, (
            f"expected 2 calls (image fail + text retry); "
            f"got {cd.client.chat.completions.create.call_count}"
        )
        # Second call must be text-only (plain str content)
        second_kwargs = cd.client.chat.completions.create.call_args_list[1].kwargs
        user_msg = next(m for m in second_kwargs["messages"] if m["role"] == "user")
        assert isinstance(user_msg["content"], str), (
            f"retry must be text-only; got {type(user_msg['content'])}"
        )
        assert result == '{"decision":"RETRY"}'

    def test_text_only_failure_no_retry(self):
        """No images: create raises → exactly 1 call, returns ""."""
        cd = _make_cd(provider="anthropic")
        cd.client.messages.create.side_effect = Exception("api-fail")

        result = cd._call_llm("sys", "user text", image_b64s=None)

        assert cd.client.messages.create.call_count == 1, (
            f"text-only failure must not retry; got {cd.client.messages.create.call_count}"
        )
        assert result == "", f"text-only failure should return ''; got {result!r}"

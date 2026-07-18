"""Unit tests for gemini_image_native.GeminiImageAPI (WS3 step 1, Nano Banana).

Mirrors tests/unit/test_gemini_omni_native.py's conventions (bypass __init__
via __new__, capture kwargs via side_effect / call_args, patch os.path.exists
/ getsize / open where needed).

All tests are offline — no real API calls, no network, no spend (COST CONTROL).
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Sibling unit tests stub heavy native-API modules into sys.modules at import
# time; drop any stub so this module always exercises the REAL implementation
# (mirrors test_veo_native_config.py / test_gemini_omni_native.py's guard).
sys.modules.pop("gemini_image_native", None)

from gemini_image_native import (  # noqa: E402
    GeminiImageAPI,
    GEMINI_MULTIREF_MAX_REFS,
    _load_image_bytes,
)


# ---------------------------------------------------------------------------
# __init__ — key resolution + graceful-raise contract
# ---------------------------------------------------------------------------


def test_init_raises_when_no_key_available():
    fake_settings = MagicMock(google_api_key="", gemini_api_key="")
    with patch("gemini_image_native.settings", fake_settings):
        with pytest.raises(EnvironmentError, match="GOOGLE_API_KEY.*GEMINI_API_KEY"):
            GeminiImageAPI()


def test_init_prefers_google_api_key():
    fake_settings = MagicMock(google_api_key="goog-key", gemini_api_key="gem-key")
    with patch("gemini_image_native.settings", fake_settings), \
         patch("gemini_image_native.genai.Client") as mock_client_cls:
        api = GeminiImageAPI()
        mock_client_cls.assert_called_once_with(api_key="goog-key")
        assert api._model == "gemini-2.5-flash-image"


def test_init_falls_back_to_gemini_api_key():
    fake_settings = MagicMock(google_api_key="", gemini_api_key="gem-key")
    with patch("gemini_image_native.settings", fake_settings), \
         patch("gemini_image_native.genai.Client") as mock_client_cls:
        GeminiImageAPI()
        mock_client_cls.assert_called_once_with(api_key="gem-key")


# ---------------------------------------------------------------------------
# _load_image_bytes — pure helper
# ---------------------------------------------------------------------------


def test_load_image_bytes_roundtrips(tmp_path):
    p = tmp_path / "ref.jpg"
    p.write_bytes(b"fake-jpeg-bytes")
    assert _load_image_bytes(str(p)) == b"fake-jpeg-bytes"


# ---------------------------------------------------------------------------
# generate_image — reference-image budget truncation
# ---------------------------------------------------------------------------


def _make_refs(tmp_path, n, prefix="ref"):
    paths = []
    for i in range(n):
        p = tmp_path / f"{prefix}_{i}.jpg"
        p.write_bytes(b"x")
        paths.append(str(p))
    return paths


def _mock_response_with_image(data: bytes = b"IMAGE_BYTES"):
    response = MagicMock()
    part = MagicMock()
    part.inline_data.data = data
    response.candidates = [MagicMock(content=MagicMock(parts=[part]))]
    return response


def test_generate_image_truncates_refs_at_budget_with_warning(tmp_path, capsys):
    api = GeminiImageAPI.__new__(GeminiImageAPI)  # bypass __init__ (no real client)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    char_img = tmp_path / "char.jpg"
    char_img.write_bytes(b"char")
    # 1 primary + 10 multi-angle refs = 11 total, well over the budget.
    multi_refs = _make_refs(tmp_path, 10, prefix="angle")
    output_path = str(tmp_path / "out.jpg")

    result = api.generate_image(
        prompt="a cinematic shot",
        output_path=output_path,
        character_image=str(char_img),
        multi_angle_refs=multi_refs,
    )

    assert result == output_path
    out = capsys.readouterr().out
    assert "WARNING" in out and "truncating" in out

    kwargs = api.client.models.generate_content.call_args.kwargs
    # contents = [prompt_text, *Part-per-ref] — ref count must equal the budget.
    assert len(kwargs["contents"]) == 1 + GEMINI_MULTIREF_MAX_REFS


def test_generate_image_no_truncation_under_budget(tmp_path, capsys):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    char_img = tmp_path / "char.jpg"
    char_img.write_bytes(b"char")
    output_path = str(tmp_path / "out.jpg")

    result = api.generate_image(
        prompt="a cinematic shot",
        output_path=output_path,
        character_image=str(char_img),
    )

    assert result == output_path
    out = capsys.readouterr().out
    assert "WARNING" not in out

    kwargs = api.client.models.generate_content.call_args.kwargs
    assert len(kwargs["contents"]) == 2  # prompt + the one primary ref


def test_generate_image_drops_missing_ref_paths(tmp_path):
    """A stale/missing ref path must not raise mid-encode — it's silently
    dropped before the GEMINI_MULTIREF_MAX_REFS budget check."""
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    char_img = tmp_path / "char.jpg"
    char_img.write_bytes(b"char")
    output_path = str(tmp_path / "out.jpg")

    result = api.generate_image(
        prompt="a cinematic shot",
        output_path=output_path,
        character_image=str(char_img),
        multi_angle_refs=[str(tmp_path / "does_not_exist.jpg")],
    )

    assert result == output_path
    kwargs = api.client.models.generate_content.call_args.kwargs
    assert len(kwargs["contents"]) == 2  # prompt + the one EXISTING ref


# ---------------------------------------------------------------------------
# generate_image — aspect_ratio mapping via fal_aspect_ratio reuse
# ---------------------------------------------------------------------------


def test_generate_image_maps_aspect_ratio_via_fal_aspect_ratio(tmp_path):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    output_path = str(tmp_path / "out.jpg")
    api.generate_image(prompt="p", output_path=output_path, aspect_ratio="9:16")

    kwargs = api.client.models.generate_content.call_args.kwargs
    assert kwargs["config"].image_config.aspect_ratio == "9:16"


def test_generate_image_defaults_aspect_ratio_to_16_9(tmp_path):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    output_path = str(tmp_path / "out.jpg")
    api.generate_image(prompt="p", output_path=output_path)

    kwargs = api.client.models.generate_content.call_args.kwargs
    assert kwargs["config"].image_config.aspect_ratio == "16:9"


def test_generate_image_unknown_aspect_ratio_defaults_to_landscape(tmp_path):
    # fal_aspect_ratio delegates to is_portrait -> resolve_output_dimensions,
    # which never raises and defaults UNKNOWN strings to the 16:9 landscape
    # dims (cinema/aspect.py) — reuse, not a bespoke ternary.
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    output_path = str(tmp_path / "out.jpg")
    api.generate_image(prompt="p", output_path=output_path, aspect_ratio="portrait")

    kwargs = api.client.models.generate_content.call_args.kwargs
    assert kwargs["config"].image_config.aspect_ratio == "16:9"


# ---------------------------------------------------------------------------
# generate_image — success path writes bytes + returns output_path
# ---------------------------------------------------------------------------


def test_generate_image_writes_bytes_and_returns_output_path(tmp_path):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image(b"REAL_IMAGE_DATA")

    output_path = str(tmp_path / "out.jpg")
    result = api.generate_image(prompt="p", output_path=output_path)

    assert result == output_path
    with open(output_path, "rb") as f:
        assert f.read() == b"REAL_IMAGE_DATA"


def test_generate_image_negative_prompt_appended_to_contents(tmp_path):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    output_path = str(tmp_path / "out.jpg")
    api.generate_image(
        prompt="a scene", output_path=output_path, negative_prompt="blurry, low quality",
    )

    kwargs = api.client.models.generate_content.call_args.kwargs
    prompt_text = kwargs["contents"][0]
    assert "a scene" in prompt_text
    assert "blurry, low quality" in prompt_text


# ---------------------------------------------------------------------------
# generate_image — no inline image data in response -> graceful None
# ---------------------------------------------------------------------------


def test_generate_image_returns_none_when_no_image_in_response(tmp_path):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()

    empty_response = MagicMock()
    part = MagicMock()
    part.inline_data = None
    empty_response.candidates = [MagicMock(content=MagicMock(parts=[part]))]
    api.client.models.generate_content.return_value = empty_response

    output_path = str(tmp_path / "out.jpg")
    result = api.generate_image(prompt="p", output_path=output_path)

    assert result is None


# ---------------------------------------------------------------------------
# generate_image — blanket exception -> graceful None (cascade-fallthrough)
# ---------------------------------------------------------------------------


def test_generate_image_returns_none_on_exception(tmp_path, capsys):
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.side_effect = RuntimeError("429 quota exceeded")

    output_path = str(tmp_path / "out.jpg")
    result = api.generate_image(prompt="p", output_path=output_path)

    assert result is None
    out = capsys.readouterr().out
    assert "[GEMINI-IMAGE] Generation failed" in out
    assert "429 quota exceeded" in out


def test_generate_image_missing_character_image_does_not_raise(tmp_path):
    """No character_image and no refs at all — still a valid (text-only) call."""
    api = GeminiImageAPI.__new__(GeminiImageAPI)
    api._model = "gemini-2.5-flash-image"
    api.client = MagicMock()
    api.client.models.generate_content.return_value = _mock_response_with_image()

    output_path = str(tmp_path / "out.jpg")
    result = api.generate_image(prompt="p", output_path=output_path, character_image=None)

    assert result == output_path
    kwargs = api.client.models.generate_content.call_args.kwargs
    assert len(kwargs["contents"]) == 1  # prompt text only, no refs


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

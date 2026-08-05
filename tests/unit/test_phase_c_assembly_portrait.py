"""FAL and Pollinations image-orientation regressions."""

from __future__ import annotations

import dataclasses
import sys
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca


def _arguments(call):
    return call.kwargs["arguments"] if "arguments" in call.kwargs else call.args[1]


@pytest.fixture
def stub_fal(monkeypatch):
    fake = MagicMock()
    fake.upload_file.return_value = "https://fake/upload"
    fake.subscribe.return_value = {
        "images": [{"url": "https://fake/image.jpg"}]
    }
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    monkeypatch.setattr(
        pca,
        "settings",
        dataclasses.replace(pca.settings, fal_key="test-key"),
    )

    def _download(_url, filename):
        with open(filename, "wb") as handle:
            handle.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _download)
    return fake


@pytest.mark.parametrize(
    ("aspect_ratio", "expected"),
    [("9:16", "9:16"), (None, "16:9")],
)
def test_kontext_orientation(stub_fal, tmp_path, aspect_ratio, expected):
    reference = tmp_path / "face.jpg"
    reference.write_bytes(b"face")
    pca._fal_flux_fallback(
        "a prompt",
        str(tmp_path / "out.jpg"),
        seed=1,
        character_image=str(reference),
        aspect_ratio=aspect_ratio,
    )
    call = stub_fal.subscribe.call_args_list[0]
    arguments = _arguments(call)
    assert arguments["aspect_ratio"] == expected


@pytest.mark.parametrize(
    ("aspect_ratio", "expected"),
    [("9:16", "9:16"), ("16:9", "16:9")],
)
def test_flux_pro_orientation(stub_fal, tmp_path, aspect_ratio, expected):
    pca._fal_flux_fallback(
        "a prompt",
        str(tmp_path / "out.jpg"),
        seed=1,
        character_image=None,
        aspect_ratio=aspect_ratio,
    )
    call = stub_fal.subscribe.call_args_list[0]
    arguments = _arguments(call)
    assert arguments["aspect_ratio"] == expected


@pytest.mark.parametrize(
    ("aspect_ratio", "expected"),
    [("9:16", "portrait_16_9"), (None, "landscape_16_9")],
)
def test_flux_schnell_orientation(
    stub_fal,
    tmp_path,
    aspect_ratio,
    expected,
):
    stub_fal.subscribe.side_effect = [
        RuntimeError("pro unavailable"),
        {"images": [{"url": "https://fake/schnell.jpg"}]},
    ]
    pca._fal_flux_fallback(
        "a prompt",
        str(tmp_path / "out.jpg"),
        seed=1,
        character_image=None,
        aspect_ratio=aspect_ratio,
    )
    call = stub_fal.subscribe.call_args_list[1]
    arguments = _arguments(call)
    assert arguments["image_size"] == expected


@pytest.mark.parametrize(
    ("aspect_ratio", "width", "height"),
    [("9:16", 768, 1344), (None, 1344, 768)],
)
def test_pollinations_orientation(
    stub_fal,
    tmp_path,
    monkeypatch,
    aspect_ratio,
    width,
    height,
):
    stub_fal.subscribe.side_effect = RuntimeError("fal unavailable")
    urls = []

    def _download(url, filename):
        urls.append(url)
        with open(filename, "wb") as handle:
            handle.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _download)
    pca._fal_flux_fallback(
        "a prompt",
        str(tmp_path / "out.jpg"),
        seed=1,
        character_image=None,
        aspect_ratio=aspect_ratio,
    )
    assert urls
    assert f"width={width}" in urls[0]
    assert f"height={height}" in urls[0]

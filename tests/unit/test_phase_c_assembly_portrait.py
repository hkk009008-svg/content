"""Portrait Phase 2 — production ComfyUI node-102 latent transpose + FAL/Pollinations orientation.

Verifies that `generate_ai_broll` reads `aspect_ratio` from
`ctx.global_settings` and transposes node 102's width/height via
`portrait_swap` when `aspect_ratio="9:16"`.

Also verifies that `_fal_flux_fallback` emits 9:16 for Kontext, Pro,
schnell, and Pollinations when called with `aspect_ratio="9:16"`, and
stays landscape when called with None/"16:9".

Offline: ComfyUI I/O is fully stubbed; no pod, no GPU, no network.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca
from cinema.context import PipelineContext


def _minimal_pulid_workflow() -> dict:
    """Minimal pulid.json-shaped dict — just the nodes generate_ai_broll touches."""
    return {
        "122": {"inputs": {"text": ""}, "class_type": "CLIPTextEncode"},
        "102": {"inputs": {"width": 0, "height": 0, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "25":  {"inputs": {"noise_seed": 0}, "class_type": "RandomNoise"},
        "13":  {"inputs": {"latent_image": ["102", 0]}, "class_type": "SamplerCustomAdvanced"},
        "17":  {"inputs": {"denoise": 1.0}, "class_type": "BasicScheduler"},
        "22":  {"inputs": {"conditioning": None, "model": None}, "class_type": "BasicGuider"},
    }


def _stub_comfyui_path(monkeypatch, tmp_path) -> dict:
    """Monkeypatch everything needed to reach queue_prompt in the production path.

    Returns a dict that will be populated with the final workflow at queue_prompt time.
    """
    # 1. Write a minimal pulid.json so os.path.exists("pulid.json") passes
    pulid_path = tmp_path / "pulid.json"
    pulid_path.write_text(json.dumps(_minimal_pulid_workflow()))
    # Change CWD-relative open to use the tmp_path copy
    original_open = pca.open if hasattr(pca, 'open') else open

    # Monkeypatch os.path.exists so "pulid.json" resolves positively
    _real_exists = pca.os.path.exists
    def _fake_exists(path):
        if path == "pulid.json":
            return True
        return _real_exists(path)
    monkeypatch.setattr(pca.os.path, "exists", _fake_exists)

    # 2. Monkeypatch the file open so json.load gets our workflow
    import builtins
    _real_open = builtins.open
    def _fake_open(path, *args, **kwargs):
        if path == "pulid.json":
            return _real_open(str(pulid_path), *args, **kwargs)
        return _real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", _fake_open)

    # 3. Set server_url so the ComfyUI path is taken
    monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, comfyui_server_url="http://fake-pod:8188"))

    # 4. Stub workflow_selector so classify_shot_type doesn't blow up
    fake_ws = MagicMock()
    fake_ws.classify_shot_type.return_value = "medium"
    fake_ws.get_workflow_params.return_value = {
        "pulid_weight": 0.8, "guidance": 3.5, "steps": 20,
        "controlnet_depth_strength": 0.35, "ip_adapter_weight": 0.30,
    }
    fake_ws.apply_workflow_params.side_effect = lambda wf, params: wf
    monkeypatch.setitem(sys.modules, "workflow_selector", fake_ws)

    # 5. Capture the workflow at queue_prompt; stub out everything else on RunPodComfyUI
    captured = {}

    def _fake_queue(self, wf):
        captured.update(wf)
        return "fake-prompt-id"

    monkeypatch.setattr(pca.RunPodComfyUI, "queue_prompt", _fake_queue, raising=True)
    monkeypatch.setattr(pca.RunPodComfyUI, "upload_image", lambda self, p: "remote_face.jpg", raising=True)
    # get_history raises immediately → falls into except → _fal_flux_fallback (which we
    # don't care about; we already captured the workflow at queue_prompt). This avoids the
    # 300×2s polling loop while ensuring the test exits fast.
    monkeypatch.setattr(pca.RunPodComfyUI, "get_history",
                        lambda self, pid: (_ for _ in ()).throw(RuntimeError("stub-exit")),
                        raising=True)

    # Stub _fal_flux_fallback so the except-path doesn't need network / FAL key
    import dataclasses as _dc
    monkeypatch.setattr(pca, "_fal_flux_fallback",
                        lambda *a, **kw: pca.ImageGenResult("stub.jpg", "POLLINATIONS"))

    return captured


class TestProductionNode102Portrait:
    """Node-102 width/height transpose for portrait (9:16) aspect ratio."""

    def test_portrait_transposes_node102(self, tmp_path, monkeypatch):
        """aspect_ratio=9:16 → node 102 becomes 768×1344 (transposed from 1344×768)."""
        captured = _stub_comfyui_path(monkeypatch, tmp_path)

        ctx = PipelineContext(global_settings={"aspect_ratio": "9:16"})

        pca.generate_ai_broll(
            "a person walking",
            str(tmp_path / "out.jpg"),
            ctx=ctx,
            quality_tier="production",
        )

        assert "102" in captured, "workflow was not captured — queue_prompt not reached"
        node102 = captured["102"]["inputs"]
        assert node102["width"] == 768, f"expected width=768 for portrait, got {node102['width']}"
        assert node102["height"] == 1344, f"expected height=1344 for portrait, got {node102['height']}"

    def test_landscape_node102_unchanged(self, tmp_path, monkeypatch):
        """aspect_ratio=16:9 (default) → node 102 stays at 1344×768."""
        captured = _stub_comfyui_path(monkeypatch, tmp_path)

        ctx = PipelineContext(global_settings={"aspect_ratio": "16:9"})

        pca.generate_ai_broll(
            "a city skyline",
            str(tmp_path / "out.jpg"),
            ctx=ctx,
            quality_tier="production",
        )

        assert "102" in captured, "workflow was not captured — queue_prompt not reached"
        node102 = captured["102"]["inputs"]
        assert node102["width"] == 1344, f"expected width=1344 for landscape, got {node102['width']}"
        assert node102["height"] == 768, f"expected height=768 for landscape, got {node102['height']}"

    def test_no_ctx_node102_defaults_landscape(self, tmp_path, monkeypatch):
        """ctx=None → node 102 stays at 1344×768 (safe default)."""
        captured = _stub_comfyui_path(monkeypatch, tmp_path)

        pca.generate_ai_broll(
            "a landscape",
            str(tmp_path / "out.jpg"),
            ctx=None,
            quality_tier="production",
        )

        assert "102" in captured, "workflow was not captured — queue_prompt not reached"
        node102 = captured["102"]["inputs"]
        assert node102["width"] == 1344, f"expected width=1344 for no-ctx default, got {node102['width']}"
        assert node102["height"] == 768, f"expected height=768 for no-ctx default, got {node102['height']}"


# ---------------------------------------------------------------------------
# Phase 2 — Task 3: FAL Kontext / Pro / schnell / Pollinations orientation
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_fal_portrait(monkeypatch):
    """Stub fal_client + urlretrieve so _fal_flux_fallback runs offline.

    Returns the fake fal_client MagicMock so individual tests can inspect
    calls or inject side_effects.
    """
    fake = MagicMock()
    fake.upload_file.return_value = "https://fake/upload"
    fake.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    monkeypatch.setattr(
        pca, "settings", dataclasses.replace(pca.settings, fal_key="test-key")
    )

    def _fake_retrieve(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)
    return fake


class TestFalFallbackPortraitOrientation:
    """_fal_flux_fallback emits 9:16 for all model paths when aspect_ratio='9:16'."""

    # ------------------------------------------------------------------
    # Portrait tests
    # ------------------------------------------------------------------

    def test_kontext_portrait_aspect_ratio(self, stub_fal_portrait, tmp_path):
        """Kontext path: aspect_ratio='9:16' → FAL arguments['aspect_ratio']=='9:16'."""
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=str(char),
                               aspect_ratio="9:16")

        # The FIRST subscribe call is Kontext.
        call_args = stub_fal_portrait.subscribe.call_args_list[0]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["aspect_ratio"] == "9:16", (
            f"Kontext portrait: expected aspect_ratio='9:16', got {arguments.get('aspect_ratio')!r}"
        )

    def test_pro_portrait_aspect_ratio(self, stub_fal_portrait, tmp_path):
        """Pro path (no character_image): aspect_ratio='9:16' → FAL arguments['aspect_ratio']=='9:16'."""
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio="9:16")

        call_args = stub_fal_portrait.subscribe.call_args_list[0]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["aspect_ratio"] == "9:16", (
            f"Pro portrait: expected aspect_ratio='9:16', got {arguments.get('aspect_ratio')!r}"
        )

    def test_schnell_portrait_image_size(self, stub_fal_portrait, tmp_path):
        """schnell path: aspect_ratio='9:16' → FAL arguments['image_size']=='portrait_16_9'."""
        # Pro fails, schnell succeeds.
        stub_fal_portrait.subscribe.side_effect = [
            RuntimeError("pro down"),
            {"images": [{"url": "https://fake/schnell.jpg"}]},
        ]
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio="9:16")

        # 2nd subscribe call is schnell.
        call_args = stub_fal_portrait.subscribe.call_args_list[1]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["image_size"] == "portrait_16_9", (
            f"schnell portrait: expected image_size='portrait_16_9', got {arguments.get('image_size')!r}"
        )

    def test_pollinations_portrait_url(self, stub_fal_portrait, tmp_path, monkeypatch):
        """Pollinations URL: aspect_ratio='9:16' → width=768&height=1344."""
        stub_fal_portrait.subscribe.side_effect = RuntimeError("fal down")

        captured_urls = []

        class _Resp:
            def read(self_inner):
                return b"x" * 6000

        def _fake_urlopen(url):
            captured_urls.append(url)
            return _Resp()

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio="9:16")

        assert captured_urls, "urlopen was not called — Pollinations path not reached"
        url = captured_urls[0]
        assert "width=768" in url, f"Pollinations portrait URL should contain width=768, got: {url}"
        assert "height=1344" in url, f"Pollinations portrait URL should contain height=1344, got: {url}"

    # ------------------------------------------------------------------
    # Landscape regression (None / "16:9" must produce landscape values)
    # ------------------------------------------------------------------

    def test_kontext_landscape_regression(self, stub_fal_portrait, tmp_path):
        """aspect_ratio=None → Kontext stays at '16:9'."""
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=str(char),
                               aspect_ratio=None)

        call_args = stub_fal_portrait.subscribe.call_args_list[0]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["aspect_ratio"] == "16:9", (
            f"Kontext landscape regression: expected '16:9', got {arguments.get('aspect_ratio')!r}"
        )

    def test_pro_landscape_regression(self, stub_fal_portrait, tmp_path):
        """aspect_ratio='16:9' → Pro stays at '16:9'."""
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio="16:9")

        call_args = stub_fal_portrait.subscribe.call_args_list[0]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["aspect_ratio"] == "16:9", (
            f"Pro landscape regression: expected '16:9', got {arguments.get('aspect_ratio')!r}"
        )

    def test_schnell_landscape_regression(self, stub_fal_portrait, tmp_path):
        """aspect_ratio=None → schnell stays at 'landscape_16_9'."""
        stub_fal_portrait.subscribe.side_effect = [
            RuntimeError("pro down"),
            {"images": [{"url": "https://fake/schnell.jpg"}]},
        ]
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio=None)

        call_args = stub_fal_portrait.subscribe.call_args_list[1]
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert arguments["image_size"] == "landscape_16_9", (
            f"schnell landscape regression: expected 'landscape_16_9', got {arguments.get('image_size')!r}"
        )

    def test_pollinations_landscape_regression(self, stub_fal_portrait, tmp_path, monkeypatch):
        """aspect_ratio=None → Pollinations URL stays width=1344&height=768."""
        stub_fal_portrait.subscribe.side_effect = RuntimeError("fal down")

        captured_urls = []

        class _Resp:
            def read(self_inner):
                return b"x" * 6000

        def _fake_urlopen(url):
            captured_urls.append(url)
            return _Resp()

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio=None)

        assert captured_urls, "urlopen was not called"
        url = captured_urls[0]
        assert "width=1344" in url, f"Pollinations landscape URL should have width=1344, got: {url}"
        assert "height=768" in url, f"Pollinations landscape URL should have height=768, got: {url}"

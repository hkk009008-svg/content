"""Portrait Phase 2 — production ComfyUI graph + FAL/Pollinations orientation.

Verifies that `generate_ai_broll` reads `aspect_ratio` from
`ctx.global_settings` and transposes the real `pulid.json` graph's latent
node 102 and delivery node 502 via `portrait_swap` when
`aspect_ratio="9:16"`.

The init-image case also pins the supported LoadImage -> VAEEncode path and
ensures the removed ControlNet/IP-Adapter nodes are not reintroduced.

Also verifies that `_fal_flux_fallback` emits 9:16 for Kontext, Pro,
schnell, and Pollinations when called with `aspect_ratio="9:16"`, and
stays landscape when called with None/"16:9".

Offline: ComfyUI I/O is fully stubbed; no pod, no GPU, no network.
"""

from __future__ import annotations

import dataclasses
import sys
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca
from cinema.context import PipelineContext


_REAL_PULID_PATH = Path(pca.__file__).with_name("pulid.json")
_UNSUPPORTED_DYNAMIC_NODE_IDS = {"400", "401", "402", "410", "411"}


def _assert_no_unsupported_dynamic_nodes(workflow: dict) -> None:
    present = _UNSUPPORTED_DYNAMIC_NODE_IDS.intersection(workflow)
    assert not present, f"unsupported production nodes were injected: {sorted(present)}"


def _stub_comfyui_path(monkeypatch, _tmp_path) -> dict:
    """Monkeypatch everything needed to reach queue_prompt in the production path.

    The workflow loaded is the repository's real pulid.json, not a minimal
    synthetic graph. Returns a dict populated at queue_prompt time.
    """
    assert _REAL_PULID_PATH.is_file(), "real pulid.json fixture is missing"

    # 1. Resolve the production code's CWD-relative pulid.json to the real graph.
    _real_exists = pca.os.path.exists
    def _fake_exists(path):
        if path == "pulid.json":
            return True
        return _real_exists(path)
    monkeypatch.setattr(pca.os.path, "exists", _fake_exists)

    # 2. Monkeypatch file open so json.load gets the repository graph even when
    # an individual test runner changes its working directory.
    import builtins
    _real_open = builtins.open
    def _fake_open(path, *args, **kwargs):
        if path == "pulid.json":
            return _real_open(_REAL_PULID_PATH, *args, **kwargs)
        return _real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", _fake_open)

    # 3. Set server_url so the ComfyUI path is taken
    monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, comfyui_server_url="http://fake-pod:8188"))

    # 4. Stub workflow_selector so classify_shot_type doesn't blow up
    fake_ws = MagicMock()
    fake_ws.classify_shot_type.return_value = "medium"
    fake_ws.get_workflow_params.return_value = {
        "pulid_weight": 0.8, "guidance": 3.5, "steps": 20,
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
    # Monitoring failure is allowed to enter the fallback cascade only after
    # the known prompt is confirmed cancelled. Keep the shared offline helper
    # aligned with that production contract (and prevent any real fake-pod I/O).
    monkeypatch.setattr(
        pca.RunPodComfyUI,
        "cancel_prompt",
        lambda self, pid: True,
        raising=True,
    )

    # Stub _fal_flux_fallback so the except-path doesn't need network / FAL key
    monkeypatch.setattr(pca, "_fal_flux_fallback",
                        lambda *a, **kw: pca.ImageGenResult("stub.jpg", "POLLINATIONS"))

    return captured


class TestProductionComfyWorkflowAspect:
    """Real graph orientation and contained img2img construction."""

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
        node502 = captured["502"]["inputs"]
        assert node502["width"] == 1536, f"expected width=1536 for portrait, got {node502['width']}"
        assert node502["height"] == 2688, f"expected height=2688 for portrait, got {node502['height']}"
        _assert_no_unsupported_dynamic_nodes(captured)

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
        node502 = captured["502"]["inputs"]
        assert node502["width"] == 2688, f"expected width=2688 for landscape, got {node502['width']}"
        assert node502["height"] == 1536, f"expected height=1536 for landscape, got {node502['height']}"
        _assert_no_unsupported_dynamic_nodes(captured)

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
        node502 = captured["502"]["inputs"]
        assert node502["width"] == 2688, f"expected width=2688 for no-ctx default, got {node502['width']}"
        assert node502["height"] == 1536, f"expected height=1536 for no-ctx default, got {node502['height']}"
        _assert_no_unsupported_dynamic_nodes(captured)

    @pytest.mark.parametrize(
        ("aspect_ratio", "latent_dims", "delivery_dims"),
        [
            ("16:9", (1344, 768), (2688, 1536)),
            ("9:16", (768, 1344), (1536, 2688)),
        ],
    )
    def test_init_image_keeps_only_supported_img2img_nodes(
        self, aspect_ratio, latent_dims, delivery_dims, tmp_path, monkeypatch
    ):
        captured = _stub_comfyui_path(monkeypatch, tmp_path)
        init_image = tmp_path / "approved_previous_shot.png"
        init_image.write_bytes(b"image")

        pca.generate_ai_broll(
            "a person walking",
            str(tmp_path / "out.jpg"),
            init_image=str(init_image),
            denoise_strength=0.42,
            ctx=PipelineContext(global_settings={"aspect_ratio": aspect_ratio}),
            quality_tier="production",
        )

        latent_inputs = captured["102"]["inputs"]
        assert (latent_inputs["width"], latent_inputs["height"]) == latent_dims
        delivery_inputs = captured["502"]["inputs"]
        assert (delivery_inputs["width"], delivery_inputs["height"]) == delivery_dims
        assert captured["200"]["class_type"] == "LoadImage"
        assert captured["201"] == {
            "inputs": {"pixels": ["200", 0], "vae": ["10", 0]},
            "class_type": "VAEEncode",
            "_meta": {"title": "VAE Encode Init (img2img)"},
        }
        assert captured["13"]["inputs"]["latent_image"] == ["201", 0]
        assert captured["17"]["inputs"]["denoise"] == pytest.approx(0.42)
        assert captured["17"]["inputs"]["model"] == ["301", 0]
        assert captured["22"]["inputs"]["model"] == ["301", 0]
        assert captured["22"]["inputs"]["conditioning"] == ["60", 0]
        _assert_no_unsupported_dynamic_nodes(captured)

    def test_completed_job_uses_validated_atomic_client_download(
        self, tmp_path, monkeypatch
    ):
        """The production path publishes through RunPodComfyUI.download_image."""
        _stub_comfyui_path(monkeypatch, tmp_path)
        monkeypatch.setattr(
            pca.RunPodComfyUI,
            "wait_for_completion",
            lambda self, pid: {
                pid: {
                    "status": {"completed": True},
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "FLUX_PuLID_00001_.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            },
            raising=True,
        )
        published = []

        def _download(
            self,
            filename,
            subfolder,
            folder_type,
            destination,
            *,
            expected_dimensions,
        ):
            published.append(
                (filename, subfolder, folder_type, destination, expected_dimensions)
            )
            Path(destination).write_bytes(b"validated-atomic-image")
            return destination

        monkeypatch.setattr(
            pca.RunPodComfyUI, "download_image", _download, raising=True
        )
        output = tmp_path / "out.jpg"

        result = pca.generate_ai_broll(
            "a city skyline",
            str(output),
            ctx=PipelineContext(global_settings={"aspect_ratio": "9:16"}),
            quality_tier="production",
        )

        assert result == pca.ImageGenResult(str(output), "COMFYUI_PULID")
        assert published == [
            (
                "FLUX_PuLID_00001_.png",
                "",
                "output",
                str(output),
                (1536, 2688),
            )
        ]
        assert output.read_bytes() == b"validated-atomic-image"

    def test_monitor_failure_cancels_known_prompt_before_fallback(
        self, tmp_path, monkeypatch
    ):
        _stub_comfyui_path(monkeypatch, tmp_path)
        cancelled = []
        monkeypatch.setattr(
            pca.RunPodComfyUI,
            "wait_for_completion",
            lambda self, pid: (_ for _ in ()).throw(RuntimeError("history lost")),
            raising=True,
        )
        monkeypatch.setattr(
            pca.RunPodComfyUI,
            "cancel_prompt",
            lambda self, pid: cancelled.append(pid) or True,
            raising=True,
        )

        result = pca.generate_ai_broll(
            "a city skyline",
            str(tmp_path / "out.jpg"),
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            quality_tier="production",
        )

        assert cancelled == ["fake-prompt-id"]
        assert result == pca.ImageGenResult("stub.jpg", "POLLINATIONS")

    def test_confirmed_timeout_is_not_cancelled_twice_before_fallback(
        self, tmp_path, monkeypatch
    ):
        _stub_comfyui_path(monkeypatch, tmp_path)
        cancelled = []

        def _cancel(self, prompt_id):
            cancelled.append(prompt_id)
            return True

        def _wait(self, prompt_id):
            # Match RunPodComfyUI.wait_for_completion's contract: a timeout is
            # raised only after this prompt's cancellation was confirmed.
            assert self.cancel_prompt(prompt_id) is True
            raise pca.ComfyUITimeout(
                "deadline exceeded after confirmed ID-scoped cancellation"
            )

        monkeypatch.setattr(
            pca.RunPodComfyUI, "cancel_prompt", _cancel, raising=True
        )
        monkeypatch.setattr(
            pca.RunPodComfyUI, "wait_for_completion", _wait, raising=True
        )

        result = pca.generate_ai_broll(
            "a city skyline",
            str(tmp_path / "out.jpg"),
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            quality_tier="production",
        )

        assert cancelled == ["fake-prompt-id"]
        assert result == pca.ImageGenResult("stub.jpg", "POLLINATIONS")

    def test_unknown_prompt_acknowledgement_refuses_duplicate_fallback(
        self, tmp_path, monkeypatch
    ):
        _stub_comfyui_path(monkeypatch, tmp_path)
        monkeypatch.setattr(
            pca.RunPodComfyUI,
            "queue_prompt",
            lambda self, workflow: (_ for _ in ()).throw(
                pca.ComfyUISubmitUnknown("acknowledgement lost")
            ),
            raising=True,
        )
        fallbacks = []
        monkeypatch.setattr(
            pca,
            "_fal_flux_fallback",
            lambda *args, **kwargs: fallbacks.append((args, kwargs)),
        )

        recovery = {}
        result = pca.generate_ai_broll(
            "a city skyline",
            str(tmp_path / "out.jpg"),
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            quality_tier="production",
            _recovery_out=recovery,
        )

        assert result is None
        assert fallbacks == []
        assert recovery == {
            "engine": "COMFYUI_PULID",
            "status": "recovery_required",
            "provider_status": "submission_unknown",
            "reason": (
                "ComfyUI may still have accepted or completed this keyframe. "
                "Reconcile its queue and history before allowing another render."
            ),
        }

    @pytest.mark.parametrize("cancel_outcome", [False, RuntimeError("pod lost")])
    def test_monitor_failure_without_confirmed_cancel_refuses_fallback(
        self, cancel_outcome, tmp_path, monkeypatch
    ):
        _stub_comfyui_path(monkeypatch, tmp_path)
        monkeypatch.setattr(
            pca.RunPodComfyUI,
            "wait_for_completion",
            lambda self, pid: (_ for _ in ()).throw(RuntimeError("history lost")),
            raising=True,
        )

        def _cancel(self, pid):
            if isinstance(cancel_outcome, BaseException):
                raise cancel_outcome
            return cancel_outcome

        monkeypatch.setattr(
            pca.RunPodComfyUI, "cancel_prompt", _cancel, raising=True
        )
        fallbacks = []
        monkeypatch.setattr(
            pca,
            "_fal_flux_fallback",
            lambda *args, **kwargs: fallbacks.append((args, kwargs)),
        )

        recovery = {}
        result = pca.generate_ai_broll(
            "a city skyline",
            str(tmp_path / "out.jpg"),
            ctx=PipelineContext(global_settings={"aspect_ratio": "16:9"}),
            quality_tier="production",
            _recovery_out=recovery,
        )

        assert result is None
        assert fallbacks == []
        assert recovery["provider_status"] == "job_state_unknown"
        assert recovery["job_id"] == "fake-prompt-id"


# ---------------------------------------------------------------------------
# Phase 2 — Task 3: FAL Kontext / Pro / schnell / Pollinations orientation
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_fal_portrait(monkeypatch):
    """Stub fal_client + image download so _fal_flux_fallback runs offline.

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

    def _fake_download(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
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

        def _fake_download(url, filename):
            captured_urls.append(url)
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
            return filename

        monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio="9:16")

        assert captured_urls, "image download was not called — Pollinations path not reached"
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

        def _fake_download(url, filename):
            captured_urls.append(url)
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
            return filename

        monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
        out = str(tmp_path / "out.jpg")

        pca._fal_flux_fallback("a prompt", out, seed=1, character_image=None,
                               aspect_ratio=None)

        assert captured_urls, "image download was not called"
        url = captured_urls[0]
        assert "width=1344" in url, f"Pollinations landscape URL should have width=1344, got: {url}"
        assert "height=768" in url, f"Pollinations landscape URL should have height=768, got: {url}"

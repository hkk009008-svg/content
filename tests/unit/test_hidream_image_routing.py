"""Unit tests for the HiDream-I1 image-engine routing wire.

Context: the prompt optimizer emits `suggested_image_api` (FLUX_DEV |
HIDREAM_I1 | SD3_5_LARGE; llm/prompt_optimizer.py). The controller now forwards
it into the max-tier `shot_hint["image_api"]`
(cinema/shots/controller.py::generate_keyframe_take). quality_max's gate
(`requested_image_api == "HIDREAM_I1"`) then calls `_swap_to_hidream`, which
swaps the FLUX UNet loader for HiDream's — but ONLY when the pod actually has
the custom node installed (self-guard); otherwise it no-ops and stays on FLUX.

These tests cover that self-guarding swap, the *consumer* end of the wire. The
optimizer's producer logic is covered by test_prompt_optimizer.py; the 1-line
controller forward is the seam between. The real HiDream firing is GPU-gated
(needs the pod node) — see the cycle-17 GPU-validation task.

Offline — no GPU, no pod, no API calls.
"""

from __future__ import annotations

from quality_max import _swap_to_hidream


def _flux_workflow_with_pulid() -> dict:
    """A minimal max-tier workflow stub: FLUX UNet at node 112, a PuLID-Flux
    chain (97/99/100/101/93), a sampler (200) consuming the PuLID-applied model
    output (node 100), and a LoRA loader at node 700."""
    return {
        "112": {"class_type": "UNETLoader",
                "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "97": {"class_type": "PulidFluxModelLoader", "inputs": {}},
        "99": {"class_type": "PulidFluxInsightFaceLoader", "inputs": {}},
        "100": {"class_type": "ApplyPulidFlux", "inputs": {"model": ["112", 0]}},
        "101": {"class_type": "PulidFluxEvaClipLoader", "inputs": {}},
        "93": {"class_type": "LoadImage", "inputs": {}},
        "700": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["112", 0]}},
        "200": {"class_type": "KSampler", "inputs": {"model": ["100", 0], "seed": 1}},
    }


class TestSwapToHidream:
    def test_swaps_when_node_available(self):
        wf = _flux_workflow_with_pulid()
        ok = _swap_to_hidream(wf, {"HiDreamModelLoader"})
        assert ok is True
        assert wf["112"]["class_type"] == "HiDreamModelLoader"
        assert wf["112"]["inputs"]["model_name"] == "HiDream-I1-Full.safetensors"

    def test_accepts_any_known_loader_class_name(self):
        # The swap probes three community wrapper names in order.
        for cls in ("HiDreamModelLoader", "HiDreamI1Loader", "HiDreamLoader"):
            wf = _flux_workflow_with_pulid()
            assert _swap_to_hidream(wf, {cls}) is True
            assert wf["112"]["class_type"] == cls

    def test_strips_pulid_nodes_on_swap(self):
        wf = _flux_workflow_with_pulid()
        _swap_to_hidream(wf, {"HiDreamI1Loader"})
        for nid in ("97", "99", "100", "101", "93"):
            assert nid not in wf, f"PuLID node {nid} should be stripped (HiDream has no PuLID)"
        assert "700" in wf, "LoRA chain must survive the swap"

    def test_rewires_pulid_consumers_to_lora(self):
        wf = _flux_workflow_with_pulid()
        _swap_to_hidream(wf, {"HiDreamLoader"})
        # The sampler that consumed node 100 (ApplyPulidFlux) is rewired to LoRA (700).
        assert wf["200"]["inputs"]["model"] == ["700", 0]

    def test_noop_when_node_unavailable(self):
        wf = _flux_workflow_with_pulid()
        before = dict(wf["112"])
        ok = _swap_to_hidream(wf, set())
        assert ok is False
        assert wf["112"] == before, "no swap when no HiDream loader class is on the pod"
        assert "100" in wf, "PuLID chain must be untouched on a no-op (stays on FLUX)"

    def test_noop_when_no_unet_node(self):
        wf = {"700": {"class_type": "LoraLoaderModelOnly", "inputs": {}}}
        assert _swap_to_hidream(wf, {"HiDreamModelLoader"}) is False

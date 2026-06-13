"""Regression guard: the production pulid.json must use the FLUX-native PuLID nodes.

The shipping production tier renders via pulid.json on a FLUX UNet (node 112 =
flux1-dev-fp8). The SDXL-era PuLID nodes (PulidModelLoader / ApplyPulid /
PulidEvaClipLoader) patch U-Net cross-attention layers FLUX's DiT lacks -> zero
face lock (a silent no-op). This test pins the FLUX-native node set so the
misconfiguration can never silently regress.

See ADR-024 + docs/superpowers/specs/2026-06-13-production-pulid-flux-fix-design.md.
"""
import json
from pathlib import Path

import pytest

PULID = Path(__file__).resolve().parents[2] / "pulid.json"


@pytest.fixture(scope="module")
def graph():
    data = json.loads(PULID.read_text())
    data.pop("_metadata", None)
    return data


def test_pulid_loader_is_flux_native(graph):
    assert graph["99"]["class_type"] == "PulidFluxModelLoader"
    assert graph["99"]["inputs"]["pulid_file"] == "pulid_flux_v0.9.1.safetensors"


def test_eva_clip_loader_is_flux_native(graph):
    assert graph["101"]["class_type"] == "PulidFluxEvaClipLoader"


def test_apply_pulid_is_flux_native(graph):
    node = graph["100"]
    assert node["class_type"] == "ApplyPulidFlux"
    inputs = node["inputs"]
    # FLUX node uses pulid_flux, not the SDXL 'pulid' key
    assert "pulid_flux" in inputs
    assert "pulid" not in inputs
    # SDXL-only 'method' key must be gone (unknown to ApplyPulidFlux)
    assert "method" not in inputs
    # model feeds direct from the UNETLoader (no LoRA node 700 in production)
    assert inputs["model"] == ["112", 0]
    # coarse-identity window must start at 0.0
    assert inputs["start_at"] == 0.0
    # a FLUX-specific fusion param is present
    assert inputs["fusion"] == "mean"


def test_no_sdxl_pulid_nodes_remain(graph):
    classes = {n.get("class_type") for n in graph.values() if isinstance(n, dict)}
    assert "ApplyPulid" not in classes
    assert "PulidModelLoader" not in classes
    assert "PulidEvaClipLoader" not in classes

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


def test_production_pulid_start_at_is_flux_zero():
    """Character-bearing classes must start PuLID at 0.0 (FLUX coarse-identity
    window). Otherwise apply_workflow_params overwrites the graph default and
    re-suppresses the swap. landscape has pulid_weight 0.0 (PuLID off) so its
    start_at is irrelevant."""
    import workflow_selector as ws
    for cls in ("portrait", "medium", "wide", "action"):
        assert ws.WORKFLOW_TEMPLATES[cls]["pulid_start_at"] == 0.0, cls


def test_production_graph_tracked_lowercase():
    """Regression guard for the case-sensitivity landmine (ADR-024 / operator F1).

    All code opens open('pulid.json') (phase_c_assembly.py:178/204), but git
    tracked the graph as 'Pulid.json' (capital P). On case-insensitive macOS both
    resolve to one inode so it works; on a case-SENSITIVE checkout (Linux CI/pod)
    open('pulid.json') -> FileNotFoundError and the production PuLID branch
    silently cascades, making the FLUX-native fix (Chunk-1) unreachable.

    os.path.exists() is blind to tracked case on macOS (same inode), so assert
    against HEAD's tree -- the committed truth, immune to per-seat index churn.
    """
    import subprocess

    root = Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("not a git checkout")
    variants = [p for p in out.splitlines() if p.lower() == "pulid.json"]
    assert variants == ["pulid.json"], (
        "production graph must be tracked as lowercase 'pulid.json' "
        f"(all code opens open('pulid.json')); got {variants!r}"
    )


def test_apply_params_default_start_at_is_flux_zero():
    """apply_workflow_params' fallback start_at must be the FLUX coarse-identity
    0.0, not the SDXL-era 0.3. Templates always pass pulid_start_at so the default
    is normally unreached, but a caller that omits it must not silently re-suppress
    the FLUX swap (operator advisory F2)."""
    import workflow_selector as ws
    wf = {"100": {"inputs": {}}}
    ws.apply_workflow_params(wf, {})
    assert wf["100"]["inputs"]["start_at"] == 0.0


def test_pulid_patched_model_feeds_pag(graph):
    """The PuLID-patched model (node 100, ApplyPulidFlux) must feed PAG (node 301)
    -> sampler. Pins the wiring so a future edit that disconnects 100->301 can't
    silently pass while the class set still looks correct (operator advisory F3;
    the original SDXL-on-FLUX no-op bug was test-dark)."""
    assert graph["301"]["class_type"] == "PerturbedAttentionGuidance"
    assert graph["301"]["inputs"]["model"] == ["100", 0]

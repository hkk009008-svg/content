"""Offline tests for the LoRA quality gate (no GPU/ComfyUI — all boundaries mocked)."""
import pytest
from prep.lora_quality import _next_lora_action, LoraAction

THRESH, BASE, BUDGET = 0.6, 0.45, 3


@pytest.mark.parametrize("attempt,score,expected", [
    (0, 0.72, LoraAction.ACCEPT),            # meets threshold on first train
    (0, None, LoraAction.ACCEPT),            # validation skipped -> accept (register unvalidated)
    (0, 0.50, LoraAction.RETRY_MORE_STEPS),  # 1st low score -> escalate steps
    (1, 0.55, LoraAction.RETRY_HIGHER_RANK), # 2nd low score -> escalate rank
    (2, 0.50, LoraAction.ACCEPT),            # budget exhausted, best >= baseline -> keep best
    (2, 0.40, LoraAction.REJECT),            # budget exhausted, best < baseline -> reject (PuLID-only)
    (2, 0.60, LoraAction.ACCEPT),            # exactly at threshold on final -> accept
])
def test_next_lora_action(attempt, score, expected):
    assert _next_lora_action(attempt, score, threshold=THRESH, baseline=BASE, budget=BUDGET) is expected


# ---------------------------------------------------------------------------
# Task 2 — _generate_with_lora
# ---------------------------------------------------------------------------
from unittest.mock import patch, MagicMock
import prep.lora_quality as lq


def test_generate_with_lora_injects_strength_and_runs_once(tmp_path, monkeypatch):
    calls = {"run": 0}
    fake_wf = {"700": {"inputs": {}}}
    monkeypatch.setattr(lq, "_qm_load_max_workflow", lambda: dict(fake_wf), raising=False)
    captured = {}

    def fake_inject_identity(wf, char_lora, face_anchor_remote, params, has_character):
        captured["lora"] = char_lora
        captured["strength_model"] = params.get("lora_strength_model")
        captured["strength_clip"] = params.get("lora_strength_clip")

    def fake_run_one(comfy, wf, output_filename, *a, **k):
        calls["run"] += 1
        return str(tmp_path / output_filename)

    monkeypatch.setattr(lq, "_qm_inject_identity", fake_inject_identity, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_conditioning", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_sampling", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_run_one_candidate", fake_run_one, raising=False)
    monkeypatch.setattr(lq, "_make_comfy", lambda url: MagicMock(), raising=False)
    monkeypatch.setattr(lq, "_default_max_params", lambda shot_type="portrait": {}, raising=False)

    out = lq._generate_with_lora("/loras/mara_v1.safetensors", "<mara> headshot",
                                 strength=0.55, seed=7, out_path=str(tmp_path / "g0.png"),
                                 comfyui_url="http://x:8188")
    assert out is not None
    assert calls["run"] == 1                          # single generation, no best-of
    assert captured["lora"] == "/loras/mara_v1.safetensors"
    assert captured["strength_model"] == 0.55 and captured["strength_clip"] == 0.55


def test_generate_with_lora_returns_none_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(lq, "_qm_load_max_workflow", lambda: {}, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_identity", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_conditioning", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_sampling", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_default_max_params", lambda shot_type="portrait": {}, raising=False)
    monkeypatch.setattr(lq, "_make_comfy", lambda url: (_ for _ in ()).throw(OSError("unreachable")), raising=False)
    out = lq._generate_with_lora("/loras/x.safetensors", "<x>", strength=1.0, seed=1,
                                 out_path=str(tmp_path / "g.png"), comfyui_url="http://x:8188")
    assert out is None


def test_generate_with_lora_injects_seed_into_node_25(tmp_path, monkeypatch):
    # The seed must reach the workflow's noise node (25) — _inject_sampling does NOT
    # set it, so without the explicit injection every gen reuses the template seed.
    captured = {}
    monkeypatch.setattr(lq, "_qm_load_max_workflow",
                        lambda: {"700": {"inputs": {}}, "25": {"inputs": {}}}, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_identity", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_conditioning", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_sampling", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_default_max_params", lambda shot_type="portrait": {}, raising=False)
    monkeypatch.setattr(lq, "_make_comfy", lambda url: MagicMock(), raising=False)

    def fake_run_one(comfy, wf, output_filename, *a, **k):
        captured["wf"] = wf
        return str(tmp_path / "g.png")
    monkeypatch.setattr(lq, "_qm_run_one_candidate", fake_run_one, raising=False)

    lq._generate_with_lora("/loras/c1.safetensors", "<c1>", strength=0.55, seed=4242,
                           out_path=str(tmp_path / "g.png"), comfyui_url="http://x:8188")
    assert captured["wf"]["25"]["inputs"]["noise_seed"] == 4242


# ---------------------------------------------------------------------------
# Task 3 — validate_lora_quality
# ---------------------------------------------------------------------------
from types import SimpleNamespace


def _cs(arc, has_arc=True):
    return SimpleNamespace(arc_score=arc, has_arc=has_arc)


def test_validate_picks_best_strength(monkeypatch, tmp_path):
    # score depends on strength: 0.55 is best, 1.0 over-bakes
    scores_by_strength = {0.45: 0.50, 0.55: 0.74, 0.7: 0.66, 1.0: 0.58}
    cur = {"score": 0.0}   # side-channel: gen() sets the score the next score_candidate returns

    def gen(lora_path, prompt, *, strength, seed, out_path, comfyui_url):
        cur["score"] = scores_by_strength[strength]
        return out_path
    monkeypatch.setattr(lq, "_generate_with_lora", gen)
    monkeypatch.setattr(lq, "_score_candidate", lambda img, anchor: _cs(cur["score"]))

    (tmp_path / "ref.png").write_bytes(b"x")
    char = {"id": "c1", "name": "Mara", "canonical_reference": str(tmp_path / "ref.png")}
    res = lq.validate_lora_quality("/loras/c1.safetensors", char,
                                   strengths=[0.45, 0.55, 0.7, 1.0], comfyui_url="http://x:8188")
    assert not res.skipped
    assert res.best_strength == 0.55
    assert abs(res.best_score - 0.74) < 1e-6


def test_validate_skips_when_no_canonical_reference(monkeypatch):
    res = lq.validate_lora_quality("/loras/c1.safetensors", {"id": "c1", "canonical_reference": ""},
                                   comfyui_url="http://x:8188")
    assert res.skipped and res.skip_reason == "no_canonical_reference"


def test_validate_skips_when_all_generations_fail(monkeypatch, tmp_path):
    (tmp_path / "ref.png").write_bytes(b"x")
    monkeypatch.setattr(lq, "_generate_with_lora", lambda *a, **k: None)  # all gens fail
    res = lq.validate_lora_quality("/loras/c1.safetensors",
                                   {"id": "c1", "canonical_reference": str(tmp_path / "ref.png")},
                                   strengths=[0.55, 1.0], comfyui_url="http://x:8188")
    assert res.skipped


def test_validate_mean_ignores_has_arc_false(monkeypatch, tmp_path):
    (tmp_path / "ref.png").write_bytes(b"x")
    monkeypatch.setattr(lq, "_generate_with_lora", lambda *a, **k: "g.png")
    seq = iter([_cs(0.7), _cs(0.0, has_arc=False), _cs(0.5)])  # middle sample is a skip
    monkeypatch.setattr(lq, "_score_candidate", lambda img, anchor: next(seq))
    res = lq.validate_lora_quality("/loras/c1.safetensors",
                                   {"id": "c1", "canonical_reference": str(tmp_path / "ref.png")},
                                   strengths=[0.55], prompts=["a", "b", "c"], comfyui_url="http://x:8188")
    # mean of 0.7 and 0.5 (skip the has_arc=False sample) = 0.6
    assert abs(res.best_score - 0.6) < 1e-6

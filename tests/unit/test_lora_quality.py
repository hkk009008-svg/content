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

"""Tests for train_character_lora as a pure single-train function (Task 5 TDD).

After Task 5:
- train_character_lora no longer calls validate_lora_quality internally.
- quality_score in the return dict is always None on success.
- LORA_VALIDATION_SKIPPED constant is removed.
- The validate_lora_quality stub is removed from prep.lora_training.
"""
import json

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path):
    """Minimal project dir with one character and one reference image."""
    char_id = "char_test_001"
    char_dir = tmp_path / "characters" / char_id
    char_dir.mkdir(parents=True)
    # Write a tiny fake reference image (just a file that exists)
    ref = char_dir / "ref.jpg"
    ref.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)  # JPEG magic bytes + padding

    project = {
        "id": "proj_test_001",
        "characters": [{"id": char_id, "name": "Test Character", "canonical_reference": str(ref)}],
    }
    (tmp_path / "project.json").write_text(json.dumps(project))
    return str(tmp_path), char_id


# ---------------------------------------------------------------------------
# Test: successful single-train returns quality_score=None
# ---------------------------------------------------------------------------

def test_train_character_lora_success_quality_score_is_none(tmp_path, monkeypatch):
    """A successful train returns quality_score=None — no internal validation."""
    import prep.lora_training as lt

    project_dir, char_id = _make_project(tmp_path)
    character = {"id": char_id, "name": "Test", "canonical_reference": "ref.jpg"}

    # Stub out dataset prep
    monkeypatch.setattr(lt, "prepare_character_lora_dataset", lambda pd, ch: {
        "image_count": 5,
        "dataset_dir": str(tmp_path / "dataset"),
    })

    # Stub trainer detection — report ai-toolkit present
    monkeypatch.setattr(lt, "_detect_trainer", lambda: "ai-toolkit")

    # Stub config writing (doesn't need to produce a real file)
    monkeypatch.setattr(lt, "_write_ai_toolkit_config", lambda *a, **kw: "/tmp/fake_config.yaml")

    # Stub the subprocess boundary — success
    monkeypatch.setattr(lt, "_run_ai_toolkit", lambda config, log: 0)

    # Create the expected output .safetensors file so the locator finds it
    # _character_lora_dir returns <project_dir>/loras/<char_id>
    output_dir = tmp_path / "loras" / char_id / "output"
    output_dir.mkdir(parents=True)
    fake_lora = output_dir / "char_test_001.safetensors"
    fake_lora.write_bytes(b"\x00" * 16)

    result = lt.train_character_lora(str(tmp_path), character)

    assert result["success"] is True
    assert result["lora_path"] is not None
    assert result["quality_score"] is None, (
        f"Expected quality_score=None (no internal validation), got {result['quality_score']!r}"
    )


def test_train_character_lora_no_validate_stub_defined():
    """After Task 5, validate_lora_quality and LORA_VALIDATION_SKIPPED must not exist in prep.lora_training."""
    import prep.lora_training as lt
    assert not hasattr(lt, "validate_lora_quality"), (
        "validate_lora_quality stub must be removed from prep.lora_training"
    )
    assert not hasattr(lt, "LORA_VALIDATION_SKIPPED"), (
        "LORA_VALIDATION_SKIPPED sentinel must be removed from prep.lora_training"
    )

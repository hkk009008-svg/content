"""Per-character LoRA training — orchestration for FLUX LoRA fine-tuning.

WHAT THIS DOES
--------------
Wraps ai-toolkit (preferred) or kohya-ss as a subprocess to train a per-character
LoRA on the project's reference images. The trained LoRA gets registered in
project.global_settings.char_lora_paths and is picked up by the maxed-quality
pipeline automatically (see workflow_selector + quality_max).

WHY IT MATTERS
--------------
Inference-time identity locks (PuLID, InfU, PhotoMaker) encode a face *embedding*,
not a person. They fail on hairstyle, body proportions, ear shape, neck, hands.
A trained LoRA learns the WHOLE identity manifold — face + body + hair +
distinctive features — and is the single biggest identity-quality lever in the
pipeline.

WHAT YOU PROVIDE
----------------
1. 25-50 varied reference images per character (see DATASET_GUIDELINES).
2. A GPU box with >= 24GB VRAM (RTX 4090 or rented RunPod pod). Training is
   ~30 min for FLUX LoRA at rank 32, fp16.
3. One of:
   - ai-toolkit installed:    pip install ai-toolkit (or git clone ostris/ai-toolkit)
   - kohya-ss installed:      git clone bmaltais/kohya_ss and run the setup script
4. Optionally a HUGGINGFACE_TOKEN env var (the FLUX-Dev base model is gated).

WHAT THIS MODULE DOES NOT DO
----------------------------
- Hyperparameter sweeps (use the defaults; they're calibrated for FLUX portraits).
- Multi-character training (one LoRA per character is the right architecture).
- Distributed training (single-GPU fine-tune is intentional — 30 min is fine).

API
---
prepare_character_lora_dataset(project_dir, character) -> dict
train_character_lora(project_dir, character, base_model="FLUX1/flux1-dev-fp16.safetensors") -> dict
get_lora_status(project_dir, char_id) -> dict

Note: validate_lora_quality has moved to prep.lora_quality (real ArcFace oracle).
The gated orchestrator (train + validate + retrain loop) is prep.lora_quality.train_character_lora_gated.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional


def _safe_under(base: str, *parts: str) -> str:
    """Join `parts` to `base` and assert the result is inside `base`.

    Defense-in-depth against path traversal: char_id is server-generated today
    via make_character (uuid4) but any future call site that passes user-supplied
    components must not be able to escape the project tree via `..` segments.
    Raises ValueError on traversal attempts so callers fail loud.
    """
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base, *parts))
    if os.path.commonpath([base_abs, target]) != base_abs:
        raise ValueError(f"path traversal blocked: {parts!r} escapes {base!r}")
    return target


DATASET_GUIDELINES = {
    "ideal_count": "25-50 images per character",
    "minimum_count": 15,
    "required_variety": [
        "Front face (4-6 images)",
        "Three-quarter angle left (3-5)",
        "Three-quarter angle right (3-5)",
        "Profile shots (2-3 each side)",
        "Full body or half body (4-6)",
        "Varied lighting (key, fill, rim, natural, neon)",
        "Varied expressions (neutral, smiling, focused, surprised)",
        "Varied distances (close-up, medium, full)",
    ],
    "avoid": [
        "Watermarks (training learns them)",
        "Heavy makeup if the character is supposed to be natural",
        "Identical poses (variety > quantity past 30 images)",
        "Group shots with multiple faces",
        "Compressed/low-resolution images (training is sensitive)",
    ],
    "image_specs": {
        "min_resolution": "1024x1024 recommended; will be downscaled",
        "format": "JPG or PNG",
        "color_space": "sRGB",
    },
}


# Default training config — calibrated for FLUX-Dev LoRA on portraits.
# Override per-call if needed; these are the values most teams report success with.
DEFAULT_TRAIN_CONFIG = {
    "rank": 32,             # LoRA rank — 32 is sweet spot for character identity
    "alpha": 32,            # Alpha = rank usually
    "learning_rate": 1e-4,  # Conservative; LoRA overshoots fast on FLUX
    "steps": 3000,          # ~30 min on RTX 4090
    "batch_size": 1,        # FLUX VRAM is tight even at fp16
    "resolution": 1024,     # Native FLUX
    "dtype": "fp16",
    "save_every": 500,      # checkpoint per 500 steps for early-stopping if overfitting
    "optimizer": "adamw8bit",
    "scheduler": "constant",
    "noise_offset": 0.05,   # helps darker scenes
    "trigger_token": None,  # if set, all captions get this prefix (e.g. "<char_01>")
}


@dataclass
class LoraStatus:
    """Training job state — persisted to <project>/loras/<char_id>/status.json."""
    char_id: str
    status: str             # idle | preparing | training | validating | done | failed
    progress_percent: float
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    lora_path: Optional[str] = None
    quality_score: Optional[float] = None
    image_count: int = 0
    config: Optional[dict] = None
    error: Optional[str] = None
    log_tail: Optional[str] = None  # last few lines of trainer stdout


# ---------------------------------------------------------------------------
# Dataset prep
# ---------------------------------------------------------------------------

def _character_lora_dir(project_dir: str, char_id: str) -> str:
    """Standard layout: <project>/loras/<char_id>/{dataset/, output/, status.json}.

    Path-traversal-safe: rejects char_id values that escape the project tree.
    """
    return _safe_under(project_dir, "loras", char_id)


def _generate_caption(char_name: str, traits: str, trigger: Optional[str]) -> str:
    """Auto-generated caption per training image. ai-toolkit expects one .txt
    per image alongside it. This is a single shared caption with the trigger
    token + a short trait description — the model learns to associate the
    trigger with the visual content.
    """
    trigger_prefix = f"{trigger} " if trigger else ""
    return f"{trigger_prefix}a photo of {char_name}, {traits[:200]}"


def prepare_character_lora_dataset(
    project_dir: str,
    character: dict,
    extra_captions: Optional[dict] = None,
) -> dict:
    """Stage training images + captions into <project>/loras/<char_id>/dataset/.

    Symlinks images from the character's reference_images to a clean training
    folder, writes a .txt caption per image, and returns a manifest. Idempotent —
    safe to re-run; rebuilds the dataset from scratch each time.

    Args:
        project_dir:  absolute path to the project directory
        character:    Character dict (id, name, physical_traits, reference_images[])
        extra_captions: optional override map { reference_image_path -> caption_text }
                       for per-image captioning instead of the shared one.

    Returns: {dataset_dir, image_count, caption_strategy, manifest_path}
    """
    char_id = character["id"]
    char_name = character.get("name", char_id)
    traits = character.get("physical_traits") or character.get("description", "")
    refs = character.get("reference_images", []) or []

    if len(refs) < DATASET_GUIDELINES["minimum_count"]:
        raise ValueError(
            f"Character {char_name} has only {len(refs)} reference images. "
            f"Minimum {DATASET_GUIDELINES['minimum_count']} required; "
            f"{DATASET_GUIDELINES['ideal_count']} recommended."
        )

    lora_dir = _character_lora_dir(project_dir, char_id)
    dataset_dir = os.path.join(lora_dir, "dataset")

    # Clean slate — wipe any prior dataset
    if os.path.isdir(dataset_dir):
        shutil.rmtree(dataset_dir)
    os.makedirs(dataset_dir, exist_ok=True)

    trigger = (DEFAULT_TRAIN_CONFIG["trigger_token"]
               or f"<{char_id}>")  # default trigger = the char_id
    manifest = []

    for i, ref in enumerate(refs):
        if not os.path.exists(ref):
            print(f"[LoRA] skipping missing reference: {ref}")
            continue
        ext = os.path.splitext(ref)[1].lower() or ".jpg"
        target = os.path.join(dataset_dir, f"{char_id}_{i:03d}{ext}")
        # Hardlink when possible (saves disk); fall back to copy
        try:
            os.link(ref, target)
        except OSError:
            shutil.copy2(ref, target)
        # Caption sidecar
        caption_text = (extra_captions or {}).get(ref) or _generate_caption(
            char_name, traits, trigger
        )
        with open(os.path.splitext(target)[0] + ".txt", "w") as f:
            f.write(caption_text)
        manifest.append({"image": target, "caption": caption_text, "source": ref})

    # Persist manifest
    manifest_path = os.path.join(lora_dir, "dataset_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({
            "char_id": char_id,
            "char_name": char_name,
            "trigger_token": trigger,
            "image_count": len(manifest),
            "items": manifest,
        }, f, indent=2)

    return {
        "dataset_dir": dataset_dir,
        "image_count": len(manifest),
        "caption_strategy": "shared" if not extra_captions else "per-image",
        "trigger_token": trigger,
        "manifest_path": manifest_path,
    }


# ---------------------------------------------------------------------------
# Status I/O
# ---------------------------------------------------------------------------

def _status_path(project_dir: str, char_id: str) -> str:
    return os.path.join(_character_lora_dir(project_dir, char_id), "status.json")


def get_lora_status(project_dir: str, char_id: str) -> dict:
    """Load training status for a character. Returns idle/no-lora when none exists."""
    sp = _status_path(project_dir, char_id)
    if not os.path.exists(sp):
        return asdict(LoraStatus(char_id=char_id, status="idle", progress_percent=0.0))
    try:
        with open(sp) as f:
            return json.load(f)
    except Exception:
        return asdict(LoraStatus(char_id=char_id, status="idle", progress_percent=0.0))


def _write_status(project_dir: str, status: LoraStatus) -> None:
    sp = _status_path(project_dir, status.char_id)
    os.makedirs(os.path.dirname(sp), exist_ok=True)
    with open(sp, "w") as f:
        json.dump(asdict(status), f, indent=2)


# ---------------------------------------------------------------------------
# Trainer subprocess wrappers
# ---------------------------------------------------------------------------

def _detect_trainer() -> Optional[str]:
    """Return 'ai-toolkit' | 'kohya' | None — picks the first installed trainer.
    ai-toolkit is preferred (cleaner FLUX support, simpler config).
    """
    if shutil.which("ai-toolkit") or shutil.which("ai_toolkit"):
        return "ai-toolkit"
    # ai-toolkit can also be installed as a Python module
    try:
        import toolkit  # ai-toolkit's package name  # noqa: F401
        return "ai-toolkit"
    except ImportError:
        pass
    if shutil.which("accelerate"):
        # Loose proxy for kohya-ss; kohya uses accelerate to launch its trainer
        return "kohya"
    return None


def _write_ai_toolkit_config(
    project_dir: str, char_id: str, dataset_info: dict,
    train_config: dict, base_model: str,
) -> str:
    """Render an ai-toolkit YAML config for this character. Returns the config path."""
    lora_dir = _character_lora_dir(project_dir, char_id)
    output_dir = os.path.join(lora_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # ai-toolkit uses YAML; we generate it as a string to avoid a dep on pyyaml.
    # Required fields cover the FLUX-Dev LoRA recipe documented in ostris/ai-toolkit.
    config_yaml = f"""---
job: extension
config:
  name: {char_id}
  process:
    - type: 'sd_trainer'
      training_folder: "{output_dir}"
      device: cuda:0
      network:
        type: "lora"
        linear: {train_config['rank']}
        linear_alpha: {train_config['alpha']}
      save:
        dtype: float16
        save_every: {train_config['save_every']}
        max_step_saves_to_keep: 4
      datasets:
        - folder_path: "{dataset_info['dataset_dir']}"
          caption_ext: "txt"
          caption_dropout_rate: 0.05
          shuffle_tokens: false
          cache_latents_to_disk: true
          resolution: [ {train_config['resolution']} ]
      train:
        batch_size: {train_config['batch_size']}
        steps: {train_config['steps']}
        gradient_accumulation_steps: 1
        train_unet: true
        train_text_encoder: false
        gradient_checkpointing: true
        noise_scheduler: "flowmatch"
        optimizer: "{train_config['optimizer']}"
        lr: {train_config['learning_rate']}
        ema_config:
          use_ema: true
          ema_decay: 0.99
        dtype: bf16
      model:
        name_or_path: "{base_model}"
        is_flux: true
        quantize: true
      sample:
        sampler: "flowmatch"
        sample_every: 250
        width: 1024
        height: 1024
        prompts:
          - "{dataset_info.get('trigger_token', '')} photo, professional headshot, soft natural light"
          - "{dataset_info.get('trigger_token', '')} photo, full body, daylight, casual outfit"
        neg: ""
        seed: 42
        walk_seed: true
        guidance_scale: 4
        sample_steps: 20
meta:
  name: "[name]"
  version: '1.0'
"""
    config_path = os.path.join(lora_dir, "ai_toolkit.yaml")
    with open(config_path, "w") as f:
        f.write(config_yaml)
    return config_path


def _run_ai_toolkit(config_path: str, log_path: str) -> int:
    """Launch ai-toolkit subprocess. Returns the process exit code.
    Writes stdout+stderr to log_path so the UI can tail it.
    """
    # ai-toolkit's typical invocation. Use sys.executable rather than ambient
    # `python` so we hit the same interpreter the server is running under (avoids
    # confusion in venvs with multiple installed Pythons).
    cmd = [sys.executable, "-m", "toolkit.run", config_path]
    with open(log_path, "w") as logf:
        proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, text=True)
        return proc.returncode


# ---------------------------------------------------------------------------
# Top-level training entry point
# ---------------------------------------------------------------------------

def train_character_lora(
    project_dir: str,
    character: dict,
    base_model: str = "FLUX1/flux1-dev-fp16.safetensors",
    config_overrides: Optional[dict] = None,
) -> dict:
    """Train a per-character LoRA. Blocks until complete (or fails).

    Designed to be invoked from a background worker — typical run is ~30 min on
    an RTX 4090. The status.json sidecar is updated at start/finish so UI can poll.

    Returns: {success: bool, lora_path: str?, error: str?, status: full status dict}
    """
    char_id = character["id"]
    log_path = os.path.join(_character_lora_dir(project_dir, char_id), "train.log")
    train_config = {**DEFAULT_TRAIN_CONFIG, **(config_overrides or {})}

    status = LoraStatus(
        char_id=char_id,
        status="preparing",
        progress_percent=0.0,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        config=train_config,
    )
    _write_status(project_dir, status)

    # 1. Dataset prep
    try:
        dataset_info = prepare_character_lora_dataset(project_dir, character)
        status.image_count = dataset_info["image_count"]
    except Exception as e:
        status.status = "failed"
        status.error = f"dataset prep: {e}"
        status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_status(project_dir, status)
        return {"success": False, "error": str(e), "status": asdict(status)}

    # 2. Trainer detection
    trainer = _detect_trainer()
    if trainer is None:
        status.status = "failed"
        status.error = (
            "No LoRA trainer found. Install ai-toolkit (recommended): "
            "git clone https://github.com/ostris/ai-toolkit && cd ai-toolkit && pip install -r requirements.txt"
        )
        status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_status(project_dir, status)
        return {"success": False, "error": status.error, "status": asdict(status)}

    status.status = "training"
    _write_status(project_dir, status)

    # 3. Run trainer
    try:
        if trainer == "ai-toolkit":
            config_path = _write_ai_toolkit_config(
                project_dir, char_id, dataset_info, train_config, base_model,
            )
            rc = _run_ai_toolkit(config_path, log_path)
        else:
            status.error = f"trainer {trainer} not yet wired (use ai-toolkit)"
            rc = 1
    except Exception as e:
        rc = 1
        status.error = f"trainer subprocess: {e}"

    # Capture tail of log for UI
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                lines = f.readlines()
            status.log_tail = "".join(lines[-40:])
        except Exception:
            pass

    if rc != 0:
        status.status = "failed"
        if not status.error:
            status.error = f"trainer exited with code {rc}"
        status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_status(project_dir, status)
        return {"success": False, "error": status.error, "status": asdict(status)}

    # 4. Locate the produced LoRA — ai-toolkit writes to output_dir/<name>.safetensors
    output_dir = os.path.join(_character_lora_dir(project_dir, char_id), "output")
    lora_path = None
    if os.path.isdir(output_dir):
        for fname in sorted(os.listdir(output_dir)):
            if fname.endswith(".safetensors"):
                lora_path = os.path.join(output_dir, fname)
                break

    if not lora_path or not os.path.exists(lora_path):
        status.status = "failed"
        status.error = "trainer succeeded but no .safetensors found in output dir"
        status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_status(project_dir, status)
        return {"success": False, "error": status.error, "status": asdict(status)}

    # Validation now lives in prep.lora_quality.train_character_lora_gated.
    # This function is pure single-train; quality_score is left unset (None).
    status.quality_score = None
    status.lora_path = lora_path
    status.status = "done"
    status.progress_percent = 100.0
    status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_status(project_dir, status)

    return {
        "success": True,
        "lora_path": lora_path,
        "quality_score": status.quality_score,
        "status": asdict(status),
    }


# ---------------------------------------------------------------------------
# CLI for quick testing / one-off training
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print(f"Usage: python -m prep.lora_training <project_dir> <character_id>")
        sys.exit(1)
    pd, cid = sys.argv[1], sys.argv[2]
    # Load character from project.json
    proj_file = os.path.join(pd, "project.json")
    with open(proj_file) as f:
        project = json.load(f)
    char = next((c for c in project.get("characters", []) if c["id"] == cid), None)
    if not char:
        print(f"Character {cid} not found in project")
        sys.exit(1)
    out = train_character_lora(pd, char)
    print(json.dumps(out, indent=2))

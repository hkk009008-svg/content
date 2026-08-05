"""Deterministic flat ComfyUI API graph for FLUX.2 Klein 4B distilled.

The graph is an offline candidate derived from the official ComfyUI workflow
template pinned in ``revisions.json``.  It uses only pinned ComfyUI core node
classes: no UI subgraphs or custom nodes are required.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any


CAPABILITY = "image-flux2-klein"
MODEL_FILENAME = "flux-2-klein-4b-fp8.safetensors"
TEXT_ENCODER_FILENAME = "qwen_3_4b.safetensors"
VAE_FILENAME = "flux2-klein-vae-bf16.safetensors"
DISTILLED_STEPS = 4
MAX_REFERENCE_IMAGES = 10

# Fixed, reviewable 1-megapixel-class canvases. Every dimension is divisible
# by 16, matching EmptyFlux2LatentImage's pinned core contract.
ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "2:3": (832, 1248),
    "3:2": (1248, 832),
    "3:4": (864, 1152),
    "4:3": (1152, 864),
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "21:9": (1568, 672),
}


def _remote_filename(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reference image names must be non-empty strings")
    name = value.strip()
    if "\\" in name or "\x00" in name:
        raise ValueError("reference image names must use safe POSIX paths")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("reference image names cannot escape the ComfyUI input folder")
    return name


def build_flux2_klein_workflow(
    *,
    prompt: str,
    reference_images: Sequence[str],
    seed: int,
    aspect_ratio: str,
    filename_prefix: str = "flux2-klein",
) -> dict[str, dict[str, Any]]:
    """Build a fixed-seed, four-step, 1..N reference API workflow.

    ``N`` is bounded to the official FLUX.2 multi-reference envelope of ten to
    prevent an operator mistake from constructing an unbounded latent graph.
    The returned object is directly suitable as ComfyUI's ``prompt`` value.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if len(prompt) > 4096:
        raise ValueError("prompt cannot exceed 4096 characters")
    if isinstance(reference_images, (str, bytes)) or not isinstance(
        reference_images, Sequence
    ):
        raise ValueError("reference_images must be a sequence")
    if not 1 <= len(reference_images) <= MAX_REFERENCE_IMAGES:
        raise ValueError(
            f"reference_images must contain 1..{MAX_REFERENCE_IMAGES} items"
        )
    remote_images = [_remote_filename(value) for value in reference_images]
    if len(set(remote_images)) != len(remote_images):
        raise ValueError("reference image names must be unique")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if aspect_ratio not in ASPECT_DIMENSIONS:
        raise ValueError(
            f"aspect_ratio must be one of {sorted(ASPECT_DIMENSIONS)}"
        )
    if (
        not isinstance(filename_prefix, str)
        or not filename_prefix.strip()
        or len(filename_prefix) > 80
        or any(char in filename_prefix for char in "\\/\x00")
    ):
        raise ValueError("filename_prefix must be a safe non-empty filename prefix")

    width, height = ASPECT_DIMENSIONS[aspect_ratio]
    graph: dict[str, dict[str, Any]] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": MODEL_FILENAME,
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": TEXT_ENCODER_FILENAME,
                "type": "flux2",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE_FILENAME},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": prompt.strip()},
        },
        "5": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["4", 0]},
        },
        "6": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": seed},
        },
        "7": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": "euler"},
        },
        "8": {
            "class_type": "Flux2Scheduler",
            "inputs": {
                "steps": DISTILLED_STEPS,
                "width": width,
                "height": height,
            },
        },
        "9": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
    }

    positive: list[object] = ["4", 0]
    negative: list[object] = ["5", 0]
    for index, remote_name in enumerate(remote_images):
        base = 100 + index * 10
        load_id = str(base)
        scale_id = str(base + 1)
        encode_id = str(base + 2)
        positive_id = str(base + 3)
        negative_id = str(base + 4)
        graph[load_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": remote_name},
        }
        graph[scale_id] = {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": [load_id, 0],
                "upscale_method": "nearest-exact",
                "megapixels": 1.0,
                "resolution_steps": 16,
            },
        }
        graph[encode_id] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": [scale_id, 0], "vae": ["3", 0]},
        }
        graph[positive_id] = {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": positive, "latent": [encode_id, 0]},
        }
        graph[negative_id] = {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": negative, "latent": [encode_id, 0]},
        }
        positive = [positive_id, 0]
        negative = [negative_id, 0]

    graph.update(
        {
            "20": {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": ["1", 0],
                    "positive": positive,
                    "negative": negative,
                    "cfg": 1.0,
                },
            },
            "21": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["6", 0],
                    "guider": ["20", 0],
                    "sampler": ["7", 0],
                    "sigmas": ["8", 0],
                    "latent_image": ["9", 0],
                },
            },
            "22": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["21", 0], "vae": ["3", 0]},
            },
            "23": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["22", 0],
                    "filename_prefix": filename_prefix.strip(),
                },
            },
        }
    )
    return graph


REQUIRED_NODE_CLASSES = frozenset(
    node["class_type"]
    for node in build_flux2_klein_workflow(
        prompt="contract probe",
        reference_images=["reference-1.png"],
        seed=0,
        aspect_ratio="1:1",
    ).values()
)

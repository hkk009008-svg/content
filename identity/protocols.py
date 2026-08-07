"""Small, fixed Identity Lab comparison contract."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_PROTOCOL_ID = "identity-benchmark-v1"
BENCHMARK_PROMPT = (
    "Cinematic medium close-up portrait of the same person, neutral expression, "
    "natural daylight, realistic skin texture, simple background, preserve exact "
    "facial identity, no text or watermark."
)
LORA_BENCHMARK_PROMPT = BENCHMARK_PROMPT.replace(
    "portrait of the same person", "portrait of hkkperson person"
)


@dataclass(frozen=True)
class CellSpec:
    cell_key: str
    method: str
    label: str
    reference_count: int
    seed: int = 0


NATIVE_FLUX2_CELL_SPECS = (
    CellSpec("native_flux2:r1:s0", "native_flux2", "1 reference", 1),
    CellSpec("native_flux2:r2:s0", "native_flux2", "2 references", 2),
    CellSpec("native_flux2:r4:s0", "native_flux2", "4 references", 4),
)

LORA_CELL_SPECS = (
    CellSpec("flux2_lora:control:s0", "flux2_character_lora", "Text-only control", 0),
    CellSpec("flux2_lora:adapter:s0", "flux2_character_lora", "Character LoRA", 0),
)

COMPARISON_CELL_SPECS = NATIVE_FLUX2_CELL_SPECS + LORA_CELL_SPECS


METHOD_CATALOG = (
    {
        "method": "native_flux2",
        "label": "Native FLUX.2 Klein 4B",
        "state": "available",
        "reason": "Runs the same prompt and seed with one, two, and four references.",
    },
    {
        "method": "flux2_character_lora",
        "label": "FLUX.2 character LoRA",
        "state": "blocked",
        # Shown only when no usable shared worker endpoint is configured, so the
        # gateway cannot be asked anything at all. It must not assert what the
        # trainer's state IS: the pinned trainer has since been installed and
        # passed its Windows canary, and this text outlived that fact unnoticed
        # because a too-short readiness timeout kept the card from ever
        # rendering its live states.
        "reason": "No usable shared Windows worker endpoint is configured, so the pinned LoRA trainer cannot be reached.",
        "blocker_code": "lora_runtime_not_proven",
    },
    {
        "method": "pulid_flux2",
        "label": "PuLID for FLUX.2",
        "state": "blocked",
        "reason": (
            "The published adapter is 4096-wide with incompatible load keys; "
            "Klein 4B needs a trained, licensed 3072-wide checkpoint."
        ),
        "blocker_code": "pulid_checkpoint_incompatible",
    },
)


def protocol_cell_specs(protocol_id: str) -> tuple[CellSpec, ...]:
    if protocol_id != SUPPORTED_PROTOCOL_ID:
        raise ValueError("unsupported identity protocol")
    return COMPARISON_CELL_SPECS

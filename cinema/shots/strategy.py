"""Generation-promise types for per-shot identity conditioning (P1-1, spec §3d).

The router (cinema/shots/controller.py::_resolve_identity_strategy) emits one
IdentityStrategy per keyframe take BEFORE generation; the validator and the
capability scorecard hold generation accountable to it. Only tags whose
mechanism is implemented are ever emitted: PRIMARY_ONLY, KONTEXT_MULTI_CHAR,
NO_IDENTITY_ASSET. The MAX_TIER_* tags were retired with the max image-gen
tier (WS1); the per-character LoRA fields below are kept dormant for the
future FLUX.2 A/B (WS3).
"""
from dataclasses import dataclass, field
from typing import List, Optional

PRIMARY_ONLY = "PRIMARY_ONLY"
KONTEXT_MULTI_CHAR = "KONTEXT_MULTI_CHAR"
NO_IDENTITY_ASSET = "NO_IDENTITY_ASSET"


@dataclass(frozen=True)
class CharIdentitySpec:
    char_id: str
    reference: str
    identity_anchor: str = ""
    fidelity: str = "reference"  # router emits "reference" only (max tier retired, WS1)
    # V-5: angle refs ride the spec through to_dict() -> generate_ai_broll ->
    # the slot allocator; a tuple (not list) keeps the frozen dataclass hashable.
    multi_angle_refs: tuple = ()
    # P1-1 slice 2 (§3b): per-char LoRA assets — formerly populated on the max
    # tier for registered-LoRA secondaries (retired WS1). The router now leaves
    # them None on every spec; kept dormant for the future FLUX.2 A/B (WS3).
    lora_path: Optional[str] = None
    lora_strength: Optional[float] = None
    # The PRIMARY's trigger rides IdentityStrategy.char_lora_trigger (the
    # char_lora_* naming convention there); this field is the per-SECONDARY
    # mirror.
    trigger: Optional[str] = None

    def to_dict(self) -> dict:
        return {"char_id": self.char_id, "reference": self.reference,
                "identity_anchor": self.identity_anchor, "fidelity": self.fidelity,
                "multi_angle_refs": list(self.multi_angle_refs),
                "lora_path": self.lora_path, "lora_strength": self.lora_strength,
                "trigger": self.trigger}


@dataclass
class IdentityStrategy:
    mechanism_tag: str
    primary_char_id: str = ""
    char_lora_path: Optional[str] = None
    char_lora_strength: Optional[float] = None
    conditioned_chars: List[CharIdentitySpec] = field(default_factory=list)
    unconditioned_chars: List[str] = field(default_factory=list)
    char_lora_trigger: Optional[str] = None

    @property
    def secondary_specs(self) -> List[CharIdentitySpec]:
        return [c for c in self.conditioned_chars if c.char_id != self.primary_char_id]

    def to_metadata_dict(self) -> dict:
        return {
            "mechanism_tag": self.mechanism_tag,
            "primary_char_id": self.primary_char_id,
            "conditioned_chars": [c.to_dict() for c in self.conditioned_chars],
            "unconditioned_chars": list(self.unconditioned_chars),
        }

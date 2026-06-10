"""Generation-promise types for per-shot identity conditioning (P1-1, spec §3d).

The router (cinema/shots/controller.py::_resolve_identity_strategy) emits one
IdentityStrategy per keyframe take BEFORE generation; the validator and the
capability scorecard hold generation accountable to it. Only tags whose
mechanism is implemented are ever emitted (slice 1: the four below; slice 2
adds MAX_TIER_MULTI_LORA / MAX_TIER_DUAL_PULID).
"""
from dataclasses import dataclass, field
from typing import List, Optional

PRIMARY_ONLY = "PRIMARY_ONLY"
KONTEXT_MULTI_CHAR = "KONTEXT_MULTI_CHAR"
MAX_TIER_PRIMARY_ONLY = "MAX_TIER_PRIMARY_ONLY"
NO_IDENTITY_ASSET = "NO_IDENTITY_ASSET"


@dataclass(frozen=True)
class CharIdentitySpec:
    char_id: str
    reference: str
    identity_anchor: str = ""
    fidelity: str = "reference"  # slice 1: reference | pulid; slice 2 adds lora
    # V-5: angle refs ride the spec through to_dict() -> generate_ai_broll ->
    # the slot allocator; a tuple (not list) keeps the frozen dataclass hashable.
    multi_angle_refs: tuple = ()

    def to_dict(self) -> dict:
        return {"char_id": self.char_id, "reference": self.reference,
                "identity_anchor": self.identity_anchor, "fidelity": self.fidelity,
                "multi_angle_refs": list(self.multi_angle_refs)}


@dataclass
class IdentityStrategy:
    mechanism_tag: str
    primary_char_id: str = ""
    char_lora_path: Optional[str] = None
    char_lora_strength: Optional[float] = None
    conditioned_chars: List[CharIdentitySpec] = field(default_factory=list)
    unconditioned_chars: List[str] = field(default_factory=list)

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

"""Provider-neutral generation promises for per-shot identity references."""
from dataclasses import dataclass, field
from typing import List

REFERENCE_PRIMARY_ONLY = "REFERENCE_PRIMARY_ONLY"
REFERENCE_MULTI_CHAR = "REFERENCE_MULTI_CHAR"
NO_IDENTITY_ASSET = "NO_IDENTITY_ASSET"


@dataclass(frozen=True)
class CharIdentitySpec:
    char_id: str
    reference: str
    identity_anchor: str = ""
    fidelity: str = "reference"
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

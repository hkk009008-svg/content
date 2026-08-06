"""Provider-neutral generation promises for per-shot identity references."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

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


@dataclass(frozen=True)
class Flux2ReferenceAllocation:
    """The exact local FLUX.2 character/continuity reference allocation.

    ``conditioned_chars`` contains only characters which own at least one path
    in ``reference_paths``.  Each retained ``CharIdentitySpec`` is rewritten to
    contain exactly the selected paths for that character, so persisted
    identity metadata and the graph input list cannot describe different
    conditioning promises.
    """

    reference_paths: tuple[str, ...] = ()
    conditioned_chars: tuple[CharIdentitySpec, ...] = ()
    continuity_reference: str = ""


def allocate_flux2_references(
    *,
    primary: Optional[CharIdentitySpec],
    secondaries: Sequence[CharIdentitySpec] = (),
    continuity_reference: object = None,
    cap: int = 4,
) -> Flux2ReferenceAllocation:
    """Select the exact regular files supplied to the local FLUX.2 graph.

    Precedence is fixed and provider-owned: primary canonical, primary angles,
    each in-frame secondary in caller order (canonical then angles), then the
    optional approved continuity reference.  Paths are canonicalized before
    global deduplication, symlinks/non-files are ignored, and selection stops
    at ``cap``.  This mirrors the final regular-file/uniqueness contract in
    :mod:`performance.flux2_klein` while making allocation reusable by both
    the identity router and graph dispatcher.
    """

    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError("FLUX.2 reference cap must be a positive integer")

    selected: list[str] = []
    seen: set[str] = set()

    def _select(value: object) -> str:
        if not isinstance(value, (str, Path)) or not str(value):
            return ""
        path = Path(value)
        try:
            if path.is_symlink() or not path.is_file():
                return ""
            canonical = str(path.resolve(strict=True))
        except OSError:
            return ""
        if canonical in seen:
            return ""
        seen.add(canonical)
        selected.append(canonical)
        return canonical

    conditioned: list[CharIdentitySpec] = []
    claimed_characters: set[str] = set()
    specs: Iterable[CharIdentitySpec] = (
        (() if primary is None else (primary,)) + tuple(secondaries)
    )
    for spec in specs:
        if len(selected) >= cap:
            break
        if not isinstance(spec, CharIdentitySpec) or not spec.char_id:
            continue
        # A malformed duplicate character record must not consume a second
        # identity allocation or create duplicate metadata entries.
        if spec.char_id in claimed_characters:
            continue
        chosen: list[str] = []
        for candidate in (spec.reference, *spec.multi_angle_refs):
            if len(selected) >= cap:
                break
            canonical = _select(candidate)
            if canonical:
                chosen.append(canonical)
        if chosen:
            claimed_characters.add(spec.char_id)
            conditioned.append(CharIdentitySpec(
                char_id=spec.char_id,
                reference=chosen[0],
                identity_anchor=spec.identity_anchor,
                fidelity=spec.fidelity,
                multi_angle_refs=tuple(chosen[1:]),
            ))

    selected_continuity = ""
    if len(selected) < cap:
        selected_continuity = _select(continuity_reference)

    return Flux2ReferenceAllocation(
        reference_paths=tuple(selected),
        conditioned_chars=tuple(conditioned),
        continuity_reference=selected_continuity,
    )


@dataclass
class IdentityStrategy:
    mechanism_tag: str
    primary_char_id: str = ""
    conditioned_chars: List[CharIdentitySpec] = field(default_factory=list)
    unconditioned_chars: List[str] = field(default_factory=list)
    # Local-only execution detail. It is empty for Gemini, preserving that
    # provider's metadata and routing semantics.
    flux2_reference_paths: tuple[str, ...] = ()
    flux2_continuity_reference: str = ""

    @property
    def secondary_specs(self) -> List[CharIdentitySpec]:
        return [c for c in self.conditioned_chars if c.char_id != self.primary_char_id]

    def to_metadata_dict(self) -> dict:
        metadata = {
            "mechanism_tag": self.mechanism_tag,
            "primary_char_id": self.primary_char_id,
            "conditioned_chars": [c.to_dict() for c in self.conditioned_chars],
            "unconditioned_chars": list(self.unconditioned_chars),
        }
        if self.flux2_reference_paths:
            metadata["flux2_reference_paths"] = list(self.flux2_reference_paths)
            metadata["flux2_continuity_reference"] = (
                self.flux2_continuity_reference or None
            )
        return metadata

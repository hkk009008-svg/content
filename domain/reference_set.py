"""The reference set a subject carries, and how it projects onto legacy fields.

WHY THIS EXISTS
---------------
This is a cinema pipeline: every still exists to become a shot, and video models
COPY identity from the references they are handed rather than inventing it. The
reference SET is therefore the identity lever.

Three problems in the record made that impossible to manage:

1. `multi_angle_refs` is the only field any provider path reads, it has ONE
   writer (character creation), and no HTTP route can touch it. A photograph
   added later is invisible to every video provider, forever.
2. References carry no labels, so nothing can reason about COVERAGE — which
   angles, expressions and lighting a set contains, and which it lacks.
3. Selection cannot fall back on the identity score. ADR-092: the scorer
   INVERTS RANK off-angle. A real photograph of the subject in profile scores
   0.556 and "fails" the 0.70 gate, while a generated panel the subject
   confirmed is NOT him scored 0.570. Ranking a pool by score returns only
   frontal images and discards exactly the views a turning character needs.

So references need labels, and selection must order by coverage.

THE `origin` DISTINCTION IS THE LESSON, NOT BOOKKEEPING
------------------------------------------------------
`photo`    — a real photograph of the subject.
`derived`  — generated from a source that CONTAINED the requested geometry
             (a lighting variant made from the subject's real profile).
`invented` — generated from a source that did NOT (a "profile" asked of a
             frontal photograph). The model had no information about the side
             of the head and produced a plausible stranger. Measured: the
             subject rejected exactly such a panel, and it had scored HIGHER
             than the one that was him.

An `invented` reference is not a weaker reference. It is a different person,
and feeding one to a video model teaches it the wrong face.

THIS MODULE IS PURE
-------------------
No I/O, no provider calls, no project mutation. It maps a character record to a
labelled set and back, so the ordering and projection rules can be tested
without a filesystem or a network.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence


# Orthogonal facets. Each answers a different question about what a reference
# SHOWS, so a set can be assessed for coverage along each axis independently.
# "unknown" is always permitted: a migrated legacy reference has no labels, and
# guessing them from a filename would be worse than admitting ignorance.
YAW_CLASSES = ("front", "three_quarter", "profile", "back", "unknown")
EXPRESSION_CLASSES = ("neutral", "smile", "speaking", "unknown")
LIGHT_CLASSES = ("studio", "daylight", "low", "unknown")
FRAMING_CLASSES = ("close", "medium", "wide", "unknown")
# "defined" is the canonical of a DESCRIBED character: generated from text, so
# it has no image source at all. It is not `derived` (nothing was edited) and
# certainly not `invented` (there is no ground truth for it to depart from) —
# it IS the ground truth, the panel every later one is measured against. Giving
# it its own kind keeps `derived` meaning exactly one thing: an edit of an image
# that already carried the requested geometry.
ORIGIN_KINDS = ("photo", "defined", "derived", "invented", "unknown")

# A human verdict, because off-angle references cannot be judged by score.
JUDGEMENTS = ("keep", "reject", "unjudged")

# How a character came to exist. The two kinds obey OPPOSITE correctness rules
# for generation, which is why the distinction has to be recorded rather than
# inferred at each call site.
#
# "real"      — a real person. Generation cannot invent a view the source does
#               not contain: asked for a profile from a frontal photograph, the
#               model produced a face the subject rejected, and it scored HIGHER
#               than the panel that was him. Off-angle panels must be generated
#               FROM a photograph at that geometry, or they are a stranger.
# "described" — defined by text. There is no ground truth to violate: panel 1
#               DEFINES the character and every later panel is an edit of it, so
#               self-consistency is the only requirement and generating a
#               profile from the canonical is legitimate.
#
# `domain/character_manager.py` states "Characters REQUIRE real uploaded photos
# (no synthetic generation)" in its module docstring, but that was prose only —
# the actual gate is `if canonical:`, an any-image test, and a description-only
# character already creates and persists with no references at all.
CREATION_KINDS = ("real", "described")

# How the generator's flat panel names map onto the facets. These are the only
# labels the pipeline has ever written (`_ANGLE_CONFIGS` plus the source-derived
# panels), so migration can recover real facets for generated references while
# uploads stay honest at "unknown".
_PANEL_FACETS: dict[str, dict[str, str]] = {
    "angle_45": {"yaw": "three_quarter"},
    "angle_profile": {"yaw": "profile"},
    "angle_back": {"yaw": "back"},
    "expression_smile": {"expression": "smile"},
    "lighting_outdoor": {"light": "daylight"},
    "profile_outdoor": {"yaw": "profile", "light": "daylight"},
    "threequarter_smile": {"yaw": "three_quarter", "expression": "smile"},
}


def _facet(value: Any, allowed: Sequence[str]) -> str:
    return value if isinstance(value, str) and value in allowed else "unknown"


def make_reference(
    path: str,
    *,
    yaw: str = "unknown",
    expression: str = "unknown",
    light: str = "unknown",
    framing: str = "unknown",
    origin: str = "unknown",
    source_path: str = "",
    judged: str = "unjudged",
    reason: str = "",
    roles: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """One labelled reference. Unrecognised facet values become "unknown"."""

    return {
        "path": path,
        "yaw": _facet(yaw, YAW_CLASSES),
        "expression": _facet(expression, EXPRESSION_CLASSES),
        "light": _facet(light, LIGHT_CLASSES),
        "framing": _facet(framing, FRAMING_CLASSES),
        "origin": _facet(origin, ORIGIN_KINDS),
        # For a derived or invented reference, WHICH image it was generated
        # from. This is what makes the distinction auditable rather than a
        # claim: a panel whose source lacks the geometry it depicts is invented.
        "source_path": source_path if isinstance(source_path, str) else "",
        "judged": _facet(judged, JUDGEMENTS),
        "reason": reason if isinstance(reason, str) else "",
        "roles": sorted({r for r in (roles or ()) if isinstance(r, str) and r}),
    }


def infer_creation_kind(character: Mapping[str, Any]) -> str:
    """Best available reading of how an EXISTING character came to exist.

    Migration only. New characters declare their kind at creation; this exists
    because records predate the field.

    Defaults to "real", deliberately. "real" carries the STRICTER generation
    rule — off-angle panels must come from a photograph at that geometry — so a
    wrong guess here refuses a legitimate generation rather than silently
    admitting an invented face into a reference set. The failure that motivated
    this whole model was an invented face nobody could detect by score.
    """

    for path in character.get("reference_images") or []:
        if isinstance(path, str) and path:
            return "real"
    canonical = character.get("canonical_reference")
    if isinstance(canonical, str) and canonical:
        return "real"
    # No image of any kind. Cannot be distinguished from a described character
    # whose canonical was never generated, so take the stricter reading.
    return "real"


def classify_generated_origin(
    creation_kind: str, *, requested_yaw: str, source_yaw: str
) -> str:
    """Decide whether a generated panel is `derived` or `invented`.

    This is the rule the whole two-kind model exists for, and it would have
    caught the failure that started it: a "profile" generated from a FRONTAL
    photograph of a real person is a face the model had no information about.
    The subject looked at that panel and said it was not him — while it scored
    0.570, HIGHER than the panel that was him at 0.539. No automatic check
    based on the image could have separated them; only its PROVENANCE can.

    described: always "derived". Panel 1 defines the character, so there is no
    ground truth for a later panel to contradict. Generating a profile from the
    canonical is exactly how a described character acquires one.

    real: "derived" only when the source already carries the geometry being
    asked for. Changing light or expression at a pose the source shows is an
    edit of a real view. Changing the YAW is not — the side of a head is not
    present in a frontal photograph and cannot be recovered from it.
    """

    if creation_kind == "described":
        # No source image at all: this panel is being generated from text and
        # therefore DEFINES the character rather than editing anything.
        if not source_yaw:
            return "defined"
        return "derived"
    if not source_yaw:
        # A real person, generated from NO source image at all — text only.
        # Nothing about the subject informed it, so it is a stranger by
        # construction. This is stronger than "unknown" and deliberately so:
        # a real character must never acquire a text-generated reference under
        # any label that reads as legitimate.
        return "invented"
    requested = _facet(requested_yaw, YAW_CLASSES)
    source = _facet(source_yaw, YAW_CLASSES)
    if requested == "unknown" or source == "unknown":
        # Cannot establish provenance. Say so rather than assert either way —
        # an unlabelled panel presented as "derived" is the exact laundering
        # this field exists to prevent.
        return "unknown"
    return "derived" if requested == source else "invented"


def consent_conflict(
    creation_kind: str, identity_refs: Sequence[Mapping[str, Any]]
) -> str:
    """Return why a set contradicts its declared kind, or "" if consistent.

    The risk worth guarding is the INVERSE of the obvious one. Training a LoRA
    on synthetic images of a fictional character under a consent flag asserted
    for nobody is harmless — there is no person. The harm runs the other way: a
    REAL person's photograph sitting inside a set declared "described", where
    nothing would prompt anyone to think about biometric consent at all.

    Consent itself is already bound to bytes — the experiment route requires a
    SHA-256 `reference_fingerprint` over the selected references, so a changed
    set forces fresh consent. What that binding cannot see is WHOSE face the
    bytes show. This can, because `origin: photo` records exactly that.
    """

    if creation_kind != "described":
        return ""
    photographs = [
        str(ref.get("path"))
        for ref in identity_refs
        if isinstance(ref, Mapping)
        and ref.get("origin") == "photo"
        and ref.get("judged") != "reject"
    ]
    if not photographs:
        return ""
    return (
        "a character declared 'described' carries real photographs "
        f"({', '.join(sorted(photographs))}); either the kind is wrong or a "
        "real person's images need the consent path for a real subject"
    )


def facets_for_panel(panel_name: str) -> dict[str, str]:
    """Facets implied by a generator panel name, empty for unknown names."""

    return dict(_PANEL_FACETS.get(panel_name, {}))


def synthesize_identity_refs(character: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build a labelled set from the three legacy fields.

    Read-time migration, matching the convention in
    `normalize_project_schema`: records converge on their next save rather than
    needing a bulk script.

    Ordering follows the legacy semantics exactly — canonical, then
    `multi_angle_refs`, then any remaining `reference_images` — so a migrated
    record hands providers the same images in the same order it did before.
    Nothing is reordered here; that is `order_for_coverage`'s job, and it is a
    separate, visible decision.

    Facets are recovered from generator panel names where possible. An upload
    keeps "unknown" rather than a guess: a filename is not evidence of a pose,
    and a wrong label would steer selection worse than an honest absence.
    """

    canonical = character.get("canonical_reference")
    angles = character.get("multi_angle_refs") or []
    uploads = character.get("reference_images") or []

    by_path: dict[str, dict[str, Any]] = {}
    refs: list[dict[str, Any]] = []

    def _add(path: Any, roles: tuple[str, ...]) -> None:
        if not isinstance(path, str) or not path:
            return
        existing = by_path.get(path)
        if existing is not None:
            # One image legitimately holds several roles — the canonical is
            # usually also an upload, and a real photograph can be an angle too.
            # Merging rather than skipping is what keeps the legacy projection a
            # true round trip: `reference_images` is derived from the "upload"
            # role, so dropping it on a second sighting would silently empty it.
            merged = sorted(set(existing["roles"]) | set(roles))
            existing["roles"] = merged
            if existing["origin"] == "unknown" and "upload" in merged:
                existing["origin"] = "photo"
            return
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        facets = facets_for_panel(stem)
        # A generated panel name implies generation; an upload implies a photo.
        # Neither implies `derived` vs `invented` — that needs the source, which
        # legacy records never stored. Left "unknown" rather than assumed.
        origin = "unknown" if facets else ("photo" if "upload" in roles else "unknown")
        ref = make_reference(path, origin=origin, roles=roles, **facets)
        by_path[path] = ref
        refs.append(ref)

    _add(canonical, ("canonical",))
    for path in angles:
        _add(path, ("angle",))
    for path in uploads:
        _add(path, ("upload",))
    return refs


def derive_legacy_fields(
    identity_refs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Project a labelled set back onto the three fields consumers read.

    The legacy fields stay AUTHORITATIVE for readers — 71 read sites across 9
    files — so this projection is rewritten whenever the set changes. Deriving
    is cheap; deleting those fields is not.

    Rejected references are excluded. A reference the subject judged "reject"
    is, in the case that motivated this, a different person's face — it must
    never reach a provider.
    """

    kept = [
        ref for ref in identity_refs
        if isinstance(ref, Mapping)
        and isinstance(ref.get("path"), str)
        and ref.get("path")
        and ref.get("judged") != "reject"
    ]
    paths = [str(ref["path"]) for ref in kept]
    canonical = ""
    for ref in kept:
        if "canonical" in (ref.get("roles") or ()):
            canonical = str(ref["path"])
            break
    if not canonical and paths:
        canonical = paths[0]

    return {
        "canonical_reference": canonical,
        # The canonical leads, exactly once. Slot 0 carries a semantic role:
        # phase_c_ffmpeg uploads `valid_refs[0]` as Kling's FRONTAL image.
        "multi_angle_refs": (
            [canonical] + [p for p in paths if p != canonical] if canonical else paths
        ),
        "reference_images": [
            str(ref["path"]) for ref in kept if "upload" in (ref.get("roles") or ())
        ],
    }


def coverage(identity_refs: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Count kept references per facet value, for gap display.

    This is what the UI shows INSTEAD of a quality score. A set with four
    frontals and no profile is a bad set, and no per-image number reveals that
    — only the distribution does.
    """

    axes = {
        "yaw": YAW_CLASSES,
        "expression": EXPRESSION_CLASSES,
        "light": LIGHT_CLASSES,
        "framing": FRAMING_CLASSES,
    }
    counts = {axis: {value: 0 for value in values} for axis, values in axes.items()}
    for ref in identity_refs:
        if not isinstance(ref, Mapping) or ref.get("judged") == "reject":
            continue
        for axis, values in axes.items():
            value = _facet(ref.get(axis), values)
            counts[axis][value] += 1
    return counts


def order_for_coverage(
    identity_refs: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Order a set so that any prefix is as diverse as possible.

    Every consumer truncates from the front and each uses a different cut — 3,
    4, 6, 8 — so ordering decides what survives. Sorting by identity score would
    fill a three-slot provider with three frontal images and drop the profile,
    because the scorer floors and inverts off-angle (ADR-092). Coverage is
    therefore the sort key and score is not used at all.

    The rules, in order:
      1. the canonical leads, always — slot 0 is Kling's frontal image;
      2. then one reference per unseen YAW, rarest axis first, because a turn is
         the variation a face set most needs and least often has;
      3. then one per unseen expression, then light, then framing;
      4. then everything else, preserving input order;
      5. photographs before generated panels within any tie — a real image of
         the subject is never worse than an edit of one, and a consumer cutting
         at 4 should see only photographs if four exist;
      6. faceless references (yaw "back") last: useful to a video model for hair
         and wardrobe, useless as identity, so they should never displace a face
         from a small budget.
    """

    kept = [
        ref for ref in identity_refs
        if isinstance(ref, Mapping) and ref.get("judged") != "reject"
    ]
    remaining = list(kept)
    ordered: list[dict[str, Any]] = []

    def _take(predicate) -> Optional[dict[str, Any]]:
        for index, ref in enumerate(remaining):
            if predicate(ref):
                return remaining.pop(index)
        return None

    canonical = _take(lambda r: "canonical" in (r.get("roles") or ()))
    if canonical is not None:
        ordered.append(canonical)

    def _faceless(ref: Mapping[str, Any]) -> bool:
        return _facet(ref.get("yaw"), YAW_CLASSES) == "back"

    for axis, values in (
        ("yaw", YAW_CLASSES),
        ("expression", EXPRESSION_CLASSES),
        ("light", LIGHT_CLASSES),
        ("framing", FRAMING_CLASSES),
    ):
        seen = {_facet(ref.get(axis), values) for ref in ordered}
        for value in values:
            if value in seen or value == "unknown":
                continue
            picked = _take(
                lambda r, a=axis, v=value: (
                    _facet(r.get(a), values) == v
                    and not _faceless(r)
                    and r.get("origin") == "photo"
                )
            ) or _take(
                lambda r, a=axis, v=value: (
                    _facet(r.get(a), values) == v and not _faceless(r)
                )
            )
            if picked is not None:
                ordered.append(picked)

    photos = [r for r in remaining if r.get("origin") == "photo" and not _faceless(r)]
    others = [
        r for r in remaining
        if r.get("origin") != "photo" and not _faceless(r)
    ]
    faceless = [r for r in remaining if _faceless(r)]
    return ordered + photos + others + faceless

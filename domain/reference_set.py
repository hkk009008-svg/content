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
ORIGIN_KINDS = ("photo", "derived", "invented", "unknown")

# A human verdict, because off-angle references cannot be judged by score.
JUDGEMENTS = ("keep", "reject", "unjudged")

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

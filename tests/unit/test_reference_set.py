"""The reference-set model: migration, projection, coverage, ordering.

These pin the rules that make a set manageable at all — and in particular the
two that are counter-intuitive:

* SELECTION IS NEVER SCORE-DRIVEN. ADR-092 measured the identity scorer
  inverting rank off-angle: the subject's own real profile photograph scores
  0.556 and "fails" the 0.70 gate, while a generated panel he confirmed is NOT
  him scored 0.570. Ordering a pool by score fills a three-slot provider with
  three frontal images and discards the profile.
* A REJECTED REFERENCE MUST NEVER REACH A PROVIDER. The case that motivated
  this was a panel showing a different person's face.
"""

from __future__ import annotations

from domain.reference_set import (
    coverage,
    derive_legacy_fields,
    facets_for_panel,
    make_reference,
    order_for_coverage,
    synthesize_identity_refs,
)


def _ref(path, **kwargs):
    return make_reference(path, **kwargs)


# --- migration from the legacy fields --------------------------------------


def test_migration_preserves_legacy_order_exactly() -> None:
    """A migrated record must hand providers the same images in the same order.

    Reordering belongs to `order_for_coverage`, which is a separate and visible
    decision. Migration silently changing what a provider receives would make
    every later comparison meaningless.
    """

    character = {
        "canonical_reference": "c/canon.jpg",
        "multi_angle_refs": ["c/canon.jpg", "c/profile.jpg"],
        "reference_images": ["c/upload.jpg"],
    }
    refs = synthesize_identity_refs(character)
    assert [r["path"] for r in refs] == ["c/canon.jpg", "c/profile.jpg", "c/upload.jpg"]


def test_one_image_can_hold_several_roles() -> None:
    """The canonical is usually also an upload, and may also be an angle.

    Dropping the second role silently emptied `reference_images` on the round
    trip, because that field is derived from the "upload" role.
    """

    character = {
        "canonical_reference": "c/a.jpg",
        "multi_angle_refs": ["c/a.jpg"],
        "reference_images": ["c/a.jpg"],
    }
    refs = synthesize_identity_refs(character)
    assert len(refs) == 1
    assert refs[0]["roles"] == ["angle", "canonical", "upload"]


def test_round_trip_reproduces_all_three_legacy_fields() -> None:
    character = {
        "canonical_reference": "c/canon.jpg",
        "multi_angle_refs": ["c/canon.jpg", "c/profile.jpg", "c/wide.jpg"],
        "reference_images": ["c/wide.jpg"],
    }
    derived = derive_legacy_fields(synthesize_identity_refs(character))
    assert derived["canonical_reference"] == character["canonical_reference"]
    assert derived["multi_angle_refs"] == character["multi_angle_refs"]
    assert derived["reference_images"] == character["reference_images"]


def test_generated_panel_names_recover_their_facets() -> None:
    """A generator panel name is evidence of a pose; an upload filename is not."""

    assert facets_for_panel("angle_profile") == {"yaw": "profile"}
    assert facets_for_panel("threequarter_smile") == {
        "yaw": "three_quarter", "expression": "smile",
    }
    assert facets_for_panel("IMG_4021") == {}

    refs = synthesize_identity_refs(
        {"canonical_reference": "", "multi_angle_refs": ["c/angle_profile.jpg"],
         "reference_images": []}
    )
    assert refs[0]["yaw"] == "profile"


def test_an_upload_keeps_unknown_facets_rather_than_a_guess() -> None:
    refs = synthesize_identity_refs(
        {"canonical_reference": "", "multi_angle_refs": [],
         "reference_images": ["c/DSC_0099.jpg"]}
    )
    assert refs[0]["yaw"] == "unknown"
    assert refs[0]["origin"] == "photo"


# --- projection back onto what providers read ------------------------------


def test_a_rejected_reference_never_reaches_a_provider() -> None:
    """The case that motivated this was a different person's face.

    It also scored HIGHER (0.570) than the panel that was the subject (0.539),
    so no automatic filter would have caught it — only the human verdict does.
    """

    refs = [
        _ref("c/canon.jpg", roles=["canonical", "upload"], origin="photo"),
        _ref("c/stranger.jpg", judged="reject", reason="not the subject"),
        _ref("c/profile.jpg", origin="photo"),
    ]
    derived = derive_legacy_fields(refs)
    assert "c/stranger.jpg" not in derived["multi_angle_refs"]
    assert derived["multi_angle_refs"] == ["c/canon.jpg", "c/profile.jpg"]


def test_the_canonical_leads_the_projection_exactly_once() -> None:
    """Slot 0 is Kling's FRONTAL image — phase_c_ffmpeg uploads valid_refs[0]."""

    refs = [
        _ref("c/profile.jpg"),
        _ref("c/canon.jpg", roles=["canonical"]),
        _ref("c/3q.jpg"),
    ]
    derived = derive_legacy_fields(refs)
    assert derived["multi_angle_refs"][0] == "c/canon.jpg"
    assert derived["multi_angle_refs"].count("c/canon.jpg") == 1


# --- coverage and ordering -------------------------------------------------


def test_coverage_counts_only_kept_references() -> None:
    refs = [
        _ref("c/a.jpg", yaw="front"),
        _ref("c/b.jpg", yaw="profile"),
        _ref("c/c.jpg", yaw="profile", judged="reject"),
    ]
    counts = coverage(refs)
    assert counts["yaw"]["front"] == 1
    assert counts["yaw"]["profile"] == 1


def test_ordering_gives_a_three_slot_provider_three_distinct_yaws() -> None:
    """The whole point: every consumer truncates, so a prefix must be diverse.

    Sorted by identity score this would be three frontal images, because the
    scorer floors and inverts off-angle. Coverage ordering puts a turn in front
    of a fourth frontal.
    """

    refs = [
        _ref("c/front_b.jpg", yaw="front", origin="photo"),
        _ref("c/front_c.jpg", yaw="front", origin="photo"),
        _ref("c/canon.jpg", yaw="front", roles=["canonical"], origin="photo"),
        _ref("c/profile.jpg", yaw="profile", origin="photo"),
        _ref("c/3q.jpg", yaw="three_quarter", origin="photo"),
    ]
    ordered = [r["path"] for r in order_for_coverage(refs)]
    assert ordered[0] == "c/canon.jpg"
    assert set(ordered[:3]) == {"c/canon.jpg", "c/profile.jpg", "c/3q.jpg"}


def test_a_faceless_reference_never_displaces_a_face() -> None:
    """`angle_back` helps a video model with hair and wardrobe, not identity.

    On a four-slot provider it must not take a seat from a real view of a face.
    """

    refs = [
        _ref("c/canon.jpg", yaw="front", roles=["canonical"], origin="photo"),
        _ref("c/back.jpg", yaw="back"),
        _ref("c/profile.jpg", yaw="profile", origin="photo"),
    ]
    ordered = [r["path"] for r in order_for_coverage(refs)]
    assert ordered[-1] == "c/back.jpg"


def test_photographs_come_before_generated_panels_at_the_same_yaw() -> None:
    """A real image of the subject is never worse than an edit of one.

    It also keeps `get_identity_reference_paths`, which stops at 4, selecting
    the consented photographs rather than a generated panel.
    """

    refs = [
        _ref("c/canon.jpg", yaw="front", roles=["canonical"], origin="photo"),
        _ref("c/gen_profile.jpg", yaw="profile", origin="derived"),
        _ref("c/real_profile.jpg", yaw="profile", origin="photo"),
    ]
    ordered = [r["path"] for r in order_for_coverage(refs)]
    assert ordered[1] == "c/real_profile.jpg"


def test_ordering_drops_rejected_references_entirely() -> None:
    refs = [
        _ref("c/canon.jpg", roles=["canonical"], origin="photo"),
        _ref("c/stranger.jpg", yaw="profile", judged="reject"),
    ]
    assert [r["path"] for r in order_for_coverage(refs)] == ["c/canon.jpg"]


def test_unrecognised_facet_values_become_unknown_not_an_error() -> None:
    """A record written by a future version must not crash an older reader."""

    ref = make_reference("c/a.jpg", yaw="dutch_angle", origin="hallucinated")
    assert ref["yaw"] == "unknown"
    assert ref["origin"] == "unknown"


# --- read-time migration inside normalize_project_schema -------------------


def _project_with(character: dict) -> dict:
    return {
        "id": "proj_1", "characters": [character], "locations": [],
        "objects": [], "scenes": [], "global_settings": {},
    }


def test_normalize_adds_identity_refs_without_touching_legacy_fields() -> None:
    """Purely additive: 71 read sites still read the legacy fields.

    If migration reordered or rewrote them, every provider would silently
    receive a different set of images on the next load.
    """

    from domain.project_manager import normalize_project_schema

    character = {
        "id": "c1",
        "canonical_reference": "c/canon.jpg",
        "multi_angle_refs": ["c/canon.jpg", "c/profile.jpg"],
        "reference_images": ["c/canon.jpg"],
    }
    project = _project_with(dict(character))
    assert normalize_project_schema(project) is True

    migrated = project["characters"][0]
    assert len(migrated["identity_refs"]) == 2
    assert migrated["multi_angle_refs"] == character["multi_angle_refs"]
    assert migrated["canonical_reference"] == character["canonical_reference"]
    assert migrated["reference_images"] == character["reference_images"]


def test_normalize_is_idempotent_for_identity_refs() -> None:
    """A second load must not re-migrate, or every read would dirty the file."""

    from domain.project_manager import normalize_project_schema

    project = _project_with({
        "id": "c1",
        "canonical_reference": "c/canon.jpg",
        "multi_angle_refs": ["c/canon.jpg"],
        "reference_images": [],
    })
    normalize_project_schema(project)
    before = list(project["characters"][0]["identity_refs"])
    normalize_project_schema(project)
    assert project["characters"][0]["identity_refs"] == before


def test_normalize_leaves_an_existing_set_alone() -> None:
    """A hand-curated set must survive a load untouched.

    Judgements and facet labels are the human's work; regenerating them from
    the legacy fields would silently discard a "reject" verdict and put a
    rejected face back in front of a provider.
    """

    from domain.project_manager import normalize_project_schema

    curated = [make_reference("c/only.jpg", yaw="profile", judged="keep")]
    project = _project_with({
        "id": "c1",
        "canonical_reference": "c/canon.jpg",
        "multi_angle_refs": ["c/canon.jpg", "c/other.jpg"],
        "reference_images": [],
        "identity_refs": curated,
    })
    normalize_project_schema(project)
    assert project["characters"][0]["identity_refs"] == curated


def test_normalize_skips_a_character_with_no_references() -> None:
    from domain.project_manager import normalize_project_schema

    project = _project_with({"id": "c1", "name": "Nobody"})
    normalize_project_schema(project)
    assert "identity_refs" not in project["characters"][0]

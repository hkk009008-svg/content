"""
FIX-REFS — character/location reference-image portable persistence.

Verified defect (live gap in slice 10's own acceptance criterion): character
and location reference images are the same class of project-owned output
that slice 10 made portable for takes, but they got ZERO chokepoint
coverage. create_character_with_images / create_location_with_images stored
ABSOLUTE dst paths into reference_images (+ canonical_reference /
multi_angle_refs / embedding_cache for characters); every reader then called
os.path.exists() on the raw stored string:
  - get_character_embedding      (embedding_cache / canonical_reference)
  - get_reference_image          (canonical_reference / reference_images) --
    the approved identity-reference input
  - get_multi_angle_refs         (multi_angle_refs / ... ) -- the Kling
    subject-binding input
  - get_location_reference       (reference_images)

After an exact repo move (the same failure mode slice 10 fixed for takes),
all four would silently degrade -- identity-reference conditioning, subject
binding, and identity embedding would find nothing, with no error, no log.

Fix mirrors slice 10 exactly:
  - WRITE side: persist project-relative, via
    domain.character_manager._to_project_relative /
    domain.location_manager._to_project_relative -- each a thin delegating
    wrapper around the ONE implementation, ShotController._to_project_relative.
  - READ side: every reader resolves through
    domain.character_manager._resolve_stored_media_path /
    domain.location_manager._resolve_stored_media_path -- each a thin
    delegating wrapper around the ONE implementation,
    ShotController._resolve_stored_media_path. Reuse shape: module-level
    duck-typed shim (mirrors cinema.screening._resolve_manifest_media_path,
    NOT ReviewController's bound-self-alike shape -- character_manager /
    location_manager are plain module-level functions with no controller
    ``self`` exposing a matching .project/.project_dir surface).

RED->GREEN: every test in TestCharacterSurvivesProjectRootRelocation /
TestLocationSurvivesProjectRootRelocation fails against the pre-fix readers
(raw os.path.exists on an un-rejoined relative string, or on a stale
absolute string after the directory move) -- see
docs/HANDOFF or the FIX-REFS commit message for the captured RED output.
They pass once the write side persists project-relative and the read side
resolves through the migration chokepoint.
"""

import json
import os
import shutil

import numpy as np
import pytest

import domain.character_manager as character_manager
import domain.location_manager as location_manager
import domain.project_manager as project_manager
from domain.character_manager import (
    create_character_with_images,
    get_character_embedding,
    get_multi_angle_refs,
    get_reference_image,
)
from domain.location_manager import create_location_with_images, get_location_reference
from domain.project_manager import load_project

FAKE_EMBEDDING = np.array([0.1, 0.2, 0.3], dtype=np.float32)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _empty_project(pid: str) -> dict:
    """Minimal valid Project dict -- Pydantic validation needs id; the
    others default via Field(default_factory=list) but every existing
    fixture in this repo (test_character_manager_voice_assignment.py,
    test_character_registration_single_face.py) spells them out, so this
    mirrors that convention."""
    return {
        "id": pid,
        "characters": [],
        "locations": [],
        "scenes": [],
        "objects": [],
    }


def _make_upload(tmp_path, name: str = "upload.jpg") -> str:
    """A tiny real file standing in for a user-uploaded reference photo.
    DeepFace is mocked out (see deterministic_character_creation), so its
    actual bytes never matter -- only that os.path.exists(src) is True so
    create_character_with_images's copy step fires."""
    src = tmp_path / name
    src.write_bytes(b"fake photo bytes")
    return str(src)


@pytest.fixture()
def deterministic_character_creation(monkeypatch):
    """Disable DeepFace/FAL network calls while keeping every branch of
    create_character_with_images that touches reference/canonical/
    multi-angle/embedding paths on a deterministic, fully offline path --
    so reference_images, canonical_reference, multi_angle_refs, AND
    embedding_cache all get populated through the REAL production control
    flow (not stubbed out) for the write-side / move-root tests to
    exercise. FAL disabled means _generate_multi_angle_refs short-circuits
    to [canonical_path] (single-element list) -- sufficient to exercise the
    list-comprehension write/read logic without a network call."""
    monkeypatch.setattr(character_manager, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(character_manager, "FAL_AVAILABLE", False)
    monkeypatch.setattr(character_manager, "_has_detectable_face", lambda p: True)
    monkeypatch.setattr(character_manager, "_count_faces", lambda p: 1)
    monkeypatch.setattr(
        character_manager, "compute_face_embedding", lambda p: FAKE_EMBEDDING
    )


def _seed_project_on_disk(pid: str) -> dict:
    """Write project.json under the CURRENT (monkeypatched)
    domain.project_manager.PROJECTS_DIR so add_character/add_location's
    real mutate_project -> disk-load/-save chain has something to load.
    Mirrors tests/unit/test_cross_controller.py's _project_on_disk
    technique (there, a context manager; here, PROJECTS_DIR is already
    patched by the caller's fixture so a plain write suffices)."""
    project = _empty_project(pid)
    project_dir = project_manager.get_project_dir(pid)
    os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, "project.json"), "w", encoding="utf-8") as f:
        json.dump(project, f)
    return project


@pytest.fixture()
def projects_root(tmp_path, monkeypatch):
    """Point domain.project_manager.PROJECTS_DIR at a tmp root so
    add_character/add_location's real mutate_project -> disk-load/-save
    chain never touches the repo's own domain/projects/. get_project_dir
    (used internally by character_manager/location_manager for
    _char_dir/_loc_dir and the new write/read helpers) and
    mutate_project/_load_expected_project_unlocked (used by
    add_character/add_location) both read this SAME module attribute at
    call time -- patching it here is the single lever that redirects the
    whole write chain, exactly like test_cross_controller.py's
    ``dpm.PROJECTS_DIR = fake_root``."""
    root = tmp_path / "projects"
    os.makedirs(root, exist_ok=True)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(root))
    return root


# ---------------------------------------------------------------------------
# WRITE side: create_character_with_images / create_location_with_images
# persist project-relative paths (Product invariant #6).
# ---------------------------------------------------------------------------

class TestCharacterWriteSidePersistsRelative:
    def test_persists_relative_paths_for_every_field(
        self, tmp_path, projects_root, deterministic_character_creation
    ):
        pid = "proj_char_write"
        project = _seed_project_on_disk(pid)
        upload = _make_upload(tmp_path)

        char = create_character_with_images(
            project, "Test Char", "a person", reference_image_paths=[upload],
        )

        assert char["reference_images"], "expected at least one stored reference"
        for p in char["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"

        assert char["canonical_reference"]
        assert not os.path.isabs(char["canonical_reference"])

        assert char["multi_angle_refs"]
        for p in char["multi_angle_refs"]:
            assert not os.path.isabs(p), f"multi_angle_refs entry not relative: {p!r}"

        assert char["embedding_cache"]
        assert not os.path.isabs(char["embedding_cache"])


class TestLocationWriteSidePersistsRelative:
    def test_persists_relative_reference_images(self, tmp_path, projects_root):
        pid = "proj_loc_write"
        project = _seed_project_on_disk(pid)
        upload = _make_upload(tmp_path, "loc_upload.jpg")

        loc = create_location_with_images(
            project, "Test Loc", "a place", reference_image_paths=[upload],
        )

        assert loc["reference_images"]
        for p in loc["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"


# ---------------------------------------------------------------------------
# Move-root simulation (the RED->GREEN core): write under dir A, physically
# relocate the ENTIRE projects root to dir B (every file, including
# project.json, moves together -- an exact repo move), reload from disk
# under the NEW root, and verify every downstream reader still resolves.
# ---------------------------------------------------------------------------

class TestCharacterSurvivesProjectRootRelocation:
    """A character created under dir A, whose project directory (and every
    file under it) is then physically relocated to dir B, must still
    resolve for every downstream consumer -- identity conditioning,
    multi-angle subject binding, and identity embedding -- exactly as it
    did before the move.

    Pre-fix, this fails: reference_images / canonical_reference /
    multi_angle_refs / embedding_cache were stored ABSOLUTE (rooted at dir
    A); every reader called os.path.exists() on that raw stale string,
    which silently returns False once dir A no longer exists.
    """

    def test_reference_embedding_multiangle_all_resolve_after_move(
        self, tmp_path, monkeypatch, deterministic_character_creation
    ):
        pid = "proj_char_move"
        root_a = tmp_path / "root_a" / "projects"
        root_b = tmp_path / "root_b" / "projects"
        os.makedirs(root_a, exist_ok=True)
        monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(root_a))

        project = _seed_project_on_disk(pid)
        upload = _make_upload(tmp_path)

        char = create_character_with_images(
            project, "Move Char", "a person", reference_image_paths=[upload],
        )
        cid = char["id"]

        # Sanity: pre-move, the persisted fields are relative (write-side
        # fix) -- confirms the assertions below actually exercise the
        # relative-join branch after the move, not a no-op on an
        # already-absolute string that happens to still exist.
        assert not os.path.isabs(char["canonical_reference"])
        assert not os.path.isabs(char["reference_images"][0])
        assert not os.path.isabs(char["multi_angle_refs"][0])
        assert not os.path.isabs(char["embedding_cache"])

        # Relocate the ENTIRE projects root -- simulates an exact repo move
        # (every file under it, including project.json, moves together).
        os.makedirs(root_b.parent, exist_ok=True)
        shutil.move(str(root_a), str(root_b))
        monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(root_b))

        # Reload from disk under the NEW root -- proves the persisted JSON
        # (not just the in-memory dict mutate_project happened to sync)
        # survives the move.
        reloaded = load_project(pid)
        assert reloaded is not None

        ref_img = get_reference_image(reloaded, cid)
        assert ref_img is not None, "identity reference did not resolve after move"
        assert os.path.isabs(ref_img) and os.path.exists(ref_img)
        assert ref_img.startswith(str(root_b))

        angles = get_multi_angle_refs(reloaded, cid)
        assert angles, "Kling multi-angle refs did not resolve after move"
        for a in angles:
            assert os.path.isabs(a) and os.path.exists(a)
            assert a.startswith(str(root_b))

        embedding = get_character_embedding(reloaded, cid)
        assert embedding is not None, "identity embedding did not resolve after move"
        assert np.allclose(embedding, FAKE_EMBEDDING)


class TestLocationSurvivesProjectRootRelocation:
    def test_location_reference_resolves_after_move(self, tmp_path, monkeypatch):
        pid = "proj_loc_move"
        root_a = tmp_path / "root_a" / "projects"
        root_b = tmp_path / "root_b" / "projects"
        os.makedirs(root_a, exist_ok=True)
        monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(root_a))

        project = _seed_project_on_disk(pid)
        upload = _make_upload(tmp_path, "loc_upload.jpg")

        loc = create_location_with_images(
            project, "Move Loc", "a place", reference_image_paths=[upload],
        )
        lid = loc["id"]
        assert not os.path.isabs(loc["reference_images"][0])

        os.makedirs(root_b.parent, exist_ok=True)
        shutil.move(str(root_a), str(root_b))
        monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(root_b))

        reloaded = load_project(pid)
        assert reloaded is not None

        ref = get_location_reference(reloaded, lid)
        assert ref is not None, "location reference did not resolve after move"
        assert os.path.isabs(ref) and os.path.exists(ref)
        assert ref.startswith(str(root_b))


# ---------------------------------------------------------------------------
# Legacy-absolute paths (pre-fix / pre-slice-10 data) must keep working --
# both unchanged-location (trivial passthrough) and moved (pid-anchor
# suffix re-root), mirroring
# test_api_serve_file.py::test_api_serve_file_move_root_migrates_legacy_absolute_path.
# ---------------------------------------------------------------------------

class TestLegacyAbsolutePathsStillResolve:
    def test_character_legacy_absolute_unmoved_still_resolves(self, tmp_path, monkeypatch):
        pid = "proj_legacy_char_unmoved"
        project_dir = tmp_path / "projects" / pid
        char_dir = project_dir / "characters" / "char_legacy"
        char_dir.mkdir(parents=True)
        ref_file = char_dir / "canonical.jpg"
        ref_file.write_bytes(b"legacy bytes")

        monkeypatch.setattr(character_manager, "get_project_dir", lambda p: str(project_dir))

        project = {
            "id": pid,
            "characters": [{
                "id": "char_legacy",
                "name": "Legacy",
                "reference_images": [str(ref_file)],
                "canonical_reference": str(ref_file),
                "multi_angle_refs": [str(ref_file)],
                "embedding_cache": "",
            }],
            "locations": [], "scenes": [], "objects": [],
        }

        result = get_reference_image(project, "char_legacy")
        assert result == str(ref_file)
        assert os.path.exists(result)

    def test_character_legacy_absolute_migrates_after_move(self, tmp_path, monkeypatch):
        """The pre-fix-era absolute path (rooted at a directory that no
        longer exists) is re-rooted under the CURRENT project directory via
        the pid-anchor suffix migration."""
        pid = "proj_legacy_char_moved"
        old_root = tmp_path / "old_location"
        new_root = tmp_path / "new_location_after_move"
        rel = os.path.join("characters", "char_legacy", "canonical.jpg")

        new_project_dir = new_root / pid
        (new_project_dir / "characters" / "char_legacy").mkdir(parents=True)
        (new_project_dir / "characters" / "char_legacy" / "canonical.jpg").write_bytes(
            b"moved bytes"
        )

        # old_root/pid is never created on disk -- the repo (and
        # PROJECTS_DIR under it) moved away from it, so this string is
        # exactly what a pre-move canonical_reference would still hold.
        legacy_absolute_path = str(old_root / pid / rel)

        monkeypatch.setattr(character_manager, "get_project_dir", lambda p: str(new_project_dir))

        project = {
            "id": pid,
            "characters": [{
                "id": "char_legacy",
                "name": "Legacy",
                "reference_images": [legacy_absolute_path],
                "canonical_reference": legacy_absolute_path,
                "multi_angle_refs": [],
                "embedding_cache": "",
            }],
            "locations": [], "scenes": [], "objects": [],
        }

        result = get_reference_image(project, "char_legacy")
        assert result == str(new_project_dir / rel)
        assert os.path.exists(result)

    def test_location_legacy_absolute_unmoved_still_resolves(self, tmp_path, monkeypatch):
        pid = "proj_legacy_loc_unmoved"
        project_dir = tmp_path / "projects" / pid
        loc_dir = project_dir / "locations" / "loc_legacy"
        loc_dir.mkdir(parents=True)
        ref_file = loc_dir / "ref_0.jpg"
        ref_file.write_bytes(b"legacy bytes")

        monkeypatch.setattr(location_manager, "get_project_dir", lambda p: str(project_dir))

        project = {
            "id": pid,
            "locations": [{
                "id": "loc_legacy", "name": "Legacy Loc",
                "reference_images": [str(ref_file)],
            }],
            "characters": [], "scenes": [], "objects": [],
        }

        result = get_location_reference(project, "loc_legacy")
        assert result == str(ref_file)
        assert os.path.exists(result)

    def test_location_legacy_absolute_migrates_after_move(self, tmp_path, monkeypatch):
        pid = "proj_legacy_loc_moved"
        old_root = tmp_path / "old_location"
        new_root = tmp_path / "new_location_after_move"
        rel = os.path.join("locations", "loc_legacy", "ref_0.jpg")

        new_project_dir = new_root / pid
        (new_project_dir / "locations" / "loc_legacy").mkdir(parents=True)
        (new_project_dir / "locations" / "loc_legacy" / "ref_0.jpg").write_bytes(
            b"moved bytes"
        )

        legacy_absolute_path = str(old_root / pid / rel)

        monkeypatch.setattr(location_manager, "get_project_dir", lambda p: str(new_project_dir))

        project = {
            "id": pid,
            "locations": [{
                "id": "loc_legacy", "name": "Legacy Loc",
                "reference_images": [legacy_absolute_path],
            }],
            "characters": [], "scenes": [], "objects": [],
        }

        result = get_location_reference(project, "loc_legacy")
        assert result == str(new_project_dir / rel)
        assert os.path.exists(result)


# ---------------------------------------------------------------------------
# A genuinely missing file must still report missing -- the fix must not
# fabricate a path that doesn't exist, nor raise.
# ---------------------------------------------------------------------------

class TestGenuinelyMissingFileReportsMissing:
    def test_character_readers_return_empty_when_genuinely_missing(self, tmp_path, monkeypatch):
        pid = "proj_char_missing"
        project_dir = tmp_path / "projects" / pid  # never created on disk
        monkeypatch.setattr(character_manager, "get_project_dir", lambda p: str(project_dir))

        project = {
            "id": pid,
            "characters": [{
                "id": "char_missing",
                "name": "Missing",
                "reference_images": [os.path.join("characters", "char_missing", "ref_0.jpg")],
                "canonical_reference": "",
                "multi_angle_refs": [],
                "embedding_cache": "",
            }],
            "locations": [], "scenes": [], "objects": [],
        }

        assert get_reference_image(project, "char_missing") is None
        assert get_character_embedding(project, "char_missing") is None
        assert get_multi_angle_refs(project, "char_missing") == []

    def test_location_reader_returns_none_when_genuinely_missing(self, tmp_path, monkeypatch):
        pid = "proj_loc_missing"
        project_dir = tmp_path / "projects" / pid  # never created on disk
        monkeypatch.setattr(location_manager, "get_project_dir", lambda p: str(project_dir))

        project = {
            "id": pid,
            "locations": [{
                "id": "loc_missing",
                "name": "Missing",
                "reference_images": [os.path.join("locations", "loc_missing", "ref_0.jpg")],
            }],
            "characters": [], "scenes": [], "objects": [],
        }

        assert get_location_reference(project, "loc_missing") is None


# ---------------------------------------------------------------------------
# Direct unit coverage of the two migration helpers, isolated from the
# higher-level character/location flows above.
# ---------------------------------------------------------------------------

class TestToProjectRelativeHelper:
    def test_character_helper_relativizes_path_under_project_dir(self, tmp_path):
        project_dir = str(tmp_path / "proj")
        abs_path = os.path.join(project_dir, "characters", "c1", "ref_0.jpg")
        result = character_manager._to_project_relative(project_dir, abs_path)
        assert result == os.path.join("characters", "c1", "ref_0.jpg")
        assert not os.path.isabs(result)

    def test_character_helper_passthrough_for_empty_or_relative(self, tmp_path):
        project_dir = str(tmp_path / "proj")
        assert character_manager._to_project_relative(project_dir, "") == ""
        assert (
            character_manager._to_project_relative(project_dir, "already/relative.jpg")
            == "already/relative.jpg"
        )

    def test_location_helper_relativizes_path_under_project_dir(self, tmp_path):
        project_dir = str(tmp_path / "proj")
        abs_path = os.path.join(project_dir, "locations", "l1", "ref_0.jpg")
        result = location_manager._to_project_relative(project_dir, abs_path)
        assert result == os.path.join("locations", "l1", "ref_0.jpg")
        assert not os.path.isabs(result)


class TestResolveStoredMediaPathHelper:
    def test_character_helper_joins_relative_onto_current_project_dir(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "proj"
        (project_dir / "characters" / "c1").mkdir(parents=True)
        (project_dir / "characters" / "c1" / "ref_0.jpg").write_bytes(b"x")
        monkeypatch.setattr(character_manager, "get_project_dir", lambda p: str(project_dir))

        result = character_manager._resolve_stored_media_path(
            {"id": "proj1"}, os.path.join("characters", "c1", "ref_0.jpg")
        )
        assert result == str(project_dir / "characters" / "c1" / "ref_0.jpg")
        assert os.path.exists(result)

    def test_character_helper_empty_stored_path_passthrough(self):
        assert character_manager._resolve_stored_media_path({"id": "p"}, "") == ""

    def test_character_helper_missing_project_id_passthrough(self):
        assert (
            character_manager._resolve_stored_media_path({}, "some/rel/path.jpg")
            == "some/rel/path.jpg"
        )

    def test_location_helper_joins_relative_onto_current_project_dir(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "proj"
        (project_dir / "locations" / "l1").mkdir(parents=True)
        (project_dir / "locations" / "l1" / "ref_0.jpg").write_bytes(b"x")
        monkeypatch.setattr(location_manager, "get_project_dir", lambda p: str(project_dir))

        result = location_manager._resolve_stored_media_path(
            {"id": "proj1"}, os.path.join("locations", "l1", "ref_0.jpg")
        )
        assert result == str(project_dir / "locations" / "l1" / "ref_0.jpg")
        assert os.path.exists(result)

"""
FIX-REFWRITE — portable reference-image WRITES in the HTTP layer.

Verified gap (disclosed by the slice that landed the read side, commit
29c52b49 "fix(media): portable reference images for characters and
locations"): four web_server.py endpoints persisted ABSOLUTE reference-image
/ canonical-reference paths straight from the multipart save() call, even
though every downstream reader already resolves through a migration
chokepoint that accepts BOTH a project-relative value (the current
persistence shape) and a legacy absolute path:

  - api_update_character  (PUT  /api/projects/<pid>/characters/<cid>)
  - api_add_object        (POST /api/projects/<pid>/objects)
  - api_update_object     (PUT  /api/projects/<pid>/objects/<oid>)
  - api_update_location   (PUT  /api/projects/<pid>/locations/<lid>)

create_character_with_images / create_location_with_images (the CREATE path
for characters/locations, called by api_add_character / api_add_location)
already relativize on write. These four endpoints were the remaining write
sites: all four build reference_images/canonical_reference directly from a
raw multipart save() call in web_server.py rather than going through those
domain-layer factories, so they kept the pre-slice-10-style absolute
persistence -- an exact repo move would silently strand any image added via
these endpoints, even though the read side was already fixed and the create
endpoints were already fixed.

Fix: relativize on write using the SAME single implementation the domain
layer already uses -- domain.character_manager._to_project_relative, a thin
duck-typed-shim wrapper delegating to the ONE implementation,
ShotController._to_project_relative. web_server.py imports and calls this
function directly at each of the four write sites; no logic is
re-implemented.

RED->GREEN: every test in Test*WriteSidePersistsRelative and
TestSurvivesProjectRootRelocation fails against the pre-fix endpoints (the
raw absolute save-path lands straight in reference_images /
canonical_reference, so `not os.path.isabs(...)` is False, and the
move-root reader lookups return None) -- captured RED output in the
FIX-REFWRITE implementer report. They pass once each endpoint relativizes
before persisting.
"""

import io
import json
import os
import shutil

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    import web_server
    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as c:
        yield c


def _new_project(name: str) -> str:
    from domain import project_manager as pm
    return pm.create_project(name)["id"]


def _seed_character(pid: str) -> str:
    from domain import project_manager as pm
    project = pm.load_project(pid)
    char = pm.make_character("Solo", "a test character")
    pm.add_character(project, char)
    return char["id"]


def _seed_location(pid: str) -> str:
    from domain import project_manager as pm
    project = pm.load_project(pid)
    loc = pm.make_location("Studio", "a test location")
    pm.add_location(project, loc)
    return loc["id"]


def _seed_object(pid: str) -> str:
    from domain import project_manager as pm
    project = pm.load_project(pid)
    obj = pm.make_object("Mug", "a test object")
    pm.add_object(project, obj)
    return obj["id"]


def _record(pid: str, collection: str, item_id: str) -> dict:
    from domain import project_manager as pm
    with pm.project_lock(pid):
        proj = pm._load_project_unlocked(pid)
    return next(x for x in proj[collection] if x["id"] == item_id)


def _upload(name: str = "ref.jpg"):
    return (io.BytesIO(b"fake-jpeg-bytes"), name)


# ---------------------------------------------------------------------------
# WRITE side: each touched endpoint persists project-relative paths (Product
# invariant #6), mirroring create_character_with_images's /
# create_location_with_images's already-fixed create path.
# ---------------------------------------------------------------------------

class TestCharacterUpdateWriteSidePersistsRelative:
    def test_put_reference_image_persists_relative_path(self, client):
        pid = _new_project("proj_char_put")
        cid = _seed_character(pid)

        resp = client.put(
            f"/api/projects/{pid}/characters/{cid}",
            data={"reference_images": _upload("newref.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "characters", cid)
        assert rec["reference_images"], "expected at least one stored reference"
        for p in rec["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"
        assert rec["canonical_reference"]
        assert not os.path.isabs(rec["canonical_reference"])


class TestObjectCreateWriteSidePersistsRelative:
    def test_post_object_with_reference_image_persists_relative_path(self, client):
        pid = _new_project("proj_obj_post")

        resp = client.post(
            f"/api/projects/{pid}/objects",
            data={
                "name": "Test Mug",
                "description": "a mug",
                "reference_images": _upload("mug.jpg"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        oid = json.loads(resp.data)["id"]

        rec = _record(pid, "objects", oid)
        assert rec["reference_images"]
        for p in rec["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"
        assert rec["canonical_reference"]
        assert not os.path.isabs(rec["canonical_reference"])


class TestObjectUpdateWriteSidePersistsRelative:
    def test_put_object_reference_image_persists_relative_path(self, client):
        pid = _new_project("proj_obj_put")
        oid = _seed_object(pid)

        resp = client.put(
            f"/api/projects/{pid}/objects/{oid}",
            data={"reference_images": _upload("mug2.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "objects", oid)
        assert rec["reference_images"]
        for p in rec["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"
        assert rec["canonical_reference"]
        assert not os.path.isabs(rec["canonical_reference"])


class TestLocationUpdateWriteSidePersistsRelative:
    def test_put_location_reference_image_persists_relative_path(self, client):
        pid = _new_project("proj_loc_put")
        lid = _seed_location(pid)

        resp = client.put(
            f"/api/projects/{pid}/locations/{lid}",
            data={"reference_images": _upload("loc.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "locations", lid)
        assert rec["reference_images"]
        for p in rec["reference_images"]:
            assert not os.path.isabs(p), f"reference_images entry not relative: {p!r}"


# ---------------------------------------------------------------------------
# Move-root simulation (the RED->GREEN core): add a reference image via the
# HTTP endpoint under root A, physically relocate the ENTIRE projects root to
# root B (an exact repo move -- every file, including project.json, moves
# together), reload from disk under the NEW root, and verify the
# domain-layer reader still resolves the image the endpoint added.
# ---------------------------------------------------------------------------

class TestSurvivesProjectRootRelocation:
    def test_character_reference_added_via_endpoint_resolves_after_move(
        self, tmp_path, monkeypatch
    ):
        from domain import project_manager as pm

        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        os.makedirs(root_a, exist_ok=True)
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_a), raising=False)

        import web_server
        web_server.app.config["TESTING"] = True
        with web_server.app.test_client() as client:
            pid = _new_project("proj_char_move")
            cid = _seed_character(pid)
            resp = client.put(
                f"/api/projects/{pid}/characters/{cid}",
                data={"reference_images": _upload("moveref.jpg")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 200

        rec = _record(pid, "characters", cid)
        # Sanity: pre-move, the persisted value is relative -- confirms the
        # assertions below exercise the relative-join branch after the move,
        # not a no-op on an already-absolute string that happens to survive.
        assert not os.path.isabs(rec["reference_images"][0])

        os.makedirs(root_b, exist_ok=True)
        shutil.move(str(root_a / pid), str(root_b / pid))
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_b), raising=False)

        from domain.character_manager import get_reference_image
        reloaded = pm.load_project(pid)
        assert reloaded is not None
        ref = get_reference_image(reloaded, cid)
        assert ref is not None, "reference did not resolve after move"
        assert os.path.isabs(ref) and os.path.exists(ref)
        assert ref.startswith(str(root_b))

    def test_location_reference_added_via_endpoint_resolves_after_move(
        self, tmp_path, monkeypatch
    ):
        from domain import project_manager as pm

        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        os.makedirs(root_a, exist_ok=True)
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_a), raising=False)

        import web_server
        web_server.app.config["TESTING"] = True
        with web_server.app.test_client() as client:
            pid = _new_project("proj_loc_move")
            lid = _seed_location(pid)
            resp = client.put(
                f"/api/projects/{pid}/locations/{lid}",
                data={"reference_images": _upload("moveloc.jpg")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 200

        rec = _record(pid, "locations", lid)
        assert not os.path.isabs(rec["reference_images"][0])

        os.makedirs(root_b, exist_ok=True)
        shutil.move(str(root_a / pid), str(root_b / pid))
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_b), raising=False)

        from domain.location_manager import get_location_reference
        reloaded = pm.load_project(pid)
        assert reloaded is not None
        ref = get_location_reference(reloaded, lid)
        assert ref is not None, "reference did not resolve after move"
        assert os.path.isabs(ref) and os.path.exists(ref)
        assert ref.startswith(str(root_b))

    def test_object_reference_added_via_create_endpoint_resolves_after_move(
        self, tmp_path, monkeypatch
    ):
        """Objects have no dedicated reader module yet (no
        domain/object_manager.py) -- resolve manually by joining the stored
        value onto the CURRENT project dir, the same relative-join branch
        _resolve_stored_media_path takes for characters/locations. Proves
        the persisted value is genuinely project-relative and portable, not
        merely string-shaped like one."""
        from domain import project_manager as pm

        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        os.makedirs(root_a, exist_ok=True)
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_a), raising=False)

        import web_server
        web_server.app.config["TESTING"] = True
        with web_server.app.test_client() as client:
            pid = _new_project("proj_obj_move")
            resp = client.post(
                f"/api/projects/{pid}/objects",
                data={
                    "name": "Move Mug",
                    "description": "a mug",
                    "reference_images": _upload("moveobj.jpg"),
                },
                content_type="multipart/form-data",
            )
            assert resp.status_code == 201
            oid = json.loads(resp.data)["id"]

        rec = _record(pid, "objects", oid)
        assert not os.path.isabs(rec["reference_images"][0])
        assert not os.path.isabs(rec["canonical_reference"])

        os.makedirs(root_b, exist_ok=True)
        shutil.move(str(root_a / pid), str(root_b / pid))
        monkeypatch.setattr(pm, "PROJECTS_DIR", str(root_b), raising=False)

        reloaded = pm.load_project(pid)
        assert reloaded is not None
        reloaded_obj = next(o for o in reloaded["objects"] if o["id"] == oid)
        resolved = os.path.join(pm.get_project_dir(pid), reloaded_obj["canonical_reference"])
        assert os.path.exists(resolved)
        assert resolved.startswith(str(root_b))


# ---------------------------------------------------------------------------
# Legacy absolute values already on a record must keep resolving -- a fresh
# relative write from these endpoints must not disturb (or need to migrate)
# a pre-existing legacy absolute entry already on the same record. The
# read-side migration is out of this fix's scope and already shipped; these
# tests confirm the write-side fix doesn't regress it.
# ---------------------------------------------------------------------------

class TestLegacyAbsoluteEntriesSurviveAFreshWrite:
    def test_character_put_leaves_legacy_absolute_canonical_ref_intact_and_resolvable(
        self, client, tmp_path
    ):
        from domain import project_manager as pm
        from domain.character_manager import get_reference_image

        pid = _new_project("proj_char_legacy_mix")
        cid = _seed_character(pid)

        legacy_abs = str(tmp_path / "elsewhere" / "old_upload.jpg")
        os.makedirs(os.path.dirname(legacy_abs), exist_ok=True)
        with open(legacy_abs, "wb") as fh:
            fh.write(b"legacy bytes")

        def _seed_legacy(p):
            for c in p["characters"]:
                if c["id"] == cid:
                    c["canonical_reference"] = legacy_abs
                    return c
            return None
        pm.mutate_project(pid, _seed_legacy)

        resp = client.put(
            f"/api/projects/{pid}/characters/{cid}",
            data={"reference_images": _upload("fresh.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "characters", cid)
        # canonical_reference was already non-empty (legacy) -- the endpoint
        # only fills it in when empty, so it must be left untouched.
        assert rec["canonical_reference"] == legacy_abs
        # the fresh upload still lands in reference_images, relative.
        assert rec["reference_images"]
        assert all(not os.path.isabs(p) for p in rec["reference_images"])

        proj = pm.load_project(pid)
        result = get_reference_image(proj, cid)
        assert result == legacy_abs
        assert os.path.exists(result)

    def test_location_put_leaves_legacy_absolute_ref_intact_and_resolvable(
        self, client, tmp_path
    ):
        from domain import project_manager as pm
        from domain.location_manager import get_location_reference

        pid = _new_project("proj_loc_legacy_mix")
        lid = _seed_location(pid)

        legacy_abs = str(tmp_path / "elsewhere" / "old_loc.jpg")
        os.makedirs(os.path.dirname(legacy_abs), exist_ok=True)
        with open(legacy_abs, "wb") as fh:
            fh.write(b"legacy bytes")

        def _seed_legacy(p):
            for loc in p["locations"]:
                if loc["id"] == lid:
                    loc.setdefault("reference_images", []).append(legacy_abs)
                    return loc
            return None
        pm.mutate_project(pid, _seed_legacy)

        resp = client.put(
            f"/api/projects/{pid}/locations/{lid}",
            data={"reference_images": _upload("fresh_loc.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "locations", lid)
        assert legacy_abs in rec["reference_images"]
        fresh_entries = [p for p in rec["reference_images"] if p != legacy_abs]
        assert fresh_entries and all(not os.path.isabs(p) for p in fresh_entries)

        proj = pm.load_project(pid)
        # get_location_reference returns the first LIST-ORDER entry that
        # resolves -- the legacy entry was seeded first and still exists on
        # disk, so it wins; proves the legacy value still reads correctly.
        result = get_location_reference(proj, lid)
        assert result == legacy_abs
        assert os.path.exists(result)

    def test_object_put_leaves_legacy_absolute_refs_intact(self, client, tmp_path):
        from domain import project_manager as pm

        pid = _new_project("proj_obj_legacy_mix")
        oid = _seed_object(pid)

        legacy_abs = str(tmp_path / "elsewhere" / "old_obj.jpg")
        os.makedirs(os.path.dirname(legacy_abs), exist_ok=True)
        with open(legacy_abs, "wb") as fh:
            fh.write(b"legacy bytes")

        def _seed_legacy(p):
            for o in p.get("objects", []):
                if o["id"] == oid:
                    o["canonical_reference"] = legacy_abs
                    o.setdefault("reference_images", []).append(legacy_abs)
                    return o
            return None
        pm.mutate_project(pid, _seed_legacy)

        resp = client.put(
            f"/api/projects/{pid}/objects/{oid}",
            data={"reference_images": _upload("fresh_obj.jpg")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

        rec = _record(pid, "objects", oid)
        assert rec["canonical_reference"] == legacy_abs, (
            "pre-set canonical_reference must not be overwritten"
        )
        assert legacy_abs in rec["reference_images"]
        fresh_entries = [p for p in rec["reference_images"] if p != legacy_abs]
        assert fresh_entries and all(not os.path.isabs(p) for p in fresh_entries)
        assert os.path.exists(legacy_abs), "legacy file itself must be untouched"

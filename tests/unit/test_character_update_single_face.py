"""A3 single-face enforcement on the PUT path (api_update_character).

The create path (create_character_with_images) rejects multi-face reference
images at registration time.  A reference image arriving via
PUT /api/projects/<pid>/characters/<cid> is the same registration event and
must meet the same contract — without this, the A3 guard is bypassed
entirely (operator Lane V finding, 2026-06-11T21:36:04Z).

Rules under test
----------------
1. PUT with a 2+-face reference image → HTTP 400 with an informative error;
   the saved file is removed and the character record gains NO new refs.
2. PUT with a single-face reference image → HTTP 200; ref appended.
3. DeepFace unavailable → guard skipped (matches the create path's gating).

Mock strategy: patch domain.character_manager._count_faces and
DEEPFACE_AVAILABLE at the module surface — the handler imports them at
call time, so module-level patches take effect.

Offline-only: no real DeepFace, no network.
"""

import io
import json
import os

import pytest
from unittest.mock import patch

import domain.character_manager as cm


@pytest.fixture
def client(tmp_path, monkeypatch):
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    import web_server
    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as c:
        yield c


def _project_with_char():
    from domain import project_manager as pm
    pid = pm.create_project("a3-put-test")["id"]
    char = pm.make_character("Solo", "single-person test character")

    def _add(p):
        p["characters"].append(char)
        return char

    pm.mutate_project(pid, _add)
    return pid, char["id"]


def _put_with_image(client, pid, cid):
    return client.put(
        f"/api/projects/{pid}/characters/{cid}",
        data={
            "name": "Solo",
            "reference_images": (io.BytesIO(b"fake-jpeg-bytes"), "newref.jpg"),
        },
        content_type="multipart/form-data",
    )


def _char_record(pid, cid):
    from domain import project_manager as pm
    with pm.project_lock(pid):
        proj = pm._load_project_unlocked(pid)
    return next(c for c in proj["characters"] if c["id"] == cid)


class TestPutMultiFaceRejected:
    def test_put_two_face_image_returns_400_and_cleans_up(self, client):
        pid, cid = _project_with_char()
        with patch.object(cm, "DEEPFACE_AVAILABLE", True), \
             patch.object(cm, "_count_faces", return_value=2):
            resp = _put_with_image(client, pid, cid)
        assert resp.status_code == 400
        body = json.loads(resp.data)
        assert "2 faces" in body["error"]
        assert "exactly 1" in body["error"]
        # No ref appended; saved file removed.
        rec = _char_record(pid, cid)
        assert rec["reference_images"] == []
        from domain import project_manager as pm
        char_dir = os.path.join(pm._project_dir(pid), "characters", cid)
        assert not os.path.exists(os.path.join(char_dir, "newref.jpg"))


class TestPutSingleFaceAccepted:
    def test_put_single_face_image_appends_ref(self, client):
        pid, cid = _project_with_char()
        with patch.object(cm, "DEEPFACE_AVAILABLE", True), \
             patch.object(cm, "_count_faces", return_value=1):
            resp = _put_with_image(client, pid, cid)
        assert resp.status_code == 200
        rec = _char_record(pid, cid)
        assert len(rec["reference_images"]) == 1
        assert rec["reference_images"][0].endswith("newref.jpg")


class TestPutGuardSkippedWithoutDeepface:
    def test_put_without_deepface_keeps_existing_behavior(self, client):
        pid, cid = _project_with_char()
        with patch.object(cm, "DEEPFACE_AVAILABLE", False), \
             patch.object(cm, "_count_faces", side_effect=AssertionError(
                 "_count_faces must not run when DeepFace unavailable")):
            resp = _put_with_image(client, pid, cid)
        assert resp.status_code == 200
        rec = _char_record(pid, cid)
        assert len(rec["reference_images"]) == 1


class TestPutCollisionDataLoss:
    """bug_001 (cloud ultrareview): a rejected multi-face PUT whose filename
    COLLIDES with an existing reference must NOT destroy that existing valid
    file.  Pre-786d9e9 the overwrite survived on disk (record stayed
    consistent); 786d9e9's os.remove cleanup turned the overwrite into a
    delete + a dangling record.  The fix validates uploads in a staging dir
    BEFORE moving anything into char_dir, so a rejection never touches an
    existing reference.
    """

    def test_rejected_multiface_put_preserves_colliding_existing_ref(self, client):
        from domain import project_manager as pm
        pid, cid = _project_with_char()

        # Seed an EXISTING valid single-face reference at a known filename and
        # register it on the record (simulating a prior successful PUT).
        char_dir = os.path.join(pm._project_dir(pid), "characters", cid)
        os.makedirs(char_dir, exist_ok=True)
        existing = os.path.join(char_dir, "headshot.jpg")
        with open(existing, "wb") as fh:
            fh.write(b"ORIGINAL-VALID-SINGLE-FACE-BYTES")

        def _add_ref(p):
            for c in p["characters"]:
                if c["id"] == cid:
                    c.setdefault("reference_images", []).append(existing)
                    return c
            return None
        pm.mutate_project(pid, _add_ref)

        # PUT the SAME filename carrying a multi-face image → must be rejected.
        with patch.object(cm, "DEEPFACE_AVAILABLE", True), \
             patch.object(cm, "_count_faces", return_value=2):
            resp = client.put(
                f"/api/projects/{pid}/characters/{cid}",
                data={
                    "name": "Solo",
                    "reference_images": (io.BytesIO(b"TWO-FACE-BYTES"), "headshot.jpg"),
                },
                content_type="multipart/form-data",
            )

        assert resp.status_code == 400
        # DATA-LOSS GUARD: the pre-existing valid reference must SURVIVE intact.
        assert os.path.exists(existing), "existing reference was destroyed (bug_001)"
        with open(existing, "rb") as fh:
            assert fh.read() == b"ORIGINAL-VALID-SINGLE-FACE-BYTES", (
                "existing reference was overwritten before validation (bug_001)"
            )
        # Record stays consistent with disk: still lists the surviving ref.
        rec = _char_record(pid, cid)
        assert existing in rec["reference_images"]

    def test_valid_single_face_put_with_new_name_still_appends(self, client):
        """Non-regression: a valid single-face PUT with a fresh filename still
        lands the reference (the staging-then-move path works end to end)."""
        pid, cid = _project_with_char()
        with patch.object(cm, "DEEPFACE_AVAILABLE", True), \
             patch.object(cm, "_count_faces", return_value=1):
            resp = _put_with_image(client, pid, cid)
        assert resp.status_code == 200
        rec = _char_record(pid, cid)
        assert len(rec["reference_images"]) == 1
        assert rec["reference_images"][0].endswith("newref.jpg")
        # the moved file actually exists on disk
        assert os.path.exists(rec["reference_images"][0])

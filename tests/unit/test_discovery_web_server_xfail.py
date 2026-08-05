"""Live regressions for HTTP-mutator defects from the hardening-campaign
discovery bug-hunt (wf_13f9d2f6-f93, confirmed[12..17]).

These began as strict-xfail CI pins. Fixed rows stay here as ordinary
regressions so the old bypasses cannot silently return.

CATALOG:
  confirmed[12] W2:MAJOR:http-clearperf-silent200
    web_server.py:972 — api_clear_performance returns 200 cleared=True even when
    shot_id does not exist (mutate_project return value discarded).
  confirmed[13] W2:MAJOR:http-drivingvid-orphan
    web_server.py:909,932 — file written before lock; mutate_project return
    discarded -> 201 even when shot not mutated (orphaned file / false-201).
  confirmed[14] W1:CRITICAL:ws-reorder-deletes — FIXED (pin removed)
    web_server.py:1402 + domain/project_manager.py:1081 — reorder_scenes now
    preserves any scene absent from the posted scene_ids (survivor pass); a
    partial list reorders, never deletes. Kept as a live regression test below.
  confirmed[15] W2:MAJOR:http-addchar-float-unguarded — CLOSED BY REMOVAL
    Was: bare float() on ip_adapter_weight with no guard -> ValueError 500 on
    non-numeric input (e.g. "abc"). Guarded by _parse_ip_adapter_weight, then
    the field itself was deleted end to end (9d removal follow-up) because it
    had no production reader at any layer. No numeric field remains on these
    four mutators, so the unguarded-float class is gone rather than fixed.
    The surviving pin below covers the removal's own risk: an old client that
    still sends the key must be ignored inertly, not 500 and not persisted.
  confirmed[16] W2:MEDIUM:http-null-json-body
    web_server.py:1966,2610,2656 — request.json None -> None.get() AttributeError
    500 when caller sends Content-Type: application/json with body null.
  confirmed[17] W2:MEDIUM:http-styleboard-false201 — CLOSED BY REMOVAL
    The dormant style-board upload/storage route was retired with its
    unconsumed FLUX Redux threading. A route-absence regression remains below.

TEST-INFEASIBLE entries: none — every defect had a viable seam (direct domain
function for [14], Flask test_client for the rest).
"""
import io
import json
import os

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_project_dir(tmp_path, monkeypatch):
    """Create a real persisted project in tmp_path; return (pid, project dict)."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    proj = project_manager.create_project("xfail-test")
    return proj["id"], proj


def _add_scene_and_shot(pid, monkeypatch, tmp_path):
    """Add one scene with one shot to the project; return (scene_id, shot_id)."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    scene = project_manager.make_scene("S1")
    shot = project_manager.make_shot("Test shot")
    scene["shots"].append(shot)
    scene["num_shots"] = 1

    def _mutate(latest):
        latest["scenes"].append(scene)
        from domain.project_manager import MutationResult
        return MutationResult(None, save=True)

    project_manager.mutate_project(pid, _mutate, timeout=5)
    return scene["id"], shot["id"]


def _add_character_record(pid, monkeypatch, tmp_path):
    """Add one character record directly to project storage; return character id."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    character = project_manager.make_character("Existing Char", "desc")

    def _mutate(latest):
        latest["characters"].append(character)
        from domain.project_manager import MutationResult
        return MutationResult(character, save=True)

    project_manager.mutate_project(pid, _mutate, timeout=5)
    return character["id"]


def _add_object_record(pid, monkeypatch, tmp_path):
    """Add one object record directly to project storage; return object id."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    obj = project_manager.make_object("Existing Object", "desc")

    def _mutate(latest):
        latest.setdefault("objects", []).append(obj)
        from domain.project_manager import MutationResult
        return MutationResult(obj, save=True)

    project_manager.mutate_project(pid, _mutate, timeout=5)
    return obj["id"]


@pytest.fixture
def client():
    import web_server
    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# confirmed[12] — W2:MAJOR:http-clearperf-silent200
# ---------------------------------------------------------------------------

def test_clear_performance_nonexistent_shot_returns_404(client, tmp_path, monkeypatch):
    """DELETE on a nonexistent shot_id should be 404, not 200 cleared=True."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    pid, _ = _make_project_dir(tmp_path, monkeypatch)
    # No scenes/shots added — any sid is nonexistent for this project.
    resp = client.delete(f"/api/projects/{pid}/shots/nonexistent_shot_id/performance")
    # CURRENT behaviour (bug): 200 {"cleared": True}
    # FIXED behaviour (what we assert): 404
    assert resp.status_code == 404, (
        f"Expected 404 for nonexistent shot, got {resp.status_code}: {resp.data!r}"
    )


# ---------------------------------------------------------------------------
# confirmed[13] — W2:MAJOR:http-drivingvid-orphan
# ---------------------------------------------------------------------------

def test_upload_driving_video_mutator_miss_returns_non_201(client, tmp_path, monkeypatch):
    """Simulate a TOCTOU where the shot disappears before the mutator runs.

    Strategy: add a scene+shot so the outer lookup succeeds (scene_id found),
    then delete the shot from the project before mutate_project is called by
    monkey-patching mutate_project itself to run the real mutator against a
    snapshot that no longer has the shot.  A simpler approach: POST a real
    file but then ensure the shot is absent from the project.json at lock time.

    Lightest seam: patch mutate_project to simulate MutationResult(None,
    save=False) — i.e. the shot-not-found path — and confirm the endpoint
    returns something other than 201.
    """
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    pid, _ = _make_project_dir(tmp_path, monkeypatch)
    scene_id, shot_id = _add_scene_and_shot(pid, monkeypatch, tmp_path)

    # Patch mutate_project so the mutator sees a project without the shot,
    # returning None (the MutationResult(None, save=False) path).
    original_mutate = project_manager.mutate_project

    def _stubbed_mutate(project_id, mutator, timeout=10, snapshot=None):
        # Run mutator on a copy of the project that has the shot removed,
        # simulating the TOCTOU window.
        import copy
        latest = project_manager._load_project_unlocked(project_id)
        if latest is None:
            return None
        # Strip all shots from all scenes — shot gone between lookup and lock.
        stripped = copy.deepcopy(latest)
        for sc in stripped.get("scenes", []):
            sc["shots"] = []
        result = mutator(stripped)
        from domain.project_manager import MutationResult
        if isinstance(result, MutationResult):
            return result.value  # None when shot not found
        return result

    import web_server
    monkeypatch.setattr(web_server, "mutate_project", _stubbed_mutate, raising=False)
    monkeypatch.setattr(project_manager, "mutate_project", _stubbed_mutate, raising=False)

    video_data = io.BytesIO(b"\x00" * 8)
    video_data.name = "driving.mp4"
    resp = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (video_data, "driving.mp4")},
        content_type="multipart/form-data",
    )
    # CURRENT behaviour (bug): 201 {"uploaded": True, "path": ...}
    # FIXED behaviour: 404 or 409 (not 201) when mutation did not persist.
    assert resp.status_code != 201, (
        f"Expected non-201 when mutator found no shot, got {resp.status_code}: {resp.data!r}"
    )


# ---------------------------------------------------------------------------
# confirmed[14] — W1:CRITICAL:ws-reorder-deletes  (direct domain-function seam)
# FIXED: domain/project_manager.py reorder_scenes now preserves unlisted scenes
# via a survivor pass (a partial scene_ids list reorders, never deletes). Pin
# removed; this is now a live regression test guarding against the data
# corruption.
# ---------------------------------------------------------------------------


def test_reorder_scenes_partial_list_preserves_unlisted_scenes(tmp_path, monkeypatch):
    """A partial scene_ids list must NOT delete the omitted scenes."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)

    pid, proj = _make_project_dir(tmp_path, monkeypatch)

    # Add two scenes.
    scene_a = project_manager.make_scene("Scene A")
    scene_b = project_manager.make_scene("Scene B")

    def _add_scenes(latest):
        latest["scenes"] = [scene_a, scene_b]
        from domain.project_manager import MutationResult
        return MutationResult(None, save=True)

    project_manager.mutate_project(pid, _add_scenes, timeout=5)

    # Load fresh copy so reorder_scenes sees the persisted state.
    proj_with_scenes = project_manager.load_project(pid)
    assert len(proj_with_scenes["scenes"]) == 2, "setup: two scenes must exist"

    # Post only scene_a's id — scene_b is omitted.
    project_manager.reorder_scenes(proj_with_scenes, [scene_a["id"]], timeout=5)

    # FIXED behaviour: scene_b must survive.
    final = project_manager.load_project(pid)
    final_ids = {sc["id"] for sc in final["scenes"]}
    assert scene_b["id"] in final_ids, (
        f"scene_b was permanently deleted by a partial reorder list "
        f"(surviving ids: {final_ids})"
    )

    # The survivor pass assigns unlisted scenes a continuing order index, so the
    # order field must remain a contiguous 0..n-1 sequence. Guards against a
    # future "preserve" refactor that drops or duplicates the index.
    final_orders = sorted(sc["order"] for sc in final["scenes"])
    assert final_orders == list(range(len(final["scenes"]))), (
        f"order fields are not contiguous after a partial reorder: {final_orders}"
    )


# ---------------------------------------------------------------------------
# confirmed[15] — W2:MAJOR:http-addchar-float-unguarded (CLOSED BY REMOVAL)
#
# The original six pins asserted 400 for non-numeric / non-finite / boolean
# ip_adapter_weight at the four character+object mutators. The field has since
# been deleted end to end, so there is no value to validate and no float() to
# guard — those pins would now assert a contract that cannot exist.
#
# What replaces them is the risk the DELETION introduces: a stale client (an
# old cached UI bundle, an operator script) that still sends the key. It must
# be ignored inertly — never a 500 from an unexpected field, and never written
# back into the record, since a persisted-but-unread value is exactly the
# decorative state this removal exists to eliminate.
# ---------------------------------------------------------------------------

def test_removed_ip_adapter_weight_is_ignored_not_persisted_on_all_mutators(
    client, tmp_path, monkeypatch,
):
    """A stale client sending ip_adapter_weight must get a success, and the
    value must not survive into the stored record at any of the four mutators."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    pid, _ = _make_project_dir(tmp_path, monkeypatch)
    cid = _add_character_record(pid, monkeypatch, tmp_path)
    oid = _add_object_record(pid, monkeypatch, tmp_path)

    cases = [
        (
            "add character",
            client.post,
            f"/api/projects/{pid}/characters",
            {"data": {"name": "Stale Char", "description": "desc",
                      "creation_request_id": "b" * 32,
                      "ip_adapter_weight": "0.85"}},
        ),
        (
            "add object",
            client.post,
            f"/api/projects/{pid}/objects",
            {"json": {"name": "Stale Object", "description": "desc",
                      "ip_adapter_weight": 0.85}},
        ),
        (
            "update character",
            client.put,
            f"/api/projects/{pid}/characters/{cid}",
            {"json": {"ip_adapter_weight": 0.85}},
        ),
        (
            "update object",
            client.put,
            f"/api/projects/{pid}/objects/{oid}",
            {"json": {"ip_adapter_weight": 0.85}},
        ),
    ]
    for label, method, url, kwargs in cases:
        resp = method(url, **kwargs)
        assert resp.status_code < 400, (
            f"A stale ip_adapter_weight must be ignored, not rejected, on "
            f"{label}; got {resp.status_code}: {resp.data!r}"
        )

    # The key must not have been written into ANY stored character or object.
    stored = project_manager.load_project(pid)
    records = list(stored.get("characters", [])) + list(stored.get("objects", []))
    assert records, "fixture produced no character/object records to inspect"
    offenders = [r.get("name") for r in records if "ip_adapter_weight" in r]
    assert not offenders, (
        f"ip_adapter_weight was persisted despite removal, on: {offenders}"
    )


# ---------------------------------------------------------------------------
# confirmed[16] — W2:MEDIUM:http-null-json-body
# ---------------------------------------------------------------------------

def test_update_shot_prompt_null_json_body_returns_400(client, tmp_path, monkeypatch):
    """PUT with Content-Type: application/json and body null must yield 400, not 500."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    pid, _ = _make_project_dir(tmp_path, monkeypatch)
    _, shot_id = _add_scene_and_shot(pid, monkeypatch, tmp_path)

    resp = client.put(
        f"/api/projects/{pid}/shots/{shot_id}/prompt",
        data=b"null",
        content_type="application/json",
    )
    # CURRENT behaviour (bug): 500 AttributeError: 'NoneType' has no attribute 'get'
    # FIXED behaviour: 400 (invalid body)
    assert resp.status_code == 400, (
        f"Expected 400 for null JSON body on /prompt, got {resp.status_code}: {resp.data!r}"
    )


def test_cleanup_null_json_body_returns_non_500(client, tmp_path, monkeypatch):
    """POST /cleanup with body null must not crash with 500."""
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    pid, _ = _make_project_dir(tmp_path, monkeypatch)

    resp = client.post(
        f"/api/projects/{pid}/cleanup",
        data=b"null",
        content_type="application/json",
    )
    # CURRENT behaviour (bug): 500 AttributeError
    # FIXED behaviour: any 2xx or 4xx (not 500)
    assert resp.status_code != 500, (
        f"Expected non-500 for null JSON body on /cleanup, got {resp.status_code}: {resp.data!r}"
    )


def test_cleanup_all_endpoint_is_retired(client):
    """The misleading global temp cleanup must not masquerade as a reset."""
    import web_server

    assert all(
        rule.rule != "/api/cleanup-all"
        for rule in web_server.app.url_map.iter_rules()
    )
    # Avoid malformed-body preflight: this assertion is about route absence,
    # not the global object-only JSON contract. The SPA's GET-only catch-all
    # makes an otherwise unknown POST a 405 instead of a 404.
    resp = client.post("/api/cleanup-all")
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# confirmed[17] — W2:MEDIUM:http-styleboard-false201 — CLOSED BY REMOVAL
# ---------------------------------------------------------------------------

def test_style_board_endpoint_is_retired(client):
    """Dormant uploads must not persist unused style-reference assets."""
    import web_server

    assert all(
        rule.rule != "/api/projects/<pid>/style-board"
        for rule in web_server.app.url_map.iter_rules()
    )
    # The SPA's GET-only catch-all makes an otherwise unknown POST a 405.
    assert client.post("/api/projects/proj_test/style-board").status_code == 405

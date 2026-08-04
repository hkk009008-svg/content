import sys, os

import json
import tempfile

import pytest
from pydantic import ValidationError

import project_manager


# ---------------------------------------------------------------------------
# Fixture: redirect PROJECTS_DIR to a temporary directory
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_projects_dir(monkeypatch):
    """Point PROJECTS_DIR to a fresh temp dir for every test.

    `project_manager` at repo root is a re-export shim for
    `domain.project_manager`. Functions resolve `PROJECTS_DIR` from their
    defining module's namespace, so the patch MUST target the real symbol
    in `domain.project_manager` — patching the shim's re-exported name is
    a silent no-op and was the cause of 6 historical failures.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", tmpdir)
        yield tmpdir


# ===================================================================
# Data model factories
# ===================================================================

class TestMakeProject:
    def test_returns_dict_with_required_keys(self):
        proj = project_manager.make_project("My Film")
        assert isinstance(proj, dict)
        assert proj["name"] == "My Film"
        assert isinstance(proj["id"], str) and len(proj["id"]) > 0
        assert proj["characters"] == []
        assert proj["locations"] == []
        assert proj["scenes"] == []
        assert isinstance(proj["global_settings"], dict)

    def test_global_settings_defaults(self):
        proj = project_manager.make_project("X")
        gs = proj["global_settings"]
        assert gs["aspect_ratio"] == "16:9"
        assert gs["competitive_generation"] is True
        assert isinstance(gs["master_seed"], int)
        assert gs["auto_approve"]["image_min_composite"] == pytest.approx(0.60)

    def test_unique_ids(self):
        ids = {project_manager.make_project("p")["id"] for _ in range(50)}
        assert len(ids) == 50


class TestMakeCharacter:
    def test_basic_fields(self):
        ch = project_manager.make_character("Alice", "A brave hero")
        assert ch["id"].startswith("char_")
        assert ch["name"] == "Alice"
        assert ch["description"] == "A brave hero"
        assert ch["reference_images"] == []
        assert ch["voice_id"] == ""
        # ip_adapter_weight was removed end to end (9d removal follow-up): it
        # had no production reader at any layer, and the PuLID node weight is
        # resolved from the shot-type template / adaptive gate instead.
        assert "ip_adapter_weight" not in ch

    def test_custom_fields(self):
        ch = project_manager.make_character(
            "Bob", "Villain",
            reference_images=["img1.png"],
            voice_id="v42",
        )
        assert ch["reference_images"] == ["img1.png"]
        assert ch["voice_id"] == "v42"

    def test_unique_ids(self):
        ids = {project_manager.make_character("c", "d")["id"] for _ in range(50)}
        assert len(ids) == 50


class TestMakeLocation:
    def test_basic_fields(self):
        loc = project_manager.make_location("Forest", "Dark woods")
        assert loc["id"].startswith("loc_")
        assert loc["name"] == "Forest"
        assert loc["description"] == "Dark woods"
        assert loc["time_of_day"] == "day"
        assert loc["weather"] == "clear"
        assert 100000 <= loc["seed"] <= 999999

    def test_custom_fields(self):
        loc = project_manager.make_location(
            "Beach", "Sandy",
            reference_images=["b.png"],
            lighting="golden hour",
            time_of_day="sunset",
            weather="windy",
        )
        assert loc["reference_images"] == ["b.png"]
        assert loc["lighting"] == "golden hour"
        assert loc["time_of_day"] == "sunset"
        assert loc["weather"] == "windy"


class TestMakeScene:
    def test_basic_fields(self):
        sc = project_manager.make_scene("Opening")
        assert sc["id"].startswith("scene_")
        assert sc["title"] == "Opening"
        assert sc["order"] == 0
        assert sc["shots"] == []
        assert sc["duration_seconds"] == 5.0
        assert sc["mood"] == "neutral"

    def test_custom_fields(self):
        sc = project_manager.make_scene(
            "Chase",
            location_id="loc_abc",
            characters_present=["char_1"],
            action="running",
            dialogue="Stop!",
            mood="tense",
            camera_direction="tracking",
            duration_seconds=10.0,
        )
        assert sc["location_id"] == "loc_abc"
        assert sc["characters_present"] == ["char_1"]
        assert sc["action"] == "running"
        assert sc["dialogue"] == "Stop!"
        assert sc["mood"] == "tense"
        assert sc["duration_seconds"] == 10.0


class TestMakeShot:
    def test_basic_fields(self):
        sh = project_manager.make_shot("A sunset over mountains")
        assert sh["id"].startswith("shot_")
        assert sh["prompt"] == "A sunset over mountains"
        assert sh["camera"] == "zoom_in_slow"
        assert sh["visual_effect"] == "cinematic_glow"
        assert sh["target_api"] == "AUTO"
        assert sh["characters_in_frame"] == []
        assert sh["generated_image"] == ""
        assert sh["generated_video"] == ""

    def test_custom_fields(self):
        sh = project_manager.make_shot(
            "Close-up",
            camera="dolly",
            visual_effect="none",
            target_api="kling",
            scene_foley="wind",
            characters_in_frame=["char_1"],
            primary_character="char_1",
        )
        assert sh["camera"] == "dolly"
        assert sh["visual_effect"] == "none"
        assert sh["target_api"] == "kling"
        assert sh["scene_foley"] == "wind"
        assert sh["characters_in_frame"] == ["char_1"]
        assert sh["primary_character"] == "char_1"


# ===================================================================
# Persistence
# ===================================================================

class TestCreateProject:
    def test_creates_dirs_and_json(self, tmp_projects_dir):
        proj = project_manager.create_project("Test Film")
        pid = proj["id"]
        proj_dir = os.path.join(tmp_projects_dir, pid)

        assert os.path.isdir(proj_dir)
        assert os.path.isdir(os.path.join(proj_dir, "characters"))
        assert os.path.isdir(os.path.join(proj_dir, "locations"))
        assert os.path.isdir(os.path.join(proj_dir, "exports"))
        assert os.path.isdir(os.path.join(proj_dir, "temp"))
        assert os.path.isfile(os.path.join(proj_dir, "project.json"))

    def test_saved_json_matches(self, tmp_projects_dir):
        proj = project_manager.create_project("Roundtrip")
        loaded = project_manager.load_project(proj["id"])
        assert loaded == proj


class TestSaveAndLoadProject:
    def test_roundtrip(self, tmp_projects_dir):
        proj = project_manager.make_project("SaveMe")
        project_manager.save_project(proj)
        loaded = project_manager.load_project(proj["id"])
        assert loaded == proj

    def test_load_nonexistent_returns_none(self):
        assert project_manager.load_project("nonexistent_id_12345") is None

    def test_overwrite(self, tmp_projects_dir):
        proj = project_manager.make_project("V1")
        project_manager.save_project(proj)
        proj["name"] = "V2"
        project_manager.save_project(proj)
        loaded = project_manager.load_project(proj["id"])
        assert loaded["name"] == "V2"

    def test_historical_unknown_shot_extension_remains_load_compatible(self):
        """Public replacement is strict without globally forbidding old data."""
        proj = project_manager.create_project("Historical extension")
        scene = project_manager.make_scene("Scene")
        shot = project_manager.make_shot("Prompt")
        shot["historical_extension"] = {"retained": True}
        scene["shots"] = [shot]
        scene["num_shots"] = 1

        def _seed(latest):
            latest["scenes"] = [scene]
            return True

        project_manager.mutate_project(proj["id"], _seed)

        loaded = project_manager.load_project(proj["id"])

        assert (
            loaded["scenes"][0]["shots"][0]["historical_extension"]
            == {"retained": True}
        )


class TestProjectIdBoundary:
    @pytest.mark.parametrize(
        "project_id",
        [
            "a",
            "0bf9d0608eab",
            "Project-2",
            "proj_1",
            "proj-iterate-during-screening",
            "A" * project_manager.MAX_PROJECT_ID_LENGTH,
        ],
    )
    def test_accepts_observed_ascii_shapes(self, project_id):
        assert project_manager.is_safe_project_id(project_id) is True

    @pytest.mark.parametrize(
        "project_id",
        [
            "",
            ".",
            "..",
            "../outside",
            "/tmp/outside",
            "nested/outside",
            r"nested\outside",
            "project id",
            "project\x00id",
            "project\x1fid",
            "prøject",
            "A" * (project_manager.MAX_PROJECT_ID_LENGTH + 1),
        ],
    )
    def test_rejects_noncanonical_or_overlong_shapes(self, project_id):
        assert project_manager.is_safe_project_id(project_id) is False

    def test_invalid_id_fails_before_projects_directory_creation(
        self,
        tmp_path,
        monkeypatch,
    ):
        missing_root = tmp_path / "not-created"
        monkeypatch.setattr(
            "domain.project_manager.PROJECTS_DIR",
            str(missing_root),
        )

        with pytest.raises(ValueError, match="Invalid project_id"):
            project_manager.load_project(
                "A" * (project_manager.MAX_PROJECT_ID_LENGTH + 1),
            )

        assert not missing_root.exists()

    def test_readonly_missing_project_creates_no_artifacts(
        self,
        tmp_projects_dir,
    ):
        assert (
            project_manager.load_existing_project_readonly("valid-missing")
            is None
        )
        assert os.listdir(tmp_projects_dir) == []

    def test_load_and_mutate_missing_project_skip_existing_target_lock(
        self,
        tmp_projects_dir,
        monkeypatch,
    ):
        import domain.project_manager as dpm
        from unittest.mock import MagicMock

        lock_bomb = MagicMock(
            side_effect=AssertionError("missing target reached lock"),
        )
        ensure_bomb = MagicMock(
            side_effect=AssertionError("missing target created directory"),
        )
        mutator = MagicMock(
            side_effect=AssertionError("missing target reached mutator"),
        )
        monkeypatch.setattr(dpm, "_acquire_existing_project_lock", lock_bomb)
        monkeypatch.setattr(dpm, "_ensure_project_dir", ensure_bomb)

        assert project_manager.load_project("valid-missing") is None
        assert project_manager.mutate_project("valid-missing", mutator) is None

        lock_bomb.assert_not_called()
        ensure_bomb.assert_not_called()
        mutator.assert_not_called()
        assert os.listdir(tmp_projects_dir) == []

    def test_stored_project_id_mismatch_fails_before_lock_or_cross_write(
        self,
        tmp_projects_dir,
        monkeypatch,
    ):
        import domain.project_manager as dpm
        from unittest.mock import MagicMock

        project = project_manager.create_project("Corrupt identity")
        route_id = project["id"]
        stored_id = "other-project"
        project_path = os.path.join(
            tmp_projects_dir,
            route_id,
            "project.json",
        )
        with open(project_path, "r", encoding="utf-8") as handle:
            corrupted = json.load(handle)
        corrupted["id"] = stored_id
        with open(project_path, "w", encoding="utf-8") as handle:
            json.dump(corrupted, handle)
        before = open(project_path, "rb").read()

        lock_bomb = MagicMock(
            side_effect=AssertionError("identity mismatch reached lock"),
        )
        write_bomb = MagicMock(
            side_effect=AssertionError("identity mismatch reached write"),
        )
        mutator = MagicMock(
            side_effect=AssertionError("identity mismatch reached mutator"),
        )
        monkeypatch.setattr(dpm, "_acquire_existing_project_lock", lock_bomb)
        monkeypatch.setattr(dpm, "_save_project_unlocked", write_bomb)

        assert project_manager.load_project(route_id) is None
        assert project_manager.load_existing_project_readonly(route_id) is None
        assert project_manager.mutate_project(route_id, mutator) is None

        lock_bomb.assert_not_called()
        write_bomb.assert_not_called()
        mutator.assert_not_called()
        assert open(project_path, "rb").read() == before
        assert not os.path.exists(os.path.join(tmp_projects_dir, stored_id))

    def test_delete_between_preflight_and_lock_creates_no_artifact(
        self,
        tmp_projects_dir,
        monkeypatch,
    ):
        import shutil
        import domain.project_manager as dpm
        from unittest.mock import MagicMock

        project = project_manager.create_project("Delete race")
        project_dir = os.path.join(tmp_projects_dir, project["id"])
        real_file_lock = dpm.FileLock

        class DeleteBeforeAcquire:
            def __init__(self, path, timeout, **kwargs):
                self._lock = real_file_lock(path, timeout=timeout, **kwargs)

            def __enter__(self):
                shutil.rmtree(project_dir)
                return self._lock.__enter__()

            def __exit__(self, exc_type, exc, tb):
                return self._lock.__exit__(exc_type, exc, tb)

        mutator = MagicMock(
            side_effect=AssertionError("deleted target reached mutator"),
        )
        ensure_bomb = MagicMock(
            side_effect=AssertionError("deleted target was recreated"),
        )
        monkeypatch.setattr(dpm, "FileLock", DeleteBeforeAcquire)
        monkeypatch.setattr(dpm, "_ensure_project_dir", ensure_bomb)

        assert project_manager.mutate_project(project["id"], mutator) is None

        mutator.assert_not_called()
        ensure_bomb.assert_not_called()
        assert not os.path.exists(project_dir)

    def test_lock_path_is_a_sibling_outside_the_project_dir(
        self,
        tmp_projects_dir,
    ):
        """Deleting projects/<pid>/ must never unlink an actively held lock.

        The unlink race (two waiters holding different inodes of the same
        lock path) is prevented by geometry: the lock file is a sibling of
        the project directory, so per-project rmtree cannot touch it.
        """
        import domain.project_manager as dpm

        pid = "abc123def456"
        lock_path = dpm._project_lock_path(pid)
        project_dir = os.path.abspath(dpm._project_dir(pid))

        assert not (lock_path + os.sep).startswith(project_dir + os.sep)
        assert os.path.dirname(lock_path) == os.path.dirname(project_dir)

        with pytest.raises(ValueError):
            dpm._project_lock_path("../escape")

    def test_stored_id_change_between_preflight_and_lock_fails_closed(
        self,
        tmp_projects_dir,
        monkeypatch,
    ):
        import domain.project_manager as dpm
        from unittest.mock import MagicMock

        project = project_manager.create_project("Identity race")
        corrupted = dict(project)
        corrupted["id"] = "other-project"
        load = MagicMock(side_effect=[dict(project), corrupted])
        mutator = MagicMock(
            side_effect=AssertionError("identity race reached mutator"),
        )
        write_bomb = MagicMock(
            side_effect=AssertionError("identity race reached write"),
        )
        monkeypatch.setattr(dpm, "_load_project_unlocked", load)
        monkeypatch.setattr(dpm, "_save_project_unlocked", write_bomb)

        assert project_manager.mutate_project(project["id"], mutator) is None

        assert load.call_count == 2
        mutator.assert_not_called()
        write_bomb.assert_not_called()
        assert not os.path.exists(
            os.path.join(tmp_projects_dir, "other-project"),
        )

    def test_mutator_cannot_redirect_save_by_changing_project_id(
        self,
        tmp_projects_dir,
    ):
        project = project_manager.create_project("Route identity")
        route_id = project["id"]
        project_path = os.path.join(
            tmp_projects_dir,
            route_id,
            "project.json",
        )
        with open(project_path, "rb") as handle:
            before = handle.read()
        snapshot = json.loads(json.dumps(project))

        def _redirect(latest):
            latest["name"] = "must not persist"
            latest["id"] = "other-project"
            return True

        result = project_manager.mutate_project(
            route_id,
            _redirect,
            snapshot=snapshot,
        )

        assert result is None
        with open(project_path, "rb") as handle:
            assert handle.read() == before
        assert snapshot == project
        assert not os.path.exists(
            os.path.join(tmp_projects_dir, "other-project"),
        )

    def test_readonly_existing_project_never_persists_normalization(
        self,
        monkeypatch,
    ):
        import domain.project_manager as dpm
        from unittest.mock import MagicMock

        project = project_manager.create_project("Read only")
        write_bomb = MagicMock(
            side_effect=AssertionError("read-only load wrote project"),
        )
        monkeypatch.setattr(dpm, "_save_project_unlocked", write_bomb)

        loaded = project_manager.load_existing_project_readonly(project["id"])

        assert loaded["id"] == project["id"]
        write_bomb.assert_not_called()


class TestDeleteProject:
    def test_delete_existing(self, tmp_projects_dir):
        proj = project_manager.create_project("Doomed")
        assert project_manager.delete_project(proj["id"]) is True
        assert not os.path.exists(os.path.join(tmp_projects_dir, proj["id"]))

    def test_delete_nonexistent(self):
        assert project_manager.delete_project("nope_999") is False


class TestListProjects:
    def test_empty(self, tmp_projects_dir):
        assert project_manager.list_projects() == []

    def test_multiple(self, tmp_projects_dir):
        p1 = project_manager.create_project("Alpha")
        p2 = project_manager.create_project("Beta")
        result = project_manager.list_projects()
        ids = {r["id"] for r in result}
        names = {r["name"] for r in result}
        assert ids == {p1["id"], p2["id"]}
        assert names == {"Alpha", "Beta"}

    def test_only_returns_id_and_name(self, tmp_projects_dir):
        project_manager.create_project("Slim")
        items = project_manager.list_projects()
        assert len(items) == 1
        assert set(items[0].keys()) == {"id", "name"}

    def test_sorted_by_mtime_descending(self, tmp_projects_dir):
        """Val#2 U1: list must return most-recently-modified projects first.
        Without this, the landing page's "Recent Productions" heading
        renders ancient pytest fixtures alongside live work.
        """
        import os
        # Create three projects in deterministic order.
        oldest = project_manager.create_project("Oldest")
        middle = project_manager.create_project("Middle")
        newest = project_manager.create_project("Newest")

        # Backdate the mtimes so order is unambiguous regardless of how
        # fast create_project ran. os.utime sets (atime, mtime); we only
        # care about mtime. tmp_projects_dir is the fixture-redirected
        # PROJECTS_DIR for this test; project_manager.PROJECTS_DIR is the
        # shim's re-exported (unredirected) symbol — see fixture docstring.
        base = 1_700_000_000  # arbitrary epoch baseline
        for pid, mtime_offset in [
            (oldest["id"], 0),       # base + 0  → oldest
            (middle["id"], 100),     # base + 100
            (newest["id"], 200),     # base + 200 → newest
        ]:
            project_json = os.path.join(tmp_projects_dir, pid, "project.json")
            os.utime(project_json, (base + mtime_offset, base + mtime_offset))

        items = project_manager.list_projects()
        ordered_names = [p["name"] for p in items]
        assert ordered_names == ["Newest", "Middle", "Oldest"], (
            f"Expected newest-first ordering; got {ordered_names}"
        )

    def test_skips_projects_with_missing_json(self, tmp_projects_dir):
        """Defensive: a directory under PROJECTS_DIR with no project.json
        (e.g., a half-deleted project, or a stray dir) must NOT crash the
        list endpoint. Pre-Val#2-U1 the load_project call returned None
        and the project was skipped silently; post-fix we additionally
        guard the os.path.getmtime call so missing/unreadable JSON files
        skip cleanly rather than raising OSError.
        """
        import os
        project_manager.create_project("Valid")
        # Create a stray directory that looks like a project but lacks project.json
        stray = os.path.join(tmp_projects_dir, "stray_no_json")
        os.makedirs(stray, exist_ok=True)

        items = project_manager.list_projects()
        names = [p["name"] for p in items]
        assert names == ["Valid"]  # stray skipped, valid included


# ===================================================================
# Mutation helpers — characters
# ===================================================================

class TestCharacterMutations:
    def _make_saved_project(self):
        return project_manager.create_project("CharTest")

    def test_add_character(self):
        proj = self._make_saved_project()
        ch = project_manager.make_character("Alice", "Hero")
        result = project_manager.add_character(proj, ch)
        assert result is ch
        assert len(proj["characters"]) == 1
        # Verify persisted
        loaded = project_manager.load_project(proj["id"])
        assert len(loaded["characters"]) == 1
        assert loaded["characters"][0]["name"] == "Alice"

    def test_get_character(self):
        proj = self._make_saved_project()
        ch = project_manager.make_character("Bob", "Sidekick")
        project_manager.add_character(proj, ch)
        assert project_manager.get_character(proj, ch["id"]) is ch
        assert project_manager.get_character(proj, "nonexistent") is None

    def test_remove_character(self):
        proj = self._make_saved_project()
        ch = project_manager.make_character("Eve", "Villain")
        project_manager.add_character(proj, ch)
        assert project_manager.remove_character(proj, ch["id"]) is True
        assert project_manager.get_character(proj, ch["id"]) is None
        # Persisted
        loaded = project_manager.load_project(proj["id"])
        assert len(loaded["characters"]) == 0

    def test_remove_nonexistent_character(self):
        proj = self._make_saved_project()
        assert project_manager.remove_character(proj, "char_fake") is False


# ===================================================================
# Mutation helpers — locations
# ===================================================================

class TestLocationMutations:
    def _make_saved_project(self):
        return project_manager.create_project("LocTest")

    def test_add_location(self):
        proj = self._make_saved_project()
        loc = project_manager.make_location("Cave", "Dark cave")
        result = project_manager.add_location(proj, loc)
        assert result is loc
        assert len(proj["locations"]) == 1
        loaded = project_manager.load_project(proj["id"])
        assert loaded["locations"][0]["name"] == "Cave"

    def test_get_location(self):
        proj = self._make_saved_project()
        loc = project_manager.make_location("Hill", "Grassy")
        project_manager.add_location(proj, loc)
        assert project_manager.get_location(proj, loc["id"]) is loc
        assert project_manager.get_location(proj, "loc_nope") is None

    def test_remove_location(self):
        proj = self._make_saved_project()
        loc = project_manager.make_location("Lake", "Blue")
        project_manager.add_location(proj, loc)
        assert project_manager.remove_location(proj, loc["id"]) is True
        assert len(proj["locations"]) == 0
        loaded = project_manager.load_project(proj["id"])
        assert len(loaded["locations"]) == 0

    def test_remove_nonexistent_location(self):
        proj = self._make_saved_project()
        assert project_manager.remove_location(proj, "loc_fake") is False


# ===================================================================
# Mutation helpers — scenes
# ===================================================================

class TestSceneMutations:
    def _make_saved_project(self):
        return project_manager.create_project("SceneTest")

    def test_add_scene_sets_order(self):
        proj = self._make_saved_project()
        s0 = project_manager.make_scene("First")
        s1 = project_manager.make_scene("Second")
        project_manager.add_scene(proj, s0)
        project_manager.add_scene(proj, s1)
        assert s0["order"] == 0
        assert s1["order"] == 1

    def test_update_scene(self):
        proj = self._make_saved_project()
        sc = project_manager.make_scene("Draft")
        project_manager.add_scene(proj, sc)
        updated = project_manager.update_scene(proj, sc["id"], {"title": "Final", "mood": "happy"})
        assert updated["title"] == "Final"
        assert updated["mood"] == "happy"
        loaded = project_manager.load_project(proj["id"])
        assert loaded["scenes"][0]["title"] == "Final"

    def test_update_nonexistent_scene(self):
        proj = self._make_saved_project()
        assert project_manager.update_scene(proj, "scene_nope", {"title": "X"}) is None

    def test_remove_scene_reorders(self):
        proj = self._make_saved_project()
        s0 = project_manager.make_scene("A")
        s1 = project_manager.make_scene("B")
        s2 = project_manager.make_scene("C")
        project_manager.add_scene(proj, s0)
        project_manager.add_scene(proj, s1)
        project_manager.add_scene(proj, s2)

        assert project_manager.remove_scene(proj, s1["id"]) is True
        assert len(proj["scenes"]) == 2
        assert proj["scenes"][0]["id"] == s0["id"]
        assert proj["scenes"][0]["order"] == 0
        assert proj["scenes"][1]["id"] == s2["id"]
        assert proj["scenes"][1]["order"] == 1

    def test_remove_nonexistent_scene(self):
        proj = self._make_saved_project()
        assert project_manager.remove_scene(proj, "scene_fake") is False

    def test_reorder_scenes(self):
        proj = self._make_saved_project()
        s0 = project_manager.make_scene("X")
        s1 = project_manager.make_scene("Y")
        s2 = project_manager.make_scene("Z")
        project_manager.add_scene(proj, s0)
        project_manager.add_scene(proj, s1)
        project_manager.add_scene(proj, s2)

        # Reverse order
        project_manager.reorder_scenes(proj, [s2["id"], s1["id"], s0["id"]])
        assert proj["scenes"][0]["id"] == s2["id"]
        assert proj["scenes"][0]["order"] == 0
        assert proj["scenes"][1]["id"] == s1["id"]
        assert proj["scenes"][1]["order"] == 1
        assert proj["scenes"][2]["id"] == s0["id"]
        assert proj["scenes"][2]["order"] == 2
        # Persisted
        loaded = project_manager.load_project(proj["id"])
        assert [s["id"] for s in loaded["scenes"]] == [s2["id"], s1["id"], s0["id"]]

    def test_reorder_scenes_drops_unknown_ids(self):
        proj = self._make_saved_project()
        s0 = project_manager.make_scene("Only")
        project_manager.add_scene(proj, s0)
        project_manager.reorder_scenes(proj, ["scene_unknown", s0["id"]])
        # Only the known scene survives
        assert len(proj["scenes"]) == 1
        assert proj["scenes"][0]["id"] == s0["id"]
        assert proj["scenes"][0]["order"] == 1  # index in the provided list


# ===================================================================
# Shot package functions
# ===================================================================

class TestShotPackages:
    def _make_saved_project(self):
        return project_manager.create_project("ShotTest")

    def test_ensure_shot_package_creates_dirs(self, tmp_projects_dir):
        proj = self._make_saved_project()
        shot_path = project_manager.ensure_shot_package(proj["id"], "shot_abc")
        assert os.path.isdir(os.path.join(shot_path, "inputs"))
        assert os.path.isdir(os.path.join(shot_path, "outputs"))

    def test_ensure_shot_package_idempotent(self, tmp_projects_dir):
        proj = self._make_saved_project()
        path1 = project_manager.ensure_shot_package(proj["id"], "shot_abc")
        path2 = project_manager.ensure_shot_package(proj["id"], "shot_abc")
        assert path1 == path2

    def test_save_shot_spec(self, tmp_projects_dir):
        proj = self._make_saved_project()
        spec = {"prompt": "test", "camera": "dolly"}
        spec_file = project_manager.save_shot_spec(proj["id"], "shot_1", spec)
        assert os.path.isfile(spec_file)
        with open(spec_file) as f:
            data = json.load(f)
        assert data["prompt"] == "test"
        assert "timestamp" in data

    def test_save_shot_spec_preserves_existing_timestamp(self, tmp_projects_dir):
        proj = self._make_saved_project()
        spec = {"prompt": "x", "timestamp": "2025-01-01T00:00:00Z"}
        project_manager.save_shot_spec(proj["id"], "shot_ts", spec)
        pkg = project_manager.get_shot_package(proj["id"], "shot_ts")
        with open(pkg["spec"]) as f:
            data = json.load(f)
        assert data["timestamp"] == "2025-01-01T00:00:00Z"

    def test_save_shot_metrics(self, tmp_projects_dir):
        proj = self._make_saved_project()
        metrics = {"vbench_overall": 0.75, "cost_usd": 0.12}
        metrics_file = project_manager.save_shot_metrics(proj["id"], "shot_m", metrics)
        assert os.path.isfile(metrics_file)
        with open(metrics_file) as f:
            data = json.load(f)
        assert data["vbench_overall"] == 0.75

    def test_get_shot_package_nonexistent(self):
        assert project_manager.get_shot_package("no_proj", "no_shot") is None

    def test_get_shot_package_manifest(self, tmp_projects_dir):
        proj = self._make_saved_project()
        pid = proj["id"]
        sid = "shot_full"
        project_manager.save_shot_spec(pid, sid, {"prompt": "hello"})
        project_manager.save_shot_metrics(pid, sid, {"score": 1})

        pkg = project_manager.get_shot_package(pid, sid)
        assert pkg is not None
        assert pkg["shot_id"] == sid
        assert pkg["spec"] is not None
        assert "metrics" in pkg["outputs"]

    def test_list_shot_packages_empty(self, tmp_projects_dir):
        proj = self._make_saved_project()
        assert project_manager.list_shot_packages(proj["id"]) == []

    def test_list_shot_packages_sorted(self, tmp_projects_dir):
        proj = self._make_saved_project()
        pid = proj["id"]
        for sid in ["shot_c", "shot_a", "shot_b"]:
            project_manager.ensure_shot_package(pid, sid)
        result = project_manager.list_shot_packages(pid)
        assert result == ["shot_a", "shot_b", "shot_c"]

    def test_list_shot_packages_nonexistent_project(self):
        assert project_manager.list_shot_packages("nope_proj") == []


# ===================================================================
# save_shot_output
# ===================================================================

class TestSaveShotOutput:
    def test_copies_file_into_outputs(self, tmp_projects_dir):
        proj = project_manager.create_project("OutputTest")
        pid = proj["id"]
        sid = "shot_out"

        # Create a source file to copy
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake image data")
            src = f.name

        try:
            dest = project_manager.save_shot_output(pid, sid, "keyframe", src)
            assert os.path.isfile(dest)
            assert dest.endswith("keyframe.png")
            with open(dest, "rb") as f:
                assert f.read() == b"fake image data"
        finally:
            os.unlink(src)


# ===================================================================
# project_lock context manager
# ===================================================================

class TestProjectLock:
    def test_lock_creates_dir_and_acquires(self, tmp_projects_dir):
        """Verify project_lock creates the project dir and can be entered/exited."""
        pid = "lock_test_id"
        proj_dir = os.path.join(tmp_projects_dir, pid)
        assert not os.path.isdir(proj_dir)
        with project_manager.project_lock(pid):
            # Directory should have been created by project_lock
            assert os.path.isdir(proj_dir)
        # After exiting, the directory still exists
        assert os.path.isdir(proj_dir)


# ===================================================================
# get_project_dir helper
# ===================================================================

class TestGetProjectDir:
    def test_returns_expected_path(self, tmp_projects_dir):
        result = project_manager.get_project_dir("my_id")
        assert result == os.path.join(tmp_projects_dir, "my_id")


class TestMutatorVariant1RaceProtection:
    """Variant 1 inner-mutator-validation under the per-project lock.

    Outer validate catches malformed input fast-fail. Inner validate
    catches the race where another writer mutates the project between
    outer validate and lock acquisition. Test that an inner-validation
    failure surfaces as ValidationError (not silent data corruption).
    """

    @pytest.fixture
    def valid_project(self, tmp_projects_dir):
        """Return a saved valid project for mutation tests."""
        proj = project_manager.make_project("RaceTest")
        project_manager.save_project(proj)
        return proj

    def test_outer_validation_raises_on_malformed_project(self, tmp_projects_dir):
        """Outer boundary validate catches malformed input before lock acquisition."""
        malformed = {"id": "bad_proj", "characters": "not_a_list"}  # missing 'name'; bad type
        with pytest.raises(ValidationError):
            project_manager.add_character(malformed, {"id": "c1", "name": "Alice", "description": ""})

    def test_inner_validation_raises_on_malformed_latest(self, valid_project, tmp_projects_dir):
        """Inner mutator-scope validate catches corruption that occurred between outer
        validate and lock acquisition (race simulation).

        We simulate the race by monkey-patching _load_project_unlocked (the
        function mutate_project calls inside the lock) to return a malformed
        snapshot. The outer validate sees a good project dict; the inner
        _Project.model_validate(latest) sees the corrupt snapshot and should
        raise ValidationError before any dict-write happens.

        Corruption type: a character dict with an integer id (survives
        normalize_project_schema, which only checks isinstance(..., list),
        but fails pydantic's str type check for Character.id).
        """
        import domain.project_manager as dpm
        from unittest.mock import patch

        # Corrupt snapshot: character with non-string id — normalize_project_schema
        # does not repair inner-dict field types, so the inner validate sees
        # this corrupt structure and raises ValidationError.
        corrupt_snapshot = dict(valid_project)
        corrupt_snapshot["characters"] = [
            {"id": 99999, "name": "BrokenIdType", "description": ""}
        ]

        with patch.object(dpm, "_load_project_unlocked", return_value=corrupt_snapshot):
            with pytest.raises(ValidationError):
                project_manager.add_character(
                    valid_project, {"id": "c1", "name": "Alice", "description": ""}
                )

    def test_outer_and_inner_validation_both_pass_for_valid_project(self, valid_project, tmp_projects_dir):
        """Sanity: a valid project passes both outer and inner validation
        and the mutation completes successfully."""
        char = project_manager.make_character("Bob", "Test character")
        result = project_manager.add_character(valid_project, char)
        assert result["id"] == char["id"]
        # Reload and verify the character was persisted
        reloaded = project_manager.load_project(valid_project["id"])
        ids = [c["id"] for c in reloaded["characters"]]
        assert char["id"] in ids


# ---------------------------------------------------------------------------
# normalize_project_schema — creative_llm read-time migration (618a6b3 residual)
# ---------------------------------------------------------------------------

class TestNormalizeCreativeLLMMigration:
    """Pure-dict, no I/O.  Mirrors VBench-drop test shape in domain/project_manager.py."""

    def _minimal_project(self, creative_llm=None):
        """Return a minimal project dict with only the keys normalize_project_schema
        touches, so the only mutation trigger is the creative_llm value."""
        proj = {
            "characters": [],
            "locations": [],
            "scenes": [],
            "global_settings": {},
        }
        if creative_llm is not None:
            proj["global_settings"]["creative_llm"] = creative_llm
        return proj

    def test_retired_sonnet_4_20250514_remapped(self):
        """claude-sonnet-4-20250514 → claude-sonnet-4-6, changed=True."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project("claude-sonnet-4-20250514")
        changed = normalize_project_schema(proj)
        assert changed is True
        assert proj["global_settings"]["creative_llm"] == "claude-sonnet-4-6"

    def test_stale_catalog_claude_sonnet_remapped(self):
        """claude-sonnet (bare, stale BE catalog value) → claude-sonnet-4-6, changed=True."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project("claude-sonnet")
        changed = normalize_project_schema(proj)
        assert changed is True
        assert proj["global_settings"]["creative_llm"] == "claude-sonnet-4-6"

    def test_auto_untouched(self):
        """creative_llm='auto' is not a retired id — untouched, changed=False."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project("auto")
        changed = normalize_project_schema(proj)
        assert changed is False
        assert proj["global_settings"]["creative_llm"] == "auto"

    def test_current_sonnet_4_6_untouched(self):
        """claude-sonnet-4-6 is already the target — must not be remapped."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project("claude-sonnet-4-6")
        changed = normalize_project_schema(proj)
        assert changed is False
        assert proj["global_settings"]["creative_llm"] == "claude-sonnet-4-6"

    def test_gpt4o_untouched(self):
        """Non-Anthropic model id passes through unchanged."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project("gpt-4o")
        changed = normalize_project_schema(proj)
        assert changed is False
        assert proj["global_settings"]["creative_llm"] == "gpt-4o"

    def test_missing_creative_llm_key_no_error(self):
        """global_settings without creative_llm key — no KeyError, no spurious change."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project()  # key absent
        assert "creative_llm" not in proj["global_settings"]
        changed = normalize_project_schema(proj)
        assert changed is False
        assert "creative_llm" not in proj["global_settings"]

    def test_unhashable_creative_llm_no_typeerror(self):
        """Malformed record with a non-str creative_llm (e.g. a list) must not
        raise inside load_project (quality-review M-1: `in` on the dict hashes
        the key). Value passes through untouched, changed=False."""
        from domain.project_manager import normalize_project_schema
        proj = self._minimal_project(["claude-sonnet"])  # list = unhashable
        changed = normalize_project_schema(proj)
        assert changed is False
        assert proj["global_settings"]["creative_llm"] == ["claude-sonnet"]

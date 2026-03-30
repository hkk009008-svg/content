import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import tempfile

import pytest

import project_manager


# ---------------------------------------------------------------------------
# Fixture: redirect PROJECTS_DIR to a temporary directory
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_projects_dir(monkeypatch):
    """Point project_manager.PROJECTS_DIR to a fresh temp dir for every test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(project_manager, "PROJECTS_DIR", tmpdir)
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
        assert ch["ip_adapter_weight"] == 0.85

    def test_custom_fields(self):
        ch = project_manager.make_character(
            "Bob", "Villain",
            reference_images=["img1.png"],
            voice_id="v42",
            ip_adapter_weight=0.5,
        )
        assert ch["reference_images"] == ["img1.png"]
        assert ch["voice_id"] == "v42"
        assert ch["ip_adapter_weight"] == 0.5

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

import importlib
import os
import pathlib
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import character_manager
import location_manager
import project_manager


def _load_web_server_with_stubs():
    def _module(name: str, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        return module

    class StubPipeline:
        def __init__(self, project_id: str, progress_callback=None):
            self.project_id = project_id
            self.progress_callback = progress_callback
            self.paused = False
            self.cancelled = False

        def generate(self, resume: bool = False):
            return "stub.mp4"

        def resume_info(self):
            return {"resumable": False}

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def cancel(self):
            self.cancelled = True

        def get_state(self):
            return {"paused": self.paused, "cancelled": self.cancelled}

        def regenerate_shot(self, scene_id: str, shot_id: str):
            return {"success": True, "scene_id": scene_id, "shot_id": shot_id}

    stubs = {
        "character_manager": _module(
            "character_manager",
            VOICE_POOL=[],
            create_character_with_images=lambda *args, **kwargs: {"id": "char_test"},
        ),
        "location_manager": _module(
            "location_manager",
            create_location_with_images=lambda *args, **kwargs: {"id": "loc_test"},
        ),
        "scene_decomposer": _module(
            "scene_decomposer",
            decompose_scene=lambda *args, **kwargs: [],
            update_scene_shots=lambda *args, **kwargs: None,
            CAMERA_MOTIONS=["zoom_in_slow"],
            VISUAL_EFFECTS=["cinematic_glow"],
            TARGET_APIS=["AUTO", "KLING_NATIVE"],
            API_REGISTRY={"AUTO": {"label": "Auto"}},
            MUSIC_MOODS=["suspense"],
        ),
        "dialogue_writer": _module(
            "dialogue_writer",
            generate_dialogue=lambda *args, **kwargs: [],
        ),
        "style_director": _module(
            "style_director",
            generate_style_rules=lambda *args, **kwargs: {"style": "ok"},
        ),
        "cinema_pipeline": _module("cinema_pipeline", CinemaPipeline=StubPipeline),
    }

    with mock.patch.dict(sys.modules, stubs):
        sys.modules.pop("web_server", None)
        return importlib.import_module("web_server")


class ProjectPersistenceBase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.projects_patch = mock.patch.object(
            project_manager, "PROJECTS_DIR", self.tempdir.name
        )
        self.projects_patch.start()
        self.addCleanup(self.projects_patch.stop)

    def create_project(self, name: str = "Test Project") -> dict:
        return project_manager.create_project(name)


class ProjectManagerMutationTests(ProjectPersistenceBase):
    def test_mutate_project_preserves_concurrent_updates(self):
        project = self.create_project()
        barrier = threading.Barrier(3)
        errors = []

        def worker(index: int):
            try:
                barrier.wait()

                def _mutate(latest_project: dict):
                    latest_project["characters"].append(
                        {"id": f"char_{index}", "name": f"Character {index}"}
                    )

                project_manager.mutate_project(project["id"], _mutate, timeout=1)
            except Exception as exc:  # pragma: no cover - test failure capture
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(1,)),
            threading.Thread(target=worker, args=(2,)),
        ]
        for thread in threads:
            thread.start()

        barrier.wait()
        for thread in threads:
            thread.join()

        latest_project = project_manager.load_project(project["id"])
        self.assertEqual(
            {character["id"] for character in latest_project["characters"]},
            {"char_1", "char_2"},
        )
        self.assertEqual(errors, [])

    def test_mutate_project_acquires_lock_once(self):
        project = self.create_project()
        enter_count = 0

        class FakeLock:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                nonlocal enter_count
                enter_count += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with mock.patch.object(project_manager, "FileLock", FakeLock):
            project_manager.mutate_project(
                project["id"],
                lambda latest_project: latest_project["global_settings"].update(
                    {"music_mood": "hopeful"}
                ),
            )

        self.assertEqual(enter_count, 1)

    def test_mutate_project_timeout_raises_project_lock_error(self):
        project = self.create_project()
        acquired = threading.Event()
        release = threading.Event()

        def holder():
            with project_manager.project_lock(project["id"], timeout=1):
                acquired.set()
                release.wait()

        thread = threading.Thread(target=holder)
        thread.start()
        self.addCleanup(thread.join)
        self.assertTrue(acquired.wait(timeout=1))

        with self.assertRaises(project_manager.ProjectLockError):
            project_manager.mutate_project(
                project["id"],
                lambda latest_project: latest_project.update({"name": "blocked"}),
                timeout=0.05,
            )

        release.set()
        thread.join(timeout=1)


class AssetCommitFailureTests(ProjectPersistenceBase):
    def _make_temp_image(self) -> str:
        image_path = pathlib.Path(self.tempdir.name) / "ref.jpg"
        image_path.write_bytes(b"not-a-real-image")
        return str(image_path)

    def test_character_asset_prep_cleans_up_on_commit_failure(self):
        project = self.create_project()
        image_path = self._make_temp_image()

        with mock.patch.object(
            character_manager, "DEEPFACE_AVAILABLE", False
        ), mock.patch.object(
            character_manager, "FAL_AVAILABLE", False
        ), mock.patch.object(
            character_manager,
            "add_character",
            side_effect=project_manager.ProjectLockError(project["id"], 0.05),
        ):
            with self.assertRaises(project_manager.ProjectLockError):
                character_manager.create_character_with_images(
                    project,
                    "Alice",
                    "Hero",
                    reference_image_paths=[image_path],
                )

        characters_dir = pathlib.Path(project_manager.get_project_dir(project["id"])) / "characters"
        self.assertEqual(list(characters_dir.iterdir()), [])

    def test_location_asset_prep_cleans_up_on_commit_failure(self):
        project = self.create_project()
        image_path = self._make_temp_image()

        with mock.patch.object(
            location_manager,
            "add_location",
            side_effect=project_manager.ProjectLockError(project["id"], 0.05),
        ):
            with self.assertRaises(project_manager.ProjectLockError):
                location_manager.create_location_with_images(
                    project,
                    "Warehouse",
                    "Dim industrial warehouse",
                    reference_image_paths=[image_path],
                )

        locations_dir = pathlib.Path(project_manager.get_project_dir(project["id"])) / "locations"
        self.assertEqual(list(locations_dir.iterdir()), [])


class WebServerPersistenceTests(ProjectPersistenceBase):
    @classmethod
    def setUpClass(cls):
        cls.web_server = _load_web_server_with_stubs()
        cls.web_server.app.testing = True

    def setUp(self):
        super().setUp()
        self.client = self.web_server.app.test_client()
        self.web_server._running_pipelines.clear()
        self.web_server._progress_queues.clear()
        self.timeout_patch = mock.patch.object(
            self.web_server, "HTTP_PROJECT_TIMEOUT", 0.05
        )
        self.timeout_patch.start()
        self.addCleanup(self.timeout_patch.stop)

    def _create_project_with_shot(self) -> dict:
        project = self.create_project()

        def _mutate(latest_project: dict):
            latest_project["scenes"] = [
                {
                    "id": "scene_1",
                    "order": 0,
                    "title": "Scene 1",
                    "location_id": "",
                    "characters_present": [],
                    "action": "",
                    "dialogue": "",
                    "mood": "neutral",
                    "camera_direction": "",
                    "duration_seconds": 5.0,
                    "num_shots": 1,
                    "shots": [
                        {
                            "id": "shot_1",
                            "prompt": "original prompt",
                            "camera": "zoom_in_slow",
                            "visual_effect": "cinematic_glow",
                            "target_api": "AUTO",
                            "scene_foley": "",
                            "characters_in_frame": [],
                            "primary_character": "",
                        }
                    ],
                }
            ]

        project_manager.mutate_project(project["id"], _mutate)
        return project_manager.load_project(project["id"])

    def test_read_endpoint_succeeds_while_lock_contended(self):
        project = self.create_project()
        acquired = threading.Event()

        def holder():
            with project_manager.project_lock(project["id"], timeout=1):
                acquired.set()
                time.sleep(0.1)

        thread = threading.Thread(target=holder)
        thread.start()
        self.addCleanup(thread.join)
        self.assertTrue(acquired.wait(timeout=1))

        response = self.client.get(f"/api/projects/{project['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], project["id"])

        thread.join(timeout=1)

    def test_mutating_endpoints_return_project_locked(self):
        project = self.create_project()
        cases = [
            (
                "project",
                "put",
                f"/api/projects/{project['id']}",
                {"json": {"name": "Renamed"}},
                mock.patch.object(
                    self.web_server,
                    "mutate_project",
                    side_effect=project_manager.ProjectLockError(project["id"], 0.05),
                ),
            ),
            (
                "character",
                "post",
                f"/api/projects/{project['id']}/characters",
                {"data": {"name": "Alice", "description": "Hero"}},
                mock.patch.object(
                    self.web_server,
                    "create_character_with_images",
                    side_effect=project_manager.ProjectLockError(project["id"], 0.05),
                ),
            ),
            (
                "location",
                "post",
                f"/api/projects/{project['id']}/locations",
                {"data": {"name": "Warehouse", "description": "Dark"}},
                mock.patch.object(
                    self.web_server,
                    "create_location_with_images",
                    side_effect=project_manager.ProjectLockError(project["id"], 0.05),
                ),
            ),
            (
                "scene",
                "post",
                f"/api/projects/{project['id']}/scenes",
                {"json": {"title": "Scene 1"}},
                mock.patch.object(
                    self.web_server,
                    "add_scene",
                    side_effect=project_manager.ProjectLockError(project["id"], 0.05),
                ),
            ),
            (
                "style",
                "post",
                f"/api/projects/{project['id']}/style-rules",
                {"json": {}},
                mock.patch.object(
                    self.web_server,
                    "mutate_project",
                    side_effect=project_manager.ProjectLockError(project["id"], 0.05),
                ),
            ),
        ]

        for label, method, path, kwargs, patcher in cases:
            with self.subTest(label=label):
                with patcher:
                    response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.get_json()["code"], "project_locked")
                self.assertTrue(response.get_json()["retryable"])

    def test_general_project_mutations_return_project_busy_while_generation_runs(self):
        project = self.create_project()
        self.web_server._running_pipelines[project["id"]] = object()

        cases = [
            ("put", f"/api/projects/{project['id']}", {"json": {"name": "Renamed"}}),
            (
                "post",
                f"/api/projects/{project['id']}/characters",
                {"data": {"name": "Alice", "description": "Hero"}},
            ),
            (
                "post",
                f"/api/projects/{project['id']}/locations",
                {"data": {"name": "Warehouse", "description": "Dark"}},
            ),
            ("post", f"/api/projects/{project['id']}/scenes", {"json": {"title": "Scene 1"}}),
            ("post", f"/api/projects/{project['id']}/style-rules", {"json": {}}),
        ]

        for method, path, kwargs in cases:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.get_json()["code"], "project_busy")
                self.assertTrue(response.get_json()["retryable"])

    def test_allowed_generation_control_and_shot_review_endpoints_remain_available(self):
        project = self._create_project_with_shot()

        class RunningPipeline:
            def __init__(self):
                self.paused = False
                self.cancelled = False

            def pause(self):
                self.paused = True

            def resume(self):
                self.paused = False

            def cancel(self):
                self.cancelled = True

            def get_state(self):
                return {"paused": self.paused, "cancelled": self.cancelled}

            def regenerate_shot(self, scene_id: str, shot_id: str):
                return {"success": True, "scene_id": scene_id, "shot_id": shot_id}

        pipeline = RunningPipeline()
        self.web_server._running_pipelines[project["id"]] = pipeline

        pause_response = self.client.post(f"/api/projects/{project['id']}/pause")
        self.assertEqual(pause_response.status_code, 200)
        self.assertEqual(pause_response.get_json(), {"paused": True})

        prompt_response = self.client.put(
            f"/api/projects/{project['id']}/shots/shot_1/prompt",
            json={"prompt": "updated prompt"},
        )
        self.assertEqual(prompt_response.status_code, 200)
        self.assertEqual(prompt_response.get_json()["updated"], True)

        latest_project = project_manager.load_project(project["id"])
        self.assertEqual(
            latest_project["scenes"][0]["shots"][0]["prompt"], "updated prompt"
        )


if __name__ == "__main__":
    unittest.main()

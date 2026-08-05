"""Artifact history and one-click client-package API contracts."""

from __future__ import annotations

import io
from pathlib import Path
import zipfile

from flask import Flask

import project_manager
from cinema.artifact_versions import ArtifactVersionStore, DISTRIBUTION_CLIENT
import web_artifacts


def _app():
    app = Flask(__name__)
    app.register_blueprint(web_artifacts.artifact_api)
    return app


def _project(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(projects))
    project = project_manager.create_project("Artifact API")
    root = Path(project_manager.get_project_dir(project["id"]))
    return project, root


def test_empty_history_get_is_read_only(tmp_path, monkeypatch):
    project, root = _project(tmp_path, monkeypatch)

    with _app().test_client() as client:
        response = client.get(f"/api/projects/{project['id']}/artifacts")

    assert response.status_code == 200
    assert response.get_json() == {
        "current": [],
        "records": [],
        "has_more": False,
        "next_before_sequence": None,
    }
    assert not (root / ".artifact_versions").exists()


def test_package_adopts_legacy_final_is_deterministic_and_downloads_by_hash(
    tmp_path, monkeypatch
):
    project, root = _project(tmp_path, monkeypatch)
    final = root / "exports" / "final_cinema.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"accepted final video")
    app = _app()

    with app.test_client() as client:
        first = client.post(f"/api/projects/{project['id']}/deliverables/package", json={})
        second = client.post(f"/api/projects/{project['id']}/deliverables/package", json={})
        download = client.get(first.get_json()["download_url"])
        history = client.get(f"/api/projects/{project['id']}/artifacts")

    try:
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.get_json()["sha256"] == second.get_json()["sha256"]
        assert first.get_json()["filename"] == (
            f"{project['id']}-deliverables-{first.get_json()['sha256']}.zip"
        )
        assert "path" not in first.get_json()
        assert download.status_code == 200
        assert download.mimetype == "application/zip"
        assert download.headers["Content-Disposition"].startswith("attachment;")
        current = history.get_json()["current"]
        assert len(current) == 1
        assert current[0]["logical_name"] == "final/master"
        assert current[0]["distribution_class"] == DISTRIBUTION_CLIENT
        assert current[0]["reproducibility"]["status"] == "output_hash_only"
        assert current[0]["parameters"] == {}
        assert "path" not in current[0]
        assert "object_path" not in current[0]
    finally:
        download.close()


def test_package_rejects_cross_project_ids_and_detects_tamper(tmp_path, monkeypatch):
    project, root = _project(tmp_path, monkeypatch)
    final = root / "exports" / "final_cinema.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"video")
    store = ArtifactVersionStore.for_project(project["id"])
    record = store.record_artifact(
        "final/master",
        final,
        distribution_class=DISTRIBUTION_CLIENT,
    )
    app = _app()

    with app.test_client() as client:
        unknown = client.post(
            f"/api/projects/{project['id']}/deliverables/package",
            json={"artifact_ids": ["av-999999999999-aaaaaaaaaaaa"]},
        )
        built = client.post(
            f"/api/projects/{project['id']}/deliverables/package",
            json={"artifact_ids": [record["artifact_id"]]},
        )
        package_path = (
            root
            / "exports"
            / "client_packages"
            / built.get_json()["filename"]
        )
        package_path.write_bytes(b"tampered")
        tampered = client.get(built.get_json()["download_url"])

    assert unknown.status_code == 404
    assert tampered.status_code == 409


def test_content_addressed_download_keeps_old_verified_package_during_new_build(
    tmp_path, monkeypatch
):
    project, root = _project(tmp_path, monkeypatch)
    final = root / "exports" / "final_cinema.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"version-one")
    store = ArtifactVersionStore.for_project(project["id"])
    first_record = store.record_artifact(
        "final/master",
        final,
        distribution_class=DISTRIBUTION_CLIENT,
    )

    with _app().test_client() as client:
        first = client.post(
            f"/api/projects/{project['id']}/deliverables/package",
            json={"artifact_ids": [first_record["artifact_id"]]},
        )
        final.write_bytes(b"version-two")
        second_record = store.record_artifact(
            "final/master",
            final,
            distribution_class=DISTRIBUTION_CLIENT,
        )
        second = client.post(
            f"/api/projects/{project['id']}/deliverables/package",
            json={"artifact_ids": [second_record["artifact_id"]]},
        )
        old_download = client.get(first.get_json()["download_url"])
        new_download = client.get(second.get_json()["download_url"])

    try:
        assert first.get_json()["filename"] != second.get_json()["filename"]
        assert old_download.status_code == 200
        assert new_download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(old_download.data)) as archive:
            assert archive.read("deliverables/final_cinema.mp4") == b"version-one"
        with zipfile.ZipFile(io.BytesIO(new_download.data)) as archive:
            assert archive.read("deliverables/final_cinema.mp4") == b"version-two"
    finally:
        old_download.close()
        new_download.close()


def test_history_is_bounded_and_validates_query(tmp_path, monkeypatch):
    project, root = _project(tmp_path, monkeypatch)
    exports = root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    store = ArtifactVersionStore.for_project(project["id"])
    for index in range(3):
        path = exports / f"asset-{index}.png"
        path.write_bytes(f"asset-{index}".encode())
        store.record_artifact(f"asset/{index}", path)

    with _app().test_client() as client:
        page = client.get(f"/api/projects/{project['id']}/artifacts?limit=2")
        invalid = client.get(f"/api/projects/{project['id']}/artifacts?limit=0")

    assert page.status_code == 200
    assert [record["sequence"] for record in page.get_json()["records"]] == [3, 2]
    assert page.get_json()["has_more"] is True
    assert page.get_json()["next_before_sequence"] == 2
    assert invalid.status_code == 400

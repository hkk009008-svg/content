from __future__ import annotations

import hashlib
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cinema.artifact_versions import (
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactValidationError,
    ArtifactVersionStore,
    ClientPackageBuilder,
)


def _project(tmp_path: Path, project_id: str = "project-a") -> tuple[Path, ArtifactVersionStore]:
    root = tmp_path / project_id
    (root / "exports").mkdir(parents=True)
    return root, ArtifactVersionStore(project_id, root)


def _write(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_record_is_complete_idempotent_and_monotonic(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"first accepted bytes")
    source_hash = hashlib.sha256(b"source").hexdigest()
    dependency_hash = hashlib.sha256(b"ffmpeg-build").hexdigest()

    first = store.record_artifact(
        "final/master",
        output,
        media_type="video/mp4",
        provider="runway",
        model="gen-4.5",
        parameters={"duration": 5, "aspect_ratio": "16:9"},
        seed=42001,
        source_hashes={"approved-take": source_hash},
        dependency_hashes={"ffmpeg": dependency_hash},
        distribution_class="client_deliverable",
    )
    retry = store.record_artifact(
        "final/master",
        "exports/final.mp4",
        media_type="video/mp4",
        provider="runway",
        model="gen-4.5",
        parameters={"aspect_ratio": "16:9", "duration": 5},
        seed=42001,
        source_hashes={"approved-take": source_hash},
        dependency_hashes={"ffmpeg": dependency_hash},
        distribution_class="client_deliverable",
    )

    assert retry == first
    assert first["artifact_id"].startswith("av-000000000001-")
    assert first["sequence"] == 1
    assert first["version"] == 1
    assert first["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert first["byte_size"] == len(output.read_bytes())
    assert first["path"] == "exports/final.mp4"
    assert first["object_path"] == f".artifact_versions/objects/{first['sha256']}"
    assert (root / first["object_path"]).read_bytes() == b"first accepted bytes"
    assert first["source_hashes"] == {"approved-take": source_hash}
    assert first["dependency_hashes"] == {"ffmpeg": dependency_hash}
    assert first["created_at"].endswith("Z")
    assert first["reproducibility"]["status"] == "provider_replay_only"
    assert first["reproducibility"]["bit_exact"] is False

    output.write_bytes(b"second accepted bytes")
    second = store.record_artifact(
        "final/master",
        output,
        media_type="video/mp4",
        provider="runway",
        model="gen-4.5",
        parameters={"duration": 5, "aspect_ratio": "16:9"},
        seed=42001,
        source_hashes={"approved-take": source_hash},
        dependency_hashes={"ffmpeg": dependency_hash},
        distribution_class="client_deliverable",
    )
    poster = _write(root, "exports/poster.png", b"poster")
    third = store.record_artifact("poster", poster, distribution_class="client_deliverable")

    assert (second["sequence"], second["version"]) == (2, 2)
    assert (third["sequence"], third["version"]) == (3, 1)
    assert [item["version"] for item in store.history("final/master")] == [1, 2]
    assert store.current("final/master") == second
    assert store.get(first["artifact_id"]) == first
    assert store.verify_artifact(first["artifact_id"]) is True
    assert store.verify_artifact(second["artifact_id"]) is True


def test_empty_history_is_read_only(tmp_path: Path) -> None:
    root, store = _project(tmp_path)

    assert store.history() == []
    assert store.current("not-created") is None
    assert not (root / ".artifact_versions").exists()


def test_local_recipe_status_still_does_not_claim_bit_exact_replay(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/master.wav", b"waveform")
    source_hash = hashlib.sha256(b"stems").hexdigest()
    record = store.record_artifact(
        "audio/master",
        output,
        model="ffmpeg-7",
        parameters={"loudness_lufs": -14},
        seed=0,
        source_hashes={"stems": source_hash},
    )
    assert record["reproducibility"]["status"] == "recipe_captured"
    assert record["reproducibility"]["bit_exact"] is False


def test_record_rejects_traversal_external_files_and_symlink_escape(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    outside = _write(tmp_path, "outside.mp4", b"outside")

    with pytest.raises(ArtifactPathError):
        store.record_artifact("escape", "../outside.mp4")
    with pytest.raises(ArtifactPathError):
        store.record_artifact("escape", outside)

    link = root / "exports" / "escape.mp4"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not supported by this filesystem")
    with pytest.raises(ArtifactPathError):
        store.record_artifact("escape", link)


def test_record_rejects_symlinked_ledger_state_directory(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"video")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        (root / ".artifact_versions").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not supported by this filesystem")

    with pytest.raises(ArtifactPathError):
        store.record_artifact("final", output)
    assert list(elsewhere.iterdir()) == []


def test_store_rejects_symlinked_project_root(tmp_path: Path) -> None:
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    alias = tmp_path / "project-a"
    try:
        alias.symlink_to(real_project, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not supported by this filesystem")

    with pytest.raises(ArtifactPathError, match="project root cannot be a symlink"):
        ArtifactVersionStore("project-a", alias)
    assert list(real_project.iterdir()) == []


def test_parameters_reject_credentials_and_non_finite_values(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"video")

    with pytest.raises(ArtifactValidationError, match="credential"):
        store.record_artifact("final", output, parameters={"headers": {"api-key": "nope"}})
    for credential_key in (
        "openai_api_key",
        "x-api-key",
        "access_token",
        "client_secret",
        "fal_key",
    ):
        with pytest.raises(ArtifactValidationError, match="credential"):
            store.record_artifact(
                "final",
                output,
                parameters={"nested": {credential_key: "must-not-enter-ledger"}},
            )
    with pytest.raises(ArtifactValidationError, match="finite JSON"):
        store.record_artifact("final", output, parameters={"guidance": float("nan")})
    with pytest.raises(ArtifactValidationError, match="SHA-256"):
        store.record_artifact("final", output, source_hashes={"source": "short"})


def test_concurrent_writers_are_idempotent_and_sequences_have_no_gaps(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    shared = _write(root, "exports/shared.mp4", b"shared")

    with ThreadPoolExecutor(max_workers=8) as pool:
        identical = list(pool.map(lambda _: store.record_artifact("shared", shared), range(24)))
    assert len({item["artifact_id"] for item in identical}) == 1
    assert len(store.history()) == 1

    paths = [_write(root, f"exports/asset-{index}.png", f"image-{index}".encode()) for index in range(16)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda pair: store.record_artifact(f"asset/{pair[0]}", pair[1]), enumerate(paths)))

    history = store.history()
    assert [item["sequence"] for item in history] == list(range(1, 18))
    assert len({item["artifact_id"] for item in history}) == 17


def test_ledger_tamper_is_detected_before_queries_return_records(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"video")
    store.record_artifact("final", output)

    ledger_file = root / ".artifact_versions" / "records" / "record-000000000001.json"
    ledger_file.chmod(0o600)
    tampered = json.loads(ledger_file.read_text(encoding="utf-8"))
    tampered["model"] = "silently-edited"
    ledger_file.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="hash mismatch"):
        store.history()


def test_client_package_is_deterministic_sorted_and_safe_by_construction(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    video = _write(root, "exports/final.mp4", b"final-video")
    captions = _write(root, "exports/captions.srt", b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    video_record = store.record_artifact(
        "final/video",
        video,
        media_type="video/mp4",
        provider="veo",
        model="veo-3.1",
        parameters={"prompt": "internal prompt must not enter client manifest"},
        seed="provider-assigned",
        distribution_class="client_deliverable",
    )
    caption_record = store.record_artifact(
        "final/captions",
        captions,
        media_type="application/x-subrip",
        distribution_class="client_deliverable",
    )

    builder = ClientPackageBuilder(store)
    first = builder.build(
        "delivery-a",
        artifact_ids=[video_record["artifact_id"], caption_record["artifact_id"]],
    )
    second = builder.build(
        "delivery-b",
        artifact_ids=[caption_record["artifact_id"], video_record["artifact_id"]],
    )

    first_bytes = Path(first.path).read_bytes()
    second_bytes = Path(second.path).read_bytes()
    assert first_bytes == second_bytes
    assert first.sha256 == hashlib.sha256(first_bytes).hexdigest() == second.sha256
    assert first.entry_count == 4

    with zipfile.ZipFile(first.path) as archive:
        assert archive.namelist() == [
            "MANIFEST.json",
            "SHA256SUMS.txt",
            "deliverables/captions.srt",
            "deliverables/final.mp4",
        ]
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        manifest_bytes = archive.read("MANIFEST.json")
        manifest = json.loads(manifest_bytes)
        assert manifest["project_id"] == "project-a"
        assert [entry["archive_path"] for entry in manifest["artifacts"]] == [
            "deliverables/captions.srt",
            "deliverables/final.mp4",
        ]
        assert all("parameters" not in entry for entry in manifest["artifacts"])
        assert all("path" not in entry for entry in manifest["artifacts"])
        assert all(len(entry["provenance_sha256"]) == 64 for entry in manifest["artifacts"])
        assert manifest["artifacts"][1]["source_hashes"] == {}
        assert manifest["artifacts"][1]["dependency_hashes"] == {}
        checksum_lines = archive.read("SHA256SUMS.txt").decode().splitlines()
        assert checksum_lines[0] == f"{hashlib.sha256(manifest_bytes).hexdigest()}  MANIFEST.json"
        for line in checksum_lines[1:]:
            digest, archive_path = line.split("  ", 1)
            assert hashlib.sha256(archive.read(archive_path)).hexdigest() == digest


@pytest.mark.parametrize(
    ("relative_path", "media_type"),
    [
        ("temp/intermediate.mp4", "video/mp4"),
        ("exports/checkpoints/state.mp4", "video/mp4"),
        ("exports/runtime.db", "application/octet-stream"),
        ("exports/secret.txt", "text/plain"),
    ],
)
def test_client_package_rejects_non_allowlisted_or_sensitive_records(
    tmp_path: Path,
    relative_path: str,
    media_type: str,
) -> None:
    root, store = _project(tmp_path)
    output = _write(root, relative_path, b"not for clients")
    record = store.record_artifact(
        "candidate",
        output,
        media_type=media_type,
        distribution_class="client_deliverable",
    )

    with pytest.raises(ArtifactValidationError):
        ClientPackageBuilder(store).build("delivery", artifact_ids=[record["artifact_id"]])


def test_client_package_rejects_internal_records_and_unsafe_output_name(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"video")
    record = store.record_artifact("final", output)
    builder = ClientPackageBuilder(store)

    with pytest.raises(ArtifactValidationError, match="client_deliverable"):
        builder.build("delivery", artifact_ids=[record["artifact_id"]])
    with pytest.raises(ArtifactValidationError, match="package_name"):
        builder.build("../delivery", artifact_ids=[record["artifact_id"]])


def test_publication_overwrite_preserves_version_and_object_tamper_cannot_replace_package(
    tmp_path: Path,
) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"accepted-video")
    record = store.record_artifact(
        "final",
        output,
        media_type="video/mp4",
        distribution_class="client_deliverable",
    )
    builder = ClientPackageBuilder(store)
    good = builder.build("delivery", artifact_ids=[record["artifact_id"]])
    good_bytes = Path(good.path).read_bytes()

    output.write_bytes(b"tampered-video")
    assert store.verify_artifact(record["artifact_id"]) is True
    rebuilt = builder.build("delivery", artifact_ids=[record["artifact_id"]])
    assert Path(rebuilt.path).read_bytes() == good_bytes

    retained = root / record["object_path"]
    retained.chmod(0o600)
    retained.write_bytes(b"tampered-retained-object")
    with pytest.raises(ArtifactIntegrityError, match="hash mismatch"):
        store.verify_artifact(record["artifact_id"])
    with pytest.raises(ArtifactIntegrityError, match="do not match"):
        builder.build("delivery", artifact_ids=[record["artifact_id"]])
    assert Path(good.path).read_bytes() == good_bytes
    assert not list((root / "exports" / "client_packages").glob("*.tmp"))


def test_client_can_package_an_explicit_historical_version_after_publication_changes(
    tmp_path: Path,
) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"version-one")
    first = store.record_artifact(
        "final/master",
        output,
        media_type="video/mp4",
        distribution_class="client_deliverable",
    )
    output.write_bytes(b"version-two")
    second = store.record_artifact(
        "final/master",
        output,
        media_type="video/mp4",
        distribution_class="client_deliverable",
    )

    package = ClientPackageBuilder(store).build(
        "historical-delivery",
        artifact_ids=[first["artifact_id"]],
    )

    assert first["sha256"] != second["sha256"]
    with zipfile.ZipFile(package.path) as archive:
        assert archive.read("deliverables/final.mp4") == b"version-one"


def test_symlinked_exports_directory_cannot_receive_a_package(tmp_path: Path) -> None:
    root, store = _project(tmp_path)
    output = _write(root, "exports/final.mp4", b"video")
    record = store.record_artifact(
        "final",
        output,
        media_type="video/mp4",
        distribution_class="client_deliverable",
    )
    real_exports = tmp_path / "moved-exports"
    (root / "exports").rename(real_exports)
    try:
        (root / "exports").symlink_to(real_exports, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not supported by this filesystem")

    with pytest.raises(ArtifactPathError, match="plain directory"):
        ClientPackageBuilder(store).build(
            "delivery",
            artifact_ids=[record["artifact_id"]],
        )
    assert not (real_exports / "client_packages").exists()

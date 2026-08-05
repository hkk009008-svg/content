"""Regression coverage for charmgr-cost-fresh-instance (W2 provisional CRITICAL).

ROW: charmgr-cost-fresh-instance
FILE: domain/character_manager.py:350
BUG: _generate_multi_angle_refs used to construct a fresh CostTracker() and call
  record_api_call('FLUX_KONTEXT', ...) on it for every angle generated. Spend landed
  on a throwaway accumulator instead of the caller/project tracker.

FIX: create_character_with_images threads a tracker into _generate_multi_angle_refs,
  and paid attempts require that caller-owned authority. No fallback tracker is
  created inside the character flow.
"""

import os
from unittest.mock import MagicMock, patch


def test_create_character_with_images_threads_project_tracker_to_angles(tmp_path, monkeypatch):
    import domain.character_manager as cm

    shared_tracker = object()

    captured = {}

    def fake_generate(
        canonical_path,
        char_path,
        description,
        cost_tracker=None,
        video_id="",
        character_id="",
        artifact_evidence_out=None,
    ):
        captured["cost_tracker"] = cost_tracker
        captured["video_id"] = video_id
        captured["character_id"] = character_id
        return [canonical_path]

    project_root = tmp_path / "projects"
    canonical_path = tmp_path / "canonical.jpg"
    canonical_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 12)

    project = {
        "id": "proj-charmgr",
        "characters": [],
        "global_settings": {"budget_limit_usd": "12.5", "language": "en"},
    }

    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", False)
    monkeypatch.setattr(cm, "get_project_dir", lambda pid: str(project_root / pid))
    monkeypatch.setattr(
        cm,
        "_find_canonical_from_uploads",
        lambda character, char_path: str(canonical_path),
    )
    monkeypatch.setattr(cm, "_generate_multi_angle_refs", fake_generate)
    monkeypatch.setattr(
        cm,
        "assign_voice",
        lambda project, language="", gender="": "voice-test",
    )
    monkeypatch.setattr(
        cm,
        "add_character",
        lambda project, character, timeout=10: project["characters"].append(character),
    )

    cm.create_character_with_images(
        project,
        name="Tracked Character",
        description="cost tracking caller path",
        reference_image_paths=[str(canonical_path)],
        cost_tracker=shared_tracker,
    )

    assert captured["cost_tracker"] is shared_tracker
    assert captured["video_id"] == "proj-charmgr"
    assert captured["character_id"].startswith("char_")


def test_multi_angle_refs_fail_closed_without_paid_attempt_authority(
    tmp_path, monkeypatch,
):
    import pytest
    import domain.character_manager as cm

    canonical = tmp_path / "canonical.jpg"
    canonical.write_bytes(b"jpeg")
    monkeypatch.setattr(cm, "FAL_AVAILABLE", True)
    monkeypatch.setattr(cm, "settings", MagicMock(fal_key="fake-key"))

    with pytest.raises(TypeError, match="shared paid-attempt tracker"):
        cm._generate_multi_angle_refs(
            str(canonical),
            str(tmp_path),
            "description",
            cost_tracker=None,
            video_id="proj-charmgr",
            character_id="char-test",
        )


def test_multi_angle_refs_spend_lands_on_shared_tracker(tmp_path, request):
    """Spend from FLUX_KONTEXT multi-angle calls must land on a caller-supplied tracker.

    Passes cost_tracker=shared_tracker (the injection seam the fix adds) and patches
    fal_client + safe_download so the function reaches the cost-recording block without
    real network I/O. The shared CostTracker must accumulate nonzero spend.
    """
    from cost_tracker import CostTracker, API_COST_USD

    # Precondition: FLUX_KONTEXT must be a priced API so spend is nonzero.
    assert API_COST_USD.get("FLUX_KONTEXT", 0.0) > 0.0, (
        "precondition: FLUX_KONTEXT must be priced in API_COST_USD"
    )

    # Shared tracker the caller would inject after the fix.
    shared_tracker = CostTracker(
        db_path=str(tmp_path / "shared.db"),
        budget_usd=100.0,
    )
    request.addfinalizer(shared_tracker.close)
    assert shared_tracker.spent_usd == 0.0, "precondition: shared tracker starts at $0"

    # Set up a temporary char_path directory.
    char_path = str(tmp_path / "char")
    os.makedirs(char_path)

    # Fake canonical image file (content doesn't matter — FAL is mocked).
    canonical_path = str(tmp_path / "canonical.jpg")
    with open(canonical_path, "wb") as fh:
        fh.write(b"\xff\xd8\xff\xe0" + b"\x00" * 12)  # minimal JPEG header

    # Fake FAL queue: upload returns a URL; submit exposes a durable request ID.
    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "https://fal.example/canonical.jpg"
    fake_fal.submit.return_value = MagicMock(request_id="fal-angle-request")
    fake_fal.status.return_value = {"status": "COMPLETED"}
    fake_fal.result.return_value = {
        "images": [{"url": "https://fal.example/angle.jpg"}]
    }

    def fake_download(_url, output, **_kwargs):
        with open(output, "wb") as handle:
            handle.write(b"jpeg")
        return output

    with (
        patch.dict(
            "sys.modules",
            {"fal_client": fake_fal},
        ),
        patch(
            "domain.character_manager.fal_client",
            fake_fal,
        ),
        patch(
            "domain.character_manager.FAL_AVAILABLE",
            True,
        ),
        patch(
            "domain.character_manager.settings",
            MagicMock(fal_key="fake-key"),
        ),
        patch(
            "domain.character_manager.safe_download",
            side_effect=fake_download,
        ),
        patch(
            "domain.character_manager._ANGLE_CONFIGS",
            ({"name": "angle_45", "prompt": "Turn 45 degrees."},),
        ),
    ):
        from domain.character_manager import _generate_multi_angle_refs

        # Pass the shared tracker via the injection seam the fix adds.
        _generate_multi_angle_refs(
            canonical_path=canonical_path,
            char_path=char_path,
            description="Test character for cost-tracking pin",
            cost_tracker=shared_tracker,
            video_id="project-character",
            character_id="char-character",
        )

    # FIXED behaviour: at least one FLUX_KONTEXT call's cost lands on shared_tracker.
    assert shared_tracker.spent_usd > 0.0, (
        f"shared_tracker.spent_usd={shared_tracker.spent_usd!r} after "
        "_generate_multi_angle_refs — FLUX_KONTEXT spend landed on a throwaway "
        "CostTracker() instead of the caller-supplied tracker "
        "(charmgr-cost-fresh-instance, character_manager.py:350)"
    )

"""Regression tests for the subject-size floors in `_count_faces`.

WHY THESE EXIST
---------------
`_count_faces` gates character creation: `character_manager.py` rejects any
reference image reporting >= 2 faces, because two subjects corrupt the embedding
(the pipeline reads `emb_list[0]` without knowing whose face it is).

Measured 2026-08-08 on this project's own reference set, the unfiltered count
rejected the subject's OWN canonical photograph. A 4032x3024 frame yields the
real face at 1664x1664 (22.7% of frame) and a 58x58 speck at 0.0276% — and the
speck is detected at confidence 0.98 against the real face's 0.94, so ordering
by confidence separates nothing. Four of ten images tripped it.

WHY THESE ARE UNIT TESTS OVER A FAKE DETECTOR
--------------------------------------------
A synthetic two-subject image cannot be built here. The detector is acutely
sensitive to JPEG re-encoding: re-saving the canonical at quality 95 with NO
geometry change drops it from 1 detected face to 0. Half-scaling drops it to 0.
Pasting it beside itself drops it to 0. So any PIL-constructed control tests the
encoder, not the guard.

What changed is the AREA FILTERING, so that is what these exercise, with the
detector faked and the geometry controlled exactly. One integration test then
pins the real photograph, which is the known value the floors were derived from.
"""

from __future__ import annotations

import pytest

import domain.character_manager as cm


def _face(width: int, height: int, confidence: float = 0.95) -> dict:
    return {"facial_area": {"x": 0, "y": 0, "w": width, "h": height},
            "confidence": confidence}


@pytest.fixture
def fake_detector(monkeypatch):
    """Drive `_count_faces` with exact detections and a known frame size."""

    def _install(faces, frame_pixels=4032 * 3024):
        monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)
        monkeypatch.setattr(
            cm.DeepFace, "extract_faces", lambda **_kwargs: list(faces)
        )
        monkeypatch.setattr(cm, "_image_pixel_area", lambda _path: frame_pixels)

    return _install


def test_the_measured_canonical_geometry_counts_as_one(fake_detector):
    """The exact geometry that used to reject the subject's own photograph.

    Real face 1664x1664 (22.7% of a 4032x3024 frame) plus a 58x58 speck
    (0.0276%), the speck detected at HIGHER confidence than the real face.
    """

    fake_detector([_face(1664, 1664, 0.94), _face(58, 58, 0.98)])
    assert cm._count_faces("irrelevant.jpg") == 1


def test_two_real_subjects_still_reject(fake_detector):
    """The guard's actual job must survive the fix.

    Two comparably sized faces are two subjects, and creation must refuse the
    image — this is the case that protects the embedding.
    """

    fake_detector([_face(1200, 1200), _face(1100, 1100)])
    assert cm._count_faces("irrelevant.jpg") == 2


def test_a_smaller_but_genuine_second_subject_still_rejects(fake_detector):
    """A second person further from camera is still a second person.

    Primary at 20% of frame, second at 6.7% — above the absolute floor and
    above a quarter of the primary's area, so both floors agree it competes.
    """

    fake_detector([_face(1560, 1560), _face(900, 900)])
    assert cm._count_faces("irrelevant.jpg") == 2


def test_a_distant_bystander_does_not_reject(fake_detector):
    """Below the absolute floor is not a competing subject.

    A face under 4% of frame in a REFERENCE PHOTOGRAPH is a background
    bystander, not a candidate the embedding could confuse for the subject —
    and its own embedding would be too small to be usable. Rejecting the upload
    over one would frustrate the user for no identity benefit. This is the
    deliberate line between the two floors: the relative floor asks "is this
    competing?", the absolute one asks "is this a subject at all?".
    """

    fake_detector([_face(1200, 1200), _face(600, 600)])  # 11.8% and 2.95%
    assert cm._count_faces("irrelevant.jpg") == 1


def test_an_off_angle_image_with_only_artifacts_counts_zero(fake_detector):
    """A true profile yields no subject-sized detection at all.

    Measured: on a real photograph of the subject in profile the largest
    detection is 96x96 (0.076% of frame). Counting zero is correct — the guard
    only rejects at >= 2, so it declines to judge rather than rejecting a valid
    reference it cannot assess.
    """

    fake_detector([_face(96, 96), _face(90, 90)])
    assert cm._count_faces("irrelevant.jpg") == 0


def test_a_malformed_detection_is_counted_not_dropped(fake_detector):
    """A parse failure must never make this guard lenient."""

    fake_detector([_face(1200, 1200), {"facial_area": {"w": None, "h": None}}])
    assert cm._count_faces("irrelevant.jpg") == 2


def test_unknown_frame_size_falls_back_to_the_relative_floor(monkeypatch):
    """Losing the frame size disables the absolute floor, not both."""

    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(
        cm.DeepFace, "extract_faces",
        lambda **_kwargs: [_face(1664, 1664), _face(58, 58)],
    )

    def _boom(_path):
        raise OSError("cannot read image header")

    monkeypatch.setattr(cm, "_image_pixel_area", _boom)
    # 58*58 is 0.12% of 1664*1664, far below the 25% relative floor.
    assert cm._count_faces("irrelevant.jpg") == 1


def test_detector_unavailable_returns_zero(monkeypatch):
    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", False)
    assert cm._count_faces("irrelevant.jpg") == 0


def test_floors_are_documented_constants() -> None:
    """Both floors exist and sit between the measured populations.

    Largest detection per image, as a share of frame: real faces spanned
    8.53%-27.3%, artifacts 0.03%-1.06%. The absolute floor must separate them.
    """

    assert 0.0106 < cm._MIN_SUBJECT_FACE_FRAME_RATIO < 0.0853
    assert 0 < cm._MIN_COMPETING_FACE_AREA_RATIO < 1

"""
A3: ref-side single-face enforcement at character registration (TDD).

Spec: SPEC-P1-1-multichar-generation-identity-2026-06-10.md §3(d) addendum
(2026-06-12): enforce single-face at character-registration time — a reference
image containing 2+ faces silently corrupts every downstream identity score.

Rules under test
----------------
1. Registration of a reference image in which the detector reports 2+ faces
   must fail LOUDLY (ValueError).
2. Registration of a reference image with exactly 1 face must SUCCEED.
3. Registration of a reference image with 0 detectable faces must follow the
   existing behavior (WARN + continue — no change; characterised here).

Mock strategy: patch "domain.character_manager.DeepFace.extract_faces" (the
same surface used by _has_detectable_face internally).  DeepFace itself is also
patched as available so the gating code runs.

Offline-only: no real files, no network, no GPU, no project disk I/O.
"""

import os
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import domain.character_manager as cm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_face(n: int):
    """Return n fake face dicts that DeepFace.extract_faces would return."""
    return [
        {
            "face": None,
            "confidence": 0.95,
            "facial_area": {"x": 10 * i, "y": 10 * i, "w": 50, "h": 50},
        }
        for i in range(n)
    ]


def _minimal_project(pid: str = "proj_test_a3") -> dict:
    return {
        "id": pid,
        "name": "A3 test",
        "characters": [],
        "locations": [],
        "scenes": [],
        "objects": [],
        "global_settings": {"language": "English"},
    }


class _RefImageContext:
    """
    Context manager that creates a temporary directory with a fake image file,
    patches all disk I/O that create_character_with_images requires, and cleans
    up on exit.

    Patches applied:
    - domain.character_manager.DEEPFACE_AVAILABLE = True  (so face checks run)
    - domain.character_manager.FAL_AVAILABLE = False       (skip multi-angle gen)
    - domain.character_manager.DeepFace.extract_faces     (controlled face count)
    - domain.character_manager.get_project_dir            (temp dir)
    - domain.character_manager.add_character              (no-op)
    - os.path.exists                                       (all files exist)
    - shutil.copy2                                         (no-op)
    - domain.character_manager.np.save                    (no-op)
    - domain.character_manager.compute_face_embedding     (return None = skip emb)
    """

    def __init__(self, face_count: int):
        self.face_count = face_count
        self._tmpdir = None
        self._patches = []
        self._fake_ref = "/fake/ref_image.jpg"

    def __enter__(self):
        self._tmpdir = tempfile.mkdtemp(prefix="a3_reg_test_")
        fake_char_dir = os.path.join(self._tmpdir, "characters", "some_char")
        os.makedirs(fake_char_dir, exist_ok=True)

        # Build the stack of patches
        p = [
            patch("domain.character_manager.DEEPFACE_AVAILABLE", True),
            patch("domain.character_manager.FAL_AVAILABLE", False),
            # Control the face count returned by extract_faces
            patch(
                "domain.character_manager.DeepFace.extract_faces",
                return_value=_fake_face(self.face_count),
            ),
            # Route project dir to our temp dir so character dir creation works
            patch(
                "domain.character_manager.get_project_dir",
                return_value=self._tmpdir,
            ),
            # Suppress actual file I/O
            patch("domain.character_manager.add_character"),
            patch("os.path.exists", return_value=True),
            patch("shutil.copy2"),
            patch("domain.character_manager.np.save"),
            patch(
                "domain.character_manager.compute_face_embedding",
                return_value=None,
            ),
            # assign_voice falls through; suppress the DEEPFACE/FAL paths cleanly
            patch("domain.character_manager._generate_multi_angle_refs", return_value=[]),
        ]
        self._patches = [pp.start() for pp in p]
        self._patch_objs = p
        return self

    def __exit__(self, *args):
        for pp in self._patch_objs:
            pp.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @property
    def fake_ref(self):
        return self._fake_ref


# ---------------------------------------------------------------------------
# RED tests (must fail before the implementation is added)
# ---------------------------------------------------------------------------

class TestSingleFaceEnforcementAtRegistration:
    """Rule: a reference with 2+ faces must raise ValueError at registration."""

    def test_two_face_ref_raises_value_error(self):
        """
        When a reference image contains 2 detected faces, registration must
        raise ValueError — not silently proceed.
        """
        proj = _minimal_project()
        with _RefImageContext(face_count=2) as ctx:
            with pytest.raises(ValueError) as exc_info:
                cm.create_character_with_images(
                    proj,
                    name="TestChar",
                    description="A test character",
                    reference_image_paths=[ctx.fake_ref],
                )
            # Error message must tell the user what was found and what is required
            msg = str(exc_info.value).lower()
            assert "2" in msg or "multiple" in msg or "faces" in msg, (
                f"Error message should mention face count; got: {exc_info.value!r}"
            )
            assert "1" in msg or "single" in msg or "one" in msg, (
                f"Error message should state single face required; got: {exc_info.value!r}"
            )

    def test_three_face_ref_raises_value_error(self):
        """3 detected faces must also raise ValueError."""
        proj = _minimal_project(pid="proj_3face")
        with _RefImageContext(face_count=3) as ctx:
            with pytest.raises(ValueError):
                cm.create_character_with_images(
                    proj,
                    name="TestChar",
                    description="A test character",
                    reference_image_paths=[ctx.fake_ref],
                )


class TestSingleFaceSucceeds:
    """Rule: a reference with exactly 1 face must succeed (no exception)."""

    def test_one_face_ref_succeeds(self):
        """
        Registering a reference image with exactly 1 detected face must
        NOT raise and must return a character dict.
        """
        proj = _minimal_project(pid="proj_1face")
        with _RefImageContext(face_count=1) as ctx:
            result = cm.create_character_with_images(
                proj,
                name="ValidChar",
                description="A single-face character",
                reference_image_paths=[ctx.fake_ref],
            )
        assert isinstance(result, dict)
        assert result.get("name") == "ValidChar"


class TestZeroFaceCharacterization:
    """
    Characterisation (not changed): 0 detected faces must continue to follow
    the existing WARN path — no exception raised.
    """

    def test_zero_face_ref_does_not_raise(self):
        """
        A reference image with 0 detectable faces emits a warning but must NOT
        raise — matches the existing behaviour (limited identity lock path).
        """
        proj = _minimal_project(pid="proj_0face")
        with _RefImageContext(face_count=0) as ctx:
            # Should complete without raising
            result = cm.create_character_with_images(
                proj,
                name="ZeroFaceChar",
                description="No face in photo",
                reference_image_paths=[ctx.fake_ref],
            )
        assert isinstance(result, dict)

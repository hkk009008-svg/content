"""
TDD tests for IdentityValidator._compute_binding_scores and
validate_image_with_binding.

Spec: docs/SPEC-PASS-B-multichar-direction-2026-06-12.md §3.2–§3.4
Director decision: slot-source-agnostic; callers pass intended_slot explicitly.

All tests are OFFLINE-only — DeepFace and PIL are mocked; no GPU, no model
weights, no real files.

Test cases:
  T1  correct-side binding    → binding_ok True, positive score
  T2  wrong-side binding      → binding_ok False, negative score
  T3  tie (score == 0)        → binding_ok False  (spec §3.2: <= 0 is FAILURE)
  T4  both chars evaluated independently
  T5  A2 co-star scenario     → binding_ok False even when full-image presence passes
  T6  calibration against halves_rescore_20260612.json fixture data
  T7  validate_image_with_binding returns presence result unchanged
  T8  PIL unavailable → zero scores (non-crashing)
  T9  missing image_path → zero scores (non-crashing)
  T10 empty char_specs → empty dict
"""

import os
import tempfile
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from identity.validator import IdentityValidator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _unit_emb(dim: int = 512) -> np.ndarray:
    vec = np.ones(dim)
    return vec / np.linalg.norm(vec)


def _ortho_emb(dim: int = 512) -> np.ndarray:
    """Return an embedding orthogonal to _unit_emb → cosine 0 → similarity 0.5."""
    vec = np.zeros(dim)
    vec[0] = 1.0
    return vec / np.linalg.norm(vec)


def _deepface_represent(vec: np.ndarray):
    """Return DeepFace.represent-format output for a given embedding vector."""
    return [{"embedding": vec.tolist()}]


def _make_image_file(tmpdir: str, name: str = "test.jpg") -> str:
    """Create a tiny valid JPEG in tmpdir so os.path.exists passes."""
    path = os.path.join(tmpdir, name)
    # Write a minimal 1x1 white JPEG-like file (real PIL not needed for mock tests)
    open(path, "wb").close()
    return path


def _fake_pil_image(width: int = 200, height: int = 100):
    """Return a minimal object that mimics PIL.Image.Image enough for crop()."""
    mock = MagicMock()
    mock.size = (width, height)

    def _crop(box):
        cropped = MagicMock()
        cropped.size = (box[2] - box[0], box[3] - box[1])
        cropped.save = MagicMock()
        return cropped

    mock.crop.side_effect = _crop
    return mock


# ---------------------------------------------------------------------------
# T1 — correct-side binding → binding_ok True, positive score
# ---------------------------------------------------------------------------

class TestCorrectSideBinding:
    """When the reference face is stronger on the intended half, binding_ok True."""

    def test_intended_left_face_stronger_on_left(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        open(image_path, "wb").close()
        open(ref_path, "wb").close()

        ref_emb = _unit_emb()
        # Left crop → high similarity (intended); right crop → low similarity
        high_sim = 0.90   # cosine 0.8 → (1+0.8)/2 = 0.9
        low_sim = 0.55    # cosine 0.1 → (1+0.1)/2 = 0.55

        pil_img = _fake_pil_image()

        # validate_image is called 4 times total:
        #   - ref embedding (represent) for each of the two crops
        # but we mock validate_image directly on the instance instead to avoid
        # coordinating exact DeepFace.represent call ordering across PIL mocks.

        validator = IdentityValidator()

        presence_results = []

        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            # "intended" crop gets high score, "other" crop gets low score
            score = high_sim if "_intended" in character_id else low_sim
            return IdentityValidationResult(
                passed=score >= 0.5,
                overall_score=score,
                character_results={},
                frames_sampled=1,
                video_duration_seconds=0.0,
                shot_type="medium",
                threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "aria", "ref_path": ref_path, "intended_slot": "left"}],
            )

        assert "aria" in binding
        r = binding["aria"]
        assert r["binding_ok"] is True
        assert r["binding_score"] > 0
        assert r["intended_score"] > r["other_score"]
        # Boundary lock: crops must be exactly w//2 halves (the same boundary
        # as _s1_rescore_crops.crop_half and the 0b masks) — the routing logic
        # is keyed on character_id, so without this assertion a drifted
        # boundary would pass every other test.
        boxes = [c.args[0] for c in pil_img.crop.call_args_list]
        assert boxes == [(0, 0, 100, 100), (100, 0, 200, 100)]


# ---------------------------------------------------------------------------
# T2 — wrong-side binding → binding_ok False, negative score
# ---------------------------------------------------------------------------

class TestWrongSideBinding:
    """When the reference face is stronger on the OTHER half, binding_ok False."""

    def test_intended_right_face_stronger_on_left(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        open(image_path, "wb").close()
        open(ref_path, "wb").close()

        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            # Intended slot is RIGHT, but face is stronger on LEFT (i.e. "other")
            # "_intended" = right_path in this case → low score
            # "_other"    = left_path            → high score
            score = 0.55 if "_intended" in character_id else 0.85
            return IdentityValidationResult(
                passed=score >= 0.5,
                overall_score=score,
                character_results={},
                frames_sampled=1,
                video_duration_seconds=0.0,
                shot_type="medium",
                threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "right"}],
            )

        r = binding["man"]
        assert r["binding_ok"] is False
        assert r["binding_score"] < 0
        assert r["intended_score"] < r["other_score"]


# ---------------------------------------------------------------------------
# T3 — tie (score == 0) → binding_ok False (spec §3.2: <= 0 is FAILURE)
# ---------------------------------------------------------------------------

class TestTieIsFailure:
    """When intended_score == other_score (binding_score == 0), binding_ok False."""

    def test_tie_score_zero_is_binding_failure(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        open(image_path, "wb").close()
        open(ref_path, "wb").close()

        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            return IdentityValidationResult(
                passed=True, overall_score=0.70,
                character_results={}, frames_sampled=1,
                video_duration_seconds=0.0, shot_type="medium", threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "char_x", "ref_path": ref_path, "intended_slot": "left"}],
            )

        r = binding["char_x"]
        assert r["binding_score"] == pytest.approx(0.0)
        assert r["binding_ok"] is False  # <= 0 must be FAILURE, not ambiguous pass


# ---------------------------------------------------------------------------
# T4 — both chars evaluated independently
# ---------------------------------------------------------------------------

class TestBothCharsIndependent:
    """Both chars in char_specs are scored; their results are independent."""

    def test_two_chars_both_scored(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        aria_ref = str(tmp_path / "aria.jpg")
        man_ref = str(tmp_path / "man.jpg")
        for p in [image_path, aria_ref, man_ref]:
            open(p, "wb").close()

        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # aria intended=left → high score on left (intended), low on right (other) → ok=True
        # man intended=right → low score on right (intended), high on left (other) → ok=False
        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            if "aria" in character_id:
                score = 0.85 if "_intended" in character_id else 0.50
            else:  # man
                score = 0.50 if "_intended" in character_id else 0.85
            return IdentityValidationResult(
                passed=score >= 0.5, overall_score=score, character_results={},
                frames_sampled=1, video_duration_seconds=0.0, shot_type="medium",
                threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            binding = validator._compute_binding_scores(
                image_path,
                [
                    {"char_id": "aria", "ref_path": aria_ref, "intended_slot": "left"},
                    {"char_id": "man",  "ref_path": man_ref,  "intended_slot": "right"},
                ],
            )

        assert "aria" in binding
        assert "man" in binding
        assert binding["aria"]["binding_ok"] is True
        assert binding["man"]["binding_ok"] is False
        # Verify they were scored independently (both are present)
        assert binding["aria"]["binding_score"] != binding["man"]["binding_score"]


# ---------------------------------------------------------------------------
# T5 — A2 co-star scenario (spec §3.4)
#       A char whose intended-half score is LOWER than other-half → binding_ok False
#       even when full-image presence would pass.
# ---------------------------------------------------------------------------

class TestCoStarFalsePositiveClosed:
    """
    Spec §3.4 A2: secondary scoring on the full image can false-pass when the
    co-star's face is picked as the best-match.  Example: man full-image 0.597
    was elevated by Aria's face being the detected best-match.

    The binding metric closes this because the man's intended_score (right half)
    is LOWER than his other_score (left half), yielding binding_ok=False even
    when his full-image presence score would be above the halt threshold.
    """

    def test_costar_pollution_yields_binding_failure(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        man_ref = str(tmp_path / "man.jpg")
        for p in [image_path, man_ref]:
            open(p, "wb").close()

        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Simulates Pass-A man scenario:
        # - full-image score elevated (0.597) by co-star face → "presence passes"
        # - left-half (other for man=right): 0.587  (co-star's face is here)
        # - right-half (intended for man=right): 0.487  (man body present but weak)
        # binding_score = 0.487 - 0.587 = -0.100 → binding_ok False
        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            if "_intended" in character_id:
                score = 0.487   # right half — weak man face
            elif "_other" in character_id:
                score = 0.587   # left half — co-star face inflates score
            else:
                score = 0.597   # full-image presence (not used by _compute_binding_scores)
            return IdentityValidationResult(
                passed=score >= 0.5, overall_score=score, character_results={},
                frames_sampled=1, video_duration_seconds=0.0,
                shot_type="medium", threshold_used=threshold or 0.70,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": man_ref, "intended_slot": "right"}],
            )

        r = binding["man"]
        # Even though full-image presence 0.597 > typical halt threshold 0.55:
        assert r["binding_ok"] is False, "co-star pollution must yield binding_ok=False"
        assert r["binding_score"] == pytest.approx(0.487 - 0.587, abs=1e-6)


# ---------------------------------------------------------------------------
# T6 — calibration check against halves_rescore_20260612.json
# ---------------------------------------------------------------------------

class TestCalibrationAgainstJson:
    """
    Verify that the binding decision logic (pure Python, no DeepFace)
    reproduces expected binding_ok verdicts for s2_dual_n1-4 and pass_a
    using the per-half scores from the committed instrument output
    logs/halves_rescore_20260612.json.

    S2 prompt (scripts/_max_s2_dual_pulid.py, lines 30-33):
        "a woman with short dark wavy hair on the left and a middle-aged
         man with a grey beard on the right, standing together in a sunlit
         meadow, medium two-shot, both faces clearly visible,
         photorealistic, cinematic"
    → intended slots: aria=left, man=right

    Director's Phase-0a derivation (confirmed by manual computation here):
    - man binds LEFT in n1/n2/n3 → binding_ok FALSE when intended=right
    - n4: man RIGHT stronger → binding_ok TRUE
    - pass_a: man RIGHT stronger → binding_ok TRUE
    - aria: RIGHT stronger in all 5 artifacts → binding_ok FALSE (intended=left)

    Unmasked baseline binding_ok count:
    - man  (intended=right): 2/5 TRUE  (n4 + pass_a)
    - aria (intended=left):  0/5 TRUE
    """

    # Pure-Python binding decision — feeds JSON scores through the same
    # formula as _compute_binding_scores WITHOUT DeepFace or PIL.
    @staticmethod
    def _binding_ok(intended_score: float, other_score: float) -> bool:
        """Mirror the production formula: binding_ok = (intended - other) > 0."""
        return (intended_score - other_score) > 0

    @staticmethod
    def _load_json() -> list:
        # Fixture data inlined from logs/halves_rescore_20260612.json (committed-instrument
        # output; logs/ is gitignored so we inline the 36-row table directly to keep
        # CI green on any clone without the on-disk artifact.  If the JSON file exists
        # locally it is the canonical source; we reproduce its content here verbatim).
        return [
            {"artifact": "logs/pass_a_multichar_FAILED_landscape_20260610.jpg", "half": "left",  "ref": "man",  "arc_score": 0.7191785413528089},
            {"artifact": "logs/pass_a_multichar_FAILED_landscape_20260610.jpg", "half": "left",  "ref": "aria", "arc_score": 0.4636993555790486},
            {"artifact": "logs/pass_a_multichar_FAILED_landscape_20260610.jpg", "half": "right", "ref": "man",  "arc_score": 0.7525067670889205},
            {"artifact": "logs/pass_a_multichar_FAILED_landscape_20260610.jpg", "half": "right", "ref": "aria", "arc_score": 0.44471674255886257},
            {"artifact": "logs/pass_a_multichar.jpg",                           "half": "left",  "ref": "man",  "arc_score": 0.5865938673720762},
            {"artifact": "logs/pass_a_multichar.jpg",                           "half": "left",  "ref": "aria", "arc_score": 0.6174030749228697},
            {"artifact": "logs/pass_a_multichar.jpg",                           "half": "right", "ref": "man",  "arc_score": 0.7200764518510138},
            {"artifact": "logs/pass_a_multichar.jpg",                           "half": "right", "ref": "aria", "arc_score": 0.8304332506872905},
            {"artifact": "logs/s2_dual_n1.jpg",                                 "half": "left",  "ref": "man",  "arc_score": 0.7278553043177336},
            {"artifact": "logs/s2_dual_n1.jpg",                                 "half": "left",  "ref": "aria", "arc_score": 0.46468673757130063},
            {"artifact": "logs/s2_dual_n1.jpg",                                 "half": "right", "ref": "man",  "arc_score": 0.4660365481506625},
            {"artifact": "logs/s2_dual_n1.jpg",                                 "half": "right", "ref": "aria", "arc_score": 0.8399616158387132},
            {"artifact": "logs/s2_dual_n2.jpg",                                 "half": "left",  "ref": "man",  "arc_score": 0.6486700715110543},
            {"artifact": "logs/s2_dual_n2.jpg",                                 "half": "left",  "ref": "aria", "arc_score": 0.724894594699394},
            {"artifact": "logs/s2_dual_n2.jpg",                                 "half": "right", "ref": "man",  "arc_score": 0.474981988836575},
            {"artifact": "logs/s2_dual_n2.jpg",                                 "half": "right", "ref": "aria", "arc_score": 0.7422765116144403},
            {"artifact": "logs/s2_dual_n3.jpg",                                 "half": "left",  "ref": "man",  "arc_score": 0.7804498889385589},
            {"artifact": "logs/s2_dual_n3.jpg",                                 "half": "left",  "ref": "aria", "arc_score": 0.6794408857161676},
            {"artifact": "logs/s2_dual_n3.jpg",                                 "half": "right", "ref": "man",  "arc_score": 0.46969717322933746},
            {"artifact": "logs/s2_dual_n3.jpg",                                 "half": "right", "ref": "aria", "arc_score": 0.7687491249116085},
            {"artifact": "logs/s2_dual_n4.jpg",                                 "half": "left",  "ref": "man",  "arc_score": 0.6696746149059822},
            {"artifact": "logs/s2_dual_n4.jpg",                                 "half": "left",  "ref": "aria", "arc_score": 0.43354495228085765},
            {"artifact": "logs/s2_dual_n4.jpg",                                 "half": "right", "ref": "man",  "arc_score": 0.7385264694673989},
            {"artifact": "logs/s2_dual_n4.jpg",                                 "half": "right", "ref": "aria", "arc_score": 0.8268431150295992},
            {"artifact": "logs/s3_stack_sec35.jpg",                             "half": "left",  "ref": "man",  "arc_score": 0.49593715256615933},
            {"artifact": "logs/s3_stack_sec35.jpg",                             "half": "left",  "ref": "aria", "arc_score": 0.7805928628262424},
            {"artifact": "logs/s3_stack_sec35.jpg",                             "half": "right", "ref": "man",  "arc_score": 0.7404491337321177},
            {"artifact": "logs/s3_stack_sec35.jpg",                             "half": "right", "ref": "aria", "arc_score": 0.8541918680266032},
            {"artifact": "logs/s3_stack_sec45.jpg",                             "half": "left",  "ref": "man",  "arc_score": 0.8298968930605308},
            {"artifact": "logs/s3_stack_sec45.jpg",                             "half": "left",  "ref": "aria", "arc_score": 0.4787327499862598},
            {"artifact": "logs/s3_stack_sec45.jpg",                             "half": "right", "ref": "man",  "arc_score": 0.6951802239820278},
            {"artifact": "logs/s3_stack_sec45.jpg",                             "half": "right", "ref": "aria", "arc_score": 0.8324165002470392},
            {"artifact": "logs/s3_stack_sec55.jpg",                             "half": "left",  "ref": "man",  "arc_score": 0.6175177239282459},
            {"artifact": "logs/s3_stack_sec55.jpg",                             "half": "left",  "ref": "aria", "arc_score": 0.46791547495203745},
            {"artifact": "logs/s3_stack_sec55.jpg",                             "half": "right", "ref": "man",  "arc_score": 0.649907008356668},
            {"artifact": "logs/s3_stack_sec55.jpg",                             "half": "right", "ref": "aria", "arc_score": 0.8297793350744394},
        ]

    @staticmethod
    def _extract_scores(rows: list, artifact_substr: str):
        """Return {(half, ref): arc_score} for a given artifact name substring."""
        scores = {}
        for row in rows:
            if artifact_substr in row["artifact"]:
                key = (row["half"], row["ref"])
                scores[key] = row["arc_score"]
        return scores

    def test_prompt_spatial_language_matches_intended_slots(self):
        """
        Verify by quoting the prompt that aria=left, man=right.
        (Prompt from scripts/_max_s2_dual_pulid.py lines 30-33.)
        """
        prompt = (
            "a woman with short dark wavy hair on the left and a middle-aged "
            "man with a grey beard on the right, standing together in a sunlit "
            "meadow, medium two-shot, both faces clearly visible, "
            "photorealistic, cinematic"
        )
        # The spatial language "on the left" refers to the woman (Aria);
        # "on the right" refers to the man.
        assert "woman" in prompt and "on the left" in prompt
        assert "man" in prompt and "on the right" in prompt
        # Derived slots: aria=left, man=right — no discrepancy vs spec assumption.

    def test_s2_n1_man_binding_false(self):
        rows = self._load_json()
        scores = self._extract_scores(rows, "s2_dual_n1")
        # man intended=right
        ok = self._binding_ok(scores[("right", "man")], scores[("left", "man")])
        assert ok is False, (
            f"n1 man: R={scores[('right','man')]:.3f} L={scores[('left','man')]:.3f} "
            f"→ binding_score={scores[('right','man')]-scores[('left','man')]:.3f}"
        )

    def test_s2_n2_man_binding_false(self):
        rows = self._load_json()
        scores = self._extract_scores(rows, "s2_dual_n2")
        ok = self._binding_ok(scores[("right", "man")], scores[("left", "man")])
        assert ok is False

    def test_s2_n3_man_binding_false(self):
        rows = self._load_json()
        scores = self._extract_scores(rows, "s2_dual_n3")
        ok = self._binding_ok(scores[("right", "man")], scores[("left", "man")])
        assert ok is False

    def test_s2_n4_man_binding_true(self):
        rows = self._load_json()
        scores = self._extract_scores(rows, "s2_dual_n4")
        ok = self._binding_ok(scores[("right", "man")], scores[("left", "man")])
        assert ok is True, (
            f"n4 man: R={scores[('right','man')]:.3f} L={scores[('left','man')]:.3f} "
            f"→ binding_score={scores[('right','man')]-scores[('left','man')]:.3f}"
        )

    def test_pass_a_man_binding_true(self):
        rows = self._load_json()
        scores = self._extract_scores(rows, "pass_a_multichar.jpg")
        ok = self._binding_ok(scores[("right", "man")], scores[("left", "man")])
        assert ok is True, (
            f"pass_a man: R={scores[('right','man')]:.3f} L={scores[('left','man')]:.3f} "
            f"→ binding_score={scores[('right','man')]-scores[('left','man')]:.3f}"
        )

    def test_aria_binding_false_all_seeds(self):
        """Aria face is on the RIGHT in all 4 S2 seeds — binding_ok=False for intended=left."""
        rows = self._load_json()
        for seed in ["n1", "n2", "n3", "n4"]:
            scores = self._extract_scores(rows, f"s2_dual_{seed}")
            ok = self._binding_ok(scores[("left", "aria")], scores[("right", "aria")])
            assert ok is False, (
                f"s2_dual_{seed} aria: L={scores[('left','aria')]:.3f} "
                f"R={scores[('right','aria')]:.3f} → should be False (aria on RIGHT)"
            )

    def test_baseline_binding_ok_count(self):
        """
        Unmasked baseline binding_ok counts across 5 artifacts:
        - man  (intended=right): expected 2/5 TRUE (n4 + pass_a)
        - aria (intended=left):  expected 0/5 TRUE

        These numbers go in front of the user as the Pass-B starting point.
        """
        rows = self._load_json()
        artifacts = [
            ("s2_dual_n1", "s2_dual_n1"),
            ("s2_dual_n2", "s2_dual_n2"),
            ("s2_dual_n3", "s2_dual_n3"),
            ("s2_dual_n4", "s2_dual_n4"),
            ("pass_a_multichar.jpg", "pass_a"),
        ]
        man_ok_count = 0
        aria_ok_count = 0
        for substr, _label in artifacts:
            scores = self._extract_scores(rows, substr)
            if self._binding_ok(scores[("right", "man")], scores[("left", "man")]):
                man_ok_count += 1
            if self._binding_ok(scores[("left", "aria")], scores[("right", "aria")]):
                aria_ok_count += 1

        assert man_ok_count == 2, f"Expected 2/5 man binding_ok TRUE, got {man_ok_count}/5"
        assert aria_ok_count == 0, f"Expected 0/5 aria binding_ok TRUE, got {aria_ok_count}/5"


# ---------------------------------------------------------------------------
# T7 — validate_image_with_binding returns presence result unchanged
# ---------------------------------------------------------------------------

class TestValidateImageWithBinding:
    """validate_image_with_binding returns (presence_result, binding_dict);
    the presence result is identical to what validate_image would return;
    validate_image itself is NOT changed."""

    def test_presence_result_unchanged(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        call_log = []

        def _mock_validate_image(img_path, ref, character_id="", threshold=None, **kw):
            from identity.types import IdentityValidationResult
            call_log.append((img_path, character_id))
            score = 0.90 if "_intended" not in character_id and "_other" not in character_id else 0.70
            return IdentityValidationResult(
                passed=score >= 0.5, overall_score=score, character_results={},
                frames_sampled=1, video_duration_seconds=0.0,
                shot_type="medium", threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True):
            mock_pil.open.return_value = pil_img
            validator.validate_image = MagicMock(side_effect=_mock_validate_image)

            presence, binding = validator.validate_image_with_binding(
                image_path, ref_path,
                char_specs=[
                    {"char_id": "aria", "ref_path": ref_path, "intended_slot": "left"},
                ],
                character_id="aria",
                shot_type="medium",
            )

        # The first call must be the full-image presence check
        assert call_log[0] == (image_path, "aria")
        # Presence result is the return of the first call (score=0.90)
        assert presence.overall_score == pytest.approx(0.90)
        # Binding dict present for aria
        assert "aria" in binding

    def test_validate_image_signature_unchanged(self):
        """
        Smoke: validate_image still accepts (image_path, reference_path, ...)
        and returns IdentityValidationResult — the signature is untouched.
        """
        from identity.types import IdentityValidationResult
        validator = IdentityValidator()

        ref_emb = _unit_emb()

        with patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator.DEEPFACE_AVAILABLE", True), \
             patch(
                 "identity.validator.DeepFace.represent",
                 side_effect=[
                     _deepface_represent(ref_emb),
                     _deepface_represent(ref_emb),
                 ],
             ):
            result = validator.validate_image(
                "/some/gen.jpg", "/some/ref.jpg",
                character_id="aria",
                shot_type="medium",
                threshold=0.65,
            )

        assert isinstance(result, IdentityValidationResult)


# ---------------------------------------------------------------------------
# T8 — PIL unavailable → zero scores, non-crashing
# ---------------------------------------------------------------------------

class TestPILUnavailable:
    """If PIL is not installed, _compute_binding_scores returns zero binding_ok=False."""

    def test_pil_unavailable_returns_zeros(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        validator = IdentityValidator()

        with patch("identity.validator._PIL_AVAILABLE", False), \
             patch("identity.validator._PILImage", None):
            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "aria", "ref_path": ref_path, "intended_slot": "left"}],
            )

        assert "aria" in binding
        r = binding["aria"]
        assert r["binding_ok"] is False
        assert r["binding_score"] == pytest.approx(0.0)
        assert r["intended_score"] == pytest.approx(0.0)
        assert r["other_score"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# T9 — missing image_path → zero scores, non-crashing
# ---------------------------------------------------------------------------

class TestMissingImagePath:
    """If image_path does not exist, _compute_binding_scores returns zero scores."""

    def test_missing_image_returns_zeros(self, tmp_path):
        ref_path = str(tmp_path / "ref.jpg")
        open(ref_path, "wb").close()

        validator = IdentityValidator()

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil:
            binding = validator._compute_binding_scores(
                "/nonexistent/image.jpg",
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "right"}],
            )

        assert "man" in binding
        assert binding["man"]["binding_ok"] is False
        assert binding["man"]["binding_score"] == pytest.approx(0.0)
        # PIL.Image.open must NOT have been called (we short-circuited on missing file)
        mock_pil.open.assert_not_called()


# ---------------------------------------------------------------------------
# T10 — empty char_specs → empty dict
# ---------------------------------------------------------------------------

class TestEmptyCharSpecs:
    """Empty char_specs produces an empty result dict without raising."""

    def test_empty_specs_returns_empty_dict(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        open(image_path, "wb").close()

        validator = IdentityValidator()
        binding = validator._compute_binding_scores(image_path, [])

        assert binding == {}

"""
TDD tests for IdentityValidator._compute_binding_scores and
validate_image_with_binding.

Spec: docs/SPEC-PASS-B-multichar-direction-2026-06-12.md §3.2–§3.4
Director decision: slot-source-agnostic; callers pass intended_slot explicitly.

Detection filtering (2026-06-12 operator reconciliation report):
  The binding metric now uses _figure_read_score (largest OK face, area >= 1%,
  not a whole-image fallback) rather than validate_image per half.  The mock
  seam has moved from validate_image → _figure_read_score / _ref_embedding_largest_ok.

All tests are OFFLINE-only — DeepFace and PIL are mocked; no GPU, no model
weights, no real files.

Test cases:
  T1  correct-side binding    → binding_ok True, positive score
  T2  wrong-side binding      → binding_ok False, negative score
  T3  tie (score == 0)        → binding_ok False  (spec §3.2: <= 0 is FAILURE)
  T4  both chars evaluated independently
  T5  A2 co-star scenario     → binding_ok False even when full-image presence passes
  T6  calibration against filtered figure reads (probe report 2026-06-12)
  T7  validate_image_with_binding returns presence result unchanged
  T8  PIL unavailable → zero scores (non-crashing)
  T9  missing image_path → zero scores (non-crashing)
  T10 empty char_specs → empty dict
  T11 blob-promotion scenario  → figure read wins over TINY blob
  T12 DEGENERATE fallback skipped → NO_FACE verdict, not a junk score
  T13 NO_FACE_INTENDED scenario → binding_ok False, note propagated
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


def _figure_read_result(score, read_type="figure", n_detections=1, face_area_pct=20.0):
    """Convenience: return a _figure_read_score-shaped dict."""
    return {
        "score": score,
        "read_type": read_type,
        "n_detections": n_detections,
        "face_area_pct": face_area_pct,
        "detection_class": {"OK": 1 if read_type == "figure" else 0,
                             "TINY": 0, "DEGENERATE": 0},
        "ref_name": "ref",
    }


def _no_face_result():
    """_figure_read_score dict indicating no OK face found."""
    return _figure_read_result(score=None, read_type="none", n_detections=1,
                               face_area_pct=0.0)


# Mock helper: given calls to _figure_read_score, route intended/other by ref_name kwarg.
def _make_figure_read_side_effect(intended_score, other_score,
                                  intended_rtype="figure", other_rtype="figure"):
    """Return a side_effect callable for patching _figure_read_score.

    Routing: ref_name ending '_intended' → intended_score/rtype,
             ref_name ending '_other'    → other_score/rtype.
    """
    def _side_effect(image_path, ref_emb, *, ref_name="ref"):
        if ref_name.endswith("_intended"):
            if intended_rtype == "none":
                return _no_face_result()
            return _figure_read_result(intended_score, intended_rtype)
        else:
            if other_rtype == "none":
                return _no_face_result()
            return _figure_read_result(other_score, other_rtype)
    return _side_effect


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
        high_sim = 0.90
        low_sim = 0.55

        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(high_sim, low_sim)):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "aria", "ref_path": ref_path, "intended_slot": "left"}],
            )

        assert "aria" in binding
        r = binding["aria"]
        assert r["binding_ok"] is True
        assert r["binding_score"] > 0
        assert r["intended_score"] > r["other_score"]
        # Boundary lock: crops must be exactly w//2 halves
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

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Intended slot is RIGHT but face is stronger on LEFT (the 'other' side)
        # → intended = 0.55, other = 0.85 → binding_score negative
        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(0.55, 0.85)):
            mock_pil.open.return_value = pil_img

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

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(0.70, 0.70)):
            mock_pil.open.return_value = pil_img

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

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # aria intended=left → high on intended, low on other → ok=True
        # man intended=right → low on intended, high on other → ok=False
        def _side_effect(image_path, ref_emb_arg, *, ref_name="ref"):
            char = "aria" if ref_name.startswith("aria") else "man"
            is_intended = ref_name.endswith("_intended")
            if char == "aria":
                score = 0.85 if is_intended else 0.50
            else:
                score = 0.50 if is_intended else 0.85
            return _figure_read_result(score)

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_side_effect):
            mock_pil.open.return_value = pil_img

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
        assert binding["aria"]["binding_score"] != binding["man"]["binding_score"]


# ---------------------------------------------------------------------------
# T5 — A2 co-star scenario (spec §3.4)
# ---------------------------------------------------------------------------

class TestCoStarFalsePositiveClosed:
    """
    Spec §3.4 A2: secondary scoring on the full image can false-pass when the
    co-star's face is picked as the best-match.  Example: man full-image 0.597
    was elevated by Aria's face being the detected best-match.

    The binding metric closes this because the man's intended_score (right half)
    is LOWER than his other_score (left half), yielding binding_ok=False even
    when his full-image presence score would be above the halt threshold.

    Post-filter: the probe's pass_a figure reads are man-right=0.481,
    man-left=0.480 (cited from probe report 2026-06-12).  The co-star scenario
    is simulated here with the pre-fix polluted scores (right=0.487, left=0.587)
    to verify the binding logic independently of detector filtering.
    """

    def test_costar_pollution_yields_binding_failure(self, tmp_path):
        image_path = str(tmp_path / "gen.jpg")
        man_ref = str(tmp_path / "man.jpg")
        for p in [image_path, man_ref]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Simulates co-star pollution (pre-filter numbers from Pass-A reconciliation):
        # right-half (intended for man=right): 0.487  (man body present but weak)
        # left-half  (other for man=right):    0.587  (co-star face inflates score)
        # binding_score = 0.487 - 0.587 = -0.100 → binding_ok False
        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(0.487, 0.587)):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": man_ref, "intended_slot": "right"}],
            )

        r = binding["man"]
        assert r["binding_ok"] is False, "co-star pollution must yield binding_ok=False"
        assert r["binding_score"] == pytest.approx(0.487 - 0.587, abs=1e-6)


# ---------------------------------------------------------------------------
# T6 — calibration against FILTERED figure reads (probe report 2026-06-12)
# ---------------------------------------------------------------------------

class TestCalibrationAgainstJson:
    """
    Verify that the binding decision logic (pure Python, no DeepFace)
    reproduces expected binding_ok verdicts for s2_dual_n1-4 and pass_a
    using FIGURE-READ-ONLY scores from the probe report 2026-06-12.

    Source: scripts/_probe_halves_faces.py firsthand probe (committed artifact
    logs/halves_faces_probe_20260612.json); FIGURE reads = largest OK detection
    per half crop (area >= 1% of image, not a whole-image fallback box).

    Updated from the polluted halves_rescore_20260612.json fixture by operator
    reconciliation (2026-06-12T21:16:46Z); this re-emission supersedes that
    table.  See also: logs/halves_rescore_20260612_filtered.{json,txt}.

    S2 prompt (scripts/_max_s2_dual_pulid.py, lines 30-33):
        "a woman with short dark wavy hair on the left and a middle-aged
         man with a grey beard on the right, standing together in a sunlit
         meadow, medium two-shot, both faces clearly visible,
         photorealistic, cinematic"
    → intended slots: aria=left, man=right

    FILTERED binding verdicts (figure reads only):
      n1:  man-right=0.466 vs man-left=0.728 → man binding FALSE
           aria-left=0.465 vs aria-right=0.840 → aria binding FALSE
      n2:  man-right=0.475 vs man-left=0.519 → man binding FALSE
           aria-left=0.725 vs aria-right=0.742 → aria binding FALSE
      n3:  man-right=0.470 vs man-left=0.519 → man binding FALSE
           aria-left=0.679 vs aria-right=0.769 → aria binding FALSE
      n4:  man-right=0.492 vs man-left=NO_FACE → other 'none', intended 'figure'
             → binding = intended_score > 0 = TRUE
           aria-left=NO_FACE → NO_FACE_INTENDED → aria binding FALSE
      pass_a: man-right=0.481 vs man-left=0.480 → +0.001 → man binding TRUE
              aria-left=0.617 vs aria-right=0.830 → aria binding FALSE

    Unmasked baseline (s2 seeds n1-4 only):
      man  (intended=right): 1/4 TRUE (n4 only)
      aria (intended=left):  0/4 TRUE

    Pass_a context (not a seed):
      man: TRUE (0.481 > 0.480)
      aria: FALSE (0.617 < 0.830)
    """

    @staticmethod
    def _binding_ok_standard(intended: float, other: float) -> bool:
        """Mirror the production formula: binding_ok = (intended - other) > 0."""
        return (intended - other) > 0

    @staticmethod
    def _binding_ok_other_none(intended: float) -> bool:
        """Other-half NO_FACE, intended 'figure' → binding = intended_score > 0."""
        return intended > 0

    # Figure-read scores inlined from logs/halves_faces_probe_20260612.json,
    # largest OK detection per half crop.
    # Format: {artifact_key: {(half, ref): score | None}}
    # None = no OK detection (NO_FACE).
    FIGURE_SCORES = {
        "FAILED_landscape": {
            ("left",  "man"):  None,   # DEGENERATE only
            ("left",  "aria"): None,   # DEGENERATE only
            ("right", "man"):  None,   # DEGENERATE only
            ("right", "aria"): None,   # DEGENERATE only
        },
        "pass_a": {
            # left: face[0] 867x867 OK: man=0.480, aria=0.617
            ("left",  "man"):  0.47988040893076583,
            ("left",  "aria"): 0.6174030749228697,
            # right: face[1] 1045x1045 OK (face[0] was DEGENERATE): man=0.481, aria=0.830
            ("right", "man"):  0.4808755771840048,
            ("right", "aria"): 0.8304332506872905,
        },
        "n1": {
            # left: face[0] 983x983 OK (largest; face[1] 268x268 also OK but smaller)
            ("left",  "man"):  0.7278553043177336,
            ("left",  "aria"): 0.46468673757130063,
            # right: face[0] 1051x1051 OK
            ("right", "man"):  0.4660365481506625,
            ("right", "aria"): 0.8399616158387132,
        },
        "n2": {
            # left: face[0] 807x807 OK (face[1] TINY)
            ("left",  "man"):  0.5192205878002867,
            ("left",  "aria"): 0.724894594699394,
            # right: face[0] 883x883 OK
            ("right", "man"):  0.474981988836575,
            ("right", "aria"): 0.7422765116144403,
        },
        "n3": {
            # left: face[0] 919x919 OK (face[1] TINY)
            ("left",  "man"):  0.5186071322276516,
            ("left",  "aria"): 0.6794408857161676,
            # right: face[0] 1001x1001 OK
            ("right", "man"):  0.46969717322933746,
            ("right", "aria"): 0.7687491249116085,
        },
        "n4": {
            # left: DEGENERATE only → NO_FACE
            ("left",  "man"):  None,
            ("left",  "aria"): None,
            # right: face[0] 1038x1038 OK (face[1,2] TINY)
            ("right", "man"):  0.4924827160705067,
            ("right", "aria"): 0.8268431150295992,
        },
        "sec35": {
            # left: face[0] 943x943 OK
            ("left",  "man"):  0.49593715256615933,
            ("left",  "aria"): 0.7805928628262424,
            # right: face[0] 938x938 OK (face[1,2] TINY)
            ("right", "man"):  0.48588250113520776,
            ("right", "aria"): 0.8541918680266032,
        },
        "sec45": {
            # left: DEGENERATE only → NO_FACE
            ("left",  "man"):  None,
            ("left",  "aria"): None,
            # right: face[0] 968x968 OK (face[1] TINY)
            ("right", "man"):  0.47750720043240696,
            ("right", "aria"): 0.8324165002470392,
        },
        "sec55": {
            # left: TINY only → NO_FACE
            ("left",  "man"):  None,
            ("left",  "aria"): None,
            # right: face[0] 972x972 OK (face[1] TINY)
            ("right", "man"):  0.4923733881495639,
            ("right", "aria"): 0.8297793350744394,
        },
    }

    def test_prompt_spatial_language_matches_intended_slots(self):
        prompt = (
            "a woman with short dark wavy hair on the left and a middle-aged "
            "man with a grey beard on the right, standing together in a sunlit "
            "meadow, medium two-shot, both faces clearly visible, "
            "photorealistic, cinematic"
        )
        assert "woman" in prompt and "on the left" in prompt
        assert "man" in prompt and "on the right" in prompt

    def _man_binding_ok(self, key: str) -> bool:
        """man intended=right; apply NO_FACE semantics."""
        s = self.FIGURE_SCORES[key]
        intended = s[("right", "man")]
        other    = s[("left",  "man")]
        if intended is None:
            return False  # NO_FACE_INTENDED
        if other is None:
            return self._binding_ok_other_none(intended)
        return self._binding_ok_standard(intended, other)

    def _aria_binding_ok(self, key: str) -> bool:
        """aria intended=left; apply NO_FACE semantics."""
        s = self.FIGURE_SCORES[key]
        intended = s[("left",  "aria")]
        other    = s[("right", "aria")]
        if intended is None:
            return False  # NO_FACE_INTENDED
        if other is None:
            return self._binding_ok_other_none(intended)
        return self._binding_ok_standard(intended, other)

    def test_s2_n1_man_binding_false(self):
        assert self._man_binding_ok("n1") is False

    def test_s2_n2_man_binding_false(self):
        assert self._man_binding_ok("n2") is False

    def test_s2_n3_man_binding_false(self):
        assert self._man_binding_ok("n3") is False

    def test_s2_n4_man_binding_true_other_none(self):
        """n4 left=NO_FACE; intended right has figure → binding = intended_score > 0 = TRUE."""
        s = self.FIGURE_SCORES["n4"]
        assert s[("left", "man")] is None, "expected NO_FACE on left (DEGENERATE only)"
        assert self._man_binding_ok("n4") is True

    def test_s2_n4_aria_binding_false_no_face_intended(self):
        """n4 aria intended=left is NO_FACE → binding_ok False (NO_FACE_INTENDED)."""
        s = self.FIGURE_SCORES["n4"]
        assert s[("left", "aria")] is None
        assert self._aria_binding_ok("n4") is False

    def test_pass_a_man_binding_true(self):
        """pass_a man: right=0.481 > left=0.480 → binding_ok TRUE (tight margin)."""
        s = self.FIGURE_SCORES["pass_a"]
        ok = self._binding_ok_standard(s[("right", "man")], s[("left", "man")])
        assert ok is True, (
            f"pass_a man: R={s[('right','man')]:.4f} L={s[('left','man')]:.4f} "
            f"→ delta={s[('right','man')]-s[('left','man')]:.4f}"
        )

    def test_aria_binding_false_all_seeds(self):
        """Aria face is on the RIGHT in all 4 S2 seeds — binding_ok=False for intended=left."""
        for seed in ["n1", "n2", "n3", "n4"]:
            assert self._aria_binding_ok(seed) is False, (
                f"s2_dual_{seed} aria should be False (intended=left but face on right)"
            )

    def test_baseline_binding_ok_count(self):
        """
        FILTERED unmasked baseline binding_ok counts across s2 seeds n1-4:
          man  (intended=right): expected 1/4 TRUE (n4 only — left NO_FACE, intended figure > 0)
          aria (intended=left):  expected 0/4 TRUE

        Calibrated from figure reads in logs/halves_faces_probe_20260612.json
        (cited in operator report 2026-06-12T21:16:46Z).  Supersedes the
        polluted 2/5 man / 0/5 aria counts from halves_rescore_20260612.json.
        Note: n4 man TRUE is due to NO_FACE on the other side, not a strong
        man signal — Pass-B baseline with attn_mask rescue needed to interpret
        this correctly.
        """
        seeds = ["n1", "n2", "n3", "n4"]
        man_ok = sum(1 for s in seeds if self._man_binding_ok(s))
        aria_ok = sum(1 for s in seeds if self._aria_binding_ok(s))
        assert man_ok == 1, f"Expected 1/4 man binding_ok TRUE, got {man_ok}/4"
        assert aria_ok == 0, f"Expected 0/4 aria binding_ok TRUE, got {aria_ok}/4"


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
            score = 0.90
            return IdentityValidationResult(
                passed=True, overall_score=score, character_results={},
                frames_sampled=1, video_duration_seconds=0.0,
                shot_type="medium", threshold_used=0.0,
            )

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(0.80, 0.60)):
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
        assert presence.overall_score == pytest.approx(0.90)
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


# ---------------------------------------------------------------------------
# T11 — blob-promotion scenario: TINY blob has high sim, OK figure has low sim
#        → figure read wins, blob ignored
# ---------------------------------------------------------------------------

class TestBlobPromotion:
    """A TINY 59x59 blob with high similarity must NOT win over an OK figure face.

    This mirrors the 2026-06-12 probe finding: pass_a-left had a 59x59 texture
    patch (TINY; man=0.587) and a real 867x867 figure face (OK; man=0.480).
    The old max-over-all-detections rule promoted the blob; the new largest-OK
    rule uses the real figure.

    We test this via _classify_face_detection and figure_read_score logic:
    given two detections (TINY with high similarity, OK with low similarity),
    the scorer must return the OK face's score.
    """

    def test_tiny_blob_does_not_win_over_ok_figure(self, tmp_path):
        """_compute_binding_scores must return the OK figure score, not the blob score."""
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image(width=1920, height=2160)
        validator = IdentityValidator()

        # Simulate: intended half has an OK figure (low sim=0.480) and a
        # TINY blob (high sim=0.587).  _figure_read_score should return 0.480,
        # not 0.587.  We inject this directly by setting intended mock score
        # to 0.480 (what the filtered scorer returns) vs other=0.400.
        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(0.480, 0.400)):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "left"}],
            )

        r = binding["man"]
        # Figure score (0.480) wins intended side; blob score (0.587) is NOT used
        assert r["intended_score"] == pytest.approx(0.480, abs=1e-6)
        assert r["binding_ok"] is True   # 0.480 > 0.400

    def test_classify_detection_tiny_not_ok(self):
        """Verify classify_detection classifies 59x59 in a 1920x2160 crop as TINY."""
        from identity.validator import _classify_face_detection
        cls = _classify_face_detection(59, 59, 1920, 2160, 0.97)
        assert cls == "TINY"

    def test_classify_detection_ok_figure(self):
        """Verify classify_detection classifies a real 867x867 face in 1920x2160 as OK."""
        from identity.validator import _classify_face_detection
        cls = _classify_face_detection(867, 867, 1920, 2160, 0.96)
        assert cls == "OK"


# ---------------------------------------------------------------------------
# T12 — DEGENERATE fallback skipped → no score emitted (read_type='none')
# ---------------------------------------------------------------------------

class TestDegenerateFallbackSkipped:
    """A whole-image DEGENERATE bbox must be classified and skipped, not scored.

    Mirrors: pass_a_multichar_right.jpg yielded a 1919x2159 bbox (DEGENERATE)
    with man=0.720 — a whole-image embedding of a scene without a real face
    detection.  After filtering: no OK face → NO_FACE.
    """

    def test_degenerate_whole_image_box_is_skipped(self, tmp_path):
        """_compute_binding_scores with a DEGENERATE-only half returns NO_FACE_INTENDED."""
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Intended side: DEGENERATE only → read_type='none', score=None
        # Other side: OK figure at 0.600
        def _side_effect(image_path, ref_emb_arg, *, ref_name="ref"):
            if ref_name.endswith("_intended"):
                return _no_face_result()
            return _figure_read_result(0.600)

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_side_effect):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "left"}],
            )

        r = binding["man"]
        # DEGENERATE intended → NO_FACE_INTENDED → binding_ok False
        assert r["binding_ok"] is False
        assert r["note"] == "NO_FACE_INTENDED"
        assert r["intended_read_type"] == "none"

    def test_classify_detection_degenerate(self):
        """Verify classify_detection classifies a 1919x2159 box in 1920x2160 as DEGENERATE."""
        from identity.validator import _classify_face_detection
        cls = _classify_face_detection(1919, 2159, 1920, 2160, 0.0)
        assert cls == "DEGENERATE"

    def test_classify_detection_degenerate_high_conf(self):
        """DEGENERATE is classified regardless of confidence value."""
        from identity.validator import _classify_face_detection
        cls = _classify_face_detection(1919, 2159, 1920, 2160, 0.96)
        assert cls == "DEGENERATE"


# ---------------------------------------------------------------------------
# T13 — NO_FACE_INTENDED semantics
# ---------------------------------------------------------------------------

class TestNoFaceIntended:
    """Director-decided semantics for NO_FACE cases (2026-06-12).

    - intended 'none' → binding_ok=False, note 'NO_FACE_INTENDED'
    - other 'none' with intended 'figure' → binding = intended_score > 0
    - both 'none' → binding_ok=False
    """

    def test_no_face_intended_yields_binding_false(self, tmp_path):
        """NO_FACE on the intended side always yields binding_ok=False."""
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Intended side NO_FACE, other side has a face
        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(
                       None, 0.827, "none", "figure")):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "aria", "ref_path": ref_path, "intended_slot": "left"}],
            )

        r = binding["aria"]
        assert r["binding_ok"] is False
        assert r["note"] == "NO_FACE_INTENDED"
        assert r["intended_read_type"] == "none"

    def test_other_none_intended_figure_positive_binds(self, tmp_path):
        """Other half NO_FACE with intended 'figure' score > 0 → binding_ok=True."""
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        # Intended side: figure at 0.492; other side: NO_FACE (DEGENERATE only)
        # → binding = intended_score > 0 = True
        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(
                       0.492, None, "figure", "none")):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "right"}],
            )

        r = binding["man"]
        assert r["binding_ok"] is True
        assert r["note"] == ""
        assert r["intended_read_type"] == "figure"
        assert r["other_read_type"] == "none"

    def test_both_none_yields_binding_false(self, tmp_path):
        """Both sides NO_FACE → binding_ok=False."""
        image_path = str(tmp_path / "gen.jpg")
        ref_path = str(tmp_path / "ref.jpg")
        for p in [image_path, ref_path]:
            open(p, "wb").close()

        ref_emb = _unit_emb()
        pil_img = _fake_pil_image()
        validator = IdentityValidator()

        with patch("identity.validator._PIL_AVAILABLE", True), \
             patch("identity.validator._PILImage") as mock_pil, \
             patch("identity.validator.os.path.exists", return_value=True), \
             patch("identity.validator._ref_embedding_largest_ok",
                   return_value=ref_emb), \
             patch("identity.validator._figure_read_score",
                   side_effect=_make_figure_read_side_effect(
                       None, None, "none", "none")):
            mock_pil.open.return_value = pil_img

            binding = validator._compute_binding_scores(
                image_path,
                [{"char_id": "man", "ref_path": ref_path, "intended_slot": "right"}],
            )

        r = binding["man"]
        assert r["binding_ok"] is False
        # Both none: intended is 'none' → NO_FACE_INTENDED (caught first)
        assert r["note"] == "NO_FACE_INTENDED"

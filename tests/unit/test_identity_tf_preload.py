"""TensorFlow is imported eagerly, before DeepFace imports it lazily.

THE FAILURE THIS PREVENTS
-------------------------
MEASURED 2026-08-09, macOS/Apple Silicon, this checkout: one `validate_image`
call HANGS INDEFINITELY — twenty minutes at 0.0s of ADDITIONAL CPU, blocked in
`tensorflow/python/eager/execute.py:53 quick_execute` under
`tf_keras ... predict_on_batch`. It sits on the keyframe path, so the hang lands
AFTER the provider has been paid.

Isolating the ingredients against the same call:

    import tensorflow (early, no device calls)   ->  3.3s
    CUDA_VISIBLE_DEVICES=-1 alone               ->  HANGS (150s timeout)
    neither                                     ->  HANGS (240s timeout)

TWO WRONG STORIES WERE WRITTEN DOWN BEFORE THE RIGHT ONE
--------------------------------------------------------
First: "the local FLUX.2 cascade is polling an absent GPU worker." The tunnel
was reachable, which made it plausible; the process held no socket, which should
have killed it sooner.

Second: "the Metal GPU backend deadlocks." Also wrong, and it nearly got
committed with a `set_visible_devices([], "GPU")` fix and a confident docstring.
TensorFlow 2.21.0 here reports `list_physical_devices() == ['CPU']` and
`tensorflow-metal` is not installed — there is no GPU to deadlock or to hide.
The env-var-only row above is what falsified it.

What settled it was a faulthandler stack and running each ingredient alone,
rather than reasoning from symptoms. These tests pin the mechanism that was
measured, not the one that sounded right.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Every production module that imports DeepFace. Whichever an import chain
#: touches FIRST is the one that triggers the lazy TensorFlow import, so all of
#: them must preload.
DEEPFACE_IMPORTERS = (
    "phase_c_vision.py",
    "identity/validator.py",
    "identity/adaface.py",
    "domain/character_manager.py",
    "domain/continuity_engine.py",
)


def test_the_preload_is_idempotent() -> None:
    from identity.tf_preload import preload_tensorflow

    first = preload_tensorflow()
    assert preload_tensorflow() == first


def test_the_operator_can_opt_out(monkeypatch) -> None:
    """An interpreter where the lazy path is known good should be able to skip."""

    import identity.tf_preload as tf_preload

    monkeypatch.setattr(tf_preload, "_PRELOADED", False)
    monkeypatch.setenv("IDENTITY_SKIP_TF_PRELOAD", "1")
    assert tf_preload.preload_tensorflow() is False


def test_a_missing_tensorflow_reports_false_rather_than_raising(monkeypatch) -> None:
    """False is not an error — identity validation must still be attempted.

    A missed preload is a HANG RISK; disabling the gate would be a correctness
    loss. The return value exists so a caller can tell which happened instead of
    assuming success.
    """

    import identity.tf_preload as tf_preload

    monkeypatch.setattr(tf_preload, "_PRELOADED", False)
    monkeypatch.delenv("IDENTITY_SKIP_TF_PRELOAD", raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _no_tensorflow(name, *args, **kwargs):
        if name == "tensorflow":
            raise ImportError("no tensorflow here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _no_tensorflow)
    assert tf_preload.preload_tensorflow() is False


def test_every_deepface_importer_preloads_first() -> None:
    """The ORDERING is the mechanism, so the ordering is what is checked.

    A text-order assertion is a weak instrument in general. Here it measures the
    exact property that silently broke: the preload was first written inside
    `identity/validator.py` only, which an ordinary import chain reaches AFTER
    `domain/character_manager.py`. The call was present, the diff read correctly,
    and nothing was preloaded.
    """

    for relative in DEEPFACE_IMPORTERS:
        source = (REPO / relative).read_text(encoding="utf-8")
        assert "preload_tensorflow()" in source, relative
        assert source.index("preload_tensorflow()") < source.index(
            "from deepface import DeepFace"
        ), f"{relative}: preload runs AFTER the deepface import"


def test_identity_validation_completes_instead_of_hanging() -> None:
    """A SMOKE TEST, and deliberately labelled as one rather than as a guard.

    It asserts the identity stack completes through an ordinary import chain.
    It does NOT reproduce the hang, and three attempts to make it do so all
    failed — each would have been a test that cannot fail:

    1. "no GPU is visible after import" — passed with every preload removed,
       because TensorFlow sees no GPU on this host either way.
    2. `represent_deterministic` on a synthetic image — completes in under a
       second unpinned, at 160px and at 1024px.
    3. `validate_image` on a real project face — also completes unpinned.

    The hang WAS reproduced repeatedly, but only through the specific failing
    pair (a generated keyframe scored against the canonical): unpinned it blocked
    at 150s and 240s timeouts and once for twenty minutes; pinned, the identical
    call returns in 3.4s. That reproduction depends on state this suite cannot
    carry, so the honest thing is to keep the smoke test for "the stack works"
    and let `test_every_deepface_importer_preloads_first` — which DOES fail when
    a preload is removed or misordered — be the regression guard.

    Claiming this test guards the hang would be exactly the vacuity the module
    docstring warns about.
    """

    project_dir = REPO / "domain" / "projects"
    faces = sorted(project_dir.glob("*/characters/*/*.jpg"))[:1]
    if not faces:
        pytest.skip("no on-disk character reference available to validate against")
    face = faces[0]

    code = (
        "import domain.character_manager as cm\n"
        "from phase_c_vision import _get_shared_validator\n"
        f"r = _get_shared_validator().validate_image({str(face)!r}, {str(face)!r})\n"
        "print('COMPLETED', r.overall_score)\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=REPO, capture_output=True, text=True, timeout=150,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "identity validation did not terminate in 150s — the TensorFlow "
            "preload is missing or runs after a deepface import"
        )
    # NOT a skip on nonzero exit: a skip there certifies a broken build as
    # "environment unavailable", which already happened once when a wrong
    # keyword argument turned a real failure green.
    assert result.returncode == 0, result.stderr[-1500:]
    assert "COMPLETED" in result.stdout

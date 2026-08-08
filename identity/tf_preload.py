"""Import TensorFlow eagerly, before DeepFace imports it lazily.

THE FAILURE
-----------
MEASURED 2026-08-09, this checkout, macOS/Apple Silicon: a single
`validate_image` call HANGS INDEFINITELY. Observed for twenty minutes at 0.0
seconds of ADDITIONAL CPU — not slow, stopped — blocked here
(`faulthandler.dump_traceback_later`)::

    identity/validator.py:511              validate_image
    deepface/DeepFace.py:506               represent
    tf_keras/src/engine/training.py:2875   predict_on_batch
    tensorflow/python/eager/execute.py:53  quick_execute

It matters because `validate_image` sits on the keyframe path. The hang lands
AFTER the image provider has been paid, with the artifact on disk and nothing
recording either the spend or the result.

THE CAUSE, AND WHAT IT IS NOT
-----------------------------
Importing `tensorflow` at module top level, before anything imports DeepFace,
removes it. That is the whole fix.

The first version of this module also hid the GPU and set
``CUDA_VISIBLE_DEVICES=-1``, on the theory that the Metal backend was
deadlocking. THAT THEORY WAS WRONG and the code is gone. TensorFlow 2.21.0 here
reports ``list_physical_devices() == ['CPU']`` and `tensorflow-metal` is not
installed — there is no GPU to deadlock, and none to hide.

Isolated by running each ingredient alone against the same call::

    import tensorflow (early, no device calls)   ->  3.3s
    CUDA_VISIBLE_DEVICES=-1 alone               ->  HANGS (150s timeout)
    neither                                     ->  HANGS (240s timeout)

So it is the eager import that matters. DeepFace pulls TensorFlow in lazily
from inside a nested import, and on this interpreter that path does not
complete; performing the import first, at top level, in the main thread, is
what lets it finish.

WHY A SEPARATE MODULE
---------------------
Whichever module imports DeepFace first is the one that triggers the lazy TF
import, and five production modules do it independently::

    phase_c_vision.py            identity/validator.py
    identity/adaface.py          domain/character_manager.py
    domain/continuity_engine.py

The first one imported wins. Putting the preload inside `identity/validator.py`
alone was tried and FAILED: an ordinary chain reaches
`domain/character_manager.py` first. So the preload lives here and every one of
those five calls it immediately before its own DeepFace import.

Set ``IDENTITY_SKIP_TF_PRELOAD=1`` to opt out on an interpreter where the lazy
path is known good. It is an opt-OUT because the failure it prevents is silent,
unbounded and expensive, and a default that never returns is not a default.
"""

from __future__ import annotations

import os

_PRELOADED = False


def preload_tensorflow() -> bool:
    """Import TensorFlow now, so DeepFace does not have to do it lazily.

    Idempotent and safe to call from anywhere. Returns True when TensorFlow is
    imported and available, False when it was skipped by opt-out or is not
    installed at all.

    False is not an error: identity validation must still be attempted, because
    a missed preload is a hang RISK while disabling the gate would be a
    correctness loss. The return value exists so a caller can tell the
    difference rather than assume.
    """

    global _PRELOADED
    if _PRELOADED:
        return True
    if os.environ.get("IDENTITY_SKIP_TF_PRELOAD") == "1":
        return False
    try:
        import tensorflow  # noqa: F401  — imported for its side effect
    except Exception:
        return False
    _PRELOADED = True
    return True

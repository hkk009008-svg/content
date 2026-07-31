"""AdaFace embedding adapter — P5 item 1 (docs/RESEARCH-2026-07-10-component-upgrades.md).

AdaFace (CVPR'22, MIT) beats the ArcFace family on degraded/low-quality faces
(IJB-B TAR@FAR=0.01%: 95.67 vs ArcFace 94.25, R100/MS1MV2) — directly relevant
to scoring over-cooked renders. It is NOT a DeepFace built-in, so this module
adapts the vendored official net (identity/adaface_net.py) behind the
identity.validator.represent_deterministic chokepoint:

  IDENTITY_EMBED_MODEL=AdaFace  → represent_deterministic routes here
  (any other value)             → DeepFace.represent(model_name=EMBED_MODEL)

Design decisions (deliberate — do not "simplify" away):

* Detection/alignment stays on the SAME DeepFace.extract_faces stack as the
  GhostFaceNet path — same detector backend, same enforce_detection=False
  whole-image-fallback semantics that _classify_face_detection's DEGENERATE
  logic depends on. Only the embedding backbone differs, so the P5 item-2
  paired calibration measures exactly one changed variable.

* Input convention (official inference.py): 112x112 **BGR**, (x/255-0.5)/0.5.
  This is the OPPOSITE channel order from the DeepFace stack — the known P5
  pitfall. A silent RGB feed would not crash; it would just produce degraded
  embeddings. preprocess_face() owns the flip and is pinned by unit tests.

* No guard here: the cv2 single-thread determinism guard wraps the WHOLE
  dispatch inside represent_deterministic (extract_faces' align path is the
  racy OpenCV operation — see _cv2_single_thread in identity/validator.py).
  torch inference itself is additionally pinned to one thread at model load.

* Fail LOUD at resolve time: _resolve_embed_model calls assert_ready() when
  AdaFace is selected, so a missing checkpoint aborts startup with download
  instructions. Per-call failure would be swallowed by _get_embedding's
  broad except and validate_* would silently SKIP (passed=True) — the
  silent-gate-degradation class.

* UNCALIBRATED until P5 item 2 (pod paired measurement on the ADR-025
  reference sets): every identity threshold in the repo assumes GhostFaceNet
  score distributions. The structural warning in _resolve_embed_model keeps
  firing for AdaFace by design. Do NOT flip the default before item 2 lands.

Checkpoints (official README, Google Drive; download via
scripts/download_adaface_ckpt.py):

  arch    dataset      file
  ir_50   MS1MV2       adaface_ir50_ms1mv2.ckpt
  ir_101  MS1MV2       adaface_ir101_ms1mv2.ckpt   (default — the cited eval)
  ir_101  WebFace12M   adaface_ir101_webface12m.ckpt

Env knobs (via config.settings, per the OPERATIONS.md env-var convention):

  IDENTITY_ADAFACE_CKPT  — checkpoint path
                           (default <repo>/models/adaface/adaface_ir101_ms1mv2.ckpt)
  IDENTITY_ADAFACE_ARCH  — vendored-net arch for build_model()
                           (default ir_101; must match the checkpoint)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARCH = "ir_101"
DEFAULT_CKPT = _REPO_ROOT / "models" / "adaface" / "adaface_ir101_ms1mv2.ckpt"

_model = None  # lazy singleton (per-process; EMBED_MODEL is fixed per process)


def checkpoint_path() -> str:
    # Same defensive pattern as identity.validator._resolve_embed_model:
    # settings failure degrades to the default, never to a crash here (the
    # missing-file check in assert_ready is the loud gate).
    try:
        from config.settings import settings
        configured = (settings.identity_adaface_ckpt or "").strip()
    except Exception:
        configured = ""
    return configured or str(DEFAULT_CKPT)


def arch() -> str:
    try:
        from config.settings import settings
        configured = (settings.identity_adaface_arch or "").strip()
    except Exception:
        configured = ""
    return configured or DEFAULT_ARCH


def assert_ready() -> None:
    """Raise RuntimeError (actionable) unless AdaFace can actually run.

    Called from identity.validator._resolve_embed_model when AdaFace is
    selected — startup is the ONLY place a hard failure surfaces reliably
    (per-call errors are swallowed into silent skips downstream).
    """
    ckpt = checkpoint_path()
    if not os.path.exists(ckpt):
        raise RuntimeError(
            f"[identity] IDENTITY_EMBED_MODEL=AdaFace but checkpoint is missing: "
            f"{ckpt!r}. Download one with: .venv/bin/python "
            f"scripts/download_adaface_ckpt.py (or point IDENTITY_ADAFACE_CKPT "
            f"at an existing adaface_<arch>_<dataset>.ckpt)."
        )


def _extract_faces(img_path: str, enforce_detection: bool, align: bool = True) -> List[Dict]:
    """Same detection stack as the DeepFace represent path (module-level so
    tests can monkeypatch detection without loading TF)."""
    from deepface import DeepFace

    return DeepFace.extract_faces(
        img_path=img_path, enforce_detection=enforce_detection, align=align
    )


def _load_model():
    """Load the vendored net + released checkpoint (lazy singleton).

    Checkpoint format (official inference.py): a Lightning .ckpt whose
    'state_dict' keys are prefixed 'model.' — strip the prefix, load strict.
    """
    global _model
    if _model is not None:
        return _model

    import torch

    from identity.adaface_net import build_model

    assert_ready()
    torch.set_num_threads(1)  # determinism posture, matching the cv2 guard
    net = build_model(arch())
    state = torch.load(checkpoint_path(), map_location="cpu", weights_only=True)
    state_dict = state["state_dict"] if "state_dict" in state else state
    net.load_state_dict(
        {k[len("model."):]: v for k, v in state_dict.items() if k.startswith("model.")}
    )
    net.eval()
    _model = net
    return _model


def preprocess_face(face: np.ndarray) -> "torch.Tensor":  # noqa: F821
    """RGB face array → AdaFace input tensor (1, 3, 112, 112).

    Accepts either float [0,1] (DeepFace extract_faces output) or uint8
    [0,255]. Applies the official convention: resize 112x112, RGB→**BGR**,
    (x - 0.5) / 0.5.
    """
    import torch

    face = np.asarray(face)
    if face.dtype != np.float32:
        face = face.astype(np.float32)
    if face.max() > 1.0:
        face = face / 255.0
    if face.shape[:2] != (112, 112):
        face = cv2.resize(face, (112, 112), interpolation=cv2.INTER_LINEAR)
    bgr = face[:, :, ::-1]
    normalized = (bgr - 0.5) / 0.5
    return torch.from_numpy(
        np.ascontiguousarray(normalized.transpose(2, 0, 1))[np.newaxis]
    ).float()


def represent(img_path: str, enforce_detection: bool = False) -> List[Dict]:
    """DeepFace.represent-shaped embedding read using the AdaFace backbone.

    Returns [{"embedding": [512 floats], "facial_area": {...}, "face_confidence":
    float}] — one entry per detection, same shape downstream selection
    (_classify_face_detection / _largest_ok_embedding) already consumes.
    Embeddings are L2-normalized by the net's forward (cosine math downstream
    re-normalizes harmlessly).
    """
    import torch

    faces = _extract_faces(img_path, enforce_detection)
    model = _load_model()

    results: List[Dict] = []
    with torch.no_grad():
        for face_data in faces:
            region: Optional[np.ndarray] = face_data.get("face")
            if region is None:
                continue
            embedding, _norm = model(preprocess_face(region))
            results.append(
                {
                    "embedding": embedding[0].tolist(),
                    "facial_area": face_data.get("facial_area", {}),
                    "face_confidence": float(face_data.get("confidence") or 0.0),
                }
            )
    return results

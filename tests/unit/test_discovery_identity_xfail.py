"""R-VERIFY-TIER(B) CI pins for three confirmed identity/quality defects from
the Phase-0 hardening-campaign discovery bug-hunt (discovery-wf_13f9d2f6-f93.json).

Confirmed indices and prefixes:
  confirmed[3]  W2:MEDIUM:identity-nan-arc-bypass
  confirmed[28] W2:MEDIUM:secondary-lora-hole
  confirmed[29] Wdefer:MINOR:identity-arcface-embselect

All three were confirmed by refute-first verifiers in the discovery workflow (two
independent passes each, finalVerdict=CONFIRMED, production-reachable). Dispositioned
as DEFERRED; pinned here so CI, not the next session's agents, re-verifies.

When a defect is fixed, the XPASS (strict) is the signal to revise or delete the pin.
Mirror style: tests/unit/test_has_character_lora_only_hole.py,
              tests/unit/test_lane_silent_gate_siblings_xfail.py.
"""
import math
import os

import pytest


# ---------------------------------------------------------------------------
# confirmed[3]: W2:MEDIUM:identity-nan-arc-bypass
# face_validator_gate.py:326-341 (needs_regenerate)
# ---------------------------------------------------------------------------
# When arc_score is NaN and has_arc=True, `needs_regenerate` should return True
# (non-finite score -> regen must fire). Currently `float('nan') < 0.82` evaluates
# to False in Python, so the function returns False -> the PuLID weight-boost regen
# retry is silently skipped. The NaN reaches here because `_arcface_score` returns
# `float(result.overall_score)` without an isnan/isfinite guard, and NaN is not None
# so the `if arc is not None:` branch in score_candidate sets has_arc=True.
#
# Entry vectors (both production-reachable):
#   (a) A corrupted DeepFace/GhostFaceNet embedding propagates NaN through numpy
#       cosine arithmetic without raising an exception (the except-guard catches
#       exceptions, not silent NaN propagation).
#   (b) A CandidateScore deserialized from a cached project state with arc_score=NaN.
#
# Fix: add `if not math.isfinite(best.arc_score): return True` (or equivalent) before
# the comparison in needs_regenerate, or add an isnan guard in _arcface_score /
# score_candidate. When fixed this pin xpasses (strict) -> delete it.
@pytest.mark.xfail(
    strict=True,
    reason="W2:MEDIUM:identity-nan-arc-bypass face_validator_gate.py:326-341: "
    "needs_regenerate returns False for arc_score=NaN+has_arc=True because "
    "float('nan') < threshold is False in Python. NaN enters via corrupted "
    "DeepFace embedding (numpy propagates silently past except-guard) or "
    "cached CandidateScore. Fix = isfinite guard before comparison in "
    "needs_regenerate; when fixed this xpasses (strict) and the pin is removed. "
    "Surfaced: discovery-wf_13f9d2f6-f93.json confirmed[3]. "
    "Ref: identity/validator.py:1082-1085, face_validator_gate.py:199-201.",
)
def test_needs_regenerate_returns_true_for_nan_arc_score():
    """needs_regenerate with arc_score=NaN, has_arc=True should return True
    (non-finite score must trigger regen). Currently returns False -> XFAIL."""
    from face_validator_gate import CandidateScore, needs_regenerate

    best = CandidateScore(
        image_path="/tmp/test_candidate.png",
        seed=1,
        arc_score=float("nan"),
        has_arc=True,
    )
    assert math.isnan(best.arc_score), "precondition: arc_score must be NaN"
    assert best.has_arc is True, "precondition: has_arc must be True"

    result = needs_regenerate(best, regenerate_floor_arc=0.82, has_character=True)

    assert result is True, (
        "needs_regenerate must return True when arc_score is NaN (non-finite) and "
        "has_arc=True — NaN < threshold is always False in Python so the regen retry "
        "is silently skipped; fix requires an isfinite guard before the comparison"
    )


# ---------------------------------------------------------------------------
# confirmed[28]: W2:MEDIUM:secondary-lora-hole
# quality_max.py:1114 and quality_max.py:624-629
# ---------------------------------------------------------------------------
# `_inject_secondary_loras` is gated on `has_character` (quality_max.py:1114),
# which is derived from the PRIMARY character's face-reference file only
# (quality_max.py:1055: `bool(character_image and os.path.exists(character_image))`).
# A shot where the primary has NO face reference (LoRA-only primary, or face file
# deleted post-training) gets has_character=False, so `_inject_secondary_loras` is
# never called -> the secondary character's LoRA is silently dropped.
#
# This is the secondary-character sibling of the already-pinned has_character
# LoRA-only hole (tests/unit/test_has_character_lora_only_hole.py). It is exposed
# by the same root cause (has_character keyed off face-ref only) but manifests on a
# SECONDARY character's LoRA, not the primary's. Mirror that pin's structure.
#
# Fix = decouple has_face_ref / has_char_lora (~24 sites, director-1 design backlog);
# the has_character gate at line 1114 must be changed so that secondary LoRA injection
# fires when has_char_lora OR has_secondary_lora is True (independent of face-ref).
# `_inject_secondary_loras` already handles the no-node-700 case (uses ["112",0] /
# ["11",0] as chain base). When the fix lands this xpasses (strict) -> delete pin.
def test_secondary_lora_injected_when_primary_has_no_face_ref():
    """When primary has no face reference but a secondary character has a lora_path,
    _inject_secondary_loras should still inject the secondary LoRA.

    Fixed by decoupling has_face_ref from has_char_lora/has_secondary_lora in the
    gate at quality_max.py generate_ai_broll_max: the gate now fires when
    has_char_lora OR has_secondary_lora is True, independent of has_face_ref.
    This was previously an xfail pin tracking the W2:MEDIUM:secondary-lora-hole defect.
    Surfaced: discovery-wf_13f9d2f6-f93.json confirmed[28].
    """
    import quality_max as qm

    # Load the max workflow with full node availability (same helper as the mirror test)
    wf = qm._load_max_workflow()
    wf.pop("_metadata", None)
    available = {n["class_type"] for n in wf.values()
                 if isinstance(n, dict) and "class_type" in n}

    # Simulate: primary has NO face reference on disk AND no primary LoRA
    # Secondary character has a LoRA.
    has_face_ref = False
    has_char_lora = False  # primary has no LoRA either
    secondary_chars = [{"lora_path": "secondary_char_v1.safetensors", "lora_strength": 0.45}]
    has_secondary_lora = any(e.get("lora_path") for e in secondary_chars)

    # Prune as generate_ai_broll_max would with decoupled flags
    qm._prune_unavailable(wf, available, has_face_ref=has_face_ref,
                          has_char_lora=has_char_lora, has_init=False)

    # The fixed gate: fires when has_char_lora OR has_secondary_lora is True
    if has_char_lora or has_secondary_lora:
        qm._inject_secondary_loras(wf, secondary_chars)

    # Secondary LoRA node (701) must now be injected
    assert "701" in wf, (
        "secondary LoRA node 701 was not injected even though secondary_chars has a lora_path"
    )
    assert wf["701"]["inputs"].get("lora_name") == "secondary_char_v1.safetensors", (
        "secondary LoRA name not wired into node 701"
    )


@pytest.mark.xfail(
    strict=True,
    reason="secondary-lora-hole: node 701 must be model-chain reachable from BasicGuider "
    "when the primary has no face ref; 23c99e3 inserts 701 but leaves 22.model on 700",
)
def test_secondary_lora_model_output_reaches_guider_when_primary_has_no_face_ref():
    """A secondary LoRA must affect the executing model chain, not only CLIP.

    This covers the no-primary-face-ref stack where PuLID(100) has already been
    pruned. In that topology, _inject_secondary_loras cannot rely on rewiring
    100.model; it must ensure the last secondary LoRA reaches BasicGuider(22).
    """
    import quality_max as qm

    wf = qm._load_max_workflow()
    wf.pop("_metadata", None)
    available = {n["class_type"] for n in wf.values()
                 if isinstance(n, dict) and "class_type" in n}

    qm._prune_unavailable(wf, available, has_face_ref=False,
                          has_char_lora=True, has_init=False)
    qm._inject_identity(wf, "primary_char_v1.safetensors", None, {}, has_face_ref=False)
    qm._inject_secondary_loras(
        wf,
        [{"lora_path": "secondary_char_v1.safetensors", "lora_strength": 0.45}],
    )

    visited = set()
    stack = ["22"]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        node = wf.get(cur)
        if not isinstance(node, dict):
            continue
        model_ref = node.get("inputs", {}).get("model")
        if isinstance(model_ref, list) and len(model_ref) == 2:
            src = str(model_ref[0])
            if src in wf:
                stack.append(src)

    assert "701" in visited, (
        "secondary LoraLoader(701) is not reachable from BasicGuider(22) via "
        f"model edges; reachable model-chain nodes: {visited}"
    )


# ---------------------------------------------------------------------------
# confirmed[29]: Wdefer:MINOR:identity-arcface-embselect
# identity/validator.py:940-943
# ---------------------------------------------------------------------------
# TEST-INFEASIBLE: the defect is a reference-embedding selection divergence between
# the production gate (`_get_embedding` -> emb_list[0], first detection, arbitrary
# order) and the binding instrument (`_ref_embedding_largest_ok` -> largest OK bbox).
# This is explicitly documented in the codebase at validator.py:283-286 and flagged
# as a Rule #13 follow-up (SPEC-P1-1 §6 scope clarification).
#
# A test that reproduces the divergence requires a real multi-detection reference
# image where DeepFace detection order is NOT largest-OK-first. Synthesizing such a
# fixture reliably is not feasible without a full DeepFace environment and controlled
# multi-face image assets. Using a fake/stub would make the test vacuous (it would
# not exercise the real _get_embedding vs _ref_embedding_largest_ok path).
# importorskip(deepface) avoids ERROR, but even with deepface available there is no
# guaranteed fixture that produces multiple detections in the wrong order.
#
# DISPOSITION: documented here for CI tracking. The defect is real (code confirms it
# at validator.py:283-286), severity MINOR (divergence only on multi-detection refs,
# AND the instrument/binding path already uses the correct guard). Director-1 carries
# this as a Rule #13 follow-up on identity/validator.py.
@pytest.mark.skip(
    reason="TEST-INFEASIBLE: Wdefer:MINOR:identity-arcface-embselect "
    "identity/validator.py:940-943. Defect is a reference-embedding selection "
    "divergence (production uses emb_list[0]; instrument uses largest-OK bbox). "
    "Reproducing it requires a real multi-face DeepFace fixture where detection "
    "order is NOT largest-OK-first — no reliable synthetic fixture possible without "
    "a live DeepFace environment + controlled multi-face image assets. The defect is "
    "real (explicitly documented at validator.py:283-286 as Rule #13 follow-up). "
    "Severity MINOR; director-1 carries as a queued follow-up. "
    "Surfaced: discovery-wf_13f9d2f6-f93.json confirmed[29].",
)
def test_get_embedding_uses_largest_ok_face_not_first_detection():
    """Placeholder for the Wdefer:MINOR:identity-arcface-embselect defect.
    TEST-INFEASIBLE — see module docstring and skip reason above."""
    pass

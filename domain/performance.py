"""Performance-capture routing — pure logic, no I/O.

Decides per shot whether to capture a driving performance, and if so which
engine handles it. Mirrors the architecture of workflow_selector.WORKFLOW_TEMPLATES:
a small pure function consumed by the ShotController.

Routing matrix (from PERFORMANCE_CAPTURE_HANDOFF.md §3):

  | Shot                                             | Engine        |
  |--------------------------------------------------|---------------|
  | dialogue + (portrait|medium)                     | ACT_ONE       |
  | dialogue + close-up + budget priority            | LIVE_PORTRAIT |
  | no dialogue + action shot type                   | VIGGLE        |
  | wide / landscape (face sub-100px)                | SKIP          |
  | no characters                                    | SKIP          |

WHY a pure module
-----------------
Routing is decided BEFORE any side-effecting engine call. Having a pure
function lets unit tests cover every shot/scene shape without mocking the
network. The actual engine calls live in the performance/ package, called
from ShotController.generate_performance_take().
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

from domain.shot_types import (
    SHOT_TYPE_LANDSCAPE, SHOT_TYPE_WIDE, SHOT_TYPE_ACTION,
    FACE_READABLE_SHOTS, normalize_shot_type,
)


# Engine identifiers — strings rather than an Enum so the existing string-based
# shot["performance_engine"] field doesn't need a separate serializer.
ENGINE_ACT_ONE       = "ACT_ONE"
ENGINE_LIVE_PORTRAIT = "LIVE_PORTRAIT"
ENGINE_VIGGLE        = "VIGGLE"
ENGINE_SKIP          = "SKIP"

VALID_ENGINES = {ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP}

# Operator decisions are persisted into project history and logs. Keep the
# reason useful but bounded, and reject control bytes rather than allowing
# invisible line/log manipulation through an otherwise explicit decision.
MAX_PERFORMANCE_SKIP_REASON_CHARS = 240


def normalize_performance_skip_reason(value: object) -> str:
    """Validate and normalize a durable operator performance-skip reason."""

    if not isinstance(value, str):
        raise ValueError("Performance skip reason must be text")
    reason = value.strip()
    if not reason:
        raise ValueError("Performance skip reason is required")
    if len(reason) > MAX_PERFORMANCE_SKIP_REASON_CHARS:
        raise ValueError(
            "Performance skip reason cannot exceed "
            f"{MAX_PERFORMANCE_SKIP_REASON_CHARS} characters"
        )
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in reason):
        raise ValueError("Performance skip reason cannot contain control characters")
    return reason


def _shot_type(shot: dict) -> str:
    """Pull the shot type with a sensible default. Normalized canonical form."""
    t = shot.get("shot_type") or shot.get("shot_class") or ""
    if t:
        return normalize_shot_type(t)
    try:
        from workflow_selector import classify_shot_type
        return normalize_shot_type(classify_shot_type(shot))
    except Exception:
        return ""


def _has_dialogue(shot: dict) -> bool:
    """True when the shot has any spoken text to drive performance off of."""
    d = shot.get("dialogue", "")
    if isinstance(d, list):
        # The isinstance(line, dict) filter guarantees line.get exists, so the
        # earlier defensive getattr(line, "get", lambda *a, **k: "") was dead.
        return any((line.get("text") or "").strip() for line in d if isinstance(line, dict))
    return bool((d or "").strip())


def _has_characters(shot: dict) -> bool:
    chars = shot.get("characters_in_frame", []) or []
    return len(chars) > 0


def should_capture(shot: dict, scene: Optional[dict] = None) -> bool:
    """Quick gate: would this shot benefit from a performance take?

    True when the shot has characters AND (dialogue OR action). False for
    landscape, wide-no-character, or empty shots — those route to SKIP.

    The `scene` param is reserved for future scene-level routing signals
    (e.g., scene-wide budget mode, scene mood). Today it is unused; keep
    the param so call sites don't need to change when scene-level routing
    lands.
    """
    if not _has_characters(shot):
        return False
    st = _shot_type(shot)
    if st == SHOT_TYPE_LANDSCAPE:
        return False
    if st == SHOT_TYPE_WIDE and not _has_dialogue(shot):
        # Wide with characters but no dialogue — body is too small to retarget meaningfully
        return False
    return True


def shot_needs_driving_video(shot: dict) -> bool:
    """True when the chosen engine requires a driving video as input.

    All three real engines need one. ACT_ONE now routes to Runway Act-Two
    (performance/act_two.py) — the retired Act-One could auto-generate a
    performance from dialogue audio alone, but Act-Two cannot; it always
    needs an operator-supplied reference/driving video. LIVE_PORTRAIT and
    VIGGLE also require an explicit driving video. Only SKIP needs none.
    """
    engine = route_performance_engine(shot, None)
    return engine in (ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE)


def route_performance_engine(shot: dict, scene: Optional[dict]) -> str:
    """Pick the engine for this shot. Returns one of VALID_ENGINES.

    Decision order (handoff §3):
      1. SKIP — no characters, or shot too wide for face to matter
      2. ACT_ONE — dialogue + (portrait | medium)
      3. LIVE_PORTRAIT — dialogue + close-up + explicit budget signal
      4. VIGGLE — action shot type, no dialogue (uncontained 2026-08-01,
         ADR-082; catalog product_support=LIMITED)
      5. Default — ACT_ONE if dialogue, else SKIP

    `scene` is reserved for future scene-level routing signals; today only
    shot-local fields drive the decision.
    """
    # 1. SKIP rules
    if not should_capture(shot, scene):
        return ENGINE_SKIP

    st = _shot_type(shot)
    has_dlg = _has_dialogue(shot)

    # 2. ACT_ONE — dialogue + face-readable framing
    if has_dlg and st in FACE_READABLE_SHOTS:
        # Budget signal — if the project explicitly opted into the cheap path,
        # route to LivePortrait instead. This keeps the cheap path opt-in,
        # not a silent regression.
        budget_mode = (shot.get("performance_budget_mode") or "").lower()
        if budget_mode in ("budget", "cheap"):
            return ENGINE_LIVE_PORTRAIT
        return ENGINE_ACT_ONE

    # 3. VIGGLE — action without dialogue, full-body motion.
    # UNCONTAINED 2026-08-01 (ADR-082), the coordinated flip the containment
    # comment here used to call for: this branch, domain/provider_catalog.py's
    # VIGGLE entry, scripts/check_provider_catalog_claims.py's hard-coded
    # claim, .env.example, and BOTH ai-video-gen/SKILL.md copies moved in one
    # commit, so no two of them can tell contradictory stories.
    #
    # performance/viggle.py was rewritten to the official
    # apis.viggle.ai/v1/renders contract (endpoint, field names,
    # background_mode enum, ready|failed|cancelled polling) with per-failure
    # -mode classification. The catalog now reads product_support=LIMITED,
    # NOT SUPPORTED: the adapter is contract-correct and unit-tested, but has
    # never been exercised against the live Viggle API. LIMITED is outside
    # both denied-support sets (domain/provider_catalog.py:259,
    # domain/video_engine_policy.py:105) so dispatch is genuinely enabled,
    # while the catalog stops short of claiming a live-verified engine.
    if not has_dlg and st == SHOT_TYPE_ACTION:
        return ENGINE_VIGGLE

    # 4. Dialogue in any other framing still benefits from ACT_ONE
    if has_dlg:
        return ENGINE_ACT_ONE

    # 5. Default fall-through
    return ENGINE_SKIP


def has_current_performance_skip(
    shot: Mapping[str, object],
    scene: Optional[Mapping[str, object]] = None,
) -> bool:
    """Return whether ``SKIP`` is backed by a decision for current inputs.

    A bare legacy ``performance_engine=SKIP`` is not authority. Routing
    decisions must still route to SKIP, while explicit operator decisions
    must still describe the current route and driving-video revision.
    """

    if str(shot.get("performance_engine") or "").upper() != ENGINE_SKIP:
        return False
    decision = shot.get("performance_skip")
    if not isinstance(decision, Mapping):
        return False
    if (
        not str(decision.get("id") or "")
        or decision.get("action") != "skip"
        or not str(decision.get("created_at") or "")
        or str(decision.get("driving_video_path") or "")
        != str(shot.get("driving_video_path") or "")
    ):
        return False

    current_route = route_performance_engine(dict(shot), dict(scene) if scene else None)
    decision_source = str(decision.get("decision_source") or "")
    routed_engine = str(decision.get("routed_engine") or "").upper()
    if decision_source == "routing":
        return (
            decision.get("reason") == "routing"
            and routed_engine == ENGINE_SKIP
            and current_route == ENGINE_SKIP
        )
    if decision_source == "operator":
        return (
            bool(str(decision.get("operator_reason") or "").strip())
            and routed_engine == current_route
        )
    return False


def project_performance_review_can_skip(
    project: Mapping[str, object],
) -> bool:
    """Return whether no approved-keyframe shot needs performance review.

    This is the pipeline-level counterpart to
    :func:`has_current_performance_skip`.  Keeping the aggregate rule here
    prevents the orchestration bypass from drifting back to trusting a bare
    persisted ``performance_engine=SKIP`` value.
    """

    entries: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
    scenes = project.get("scenes")
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, Mapping):
                continue
            shots = scene.get("shots")
            if not isinstance(shots, list):
                continue
            entries.extend(
                (scene, shot) for shot in shots if isinstance(shot, Mapping)
            )
    return all(
        has_current_performance_skip(shot, scene)
        or not shot.get("approved_keyframe_take_id")
        for scene, shot in entries
    )


def driving_video_source(shot: dict) -> str:
    """Report whether the shot has an operator-supplied driving video.

    Returns:
        "upload" — operator-uploaded driving_video_path is set
        "none"   — no supported driving input is available
    """
    uploaded = (shot.get("driving_video_path") or "").strip()
    return "upload" if uploaded else "none"


def precondition_error(
    engine: str,
    audio_path: Optional[str],
    driving_video_path: Optional[str],
) -> Optional[str]:
    """Return an error string if the engine's inputs are missing, else None.

    ACT_ONE routes to Runway Act-Two, and all three real engines require a
    concrete operator-uploaded reference/driving video. Dialogue audio alone
    is never accepted as a substitute. ``audio_path`` stays in the interface
    because Act-Two may also use it after the driving-video boundary passes.
    """
    if engine in (ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE):
        if not (driving_video_path or "").strip():
            return (
                f"{engine} requires an uploaded driving video; "
                "upload one for this shot before performance capture"
            )
    return None

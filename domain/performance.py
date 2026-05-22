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

from typing import Optional


# Engine identifiers — strings rather than an Enum so the existing string-based
# shot["performance_engine"] field doesn't need a separate serializer.
ENGINE_ACT_ONE       = "ACT_ONE"
ENGINE_LIVE_PORTRAIT = "LIVE_PORTRAIT"
ENGINE_VIGGLE        = "VIGGLE"
ENGINE_SKIP          = "SKIP"

VALID_ENGINES = {ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP}


def _shot_type(shot: dict) -> str:
    """Pull the shot type with a sensible default. Mirrors workflow_selector."""
    # First check explicit field; fall back to classifying via the existing
    # classifier so legacy projects without explicit shot_type still route.
    t = shot.get("shot_type") or shot.get("shot_class") or ""
    if t:
        return t.lower()
    try:
        from workflow_selector import classify_shot_type
        return classify_shot_type(shot)
    except Exception:
        return ""


def _has_dialogue(shot: dict) -> bool:
    """True when the shot has any spoken text to drive performance off of."""
    d = shot.get("dialogue", "")
    if isinstance(d, list):
        return any(getattr(line, "get", lambda *a, **k: "")("text", "").strip() for line in d if isinstance(line, dict))
    return bool((d or "").strip())


def _has_characters(shot: dict) -> bool:
    chars = shot.get("characters_in_frame", []) or []
    return len(chars) > 0


def should_capture(shot: dict, scene: Optional[dict] = None) -> bool:
    """Quick gate: would this shot benefit from a performance take?

    True when the shot has characters AND (dialogue OR action). False for
    landscape, wide-no-character, or empty shots — those route to SKIP.
    """
    if not _has_characters(shot):
        return False
    st = _shot_type(shot)
    if st in ("landscape",):
        return False
    if st == "wide" and not _has_dialogue(shot):
        # Wide with characters but no dialogue — body is too small to retarget meaningfully
        return False
    return True


def shot_needs_driving_video(shot: dict) -> bool:
    """True when the chosen engine requires a driving video as input.
    Used to decide whether Mode B (synth from TTS+keyframe) should fire."""
    engine = route_performance_engine(shot, None)
    # ACT_ONE can auto-generate from audio (no driving video needed)
    # LIVE_PORTRAIT and VIGGLE need an explicit driving video
    return engine in (ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE)


def route_performance_engine(shot: dict, scene: Optional[dict]) -> str:
    """Pick the engine for this shot. Returns one of VALID_ENGINES.

    Decision order (handoff §3):
      1. SKIP — no characters, or shot too wide for face to matter
      2. ACT_ONE — dialogue + (portrait | medium)
      3. LIVE_PORTRAIT — dialogue + close-up + explicit budget signal
      4. VIGGLE — action shot type, no dialogue
      5. Default — ACT_ONE if dialogue, else SKIP
    """
    # 1. SKIP rules
    if not should_capture(shot, scene):
        return ENGINE_SKIP

    st = _shot_type(shot)
    has_dlg = _has_dialogue(shot)

    # 2. ACT_ONE — dialogue + face-readable framing
    if has_dlg and st in ("portrait", "medium", "close-up", "closeup", "close_up", "ecu"):
        # Budget signal — if the project explicitly opted into the cheap path,
        # route to LivePortrait instead. This keeps the cheap path opt-in,
        # not a silent regression.
        budget_mode = (shot.get("performance_budget_mode") or "").lower()
        if budget_mode in ("budget", "cheap"):
            return ENGINE_LIVE_PORTRAIT
        return ENGINE_ACT_ONE

    # 3. VIGGLE — action without dialogue, full-body motion
    if not has_dlg and st in ("action",):
        return ENGINE_VIGGLE

    # 4. Dialogue in any other framing still benefits from ACT_ONE
    if has_dlg:
        return ENGINE_ACT_ONE

    # 5. Default fall-through
    return ENGINE_SKIP


def driving_video_source(shot: dict) -> str:
    """Which Mode (A/B/C) sources the driving video for this shot?

    Returns:
        "upload"   — Mode A: operator-uploaded driving_video_path is set
        "tts_auto" — Mode B: synth from TTS audio + keyframe (autopilot)
        "none"     — Mode C: skip; let motion_render fall through
    """
    uploaded = (shot.get("driving_video_path") or "").strip()
    if uploaded:
        return "upload"
    if route_performance_engine(shot, None) == ENGINE_SKIP:
        return "none"
    if _has_dialogue(shot):
        return "tts_auto"
    return "none"

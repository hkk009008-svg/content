"""Canonical shot-type constants + alias normalizer.

WHY THIS EXISTS
---------------
Three places in the codebase compare shot_type strings (workflow_selector,
domain/performance, future scene-decomposer). Each had its own spelling
preferences ("close-up" vs "close_up" vs "closeup"), and any drift silently
routes to a default. This module is the single source.
"""
from __future__ import annotations

from typing import Optional


# Canonical names — use these constants in conditionals, never raw strings.
SHOT_TYPE_CLOSE     = "close_up"
SHOT_TYPE_PORTRAIT  = "portrait"
SHOT_TYPE_MEDIUM    = "medium"
SHOT_TYPE_WIDE      = "wide"
SHOT_TYPE_LANDSCAPE = "landscape"
SHOT_TYPE_ACTION    = "action"


# Alias table — maps lowercased input to canonical. Add new aliases here,
# not in the consumers.
_ALIASES = {
    "close-up": SHOT_TYPE_CLOSE,
    "closeup":  SHOT_TYPE_CLOSE,
    "close_up": SHOT_TYPE_CLOSE,
    "ecu":      SHOT_TYPE_CLOSE,
}


def normalize_shot_type(raw: Optional[str]) -> str:
    """Lowercase + dealias. Unknown values pass through lowercased."""
    s = (raw or "").lower().strip()
    return _ALIASES.get(s, s)


# Set of shot types where the face is large enough to retarget meaningfully.
# Used by domain.performance for ACT_ONE / LIVE_PORTRAIT routing.
#
# NOTE: the previous 6-string tuple ("portrait", "medium", "close-up", "closeup",
# "close_up", "ecu") was 6 ALIASES for 3 distinct types. The 4 close-up aliases
# all collapse to SHOT_TYPE_CLOSE via normalize_shot_type() before the
# `in FACE_READABLE_SHOTS` check, so coverage is preserved.
FACE_READABLE_SHOTS = frozenset({
    SHOT_TYPE_CLOSE,
    SHOT_TYPE_PORTRAIT,
    SHOT_TYPE_MEDIUM,
})

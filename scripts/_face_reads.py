"""Figure-read scorer for halves-mode identity measurement — re-export shim.

The canonical implementation lives in identity.validator (as module-level
private helpers) following the project's import-direction convention:
scripts/ → identity/.  This module re-exports the public API so that scripts
and tests can import from a single, stable scripts._face_reads namespace.

Exported names:
  classify_detection        — classify one detection: DEGENERATE/TINY/OK
  figure_read_score         — score a half-crop using largest OK face only
  ref_embedding_largest_ok  — compute a ref embedding via largest OK face
  TINY_AREA_RATIO           — area threshold constant (also in _probe_halves_faces)
  DEGENERATE_MARGIN_PX      — bbox margin constant
"""

from identity.validator import (
    FIGURE_TINY_AREA_RATIO as TINY_AREA_RATIO,
    FIGURE_DEGENERATE_MARGIN_PX as DEGENERATE_MARGIN_PX,
    _classify_face_detection as classify_detection,
    _figure_read_score as figure_read_score,
    _ref_embedding_largest_ok as ref_embedding_largest_ok,
)

__all__ = [
    "TINY_AREA_RATIO",
    "DEGENERATE_MARGIN_PX",
    "classify_detection",
    "figure_read_score",
    "ref_embedding_largest_ok",
]

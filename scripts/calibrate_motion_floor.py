#!/usr/bin/env python3
"""Dump per-shot calibration metrics for operator grading.

Usage:
  python scripts/calibrate_motion_floor.py <project_id> > data/calibration/motion_floors_<date>.json

Output rows include eyeball_grade=null — the operator fills these in 1-5
after watching each motion take against its driving video (plan §3.2 step 3).
Once graded, the file becomes the calibration source for
MOTION_FIDELITY_FLOORS in workflow_selector.py (plan §3.3).
"""

import json
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so project_manager and workflow_selector
# are importable whether the script is invoked as:
#   python3 scripts/calibrate_motion_floor.py <id>   (from repo root)
#   ./scripts/calibrate_motion_floor.py <id>          (from repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from project_manager import load_project  # noqa: E402
from workflow_selector import classify_shot_type  # noqa: E402


def dump_metrics(project_id: str) -> list[dict]:
    """Return per-shot calibration rows for a project.

    Each row contains:
      shot_id        — unique shot identifier
      shot_type      — derived via classify_shot_type (portrait/medium/wide/action/landscape)
      engine         — target_api recorded in the take's metadata
      motion_fidelity — float quality score (None if not yet scored)
      identity_score  — float face-match score (None if not yet scored)
      eyeball_grade   — null placeholder; operator fills in 1–5 after review

    Rows are sorted by shot_type then motion_fidelity (nulls last) so related
    shots cluster together for efficient grading.
    """
    project = load_project(project_id)
    if project is None:
        print(
            f"error: project {project_id!r} not found — check the project ID and "
            "that the data directory is accessible.",
            file=sys.stderr,
        )
        sys.exit(1)

    rows: list[dict] = []
    for scene in project.get("scenes", []):
        for shot in scene.get("shots", []):
            mt = shot.get("motion_takes", [])
            if not mt:
                continue
            latest = mt[-1]
            meta = latest.get("metadata", {})
            rows.append(
                {
                    "shot_id": shot["id"],
                    "shot_type": classify_shot_type(shot),
                    "engine": meta.get("target_api", "?"),
                    "motion_fidelity": meta.get("motion_fidelity"),
                    "identity_score": meta.get("identity_score"),
                    "eyeball_grade": None,  # operator fills in 1–5
                }
            )

    # Sort: shot_type alphabetically, then motion_fidelity ascending (nulls last)
    rows.sort(
        key=lambda r: (
            r["shot_type"],
            r["motion_fidelity"] if r["motion_fidelity"] is not None else float("inf"),
        )
    )
    return rows


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/calibrate_motion_floor.py <project_id>",
            file=sys.stderr,
        )
        sys.exit(1)

    print(json.dumps(dump_metrics(sys.argv[1]), indent=2))

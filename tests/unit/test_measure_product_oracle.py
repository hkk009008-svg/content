import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.measure_product_oracle import (
    _sample_times,
    best_offset_frames,
    build_artifact,
)


def test_sample_times_are_inside_clip():
    assert _sample_times(4.0, 4) == [0.5, 1.5, 2.5, 3.5]


def test_best_offset_positive_means_mouth_lags_audio():
    audio = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    mouth = [0, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]

    result = best_offset_frames(mouth, audio, max_lag_frames=4)

    assert result["offset_frames"] == 2.0
    assert result["correlation"] == pytest.approx(1.0)


def test_build_artifact_has_wave_gate_contract(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    reference = tmp_path / "ref.jpg"
    video.write_bytes(b"video")
    reference.write_bytes(b"reference")

    artifact = build_artifact(
        wave=2,
        video_path=video,
        reference_image=reference,
        video_meta={"fps": 25.0, "frame_count": 10, "duration_seconds": 0.4},
        arcface={"arc_score": 0.7},
        lipsync={"offset_frames": -1.0},
        command="python scripts/measure_product_oracle.py ...",
    )

    assert artifact["artifact_kind"] == "product-oracle"
    assert artifact["wave"] == 2
    assert math.isfinite(artifact["arcface"]["arc_score"])
    assert math.isfinite(artifact["lipsync"]["offset_frames"])
    assert artifact["instrument"] == "scripts/measure_product_oracle.py"
    assert artifact["inputs"]["video"]["sha256"]
    assert artifact["inputs"]["reference_image"]["sha256"]


def test_script_path_execution_bootstraps_repo_root_for_identity_import():
    root = Path(__file__).resolve().parent.parent.parent
    code = r"""
import runpy
import sys
from pathlib import Path

root = Path.cwd()
script = root / "scripts" / "measure_product_oracle.py"
sys.path = [str(script.parent)] + [
    path for path in sys.path
    if path not in ("", str(root), str(root.resolve()))
]
namespace = runpy.run_path(str(script), run_name="__product_oracle_test__")
try:
    namespace["measure_arcface"](
        root / "missing-product-oracle.mp4",
        root / "logs" / "ref_lighting.jpg",
        sample_count=1,
    )
except ModuleNotFoundError as exc:
    print(f"IMPORT_FAILED: {exc}")
    raise
except RuntimeError as exc:
    print(f"IMPORT_OK: {exc}")
"""
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT_OK:" in result.stdout

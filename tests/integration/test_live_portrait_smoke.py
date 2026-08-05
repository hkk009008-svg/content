"""Windows LivePortrait performance-capture smoke.

Calls the dedicated Windows worker through the Mac's authenticated loopback
tunnel with a hash-verified fictional-adult keyframe and a two-second facial-
expression driving video. Gated behind an explicit
`windows-liveportrait-performance` selection and the exact role-bound worker
readiness contract.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
from pathlib import Path
import subprocess
import tempfile

import pytest

from config.settings import settings


SELECTED = (
    os.environ.get("LIVE_CONTRACT_CANARY_TARGET", "")
    == "windows-liveportrait-performance"
)
HAS_COMFYUI = bool(
    getattr(settings, "performance_comfyui_server_url", "")
    and getattr(settings, "performance_comfyui_api_key", "")
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_SHEET = (
    _REPOSITORY_ROOT
    / "tests"
    / "assets"
    / "live_contract"
    / "runway_act_two_synthetic_performer.jpg"
)
_FIXTURE_SHEET_SHA256 = (
    "97471b9377c817251c86dbb58982464d7586b6b3d800936683f900da668c0fb6"
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not SELECTED or not HAS_COMFYUI,
        reason="Windows LivePortrait worker was not selected or configured",
    ),
]


def _load_verified_expression_panels():
    """Load four detected-face expressions and reject fixture byte drift."""
    from PIL import Image

    payload = _FIXTURE_SHEET.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha256, _FIXTURE_SHEET_SHA256):
        raise RuntimeError(
            f"LivePortrait fixture hash mismatch: expected {_FIXTURE_SHEET_SHA256}, "
            f"received {actual_sha256}"
        )
    with Image.open(io.BytesIO(payload)) as opened:
        sheet = opened.convert("RGB")
    width, height = sheet.size
    if width != height or width % 2:
        raise RuntimeError("LivePortrait expression sheet must be an even square")
    half = width // 2
    return [
        sheet.crop((0, 0, half, half)),
        sheet.crop((half, 0, width, half)),
        sheet.crop((0, half, half, height)),
        sheet.crop((half, half, width, height)),
    ]


def _make_test_keyframe(path: str) -> None:
    _load_verified_expression_panels()[0].save(path, "JPEG", quality=92)


def _make_test_driving_video(path: str, frames: int = 50, fps: int = 25) -> None:
    """Cross-blend real facial expressions into a deterministic driving clip."""
    from PIL import Image

    panels = _load_verified_expression_panels()
    sequence = [0, 1, 2, 3, 2, 1, 0]
    frames_dir = Path(path).with_suffix("").with_name("liveportrait-frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame_index in range(frames):
        progress = frame_index * (len(sequence) - 1) / (frames - 1)
        segment = min(int(progress), len(sequence) - 2)
        frame = Image.blend(
            panels[sequence[segment]],
            panels[sequence[segment + 1]],
            progress - segment,
        )
        frame.save(frames_dir / f"{frame_index:03d}.jpg", "JPEG", quality=90)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-i", str(frames_dir / "%03d.jpg"),
            "-frames:v", str(frames), "-an",
            # The hash-pinned expression sheet is 1254 px square, so each
            # source panel is 627x627. H.264 yuv420p requires even geometry;
            # pad one deterministic edge pixel instead of mutating the
            # verified source fixture or depending on encoder tolerance.
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-preset", "fast",
            "-movflags", "+faststart", path,
        ],
        check=True, capture_output=True, timeout=30,
    )


def test_live_portrait_windows_round_trip():
    """The exact Windows worker accepts the graph and returns a valid video."""
    from performance.live_portrait import generate_live_portrait_performance

    # Confirm ffmpeg is available — otherwise we can't make the driving video.
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.fail("ffmpeg not on PATH; Windows canary cannot create its fixture")

    with tempfile.TemporaryDirectory() as td:
        kf = os.path.join(td, "kf.jpg")
        driving = os.path.join(td, "driving.mp4")
        out = os.path.join(td, "out.mp4")
        _make_test_keyframe(kf)
        _make_test_driving_video(driving)

        result = generate_live_portrait_performance(
            keyframe_path=kf,
            driving_video_path=driving,
            output_mp4=out,
            duration_s=2.0,
            poll_timeout_s=120,  # tighter for smoke
        )
        if result is None:
            pytest.fail("configured Windows LivePortrait worker returned no result")
        assert result == out
        assert os.path.exists(out)
        assert os.path.getsize(out) > 1024

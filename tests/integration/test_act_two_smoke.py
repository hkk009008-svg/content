"""Act-Two performance-capture smoke test (handoff §13; migrated from Act-One
2026-07-30, slice 5b — see performance/act_two.py's module docstring for the
audited SDK contract).

Runs ONE real Runway Act-Two call with a recognizable character image and a
short synthetic performance video, then asserts a non-empty mp4 comes back.
Both inputs are derived from one repository-tracked, hash-verified expression
sheet of an entirely fictional adult. Gated behind
an explicit `runway-act-two` selection and RUNWAYML_API_SECRET, so ordinary CI
and ambient developer credentials cannot trigger spend.

Marked `@pytest.mark.e2e` to match the existing tests/integration/* gating.
Tag with `-m e2e` to run; `-m "not e2e"` skips.

NOTE: unlike the retired Act-One, Act-Two has no audio-only generation mode
— every call needs a real reference performance video (3-30s), so this test
constructs one at the minimum three-second duration instead of driving off
audio alone. A color test pattern is not a valid Act-Two performer.
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
from cost_tracker import CostTracker


SELECTED = os.environ.get("LIVE_CONTRACT_CANARY_TARGET", "") == "runway-act-two"
_RUNWAY_SECRET = getattr(settings, "runwayml_api_secret", "")
HAS_RUNWAY = bool(_RUNWAY_SECRET and "placeholder" not in _RUNWAY_SECRET.lower())

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
        not SELECTED or not HAS_RUNWAY,
        reason="Runway Act-Two was not selected or configured",
    ),
]


def _load_verified_expression_panels():
    """Load four synthetic expressions and reject any fixture byte drift."""
    from PIL import Image

    payload = _FIXTURE_SHEET.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_sha256, _FIXTURE_SHEET_SHA256):
        raise RuntimeError(
            f"Act-Two fixture hash mismatch: expected {_FIXTURE_SHEET_SHA256}, "
            f"received {actual_sha256}"
        )
    with Image.open(io.BytesIO(payload)) as opened:
        sheet = opened.convert("RGB")
    width, height = sheet.size
    if width != height or width % 2:
        raise RuntimeError("Act-Two expression sheet must be an even square")
    half = width // 2
    panel_size = half - (half % 2)
    return [
        sheet.crop((0, 0, panel_size, panel_size)),
        sheet.crop((width - panel_size, 0, width, panel_size)),
        sheet.crop((0, height - panel_size, panel_size, height)),
        sheet.crop((width - panel_size, height - panel_size, width, height)),
    ]


def _make_test_keyframe(path: str) -> None:
    """Create a recognizable character portrait from the neutral panel."""
    _load_verified_expression_panels()[0].save(path, "JPEG", quality=92)


def _make_test_reference_video(
    path: str,
    duration_s: float = 3.0,
    fps: int = 25,
) -> None:
    """Blend synthetic expressions into one continuous, cut-free performance."""
    from PIL import Image

    panels = _load_verified_expression_panels()
    sequence = [0, 1, 2, 3, 2, 1, 0]
    frame_count = int(round(duration_s * fps))
    if frame_count < 2:
        raise ValueError("Act-Two reference video needs at least two frames")
    frames_dir = Path(path).with_suffix("").with_name("reference-frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame_index in range(frame_count):
        progress = frame_index * (len(sequence) - 1) / (frame_count - 1)
        segment = min(int(progress), len(sequence) - 2)
        alpha = progress - segment
        frame = Image.blend(
            panels[sequence[segment]],
            panels[sequence[segment + 1]],
            alpha,
        )
        frame.save(frames_dir / f"{frame_index:03d}.jpg", "JPEG", quality=90)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-i", str(frames_dir / "%03d.jpg"),
            "-frames:v", str(frame_count), "-an", "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast", "-movflags", "+faststart", path,
        ],
        check=True, capture_output=True, timeout=30,
    )


def test_act_two_minimal_call_returns_mp4():
    """Smoke: actually call Runway Act-Two and assert we got a video back."""
    from performance.act_two import generate_act_two_performance
    from scripts.live_contract_canary import (
        checkpoint_runway_task,
        claim_runway_submission,
    )

    if len(os.environ.get("CANARY_AUTHORITY_GITHUB_TOKEN", "")) < 16:
        pytest.fail("durable Runway task-checkpoint authority is unavailable")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        pytest.fail("live Runway submission authority is restricted to main")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.fail("ffmpeg not on PATH; selected Act-Two canary cannot create its fixture")

    with tempfile.TemporaryDirectory() as td:
        fixture_dir = Path(
            os.environ.get("LIVE_CONTRACT_CANARY_FIXTURE_DIR", td)
        ).resolve()
        fixture_dir.mkdir(parents=True, exist_ok=True)
        kf = str(fixture_dir / "kf.jpg")
        reference = str(fixture_dir / "reference.mp4")
        out = os.path.join(td, "out.mp4")
        ledger_path = os.environ.get(
            "LIVE_CONTRACT_CANARY_LEDGER_PATH",
            os.path.join(td, "runway-act-two.sqlite3"),
        )
        os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
        _make_test_keyframe(kf)
        _make_test_reference_video(reference, duration_s=3.0)

        with CostTracker(
            db_path=ledger_path,
            budget_usd=float(os.environ["LIVE_CONTRACT_CANARY_MAX_COST_USD"]),
        ) as tracker:
            result = generate_act_two_performance(
                keyframe_path=kf,
                audio_path="",
                output_mp4=out,
                driving_video_path=reference,
                duration_s=3.0,
                shot_id="runway-act-two-fixture-v1",
                video_id="live-contract-canary",
                cost_tracker=tracker,
                task_submission_callback=(
                    lambda: claim_runway_submission(os.environ)
                ),
                task_acceptance_callback=(
                    lambda task_id: checkpoint_runway_task(os.environ, task_id)
                ),
            )
            attempt = tracker.get_latest_paid_attempt(
                video_id="live-contract-canary",
                shot_id="runway-act-two-fixture-v1",
                engine="ACT_ONE",
                operation="performance_capture",
            )
        if result is None:
            evidence = {
                key: (attempt or {}).get(key)
                for key in (
                    "state",
                    "provider_job_id",
                    "provider_status",
                    "failure_code",
                    "billed",
                )
            }
            pytest.fail(
                f"configured Runway Act-Two returned no result; attempt={evidence}"
            )
        assert result == out, f"Expected {out}, got {result}"
        assert os.path.exists(out), f"Output file missing: {out}"
        assert os.path.getsize(out) > 1024, f"Output suspiciously small: {os.path.getsize(out)} bytes"

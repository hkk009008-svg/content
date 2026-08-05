"""Deterministic, bounded driving-video preparation for performance providers.

Every provider receives the same physically bounded MP4.  A duration argument
alone is insufficient because Act-Two and Viggle derive their output length
from the uploaded reference and do not expose a duration field.
"""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import tempfile
from pathlib import Path

from performance._net import validate_video_artifact


DRIVING_CLIP_FPS = 25
_ENCODE_CONTRACT = "h264-yuv420p-25fps-v1"


class DrivingClipError(RuntimeError):
    """Raised before provider access when a bounded input cannot be proven."""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_bounded_driving_clip(
    source_path: str,
    *,
    project_root: str,
    duration_s: float,
) -> str:
    """Return a project-owned MP4 containing at most the first requested frames.

    The cache key binds source bytes, frame count, and the encode contract.  The
    resulting bytes are retained so artifact provenance and paid-attempt
    fingerprints remain stable across retries and project relocation.
    """

    source_was_symlink = os.path.islink(source_path)
    source = os.path.realpath(source_path)
    root = os.path.realpath(project_root)
    try:
        inside_project = (
            os.path.commonpath([root, source]) == root and source != root
        )
    except ValueError:
        inside_project = False
    if not inside_project or not os.path.isfile(source) or source_was_symlink:
        raise DrivingClipError(
            "Driving video must be a regular, non-symlink file inside the project"
        )

    try:
        requested_duration = float(duration_s)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DrivingClipError("Driving-video duration is invalid") from exc
    if not math.isfinite(requested_duration) or requested_duration <= 0:
        raise DrivingClipError("Driving-video duration must be finite and positive")

    frame_count = max(1, int(math.floor(requested_duration * DRIVING_CLIP_FPS + 1e-9)))
    bounded_duration_s = frame_count / DRIVING_CLIP_FPS
    source_digest = _sha256(source)
    cache_key = hashlib.sha256(
        f"{source_digest}:{frame_count}:{_ENCODE_CONTRACT}".encode("ascii")
    ).hexdigest()
    output_dir = os.path.join(root, "performance_inputs", "bounded")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"driving-{cache_key}.mp4")

    if os.path.exists(output_path):
        validation_error = validate_video_artifact(
            output_path,
            max_duration_s=bounded_duration_s + (1.0 / DRIVING_CLIP_FPS),
        )
        if validation_error is None:
            return output_path
        raise DrivingClipError(
            f"Cached bounded driving video is invalid: {validation_error}"
        )

    fd, staged_path = tempfile.mkstemp(
        prefix=".bounded-driving-",
        suffix=".mp4",
        dir=output_dir,
    )
    os.close(fd)
    try:
        command = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            source,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={DRIVING_CLIP_FPS}",
            "-frames:v",
            str(frame_count),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            staged_path,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DrivingClipError(f"ffmpeg could not bound the driving video: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "ffmpeg failed").strip()[:400]
            raise DrivingClipError(f"ffmpeg could not bound the driving video: {detail}")

        validation_error = validate_video_artifact(
            staged_path,
            max_duration_s=bounded_duration_s + (1.0 / DRIVING_CLIP_FPS),
        )
        if validation_error is not None:
            raise DrivingClipError(
                f"Bounded driving video failed validation: {validation_error}"
            )
        with open(staged_path, "rb") as staged:
            os.fsync(staged.fileno())
        os.replace(staged_path, output_path)
        directory_fd = os.open(output_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return output_path
    finally:
        try:
            Path(staged_path).unlink()
        except FileNotFoundError:
            pass

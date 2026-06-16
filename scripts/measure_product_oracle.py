#!/usr/bin/env python3
"""Measure a Wave product-oracle artifact from a local product clip.

The artifact is intentionally small JSON under logs/product-oracle-*.json so
the wave gate can verify it from HEAD. Source media can remain local scratch;
the JSON records input hashes and the exact command for R-MEASURE provenance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"{label} not found: {_repo_rel(path)}")
    if not path.is_file():
        raise SystemExit(f"{label} is not a file: {_repo_rel(path)}")


def _run(args: list[str], *, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=_REPO_ROOT,
        env={k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"},
        text=not binary,
        capture_output=True,
        check=False,
    )


def _video_meta(video_path: Path) -> dict:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("opencv-python is required for video probing") from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {_repo_rel(video_path)}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if fps <= 0.0 or frame_count <= 0:
        raise RuntimeError(f"could not read fps/frame_count: {_repo_rel(video_path)}")
    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": frame_count / fps,
        "width": width,
        "height": height,
    }


def _sample_times(duration_seconds: float, sample_count: int) -> list[float]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    step = duration_seconds / sample_count
    return [min(duration_seconds - 0.05, max(0.0, (i + 0.5) * step)) for i in range(sample_count)]


def _extract_frame(video_path: Path, time_seconds: float, out_path: Path) -> None:
    proc = _run([
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-ss",
        f"{time_seconds:.6f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(out_path),
    ])
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg frame extract failed at {time_seconds:.3f}s: "
            f"{(proc.stderr or proc.stdout).strip()}"
        )


def measure_arcface(video_path: Path, reference_image: Path, *, sample_count: int) -> dict:
    from identity.validator import IdentityValidator

    meta = _video_meta(video_path)
    validator = IdentityValidator()
    samples: list[dict] = []
    scores: list[float] = []
    with tempfile.TemporaryDirectory(prefix="product-oracle-frames-") as tmp:
        tmp_path = Path(tmp)
        for index, time_seconds in enumerate(_sample_times(meta["duration_seconds"], sample_count)):
            frame_path = tmp_path / f"frame_{index:03d}.jpg"
            _extract_frame(video_path, time_seconds, frame_path)
            result = validator.validate_image(
                str(frame_path),
                str(reference_image),
                threshold=0.0,
                shot_type="medium",
            )
            score = result.overall_score
            sample = {
                "index": index,
                "time_seconds": round(time_seconds, 6),
                "score": score,
                "passed": bool(result.passed),
                "skipped": bool(result.skipped),
            }
            samples.append(sample)
            if isinstance(score, (int, float)) and math.isfinite(float(score)):
                scores.append(float(score))
    if not scores:
        raise RuntimeError("ArcFace produced no finite sample scores")
    return {
        "arc_score": sum(scores) / len(scores),
        "aggregation": "mean_finite_sample_scores",
        "threshold": 0.0,
        "sample_count": len(scores),
        "requested_sample_count": sample_count,
        "min_score": min(scores),
        "max_score": max(scores),
        "samples": samples,
    }


def _audio_energy_by_frame(video_path: Path, *, fps: float, frame_count: int, sample_rate: int) -> list[float]:
    proc = _run([
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-",
    ], binary=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio decode failed: {(proc.stderr or proc.stdout).strip()}")

    import numpy as np

    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError("decoded audio stream is empty")
    energy: list[float] = []
    for frame_idx in range(frame_count):
        start = int(frame_idx / fps * sample_rate)
        stop = int((frame_idx + 1) / fps * sample_rate)
        segment = audio[start:stop]
        if segment.size == 0:
            energy.append(0.0)
        else:
            energy.append(float(np.sqrt(np.mean(segment * segment))))
    return energy


def _mouth_motion_by_frame(video_path: Path) -> tuple[list[float], float]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("opencv-python and numpy are required for lip-sync measurement") from exc

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {_repo_rel(video_path)}")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    last_face: tuple[int, int, int, int] | None = None
    previous_roi = None
    detected = 0
    motion: list[float] = []

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        boxes = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(80, 80),
        )
        if len(boxes):
            x, y, w, h = max(boxes, key=lambda b: int(b[2]) * int(b[3]))
            last_face = (int(x), int(y), int(w), int(h))
            detected += 1
        elif last_face is not None:
            x, y, w, h = last_face
        else:
            height, width = gray.shape
            x, y, w, h = (
                int(width * 0.32),
                int(height * 0.15),
                int(width * 0.36),
                int(height * 0.65),
            )

        y0 = y + int(h * 0.55)
        y1 = min(y + h, gray.shape[0])
        x0 = x + int(w * 0.18)
        x1 = min(x + int(w * 0.82), gray.shape[1])
        if y1 <= y0 or x1 <= x0:
            motion.append(0.0)
            continue
        roi = cv2.resize(gray[y0:y1, x0:x1], (64, 32))
        if previous_roi is None:
            motion.append(0.0)
        else:
            motion.append(float(np.mean(np.abs(roi.astype(np.float32) - previous_roi.astype(np.float32)))))
        previous_roi = roi

    cap.release()
    if len(motion) < 8:
        raise RuntimeError("too few video frames for lip-sync measurement")
    denominator = frame_count if frame_count > 0 else len(motion)
    return motion, detected / max(denominator, 1)


def best_offset_frames(
    mouth_motion: Iterable[float],
    audio_energy: Iterable[float],
    *,
    max_lag_frames: int,
) -> dict:
    """Return the lag with highest correlation.

    Positive offset means mouth motion lags audio by that many video frames.
    Negative offset means mouth motion leads audio.
    """
    import numpy as np

    mouth = np.asarray(list(mouth_motion), dtype=float)[1:]
    audio = np.asarray(list(audio_energy), dtype=float)[1:]
    n = min(mouth.size, audio.size)
    mouth = mouth[:n]
    audio = audio[:n]
    if n < 8:
        raise RuntimeError("too few paired mouth/audio samples")

    best: tuple[float, int, int] | None = None
    lag_table: list[dict] = []
    for lag in range(-max_lag_frames, max_lag_frames + 1):
        if lag > 0:
            m = mouth[lag:]
            a = audio[:-lag]
        elif lag < 0:
            m = mouth[:lag]
            a = audio[-lag:]
        else:
            m = mouth
            a = audio
        if m.size < 8 or a.size < 8 or float(m.std()) < 1e-9 or float(a.std()) < 1e-9:
            continue
        corr = float(np.corrcoef(m, a)[0, 1])
        if not math.isfinite(corr):
            continue
        lag_table.append({"lag_frames": lag, "correlation": corr, "paired_samples": int(m.size)})
        if best is None or corr > best[0]:
            best = (corr, lag, int(m.size))

    if best is None:
        raise RuntimeError("no finite mouth/audio correlation was measurable")
    best_corr, best_lag, paired_samples = best
    top_lags = sorted(lag_table, key=lambda row: row["correlation"], reverse=True)[:5]
    return {
        "offset_frames": float(best_lag),
        "correlation": best_corr,
        "paired_samples": paired_samples,
        "top_lags": top_lags,
    }


def measure_lipsync(video_path: Path, *, max_lag_frames: int, sample_rate: int) -> dict:
    meta = _video_meta(video_path)
    mouth_motion, face_detect_rate = _mouth_motion_by_frame(video_path)
    audio_energy = _audio_energy_by_frame(
        video_path,
        fps=meta["fps"],
        frame_count=len(mouth_motion),
        sample_rate=sample_rate,
    )
    offset = best_offset_frames(
        mouth_motion,
        audio_energy,
        max_lag_frames=max_lag_frames,
    )
    offset["offset_seconds"] = offset["offset_frames"] / meta["fps"]
    offset.update({
        "fps": meta["fps"],
        "max_lag_frames": max_lag_frames,
        "sample_rate_hz": sample_rate,
        "mouth_signal": "lower_face_frame_difference",
        "audio_signal": "per_video_frame_rms",
        "face_detect_rate": face_detect_rate,
        "sign_convention": "positive offset_frames means mouth motion lags audio",
    })
    return offset


def build_artifact(
    *,
    wave: int,
    video_path: Path,
    reference_image: Path,
    video_meta: dict,
    arcface: dict,
    lipsync: dict,
    command: str,
) -> dict:
    return {
        "artifact_kind": "product-oracle",
        "wave": wave,
        "created_at_utc": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "instrument": "scripts/measure_product_oracle.py",
        "command": command,
        "inputs": {
            "video": {
                "path": _repo_rel(video_path),
                "sha256": _sha256_file(video_path),
                **video_meta,
            },
            "reference_image": {
                "path": _repo_rel(reference_image),
                "sha256": _sha256_file(reference_image),
            },
        },
        "arcface": arcface,
        "lipsync": lipsync,
        "notes": [
            "Source media are local runtime artifacts; this committed JSON preserves input hashes and measured values.",
            "ArcFace uses IdentityValidator.validate_image on sampled frames with threshold=0.0.",
            "Lip-sync offset is a deterministic mouth-motion/audio-energy cross-correlation, not a SyncNet confidence score.",
        ],
    }


def _rounded_artifact(data: dict) -> dict:
    def convert(value):
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    return convert(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", type=int, default=2)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--arcface-samples", type=int, default=8)
    parser.add_argument("--max-lag-frames", type=int, default=12)
    parser.add_argument("--audio-sample-rate", type=int, default=16000)
    args = parser.parse_args(argv)

    video_path = (_REPO_ROOT / args.video).resolve() if not args.video.is_absolute() else args.video
    reference_image = (
        (_REPO_ROOT / args.reference_image).resolve()
        if not args.reference_image.is_absolute()
        else args.reference_image
    )
    output = args.output or (_REPO_ROOT / "logs" / f"product-oracle-wave{args.wave}.json")
    output = (_REPO_ROOT / output).resolve() if not output.is_absolute() else output

    _ensure_file(video_path, "video")
    _ensure_file(reference_image, "reference image")
    output.parent.mkdir(parents=True, exist_ok=True)

    command = shlex.join([sys.executable, *sys.argv])
    video_meta = _video_meta(video_path)
    arcface = measure_arcface(video_path, reference_image, sample_count=args.arcface_samples)
    lipsync = measure_lipsync(
        video_path,
        max_lag_frames=args.max_lag_frames,
        sample_rate=args.audio_sample_rate,
    )
    artifact = build_artifact(
        wave=args.wave,
        video_path=video_path,
        reference_image=reference_image,
        video_meta=video_meta,
        arcface=arcface,
        lipsync=lipsync,
        command=command,
    )
    output.write_text(json.dumps(_rounded_artifact(artifact), indent=2, sort_keys=True) + "\n")
    print(f"wrote {_repo_rel(output)}")
    print(
        "arcface.arc_score={:.6f} lipsync.offset_frames={:.3f} "
        "lipsync.correlation={:.6f}".format(
            artifact["arcface"]["arc_score"],
            artifact["lipsync"]["offset_frames"],
            artifact["lipsync"]["correlation"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

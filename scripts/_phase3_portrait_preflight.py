#!/usr/bin/env python3
"""Phase-3 portrait 9:16 per-provider preflight.

⚠️  LIVE SPEND — this script makes REAL, PAID API calls to Veo, Sora, Kling,
Runway, and FAL.  Each call costs ~$0.30–$0.80.  Total expected spend: ~$2–4
(4 video providers — Veo, Sora, Kling, Runway — + 1 FAL image smoke = 5 checks).
The context pins cascade_retry_limit=0
so each provider is billed EXACTLY ONCE — without it, a failing provider would
double-bill (a second call after a 30s quota-cooldown sleep), making a worst-case
all-fail run cost up to ~2× and stall ~30s per failure.

DO NOT RUN unless you have authorised the spend and all provider API keys are
set in your environment.  This is a USER-RUN gate, not a CI check.

Usage:
    # Preferred — use the bundled portrait keyframe:
    python scripts/_phase3_portrait_preflight.py

    # Custom keyframe (must be portrait, i.e. height > width):
    python scripts/_phase3_portrait_preflight.py --keyframe /path/to/portrait.jpg

    # Custom output directory (default: system tmp):
    python scripts/_phase3_portrait_preflight.py --out-dir /tmp/preflight

Purpose:
    Exercises the T3–T7 aspect wiring + post-gen backstop end-to-end.
    Each provider is pinned via video_fallbacks=[PROVIDER] so the cascade
    cannot silently succeed on a different engine.  After all video providers,
    a FAL FLUX-schnell image smoke (SPEC-3) verifies image-aspect plumbing.

    PASS criterion: out is not None AND ffprobe reports height > width.
    The post-gen backstop rejects wrong-orientation clips → those exhaust to
    out=None → that provider FAILS the preflight (correct behaviour).

Exit:
    sys.exit(0)  — all providers PASS
    sys.exit(N)  — N providers failed (see FAIL rows in the table)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

# ── repo root on sys.path ──────────────────────────────────────────────────────
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

# ── production imports ─────────────────────────────────────────────────────────
from cinema.aspect import fal_image_size                       # noqa: E402
from cinema.context import PipelineContext                      # noqa: E402
from phase_c_ffmpeg import generate_ai_video                   # noqa: E402

# ── defaults ───────────────────────────────────────────────────────────────────
# A bundled portrait character image (880×1184) known to exist in this repo.
_DEFAULT_KEYFRAME = os.path.join(
    _REPO,
    "domain/projects/c4507d802f38/characters/char_dca864303d9b/canonical.jpg",
)

# Providers shipped by Phase-3 (T3–T6).  LTX and SEEDANCE are out of scope.
_PROVIDERS = [
    "VEO_NATIVE",
    "SORA_NATIVE",
    "KLING_NATIVE",
    "RUNWAY_GEN4",
]

# ── helpers ────────────────────────────────────────────────────────────────────

def ffprobe_streams(path: str) -> dict:
    """Return parsed ffprobe JSON for *path*, or {} on any error."""
    if not path or not os.path.exists(path):
        return {}
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,sample_rate,channels,duration"
                ":format=duration",
                "-of", "json",
                path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(r.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"ffprobe_error": str(exc)[:200]}


def _video_dims(probe: dict) -> tuple[int | None, int | None]:
    """Return (width, height) of the first video stream, or (None, None)."""
    for s in probe.get("streams", []):
        if s.get("codec_type") == "video":
            return s.get("width"), s.get("height")
    return None, None


def _make_ctx(aspect: str = "9:16") -> PipelineContext:
    # cascade_retry_limit=0 (PF-1): each provider is pinned via video_fallbacks=[PROVIDER],
    # so a FAILING provider would otherwise re-enter the quota-cooldown retry pass —
    # time.sleep(30) + a SECOND billed call to the same provider — doubling spend exactly
    # in the all-fail case this preflight exists to surface. Pinning the retry limit to 0
    # bounds each provider to a single billed call (mirrors test_phase_c_video_aspect.py:711).
    return PipelineContext(global_settings={"aspect_ratio": aspect, "cascade_retry_limit": 0})


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase-3 portrait 9:16 per-provider preflight (LIVE SPEND).",
    )
    parser.add_argument(
        "keyframe",
        nargs="?",
        default=_DEFAULT_KEYFRAME,
        help=(
            "Path to a portrait (height > width) keyframe image.  "
            f"Default: {_DEFAULT_KEYFRAME}"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for generated clips (default: system tmp, auto-cleaned).",
    )
    args = parser.parse_args()

    keyframe: str = args.keyframe
    out_dir: str | None = args.out_dir

    # ── sanity checks ──────────────────────────────────────────────────────────
    if not os.path.exists(keyframe):
        print(f"ABORT: keyframe not found: {keyframe}")
        print("  Pass a valid portrait image as the first argument.")
        return 1

    probe_kf = ffprobe_streams(keyframe)
    kf_w, kf_h = _video_dims(probe_kf)
    if kf_w is None or kf_h is None:
        # ffprobe doesn't parse static images via the video stream; try the
        # generic streams list (some images report w/h as image2 streams).
        for s in probe_kf.get("streams", []):
            if "width" in s and "height" in s:
                kf_w, kf_h = s["width"], s["height"]
                break
    if kf_w is not None and kf_h is not None and kf_h <= kf_w:
        print(
            f"ABORT: keyframe is NOT portrait ({kf_w}x{kf_h}; need height > width).\n"
            "  Pass a 9:16-ratio (portrait) image."
        )
        return 1

    print("=" * 72)
    print("PHASE-3 PORTRAIT PREFLIGHT  —  9:16 per-provider smoke  (LIVE SPEND)")
    print("=" * 72)
    print(f"keyframe : {keyframe}")
    print(f"out_dir  : {out_dir or '(system tmp)'}")
    print()

    # ── per-provider video tests ───────────────────────────────────────────────
    ctx = _make_ctx("9:16")
    problems: list[str] = []
    results: list[dict] = []

    use_tmp = out_dir is None
    tmp_dir_obj = tempfile.TemporaryDirectory(prefix="phase3_preflight_") if use_tmp else None
    work_dir = tmp_dir_obj.name if tmp_dir_obj else out_dir

    print(f"{'PROVIDER':<16}  {'RESULT':<8}  {'DIMS':<14}  NOTE")
    print("-" * 72)

    for provider in _PROVIDERS:
        out_path = os.path.join(work_dir, f"preflight_{provider.lower()}.mp4")
        note = ""
        try:
            out = generate_ai_video(
                image_path=keyframe,
                camera_motion="zoom_in_slow",
                target_api=provider,
                output_mp4=out_path,
                shot_type="portrait",
                ctx=ctx,
                # Pin to exactly this provider.  If the backstop rejects a
                # wrong-orientation clip the cascade exhausts to None → FAIL.
                video_fallbacks=[provider],
            )
        except Exception as exc:  # noqa: BLE001
            out = None
            note = f"exception: {exc!r}"[:80]

        probe = ffprobe_streams(out) if out else {}
        w, h = _video_dims(probe)

        if out and os.path.exists(out) and h is not None and w is not None and h > w:
            verdict = "PASS"
            dims = f"{w}x{h}"
        else:
            verdict = "FAIL"
            if out and os.path.exists(out) and w is not None and h is not None:
                dims = f"{w}x{h}"
                note = note or "wrong orientation (landscape/square)"
            elif out and os.path.exists(out):
                dims = "?x?"
                note = note or "ffprobe could not read dims"
            elif out is None and not note:
                dims = "—"
                note = "generate_ai_video returned None (backstop rejected or API error)"
            else:
                dims = "—"
            problems.append(f"{provider}: {note or 'FAIL (unknown reason)'}")

        print(f"{provider:<16}  {verdict:<8}  {dims:<14}  {note}")
        results.append({"provider": provider, "verdict": verdict, "dims": f"{w}x{h}" if w else "—", "note": note})

    # ── SPEC-3: FAL FLUX-schnell image portrait smoke ─────────────────────────
    # The production schnell path is inside `phase_c_assembly._fal_flux_fallback`
    # (a private function with no stable callable entry point for external use).
    # The SPEC-3 smoke is therefore implemented here by calling fal_client
    # directly — the same fal-ai/flux/schnell endpoint, same image_size
    # argument via fal_image_size("9:16") — mirroring the production call at
    # phase_c_assembly.py:572-580.
    #
    # Verification: the produced image file is ffprobe-checked for height > width.
    #
    print()
    print("SPEC-3: FAL FLUX-schnell image portrait smoke")
    print("-" * 72)

    schnell_size = fal_image_size("9:16")   # → "portrait_16_9"
    print(f"fal_image_size('9:16') = {schnell_size!r}")

    try:
        import fal_client  # type: ignore  # noqa: F401
        _fal_available = True
    except ImportError:
        _fal_available = False

    if not _fal_available:
        note_s = "fal_client not installed — cannot run schnell smoke"
        print(f"{'FAL_SCHNELL':<16}  {'SKIP':<8}  {'—':<14}  {note_s}")
        problems.append(f"FAL_SCHNELL: {note_s}")
    else:
        import urllib.request
        schnell_out = os.path.join(work_dir, "preflight_schnell.jpg")
        try:
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                arguments={
                    "prompt": (
                        "a woman in portrait orientation, looking directly at the camera, "
                        "photorealistic, soft natural light, shallow depth of field"
                    ),
                    "image_size": schnell_size,
                    "num_inference_steps": 4,
                },
            )
            img_url = result["images"][0]["url"]
            urllib.request.urlretrieve(img_url, schnell_out)

            # Verify dimensions — static image via PIL if available, else ffprobe
            s_w: int | None = None
            s_h: int | None = None
            try:
                from PIL import Image as _PILImage  # type: ignore
                with _PILImage.open(schnell_out) as im:
                    s_w, s_h = im.size
            except Exception:  # noqa: BLE001
                probe_s = ffprobe_streams(schnell_out)
                for _s in probe_s.get("streams", []):
                    if "width" in _s and "height" in _s:
                        s_w, s_h = _s["width"], _s["height"]
                        break

            if s_w is not None and s_h is not None and s_h > s_w:
                s_verdict = "PASS"
                s_dims = f"{s_w}x{s_h}"
                s_note = ""
            else:
                s_verdict = "FAIL"
                s_dims = f"{s_w}x{s_h}" if s_w else "?x?"
                s_note = "image not portrait" if s_w else "could not read dims"
                problems.append(f"FAL_SCHNELL: {s_note}")

        except Exception as exc_s:  # noqa: BLE001
            s_verdict = "FAIL"
            s_dims = "—"
            s_note = f"exception: {exc_s!r}"[:80]
            problems.append(f"FAL_SCHNELL: {s_note}")

        print(f"{'FAL_SCHNELL':<16}  {s_verdict:<8}  {s_dims:<14}  {s_note}")

    # ── summary ────────────────────────────────────────────────────────────────
    if tmp_dir_obj:
        tmp_dir_obj.cleanup()

    print()
    print("=" * 72)
    if problems:
        print(f"PREFLIGHT FAILED — {len(problems)} problem(s):")
        for p in problems:
            print(f"  ✗ {p}")
        print()
        print("Fix the failing providers before running T10 (un-gate SUPPORTED_ASPECT_RATIOS).")
    else:
        print("PREFLIGHT: ALL GREEN — safe to proceed with T10 un-gate.")
    print("=" * 72)

    return len(problems)


if __name__ == "__main__":
    sys.exit(main())

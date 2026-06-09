#!/usr/bin/env python3
"""Max-tier FULL HARNESS — N=8 best-of keyframe (live pod) -> Veo native-audio clip.

Recreates the missing `run_veo_dialogue_max.py` by chaining the two REAL
production functions end-to-end (no bespoke ComfyUI plumbing):

  Stage 1 — quality_max.generate_ai_broll_max(...)
      N=8 adaptive best-of on the live pod. fp16 FLUX + PuLID identity
      (LoRA-less) + FaceDetailer + ReActor + SUPIR 4K. Each candidate is scored
      locally by ArcFace (identity); the best-composite keyframe is promoted.
      candidate_count=8 for every shot type (workflow_selector.MAX_QUALITY_TEMPLATES);
      aesthetic scorer is absent on this Mac so composite is ArcFace-driven and
      the run executes the full N=8 (no early halt).

  Stage 2 — veo_native.VeoNativeAPI().generate_video(image=keyframe, generate_audio=True)
      Image-to-video with SYNCED NATIVE AUDIO (Veo 3.1, Vertex backend). The
      keyframe is the start frame; identity rides the start frame (Bug #4: refs
      are mutually exclusive with image). duration 8s, 720p (the proven config).

  Stage 3 — ffprobe the output: PASS iff video file exists AND has an audio stream.

Pre-flight (scripts/_max_harness_preflight.py) must be GREEN first. Costs real
money: ~37 min GPU (N=8 SUPIR-inline) + ~$0.50-1 Veo. Run in background.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# True-max precision: re-point UNet/T5 to fp16 (the validated 4K-image path).
# Read at call-time by quality_max._apply_model_precision, so setting it here is
# in time. The pod has fp16 FLUX (23.8GB) provisioned.
os.environ.setdefault("MAX_MODEL_PRECISION", "fp16")

# Known-good clean frontal ref for the max workflow (handoff: arc 0.6-0.79; the
# fix for the "two-women" weak-canonical failure mode).
FACE_REF = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"

KEYFRAME = "logs/max_harness_keyframe.jpg"
FINAL_MP4 = "logs/max_harness_final.mp4"

# Stage-1 image: a solo photorealistic close-up talking-head — a good Veo start
# frame for a spoken-dialogue clip. "single woman, solo" guards the two-women mode.
IMG_PROMPT = (
    "Photorealistic cinematic close-up portrait of a single woman, solo, looking "
    "directly into the camera with a warm natural expression, head-and-shoulders "
    "framing, shoulder-length hair, soft natural key light, shallow depth of field, "
    "subtle film grain, 85mm lens, ultra-detailed skin texture. One person only."
)

# Stage-2 Veo motion: she speaks the line aloud -> native synced audio.
VEO_PROMPT = (
    "The woman looks directly at the camera and speaks warmly to the viewer. "
    'She clearly says aloud: "Thank you for being here. This is exactly the '
    'moment I have been working toward." Subtle natural head movement and blinking, '
    "photorealistic, soft key light, shallow depth of field. "
    "Clear synchronized speech audio."
)


def ffprobe_streams(path):
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,sample_rate,channels,duration:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(out.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ffprobe_error": str(e)[:200]}


def main():
    t0 = time.time()
    os.makedirs("logs", exist_ok=True)
    for stale in (KEYFRAME, FINAL_MP4):
        if os.path.exists(stale):
            os.remove(stale)

    print("=" * 78, flush=True)
    print("MAX-TIER FULL HARNESS  (N=8 best-of keyframe -> Veo native-audio clip)")
    print(f"  face ref:  {FACE_REF}")
    print(f"  keyframe:  {KEYFRAME}")
    print(f"  final:     {FINAL_MP4}")
    print(f"  precision: {os.environ.get('MAX_MODEL_PRECISION')}")
    print("=" * 78, flush=True)

    if not os.path.exists(FACE_REF):
        print(f"ABORT: face ref missing: {FACE_REF}")
        return 2

    # ---- Stage 1: N=8 best-of keyframe on the live pod ----
    from quality_max import generate_ai_broll_max
    print("\n[STAGE 1] generate_ai_broll_max — N=8 best-of on the pod (SUPIR inline ~4.6min/cand)...",
          flush=True)
    s1 = time.time()
    result = generate_ai_broll_max(
        prompt=IMG_PROMPT,
        output_filename=KEYFRAME,
        character_image=FACE_REF,
        # no init_image, no char_lora_path, no style_reference -> the proven
        # char + no-init, LoRA-less, PuLID-only path (node 700 pruned).
    )
    s1_min = (time.time() - s1) / 60.0
    print(f"[STAGE 1] returned: {result!r}  (elapsed {s1_min:.1f} min)", flush=True)

    if result is None or not os.path.exists(KEYFRAME):
        print("ABORT: keyframe generation failed (pod unavailable / all candidates "
              "failed). No Veo spend.")
        return 2
    kf_probe = ffprobe_streams(KEYFRAME)
    print(f"[STAGE 1] keyframe ffprobe: {json.dumps(kf_probe)}", flush=True)
    print(f"[STAGE 1] OK — keyframe at {KEYFRAME} "
          f"({os.path.getsize(KEYFRAME)/1024/1024:.1f} MB)", flush=True)

    # ---- Stage 2: Veo native-audio video from the keyframe ----
    from veo_native import VeoNativeAPI
    api = VeoNativeAPI()
    if getattr(api, "_backend", None) != "vertex":
        print(f"ABORT: Veo backend={api._backend!r} not 'vertex' — native audio "
              f"impossible. Keyframe is saved at {KEYFRAME}.")
        return 3
    print(f"\n[STAGE 2] VeoNativeAPI generate_video — vertex, model={api._model}, "
          f"8s/720p, audio=True...", flush=True)
    s2 = time.time()
    video = api.generate_video(
        image_path=KEYFRAME,
        prompt=VEO_PROMPT,
        output_path=FINAL_MP4,
        duration="8s",
        resolution="720p",
        generate_audio=True,
    )
    s2_min = (time.time() - s2) / 60.0
    print(f"[STAGE 2] returned: {video!r}  (elapsed {s2_min:.1f} min)", flush=True)

    # ---- Stage 3: verdict ----
    probe = ffprobe_streams(video)
    print(f"[STAGE 3] final ffprobe: "
          f"{json.dumps(probe, indent=2) if isinstance(probe, dict) else probe}", flush=True)
    has_audio = has_video = False
    if isinstance(probe, dict):
        for s in probe.get("streams", []):
            if s.get("codec_type") == "audio":
                has_audio = True
            if s.get("codec_type") == "video":
                has_video = True

    total_min = (time.time() - t0) / 60.0
    print("=" * 78, flush=True)
    if video and os.path.exists(video) and has_video and has_audio:
        size_mb = os.path.getsize(video) / 1024 / 1024
        print(f"VERDICT: ✅ PASS — full max-tier harness end-to-end.")
        print(f"  keyframe: {KEYFRAME}")
        print(f"  final:    {video} ({size_mb:.1f} MB, video+audio)")
        print(f"  total wall: {total_min:.1f} min")
        return 0
    if video and os.path.exists(video) and has_video and not has_audio:
        print(f"VERDICT: ⚠️ PARTIAL — video generated but NO audio stream "
              f"(generate_audio=True did not yield audio). {video}")
        return 1
    print(f"VERDICT: ❌ FAIL — Veo produced no usable output ({video!r}). "
          f"Keyframe is saved at {KEYFRAME} (Stage 1 succeeded).")
    return 4


if __name__ == "__main__":
    sys.exit(main())

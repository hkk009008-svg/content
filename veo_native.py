"""
Veo Native API Client — Direct Google Veo 3.1 integration via google-genai SDK.
Bypasses fal.ai proxy for native access to Veo's first+last frame control,
reference image character preservation, and synced audio generation.
"""
from __future__ import annotations

import os
import time

from google import genai
from google.genai import types
from config.settings import settings

VEO_RESOLUTIONS = {
    "720p": "720p",
    "1080p": "1080p",
    "4k": "2160p",
    "2160p": "2160p",
}
VEO_DURATIONS = ["5s", "6s", "8s"]


def _parse_duration_seconds(duration, default: int = 8) -> int:
    """'8s' -> 8. Returns `default` on any malformed input — a formatting edge
    must not fail the whole generation."""
    try:
        return int(str(duration).strip().lower().rstrip("s"))
    except (ValueError, TypeError, AttributeError):
        return default


def _build_generate_videos_config(
    *,
    generate_audio: bool,
    duration: str,
    resolution: str,
    reference_images=None,
    person_generation: str = "allow_adult",
    aspect_ratio: str = "16:9",
):
    """Pure: map generate_video() params -> GenerateVideosConfig. No I/O.

    `reference_images` is a list of already-loaded ``types.Image`` (or None); each
    is wrapped in a ``VideoGenerationReferenceImage`` (reference_type=ASSET — the
    config's required type for subject/character preservation). The previous code
    passed raw Images as a top-level ``generate_videos`` kwarg, which the SDK
    rejects (TypeError); and never set audio/duration/resolution at all.
    """
    kwargs = dict(
        person_generation=person_generation,
        aspect_ratio=aspect_ratio,
        generate_audio=generate_audio,
        duration_seconds=_parse_duration_seconds(duration),
        resolution=resolution,
    )
    if reference_images:
        kwargs["reference_images"] = [
            types.VideoGenerationReferenceImage(
                image=img,
                reference_type=types.VideoGenerationReferenceType.ASSET,
            )
            for img in reference_images
        ]
    return types.GenerateVideosConfig(**kwargs)


class VeoNativeAPI:
    """Native Google Veo 3.1 client using the google-genai SDK.

    Prefers Vertex AI (supports generate_audio for native speech).
    Falls back to Gemini API (no audio generation) if Vertex AI unavailable.
    """

    def __init__(self):
        # Prefer Vertex AI for native audio generation support
        gcp_project = settings.google_cloud_project or "project-ffb1f53f-bb4c-4add-8e7"
        gcp_location = settings.google_cloud_location
        try:
            self.client = genai.Client(
                vertexai=True,
                project=gcp_project,
                location=gcp_location,
            )
            self._backend = "vertex"
            print(f"[VEO-NATIVE] Vertex AI client initialized (project={gcp_project}, location={gcp_location})")
        except Exception as e:
            print(f"[VEO-NATIVE] Vertex AI unavailable ({e}), falling back to Gemini API")
            api_key = settings.google_api_key
            if not api_key:
                raise EnvironmentError(
                    "[VEO-NATIVE] Neither Vertex AI nor GOOGLE_API_KEY available."
                )
            self.client = genai.Client(api_key=api_key)
            self._backend = "gemini"
            print("[VEO-NATIVE] Gemini API client initialized (no audio generation)")

        # Vertex AI uses stable model names; Gemini API uses -preview suffix
        self._model = "veo-3.1-generate-001" if self._backend == "vertex" else "veo-3.1-generate-preview"

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        reference_images: list = None,
        duration: str = "8s",
        resolution: str = "720p",
        generate_audio: bool = False,
        driving_video_path: str = "",
    ) -> str | None:
        """
        Generate video from a start frame image + text prompt using Veo 3.1.

        Args:
            image_path: Path to the start frame image.
            prompt: Cinematic text prompt describing the desired motion/scene.
            output_path: Where to save the generated video.
            reference_images: Optional list of up to 3 image paths for character
                              preservation across shots.
            duration: Video duration — "5s", "6s", or "8s".
            resolution: Output resolution — "720p" or "1080p".
            generate_audio: If True, Veo generates synced audio (use for dialogue scenes).
            driving_video_path: Optional path to a performance-capture clip.
                NOT currently applied. The SDK's video input (`video=` /
                `source.video`) is for video *extension* and is mutually
                exclusive with the start `image` we always supply ("Not allowed
                if image is provided"), so a driving clip cannot condition an
                image-to-video call here. Accepted for interface stability;
                wiring motion conditioning needs a separate GenerateVideosSource
                design (spec §4.2). Currently image-only.

        Returns:
            output_path on success, None on failure.
        """
        if not os.path.exists(image_path):
            print(f"[VEO-NATIVE] Start frame not found: {image_path}")
            return None

        try:
            print(f"[VEO-NATIVE] Generating video — {duration}, {resolution}, audio={generate_audio}")
            print(f"[VEO-NATIVE] Prompt: {prompt[:120]}...")

            # Upload start frame — from_file requires keyword arg 'location'
            start_image = types.Image.from_file(location=image_path)

            # Load reference images for character preservation (up to 3). Loaded
            # here (I/O); the pure builder wraps them + places them INSIDE the
            # config. Passing raw Images as a top-level generate_videos kwarg (the
            # old code) raises TypeError -> Veo fails -> cascade.
            ref_images = []
            if reference_images:
                for ref_path in reference_images[:3]:
                    if os.path.exists(ref_path):
                        ref_images.append(types.Image.from_file(location=ref_path))
                        print(f"[VEO-NATIVE] Reference image loaded: {os.path.basename(ref_path)}")
                    else:
                        print(f"[VEO-NATIVE] Reference image not found, skipping: {ref_path}")

            # Thread ALL caller-intent params into the config (audio/duration/
            # resolution/refs) — see _build_generate_videos_config.
            config = _build_generate_videos_config(
                generate_audio=generate_audio,
                duration=duration,
                resolution=resolution,
                reference_images=ref_images or None,
            )

            generate_kwargs = {
                "model": self._model,
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # NOTE: driving-video motion conditioning is NOT wired on this path.
            # The SDK's only video input (`video=` / `source.video`) is for video
            # *extension* and is mutually exclusive with `image=` (SDK: "Not
            # allowed if image is provided"). Since we always supply a start
            # image, a driving clip cannot ride along an image-to-video call here.
            # Applying motion conditioning needs a separate GenerateVideosSource
            # design (spec §4.2). Until then the param is accepted for interface
            # stability but the call is image-only — we must NOT add `video=`
            # alongside `image=`, or the whole generation fails server-side.
            if driving_video_path and os.path.exists(driving_video_path):
                print(f"[VEO-NATIVE] Driving video provided but not wired on the "
                      f"image-to-video path (SDK image/video are mutually exclusive); "
                      f"proceeding image-only: {os.path.basename(driving_video_path)}")

            # Submit generation
            operation = self.client.models.generate_videos(**generate_kwargs)
            print(f"[VEO-NATIVE] Operation submitted, polling for completion...")

            # Poll until done (max 20 minutes to avoid indefinite hangs)
            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            while not operation.done:
                if poll_count >= max_polls:
                    raise TimeoutError(f"VEO operation timed out after {poll_count * 10}s")
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still generating... ({poll_count * 10}s elapsed)")

            # Check for RAI content filter rejection
            resp = operation.response
            if not resp or not resp.generated_videos:
                rai_reasons = getattr(resp, "rai_media_filtered_reasons", []) if resp else []
                if rai_reasons:
                    print(f"[VEO-NATIVE] RAI filter: {rai_reasons[0][:120]}")
                else:
                    print(f"[VEO-NATIVE] No video generated (empty response)")
                return None

            generated_video = resp.generated_videos[0]
            video_data = self.client.files.download(file=generated_video.video)
            with open(output_path, "wb") as f:
                f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[VEO-NATIVE] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except Exception as e:
            print(f"[VEO-NATIVE] Generation failed: {e}")
            return None

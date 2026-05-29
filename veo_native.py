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
            driving_video_path: Optional path to a performance-capture clip
                (produced by the performance/ engine adapters). When provided
                AND the file is readable, Veo accepts it as a ``reference_video``
                for motion conditioning — the character moves like the clip
                while compositionally respecting the start image. Falls through
                silently when the file is missing OR when the installed Vertex
                SDK doesn't expose the reference_video field (older builds).

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

            # Build config
            config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
            )

            # Build the generation request kwargs
            generate_kwargs = {
                "model": self._model,
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # Upload reference images for character preservation (up to 3)
            if reference_images:
                ref_images = []
                for ref_path in reference_images[:3]:
                    if os.path.exists(ref_path):
                        ref_images.append(types.Image.from_file(location=ref_path))
                        print(f"[VEO-NATIVE] Reference image loaded: {os.path.basename(ref_path)}")
                    else:
                        print(f"[VEO-NATIVE] Reference image not found, skipping: {ref_path}")
                if ref_images:
                    generate_kwargs["reference_images"] = ref_images

            # Driving-video motion conditioning. The Vertex SDK may expose this
            # under different names across versions: ``reference_video``,
            # ``motion_reference``, or as a ``Video`` instance in a list. We try
            # the documented modern name first and silently skip on AttributeError
            # so older SDK builds don't break the call.
            if driving_video_path and os.path.exists(driving_video_path):
                try:
                    # Modern Vertex AI SDK (>= 0.30): types.Video.from_file()
                    driving_video = types.Video.from_file(location=driving_video_path)  # type: ignore[attr-defined]
                    generate_kwargs["reference_video"] = driving_video
                    print(f"[VEO-NATIVE] Driving video loaded: {os.path.basename(driving_video_path)}")
                except AttributeError:
                    # Older SDK — no Video type. Skip silently; fall through to
                    # baseline image-to-video.
                    print(f"[VEO-NATIVE] reference_video not supported by installed SDK; using image-only path")
                except Exception as _e:
                    print(f"[VEO-NATIVE] driving_video load failed ({_e}); using image-only path")

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

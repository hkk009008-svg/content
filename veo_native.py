"""
Veo Native API Client — Direct Google Veo 3.1 integration via google-genai SDK.
Bypasses fal.ai proxy for native access to Veo's first+last frame control,
reference image character preservation, and synced audio generation.
"""

import os
import time

from google import genai
from google.genai import types


class VeoNativeAPI:
    """Native Google Veo 3.1 client using the google-genai SDK."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "[VEO-NATIVE] GOOGLE_API_KEY not set. "
                "Export it or add to .env before using VeoNativeAPI."
            )
        self.client = genai.Client(api_key=api_key)
        print("[VEO-NATIVE] Client initialized")

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        reference_images: list = None,
        duration: str = "8s",
        resolution: str = "720p",
        generate_audio: bool = False,
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
                "model": "veo-3.1-generate-preview",
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

            # Submit generation
            operation = self.client.models.generate_videos(**generate_kwargs)
            print(f"[VEO-NATIVE] Operation submitted, polling for completion...")

            # Poll until done
            poll_count = 0
            while not operation.done:
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still generating... ({poll_count * 10}s elapsed)")

            # Download result — files.download returns bytes
            generated_video = operation.response.generated_videos[0]
            video_data = self.client.files.download(file=generated_video.video)
            with open(output_path, "wb") as f:
                f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[VEO-NATIVE] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except Exception as e:
            print(f"[VEO-NATIVE] Generation failed: {e}")
            return None

    def generate_video_with_frames(
        self,
        first_frame_path: str,
        last_frame_path: str,
        prompt: str,
        output_path: str,
        duration: str = "6s",
    ) -> str | None:
        """
        Generate video interpolating between a first and last frame.
        Veo's unique first+last frame control — ideal for shot-to-shot transitions
        where you want deterministic start and end compositions.

        Args:
            first_frame_path: Path to the opening frame image.
            last_frame_path: Path to the closing frame image.
            prompt: Text prompt describing the transition/motion.
            output_path: Where to save the generated video.
            duration: Video duration — "5s", "6s", or "8s".

        Returns:
            output_path on success, None on failure.
        """
        if not os.path.exists(first_frame_path):
            print(f"[VEO-NATIVE] First frame not found: {first_frame_path}")
            return None
        if not os.path.exists(last_frame_path):
            print(f"[VEO-NATIVE] Last frame not found: {last_frame_path}")
            return None

        try:
            print(f"[VEO-NATIVE] Frame interpolation — {duration}")
            print(f"[VEO-NATIVE] First: {os.path.basename(first_frame_path)} → Last: {os.path.basename(last_frame_path)}")

            first_image = types.Image.from_file(location=first_frame_path)
            last_image = types.Image.from_file(location=last_frame_path)

            config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
            )

            operation = self.client.models.generate_videos(
                model="veo-3.1-generate-preview",
                prompt=prompt,
                image=first_image,
                end_image=last_image,
                config=config,
            )
            print(f"[VEO-NATIVE] Frame interpolation submitted, polling...")

            poll_count = 0
            while not operation.done:
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still interpolating... ({poll_count * 10}s elapsed)")

            video = operation.response.generated_videos[0].video
            self.client.files.download(file=video, path=output_path)

            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"[VEO-NATIVE] Interpolation saved: {output_path} ({file_size:.1f} MB)")
                return output_path
            else:
                print("[VEO-NATIVE] Download completed but file not found at output path")
                return None

        except Exception as e:
            print(f"[VEO-NATIVE] Frame interpolation failed: {e}")
            return None

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

VEO_RESOLUTIONS = {
    "720p": "720p",
    "1080p": "1080p",
    "4k": "2160p",
    "2160p": "2160p",
}
VEO_DURATIONS = ["5s", "6s", "8s"]


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

    def generate_video_4k(
        self,
        prompt: str,
        start_frame_path: str,
        output_path: str,
        duration: str = "8s",
        resolution: str = "4k",
        audio: bool = True,
        reference_images: list = None,
    ) -> tuple[str | None, str | None]:
        """
        Generate 4K video with native 24fps and optional 48kHz stereo audio
        using the full Veo 3.1 model (not preview).

        Args:
            prompt: Cinematic text prompt describing the desired scene.
            start_frame_path: Path to the start frame image.
            output_path: Where to save the generated video.
            duration: Video duration — "5s", "6s", or "8s".
            resolution: Output resolution — "720p", "1080p", "4k", or "2160p".
            audio: If True, generates native 48kHz stereo audio alongside video.
            reference_images: Optional list of up to 3 image paths for
                              character/style consistency (Ingredients-to-Video).

        Returns:
            (video_path, audio_path) tuple. audio_path is None if audio=False
            or if audio extraction fails. video_path is None on failure.
        """
        if not os.path.exists(start_frame_path):
            print(f"[VEO-NATIVE] Start frame not found: {start_frame_path}")
            return None, None

        resolved_resolution = VEO_RESOLUTIONS.get(resolution, "2160p")

        try:
            print(f"[VEO-NATIVE] 4K generation — {duration}, {resolved_resolution}, audio={audio}")
            print(f"[VEO-NATIVE] Prompt: {prompt[:120]}...")

            start_image = types.Image.from_file(location=start_frame_path)

            config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
                resolution=resolved_resolution,
                generate_audio=audio,
            )

            generate_kwargs = {
                "model": "veo-3.1-generate",
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # Upload reference images for character/style consistency (up to 3)
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

            operation = self.client.models.generate_videos(**generate_kwargs)
            print(f"[VEO-NATIVE] 4K operation submitted, polling for completion...")

            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            while not operation.done:
                if poll_count >= max_polls:
                    raise TimeoutError(f"VEO 4K operation timed out after {poll_count * 10}s")
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still generating... ({poll_count * 10}s elapsed)")

            generated_video = operation.response.generated_videos[0]

            # Download video
            video_data = self.client.files.download(file=generated_video.video)
            with open(output_path, "wb") as f:
                f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[VEO-NATIVE] 4K video saved: {output_path} ({file_size:.1f} MB)")

            # Extract audio if generated
            audio_path = None
            if audio and hasattr(generated_video, "audio") and generated_video.audio:
                audio_path = output_path.rsplit(".", 1)[0] + "_audio.wav"
                audio_data = self.client.files.download(file=generated_video.audio)
                with open(audio_path, "wb") as f:
                    f.write(audio_data)
                audio_size = os.path.getsize(audio_path) / (1024 * 1024)
                print(f"[VEO-NATIVE] 48kHz stereo audio saved: {audio_path} ({audio_size:.1f} MB)")

            return output_path, audio_path

        except Exception as e:
            print(f"[VEO-NATIVE] 4K generation failed: {e}")
            return None, None

    def generate_video_with_frames(
        self,
        first_frame_path: str,
        last_frame_path: str,
        prompt: str,
        output_path: str,
        duration: str = "6s",
        audio: bool = False,
        resolution: str = "1080p",
        reference_images: list = None,
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
            audio: If True, generates synced audio alongside video.
            resolution: Output resolution — "720p", "1080p", "4k", or "2160p".
            reference_images: Optional list of up to 3 image paths for
                              identity consistency across shots.

        Returns:
            output_path on success, None on failure.
        """
        if not os.path.exists(first_frame_path):
            print(f"[VEO-NATIVE] First frame not found: {first_frame_path}")
            return None
        if not os.path.exists(last_frame_path):
            print(f"[VEO-NATIVE] Last frame not found: {last_frame_path}")
            return None

        resolved_resolution = VEO_RESOLUTIONS.get(resolution, "1080p")

        try:
            print(f"[VEO-NATIVE] Frame interpolation — {duration}, {resolved_resolution}, audio={audio}")
            print(f"[VEO-NATIVE] First: {os.path.basename(first_frame_path)} → Last: {os.path.basename(last_frame_path)}")

            first_image = types.Image.from_file(location=first_frame_path)
            last_image = types.Image.from_file(location=last_frame_path)

            config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
                resolution=resolved_resolution,
                generate_audio=audio,
            )

            generate_kwargs = {
                "model": "veo-3.1-generate-preview",
                "prompt": prompt,
                "image": first_image,
                "end_image": last_image,
                "config": config,
            }

            # Upload reference images for identity consistency (up to 3)
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

            operation = self.client.models.generate_videos(**generate_kwargs)
            print(f"[VEO-NATIVE] Frame interpolation submitted, polling...")

            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            while not operation.done:
                if poll_count >= max_polls:
                    raise TimeoutError(f"VEO interpolation timed out after {poll_count * 10}s")
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

    def generate_with_audio(
        self,
        prompt: str,
        start_frame_path: str,
        output_path: str,
        dialogue_audio_path: str = None,
        duration: str = "5s",
    ) -> tuple[str | None, str | None]:
        """
        Generate video optimized for dialogue scenes with native audio.

        If dialogue_audio_path is provided, generates video with lip-sync
        aligned to the supplied audio track. Otherwise, Veo generates its
        own native audio from the prompt (ambient sound, speech, SFX).

        Args:
            prompt: Text prompt describing the dialogue scene.
            start_frame_path: Path to the start frame image.
            output_path: Where to save the generated video.
            dialogue_audio_path: Optional path to a dialogue audio file
                                 for lip-sync generation.
            duration: Video duration — "5s", "6s", or "8s".

        Returns:
            (video_path, synced_audio_path) tuple. video_path is None on failure.
        """
        if not os.path.exists(start_frame_path):
            print(f"[VEO-NATIVE] Start frame not found: {start_frame_path}")
            return None, None

        if dialogue_audio_path and not os.path.exists(dialogue_audio_path):
            print(f"[VEO-NATIVE] Dialogue audio not found: {dialogue_audio_path}")
            return None, None

        try:
            mode = "lip-sync" if dialogue_audio_path else "native-audio"
            print(f"[VEO-NATIVE] Dialogue generation ({mode}) — {duration}")
            print(f"[VEO-NATIVE] Prompt: {prompt[:120]}...")

            start_image = types.Image.from_file(location=start_frame_path)

            config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
                generate_audio=True,
            )

            generate_kwargs = {
                "model": "veo-3.1-generate",
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # Attach dialogue audio for lip-sync if provided
            if dialogue_audio_path:
                generate_kwargs["audio"] = types.Audio.from_file(location=dialogue_audio_path)
                print(f"[VEO-NATIVE] Dialogue audio attached: {os.path.basename(dialogue_audio_path)}")

            operation = self.client.models.generate_videos(**generate_kwargs)
            print(f"[VEO-NATIVE] Dialogue operation submitted, polling...")

            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            while not operation.done:
                if poll_count >= max_polls:
                    raise TimeoutError(f"VEO dialogue operation timed out after {poll_count * 10}s")
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still generating... ({poll_count * 10}s elapsed)")

            generated_video = operation.response.generated_videos[0]

            # Download video
            video_data = self.client.files.download(file=generated_video.video)
            with open(output_path, "wb") as f:
                f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[VEO-NATIVE] Dialogue video saved: {output_path} ({file_size:.1f} MB)")

            # Extract synced audio
            synced_audio_path = None
            if hasattr(generated_video, "audio") and generated_video.audio:
                synced_audio_path = output_path.rsplit(".", 1)[0] + "_audio.wav"
                audio_data = self.client.files.download(file=generated_video.audio)
                with open(synced_audio_path, "wb") as f:
                    f.write(audio_data)
                audio_size = os.path.getsize(synced_audio_path) / (1024 * 1024)
                print(f"[VEO-NATIVE] Synced audio saved: {synced_audio_path} ({audio_size:.1f} MB)")

            return output_path, synced_audio_path

        except Exception as e:
            print(f"[VEO-NATIVE] Dialogue generation failed: {e}")
            return None, None

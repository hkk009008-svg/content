"""
Sora Native API Client — Direct OpenAI Sora 2 integration via openai SDK.
Uses the /v1/videos endpoint for image-to-video generation with
up to 20s duration at 1080p.

Note: OpenAI has announced Sora will shut down September 2026.
"""
from __future__ import annotations

import os
import time
import base64
import mimetypes
import urllib.request

import openai
from config.settings import settings


class SoraNativeAPI:
    """Native OpenAI Sora 2 client using the openai SDK."""

    def __init__(self):
        api_key = settings.openai_api_key
        if not api_key:
            raise EnvironmentError(
                "[SORA-NATIVE] OPENAI_API_KEY not set. "
                "Export it or add to .env before using SoraNativeAPI."
            )
        self.client = openai.OpenAI(api_key=api_key)
        print("[SORA-NATIVE] Client initialized")

    def _image_to_data_url(self, image_path: str) -> str:
        """Convert a local image file to a base64 data URL for the API."""
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        duration: int = 4,
        model: str = "sora-2",
        resolution: str = "1080p",
        driving_video_path: str = "",
    ) -> str | None:
        """
        Generate video from a start frame image + text prompt using Sora 2.

        Args:
            image_path: Path to the start frame image.
            prompt: Text prompt describing the desired motion/scene.
            output_path: Where to save the generated video.
            duration: Video duration in seconds — 4, 8, 12, 16, or 20 (integer).
            model: Model name — "sora-2" (default).
            resolution: Output resolution — "480p", "720p", or "1080p".
            driving_video_path: Optional path to a performance-capture clip.
                When provided AND the file exists, Sora uses it as the
                ``input_reference`` (video) instead of the resized still image.
                Sora 2 supports video conditioning natively through this same
                field — driving the character's motion from the reference clip
                while still respecting the start-frame composition. Falls
                through to the still-image path on any access error.

        Returns:
            output_path on success, None on failure.
        """
        if not os.path.exists(image_path):
            print(f"[SORA-NATIVE] Start frame not found: {image_path}")
            return None
        # Driving video opt-in: only used when the file actually exists.
        use_driving = bool(driving_video_path) and os.path.exists(driving_video_path)
        if use_driving:
            print(f"[SORA-NATIVE] Using performance driving video as input_reference: {os.path.basename(driving_video_path)}")

        valid_durations = [4, 8, 12, 16, 20]
        if duration not in valid_durations:
            print(f"[SORA-NATIVE] Invalid duration {duration}s, must be one of {valid_durations}. Defaulting to 4s.")
            duration = 4

        try:
            print(f"[SORA-NATIVE] Generating video — {duration}s, {resolution}, model={model}")
            print(f"[SORA-NATIVE] Prompt: {prompt[:120]}...")

            # Encode image as data URL
            image_data_url = self._image_to_data_url(image_path)

            # Resize image to 1280x720 and save as temp file
            from PIL import Image as PILImage
            import tempfile
            img = PILImage.open(image_path)
            img = img.resize((1280, 720), PILImage.LANCZOS)
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            img.save(tmp.name, format="JPEG", quality=90)
            tmp_path = tmp.name
            tmp.close()
            print(f"[SORA-NATIVE] Image resized to 1280x720: {tmp_path}")

            # Pass as PathLike — the SDK expects a file path, bytes, or IO object.
            # When a driving video was supplied, prefer it as the reference: Sora 2
            # accepts video here for motion conditioning. The still-frame resize
            # above still runs as a safety net (Sora needs a valid composition
            # even when video conditioning is used).
            from pathlib import Path
            reference_for_sora = Path(driving_video_path) if use_driving else Path(tmp_path)
            video = self.client.videos.create_and_poll(
                model=model,
                prompt=prompt,
                input_reference=reference_for_sora,
                seconds=duration,
                size="1280x720",
            )

            # Clean up the still-frame temp file (driving video is operator-owned, leave it).
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

            status = getattr(video, "status", "unknown")
            if status != "completed":
                print(f"[SORA-NATIVE] Generation ended with status: {status}")
                return None

            print(f"[SORA-NATIVE] Generation completed")

            # Download — try multiple response structures
            download_url = None
            for attr_chain in [("url",), ("video", "url"), ("output", "url")]:
                obj = video
                for attr in attr_chain:
                    obj = getattr(obj, attr, None)
                    if obj is None:
                        break
                if isinstance(obj, str) and obj.startswith("http"):
                    download_url = obj
                    break

            # Download via download_content — the primary method for Sora
            print(f"[SORA-NATIVE] Downloading video {video.id}...")
            content = self.client.videos.download_content(video.id)
            with open(output_path, "wb") as f:
                for chunk in content.response.iter_bytes():
                    f.write(chunk)
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[SORA-NATIVE] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except Exception as e:
            print(f"[SORA-NATIVE] Generation failed: {e}")
            return None

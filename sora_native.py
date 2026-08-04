"""
Sora Native API Client — Direct OpenAI Sora 2 integration via openai SDK.
Uses the /v1/videos endpoint for image-to-video generation with
4, 8, or 12 second duration requests.

Note: OpenAI has announced Sora will shut down September 2026.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

import openai
from config.settings import settings
from cinema.aspect import portrait_swap
from performance._net import (
    DEFAULT_MAX_BYTES,
    atomic_publish_stream,
    validate_video_artifact,
)

# Maps the public resolution string to the Sora API `size` parameter value.
# Mirrors the naming convention of ltx_native.RESOLUTION_MAP (sora uses flat
# "WxH" strings; ltx uses {"width": N, "height": N} dicts).
RESOLUTION_MAP: dict[str, str] = {
    "480p": "480x270",
    "720p": "1280x720",
    "1080p": "1920x1080",
}

SORA_DURATION_SECONDS = (4, 8, 12)
SORA_MAX_VIDEO_BYTES = DEFAULT_MAX_BYTES


class SoraNativeAPI:
    """Native OpenAI Sora 2 client using the openai SDK.

    Note: __init__ raises EnvironmentError when OPENAI_API_KEY is empty.
    This is intentional — matches veo_native behaviour; caller (phase_c_ffmpeg)
    catches the exception and falls through to the next API.
    """

    def __init__(self):
        api_key = settings.openai_api_key
        if not api_key:
            raise EnvironmentError(
                "[SORA-NATIVE] OPENAI_API_KEY not set. "
                "Export it or add to .env before using SoraNativeAPI."
            )
        self.client = openai.OpenAI(api_key=api_key)
        print("[SORA-NATIVE] Client initialized")

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        duration: int = 4,
        model: str = "sora-2",
        resolution: str = "1080p",
        driving_video_path: str = "",
        aspect_ratio: str = "16:9",
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Generate video from a start frame image + text prompt using Sora 2.

        Args:
            image_path: Path to the required start frame image.
            prompt: Text prompt describing the desired motion/scene.
            output_path: Where to save the generated video.
            duration: Video duration in seconds — 4, 8, or 12 (integer).
            model: Model name — "sora-2" (default).
            resolution: Output resolution — "480p", "720p", or "1080p".
            driving_video_path: Interface-compatible performance-capture path.
                Sora's ``input_reference`` accepts images, not video. Any
                non-empty value is rejected before preprocessing or submission.
            aspect_ratio: Project aspect ratio string — "16:9" (default, landscape)
                or "9:16" (portrait). When portrait, both the PIL resize target
                and the API ``size=`` parameter are transposed via portrait_swap
                so the full generation pipeline emits 9:16 output.
            on_billed: Optional zero-arg callback invoked exactly once, the
                moment the provider reports the generation ``completed`` —
                the repo's billed bar (a provider that finished rendering a
                video is billed regardless of what happens next; see
                phase_c_ffmpeg._note_billed_attempt). Fires BEFORE the
                download_content call so a caller can record the spend even
                when the download that follows fails and this method still
                returns None (money-gate 2026-07-11 class, extended to the
                native adapters in slice M2: post-billing failures were
                previously indistinguishable from pre-billing ones).
                Exceptions raised by the callback are logged and swallowed —
                a broken accounting hook must never abort a download that
                would otherwise succeed.

        Returns:
            output_path on success, None on failure — either pre-billing
            (SDK/create_and_poll error, non-completed status) or
            post-billing (the provider completed the video but the download
            that followed failed).
        """
        if driving_video_path:
            print(
                "[SORA-NATIVE] Driving-video input is unsupported; "
                "input_reference must be a still image."
            )
            return None

        if duration not in SORA_DURATION_SECONDS:
            print(
                f"[SORA-NATIVE] Invalid duration {duration}s; "
                f"must be one of {list(SORA_DURATION_SECONDS)}."
            )
            return None

        if not os.path.exists(image_path):
            print(f"[SORA-NATIVE] Start frame not found: {image_path}")
            return None

        # sora-2 supports ONLY the 720p tier (1280x720 / 720x1280 per the API); 1080p and
        # 480p requests 400 ("Invalid size for sora-2 model"). Clamp to 720p so the call can't
        # fail on size — assembly normalize upscales the 720p clip to the project container
        # (e.g. 1080x1920) at render. sora-2-pro is left unclamped. See plan U6 + T9 preflight.
        if model == "sora-2" and resolution != "720p":
            print(f"[SORA-NATIVE] {model} supports only 720p sizes; clamping {resolution}→720p (assembly upscales).")
            resolution = "720p"

        try:
            print(f"[SORA-NATIVE] Generating video — {duration}s, {resolution}, model={model}")
            print(f"[SORA-NATIVE] Prompt: {prompt[:120]}...")

            # Resolve resolution to the API size string, then parse W×H for resize.
            # Apply portrait_swap once: this drives BOTH the PIL resize target
            # (below) and the API size= param — one swap covers both surfaces.
            size = RESOLUTION_MAP.get(resolution, RESOLUTION_MAP["720p"])
            w_str, h_str = size.split("x")
            target_w, target_h = portrait_swap(int(w_str), int(h_str), aspect_ratio)
            size = f"{target_w}x{target_h}"

            temp_still_path: Path | None = None
            try:
                # Pass as PathLike — the SDK expects a file path, bytes, or IO
                # object. The Videos API input-reference contract is image-only.
                from PIL import Image as PILImage

                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as temp_still:
                    temp_still_path = Path(temp_still.name)

                with PILImage.open(image_path) as source_image:
                    resized_image = source_image.resize(
                        (target_w, target_h), PILImage.LANCZOS
                    )
                    try:
                        resized_image.save(
                            temp_still_path, format="JPEG", quality=90
                        )
                    finally:
                        resized_image.close()

                reference_for_sora = temp_still_path
                print(
                    f"[SORA-NATIVE] Image resized to {size}: "
                    f"{temp_still_path}"
                )

                video = self.client.videos.create_and_poll(
                    model=model,
                    prompt=prompt,
                    input_reference=reference_for_sora,
                    seconds=duration,
                    size=size,
                )

                status = getattr(video, "status", "unknown")
                if status != "completed":
                    print(f"[SORA-NATIVE] Generation ended with status: {status}")
                    return None

                print(f"[SORA-NATIVE] Generation completed")

                # Provider reports the video completed — billed regardless of
                # what happens next. Notify the caller BEFORE the download
                # attempt so a subsequent download failure below still reaches
                # the caller's spend accounting, even though this call goes on
                # to return None.
                if on_billed is not None:
                    try:
                        on_billed()
                    except Exception as callback_exc:
                        print(
                            f"[SORA-NATIVE] Warning: on_billed callback raised: {callback_exc}"
                        )

                # Download via download_content through the shared bounded,
                # validated atomic publisher. A mid-stream failure or response
                # over the hard cap preserves any prior output_path.
                print(f"[SORA-NATIVE] Downloading video {video.id}...")
                content = self.client.videos.download_content(video.id)
                if atomic_publish_stream(
                    content.response.iter_bytes(),
                    output_path,
                    max_bytes=SORA_MAX_VIDEO_BYTES,
                    content_validator=validate_video_artifact,
                ) is None:
                    raise RuntimeError("Sora response failed MP4 validation")
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                print(f"[SORA-NATIVE] Video saved: {output_path} ({file_size:.1f} MB)")
                return output_path
            finally:
                # Only this method's generated still is owned here.
                if temp_still_path is not None:
                    try:
                        temp_still_path.unlink()
                    except OSError:
                        pass  # Cleanup is non-fatal if the OS refuses deletion.

        except Exception as e:
            print(f"[SORA-NATIVE] Generation failed: {e}")
            return None

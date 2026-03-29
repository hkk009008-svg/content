"""
Kling 3.0 Native API Client
Direct integration with Kling's image-to-video and storyboard APIs.
Uses JWT (HS256) authentication with access/secret key pairs.

Requirements:
    pip install PyJWT requests
"""

import os
import time
import base64
import jwt
import requests


class KlingNativeAPI:
    """Native client for the Kling 3.0 video generation API."""

    BASE_URL = "https://api.klingai.com"

    def __init__(self):
        """Initialize the Kling API client.

        Reads KLING_ACCESS_KEY and KLING_SECRET_KEY from environment variables
        and generates an initial JWT token.

        Raises:
            ValueError: If required environment variables are not set.
        """
        self.access_key = os.environ.get("KLING_ACCESS_KEY")
        self.secret_key = os.environ.get("KLING_SECRET_KEY")

        if not self.access_key or not self.secret_key:
            raise ValueError(
                "[KLING-NATIVE] KLING_ACCESS_KEY and KLING_SECRET_KEY must be set"
            )

        self._token = None
        self._token_exp = 0
        self._generate_token()
        print("[KLING-NATIVE] Client initialized")

    def _generate_token(self) -> str:
        """Generate a JWT token with HS256 signing.

        Caches the token and only regenerates when less than 5 minutes remain
        before expiration.

        Returns:
            The signed JWT token string.
        """
        now = time.time()

        # Return cached token if more than 5 minutes remain
        if self._token and (self._token_exp - now) > 300:
            return self._token

        exp = now + 1800  # 30 minutes
        nbf = now - 5

        payload = {
            "iss": self.access_key,
            "exp": int(exp),
            "nbf": int(nbf),
        }

        self._token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        self._token_exp = exp
        return self._token

    def _headers(self) -> dict:
        """Build request headers with a fresh Bearer token.

        Returns:
            Dict with Authorization and Content-Type headers.
        """
        token = self._generate_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def create_image_to_video(
        self,
        image_path: str,
        prompt: str,
        negative_prompt: str = "",
        duration: str = "5",
        mode: str = "pro",
        model_name: str = "kling-v1-6",
        cfg_scale: float = 0.5,
        face_consistency: bool = False,
        image_references: list = None,
    ) -> str:
        """Submit an image-to-video generation task.

        Args:
            image_path: Path to the source image file.
            prompt: Text prompt describing the desired video motion.
            negative_prompt: Things to avoid in the generation.
            duration: Video duration in seconds (as string).
            mode: Generation mode ('pro' or 'std').
            model_name: Kling model version identifier.
            cfg_scale: Classifier-free guidance scale (0.0-1.0).
            face_consistency: Enable face consistency preservation.
            image_references: Optional list of reference image paths for
                style/character consistency.

        Returns:
            The task_id string for polling.

        Raises:
            FileNotFoundError: If image_path or any reference path does not exist.
            RuntimeError: If the API returns an error.
        """
        # Read and encode the source image
        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"[KLING-NATIVE] Source image not found: {image_path}"
            )

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        body = {
            "model_name": model_name,
            "image": image_b64,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": duration,
            "mode": mode,
            "cfg_scale": cfg_scale,
        }

        if face_consistency:
            body["face_consistency"] = True

        # Encode reference images if provided
        if image_references:
            ref_list = []
            for ref_path in image_references:
                if not os.path.exists(ref_path):
                    raise FileNotFoundError(
                        f"[KLING-NATIVE] Reference image not found: {ref_path}"
                    )
                with open(ref_path, "rb") as f:
                    ref_list.append(base64.b64encode(f.read()).decode("utf-8"))
            body["image_reference"] = ref_list

        url = f"{self.BASE_URL}/v1/videos/image2video"
        print(f"[KLING-NATIVE] Submitting image2video task ({mode}, {duration}s)")

        resp = requests.post(url, json=body, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 0:
            raise RuntimeError(
                f"[KLING-NATIVE] API error {result.get('code')}: "
                f"{result.get('message', 'unknown error')}"
            )

        task_id = result["data"]["task_id"]
        print(f"[KLING-NATIVE] Task {task_id} queued")
        return task_id

    def poll_task(
        self, task_id: str, timeout: int = 600, initial_interval: int = 3
    ) -> dict:
        """Poll a task until completion, failure, or timeout.

        Uses exponential backoff: 3s -> 5s -> 8s -> 12s -> 15s (capped).

        Args:
            task_id: The task ID returned by create_image_to_video.
            timeout: Maximum seconds to wait before raising TimeoutError.
            initial_interval: Starting poll interval in seconds.

        Returns:
            The full task result dict on success.

        Raises:
            RuntimeError: If the task fails.
            TimeoutError: If polling exceeds the timeout.
        """
        url = f"{self.BASE_URL}/v1/videos/image2video/{task_id}"
        backoff_schedule = [3, 5, 8, 12, 15]
        backoff_idx = 0
        elapsed = 0
        interval = initial_interval

        print(f"[KLING-NATIVE] Polling task {task_id}...")

        while elapsed < timeout:
            time.sleep(interval)
            elapsed += interval

            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                raise RuntimeError(
                    f"[KLING-NATIVE] Poll error {result.get('code')}: "
                    f"{result.get('message', 'unknown error')}"
                )

            data = result.get("data", {})
            status = data.get("task_status", "unknown")

            print(f"[KLING-NATIVE] Polling... ({int(elapsed)}s) — status: {status}")

            if status == "succeed":
                print(f"[KLING-NATIVE] Task {task_id} completed successfully")
                return data

            if status == "failed":
                reason = data.get("task_status_msg", "no reason given")
                raise RuntimeError(
                    f"[KLING-NATIVE] Task {task_id} failed: {reason}"
                )

            # Advance backoff
            if backoff_idx < len(backoff_schedule) - 1:
                backoff_idx += 1
            interval = backoff_schedule[backoff_idx]

        raise TimeoutError(
            f"[KLING-NATIVE] Task {task_id} timed out after {timeout}s"
        )

    def download_video(self, video_url: str, output_path: str) -> str:
        """Stream-download a video from a URL to a local file.

        Args:
            video_url: The remote URL of the generated video.
            output_path: Local file path to write the video to.

        Returns:
            The output_path on success.

        Raises:
            requests.HTTPError: If the download request fails.
        """
        print(f"[KLING-NATIVE] Downloading video to {output_path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[KLING-NATIVE] Downloaded {size_mb:.1f}MB to {output_path}")
        return output_path

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        **kwargs,
    ) -> str | None:
        """High-level convenience: create task, poll, download.

        Args:
            image_path: Path to the source image.
            prompt: Motion/action prompt for the video.
            output_path: Where to save the resulting video file.
            **kwargs: Additional arguments passed to create_image_to_video
                (negative_prompt, duration, mode, model_name, cfg_scale,
                face_consistency, image_references).

        Returns:
            The output_path on success, None on failure.
        """
        try:
            task_id = self.create_image_to_video(image_path, prompt, **kwargs)
            print(f"[KLING-NATIVE] Task {task_id} queued...")

            timeout = kwargs.pop("timeout", 600)
            result = self.poll_task(task_id, timeout=timeout)

            # Extract video URL from result
            videos = result.get("task_result", {}).get("videos", [])
            if not videos:
                print("[KLING-NATIVE] Error: No videos in task result")
                return None

            video_url = videos[0].get("url")
            if not video_url:
                print("[KLING-NATIVE] Error: No URL in video result")
                return None

            path = self.download_video(video_url, output_path)
            print(f"[KLING-NATIVE] Success: {path}")
            return path

        except Exception as e:
            print(f"[KLING-NATIVE] Error in generate_video: {e}")
            return None

    def generate_storyboard(
        self,
        image_path: str,
        shots: list,
        output_path: str,
        image_references: list = None,
    ) -> str | None:
        """Generate a multi-shot storyboard video using Kling's 6-shot mode.

        Distributes up to 15 seconds across the provided shots and enables
        face consistency by default for character continuity.

        Args:
            image_path: Path to the source/anchor image.
            shots: List of shot dicts, each with at least a "prompt" key.
                Optional "duration" key per shot; otherwise auto-distributed.
                Example: [{"prompt": "Character turns left"}, {"prompt": "Close-up smile"}]
            output_path: Where to save the resulting storyboard video.
            image_references: Optional list of reference image paths for
                character/style consistency across shots.

        Returns:
            The output_path on success, None on failure.
        """
        try:
            if not shots:
                print("[KLING-NATIVE] Error: No shots provided for storyboard")
                return None

            max_total_duration = 15.0
            num_shots = min(len(shots), 6)  # Kling supports up to 6 shots
            active_shots = shots[:num_shots]

            if num_shots < len(shots):
                print(
                    f"[KLING-NATIVE] Warning: Truncating {len(shots)} shots to "
                    f"max 6 for storyboard"
                )

            # Distribute duration across shots
            # Respect per-shot durations if provided, otherwise split evenly
            per_shot_duration = max_total_duration / num_shots

            multi_prompt = []
            total_allocated = 0.0

            for shot in active_shots:
                shot_dur = float(shot.get("duration", per_shot_duration))
                # Clamp so we don't exceed total budget
                remaining = max_total_duration - total_allocated
                shot_dur = min(shot_dur, remaining)
                shot_dur = max(shot_dur, 1.0)  # Minimum 1 second per shot

                multi_prompt.append({
                    "prompt": shot["prompt"],
                    "duration": str(round(shot_dur, 1)),
                })
                total_allocated += shot_dur

            total_duration = str(round(total_allocated))

            print(
                f"[KLING-NATIVE] Storyboard: {num_shots} shots, "
                f"{total_duration}s total"
            )

            # Read and encode source image
            if not os.path.exists(image_path):
                raise FileNotFoundError(
                    f"[KLING-NATIVE] Source image not found: {image_path}"
                )

            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            body = {
                "model_name": "kling-v1-6",
                "image": image_b64,
                "prompt": " | ".join(s["prompt"] for s in active_shots),
                "negative_prompt": "",
                "duration": total_duration,
                "mode": "pro",
                "cfg_scale": 0.5,
                "face_consistency": True,
                "multi_prompt": multi_prompt,
            }

            # Encode reference images
            if image_references:
                ref_list = []
                for ref_path in image_references:
                    if not os.path.exists(ref_path):
                        raise FileNotFoundError(
                            f"[KLING-NATIVE] Reference image not found: {ref_path}"
                        )
                    with open(ref_path, "rb") as f:
                        ref_list.append(
                            base64.b64encode(f.read()).decode("utf-8")
                        )
                body["image_reference"] = ref_list

            url = f"{self.BASE_URL}/v1/videos/image2video"
            print(f"[KLING-NATIVE] Submitting storyboard task ({num_shots} shots)")

            resp = requests.post(url, json=body, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            result = resp.json()

            if result.get("code") != 0:
                raise RuntimeError(
                    f"[KLING-NATIVE] API error {result.get('code')}: "
                    f"{result.get('message', 'unknown error')}"
                )

            task_id = result["data"]["task_id"]
            print(f"[KLING-NATIVE] Storyboard task {task_id} queued...")

            # Poll for completion
            data = self.poll_task(task_id, timeout=600)

            videos = data.get("task_result", {}).get("videos", [])
            if not videos:
                print("[KLING-NATIVE] Error: No videos in storyboard result")
                return None

            video_url = videos[0].get("url")
            if not video_url:
                print("[KLING-NATIVE] Error: No URL in storyboard result")
                return None

            path = self.download_video(video_url, output_path)
            print(f"[KLING-NATIVE] Storyboard success: {path}")
            return path

        except Exception as e:
            print(f"[KLING-NATIVE] Error in generate_storyboard: {e}")
            return None

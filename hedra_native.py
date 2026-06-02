"""
Hedra Native API Client — Direct Hedra Character-3 talking-head integration.

Bypasses the dead fal-ai/hedra proxy (HTTP 404) with a direct call to
api.hedra.com. Flow confirmed from scripts/_hedra_test.py (proven live):
  create image asset → upload → create audio asset → upload
  → POST /generations (Character-3) → poll /status → download from url.

Public entry: HedraAPI.generate_talking_head(image_path, audio_path, output_path, ...)
Returns output_path on success, None on failure.
"""
from __future__ import annotations

import os
import time

import requests

from config.settings import settings

BASE = "https://api.hedra.com/web-app/public"
CHAR3 = "d1dd37a3-e39a-4854-a298-6510289f9cf2"  # Character-3 model id (confirmed live)


class HedraAPI:
    """Direct Hedra Character-3 client.

    Uploading assets and submitting generations via api.hedra.com.
    Mirrors the contract of the other *_native clients: public method
    returns output_path on success, None on graceful failure.
    """

    def __init__(self):
        self._key = settings.hedra_api_key
        self._headers = {"x-api-key": self._key}

    def _create_and_upload(self, path: str, atype: str) -> str | None:
        """Create a Hedra asset of `atype` ("image" or "audio"), upload `path`,
        return the asset id. Returns None on any error (caller logs + returns None)."""
        json_headers = {**self._headers, "Content-Type": "application/json"}
        r = requests.post(
            f"{BASE}/assets",
            headers=json_headers,
            json={"name": os.path.basename(path), "type": atype},
            timeout=30,
        )
        r.raise_for_status()
        aid = r.json()["id"]
        with open(path, "rb") as f:
            up = requests.post(
                f"{BASE}/assets/{aid}/upload",
                headers=self._headers,
                files={"file": f},
                timeout=180,
            )
            up.raise_for_status()
        print(f"   [HEDRA-NATIVE] uploaded {atype} -> asset {aid}")
        return aid

    def generate_talking_head(
        self,
        character_image_path: str,
        audio_path: str,
        output_path: str,
        text_prompt: str = (
            "A person speaks warmly and naturally to the camera, subtle natural "
            "head movement, gentle smile, photorealistic, soft natural light."
        ),
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
    ) -> str | None:
        """
        Generate a Character-3 talking-head video from a still image + audio.

        Args:
            character_image_path: Local path to the character reference image.
            audio_path:           Local path to the dialogue audio file.
            output_path:          Where to save the resulting mp4.
            text_prompt:          Style / motion guidance fed to Character-3.
            resolution:           "720p" (default) or higher Hedra-supported tier.
            aspect_ratio:         "16:9" (default), "9:16", or "1:1".

        Returns:
            output_path on success, None on any failure (logs reason; cascade falls through).
        """
        if not self._key:
            print("   [HEDRA-NATIVE] hedra_api_key is empty — skipping")
            return None

        if not os.path.exists(character_image_path):
            print(f"   [HEDRA-NATIVE] image not found: {character_image_path}")
            return None

        if not os.path.exists(audio_path):
            print(f"   [HEDRA-NATIVE] audio not found: {audio_path}")
            return None

        try:
            t0 = time.time()
            print(
                f"   [HEDRA-NATIVE] Character-3 — image={os.path.basename(character_image_path)} "
                f"audio={os.path.basename(audio_path)} res={resolution} aspect={aspect_ratio}"
            )

            image_id = self._create_and_upload(character_image_path, "image")
            audio_id = self._create_and_upload(audio_path, "audio")

            body = {
                "type": "video",
                "ai_model_id": CHAR3,
                "start_keyframe_id": image_id,
                "audio_id": audio_id,
                "generated_video_inputs": {
                    "text_prompt": text_prompt,
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                },
            }
            g = requests.post(
                f"{BASE}/generations",
                headers={**self._headers, "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            if g.status_code >= 400:
                print(f"   [HEDRA-NATIVE] generation rejected {g.status_code}: {g.text[:400]}")
                return None

            gid = g.json()["id"]
            print(f"   [HEDRA-NATIVE] generation {gid} submitted; polling /status...")

            url = None
            for i in range(150):  # up to ~12.5 minutes at 5s intervals
                time.sleep(5)
                s = requests.get(
                    f"{BASE}/generations/{gid}/status",
                    headers=self._headers,
                    timeout=30,
                )
                s.raise_for_status()
                st = s.json()
                status = st.get("status")
                if i % 6 == 0:
                    print(
                        f"   [HEDRA-NATIVE] status={status} progress={st.get('progress')} "
                        f"({i * 5}s elapsed)"
                    )
                if status == "complete":
                    url = st.get("download_url") or st.get("url")
                    break
                if status == "error":
                    print(f"   [HEDRA-NATIVE] generation error: {st.get('error_message')}")
                    return None

            if not url:
                print("   [HEDRA-NATIVE] timeout — no download_url received")
                return None

            elapsed = (time.time() - t0) / 60
            print(f"   [HEDRA-NATIVE] complete ({elapsed:.1f} min); downloading...")
            v = requests.get(url, timeout=300)
            v.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(v.content)

            size_mb = os.path.getsize(output_path) / 1024 / 1024
            print(f"   [HEDRA-NATIVE] saved {output_path} ({size_mb:.1f} MB)")
            return output_path

        except Exception as e:
            print(f"   [HEDRA-NATIVE] failed: {e}")
            return None

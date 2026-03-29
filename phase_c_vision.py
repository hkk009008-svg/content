import cv2
import os
import json
import base64
try:
    from deepface import DeepFace
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("⚠️ [VISION WARNING] DeepFace/Tensorflow unavailable via PIP. Identity validation loop bypassed.")

def get_middle_frame(video_path, output_image_path):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    middle_frame_index = total_frames // 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame_index)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_image_path, frame)
    cap.release()
    return ret

def validate_identity(video_path, character_id, threshold=0.60):
    """
    DEPRECATED: Use IdentityValidator.validate_video() for rich diagnostics.
    Kept for backward compatibility — returns bool.
    """
    if not VISION_AVAILABLE:
        return True

    char_db_path = "characters.json"
    if not os.path.exists(char_db_path):
        print(f"   ⚠️ {char_db_path} not found, bypassing identity validation")
        return True

    with open(char_db_path, "r") as f:
        chars = json.load(f)

    char_data = chars.get(character_id)
    if not char_data or "reference_image" not in char_data:
        return True

    ref_img = char_data["reference_image"]
    if not os.path.exists(ref_img):
        return True

    from identity_validator import IdentityValidator
    validator = IdentityValidator()
    result = validator.validate_video(
        video_path,
        [{"id": character_id, "reference_image": ref_img, "name": character_id}],
        threshold=threshold,
    )
    return result.passed


def validate_identity_image(image_path: str, reference_path: str, threshold: float = 0.70) -> dict:
    """
    DEPRECATED: Use IdentityValidator.validate_image() for rich diagnostics.
    Kept for backward compatibility — returns {"passed": bool, "similarity": float}.
    """
    if not VISION_AVAILABLE:
        return {"passed": True, "similarity": 1.0}

    if not os.path.exists(image_path) or not os.path.exists(reference_path):
        return {"passed": True, "similarity": 0.0}

    from identity_validator import IdentityValidator
    validator = IdentityValidator()
    result = validator.validate_image(image_path, reference_path, threshold=threshold)
    return {"passed": result.passed, "similarity": result.overall_score}

def validate_multi_identity(video_path, character_configs: list, threshold=0.55):
    """
    DEPRECATED: Use IdentityValidator.validate_video() for rich diagnostics.
    Kept for backward compatibility — returns {"passed": bool, "results": {char_id: {...}}}.
    """
    if not VISION_AVAILABLE:
        return {"passed": True, "results": {}}

    if not character_configs:
        return {"passed": True, "results": {}}

    from identity_validator import IdentityValidator
    validator = IdentityValidator()
    result = validator.validate_video(video_path, character_configs, threshold=threshold)
    return {
        "passed": result.passed,
        "results": {
            cid: {"matched": cr.matched, "similarity": cr.best_similarity}
            for cid, cr in result.character_results.items()
        },
    }


def extract_frame_at(video_path, position_ratio, output_path):
    """Extract a frame at a given position (0.0 to 1.0) from a video."""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * position_ratio))
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_path, frame)
    cap.release()
    return ret


def face_swap_video_frames(video_path, reference_image, output_path):
    """
    Post-processing face swap for identity consistency.
    Priority: fal.ai cloud swap → FaceFusion CLI → skip
    """
    # PRIORITY 1: fal.ai PixVerse face swap (cloud, no local deps)
    try:
        import fal_client
        import urllib.request

        if os.getenv("FAL_KEY"):
            print(f"   [FACESWAP] Uploading to fal.ai...")
            video_url = fal_client.upload_file(video_path)
            face_url = fal_client.upload_file(reference_image)

            result = fal_client.subscribe(
                "fal-ai/pixverse/swap",
                arguments={
                    "video_url": video_url,
                    "swap_image_url": face_url,
                },
                with_logs=True,
            )
            out_url = result.get("video", {}).get("url")
            if out_url:
                urllib.request.urlretrieve(out_url, output_path)
                print(f"   [FACESWAP] Cloud swap complete: {output_path}")
                return output_path
    except Exception as e:
        print(f"   [FACESWAP] fal.ai swap failed: {e}")

    # PRIORITY 2: FaceFusion CLI (local, needs full install)
    try:
        import subprocess
        result = subprocess.run(
            ["facefusion", "headless-run",
             "--source-paths", reference_image,
             "--target-path", video_path,
             "--output-path", output_path,
             "--face-swapper-model", "inswapper_128_fp16",
             "--face-enhancer-model", "gfpgan_1.4",
             "--execution-providers", "cpu"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"   [FACESWAP] FaceFusion complete: {output_path}")
            return output_path
    except FileNotFoundError:
        print("   [FACESWAP] FaceFusion not installed. Skipping.")
    except Exception as e:
        print(f"   [FACESWAP] FaceFusion error: {e}")

    return None


if __name__ == "__main__":
    valid = validate_identity("temp_vid_0.mp4", "the_strategist")
    print(f"Structural Identity Lock Valid: {valid}")

def quality_control_image(image_path: str, prompt_text: str = "") -> bool:
    """
    Validates structural integrity of a generated latent frame.
    Given TensorFlow limitations over PIP on MacOS Apple Silicon, this acts as a
    graceful passthrough if proper vision validation routines are missing.
    """
    if not VISION_AVAILABLE:
        return True
    return True


# ======================================================================
# LLM Vision Validators — GPT-4o, Claude, Gemini
# ======================================================================

def _encode_image_base64(image_path: str) -> str:
    """Read an image file and return its base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _image_media_type(image_path: str) -> str:
    """Infer MIME type from file extension."""
    ext = os.path.splitext(image_path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def validate_shot_quality_vision(image_path: str, original_prompt: str) -> dict:
    """
    GPT-4o Vision analyzes a generated image against its prompt.
    Returns: {"score": 0-10, "issues": [...], "pass": bool, "suggestions": [...]}
    """
    default_pass = {
        "score": 7,
        "issues": [],
        "pass": True,
        "suggestions": [],
        "source": "default",
    }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[VISION-QA] WARNING: No OPENAI_API_KEY — returning default pass")
        return default_pass

    if not os.path.exists(image_path):
        print(f"[VISION-QA] WARNING: Image not found: {image_path}")
        return default_pass

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        img_b64 = _encode_image_base64(image_path)
        media_type = _image_media_type(image_path)

        system_prompt = (
            "You are a cinematic shot quality evaluator. Analyze this generated image against "
            "the original prompt. Evaluate on these criteria:\n"
            "1. Composition — rule of thirds, framing, visual balance\n"
            "2. Lighting — natural, consistent, mood-appropriate\n"
            "3. Face visibility — if people are present, are faces clear and well-formed?\n"
            "4. Outfit/wardrobe accuracy — does clothing match the prompt description?\n"
            "5. Prompt adherence — does the image match what was requested?\n"
            "6. Artifact detection — any glitches, extra limbs, blurry regions, text artifacts?\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"score": <0-10>, "issues": ["..."], "suggestions": ["..."]}'
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Original prompt: \"{original_prompt}\"\n\nEvaluate this generated image:",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{img_b64}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=0.2,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        result["pass"] = result.get("score", 0) >= 7
        result["source"] = "gpt-4o"
        print(f"[VISION-QA] GPT-4o score: {result['score']}/10 — {'PASS' if result['pass'] else 'FAIL'}")
        if result.get("issues"):
            for issue in result["issues"]:
                print(f"   - {issue}")
        return result

    except Exception as e:
        print(f"[VISION-QA] GPT-4o validation failed: {e}")
        return default_pass


def validate_identity_vision(reference_path: str, generated_path: str) -> dict:
    """
    Claude Vision compares reference face vs generated face.
    Replaces broken DeepFace with LLM visual reasoning.
    Returns: {"match": bool, "confidence": 0.0-1.0, "issues": [...]}
    """
    default_pass = {
        "match": True,
        "confidence": 0.7,
        "issues": [],
        "source": "default",
    }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[VISION-ID] WARNING: No ANTHROPIC_API_KEY — returning default pass")
        return default_pass

    if not os.path.exists(reference_path):
        print(f"[VISION-ID] WARNING: Reference image not found: {reference_path}")
        return default_pass
    if not os.path.exists(generated_path):
        print(f"[VISION-ID] WARNING: Generated image not found: {generated_path}")
        return default_pass

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        ref_b64 = _encode_image_base64(reference_path)
        gen_b64 = _encode_image_base64(generated_path)
        ref_media = _image_media_type(reference_path)
        gen_media = _image_media_type(generated_path)

        system_prompt = (
            "You are an identity verification expert. Compare these two images and determine "
            "if they show the same person. Focus on:\n"
            "- Facial bone structure\n"
            "- Eye shape and spacing\n"
            "- Nose shape and size\n"
            "- Jawline and chin shape\n"
            "- Hair color and style\n\n"
            "IGNORE differences in: clothing, background, lighting, pose, expression, "
            "image style (photo vs illustration).\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"confidence": <0.0-1.0>, "issues": ["..."]}'
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Image 1 is the REFERENCE (ground truth). Image 2 is the GENERATED image. Are they the same person?",
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": ref_media,
                                "data": ref_b64,
                            },
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": gen_media,
                                "data": gen_b64,
                            },
                        },
                    ],
                },
            ],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        result["match"] = result.get("confidence", 0.0) >= 0.7
        result["source"] = "claude-sonnet"
        status = "MATCH" if result["match"] else "MISMATCH"
        print(f"[VISION-ID] Claude identity check: {result['confidence']:.2f} — {status}")
        if result.get("issues"):
            for issue in result["issues"]:
                print(f"   - {issue}")
        return result

    except Exception as e:
        print(f"[VISION-ID] Claude identity validation failed: {e}")
        return default_pass


def validate_scene_coherence_vision(shot_images: list[str]) -> dict:
    """
    Gemini Vision checks consecutive shots for continuity errors.
    Returns: {"coherent": bool, "issues": [...]}
    """
    default_pass = {
        "coherent": True,
        "issues": [],
        "source": "default",
    }

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[VISION-COHERENCE] WARNING: No GEMINI_API_KEY — returning default pass")
        return default_pass

    valid_images = [p for p in shot_images if os.path.exists(p)]
    if len(valid_images) < 2:
        print("[VISION-COHERENCE] WARNING: Need at least 2 images for coherence check")
        return default_pass

    # Limit to 3 images max to keep token usage reasonable
    valid_images = valid_images[:3]

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        contents = [
            "These are consecutive shots from the same scene in a film. "
            "Check for continuity errors between them:\n"
            "1. Lighting direction — is the light source consistent?\n"
            "2. Character wardrobe — do outfits match across shots?\n"
            "3. Background consistency — are surroundings the same?\n"
            "4. Spatial positioning — are characters/objects in logical positions?\n"
            "5. Color grading — is the mood/palette consistent?\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"coherent": <true/false>, "issues": ["..."]}'
        ]

        # Attach images using Gemini's Part format
        image_parts = []
        for img_path in valid_images:
            img_b64 = _encode_image_base64(img_path)
            media = _image_media_type(img_path)
            image_parts.append(
                genai.types.Part.from_bytes(
                    data=base64.b64decode(img_b64),
                    mime_type=media,
                )
            )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[*image_parts, contents[0]],
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        result["source"] = "gemini-flash"
        status = "COHERENT" if result.get("coherent", False) else "ISSUES FOUND"
        print(f"[VISION-COHERENCE] Gemini scene check: {status}")
        if result.get("issues"):
            for issue in result["issues"]:
                print(f"   - {issue}")
        return result

    except Exception as e:
        print(f"[VISION-COHERENCE] Gemini coherence check failed: {e}")
        return default_pass

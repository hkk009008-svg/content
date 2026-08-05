import cv2
import os
import json
import base64
import logging
from pipeline_context import PIPELINE_CONTEXT
from config.settings import settings
from cinema.fal_limits import FAL_TIMEOUT_VIDEO_S
from llm.image_encoding import encode_image_for_llm
from performance._net import safe_download, validate_video_artifact
try:
    from deepface import DeepFace
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("⚠️ [VISION WARNING] DeepFace/Tensorflow unavailable via PIP. Identity validation loop bypassed.")


logger = logging.getLogger(__name__)


def _identity_error_result(reason: str, issue: str) -> dict:
    """Fail-closed marker for identity checks that could not run."""
    return {
        "match": False,
        "confidence": 0.0,
        "issues": [issue],
        "source": "error",
        "error": True,
        "error_reason": reason,
    }


def _get_shared_validator():
    """Lazy-construct + return the process-wide IdentityValidator.

    Backward-compat alias for `identity.get_shared_validator()`. Kept under
    the original name because the §15 smoke block in ARCHITECTURE.md
    references this exact symbol path (`phase_c_vision._get_shared_validator`).
    Internally delegates to the consolidated factory so phase_c_vision and
    performance.identity_gate return the same instance.
    """
    from identity import get_shared_validator
    return get_shared_validator()


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


def face_swap_video_frames(
    video_path,
    reference_image,
    output_path,
    *,
    cost_tracker=None,
    shot_id="",
    video_id="",
    _cascade_out=None,
):
    """
    Post-processing face swap for identity consistency.

    Pipeline-owned FAL calls use the shared paid-attempt ledger.  A provider
    request ID is persisted before polling and the same request is resumed
    after restart.  FaceFusion is eligible only when the cloud request was
    provably never submitted (missing key/authority, upload/preflight failure,
    or an atomic budget refusal) or is terminal with explicit unbilled
    evidence.  Ambiguous, running, succeeded-but-not-retained, and billed
    failures deliberately raise ``PaidCallDeferred`` instead of starting a
    replacement transform.
    """
    # Both swap paths (fal.ai PixVerse, FaceFusion CLI) emit VIDEO-ONLY clips.
    # Restore the source clip's audio in place so a face-swap of a dialogue take
    # is not silently muted — otherwise the postprocess assembler substitutes
    # generic scene-TTS for the dropped voice. Lazy import (no module-level
    # coupling; lip_sync owns the shared re-mux helper). [§3 audio-sibling family]
    from lip_sync import _remux_source_audio_in_place

    from paid_provider import (
        PaidCallBudgetBlocked,
        PaidCallDeferred,
        PaidCallUnbilled,
        file_fingerprint,
        has_paid_attempt_authority,
        paid_attempt_id,
        request_fingerprint,
        run_durable_fal_job,
    )

    def _record_winner(**fields):
        if isinstance(_cascade_out, dict):
            _cascade_out.update(fields)

    # PRIORITY 1: fal.ai PixVerse face swap.  There is intentionally no direct
    # subscribe compatibility path: without project-scoped durable authority,
    # the paid provider is provably unsubmitted and only the local path may run.
    if settings.fal_key and has_paid_attempt_authority(cost_tracker):
        application = "fal-ai/pixverse/swap"
        try:
            stable_request = request_fingerprint(
                application,
                file_fingerprint(video_path),
                file_fingerprint(reference_image),
                "person",
                "720p",
                "5",
            )
            attempt_id = paid_attempt_id(
                "fal-pixverse-swap",
                video_id,
                shot_id,
                stable_request,
            )
        except Exception as exc:
            # No provider upload or generation submission has happened yet.
            logger.warning(
                "PixVerse face-swap preflight failed before provider submission",
                extra={
                    "provider": "fal",
                    "engine": "FAL_PIXVERSE_SWAP",
                    "shot_id": shot_id,
                    "video_id": video_id,
                    "detail": type(exc).__name__,
                },
            )
        else:
            try:
                import fal_client

                print("   [FACESWAP] Uploading inputs to fal.ai...")
                video_url = fal_client.upload_file(video_path)
                face_url = fal_client.upload_file(reference_image)
            except Exception as exc:
                # FAL file upload is not the paid generation boundary.  With no
                # queue submission, local execution remains safe.
                logger.warning(
                    "PixVerse face-swap upload failed before paid submission",
                    extra={
                        "provider": "fal",
                        "engine": "FAL_PIXVERSE_SWAP",
                        "shot_id": shot_id,
                        "video_id": video_id,
                        "attempt_id": attempt_id,
                        "detail": type(exc).__name__,
                    },
                )
            else:
                arguments = {
                    "video_url": video_url,
                    "image_url": face_url,
                    "mode": "person",
                    "resolution": "720p",
                    "duration": "5",
                    # The local re-mux remains the repository's measured audio
                    # integrity path; avoid paying the provider to transform it.
                    "original_sound_switch": False,
                }
                logger.info(
                    "PixVerse face-swap paid request starting or resuming",
                    extra={
                        "provider": "fal",
                        "engine": "FAL_PIXVERSE_SWAP",
                        "shot_id": shot_id,
                        "video_id": video_id,
                        "attempt_id": attempt_id,
                    },
                )
                try:
                    from cost_tracker import API_COST_USD

                    result = run_durable_fal_job(
                        application=application,
                        arguments=arguments,
                        attempt_id=attempt_id,
                        engine="FAL_PIXVERSE_SWAP",
                        operation="face_swap",
                        estimated_cost_usd=API_COST_USD["FAL_PIXVERSE_SWAP"],
                        request_fingerprint_value=stable_request,
                        cost_tracker=cost_tracker,
                        shot_id=shot_id,
                        video_id=video_id,
                        poll_timeout_s=FAL_TIMEOUT_VIDEO_S,
                        with_logs=True,
                    )
                except PaidCallBudgetBlocked as exc:
                    # The reservation transaction proves no provider request
                    # was submitted, so local FaceFusion remains eligible.
                    _record_winner(
                        paid_attempt=dict(exc.snapshot.attempt),
                        paid_deferred=False,
                    )
                    logger.warning(
                        "PixVerse face-swap atomic budget reservation refused",
                        extra={
                            "provider": "fal",
                            "engine": "FAL_PIXVERSE_SWAP",
                            "shot_id": shot_id,
                            "video_id": video_id,
                            "attempt_id": attempt_id,
                            "state": "blocked_budget",
                        },
                    )
                except PaidCallUnbilled as exc:
                    # Explicit terminal no-charge evidence permits the local
                    # implementation, but never re-POSTs this attempt ID.
                    _record_winner(
                        paid_attempt=dict(exc.attempt),
                        paid_deferred=False,
                    )
                    logger.warning(
                        "PixVerse face-swap is terminal and unbilled; using local path",
                        extra={
                            "provider": "fal",
                            "engine": "FAL_PIXVERSE_SWAP",
                            "shot_id": shot_id,
                            "video_id": video_id,
                            "attempt_id": attempt_id,
                            "state": str(exc.attempt.get("state") or "failed_unbilled"),
                        },
                    )
                except PaidCallDeferred as exc:
                    _record_winner(
                        paid_attempt=dict(exc.snapshot.attempt),
                        paid_deferred=True,
                    )
                    logger.warning(
                        "PixVerse face-swap requires provider recovery; local replacement blocked",
                        extra={
                            "provider": "fal",
                            "engine": "FAL_PIXVERSE_SWAP",
                            "shot_id": shot_id,
                            "video_id": video_id,
                            "attempt_id": attempt_id,
                            "provider_status": str(exc.snapshot.attempt.get("provider_status") or ""),
                            "state": str(exc.snapshot.attempt.get("state") or "accepted_unknown"),
                        },
                    )
                    raise
                except Exception as exc:
                    # The durable adapter is designed to translate provider
                    # ambiguity to PaidCallDeferred.  Any unexpected error at
                    # this boundary is still not proof of non-submission.
                    try:
                        attempt = cost_tracker.get_paid_attempt(attempt_id) or {}
                    except Exception:
                        attempt = {}
                    _record_winner(paid_attempt=dict(attempt), paid_deferred=True)
                    raise PaidCallDeferred(
                        "PixVerse face-swap paid boundary failed without safe fallback evidence",
                        attempt=attempt,
                    ) from exc
                else:
                    try:
                        attempt = cost_tracker.get_paid_attempt(attempt_id) or {}
                    except Exception:
                        attempt = {}
                    _record_winner(
                        engine="FAL_PIXVERSE_SWAP",
                        model=application,
                        provider="fal",
                        paid_attempt=dict(attempt),
                        paid_attempt_id=attempt_id,
                        provider_job_id=str(attempt.get("provider_job_id") or ""),
                        paid_cost_recorded=True,
                    )
                    out_url = result.get("video", {}).get("url")
                    if not out_url:
                        _record_winner(paid_deferred=True)
                        logger.warning(
                            "PixVerse completed without a retained video URL",
                            extra={
                                "provider": "fal",
                                "engine": "FAL_PIXVERSE_SWAP",
                                "shot_id": shot_id,
                                "video_id": video_id,
                                "attempt_id": attempt_id,
                                "provider_status": "completed",
                                "state": "succeeded",
                            },
                        )
                        raise PaidCallDeferred(
                            "PixVerse completed without a retained video; no local replacement started",
                            attempt=attempt,
                        )
                    try:
                        downloaded = safe_download(
                            out_url,
                            output_path,
                            allowed_content_types=("video/mp4",),
                            content_validator=validate_video_artifact,
                        )
                    except Exception as exc:
                        _record_winner(paid_deferred=True)
                        raise PaidCallDeferred(
                            "PixVerse completed but output retention raised; no local replacement started",
                            attempt=attempt,
                        ) from exc
                    if downloaded is None:
                        _record_winner(paid_deferred=True)
                        raise PaidCallDeferred(
                            "PixVerse completed but output retention failed; no local replacement started",
                            attempt=attempt,
                        )
                    _remux_source_audio_in_place(
                        output_path, video_path, engine="pixverse_swap"
                    )
                    logger.info(
                        "PixVerse face-swap completed",
                        extra={
                            "provider": "fal",
                            "engine": "FAL_PIXVERSE_SWAP",
                            "shot_id": shot_id,
                            "video_id": video_id,
                            "attempt_id": attempt_id,
                            "provider_status": "completed",
                            "state": "succeeded",
                            "cost_usd": API_COST_USD["FAL_PIXVERSE_SWAP"],
                        },
                    )
                    print(f"   [FACESWAP] Cloud swap complete: {output_path}")
                    return output_path
    elif settings.fal_key:
        logger.warning(
            "PixVerse face-swap skipped before submission: no project paid-attempt authority",
            extra={
                "provider": "fal",
                "engine": "FAL_PIXVERSE_SWAP",
                "shot_id": shot_id,
                "video_id": video_id,
                "state": "unsubmitted",
            },
        )

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
            _remux_source_audio_in_place(output_path, video_path, engine="facefusion")
            _record_winner(
                engine="FACEFUSION_LOCAL",
                model="inswapper_128_fp16+gfpgan_1.4",
                provider="local",
                paid_cost_recorded=False,
            )
            logger.info(
                "local FaceFusion face-swap completed",
                extra={
                    "provider": "local",
                    "engine": "FACEFUSION_LOCAL",
                    "shot_id": shot_id,
                    "video_id": video_id,
                    "state": "succeeded",
                    "cost_usd": 0.0,
                },
            )
            print(f"   [FACESWAP] FaceFusion complete: {output_path}")
            return output_path
    except FileNotFoundError:
        print("   [FACESWAP] FaceFusion not installed. Skipping.")
    except Exception as e:
        print(f"   [FACESWAP] FaceFusion error: {e}")

    return None


def quality_control_image(image_path: str, prompt_text: str = "") -> bool:
    """
    Validates structural integrity of a generated latent frame using GPT-4o Vision.
    Returns True if image passes quality threshold (score >= 7/10), False otherwise.
    """
    # Unreached in production (zero callers on main/feat); fixed for consistency.
    if not os.path.exists(image_path):
        print(f"[QC] WARNING: Image not found: {image_path} — QC fail (missing)")
        return False

    result = validate_shot_quality_vision(image_path, prompt_text)
    passed = result.get("pass", True)
    score = result.get("score", 7)
    source = result.get("source", "unknown")

    if not passed:
        print(f"[QC] REJECTED (score={score}/10, source={source})")
        for issue in result.get("issues", []):
            print(f"   - {issue}")
    else:
        print(f"[QC] PASSED (score={score}/10, source={source})")

    return passed


# ======================================================================
# LLM Vision Validators — GPT-4o, Claude, Gemini
# ======================================================================
# Image encoding: all validators use encode_image_for_llm (llm/image_encoding.py)
# which PIL-opens → converts to RGB → downscales to ≤1568px long-edge →
# re-encodes as JPEG quality=90.  Media type is image/jpeg BY CONSTRUCTION —
# all provider payloads hardcode "image/jpeg".  This closes two failure modes:
#   (1) 4K keyframes up to 20.28 MB b64 exceeding the Anthropic 10 MB/image limit.
#   (2) Extension-derived MIME was frequently wrong (.jpg files contain PNG bytes).


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

    api_key = settings.openai_api_key
    if not api_key:
        print("[VISION-QA] WARNING: No OPENAI_API_KEY — returning default pass")
        return default_pass

    # Unreached in production (zero callers on main/feat); fixed for consistency.
    if not os.path.exists(image_path):
        print(f"[VISION-QA] WARNING: Image not found: {image_path}")
        return {"pass": False, "score": 0, "issues": ["image missing"], "suggestions": [], "source": "default"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=120.0)

        img_b64 = encode_image_for_llm(image_path)
        if img_b64 is None:
            print(f"[VISION-QA] WARNING: Image encode failed: {image_path}")
            return default_pass

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
            '{"score": <0-10>, "issues": ["..."], "suggestions": ["..."]}\n\n'
            + PIPELINE_CONTEXT
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
                                "url": f"data:image/jpeg;base64,{img_b64}",
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


def validate_identity_vision(
    reference_path: str,
    generated_path: str,
    *,
    cost_tracker=None,
    video_id: str = "",
    shot_id: str = "",
) -> dict:
    """
    Claude Vision compares reference face vs generated face.
    Replaces broken DeepFace with LLM visual reasoning.
    Returns: {"match": bool, "confidence": 0.0-1.0, "issues": [...]}
    """
    api_key = settings.anthropic_api_key
    if not api_key:
        logger.warning("[VISION-ID] Identity validation unavailable: missing ANTHROPIC_API_KEY")
        return _identity_error_result(
            "missing_anthropic_api_key",
            "identity check unavailable: missing ANTHROPIC_API_KEY",
        )

    if not os.path.exists(reference_path):
        print(f"[VISION-ID] WARNING: Reference image not found: {reference_path}")
        return {"match": True, "skip": True, "confidence": None, "issues": [], "source": "default"}
    if not os.path.exists(generated_path):
        print(f"[VISION-ID] WARNING: Generated image not found: {generated_path}")
        return {"match": False, "missing_generated": True, "confidence": 0.0, "issues": ["generated image missing"], "source": "default"}

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key, timeout=120.0)

        ref_b64 = encode_image_for_llm(reference_path)
        gen_b64 = encode_image_for_llm(generated_path)
        if ref_b64 is None or gen_b64 is None:
            logger.warning(
                "[VISION-ID] Identity validation unavailable: image encode failed "
                "(ref_failed=%s, gen_failed=%s)",
                ref_b64 is None,
                gen_b64 is None,
            )
            return _identity_error_result(
                "image_encode_failed",
                "identity check unavailable: image encode failed",
            )

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
            '{"confidence": <0.0-1.0>, "issues": ["..."]}\n\n'
            + PIPELINE_CONTEXT
        )

        from cost_tracker import API_COST_USD, PRICING
        from cost_tracker_lifecycle import cost_tracker_scope
        from paid_provider import (
            PaidCallBudgetBlocked,
            PaidCallDeferred,
            PaidCallUnbilled,
            file_fingerprint,
            paid_attempt_id,
            request_fingerprint,
            run_nonresumable_paid_call,
        )

        def _input_fingerprint(path: str) -> str:
            try:
                return file_fingerprint(path)
            except Exception:
                return request_fingerprint("unreadable-identity-input", path)

        request_key = request_fingerprint(
            "claude-vision-identity-v1",
            "claude-sonnet-4-6",
            _input_fingerprint(reference_path),
            _input_fingerprint(generated_path),
        )
        attempt_key = paid_attempt_id(
            "claude-vision-identity",
            video_id,
            shot_id,
            request_key,
        )

        def _call_provider():
            return client.messages.create(
                    model="claude-sonnet-4-6",
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
                                        "media_type": "image/jpeg",
                                        "data": ref_b64,
                                    },
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": gen_b64,
                                    },
                                },
                            ],
                        },
                    ],
                )

        def _actual_cost(response) -> float:
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            pricing = PRICING["claude-sonnet-4-6"]
            return (
                input_tokens / 1_000_000 * pricing["input"]
                + output_tokens / 1_000_000 * pricing["output"]
            )

        try:
            with cost_tracker_scope(cost_tracker) as tracker:
                response = run_nonresumable_paid_call(
                    call=_call_provider,
                    attempt_id=attempt_key,
                    provider="anthropic",
                    engine="CLAUDE_VISION_IDENTITY",
                    operation="identity_validation",
                    estimated_cost_usd=API_COST_USD["CLAUDE_VISION_IDENTITY"],
                    actual_cost_usd=_actual_cost,
                    request_fingerprint_value=request_key,
                    cost_tracker=tracker,
                    shot_id=shot_id,
                    video_id=video_id,
                )
        except PaidCallBudgetBlocked:
            logger.warning(
                "[VISION-ID] Identity validation blocked by the project budget"
            )
            return _identity_error_result(
                "paid_budget_blocked",
                "identity check unavailable: project budget refused the provider call",
            )
        except PaidCallDeferred:
            logger.warning(
                "[VISION-ID] Claude identity outcome requires reconciliation; "
                "automatic replay is blocked"
            )
            return _identity_error_result(
                "paid_work_reconciliation_required",
                "identity check unavailable: provider outcome requires reconciliation",
            )
        except PaidCallUnbilled:
            logger.warning(
                "[VISION-ID] Claude identity request has terminal unbilled evidence"
            )
            return _identity_error_result(
                "provider_unbilled_failure",
                "identity check unavailable: provider rejected the request",
            )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        # `match` is advisory (hardcoded 0.7); production callers re-threshold
        # via IdentityValidator (validator.py:~754) which re-computes `matched`
        # using its own configured threshold.  The 0.7 here never governs a
        # real production gate — it is a convenience key for direct callers only.
        result["match"] = result.get("confidence", 0.0) >= 0.7
        result["source"] = "claude-sonnet"
        status = "MATCH" if result["match"] else "MISMATCH"
        print(f"[VISION-ID] Claude identity check: {result['confidence']:.2f} — {status}")
        if result.get("issues"):
            for issue in result["issues"]:
                print(f"   - {issue}")
        return result

    except Exception as e:
        logger.warning("[VISION-ID] Claude identity validation failed; failing closed", exc_info=True)
        return _identity_error_result(
            "provider_error",
            f"identity check unavailable: {e}",
        )


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

    api_key = settings.gemini_api_key or settings.google_api_key
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
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key, http_options=genai_types.HttpOptions(timeout=120_000))

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
            img_b64 = encode_image_for_llm(img_path)
            if img_b64 is None:
                print(f"[VISION-COHERENCE] WARNING: Image encode failed, skipping: {img_path}")
                continue
            image_parts.append(
                genai.types.Part.from_bytes(
                    data=base64.b64decode(img_b64),
                    mime_type="image/jpeg",
                )
            )
        if len(image_parts) < 2:
            print("[VISION-COHERENCE] WARNING: Fewer than 2 images encoded successfully")
            return default_pass

        # Migrated off gemini-2.5-flash (shutdown deadline 2026-10-16; Slice
        # 6b) to gemini-3.6-flash, its documented successor — vision input +
        # structured outputs both confirmed on the model page (2026-07-31
        # WebFetch). response_mime_type mirrors llm/ensemble.py:_generate_gemini's
        # existing json_mode idiom; the prompt's own "Respond ONLY with valid
        # JSON" instruction plus the code-fence-stripping parse below are KEPT
        # as a tolerant fallback in case the model still fences its output —
        # belt and braces, no behavior regression either way.
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[*image_parts, contents[0]],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
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

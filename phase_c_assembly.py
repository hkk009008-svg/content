import os
import json
import math
import time

from typing import NamedTuple

from config.settings import settings
from cinema.aspect import portrait_swap, fal_image_size, fal_aspect_ratio, DEFAULT_ASPECT_RATIO
from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from cinema.context import get_project_setting
from comfyui_client import (
    ComfyUIJobError,
    ComfyUIJobStateUnknown,
    ComfyUISubmitUnknown,
    ComfyUITimeout,
    RunPodComfyUI,
)
from performance._net import safe_download, validate_image_artifact


class ImageGenResult(NamedTuple):
    """Provenance-carrying result of an image-generation backend.

    ``path`` is the saved image (equals ``output_filename`` on success);
    ``api_name`` is the cost_tracker API key for the backend that ACTUALLY ran
    (``GEMINI_IMAGE`` | ``COMFYUI_PULID`` | ``FLUX_KONTEXT`` | ``FLUX_PRO`` |
    ``FLUX_SCHNELL`` | ``POLLINATIONS``; ``QUALITY_MAX`` was retired WS1 Task 4
    along with quality_max.py). Callers record ``api_name`` so cost_log reflects where the
    image was really generated (pod vs FAL), not a tier-based guess. Backends
    return ``None`` (not this type) on failure, so the caller's ``if not
    result`` success guard is preserved (a populated NamedTuple is always
    truthy regardless of field count).

    ``billed_rejects`` (WS3 money-loss close-out, mirrors
    ``cinema/shots/controller.py::_record_billed_rejects`` on the video side):
    engines that BILLED for a real generation this call incurred but did NOT
    win (currently only ``"GEMINI_IMAGE"`` — Nano Banana 2 bills on generation,
    independent of the later identity check). Defaults to ``()`` so existing
    2-positional-arg construction (``ImageGenResult(path, api_name)``) stays
    valid. The caller (``cinema/shots/controller.py``) records each entry
    against cost_tracker with ``operation="image_generation_rejected"`` next
    to the winner-keyed ``keyframe_generation`` record.
    """

    path: str
    api_name: str
    billed_rejects: tuple = ()


def _download_generated_jpeg(url: str, output_filename: str):
    """Publish only a bounded, MIME-true, decodable JPEG provider output."""
    return safe_download(
        url,
        output_filename,
        max_bytes=64 * 1024 * 1024,
        allowed_content_types=("image/jpeg",),
        content_validator=lambda path: validate_image_artifact(
            path,
            expected_formats=("JPEG",),
        ),
    )


def _resolve_ui_denoise(ctx):
    """Resolve a standard-tier img2img_denoise override from continuity_options,
    finite-guarded and clamped to [0.2, 0.6]. Returns None — "keep the caller's
    denoise default" — for an absent / non-dict / non-numeric / non-finite value.

    A bare NaN survives project.json (json.load allow_nan=True); a raw
    max(0.2, min(0.6, nan)) clamp-lucks to 0.6, silently overriding the caller. The
    math.isfinite guard skips it instead. Mirrors bf1034a's same-knob guard in
    workflow_selector (formerly also quality_max._clamp_img2img_denoise's
    reject-non-finite policy + its isinstance(continuity_options, dict) check,
    before that module was retired WS1 Task 4). Extracted (vs inline)
    so the gate is unit-testable — drop math.isfinite and the nan test goes red."""
    if ctx is None:
        return None
    gs = ctx.global_settings or {}
    co = gs.get("continuity_options") if isinstance(gs, dict) else None
    raw = co.get("img2img_denoise") if isinstance(co, dict) else None
    if not isinstance(raw, (int, float)) or not math.isfinite(raw):
        return None
    return max(0.2, min(0.6, float(raw)))


def generate_ai_broll(prompt, output_filename, seed=None, character_image=None,
                       init_image=None, denoise_strength=1.0, characters=None,
                       multi_angle_refs=None, identity_anchor="",
                       pulid_weight_override=None, negative_prompt="",
                       quality_tier="production",
                       # char_lora_path/strength/trigger, style_reference, shot_hint:
                       # reserved — dormant, kept for a possible future FLUX.2 A/B (a
                       # separate, deferred track — NOT WS3, which shipped Nano Banana 2
                       # / gemini_multiref instead and binds identity via reference
                       # images, not LoRA). Threaded from the controller
                       # (cinema/shots/controller.py) but unconsumed now that the
                       # max-tier dispatch below is gone — WS1 retired
                       # quality_tier=="max" (ADR-024: the max graph over-cooks
                       # structurally; production/pulid.json is the validated survivor).
                       # Kept, not dead code. (secondary_char_refs stays LIVE below — it
                       # still feeds the FAL Kontext multi-char fallback, unrelated to
                       # the deleted max dispatch.)
                       char_lora_path=None,
                       char_lora_strength=None,
                       char_lora_trigger=None,
                       secondary_char_refs=None,
                       style_reference=None, shot_hint=None, ctx=None,
                       _recovery_out=None):
    """
    Generates a cinematic image with face-identity preservation.

    Priority chain (production — the only tier since WS1's max-tier retirement):
    0. Gemini 3.1 Flash Image (Nano Banana 2) — PRIMARY for all projects (WS3,
       user-confirmed); set identity_backend='pod' to opt OUT.
    1. ComfyUI + PuLID (pod) — arc-gate fallback
    2. FLUX Kontext
    3. FLUX-Pro
    4. FLUX-Schnell
    5. Pollinations

    Args:
        prompt: Image generation prompt (enhanced by continuity engine)
        output_filename: Output path for generated image
        seed: Deterministic seed for consistency
        character_image: Primary character reference for face identity
        init_image: Previous shot image for img2img temporal chaining
        denoise_strength: 0.0-1.0, lower = more similar to init_image
        characters: List of character config dicts
        quality_tier: informational only (WS1 retired the "max" fork below —
            pulid.json/ComfyUI production is now the only pipeline).
        char_lora_path: reserved — dormant, kept for a possible future FLUX.2
            A/B (separate, deferred track — not WS3).
        char_lora_trigger: reserved — dormant, kept for a possible future
            FLUX.2 A/B (separate, deferred track — not WS3).
        secondary_char_refs: P1-1 slice 1: additional character entries forwarded
            to _fal_flux_fallback; each entry has char_id, reference, multi_angle_refs,
            identity_anchor. None / [] takes the single-char (golden) path.
        style_reference: reserved — dormant, kept for a possible future FLUX.2
            A/B (separate, deferred track — not WS3).
        shot_hint: reserved — dormant, kept for a possible future FLUX.2 A/B
            (separate, deferred track — not WS3).

    Returns:
        ImageGenResult(path, api_name, billed_rejects) naming the backend
        that actually ran (GEMINI_IMAGE | COMFYUI_PULID | FLUX_KONTEXT |
        FLUX_PRO | FLUX_SCHNELL | POLLINATIONS), or None if every backend
        failed. Callers record ``api_name`` for cost attribution so a pod
        generation is distinguishable from a FAL fallback (and both from a
        Gemini-native generation) in cost_log. ``billed_rejects`` names any
        engine that billed for a generation this call incurred but did NOT
        win (WS3: a Gemini bill-but-identity-reject before falling through) —
        callers must record these too or the spend is invisible to the
        budget gate.
    """

    mode = "img2img" if init_image else "txt2img"

    # Read per-project aspect ratio early — must be in scope at ALL six
    # _fal_flux_fallback call sites (including early-return and except paths).
    # Phase 2: portrait-aware latent dimensions + FAL/Pollinations orientation.
    # get_project_setting is a safe dict lookup with a default (never raises,
    # handles ctx=None), so it is safe to call here outside the try block.
    aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)

    # WS3 money-loss close-out (mirrors cinema/shots/controller.py's
    # _record_billed_rejects on the video side): Gemini can BILL a real
    # image (Nano Banana 2, $0.067) that then fails identity and falls through
    # to the pod/FAL cascade below — a billed engine that never becomes the
    # winner. Track it here and thread it onto whichever ImageGenResult this
    # call finally returns, so the caller's cost_tracker sees the spend even
    # though Gemini didn't win. Only the PRIORITY-0 block below appends to
    # this list; the Gemini SUCCESS return just below keeps it empty (there
    # is nothing to fall through from).
    billed_rejects = []

    def _with_rejects(result):
        """Hand accumulated billed rejects to the caller on every outcome.

        A winner carries them on ``ImageGenResult``.  If every fallback
        fails, use the private recovery handoff so the controller can still
        record already-incurred spend before returning the ordinary failure.
        """
        if result is not None and billed_rejects:
            return result._replace(billed_rejects=tuple(billed_rejects))
        if result is None and billed_rejects and isinstance(_recovery_out, dict):
            _recovery_out["_billed_rejects"] = tuple(billed_rejects)
        return result

    # ----- PRIORITY 0: Gemini 3.1 Flash Image (Nano Banana 2, WS3) -----
    # Google-first overhaul: Nano Banana 2 is the image PRIMARY for all
    # projects (WS3, user-confirmed decision — "Nano Banana as image
    # PRIMARY, pod demoted to first fallback"); a project sets
    # identity_backend='pod' to opt OUT. The pod remains the arc-gate
    # fallback below. This block NEVER raises and NEVER returns None — a
    # missing key, a generation failure, or a failed identity check all
    # fall through into the existing PRIORITY-1 pod logic below untouched
    # (silent-gate-degradation discipline: fall through loudly via prints,
    # not silently).
    identity_backend = get_project_setting(ctx, "identity_backend", "gemini_multiref")
    if (
        (settings.google_api_key or settings.gemini_api_key)
        and character_image
        and os.path.exists(character_image)
        and identity_backend != "pod"
    ):
        try:
            from gemini_image_native import GeminiImageAPI
            gemini_secondary_refs = [
                sc.get("reference") for sc in (secondary_char_refs or []) if sc.get("reference")
            ]
            gemini_path = GeminiImageAPI().generate_image(
                prompt,
                output_filename,
                character_image=character_image,
                multi_angle_refs=multi_angle_refs,
                secondary_char_refs=gemini_secondary_refs,
                aspect_ratio=aspect_ratio,
                negative_prompt=negative_prompt,
            )
            if gemini_path:
                # A successful generation crosses Google's billing boundary.
                # Record that spend before any local validation work because
                # the validator can reject *or raise* after the provider has
                # already charged for the frame.  A passing Gemini result
                # returns directly below, so this local reject ledger is only
                # threaded onto a later fallback winner.
                billed_rejects.append("GEMINI_IMAGE")
                from phase_c_vision import _get_shared_validator
                _chars_in_frame = (shot_hint or {}).get("characters_in_frame") or []
                id_result = _get_shared_validator().validate_image(
                    gemini_path, character_image,
                    character_id=_chars_in_frame[0] if _chars_in_frame else "",
                    threshold=get_project_setting(ctx, "identity_strictness", None),
                )
                if id_result.passed:
                    print(f"   [PHASE C] Gemini 3.1 Flash Image (Nano Banana 2) passed identity "
                          f"check (score={id_result.overall_score}): '{prompt[:60]}...'")
                    return ImageGenResult(output_filename, "GEMINI_IMAGE")
                print(f"   [GEMINI-IMAGE] Identity check failed (score={id_result.overall_score}); "
                      f"falling back to the pod/FAL cascade")
                try:
                    os.makedirs("logs", exist_ok=True)
                    with open("logs/gemini_image_arc_comparison.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": time.time(),
                            "prompt": prompt[:200],
                            "output_filename": output_filename,
                            "character_image": character_image,
                            "characters_in_frame": _chars_in_frame,
                            "gemini_score": id_result.overall_score,
                            "threshold": id_result.threshold_used,
                        }) + "\n")
                except Exception:
                    pass  # comparison log is best-effort telemetry, never load-bearing
            else:
                print("   [GEMINI-IMAGE] Generation returned no image; falling back to the pod/FAL cascade")
        except Exception as e:
            print(f"   [GEMINI-IMAGE] PRIORITY-0 block failed ({e}); falling back to the pod/FAL cascade")

    # ----- Backend selection (PRIORITY order) -----
    # The previous implementation relied on a confusing if/elif/else where
    # only branch #1 fell through to the ComfyUI path below, and the
    # downstream `if not server_url` check was dead code (the else-branch
    # had already returned). Rewriting with explicit early-returns so the
    # control flow is self-evident.
    server_url = settings.comfyui_server_url

    # PRIORITY 2 / 3: ComfyUI is unavailable — route to FLUX fallback.
    # (Same args as the old elif/else, consolidated.)
    if not (server_url and os.path.exists("pulid.json")):
        if character_image and os.path.exists(character_image) and settings.fal_key:
            return _with_rejects(_fal_flux_fallback(
                prompt, output_filename, seed,
                character_image=character_image,
                multi_angle_refs=multi_angle_refs,
                identity_anchor=identity_anchor,
                aspect_ratio=aspect_ratio,
                secondary_char_refs=secondary_char_refs,
            ))
        return _with_rejects(_fal_flux_fallback(
            prompt, output_filename, seed,
            character_image=character_image,
            aspect_ratio=aspect_ratio,
            secondary_char_refs=None,
        ))

    # PRIORITY 1: ComfyUI + PuLID on RunPod RTX 4090 (fastest + strongest face-lock)
    print(f"   [PHASE C] Generating [{mode}] via ComfyUI PuLID (RTX 4090): '{prompt[:60]}...'")

    prompt_id = None
    try:
        if not os.path.exists("pulid.json"):
            print("   [WARN] pulid.json missing — using Kontext fallback")
            return _with_rejects(_fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                      aspect_ratio=aspect_ratio, secondary_char_refs=None))

        with open("pulid.json", "r") as f:
            workflow = json.load(f)

        # WORKFLOW SELECTOR — apply shot-type-specific parameters
        try:
            from workflow_selector import classify_shot_type, get_workflow_params, apply_workflow_params
            # Build a minimal shot dict for classification
            shot_info = {"prompt": prompt, "characters_in_frame": ["char"] if character_image else []}
            shot_type = classify_shot_type(shot_info)
            wf_params = get_workflow_params(shot_type, settings=ctx.global_settings if ctx else None)
            workflow = apply_workflow_params(workflow, wf_params)

            # Apply adaptive PuLID weight override from continuity engine feedback loop
            if pulid_weight_override is not None and "100" in workflow:
                workflow["100"]["inputs"]["weight"] = pulid_weight_override
                print(f"   [WORKFLOW] {shot_type}: PuLID={pulid_weight_override:.2f} (adaptive), CFG={wf_params['guidance']}, steps={wf_params['steps']}")
            else:
                print(f"   [WORKFLOW] {shot_type}: PuLID={wf_params['pulid_weight']}, CFG={wf_params['guidance']}, steps={wf_params['steps']}")

            # Skip ComfyUI entirely for landscape shots (no face-lock needed)
            if shot_type == "landscape" and character_image:
                print(f"   [WORKFLOW] Landscape detected — skipping PuLID, using Kontext")
                return _with_rejects(_fal_flux_fallback(prompt, output_filename, seed, character_image=None,
                                          aspect_ratio=aspect_ratio, secondary_char_refs=None))
        except ImportError:
            pass  # workflow_selector not available — use defaults

        comfy = RunPodComfyUI(
            server_url,
            auth_token=settings.comfyui_api_key,
        )

        # 1. Inject LLM Text prompt to CLIP node "122"
        workflow["122"]["inputs"]["text"] = prompt

        # 2. Aspect ratio — native latent dims via EmptyLatentImage node "102"
        #    portrait_swap transposes 1344×768 → 768×1344 when aspect_ratio=9:16;
        #    landscape / unknown → unchanged. Phase 2 (portrait keyframe support).
        _w, _h = portrait_swap(1344, 768, aspect_ratio)
        workflow["102"]["inputs"]["width"] = _w
        workflow["102"]["inputs"]["height"] = _h
        workflow["102"]["inputs"]["batch_size"] = 1

        # Keep the final ImageScale orientation aligned with the latent canvas.
        # pulid.json stores the landscape default; portrait projects transpose it
        # with the same single-source helper used for node 102 above.
        _delivery_w, _delivery_h = portrait_swap(2688, 1536, aspect_ratio)
        workflow["502"]["inputs"]["width"] = _delivery_w
        workflow["502"]["inputs"]["height"] = _delivery_h

        # 3. Seed control via RandomNoise node "25"
        if seed is not None:
             workflow["25"]["inputs"]["noise_seed"] = seed

        # 4. Primary character face-lock via PuLID LoadImage node "93"
        if character_image and os.path.exists(character_image):
            remote_face_filename = comfy.upload_image(character_image)
            workflow["93"]["inputs"]["image"] = remote_face_filename
            print(f"      ↳ PuLID face-locked to: {os.path.basename(character_image)}")
        else:
            # No character image — strip ALL PuLID nodes so ComfyUI doesn't validate them
            # Rewire: FreeU takes model directly from UNETLoader (skip PuLID)
            print("   ↳ No character — bypassing PuLID, pure txt2img mode")
            for nid in ["93", "97", "99", "100", "101"]:
                workflow.pop(nid, None)
            # Rewire PAG to take model from UNETLoader directly (node 112), skipping PuLID
            if "301" in workflow:
                workflow["301"]["inputs"]["model"] = ["112", 0]

        # 5. IMG2IMG MODE: Temporal consistency via init image.
        # Keep this path limited to the provisioned, FLUX-compatible
        # LoadImage -> VAEEncode graph. The former dynamic SD1.5 ControlNet and
        # IP-Adapter nodes were not valid members of this production workflow.
        # Injects a VAEEncode node to convert init image → latent, replacing EmptyLatentImage
        if init_image and os.path.exists(init_image):
            remote_init = comfy.upload_image(init_image)

            # Add a LoadImage node for the init image (node "200")
            workflow["200"] = {
                "inputs": {"image": remote_init},
                "class_type": "LoadImage",
                "_meta": {"title": "Load Init Image (img2img)"}
            }

            # Add a VAEEncode node (node "201") to convert init image → latent
            workflow["201"] = {
                "inputs": {
                    "pixels": ["200", 0],
                    "vae": ["10", 0]  # Same VAE as the decode path (node 10)
                },
                "class_type": "VAEEncode",
                "_meta": {"title": "VAE Encode Init (img2img)"}
            }

            # Rewire: SamplerCustomAdvanced (node 13) now takes latent from VAEEncode
            # instead of EmptyLatentImage (node 102)
            workflow["13"]["inputs"]["latent_image"] = ["201", 0]

            # Set denoise strength in BasicScheduler (node 17).
            # img2img_denoise from global_settings.continuity_options overrides the
            # caller-supplied denoise_strength when present (slider: min 0.2, max 0.6).
            _ui_denoise = _resolve_ui_denoise(ctx)
            effective_denoise = _ui_denoise if _ui_denoise is not None else denoise_strength
            workflow["17"]["inputs"]["denoise"] = effective_denoise
            print(f"      ↳ img2img mode: denoise={effective_denoise:.2f} from {os.path.basename(init_image)}")
        else:
            # Full text-to-image: EmptyLatentImage feeds sampler (default workflow)
            workflow["13"]["inputs"]["latent_image"] = ["102", 0]
            if "17" in workflow:
                workflow["17"]["inputs"]["denoise"] = 1.0

        # FACE REFINEMENT removed. PuLID face-locking provides sufficient identity
        # for the current pipeline; FAL PixVerse swap handles any post-video refinement
        # (see phase_c_vision.face_swap_video_frames).

        # 6. Fire Master Execution Workflow
        prompt_id = comfy.queue_prompt(workflow)
        print(f"      ↳ ComfyUI Task {prompt_id} queued. Awaiting GPU computation...")

        # 7. WebSocket job events with bounded /history fallback.  Terminal
        # execution_error/interrupted events fail immediately; a timeout enters
        # fallback only after ID-scoped cancellation is positively confirmed.
        try:
            history = comfy.wait_for_completion(prompt_id)
        except KeyboardInterrupt:
            try:
                comfy.cancel_prompt(prompt_id)
            except Exception as cancel_error:
                print(f"      ↳ ComfyUI cancellation failed: {cancel_error}")
            raise
        except ComfyUIJobError:
            # Explicit terminal execution failure: no live job remains, so the
            # normal image cascade may safely continue.
            raise
        except ComfyUITimeout:
            # wait_for_completion raises this type only after ID-scoped
            # cancellation was positively confirmed. Do not cancel twice.
            raise
        except Exception as monitor_error:
            # A known prompt must not be abandoned while the cascade starts a
            # replacement render. Continue only after cancellation is confirmed.
            try:
                cancelled = comfy.cancel_prompt(prompt_id)
            except Exception as cancel_error:
                raise ComfyUIJobStateUnknown(
                    f"ComfyUI monitoring failed ({monitor_error}); cancellation "
                    f"could not be confirmed ({cancel_error})"
                ) from monitor_error
            if not cancelled:
                raise ComfyUIJobStateUnknown(
                    f"ComfyUI monitoring failed ({monitor_error}); prompt/output "
                    "state remains UNKNOWN"
                ) from monitor_error
            raise
        record = history.get(prompt_id, {})
        outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
        if isinstance(outputs, dict):
            for node_output in outputs.values():
                images = node_output.get("images") if isinstance(node_output, dict) else None
                if not isinstance(images, list) or not images:
                    continue
                img_info = images[0]
                if not isinstance(img_info, dict):
                    continue
                comfy.download_image(
                    img_info.get("filename"),
                    img_info.get("subfolder", ""),
                    img_info.get("type", "output"),
                    output_filename,
                    expected_dimensions=(_delivery_w, _delivery_h),
                )
                print(f"      ✅ Downloaded {mode} render: {output_filename}")
                return _with_rejects(ImageGenResult(output_filename, "COMFYUI_PULID"))

        print("      ⚠️ ComfyUI task completed but produced no valid image output")

        print("   [WARN] ComfyUI timed out or crashed. Falling back to FAL FLUX...")
        return _with_rejects(_fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                  aspect_ratio=aspect_ratio, secondary_char_refs=None))

    except (ComfyUISubmitUnknown, ComfyUIJobStateUnknown) as e:
        # A lost acknowledgement or unconfirmed cancellation may leave a valid
        # ComfyUI render in flight or recoverable. Starting FAL here would
        # duplicate work/spend, so fail closed for operator recovery.
        if isinstance(_recovery_out, dict):
            _recovery_out.clear()
            _recovery_out.update({
                "engine": "COMFYUI_PULID",
                "status": "recovery_required",
                "provider_status": (
                    "submission_unknown"
                    if isinstance(e, ComfyUISubmitUnknown)
                    else "job_state_unknown"
                ),
                "reason": (
                    "ComfyUI may still have accepted or completed this keyframe. "
                    "Reconcile its queue and history before allowing another render."
                ),
            })
            if isinstance(prompt_id, str) and prompt_id:
                _recovery_out["job_id"] = prompt_id
            if billed_rejects:
                # Internal-only accounting handoff. The controller removes
                # this before persisting the public recovery descriptor.
                _recovery_out["_billed_rejects"] = tuple(billed_rejects)
        print(f"   [UNKNOWN] ComfyUI job state: {e}. Refusing duplicate fallback.")
        return None
    except Exception as e:
        print(f"   [WARN] ComfyUI error: {e}. Falling back to FAL FLUX...")
        return _with_rejects(_fal_flux_fallback(prompt, output_filename, seed, character_image=character_image,
                                  aspect_ratio=aspect_ratio, secondary_char_refs=None))


def _parse_structured_prompt(prompt: str) -> dict:
    """
    Parse a structured prompt with [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections.
    Returns dict with extracted sections. Falls back to full prompt if not structured.
    """
    import re
    sections = {}
    for tag in ["SHOT", "SCENE", "ACTION", "OUTFIT", "QUALITY"]:
        match = re.search(rf'\[{tag}\]\s*(.+?)(?=\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\]|$)', prompt, re.DOTALL)
        if match:
            sections[tag] = match.group(1).strip()

    # If no sections found, treat entire prompt as scene description
    if not sections:
        sections["SCENE"] = prompt
    return sections


def _allocate_ref_slots(primary_refs, secondary_chars, cap=6):
    """Partition the Kontext image_urls budget across characters (P1-1 spec §3a).

    FIXED shares, CONTIGUOUS slots: primary takes up to 3 (up to `cap` when no
    secondaries); the first secondary up to 2 (canonical first, then angles);
    the second secondary up to 1. The cap is a ceiling, not a quota — thin
    secondaries leave it unfilled rather than reordering slots (the primary's
    @ImageN indices must stay 1..k). Returns (ordered file paths, slot_map)
    with 1-based @ImageN indices per char_id ('primary' for the primary).
    """
    n_secondary = len(secondary_chars)
    primary_take = min(len(primary_refs), 3 if n_secondary else cap)
    paths = list(primary_refs[:primary_take])
    slot_map = {"primary": list(range(1, len(paths) + 1))}
    for i, entry in enumerate(secondary_chars):
        share = 2 if i == 0 else 1
        char_paths = ([entry["reference"]]
                      + list(entry.get("multi_angle_refs") or []))[:share]
        start = len(paths) + 1
        paths.extend(char_paths)
        slot_map[entry["char_id"]] = list(range(start, start + len(char_paths)))
    return paths, slot_map


def _build_multichar_kontext_prompt(sections, char_blocks):
    """Per-character @ImageN PRESERVE blocks + shared scene/constraints/quality.

    char_blocks: [(first_slot_index, identity_anchor), ...] — one per character,
    primary first. Single-char shots NEVER reach this function (early return in
    _fal_flux_fallback keeps the golden-snapshot path untouched).
    """
    scene_desc = sections.get("SCENE", "")
    action_desc = sections.get("ACTION", "facing the camera")
    outfit_desc = sections.get("OUTFIT", "")
    shot_desc = sections.get("SHOT", "Medium shot, 85mm lens")

    parts = []
    for slot, anchor in char_blocks:
        who = anchor or "the person in this reference"
        parts.append(
            f"PRESERVE IDENTITY: The person from @Image{slot} is {who}. "
            f"Keep this EXACT face, hair, glasses, eye color, skin tone unchanged."
        )
    parts.append(f"CHANGE BACKGROUND: {scene_desc}.")
    if outfit_desc:
        parts.append(f"CHANGE OUTFIT: {outfit_desc}.")
    parts.append(f"SET POSE: {action_desc}.")
    parts.append(f"SET CAMERA: {shot_desc}.")
    tokens = ", ".join(f"@Image{slot}" for slot, _ in char_blocks)
    parts.append(
        f"CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
        f"Do NOT generate a different person. Do NOT blend or average the faces. "
        f"Do NOT transfer clothing between people — each person keeps their own "
        f"outfit. "
        f"Each output face MUST match its own reference ({tokens}) exactly."
    )
    parts.append(
        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
        "shallow depth of field with circular bokeh, natural film grain ISO 400, "
        "volumetric atmospheric lighting, micro-detail in fabric texture, "
        "no AI artifacts, no smooth plastic skin, no over-saturated colors."
    )
    return " ".join(parts)


def _fal_flux_fallback(prompt, output_filename, seed=None, character_image=None,
                       multi_angle_refs=None, identity_anchor="", aspect_ratio=None,
                       secondary_char_refs=None):
    """
    Image generator using FAL.ai FLUX Kontext Max Multi for identity preservation.

    v4 strategy — structured prompt parsing:
    - Parse [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections from prompt
    - Build Kontext prompt: identity anchor FIRST, then scene + outfit changes only
    - NEVER pass raw character descriptions to Kontext (they compete with face ref)
    - Use Kontext Max Multi with up to 9 reference images (AuraFace embeddings)
    """
    fal_key = settings.fal_key
    if not fal_key:
        print("   [FAIL] FAL_KEY missing. No image generation available.")
        return None

    try:
        import fal_client

        # PRIORITY 1: FLUX Kontext Max Multi (strongest identity — up to 9 refs)
        if character_image and os.path.exists(character_image):
            try:
                if secondary_char_refs:
                    # P1-1 multi-char branch (S1-gated). Existence-filter refs the
                    # same way the single-char path does, upload, allocate slots
                    # over the SURVIVORS, address each character by its first slot.
                    primary_refs = [r for r in (multi_angle_refs or []) if os.path.exists(r)] \
                        or [character_image]
                    live_secondaries = [
                        e for e in secondary_char_refs if os.path.exists(e["reference"])
                    ]
                    # Upload BEFORE allocating slots: a silent mid-list upload
                    # failure used to left-shift every later image while the
                    # prompt's @ImageN labels stayed put, so the prompt addressed
                    # the WRONG reference (operator Lane-V disposition 2026-06-11).
                    candidate_paths = list(dict.fromkeys(
                        primary_refs
                        + [e["reference"] for e in live_secondaries]
                        + [r for e in live_secondaries
                           for r in (e.get("multi_angle_refs") or [])]))
                    url_by_path = {}
                    for ref_path in candidate_paths:
                        try:
                            url_by_path[ref_path] = fal_client.upload_file(ref_path)
                        except Exception:
                            pass  # Upload failed for this ref — excluded from the slot map; others proceed
                    uploaded_primary = [r for r in primary_refs if r in url_by_path]
                    uploaded_secondaries = [
                        {**e, "multi_angle_refs": [
                            r for r in (e.get("multi_angle_refs") or [])
                            if r in url_by_path]}
                        for e in live_secondaries if e["reference"] in url_by_path
                    ]
                    ref_paths, slot_map = _allocate_ref_slots(uploaded_primary,
                                                              uploaded_secondaries)
                    image_urls = [url_by_path[p] for p in ref_paths]
                    sections = _parse_structured_prompt(prompt)
                    if slot_map.get("primary"):
                        char_blocks = [(slot_map["primary"][0], identity_anchor)]
                        char_blocks += [
                            (slot_map[e["char_id"]][0], e.get("identity_anchor", ""))
                            for e in uploaded_secondaries if e["char_id"] in slot_map
                        ]
                        kontext_prompt = _build_multichar_kontext_prompt(sections, char_blocks)
                        print(f"   [KONTEXT] Multi-char ({len(image_urls)} refs, "
                              f"{len(char_blocks)} identities)")
                    else:
                        # no surviving primary ref — force the degradation guard
                        image_urls = []
                    if not image_urls:
                        # every primary upload failed — degrade to single-char via
                        # the multichar builder (1 block); do not crash the take
                        image_urls = [fal_client.upload_file(character_image)]
                        kontext_prompt = _build_multichar_kontext_prompt(
                            _parse_structured_prompt(prompt),
                            [(1, identity_anchor)],
                        )
                else:
                    # Collect all reference image URLs
                    image_urls = []
                    refs_to_upload = []

                    if multi_angle_refs and len(multi_angle_refs) > 0:
                        refs_to_upload = [r for r in multi_angle_refs if os.path.exists(r)]
                    else:
                        refs_to_upload = [character_image]

                    for ref_path in refs_to_upload[:6]:  # Up to 6 refs for max identity
                        try:
                            image_urls.append(fal_client.upload_file(ref_path))
                        except Exception:
                            pass  # Upload failed for this ref — excluded from batch; others proceed

                    if not image_urls:
                        image_urls = [fal_client.upload_file(character_image)]

                    # Parse structured sections from the prompt
                    sections = _parse_structured_prompt(prompt)
                    scene_desc = sections.get("SCENE", prompt[:200])
                    action_desc = sections.get("ACTION", "facing the camera")
                    outfit_desc = sections.get("OUTFIT", "")
                    shot_desc = sections.get("SHOT", "Medium shot, 85mm lens")

                    print(f"   [KONTEXT] Max Multi ({len(image_urls)} refs): scene='{scene_desc[:50]}...'")

                    # BUILD KONTEXT PROMPT — audit-grade structured prompt
                    # Architecture: PRESERVE → CHANGE → CONSTRAIN
                    # Rule: identity tokens go FIRST (early attention priority)

                    parts = []

                    # BLOCK 1: IDENTITY PRESERVATION (highest priority tokens)
                    if identity_anchor:
                        parts.append(
                            f"PRESERVE IDENTITY: The person from @Image1 is {identity_anchor}. "
                            f"Keep this EXACT face, hair, glasses, eye color, skin tone unchanged."
                        )
                    else:
                        parts.append(
                            "PRESERVE IDENTITY: Keep the exact same person from @Image1. "
                            "Do not change face, hair, or any physical features."
                        )

                    # BLOCK 2: SURGICAL CHANGES (only what differs from reference)
                    parts.append(f"CHANGE BACKGROUND: {scene_desc}.")
                    if outfit_desc:
                        parts.append(f"CHANGE OUTFIT: {outfit_desc}.")
                    parts.append(f"SET POSE: {action_desc}.")
                    parts.append(f"SET CAMERA: {shot_desc}.")

                    # BLOCK 3: HARD CONSTRAINTS (reinforcement)
                    parts.append(
                        "CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
                        "Do NOT generate a different person. "
                        "The face in the output MUST match @Image1 exactly."
                    )

                    # BLOCK 4: QUALITY (perceptual tokens FLUX actually understands)
                    parts.append(
                        "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
                        "shallow depth of field with circular bokeh, natural film grain ISO 400, "
                        "volumetric atmospheric lighting, micro-detail in fabric texture, "
                        "no AI artifacts, no smooth plastic skin, no over-saturated colors."
                    )

                    kontext_prompt = " ".join(parts)

                result = fal_client.subscribe(
                    "fal-ai/flux-pro/kontext/max/multi",
                    client_timeout=FAL_TIMEOUT_IMAGE_S,
                    arguments={
                        "prompt": kontext_prompt,
                        "image_urls": image_urls,
                        "guidance_scale": 3.5,
                        "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                        "output_format": "jpeg",
                        "num_images": 1,
                    },
                )
                img_url = result["images"][0]["url"]
                if _download_generated_jpeg(img_url, output_filename) is None:
                    raise RuntimeError("FLUX Kontext output failed JPEG validation")
                print(f"      [OK] FLUX Kontext image: {output_filename}")
                return ImageGenResult(output_filename, "FLUX_KONTEXT")
            except Exception as e_kontext:
                print(f"      [WARN] FLUX Kontext failed: {e_kontext}, trying FLUX-Pro...")

        # PRIORITY 2: FLUX-Pro text-to-image (no face-lock)
        print(f"   [FALLBACK] FLUX-Pro (no face-lock): '{prompt[:60]}...'")
        try:
            result = fal_client.subscribe(
                "fal-ai/flux-pro/v1.1-ultra",
                client_timeout=FAL_TIMEOUT_IMAGE_S,
                arguments={
                    "prompt": prompt,
                    "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                    "output_format": "jpeg",
                    "seed": seed,
                    "num_inference_steps": 32,
                    "guidance_scale": 3.5,
                },
            )
            img_url = result["images"][0]["url"]
            if _download_generated_jpeg(img_url, output_filename) is None:
                raise RuntimeError("FLUX-Pro output failed JPEG validation")
            print(f"      [OK] FLUX-Pro image: {output_filename}")
            return ImageGenResult(output_filename, "FLUX_PRO")
        except Exception as e1:
            print(f"      [WARN] FLUX-Pro failed: {e1}, trying FLUX schnell...")

        # Fallback to schnell (faster, lower quality)
        try:
            import fal_client
            result = fal_client.subscribe(
                "fal-ai/flux/schnell",
                client_timeout=FAL_TIMEOUT_IMAGE_S,
                arguments={
                    "prompt": prompt,
                    "image_size": fal_image_size(aspect_ratio),
                    "num_inference_steps": 4,
                    "seed": seed,
                },
            )
            img_url = result["images"][0]["url"]
            if _download_generated_jpeg(img_url, output_filename) is None:
                raise RuntimeError("FLUX-schnell output failed JPEG validation")
            print(f"      ✅ FAL FLUX-schnell image: {output_filename}")
            return ImageGenResult(output_filename, "FLUX_SCHNELL")
        except Exception as e2:
            print(f"      ⚠️ FLUX-schnell also failed: {e2}")

        # Last resort: Pollinations (free, lower quality)
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        _pw, _ph = portrait_swap(1344, 768, aspect_ratio)
        poll_seed = 42 if seed is None else seed
        poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width={_pw}&height={_ph}&nologo=True&model=flux&seed={poll_seed}"
        if _download_generated_jpeg(poll_url, output_filename) is not None:
            print(f"      ✅ Pollinations fallback image: {output_filename}")
            return ImageGenResult(output_filename, "POLLINATIONS")

        print("❌ All image generation methods failed.")
        return None

    except Exception as e:
        print(f"❌ Fallback image generation failed: {e}")
        return None

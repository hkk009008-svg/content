import os
import logging
import shutil
import tempfile

from typing import Mapping, NamedTuple

from config.settings import settings
from cinema.aspect import portrait_swap, fal_image_size, fal_aspect_ratio, DEFAULT_ASPECT_RATIO
from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from cinema.context import get_project_setting
from performance._net import safe_download, validate_image_artifact
from paid_provider import has_paid_attempt_authority


logger = logging.getLogger(__name__)


class _ImagePaidCascadeStop(RuntimeError):
    """Internal signal that a paid image outcome blocks fallback."""


class ImageGenResult(NamedTuple):
    """Provenance-carrying result of an image-generation backend.

    ``path`` is the saved image (equals ``output_filename`` on success);
    ``api_name`` is the cost_tracker API key for the backend that ACTUALLY ran
    (``GEMINI_IMAGE`` | ``FLUX2_KLEIN_LOCAL`` | ``FLUX_KONTEXT`` |
    ``FLUX_PRO`` | ``FLUX_SCHNELL`` | ``POLLINATIONS``). Callers record
    ``api_name`` so cost_log reflects where the
    image was really generated, not a tier-based guess. Backends
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


def generate_ai_broll(prompt, output_filename, seed=None, character_image=None,
                       continuity_reference=None,
                       multi_angle_refs=None, identity_anchor="",
                       negative_prompt="",
                       secondary_char_refs=None,
                       shot_hint=None, ctx=None,
                       _recovery_out=None, cost_tracker=None,
                       shot_id="", video_id="", take_id="",
                       project_snapshot=None, project_root=None,
                       artifact_metadata=None):
    """
    Generates a cinematic image with face-identity preservation.

    Current production routing starts with the explicitly selected image
    backend, then uses supported fallbacks only when the project did not pin a
    local route. Unsupported stored backend values fail closed and can only be
    migrated through the setup UI.

    Args:
        prompt: Image generation prompt (enhanced by continuity engine)
        output_filename: Output path for generated image
        seed: Deterministic seed for consistency
        character_image: Primary character reference for face identity
        continuity_reference: Approved previous keyframe, when present. Local
            FLUX.2 may include it in its immutable reference-latent workflow.
        secondary_char_refs: P1-1 slice 1: additional character entries forwarded
            to _fal_flux_fallback; each entry has char_id, reference, multi_angle_refs,
            identity_anchor. None / [] takes the single-char (golden) path.
        shot_hint: Provider-neutral shot metadata used by identity validation.

    Returns:
        ImageGenResult(path, api_name, billed_rejects) naming the backend
        that actually ran (GEMINI_IMAGE | FLUX2_KLEIN_LOCAL | FLUX_KONTEXT |
        FLUX_PRO | FLUX_SCHNELL | POLLINATIONS), or None if every backend
        failed. Callers record ``api_name`` for cost attribution so provider
        routes remain distinguishable in cost_log. ``billed_rejects`` names any
        engine that billed for a generation this call incurred but did NOT
        win (WS3: a Gemini bill-but-identity-reject before falling through) —
        callers must record these too or the spend is invisible to the
        budget gate.
    """

    # Read per-project aspect ratio early — must be in scope at ALL six
    # _fal_flux_fallback call sites (including early-return and except paths).
    # Phase 2: portrait-aware latent dimensions + FAL/Pollinations orientation.
    # get_project_setting is a safe dict lookup with a default (never raises,
    # handles ctx=None), so it is safe to call here outside the try block.
    aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)

    # WS3 money-loss close-out (mirrors cinema/shots/controller.py's
    # _record_billed_rejects on the video side): Gemini can BILL a real
    # image (Nano Banana 2, $0.067) that then fails identity and falls through
    # to the remaining cascade below — a billed engine that never becomes the
    # winner. Track it here and thread it onto whichever ImageGenResult this
    # call finally returns, so the caller's cost_tracker sees the spend even
    # though Gemini didn't win. Only the PRIORITY-0 block below appends to
    # this list; the Gemini SUCCESS return just below keeps it empty (there
    # is nothing to fall through from).
    billed_rejects = []

    has_artifact_scope = bool(
        video_id
        and shot_id
        and take_id
        and project_root is not None
        and isinstance(project_snapshot, Mapping)
    )

    def _gemini_candidate_take(
        *,
        status: str,
        stage: str,
        identity_score=None,
        identity_threshold=None,
    ) -> dict:
        metadata = (
            dict(artifact_metadata)
            if isinstance(artifact_metadata, Mapping)
            else {}
        )
        metadata.update({
            "prompt": prompt,
            "seed": seed,
            "mechanism_actually_used": "GEMINI_IMAGE",
            "rejection_stage": stage if status == "rejected" else None,
            "identity_score": identity_score,
            "identity_threshold": identity_threshold,
        })
        return {
            "id": take_id,
            "kind": "keyframe",
            "path": output_filename,
            "status": status,
            "metadata": metadata,
            "cascade_metadata": {
                "engine": "GEMINI_IMAGE",
                "stage": stage,
            },
        }

    def _record_gemini_candidate(
        *,
        status: str,
        stage: str,
        identity_score=None,
        identity_threshold=None,
    ) -> dict | None:
        if not has_artifact_scope:
            return None
        from cinema.artifact_indexing import record_take_version

        return record_take_version(
            video_id,
            shot_id,
            "keyframe",
            _gemini_candidate_take(
                status=status,
                stage=stage,
                identity_score=identity_score,
                identity_threshold=identity_threshold,
            ),
            project_snapshot=project_snapshot,
            project_root=project_root,
        )

    def _retain_rejected_gemini(
        *,
        rejection_stage: str,
        identity_score=None,
        identity_threshold=None,
    ):
        """Copy a rejected paid frame before a fallback overwrites it.

        ``None`` means this is a legacy unscoped caller. The active controller
        always supplies an exact project/take scope; there, ``False`` blocks
        fallback so a retention failure cannot destroy the only provider
        output bytes.
        """
        if not has_artifact_scope:
            return None
        try:
            record = _record_gemini_candidate(
                status="rejected",
                stage=rejection_stage,
                identity_score=identity_score,
                identity_threshold=identity_threshold,
            )
        except Exception:
            if isinstance(_recovery_out, dict):
                _recovery_out.update({
                    "engine": "GEMINI_IMAGE",
                    "status": "recovery_required",
                    "provider_status": "artifact_retention_failed",
                    "reason": (
                        "Gemini returned a paid frame, but its rejected bytes "
                        "could not be copied into immutable artifact history. "
                        "Fallback is blocked so the provider output is not overwritten."
                    ),
                })
            print(
                "   [UNKNOWN] Rejected Gemini frame could not be retained; "
                "fallback blocked"
            )
            return False
        return record

    def _restore_completed_gemini_candidate():
        """Restore retained provider bytes, or flag a prior local rejection."""
        if not has_artifact_scope:
            return None
        from cinema.artifact_versions import ArtifactVersionStore

        store = ArtifactVersionStore(video_id, project_root)
        logical_name = f"shots/{shot_id}/keyframe/{take_id}"
        records = [
            record
            for record in store.history(logical_name)
            if record.get("provider") == "GEMINI_IMAGE"
        ]
        completed = [
            record
            for record in records
            if (record.get("parameters") or {}).get("status")
            == "provider_completed"
        ]
        if not completed:
            return None
        latest_completed = completed[-1]
        rejected_later = any(
            record.get("sequence", 0) > latest_completed.get("sequence", 0)
            and (record.get("parameters") or {}).get("status") == "rejected"
            for record in records
        )
        if rejected_later:
            return False
        if not store.verify_artifact(latest_completed["artifact_id"]):
            raise RuntimeError("retained Gemini candidate failed hash verification")
        source = os.path.join(project_root, latest_completed["object_path"])
        destination_dir = os.path.dirname(output_filename) or "."
        os.makedirs(destination_dir, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{os.path.basename(output_filename)}.",
            suffix=".artifact-restore",
            dir=destination_dir,
        )
        os.close(fd)
        try:
            shutil.copyfile(source, temporary)
            if not validate_image_artifact(temporary, expected_formats=("JPEG",)):
                raise RuntimeError("retained Gemini candidate is not a valid JPEG")
            os.replace(temporary, output_filename)
        finally:
            try:
                os.remove(temporary)
            except FileNotFoundError:
                pass
        return output_filename

    def _retain_completed_gemini_candidate(_result) -> None:
        if not has_artifact_scope:
            return
        try:
            _record_gemini_candidate(
                status="provider_completed",
                stage="provider_response",
            )
        except Exception:
            if isinstance(_recovery_out, dict):
                _recovery_out.update({
                    "engine": "GEMINI_IMAGE",
                    "status": "recovery_required",
                    "provider_status": "artifact_retention_failed",
                    "reason": (
                        "Gemini completed a paid frame, but its bytes could not "
                        "be retained before reconciliation. Automatic replay and "
                        "fallback are blocked."
                    ),
                })
            raise

    def _fal_fallback(*args, **kwargs):
        kwargs.update({
            "cost_tracker": cost_tracker,
            "shot_id": shot_id,
            "video_id": video_id,
            "_recovery_out": _recovery_out,
        })
        return _fal_flux_fallback(*args, **kwargs)

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

    # ----- Primary image route: Gemini multi-reference -----
    # Gemini runs only when the project selected it. Ordinary unbilled failure
    # and safely retained identity rejection may continue through the guarded
    # local/cloud cascade. Ambiguous paid work or rejected-byte retention
    # failure stops every replacement provider.
    identity_backend = get_project_setting(ctx, "identity_backend", "gemini_multiref")
    if (
        (settings.google_api_key or settings.gemini_api_key)
        and character_image
        and os.path.exists(character_image)
        and identity_backend == "gemini_multiref"
    ):
        try:
            from gemini_image_native import GeminiImageAPI
            gemini_secondary_refs = [
                sc.get("reference") for sc in (secondary_char_refs or []) if sc.get("reference")
            ]
            def _generate_gemini_image():
                return GeminiImageAPI().generate_image(
                    prompt,
                    output_filename,
                    character_image=character_image,
                    multi_angle_refs=multi_angle_refs,
                    secondary_char_refs=gemini_secondary_refs,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=negative_prompt,
                )

            if not has_paid_attempt_authority(cost_tracker):
                gemini_path = _generate_gemini_image()
            else:
                from cost_tracker import API_COST_USD
                from paid_provider import (
                    PaidCallBudgetBlocked,
                    PaidCallDeferred,
                    PaidCallUnbilled,
                    file_fingerprint,
                    paid_attempt_id,
                    request_fingerprint,
                    run_nonresumable_paid_call,
                )

                ref_paths = [character_image]
                ref_paths.extend(
                    path for path in (multi_angle_refs or []) if path and os.path.exists(path)
                )
                ref_paths.extend(
                    path for path in gemini_secondary_refs if path and os.path.exists(path)
                )
                stable_request = request_fingerprint(
                    "gemini-image",
                    prompt,
                    negative_prompt,
                    aspect_ratio,
                    [file_fingerprint(path) for path in ref_paths],
                    os.path.abspath(output_filename),
                )
                gemini_attempt_id = paid_attempt_id(
                    "gemini-image",
                    video_id,
                    shot_id,
                    os.path.abspath(output_filename),
                )
                try:
                    existing_attempt = cost_tracker.get_paid_attempt(
                        gemini_attempt_id
                    )
                    restored = (
                        _restore_completed_gemini_candidate()
                        if existing_attempt is not None
                        else None
                    )
                    if restored is False:
                        # Identity already rejected the exact immutable Gemini
                        # candidate. Continue into the durable fallback chain
                        # without trying or revalidating Gemini again.
                        gemini_path = None
                    elif isinstance(restored, str):
                        if existing_attempt.get("state") != "succeeded":
                            cost_tracker.reconcile_paid_attempt(
                                gemini_attempt_id,
                                state="succeeded",
                                actual_cost_usd=API_COST_USD["GEMINI_IMAGE"],
                                provider_status="completed_artifact_recovered",
                                detail=(
                                    "Recovered exact retained Gemini output "
                                    "without another provider submission"
                                ),
                            )
                        gemini_path = restored
                    else:
                        gemini_path = run_nonresumable_paid_call(
                            call=_generate_gemini_image,
                            attempt_id=gemini_attempt_id,
                            provider="google",
                            engine="GEMINI_IMAGE",
                            operation="keyframe_generation",
                            estimated_cost_usd=API_COST_USD["GEMINI_IMAGE"],
                            request_fingerprint_value=stable_request,
                            cost_tracker=cost_tracker,
                            shot_id=shot_id,
                            video_id=video_id,
                            on_completed=_retain_completed_gemini_candidate,
                        )
                except PaidCallUnbilled:
                    gemini_path = None
                except (PaidCallBudgetBlocked, PaidCallDeferred) as paid_error:
                    if isinstance(_recovery_out, dict):
                        _recovery_out.setdefault("engine", "GEMINI_IMAGE")
                        _recovery_out.setdefault("status", "recovery_required")
                        _recovery_out.setdefault(
                            "provider_status",
                            "budget_blocked"
                            if isinstance(paid_error, PaidCallBudgetBlocked)
                            else "accepted_unknown",
                        )
                        _recovery_out.setdefault(
                            "reason",
                            "Gemini Image has no durable job identifier or "
                            "idempotency key. Automatic replay and paid fallback "
                            "are blocked until this attempt is reconciled.",
                        )
                        _recovery_out["paid_attempt_id"] = (
                            paid_error.snapshot.attempt.get("attempt_id")
                        )
                    print(f"   [UNKNOWN] Gemini image paid outcome: {paid_error}")
                    return None
                except Exception as recovery_error:
                    if isinstance(_recovery_out, dict):
                        _recovery_out.update({
                            "engine": "GEMINI_IMAGE",
                            "status": "recovery_required",
                            "provider_status": "artifact_recovery_failed",
                            "reason": (
                                "Retained Gemini provider bytes could not be "
                                "verified or restored. Automatic fallback is blocked."
                            ),
                        })
                    raise _ImagePaidCascadeStop(
                        "Gemini artifact recovery failed"
                    ) from recovery_error
            if gemini_path:
                # A successful generation crosses Google's billing boundary.
                # Record that spend before any local validation work because
                # the validator can reject *or raise* after the provider has
                # already charged for the frame.  A passing Gemini result
                # returns directly below, so this local reject ledger is only
                # threaded onto a later fallback winner.
                if not has_paid_attempt_authority(cost_tracker):
                    billed_rejects.append("GEMINI_IMAGE")
                from phase_c_vision import _get_shared_validator
                _chars_in_frame = (shot_hint or {}).get("characters_in_frame") or []
                try:
                    id_result = _get_shared_validator().validate_image(
                        gemini_path, character_image,
                        character_id=_chars_in_frame[0] if _chars_in_frame else "",
                        threshold=get_project_setting(ctx, "identity_strictness", None),
                        cost_tracker=cost_tracker,
                        video_id=video_id,
                        shot_id=shot_id,
                    )
                except Exception:
                    retained = _retain_rejected_gemini(
                        rejection_stage="identity_validation_error",
                    )
                    if retained is False:
                        raise _ImagePaidCascadeStop(
                            "rejected Gemini output retention failed"
                        )
                    raise
                if id_result.passed:
                    print(f"   [PHASE C] Gemini 3.1 Flash Image (Nano Banana 2) passed identity "
                          f"check (score={id_result.overall_score}): '{prompt[:60]}...'")
                    if isinstance(_recovery_out, dict) and has_paid_attempt_authority(cost_tracker):
                        _recovery_out["_winner_paid_cost_recorded"] = True
                    return ImageGenResult(output_filename, "GEMINI_IMAGE")
                print(f"   [GEMINI-IMAGE] Identity check failed (score={id_result.overall_score}); "
                      f"falling back to the remaining provider cascade")
                retained = _retain_rejected_gemini(
                    rejection_stage="identity_validation",
                    identity_score=id_result.overall_score,
                    identity_threshold=id_result.threshold_used,
                )
                if retained is False:
                    raise _ImagePaidCascadeStop(
                        "rejected Gemini output retention failed"
                    )
                logger.info(
                    "Gemini identity candidate rejected",
                    extra={
                        "provider": "google",
                        "engine": "GEMINI_IMAGE",
                        "code": "identity_validation",
                        "status": "rejected",
                        "shot_id": shot_id,
                        "video_id": video_id,
                        "identity_score": id_result.overall_score,
                        "identity_threshold": id_result.threshold_used,
                        "artifact_id": (
                            retained.get("artifact_id")
                            if isinstance(retained, Mapping)
                            else None
                        ),
                        "artifact_sha256": (
                            retained.get("sha256")
                            if isinstance(retained, Mapping)
                            else None
                        ),
                    },
                )
            else:
                print("   [GEMINI-IMAGE] Generation returned no image; falling back to the remaining provider cascade")
        except _ImagePaidCascadeStop as e:
            print(f"   [UNKNOWN] Gemini image cascade stopped: {e}")
            return None
        except Exception as e:
            print(f"   [GEMINI-IMAGE] Primary route failed ({e}); falling back to the remaining provider cascade")

    # ----- Supported local/remote fallback selection -----
    def _fall_through_to_fal():
        if character_image and os.path.exists(character_image) and settings.fal_key:
            return _with_rejects(_fal_fallback(
                prompt, output_filename, seed,
                character_image=character_image,
                multi_angle_refs=multi_angle_refs,
                identity_anchor=identity_anchor,
                aspect_ratio=aspect_ratio,
                secondary_char_refs=secondary_char_refs,
            ))
        return _with_rejects(_fal_fallback(
            prompt, output_filename, seed,
            character_image=character_image,
            aspect_ratio=aspect_ratio,
            secondary_char_refs=None,
        ))

    def _block_local(*, code: str, reason: str):
        if isinstance(_recovery_out, dict):
            _recovery_out.update({
                "engine": "FLUX2_KLEIN_LOCAL",
                "status": "blocked",
                "provider_status": code,
                "code": code,
                "retryable": False,
                "reason": reason,
            })
        print(f"   [BLOCKED] Local FLUX.2 Klein: {reason}")
        return None

    if identity_backend not in {"gemini_multiref", "local_flux2_klein"}:
        return _block_local(
            code="image_backend_invalid",
            reason="The project has an unsupported image backend selection.",
        )

    local_references = []
    for candidate in [
        character_image,
        *(multi_angle_refs or []),
        *(
            item
            for entry in (secondary_char_refs or [])
            for item in [entry.get("reference"), *(entry.get("multi_angle_refs") or [])]
        ),
        continuity_reference,
    ]:
        if (
            candidate
            and os.path.isfile(candidate)
            and candidate not in local_references
        ):
            local_references.append(candidate)
        if len(local_references) == 10:
            break

    explicit_local = identity_backend == "local_flux2_klein"
    if explicit_local and not local_references:
        return _block_local(
            code="local_reference_required",
            reason=(
                "The local FLUX.2 workflow requires at least one approved "
                "character or continuity reference image."
            ),
        )

    if local_references:
        from paid_provider import (
            PaidCallBudgetBlocked,
            PaidCallDeferred,
            PaidCallUnbilled,
        )
        from performance.flux2_klein import run_flux2_klein_image_job
        from performance.worker_readiness import (
            PerformanceWorkerUnavailable,
            require_flux2_worker_ready,
        )

        try:
            require_flux2_worker_ready(settings)
        except PerformanceWorkerUnavailable as readiness_error:
            if explicit_local:
                return _block_local(
                    code="local_flux2_not_ready",
                    reason=str(readiness_error),
                )
            print(
                "   [PHASE C] Local FLUX.2 is not ready; continuing to the "
                "supported cloud fallback."
            )
        else:
            if not has_paid_attempt_authority(cost_tracker):
                if explicit_local:
                    return _block_local(
                        code="durable_job_authority_required",
                        reason=(
                            "Local FLUX.2 dispatch requires the project-scoped "
                            "durable job ledger."
                        ),
                    )
            else:
                local_seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else 0
                try:
                    local_result = run_flux2_klein_image_job(
                        prompt=prompt,
                        reference_image_paths=local_references,
                        output_path=output_filename,
                        seed=local_seed,
                        aspect_ratio=aspect_ratio,
                        cost_tracker=cost_tracker,
                        shot_id=shot_id,
                        video_id=video_id,
                        request_id=take_id,
                    )
                except PaidCallUnbilled as local_rejected:
                    if explicit_local:
                        return _block_local(
                            code="local_flux2_rejected_unbilled",
                            reason=str(local_rejected),
                        )
                    print(
                        "   [PHASE C] Local FLUX.2 rejected the graph before "
                        "execution; continuing to the supported cloud fallback."
                    )
                except (PaidCallBudgetBlocked, PaidCallDeferred) as local_deferred:
                    if isinstance(_recovery_out, dict):
                        _recovery_out.update({
                            "engine": "FLUX2_KLEIN_LOCAL",
                            "status": "recovery_required",
                            "provider_status": (
                                "budget_blocked"
                                if isinstance(local_deferred, PaidCallBudgetBlocked)
                                else "job_state_unknown"
                            ),
                            "reason": (
                                "The local FLUX.2 job is reserved or recoverable "
                                "by its durable prompt ID. No replacement image "
                                "provider was started."
                            ),
                            "paid_attempt_id": local_deferred.snapshot.attempt.get(
                                "attempt_id"
                            ),
                        })
                        job_id = local_deferred.snapshot.attempt.get("provider_job_id")
                        if job_id:
                            _recovery_out["job_id"] = job_id
                    print(f"   [UNKNOWN] Local FLUX.2 job requires recovery: {local_deferred}")
                    return None
                except Exception as local_error:
                    # Readiness was proven immediately before dispatch, so any
                    # later exception may follow upload, queue acceptance, or
                    # completed GPU work. Conservatively block a replacement.
                    if isinstance(_recovery_out, dict):
                        _recovery_out.update({
                            "engine": "FLUX2_KLEIN_LOCAL",
                            "status": "recovery_required",
                            "provider_status": "local_job_or_artifact_unknown",
                            "reason": (
                                "Local FLUX.2 failed after its readiness proof. "
                                "Reconcile the durable prompt and output before retrying."
                            ),
                        })
                    print(f"   [UNKNOWN] Local FLUX.2 outcome: {local_error}")
                    return None
                else:
                    if isinstance(_recovery_out, dict):
                        _recovery_out["_winner_paid_cost_recorded"] = True
                    print(f"      [OK] Local FLUX.2 image: {local_result.published_path}")
                    return _with_rejects(ImageGenResult(
                        local_result.published_path,
                        "FLUX2_KLEIN_LOCAL",
                    ))

    return _fall_through_to_fal()


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
                       secondary_char_refs=None, cost_tracker=None,
                       shot_id="", video_id="", _recovery_out=None):
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

        local_ref_paths = []
        for candidate in [character_image, *(multi_angle_refs or [])]:
            if candidate and os.path.exists(candidate):
                local_ref_paths.append(candidate)
        for entry in secondary_char_refs or []:
            for candidate in [entry.get("reference"), *(entry.get("multi_angle_refs") or [])]:
                if candidate and os.path.exists(candidate):
                    local_ref_paths.append(candidate)

        def _fal_image_call(application: str, arguments: dict, engine_key: str) -> dict:
            if not has_paid_attempt_authority(cost_tracker):
                return fal_client.subscribe(
                    application,
                    client_timeout=FAL_TIMEOUT_IMAGE_S,
                    arguments=arguments,
                )
            from cost_tracker import API_COST_USD
            from paid_provider import (
                PaidCallBudgetBlocked,
                PaidCallDeferred,
                PaidCallUnbilled,
                file_fingerprint,
                paid_attempt_id,
                request_fingerprint,
                run_durable_fal_job,
            )

            safe_arguments = {
                key: value
                for key, value in arguments.items()
                if key not in {"image_urls", "image_url"}
            }
            stable_request = request_fingerprint(
                application,
                safe_arguments,
                [file_fingerprint(path) for path in local_ref_paths],
                os.path.abspath(output_filename),
            )
            try:
                return run_durable_fal_job(
                    application=application,
                    arguments=arguments,
                    attempt_id=paid_attempt_id(
                        "fal-keyframe",
                        video_id,
                        shot_id,
                        engine_key,
                        os.path.abspath(output_filename),
                    ),
                    engine=engine_key,
                    operation="keyframe_generation",
                    estimated_cost_usd=API_COST_USD[engine_key],
                    request_fingerprint_value=stable_request,
                    cost_tracker=cost_tracker,
                    shot_id=shot_id,
                    video_id=video_id,
                    poll_timeout_s=FAL_TIMEOUT_IMAGE_S,
                )
            except PaidCallUnbilled:
                return {}
            except (PaidCallBudgetBlocked, PaidCallDeferred) as paid_error:
                if isinstance(_recovery_out, dict):
                    _recovery_out.update({
                        "engine": engine_key,
                        "status": "recovery_required",
                        "provider_status": (
                            "budget_blocked"
                            if isinstance(paid_error, PaidCallBudgetBlocked)
                            else "job_state_unknown"
                        ),
                        "reason": (
                            "FAL keyframe request is budget-blocked or recoverable "
                            "by durable request ID. No paid fallback was started."
                        ),
                        "paid_attempt_id": paid_error.snapshot.attempt.get("attempt_id"),
                    })
                    job_id = paid_error.snapshot.attempt.get("provider_job_id")
                    if job_id:
                        _recovery_out["job_id"] = job_id
                raise _ImagePaidCascadeStop(str(paid_error)) from paid_error

        def _defer_completed_image_artifact(engine_key: str) -> None:
            if not has_paid_attempt_authority(cost_tracker):
                return
            attempt = None
            try:
                attempt = cost_tracker.get_latest_paid_attempt(
                    video_id=video_id,
                    shot_id=shot_id,
                    engine=engine_key,
                    operation="keyframe_generation",
                )
            except Exception:
                pass
            if isinstance(_recovery_out, dict):
                _recovery_out.update({
                    "engine": engine_key,
                    "status": "recovery_required",
                    "provider_status": "artifact_unavailable",
                    "reason": (
                        "The provider completed and may be billed, but its image "
                        "could not be published. Retrieve the durable provider result "
                        "instead of starting another paid backend."
                    ),
                })
                if isinstance(attempt, dict):
                    _recovery_out["paid_attempt_id"] = attempt.get("attempt_id")
                    if attempt.get("provider_job_id"):
                        _recovery_out["job_id"] = attempt["provider_job_id"]
            raise _ImagePaidCascadeStop(
                f"{engine_key} completed but artifact publication failed"
            )

        # First supported reference-conditioned route (up to 9 refs).
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

                result = _fal_image_call(
                    "fal-ai/flux-pro/kontext/max/multi",
                    {
                        "prompt": kontext_prompt,
                        "image_urls": image_urls,
                        "guidance_scale": 3.5,
                        "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                        "output_format": "jpeg",
                        "num_images": 1,
                    },
                    "FLUX_KONTEXT",
                )
                img_url = result["images"][0]["url"]
                if _download_generated_jpeg(img_url, output_filename) is None:
                    _defer_completed_image_artifact("FLUX_KONTEXT")
                    raise RuntimeError("FLUX Kontext output failed JPEG validation")
                print(f"      [OK] FLUX Kontext image: {output_filename}")
                if isinstance(_recovery_out, dict) and has_paid_attempt_authority(cost_tracker):
                    _recovery_out["_winner_paid_cost_recorded"] = True
                return ImageGenResult(output_filename, "FLUX_KONTEXT")
            except _ImagePaidCascadeStop:
                return None
            except Exception as e_kontext:
                print(f"      [WARN] FLUX Kontext failed: {e_kontext}, trying FLUX-Pro...")

        # PRIORITY 2: FLUX-Pro text-to-image (no face-lock)
        print(f"   [FALLBACK] FLUX-Pro (no face-lock): '{prompt[:60]}...'")
        try:
            result = _fal_image_call(
                "fal-ai/flux-pro/v1.1-ultra",
                {
                    "prompt": prompt,
                    "aspect_ratio": fal_aspect_ratio(aspect_ratio),
                    "output_format": "jpeg",
                    "seed": seed,
                    "num_inference_steps": 32,
                    "guidance_scale": 3.5,
                },
                "FLUX_PRO",
            )
            img_url = result["images"][0]["url"]
            if _download_generated_jpeg(img_url, output_filename) is None:
                _defer_completed_image_artifact("FLUX_PRO")
                raise RuntimeError("FLUX-Pro output failed JPEG validation")
            print(f"      [OK] FLUX-Pro image: {output_filename}")
            if isinstance(_recovery_out, dict) and has_paid_attempt_authority(cost_tracker):
                _recovery_out["_winner_paid_cost_recorded"] = True
            return ImageGenResult(output_filename, "FLUX_PRO")
        except _ImagePaidCascadeStop:
            return None
        except Exception as e1:
            print(f"      [WARN] FLUX-Pro failed: {e1}, trying FLUX schnell...")

        # Fallback to schnell (faster, lower quality)
        try:
            import fal_client
            result = _fal_image_call(
                "fal-ai/flux/schnell",
                {
                    "prompt": prompt,
                    "image_size": fal_image_size(aspect_ratio),
                    "num_inference_steps": 4,
                    "seed": seed,
                },
                "FLUX_SCHNELL",
            )
            img_url = result["images"][0]["url"]
            if _download_generated_jpeg(img_url, output_filename) is None:
                _defer_completed_image_artifact("FLUX_SCHNELL")
                raise RuntimeError("FLUX-schnell output failed JPEG validation")
            print(f"      ✅ FAL FLUX-schnell image: {output_filename}")
            if isinstance(_recovery_out, dict) and has_paid_attempt_authority(cost_tracker):
                _recovery_out["_winner_paid_cost_recorded"] = True
            return ImageGenResult(output_filename, "FLUX_SCHNELL")
        except _ImagePaidCascadeStop:
            return None
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

    except _ImagePaidCascadeStop:
        return None
    except Exception as e:
        print(f"❌ Fallback image generation failed: {e}")
        return None

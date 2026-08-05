"""Runway Act-Two — character-performance retargeting.

Act-Two is Runway's character-performance model: given a still keyframe (or
video) of a character and a REFERENCE VIDEO of a person performing, it maps
the reference's facial expressions (and, opt-in, body movement) onto the
character.

Migrated from the retired Act-One integration (2026-07-30, slice 5b).
Verified against the installed ``runwayml`` SDK (v4.14.0) — see
``runwayml/types/character_performance_create_params.py`` and
``runwayml/resources/character_performance.py`` in site-packages:

  - ``model`` is typed ``Literal["act_two"]`` — "act_one" is not a
    constructible value for ``character_performance.create()`` any more.
  - ``reference`` MUST be ``{"type": "video", "uri": <https-url>}`` — a
    video, 3-30 seconds long, of a person performing. There is NO
    audio-reference mode. Act-One could auto-generate a performance from
    dialogue audio alone; Act-Two cannot — every call needs an actual
    driving/reference performance clip. Callers with only TTS/dialogue
    audio and no reference video get a clear, logged failure (see
    ``generate_act_two_performance`` below) rather than a malformed
    audio-typed request that the SDK/server would reject anyway.
  - ``.create()`` takes NO ``duration`` parameter — Act-Two infers output
    length from the reference video. The pre-migration code sent
    ``duration=int(round(duration_s))`` on every call; the SDK's
    ``CharacterPerformanceCreateParams`` TypedDict does not define that
    field, so it has been removed from the outgoing request entirely.
    ``duration_s`` remains a Python-side keyword, used only for the $/s cost
    estimate — it is never forwarded to Runway. The raw REST path is now
    retrieval-only and cannot submit new work.
  - Optional knobs the endpoint DOES offer but this adapter does not yet
    wire: ``body_control`` (bool), ``content_moderation``,
    ``expression_intensity`` (1-5 int), ``seed``.
  - ``uri`` for both ``character`` and ``reference`` cannot be a local
    filesystem path.  New submissions therefore use the SDK's documented
    ``uploads.create_ephemeral(file=Path(...))`` transport and pass the
    returned short-lived ``runway://`` URIs to ``character_performance``.
    A resumed task already owns its inputs and goes directly to retrieval;
    it never uploads or submits again.

API surface:
  - POST https://api.dev.runwayml.com/v1/character_performance
  - GET  https://api.dev.runwayml.com/v1/tasks/{id}  (polled until done)

Auth: bearer token = settings.runwayml_api_secret (already configured for
the existing Runway Gen-4 integration).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from config.settings import settings
from performance._net import safe_download, validate_video_artifact


_POLL_INTERVAL_S = 3
_MODEL = "act_two"
_RUNWAY_API_VERSION = "2024-11-06"


def _evidence_token(value: object, *, fallback: str = "UNKNOWN") -> str:
    """Return a bounded, single-line token safe for operator evidence logs."""
    raw = str(value or "").strip()
    safe = "".join(
        character if character.isalnum() or character in "._:-" else "_"
        for character in raw
    )[:128]
    return safe or fallback


def _ephemeral_uri(client, path: str, *, role: str) -> str:
    """Upload one local input and validate the SDK's opaque Runway URI."""
    response = client.uploads.create_ephemeral(file=Path(path))
    uri = getattr(response, "uri", None)
    if not isinstance(uri, str) or not uri.startswith("runway://"):
        raise ValueError(f"Runway {role} upload returned no usable runway URI")
    return uri


def _cost_log(
    operation: str,
    duration_s: float,
    shot_id: str = "",
    video_id: str = "",
    cost_tracker=None,
    provider_job_id: str | None = None,
) -> None:
    """Best-effort cost log. Doesn't fail the call if tracking isn't wired."""
    try:
        from cost_tracker import CostTracker
        # Runway Act-Two: ~$0.05/s of output video (confirm with their pricing page)
        tracker = cost_tracker or CostTracker()
        try:
            tracker.log_api(
                provider="runway",
                model=_MODEL,
                operation=operation,
                cost_usd=round(0.05 * float(duration_s), 4),
                shot_id=shot_id,
                video_id=video_id,
                provider_job_id=provider_job_id,
            )
        finally:
            if cost_tracker is None:
                tracker.close()
    except Exception:
        pass  # Cost tracking is best-effort — import or write failure doesn't fail the render


def generate_act_two_performance(
    keyframe_path: str,
    audio_path: str,
    output_mp4: str,
    *,
    driving_video_path: Optional[str] = None,
    duration_s: float = 5.0,
    shot_id: str = "",
    video_id: str = "",
    poll_timeout_s: int = 300,
    cost_tracker=None,
    task_submission_callback: Optional[Callable[[], object]] = None,
    task_acceptance_callback: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Generate an Act-Two performance clip.

    Args:
        keyframe_path: still image of the character (the approved keyframe)
        audio_path:    NOT sent to the Act-Two API — kept only for call-site
            / signature compatibility with performance/_router.py's
            dispatch(). Act-Two has no audio-reference mode (see module
            docstring); this is reserved for a possible future audio-mux
            post-process, not consumed here today.
        output_mp4:    local write target
        driving_video_path: the reference performance video (3-30s of a
            person performing the way the character should perform). This
            is EFFECTIVELY REQUIRED — unlike the retired Act-One, Act-Two
            cannot synthesize a performance from audio alone. When missing
            or not found on disk, this function returns None with a clear
            log line rather than attempting an unsupported audio-typed
            request.
        duration_s:    used ONLY for the cost-tracker estimate ($/s);
            never sent to Runway — character_performance.create() has no
            duration parameter.
        shot_id / video_id: telemetry only

    Returns the output path on success, None on any failure.
    """
    api_key = getattr(settings, "runwayml_api_secret", "") or os.environ.get("RUNWAYML_API_SECRET", "")
    if not api_key:
        print("   [ACT-TWO] RUNWAYML_API_SECRET not set; skipping")
        return None
    if not keyframe_path or not os.path.exists(keyframe_path):
        print(f"   [ACT-TWO] keyframe missing: {keyframe_path}")
        return None
    if not driving_video_path or not os.path.exists(driving_video_path):
        # Act-Two's `reference` field only accepts type="video" — there is no
        # audio-reference mode, so an audio_path alone (Act-One's old
        # auto-generate-from-audio path) cannot drive this endpoint. Fail
        # loudly and explicitly rather than send a request Runway will
        # reject, or silently mis-type audio as a "video" reference.
        print(
            "   [ACT-TWO] no driving/reference video supplied — Act-Two "
            "requires a 3-30s reference performance video (audio-only "
            "generation, which the retired Act-One supported, is not "
            "available on this endpoint); skipping"
        )
        return None

    _paid_attempt: dict | None = None
    _resume_task_id: str | None = None
    _submission_started = False
    try:
        from cost_tracker import CostTracker
    except Exception:
        CostTracker = None  # type: ignore[assignment,misc]
    if CostTracker is not None and isinstance(cost_tracker, CostTracker):
        from performance.runway_tasks import build_attempt_id

        attempt_id, request_fingerprint = build_attempt_id(
            provider="runway",
            engine="ACT_ONE",
            operation="performance_capture",
            video_id=video_id,
            shot_id=shot_id,
            request={
                "keyframe_path": os.path.abspath(keyframe_path),
                "driving_video_path": os.path.abspath(driving_video_path),
                "duration_s": float(duration_s),
                "model": _MODEL,
                "ratio": "1280:720",
            },
        )
        _paid_attempt = cost_tracker.reserve_paid_attempt(
            attempt_id=attempt_id,
            provider="runway",
            engine="ACT_ONE",
            operation="performance_capture",
            estimated_cost_usd=round(0.05 * float(duration_s), 4),
            shot_id=shot_id,
            video_id=video_id,
            request_fingerprint=request_fingerprint,
        )
        if not _paid_attempt.get("acquired"):
            state = str(_paid_attempt.get("state") or "")
            task_id = _paid_attempt.get("provider_job_id")
            if isinstance(task_id, str) and task_id:
                _resume_task_id = task_id
            if state in {"failed_unbilled", "cancelled", "blocked_budget"}:
                return None
            if state == "failed_billed":
                return None
            if not _resume_task_id:
                cost_tracker.update_paid_attempt(
                    attempt_id,
                    state="accepted_unknown",
                    detail=(
                        "A prior Act-Two worker claimed submission without a "
                        "durable provider task ID; duplicate submission blocked"
                    ),
                )
                return None

    def _paid_update(state: str, **kwargs) -> None:
        nonlocal _paid_attempt
        if _paid_attempt is None:
            return
        _paid_attempt = cost_tracker.update_paid_attempt(
            _paid_attempt["attempt_id"], state=state, **kwargs
        )

    def _paid_reconcile(state: str, **kwargs) -> None:
        nonlocal _paid_attempt
        if _paid_attempt is None:
            return
        _paid_attempt = cost_tracker.reconcile_paid_attempt(
            _paid_attempt["attempt_id"], state=state, **kwargs
        )

    def _keep_known_task_reserved(detail: str) -> bool:
        """Preserve ownership when an error occurs after task acceptance."""
        if not _resume_task_id:
            return False
        _paid_update(
            "accepted_unknown",
            provider_job_id=_resume_task_id,
            detail=detail,
        )
        return True

    # New submissions require the official SDK because it owns the supported
    # ephemeral-upload flow.  When the SDK is missing, _raw_rest_call may only
    # retrieve an already-durable task ID; it must never improvise a second
    # submission transport. Errors raised BY the SDK after a successful import
    # are classified below and never trigger a REST retry.
    try:
        from runwayml import RunwayML  # type: ignore
        from runwayml import (  # type: ignore
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        )
    except ImportError:
        return _raw_rest_call(
            api_key, output_mp4,
            duration_s, poll_timeout_s, shot_id, video_id,
            cost_tracker=cost_tracker,
            paid_attempt=_paid_attempt,
            resume_task_id=_resume_task_id,
        )

    try:
        # Submission is intentionally single-shot. The SDK otherwise retries
        # POST requests after connection/5xx failures without an idempotency
        # key, which can create duplicate paid tasks before any task ID reaches
        # our durable authority.
        client = RunwayML(api_key=api_key, max_retries=0)
        task_id = _resume_task_id
        if not task_id:
            # Uploads are deliberately outside the generation-submission
            # ambiguity boundary. Even if one upload succeeds and the other
            # fails, no paid Act-Two task exists; the short-lived orphan simply
            # expires. Runway's upload contract says a failed upload is not
            # retried in place, so a later invocation starts a fresh upload.
            try:
                character_uri = _ephemeral_uri(client, keyframe_path, role="character")
                reference_uri = _ephemeral_uri(client, driving_video_path, role="reference")
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                failure_code = (
                    f"UPLOAD_HTTP_{status}"
                    if isinstance(status, int)
                    else f"UPLOAD_{type(exc).__name__.upper()}"
                )
                failure_code = _evidence_token(failure_code)
                print(
                    "   [ACT-TWO] input upload failed before generation "
                    f"submission: failure_code={failure_code}"
                )
                _paid_reconcile(
                    "failed_unbilled",
                    failure_code=failure_code,
                    detail=(
                        "Runway ephemeral input upload failed before "
                        "Act-Two generation submission"
                    ),
                )
                return None

            kwargs = {
                "model": _MODEL,
                "character": {"type": "image", "uri": character_uri},
                "reference": {"type": "video", "uri": reference_uri},
                "ratio": "1280:720",
            }
            if task_submission_callback is not None:
                try:
                    task_submission_callback()
                except Exception as exc:
                    _paid_update(
                        "accepted_unknown",
                        detail=(
                            "Act-Two remote pre-submit claim was ambiguous: "
                            f"{type(exc).__name__}"
                        ),
                    )
                    print(
                        "   [ACT-TWO] durable pre-submit claim failed; "
                        "provider creation was not attempted"
                    )
                    return None
            _submission_started = True
            task = client.character_performance.create(**kwargs)
            task_id = getattr(task, "id", None)
            if not isinstance(task_id, str) or not task_id:
                print("   [ACT-TWO] accepted response had no usable task_id")
                _paid_update(
                    "accepted_unknown",
                    detail="Act-Two accepted response had no usable task ID",
                )
                return None
            _resume_task_id = task_id
            if task_acceptance_callback is not None:
                try:
                    task_acceptance_callback(task_id)
                except Exception as exc:
                    _paid_update(
                        "accepted_unknown",
                        provider_job_id=task_id,
                        detail=(
                            "Act-Two task accepted but remote task checkpoint "
                            f"failed: {type(exc).__name__}"
                        ),
                    )
                    print(
                        "   [ACT-TWO] task accepted but durable remote "
                        "checkpoint failed; polling stopped"
                    )
                    return None
            _paid_update(
                "running",
                provider_job_id=task_id,
                provider_status="PENDING",
                detail="Act-Two task accepted; polling durable task identity",
            )
            print(f"   [ACT-TWO] task accepted: task_id={_evidence_token(task_id)}")
        else:
            print(f"   [ACT-TWO] resuming task: task_id={_evidence_token(task_id)}")

        from performance.runway_tasks import call_with_backoff, classify_task_failure

        elapsed = 0
        while True:
            try:
                final_task = call_with_backoff(
                    lambda: client.tasks.retrieve(id=task_id),
                    attempts=4,
                    base_delay_s=0.5,
                )
            except Exception as exc:
                print(
                    "   [ACT-TWO] task retrieval remained ambiguous: "
                    f"task_id={_evidence_token(task_id)} "
                    f"error={_evidence_token(type(exc).__name__)}"
                )
                _paid_update(
                    "accepted_unknown",
                    provider_job_id=task_id,
                    detail=f"Act-Two retrieval remained ambiguous: {type(exc).__name__}",
                )
                return None
            final_status = str(getattr(final_task, "status", "") or "").upper()
            if final_status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            if elapsed >= poll_timeout_s:
                print(
                    "   [ACT-TWO] local poll timeout; provider still owns task: "
                    f"task_id={_evidence_token(task_id)} "
                    f"status={_evidence_token(final_status)}"
                )
                _paid_update(
                    "accepted_unknown",
                    provider_job_id=task_id,
                    provider_status=final_status or "UNKNOWN",
                    detail="Act-Two still owns the shot after local poll timeout",
                )
                return None
            _paid_update(
                "running",
                provider_job_id=task_id,
                provider_status=final_status or "PENDING",
                detail="Act-Two task is still running",
            )
            time.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S

        if final_status == "CANCELLED":
            print(f"   [ACT-TWO] task cancelled: task_id={_evidence_token(task_id)}")
            _paid_reconcile(
                "cancelled",
                provider_job_id=task_id,
                provider_status=final_status,
                detail="Runway reported terminal Act-Two cancellation",
            )
            return None
        if final_status == "FAILED":
            failure = classify_task_failure(final_task)
            failure_code = _evidence_token(failure["code"])
            print(
                "   [ACT-TWO] task failed: "
                f"task_id={_evidence_token(task_id)} "
                f"failure_code={failure_code}"
            )
            _paid_reconcile(
                "failed_billed" if failure["billed"] else "failed_unbilled",
                provider_job_id=task_id,
                provider_status=final_status,
                failure_code=failure_code,
                detail="Runway reported terminal Act-Two failure",
            )
            return None
        output = getattr(final_task, "output", None)
        out_url = (output or [None])[0]
        if not out_url:
            print(
                "   [ACT-TWO] task succeeded without output URL: "
                f"task_id={_evidence_token(task_id)}"
            )
            _paid_update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two succeeded without a usable output URL",
                billed=True,
            )
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
            print(
                "   [ACT-TWO] output reconciliation failed: "
                f"task_id={_evidence_token(task_id)}"
            )
            _paid_update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two succeeded but local download reconciliation failed",
                billed=True,
            )
            return None
        if _paid_attempt is not None:
            _paid_reconcile(
                "succeeded",
                actual_cost_usd=round(0.05 * float(duration_s), 4),
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two output reconciled locally",
            )
        else:
            _cost_log(
                "performance_capture",
                duration_s,
                shot_id,
                video_id,
                cost_tracker=cost_tracker,
                provider_job_id=task_id,
            )
        print(f"   ✅ Act-Two: {output_mp4}")
        return output_mp4
    except AuthenticationError as e:
        print("   [ACT-TWO] SDK auth error (bad/expired RUNWAYML_API_SECRET)")
        if not _keep_known_task_reserved(
            "Act-Two accepted task could not be retrieved after authentication failed"
        ):
            _paid_reconcile(
                "failed_unbilled",
                failure_code="AUTHENTICATION_ERROR",
                detail=type(e).__name__,
            )
        return None
    except BadRequestError as e:
        print("   [ACT-TWO] SDK rejected the request (bad params)")
        if not _keep_known_task_reserved(
            "Act-Two accepted task retrieval returned a bad-request response"
        ):
            _paid_reconcile(
                "failed_unbilled",
                failure_code="BAD_REQUEST",
                detail=type(e).__name__,
            )
        return None
    except RateLimitError as e:
        print("   [ACT-TWO] SDK rate-limited")
        if not _keep_known_task_reserved(
            "Act-Two accepted task retrieval remained rate-limited"
        ):
            _paid_reconcile(
                "failed_unbilled",
                failure_code="RATE_LIMIT",
                detail=type(e).__name__,
            )
        return None
    except APIConnectionError as e:
        print(f"   [ACT-TWO] SDK connection error: {type(e).__name__}")
        _paid_update(
            "accepted_unknown",
            provider_job_id=_resume_task_id,
            detail="Act-Two submission/retrieval connection outcome is ambiguous",
        )
        return None
    except APIStatusError as e:
        status = getattr(e, "status_code", "?")
        print(f"   [ACT-TWO] SDK API error (status={status})")
        if _keep_known_task_reserved(
            f"Act-Two accepted task retrieval returned HTTP {status}"
        ):
            pass
        elif status in {400, 401, 403, 422}:
            _paid_reconcile(
                "failed_unbilled",
                failure_code=f"HTTP_{status}",
                detail=type(e).__name__,
            )
        else:
            _paid_update(
                "accepted_unknown",
                provider_job_id=_resume_task_id,
                detail=f"Act-Two API outcome is ambiguous (HTTP {status})",
            )
        return None
    except Exception as e:
        print(
            "   [ACT-TWO] SDK call failed with unexpected error "
            f"({type(e).__name__})"
        )
        if _resume_task_id or _submission_started:
            _paid_update(
                "accepted_unknown",
                provider_job_id=_resume_task_id,
                detail=(
                    "Act-Two submission outcome is ambiguous after local "
                    f"{type(e).__name__}"
                ),
            )
        else:
            _paid_reconcile(
                "failed_unbilled",
                failure_code=type(e).__name__.upper()[:128],
                detail=type(e).__name__,
            )
        return None


def _raw_rest_call(
    api_key: str, output_mp4: str,
    duration_s: float, poll_timeout_s: int, shot_id: str, video_id: str,
    cost_tracker=None,
    paid_attempt: Optional[dict] = None,
    resume_task_id: Optional[str] = None,
) -> Optional[str]:
    """Retrieve a durable Act-Two task when the official SDK is unavailable.

    New submissions fail closed: local inputs require the SDK's official
    ephemeral-upload transport, and inventing a second raw submission path
    would reopen duplicate-paid-work and asset-contract ambiguity. GET polling
    an already-recorded task ID remains safe and idempotent.
    """
    import requests

    def _update(state: str, **kwargs) -> Optional[dict]:
        nonlocal paid_attempt
        if not paid_attempt:
            return None
        paid_attempt = cost_tracker.update_paid_attempt(
            paid_attempt["attempt_id"], state=state, **kwargs
        )
        return paid_attempt

    def _reconcile(state: str, **kwargs) -> Optional[dict]:
        nonlocal paid_attempt
        if not paid_attempt:
            return None
        paid_attempt = cost_tracker.reconcile_paid_attempt(
            paid_attempt["attempt_id"], state=state, **kwargs
        )
        return paid_attempt

    task_id = resume_task_id
    if not task_id:
        print(
            "   [ACT-TWO/REST] SDK unavailable; refusing new Act-Two "
            "submission before paid work"
        )
        _reconcile(
            "failed_unbilled",
            failure_code="SDK_UNAVAILABLE",
            detail=(
                "Official Runway SDK unavailable; new Act-Two submission "
                "requires ephemeral input uploads"
            ),
        )
        return None

    print(f"   [ACT-TWO/REST] resuming task: task_id={_evidence_token(task_id)}")
    try:
        def _get_status_rest():
            tr = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {api_key}", "X-Runway-Version": _RUNWAY_API_VERSION},
                timeout=15,
            )
            if not tr.ok:
                raise requests.HTTPError(
                    f"Runway REST retrieve HTTP {tr.status_code}",
                    response=tr,
                )
            return tr.json()

        from performance.runway_tasks import call_with_backoff

        elapsed = 0
        while True:
            try:
                final = call_with_backoff(
                    _get_status_rest,
                    attempts=4,
                    base_delay_s=0.5,
                )
            except Exception as exc:
                print(
                    "   [ACT-TWO/REST] task retrieval remained ambiguous: "
                    f"task_id={_evidence_token(task_id)} "
                    f"error={_evidence_token(type(exc).__name__)}"
                )
                _update(
                    "accepted_unknown",
                    provider_job_id=task_id,
                    detail=f"Act-Two REST retrieval ambiguous: {type(exc).__name__}",
                )
                return None
            final_status = str(final.get("status") or "").upper()
            if final_status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            if elapsed >= poll_timeout_s:
                print(
                    "   [ACT-TWO/REST] local poll timeout; provider still owns task: "
                    f"task_id={_evidence_token(task_id)} "
                    f"status={_evidence_token(final_status)}"
                )
                _update(
                    "accepted_unknown",
                    provider_job_id=task_id,
                    provider_status=final_status or "UNKNOWN",
                    detail="Act-Two REST task still owns shot after poll timeout",
                )
                return None
            _update(
                "running",
                provider_job_id=task_id,
                provider_status=final_status or "PENDING",
                detail="Act-Two REST task is still running",
            )
            time.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S

        if final_status == "CANCELLED":
            print(f"   [ACT-TWO/REST] task cancelled: task_id={_evidence_token(task_id)}")
            _reconcile(
                "cancelled",
                provider_job_id=task_id,
                provider_status=final_status,
                detail="Runway reported terminal Act-Two cancellation",
            )
            return None
        if final_status == "FAILED":
            code = str(
                final.get("failureCode")
                or final.get("failure_code")
                or final.get("failure")
                or "UNKNOWN_FAILURE"
            )
            code = _evidence_token(code.upper())
            billed = any(marker in code for marker in ("SAFETY", "MODERAT", "CONTENT_POLICY"))
            print(
                "   [ACT-TWO/REST] task failed: "
                f"task_id={_evidence_token(task_id)} failure_code={code}"
            )
            _reconcile(
                "failed_billed" if billed else "failed_unbilled",
                provider_job_id=task_id,
                provider_status=final_status,
                failure_code=code,
                detail="Runway reported terminal Act-Two REST failure",
            )
            return None
        out_url = (final.get("output") or [None])[0]
        if not out_url:
            print(
                "   [ACT-TWO/REST] task succeeded without output URL: "
                f"task_id={_evidence_token(task_id)}"
            )
            _update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two REST succeeded without output URL",
                billed=True,
            )
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
            print(
                "   [ACT-TWO/REST] output reconciliation failed: "
                f"task_id={_evidence_token(task_id)}"
            )
            _update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two REST output download reconciliation failed",
                billed=True,
            )
            return None
        if paid_attempt:
            _reconcile(
                "succeeded",
                actual_cost_usd=round(0.05 * float(duration_s), 4),
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two REST output reconciled locally",
            )
        else:
            _cost_log(
                "performance_capture",
                duration_s,
                shot_id,
                video_id,
                cost_tracker=cost_tracker,
                provider_job_id=task_id,
            )
        print(f"   ✅ Act-Two (REST): {output_mp4}")
        return output_mp4
    except Exception as e:
        print(f"   [ACT-TWO/REST] failed: {e}")
        existing_task_id = locals().get("task_id")
        if existing_task_id:
            _update(
                "accepted_unknown",
                provider_job_id=existing_task_id,
                detail=f"Act-Two REST accepted task hit {type(e).__name__}",
            )
        return None

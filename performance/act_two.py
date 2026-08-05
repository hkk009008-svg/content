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
    field, so it has been removed from the outgoing request entirely (both
    the SDK kwargs and the REST fallback body). ``duration_s`` remains a
    Python-side keyword, used only for the $/s cost estimate — it is never
    forwarded to Runway.
  - Optional knobs the endpoint DOES offer but this adapter does not yet
    wire: ``body_control`` (bool), ``content_moderation``,
    ``expression_intensity`` (1-5 int), ``seed``.
  - ``uri`` for both ``character`` and ``reference`` is a LOCAL FILESYSTEM
    PATH at the call sites in this module (``keyframe_path`` /
    ``driving_video_path``) — Runway obviously cannot fetch a path off this
    machine's disk. This adapter encodes each local file as an RFC 2397
    ``data:<mime>;base64,<...>`` URI (see ``_to_data_uri`` below) rather than
    passing the path through, since the SDK's own type stubs document `uri`
    as "A HTTPS URL." with no separate local-file/upload parameter on
    ``character_performance.create()``.

API surface:
  - POST https://api.dev.runwayml.com/v1/character_performance
  - GET  https://api.dev.runwayml.com/v1/tasks/{id}  (polled until done)

Auth: bearer token = settings.runwayml_api_secret (already configured for
the existing Runway Gen-4 integration).
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from typing import Optional

from config.settings import settings
from performance._net import safe_download, validate_video_artifact


_POLL_INTERVAL_S = 3
_MODEL = "act_two"
_RUNWAY_API_VERSION = "2024-11-06"

# Conservative pre-encode size cap for inline data-URI payloads. The installed
# runwayml SDK (v4.14.0) does NOT document a data-URI byte limit anywhere —
# `character_performance_create_params.py` types `uri` only as "A HTTPS URL.",
# and grepping the SDK's types/, resources/, and dist-info METADATA for
# "data:", "base64", or a size figure turns up nothing. This cap is therefore
# THIS ADAPTER's own safety bound, not a documented Runway limit: base64
# inflates a payload by ~4/3, and `reference` videos can run up to 30s, so an
# unbounded inline encode risks a multi-hundred-MB JSON request body. Fail
# loudly before sending rather than hang on an oversized request or have an
# intermediate proxy silently truncate it.
# 15 MB pre-encode (~20 MB after base64). This is this adapter's OWN safety
# bound, not a documented Runway limit. For larger assets the installed SDK
# exposes uploads.create_ephemeral() (asset upload, no inline cap) — the
# future no-cap path if real driving videos outgrow inline data-URIs.
_MAX_INLINE_BYTES = 15 * 1024 * 1024


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

    # Prefer the official SDK when available; fall through to raw REST only
    # on ImportError (SDK package missing) — a transport swap that sends the
    # exact same act_two contract (see _raw_rest_call). Errors raised BY the
    # SDK after a successful import (auth, malformed request, rate limit,
    # network, ...) are classified below and returned as None WITHOUT a REST
    # retry: REST would hit the same API with the same credentials/payload
    # and fail the same way, so retrying there would not change the outcome
    # — only hide which failure mode actually happened. That classification
    # IS the "no silent conceal" contract for this adapter.
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
            api_key, keyframe_path, driving_video_path, output_mp4,
            duration_s, poll_timeout_s, shot_id, video_id,
            cost_tracker=cost_tracker,
            paid_attempt=_paid_attempt,
            resume_task_id=_resume_task_id,
        )

    try:
        character_uri = _to_data_uri(keyframe_path)
        reference_uri = _to_data_uri(driving_video_path)
    except (OSError, ValueError) as e:
        print(f"   [ACT-TWO] failed to encode input as a data URI: {e}")
        return None

    try:
        client = RunwayML(api_key=api_key)
        kwargs = {
            "model": _MODEL,
            "character": {"type": "image", "uri": character_uri},
            "reference": {"type": "video", "uri": reference_uri},
            "ratio": "1280:720",
        }
        task_id = _resume_task_id
        if not task_id:
            create_attempt = 0
            while True:
                try:
                    task = client.character_performance.create(**kwargs)
                    break
                except RateLimitError as exc:
                    create_attempt += 1
                    if create_attempt >= 4:
                        raise
                    from performance.runway_tasks import retry_delay_seconds

                    time.sleep(retry_delay_seconds(exc, create_attempt - 1))
            task_id = getattr(task, "id", None)
            if not isinstance(task_id, str) or not task_id:
                _paid_update(
                    "accepted_unknown",
                    detail="Act-Two accepted response had no usable task ID",
                )
                return None
            _resume_task_id = task_id
            _paid_update(
                "running",
                provider_job_id=task_id,
                provider_status="PENDING",
                detail="Act-Two task accepted; polling durable task identity",
            )

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
            _paid_reconcile(
                "cancelled",
                provider_job_id=task_id,
                provider_status=final_status,
                detail="Runway reported terminal Act-Two cancellation",
            )
            return None
        if final_status == "FAILED":
            failure = classify_task_failure(final_task)
            _paid_reconcile(
                "failed_billed" if failure["billed"] else "failed_unbilled",
                provider_job_id=task_id,
                provider_status=final_status,
                failure_code=str(failure["code"]),
                detail="Runway reported terminal Act-Two failure",
            )
            return None
        output = getattr(final_task, "output", None)
        out_url = (output or [None])[0]
        if not out_url:
            print("   [ACT-TWO] SUCCEEDED but no output URL")
            _paid_update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two succeeded without a usable output URL",
                billed=True,
            )
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
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
        print(f"   [ACT-TWO] SDK auth error (bad/expired RUNWAYML_API_SECRET): {e}")
        _paid_reconcile("failed_unbilled", failure_code="AUTHENTICATION_ERROR", detail=str(e))
        return None
    except BadRequestError as e:
        print(f"   [ACT-TWO] SDK rejected the request (bad params): {e}")
        _paid_reconcile("failed_unbilled", failure_code="BAD_REQUEST", detail=str(e))
        return None
    except RateLimitError as e:
        print(f"   [ACT-TWO] SDK rate-limited: {e}")
        _paid_reconcile("failed_unbilled", failure_code="RATE_LIMIT", detail=str(e))
        return None
    except APIConnectionError as e:
        print(f"   [ACT-TWO] SDK connection error: {e}")
        _paid_update(
            "accepted_unknown",
            provider_job_id=_resume_task_id,
            detail="Act-Two submission/retrieval connection outcome is ambiguous",
        )
        return None
    except APIStatusError as e:
        status = getattr(e, "status_code", "?")
        print(f"   [ACT-TWO] SDK API error (status={status}): {e}")
        if status in {400, 401, 403, 422}:
            _paid_reconcile(
                "failed_unbilled",
                failure_code=f"HTTP_{status}",
                detail=str(e),
            )
        else:
            _paid_update(
                "accepted_unknown",
                provider_job_id=_resume_task_id,
                detail=f"Act-Two API outcome is ambiguous (HTTP {status})",
            )
        return None
    except Exception as e:
        print(f"   [ACT-TWO] SDK call failed with unexpected error ({type(e).__name__}): {e}")
        if _resume_task_id:
            _paid_update(
                "accepted_unknown",
                provider_job_id=_resume_task_id,
                detail=f"Act-Two accepted task hit local {type(e).__name__}",
            )
        else:
            _paid_reconcile(
                "failed_unbilled",
                failure_code=type(e).__name__.upper()[:128],
                detail=str(e),
            )
        return None


def _to_data_uri(path: str) -> str:
    """Encode a local file as an RFC 2397 ``data:<mime>;base64,<...>`` URI.

    Used for both ``character.uri`` and ``reference.uri`` — the SDK's typed
    params document ``uri`` as "A HTTPS URL." with no separate local-file
    parameter, and this adapter has no asset-upload step, so a real data URI
    (not a bare filesystem path, which Runway's servers cannot dereference)
    is the only way to hand Runway a local keyframe/driving-video file.

    Raises:
        OSError: the file cannot be stat'd or read (missing/permissions).
        ValueError: the file exceeds ``_MAX_INLINE_BYTES`` — callers must
            fail the request loudly rather than attempt an inline payload
            this large (see ``_MAX_INLINE_BYTES`` for why the cap exists).
    """
    size = os.path.getsize(path)
    if size > _MAX_INLINE_BYTES:
        raise ValueError(
            f"{path} is {size} bytes, over the {_MAX_INLINE_BYTES}-byte "
            f"inline data-URI cap for Act-Two requests"
        )
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "application/octet-stream"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _raw_rest_call(
    api_key: str, keyframe_path: str, reference_video_path: str, output_mp4: str,
    duration_s: float, poll_timeout_s: int, shot_id: str, video_id: str,
    cost_tracker=None,
    paid_attempt: Optional[dict] = None,
    resume_task_id: Optional[str] = None,
) -> Optional[str]:
    """Raw REST fallback for when the ``runwayml`` package isn't installed.

    Sends the SAME act_two contract as the SDK path above: model="act_two",
    a video `reference` (Act-Two has no audio-reference mode — see module
    docstring), and no `duration` field (the endpoint doesn't accept one).
    The precondition (reference_video_path exists) is already checked by
    the caller before this is invoked.

    Returns None on any failure — graceful for the cascade.
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

    try:
        character_uri = _to_data_uri(keyframe_path)
        reference_uri = _to_data_uri(reference_video_path)
    except (OSError, ValueError) as e:
        print(f"   [ACT-TWO/REST] failed to encode input as a data URI: {e}")
        return None

    try:
        body = {
            "model": _MODEL,
            "character": {"type": "image", "uri": character_uri},
            "reference": {"type": "video", "uri": reference_uri},
            "ratio": "1280:720",
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Runway-Version": _RUNWAY_API_VERSION,
            "Content-Type": "application/json",
        }
        task_id = resume_task_id
        if not task_id:
            post_attempt = 0
            while True:
                r = requests.post(
                    "https://api.dev.runwayml.com/v1/character_performance",
                    json=body,
                    headers=headers,
                    timeout=60,
                )
                if r.status_code != 429 or post_attempt >= 3:
                    break
                from types import SimpleNamespace
                from performance.runway_tasks import retry_delay_seconds

                time.sleep(
                    retry_delay_seconds(
                        SimpleNamespace(response=r),
                        post_attempt,
                    )
                )
                post_attempt += 1
            if r.status_code not in (200, 201, 202):
                print(f"   [ACT-TWO/REST] HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code in {400, 401, 403, 422, 429}:
                    _reconcile(
                        "failed_unbilled",
                        failure_code=f"HTTP_{r.status_code}",
                        detail="Runway REST submission rejected",
                    )
                else:
                    _update(
                        "accepted_unknown",
                        detail=f"Runway REST submission outcome ambiguous (HTTP {r.status_code})",
                    )
                return None
            task_id = r.json().get("id")
            if not isinstance(task_id, str) or not task_id:
                _update(
                    "accepted_unknown",
                    detail="Runway REST accepted response had no usable task ID",
                )
                return None
            _update(
                "running",
                provider_job_id=task_id,
                provider_status="PENDING",
                detail="Act-Two REST task accepted",
            )

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
            ).upper()[:128]
            billed = any(marker in code for marker in ("SAFETY", "MODERAT", "CONTENT_POLICY"))
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
            _update(
                "accepted_unknown",
                provider_job_id=task_id,
                provider_status="SUCCEEDED",
                detail="Act-Two REST succeeded without output URL",
                billed=True,
            )
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
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
        else:
            _update(
                "accepted_unknown",
                detail=f"Act-Two REST submission outcome ambiguous: {type(e).__name__}",
            )
        return None

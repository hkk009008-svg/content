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
from typing import Optional

from config.settings import settings
from performance._net import safe_download, validate_video_artifact
from performance._poll import poll_task


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


def _cost_log(operation: str, duration_s: float, shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
    """Best-effort cost log. Doesn't fail the call if tracking isn't wired."""
    try:
        from cost_tracker import CostTracker
        # Runway Act-Two: ~$0.05/s of output video (confirm with their pricing page)
        (cost_tracker or CostTracker()).log_api(
            provider="runway",
            model=_MODEL,
            operation=operation,
            cost_usd=round(0.05 * float(duration_s), 4),
            shot_id=shot_id,
            video_id=video_id,
        )
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
        task = client.character_performance.create(**kwargs)

        def _get_status_sdk():
            t = client.tasks.retrieve(id=task.id)
            return {
                "status": (getattr(t, "status", "") or "").upper(),
                "output": getattr(t, "output", None),
                "failure": getattr(t, "failure", None),
            }

        final = poll_task(
            _get_status_sdk,
            success_states={"SUCCEEDED"},
            terminal_states={"FAILED", "CANCELLED"},
            interval_s=_POLL_INTERVAL_S,
            timeout_s=poll_timeout_s,
        )
        if final is None:
            print(f"   [ACT-TWO] poll terminal or timed out")
            return None
        out_url = (final.get("output") or [None])[0]
        if not out_url:
            print("   [ACT-TWO] SUCCEEDED but no output URL")
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
            return None
        _cost_log("performance_capture", duration_s, shot_id, video_id, cost_tracker=cost_tracker)
        print(f"   ✅ Act-Two: {output_mp4}")
        return output_mp4
    except AuthenticationError as e:
        print(f"   [ACT-TWO] SDK auth error (bad/expired RUNWAYML_API_SECRET): {e}")
        return None
    except BadRequestError as e:
        print(f"   [ACT-TWO] SDK rejected the request (bad params): {e}")
        return None
    except RateLimitError as e:
        print(f"   [ACT-TWO] SDK rate-limited: {e}")
        return None
    except APIConnectionError as e:
        print(f"   [ACT-TWO] SDK connection error: {e}")
        return None
    except APIStatusError as e:
        status = getattr(e, "status_code", "?")
        print(f"   [ACT-TWO] SDK API error (status={status}): {e}")
        return None
    except Exception as e:
        print(f"   [ACT-TWO] SDK call failed with unexpected error ({type(e).__name__}): {e}")
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

        r = requests.post(
            "https://api.dev.runwayml.com/v1/character_performance",
            json=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Runway-Version": _RUNWAY_API_VERSION,
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        if r.status_code not in (200, 201, 202):
            print(f"   [ACT-TWO/REST] HTTP {r.status_code}: {r.text[:200]}")
            return None
        task_id = r.json().get("id")
        if not task_id:
            return None

        def _get_status_rest():
            tr = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {api_key}", "X-Runway-Version": _RUNWAY_API_VERSION},
                timeout=15,
            )
            if not tr.ok:
                return {"status": "PENDING"}
            body = tr.json()
            return {
                "status": (body.get("status") or "").upper(),
                "output": body.get("output"),
            }

        final = poll_task(
            _get_status_rest,
            success_states={"SUCCEEDED"},
            terminal_states={"FAILED", "CANCELLED"},
            interval_s=_POLL_INTERVAL_S,
            timeout_s=poll_timeout_s,
        )
        if final is None:
            return None
        out_url = (final.get("output") or [None])[0]
        if not out_url:
            return None
        if not safe_download(out_url, output_mp4, allowed_content_types=("video/mp4",), content_validator=validate_video_artifact):
            return None
        _cost_log("performance_capture", duration_s, shot_id, video_id, cost_tracker=cost_tracker)
        print(f"   ✅ Act-Two (REST): {output_mp4}")
        return output_mp4
    except Exception as e:
        print(f"   [ACT-TWO/REST] failed: {e}")
        return None

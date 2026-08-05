"""Viggle — full-body motion retargeting.

Driving video shows a human performing an action; Viggle maps the motion
onto the character in the keyframe. Best for non-dialogue action beats —
running, fighting, dancing, gesturing.

Requires:
  - VIGGLE_API_KEY env var
  - operator-uploaded driving_video_path (Mode A only — Viggle doesn't
    auto-generate driving from audio)

API surface (official developer API, confirmed via WebFetch to
https://docs.viggle.ai — viggle.ai itself 403s bots, so docs.viggle.ai is the
only fetchable source):
  - POST https://apis.viggle.ai/v1/renders
      multipart fields:
        image           (character keyframe; docs also allow image_url,
                          not used here — this adapter always has a local
                          keyframe file, never a remote URL)
        motion_video     (driving video; docs also allow motion_video_url,
                          same rationale — not used here)
        background_mode  "original" (default) | "solid" | "transparent"
        bg_color         "R,G,B" string — only meaningful when
                          background_mode == "solid"
      creation response: {"status": "queued", "id": ..., "progress": ...,
                          "created_at": ...}
  - GET  https://apis.viggle.ai/v1/renders/{id}   (poll until terminal)
      response: {"status": "ready" | "failed" | "cancelled", "video_url":
                 ..., "alpha_url": ... (transparent mode only)}
  - Auth: Authorization: Bearer <VIGGLE_API_KEY>

This repairs the pre-official-API adapter that this module used to target
(api.viggle.ai/v1/motion-transfer, files={character_image, motion_video},
background_mode white|green|transparent, and a "background" field name that
didn't even match that pre-official shape) — see domain/provider_catalog.py's
VIGGLE catalog entry for the full before/after mismatch table this fixes.

The catalog entry (domain/provider_catalog.py) and the rule-3 routing
containment (domain/performance.py) are NOT flipped back by this repair —
see those files' comments for why the containment stays in place even
though the adapter itself is now correct.
"""

from __future__ import annotations

import os
from typing import Optional

from config.settings import settings
from cost_tracker_lifecycle import cost_tracker_scope
from paid_provider import has_paid_attempt_authority
from performance._net import safe_download, validate_video_artifact
from performance._poll import poll_task


_POLL_INTERVAL_S = 3
_RENDERS_URL = "https://apis.viggle.ai/v1/renders"

# docs.viggle.ai's documented background_mode values. "white" / "green" —
# the pre-official adapter's values — are no longer valid inputs.
_VALID_BACKGROUND_MODES = frozenset({"original", "solid", "transparent"})


def _cost_log(shot_id: str = "", video_id: str = "", cost_tracker=None) -> None:
    """Viggle is per-clip pricing (~$0.10–$0.25)."""
    try:
        with cost_tracker_scope(cost_tracker) as tracker:
            tracker.log_api(
                provider="viggle",
                model="motion_retarget",
                operation="performance_capture",
                cost_usd=0.20,
                shot_id=shot_id,
                video_id=video_id,
            )
    except Exception:
        pass  # Cost tracking is best-effort — import or write failure doesn't fail the render


def generate_viggle_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    background_mode: str = "original",   # 'original' | 'solid' | 'transparent'
    bg_color: Optional[str] = None,      # "R,G,B" — only sent when background_mode == "solid"
    shot_id: str = "",
    video_id: str = "",
    request_id: str = "",
    poll_timeout_s: int = 300,
    cost_tracker=None,
) -> Optional[str]:
    """Viggle motion retargeting via the official apis.viggle.ai/v1/renders contract.

    Driving video is mandatory — Viggle has no audio-only synthesis mode.

    Returns the local output path on success, None on any failure (graceful —
    the dispatch cascade falls through to text-to-video on None). Every
    failure path below is logged with a distinguishing [VIGGLE] reason
    instead of one generic catch-all message, so callers can grep which
    failure mode actually happened.
    """
    api_key = getattr(settings, "viggle_api_key", "") or os.environ.get("VIGGLE_API_KEY", "")
    if not api_key:
        print("   [VIGGLE] VIGGLE_API_KEY not set; skipping")
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        print(f"   [VIGGLE] keyframe missing: {keyframe_path}")
        return None
    if not (driving_video_path and os.path.exists(driving_video_path)):
        print(f"   [VIGGLE] driving video missing: {driving_video_path}")
        return None
    if background_mode not in _VALID_BACKGROUND_MODES:
        print(
            f"   [VIGGLE] invalid background_mode {background_mode!r}; "
            f"must be one of {sorted(_VALID_BACKGROUND_MODES)}"
        )
        return None

    try:
        import requests
    except ImportError as e:
        print(f"   [VIGGLE] 'requests' package not available: {e}")
        return None

    auth_headers = {"Authorization": f"Bearer {api_key}"}
    durable = has_paid_attempt_authority(cost_tracker)
    attempt: dict = {}
    attempt_id = ""
    stable_request = ""
    render_id = ""

    def _mark_unknown(detail: str, *, provider_job_id: str = "") -> None:
        nonlocal attempt
        if not durable:
            return
        try:
            current = cost_tracker.get_paid_attempt(attempt_id) or attempt
        except Exception:
            current = attempt
        if current.get("state") in {
            "succeeded", "failed_billed", "failed_unbilled", "cancelled",
        }:
            attempt = dict(current)
            return
        try:
            attempt = cost_tracker.update_paid_attempt(
                attempt_id,
                state="accepted_unknown",
                provider_job_id=provider_job_id or None,
                provider_status="outcome_unknown",
                detail=detail,
            )
        except Exception:
            # The pre-existing submitting/running row remains a no-replay
            # fence even when this best-effort detail update fails.
            attempt = dict(current)

    if durable:
        from cost_tracker import API_COST_USD
        from paid_provider import file_fingerprint, paid_attempt_id, request_fingerprint

        try:
            stable_request = request_fingerprint(
                "viggle-motion-retarget",
                file_fingerprint(keyframe_path),
                file_fingerprint(driving_video_path),
                background_mode,
                bg_color if background_mode == "solid" else None,
                request_id,
            )
            attempt_id = paid_attempt_id(
                "viggle-render",
                video_id,
                shot_id,
                stable_request,
            )
            attempt = cost_tracker.reserve_paid_attempt(
                attempt_id=attempt_id,
                provider="viggle",
                engine="VIGGLE",
                operation="performance_capture",
                estimated_cost_usd=API_COST_USD["VIGGLE"],
                shot_id=shot_id,
                video_id=video_id,
                request_fingerprint=stable_request,
            )
        except Exception as exc:
            print(f"   [VIGGLE] durable reservation failed: {exc}")
            return None
        if not attempt.get("acquired"):
            if str(attempt.get("request_fingerprint") or "") != stable_request:
                print("   [VIGGLE] paid-attempt key conflicts with different inputs")
                return None
            state = str(attempt.get("state") or "")
            if state == "blocked_budget":
                print("   [VIGGLE] atomic budget reservation refused; skipping submission")
                return None
            if state in {"failed_unbilled", "cancelled"}:
                print(f"   [VIGGLE] prior render is terminal and unbilled ({state})")
                return None
            if state == "failed_billed":
                print("   [VIGGLE] prior render failed after billing; no replacement started")
                return None
            render_id = str(attempt.get("provider_job_id") or "")
            if not render_id:
                _mark_unknown(
                    "Viggle submission may have been accepted without a durable render ID"
                )
                print("   [VIGGLE] prior submission has no recoverable render id")
                return None

    # NOTE: don't set Content-Type explicitly when using files= — requests
    # generates the multipart boundary; setting it manually breaks the request.
    if not render_id:
        try:
            with open(keyframe_path, "rb") as kf, open(driving_video_path, "rb") as dv:
                files = {
                    "image": kf,
                    "motion_video": dv,
                }
                data = {"background_mode": background_mode}
                if background_mode == "solid" and bg_color:
                    data["bg_color"] = bg_color
                r = requests.post(
                    _RENDERS_URL, headers=auth_headers, files=files, data=data, timeout=120,
                )
        except requests.exceptions.Timeout as e:
            _mark_unknown(
                "Viggle submit timed out after entering the paid boundary"
            )
            print(f"   [VIGGLE] render request timed out: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            _mark_unknown(
                "Viggle submit connection failed with unknown provider acceptance"
            )
            print(f"   [VIGGLE] render request connection error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            _mark_unknown(
                "Viggle submit failed with unknown provider acceptance"
            )
            print(f"   [VIGGLE] render request failed ({type(e).__name__}): {e}")
            return None

        if r.status_code in (401, 403):
            if durable:
                attempt = cost_tracker.reconcile_paid_attempt(
                    attempt_id,
                    state="failed_unbilled",
                    provider_status="rejected",
                    failure_code=f"http_{r.status_code}",
                    detail="Viggle authentication rejected before render acceptance",
                )
            print(f"   [VIGGLE] auth rejected (HTTP {r.status_code}): {r.text[:200]}")
            return None
        if r.status_code == 429:
            if durable:
                attempt = cost_tracker.reconcile_paid_attempt(
                    attempt_id,
                    state="failed_unbilled",
                    provider_status="rate_limited",
                    failure_code="http_429",
                    detail="Viggle rate-limited submission before render acceptance",
                )
            print(f"   [VIGGLE] rate-limited (HTTP 429): {r.text[:200]}")
            return None
        if r.status_code not in (200, 201, 202):
            if 400 <= r.status_code < 500 and durable:
                attempt = cost_tracker.reconcile_paid_attempt(
                    attempt_id,
                    state="failed_unbilled",
                    provider_status="rejected",
                    failure_code=f"http_{r.status_code}",
                    detail="Viggle rejected submission before render acceptance",
                )
            else:
                _mark_unknown(
                    f"Viggle submission returned HTTP {r.status_code}; acceptance unknown"
                )
            print(f"   [VIGGLE] HTTP {r.status_code}: {r.text[:200]}")
            return None

        try:
            body = r.json()
        except ValueError as e:
            _mark_unknown("Viggle accepted response was not valid JSON")
            print(f"   [VIGGLE] creation response was not valid JSON: {e}")
            return None

        render_id = str(body.get("id") or "")
        if not render_id:
            _mark_unknown("Viggle accepted response omitted the durable render ID")
            print(f"   [VIGGLE] creation response missing 'id': {body}")
            return None
        if durable:
            try:
                attempt = cost_tracker.update_paid_attempt(
                    attempt_id,
                    state="running",
                    provider_job_id=render_id,
                    provider_status=str(body.get("status") or "queued")[:128],
                    detail="Viggle render ID acknowledged; polling exact render",
                )
            except Exception:
                _mark_unknown(
                    "Viggle render ID was acknowledged but could not be durably recorded",
                    provider_job_id=render_id,
                )
                print("   [VIGGLE] render id could not be persisted; polling stopped")
                return None

    def _get_status():
        pr = requests.get(
            f"{_RENDERS_URL}/{render_id}",
            headers=auth_headers,
            timeout=15,
        )
        if not pr.ok:
            # Transient poll failure — poll_task tolerates this and keeps
            # going; "PENDING" is a synthetic non-terminal placeholder, not
            # a real Viggle status.
            return {"status": "PENDING"}
        pb = pr.json()
        return {
            "status": (pb.get("status") or "").upper(),
            "video_url": pb.get("video_url"),
        }

    final = poll_task(
        _get_status,
        success_states={"READY"},
        terminal_states={"FAILED", "CANCELLED"},
        interval_s=_POLL_INTERVAL_S,
        timeout_s=poll_timeout_s,
    )
    if final is None:
        _mark_unknown(
            "Viggle render is terminal or exceeded the local poll deadline; billing outcome requires recovery",
            provider_job_id=render_id,
        )
        print(f"   [VIGGLE] render {render_id} did not finish (failed, cancelled, or timed out)")
        return None

    out_url = final.get("video_url")
    if not out_url:
        _mark_unknown(
            "Viggle reported READY without a downloadable video URL",
            provider_job_id=render_id,
        )
        print(f"   [VIGGLE] render {render_id} is ready but response has no video_url")
        return None
    if durable and str(attempt.get("state") or "") != "succeeded":
        from cost_tracker import API_COST_USD

        try:
            attempt = cost_tracker.reconcile_paid_attempt(
                attempt_id,
                state="succeeded",
                actual_cost_usd=API_COST_USD["VIGGLE"],
                provider_job_id=render_id,
                provider_status="ready",
                detail="Viggle render completed",
            )
        except Exception:
            _mark_unknown(
                "Viggle completed but cost reconciliation failed",
                provider_job_id=render_id,
            )
            print("   [VIGGLE] render completed but accounting reconciliation failed")
            return None
    if not safe_download(
        out_url,
        output_mp4,
        allowed_content_types=("video/mp4",),
        content_validator=validate_video_artifact,
    ):
        return None
    if not durable:
        _cost_log(shot_id, video_id, cost_tracker=cost_tracker)
    print(f"   ✅ Viggle: {output_mp4}")
    return output_mp4

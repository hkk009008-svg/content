"""Build the capability scorecard (Part 4 / U1+U2+U8) from a project dict.

Pure aggregation: reads the already-persisted project + per-character LoRA
status; computes per-dimension measured-vs-bar, gate rollup, cascade routing,
and component-wiring status. No mutation, no Flask.
"""
from __future__ import annotations
import logging
import tomllib
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Optional

from cinema.aspect import resolve_output_dimensions, DEFAULT_ASPECT_RATIO
from cinema.context import _finite_or

# U3 — Final-media conformance constants.
# LUFS pass = abs(value - target) <= tolerance (streaming-platform window,
# matches two_pass_loudnorm default target).
LUFS_TARGET: float = -14.0
LUFS_TOLERANCE: float = 1.0
EXPECTED_VCODEC: str = "h264"
EXPECTED_ACODEC: str = "aac"

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent


def _all_shots(project: dict) -> list[dict]:
    return [sh for sc in project.get("scenes", []) for sh in sc.get("shots", [])]


def _approved_take(shot: dict, list_key: str, approved_key: str) -> Optional[dict]:
    takes = shot.get(list_key) or []
    aid = shot.get(approved_key)
    if aid:
        for t in takes:
            if t.get("id") == aid:
                return t
    return takes[-1] if takes else None


def _coherence_for(shot: dict, take: Optional[dict]) -> Optional[float]:
    # Prefer persisted take.metadata; fall back to the latest diagnostic (Task 1 may not run).
    if take and isinstance(take.get("metadata"), dict) and take["metadata"].get("coherence_score") is not None:
        return take["metadata"]["coherence_score"]
    diags = [d for d in (shot.get("diagnostics") or []) if isinstance(d.get("scores"), dict) and d["scores"].get("coherence") is not None]
    return diags[-1]["scores"]["coherence"] if diags else None


def _dimension(key: str, label: str, values: list[float], bar: Optional[float]) -> dict:
    measured = [v for v in values if v is not None]
    value = round(mean(measured), 3) if measured else None
    passed = None if value is None else (True if bar is None else value >= bar)
    return {"key": key, "label": label, "value": value, "bar": bar, "pass": passed, "n_measured": len(measured)}


def _build_media_block(project: dict) -> "dict | None":
    """Build the media conformance block from the persisted media_report.

    Returns a dict with 'lufs', 'format', and 'measured_at' sub-entries, or
    None when no media_report is present or the report is malformed. Either
    sub-block may be None independently (partial probe results).

    Pure read — no subprocess, no mutation. Defensive against malformed data.
    """
    raw = project.get("media_report")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.debug("capability scorecard: media_report is not a dict — ignoring")
        return None

    try:
        # ---- LUFS sub-block ----
        lufs_block: "dict | None" = None
        audio = raw.get("audio")
        if isinstance(audio, dict) and audio.get("integrated_lufs") is not None:
            value = float(audio["integrated_lufs"])
            lufs_block = {
                "value": value,
                "target": LUFS_TARGET,
                "tolerance": LUFS_TOLERANCE,
                "pass": abs(value - LUFS_TARGET) <= LUFS_TOLERANCE,
            }

        # ---- Format sub-block ----
        format_block: "dict | None" = None
        fmt = raw.get("format")
        if isinstance(fmt, dict):
            w = fmt.get("width")
            h = fmt.get("height")
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            gs = project.get("global_settings", {}) or {}
            expected_res = resolve_output_dimensions(
                gs.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
            resolution_ok = (w, h) == expected_res
            codec_ok = (vcodec == EXPECTED_VCODEC and acodec == EXPECTED_ACODEC)
            format_block = {
                "width": w,
                "height": h,
                "vcodec": vcodec,
                "acodec": acodec,
                "pass": resolution_ok and codec_ok,
            }

        if lufs_block is None and format_block is None:
            return None

        return {
            "lufs": lufs_block,
            "format": format_block,
            "measured_at": raw.get("measured_at"),
        }
    except Exception:
        logger.debug("capability scorecard: media_report build failed", exc_info=True)
        return None


def build_capability_scorecard(project: dict, *, project_dir: str) -> dict:
    shots = _all_shots(project)
    gs = project.get("global_settings", {}) or {}
    tier = gs.get("quality_tier", "production")

    # --- bars (sourced from named config; see plan "Critical context") ---
    try:
        from cinema.auto_approve import AutoApproveConfig
        cfg = AutoApproveConfig.from_project(project)
        identity_bar = getattr(cfg, "motion_min_identity", 0.6)
        lipsync_bar = _finite_or(gs.get("lipsync_validation_threshold", 0.65), 0.65)
    except Exception:
        logger.debug("capability scorecard: bar sourcing failed, using defaults", exc_info=True)
        identity_bar, lipsync_bar = 0.6, 0.65
    coherence_bar = _finite_or(gs.get("coherence_threshold", 0.6), 0.6)

    ident_v, coh_v, motion_v, lip_v = [], [], [], []
    per_shot, provenance = [], []
    routing = Counter()

    for shot in shots:
        kf = _approved_take(shot, "keyframe_takes", "approved_keyframe_take_id")
        mo = _approved_take(shot, "motion_takes", "approved_motion_take_id")
        idv = (kf or {}).get("metadata", {}).get("identity_score") if kf else None
        cov = _coherence_for(shot, kf)
        mov = (mo or {}).get("metadata", {}).get("motion_fidelity") if mo else None
        liv = (mo or {}).get("metadata", {}).get("lipsync_score") if mo else None
        ident_v.append(idv); coh_v.append(cov); motion_v.append(mov); lip_v.append(liv)

        # per-source: prefer the motion take's cascade, else the keyframe's (don't lose the
        # keyframe engine when the motion take lacks cascade_metadata). Handles empty-string engine.
        cas = (mo or {}).get("cascade_metadata") or (kf or {}).get("cascade_metadata") or {}
        engine = (cas.get("engine") or shot.get("target_api") or "").upper()
        attempts = cas.get("attempts") or []
        silent = bool(cas.get("fallback")) or (len(attempts) > 1)
        if silent: routing["fallback"] += 1
        else: routing["first_try"] += 1
        if cas.get("fallback"): routing["silent_fallback"] += 1

        per_shot.append({"shot_id": shot.get("id"), "identity": idv, "coherence": cov,
                         "motion": mov, "lipsync": liv, "engine": engine})
        kf_md = (kf or {}).get("metadata", {})
        if kf_md.get("identity_strategy"):
            strat = kf_md["identity_strategy"]
            per_shot[-1]["identity_multi"] = {
                "mechanism": strat.get("mechanism_tag"),
                "per_char": kf_md.get("identity_per_char", {}),
                "unconditioned": strat.get("unconditioned_chars", []),
            }
        provenance.append({"shot_id": shot.get("id"), "engine": engine,
                           "attempts": attempts, "fallback": bool(cas.get("fallback"))})

    dimensions = [
        _dimension("identity", "Identity · ArcFace", ident_v, identity_bar),
        _dimension("coherence", "Coherence", coh_v, coherence_bar),
        _dimension("motion", "Motion fidelity", motion_v, None),
        _dimension("lipsync", "Lipsync · SyncNet", lip_v, lipsync_bar),
    ]
    return {
        "project_id": project.get("id"),
        "tier": tier,
        "summary": {"shots_total": len(shots), "shots_clearing_all_bars": _shots_clearing(shots, dimensions, ident_v, coh_v, motion_v, lip_v, identity_bar, coherence_bar, lipsync_bar)},
        "dimensions": dimensions,
        "routing": {"first_try": routing["first_try"], "fallback": routing["fallback"], "silent_fallback": routing["silent_fallback"]},
        "gates": _gate_rollup(shots),
        "lora": _lora_summary(project, project_dir),
        "components": _components(),
        "per_shot": per_shot,
        "provenance": provenance,
        "media": _build_media_block(project),
        "future_dimensions": ["pod_health", "budget"],
    }


def _shots_clearing(shots, dimensions, ident_v, coh_v, motion_v, lip_v, ib, cb, lb) -> int:
    # A shot counts only if it has >=1 measured bar-bearing dimension AND none of its
    # measured dimensions fall below bar. An entirely-unscored shot does NOT count
    # (avoids the vacuous-truth where shots_clearing_all_bars == shots_total for an
    # unscored project). Motion is excluded (its bar is None / advisory).
    n = 0
    for i in range(len(shots)):
        measured = 0
        ok = True
        for v, bar in ((ident_v[i], ib), (coh_v[i], cb), (lip_v[i], lb)):
            if v is not None:
                measured += 1
                if v < bar:
                    ok = False
        n += 1 if (ok and measured > 0) else 0
    return n


def _gate_rollup(shots: list[dict]) -> dict:
    out = {g: {"approved": 0, "vetoed": 0, "top_vetoes": []} for g in ("plan", "image", "motion", "final")}
    veto_ctr = {g: Counter() for g in out}
    for shot in shots:
        # The audit log is append-only and an operator override appends a 2nd
        # entry (web_server.py::api_reject_auto_approve) instead of replacing
        # the first. Reduce to the CURRENT decision per gate — the latest entry
        # by timestamp — so an overridden approval is not double-counted as both
        # approved and vetoed. Strict '>' keeps the first-appended entry on a
        # timestamp tie, mirroring PostRunSummary.tsx's latest-per-(shot,gate)
        # semantics so the two surfaces can't silently diverge.
        latest: dict[str, dict] = {}
        for e in (shot.get("auto_approve_audit") or []):
            g = e.get("gate")
            if g not in out:
                continue
            cur = latest.get(g)
            if cur is None or (e.get("timestamp") or "") > (cur.get("timestamp") or ""):
                latest[g] = e
        for g, e in latest.items():
            if e.get("auto_approved"):
                out[g]["approved"] += 1
            else:
                out[g]["vetoed"] += 1
            for v in (e.get("vetoes") or []):
                veto_ctr[g][v] += 1
    for g in out:
        out[g]["top_vetoes"] = veto_ctr[g].most_common(3)
    return out


def _lora_summary(project: dict, project_dir: str) -> list[dict]:
    try:
        from prep.lora_training import get_lora_status
    except Exception:
        return []
    rows = []
    for ch in project.get("characters", []):
        cid = ch.get("id")
        if not cid:
            continue
        try:
            st = get_lora_status(project_dir, cid)
        except Exception:
            logger.debug("capability scorecard: get_lora_status failed for %s", cid, exc_info=True)
            continue
        if st.get("status") in (None, "idle") and st.get("quality_score") is None:
            continue
        verdict = "rejected" if st.get("rejected") else ("warning" if st.get("quality_warning") else "ok")
        rows.append({"char_id": cid, "strength": st.get("best_strength"),
                     "score": st.get("quality_score"), "verdict": verdict})
    return rows


def _components() -> list[dict]:
    path = REPO_ROOT / "docs" / "pipeline_status.toml"
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.debug("capability scorecard: failed to read pipeline_status.toml", exc_info=True)
        return []
    return [{"id": c.get("id"), "title": c.get("title"), "status": c.get("status"), "note": c.get("note")}
            for c in data.get("component", [])]

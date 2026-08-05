"""
Cost tracking and budget governance system for the cinema pipeline.

Tracks all LLM and API costs across providers, models, and operations.
Provides budget checking, cost-per-second analysis, and spend summaries.

Per-API generation cost estimates
===================================

``API_COST_USD`` maps API name (uppercase, matching ``generate_ai_video``
and ``generate_ai_broll`` target names) to estimated USD per generation call.

Estimates are conservative averages for typical 5-second 720p clips / 1024px
stills. Actual costs vary by duration, resolution, and provider pricing changes.
Operators should treat values as ±30% accurate and tune against their invoices.
The ``record_api_call`` method uses this table; pass ``cost_usd`` explicitly
to override any entry.

Budget gate
===========

Construct ``CostTracker(budget_usd=N)`` to enable the project cap. The legacy
``would_exceed(api_name)`` helper remains an early UI precheck; paid adapters
must call ``reserve_paid_attempt`` immediately before submission and reconcile
that reservation after the provider outcome. The reservation transaction reads
durable spend, active commitments, and the current durable project cap, closing
the old cross-thread/process check-then-submit race. ``would_exceed`` and
``is_over_budget`` both return False when ``budget_usd`` is None
(no limit); a falsy budget (0 / 0.0) is coerced to None at construction —
it is the project-settings sentinel for "unlimited", not a zero cap. A
non-finite (NaN/inf) or non-coercible cap is corruption, not "unlimited":
it is coerced to a blocking sentinel so the gate fail-safe BLOCKS rather
than silently disabling enforcement (ADR-026).
``spent_usd`` accumulates in-process only; SQLite is the durable store,
but the budget gate uses the fast in-memory counter.
"""

import math
import sqlite3
import os
import sys
import threading
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Per-API estimated USD cost per generation call.
# Calibrate against your provider invoices; defaults are reasonable starting
# points for typical 5-second 720p clips / 1024px stills.
# ---------------------------------------------------------------------------

API_COST_USD: dict[str, float] = {
    # Video APIs (per ~5s clip)
    "KLING_NATIVE":  0.50,    # legacy kling-v1-6 native route (fallback-only since 2026-07-11); price is a pre-v3 estimate
    "KLING_3_0":     0.56,    # per ~5s clip: fal kling-video/v3/pro $0.112/s audio-off (fal model page + kling.ai/dev/pricing parity, read 2026-07-11)
    "SORA_NATIVE":   0.80,
    "SORA_2":        0.60,
    "VEO_NATIVE":    0.30,
    "GEMINI_OMNI":   0.56,   # $0.112/s x ~5s estimate (Gemini Developer API preview pricing — WEB-VERIFIED NOT REPO-MEASURED, confirm against a live billed call per R-MEASURE). Duration is prompt-inferred/variable on this API (no structured duration kwarg), so this flat per-clip estimate risks the exact under-billing pattern SEEDANCE needed fixing for on 2026-07-11 (see SEEDANCE_DURATIONS, phase_c_ffmpeg.py:38) — a duration-probe (ffprobe on the downloaded mp4) fix is recommended before this is load-bearing at scale, not shipped in this first pass.
    "VEO":           0.25,
    "LTX":           0.36,   # FLOOR ESTIMATE (pre-spend gate / no-duration callers only): fal ltx-2.3 $0.06/s audio-off @1080p x 6s MINIMUM duration (fal OpenAPI + model page 2026-07-11); native api.ltx.io pricing unverified. The dispatcher's shared default duration is 8s (phase_c_ffmpeg.generate_ai_video(duration="8s")), so this 6s-assuming flat figure under-records ~33% on default shots — record_api_call(duration_seconds=...) computes the TRUE per-second cost from API_COST_PER_SECOND_USD below whenever the caller supplies the actual dispatched duration (money-gate finding 2026-07-30).
    "RUNWAY_GEN4":   0.50,
    "RUNWAY":        0.40,
    "FAL_SVD":       0.20,    # per ~5s clip via fal-ai/fast-svd (conservative estimate; calibrate against fal.ai invoice)
    "SEEDANCE":      1.51,    # per ~5s clip: fal bytedance/seedance-2.0 standard 720p = $0.3024/s (fal model page, read 2026-07-11; r2v-with-video-input bills 0.6x; calibrate against fal invoice)
    # Performance-capture APIs (per ~5s clip; mirrors performance/* _cost_log estimates).
    # ACT_ONE: the routing engine NAME kept for backward compat with existing
    # routing/historical cost-log data (domain.performance.ENGINE_ACT_ONE,
    # performance/_router.py) — the adapter it actually dispatches migrated
    # to Runway ACT-TWO (performance/act_two.py, 2026-07-30 slice 5b); rate
    # unchanged (~$0.05/s matches act_two.py's own _cost_log estimate).
    "ACT_ONE":        0.25,    # Runway Act-Two retargeting (key name is legacy — see comment above), approx $0.05/s.
    "LIVE_PORTRAIT":  0.04,    # ComfyUI LivePortrait amortized GPU cost.
    "VIGGLE":         0.20,    # Viggle full-body motion retargeting.
    "PERFORMANCE_DRIVING_SADTALKER":  0.045,  # Mode-B SadTalker driving face, 5s estimate.
    # Image APIs (per still)
    "COMFYUI_PULID": 0.04,   # FLUX+PuLID on the ComfyUI pod (GPU-time estimate)
    "FLUX_PULID":    0.05,
    # fal.ai list price read 2026-06-11 (model page for flux-pro/kontext/max/multi,
    # the variant production actually calls): "$0.08 per image" — per OUTPUT image,
    # no per-input-ref surcharge listed. The old 0.04 was the non-max Kontext tier.
    "FLUX_KONTEXT":  0.08,
    "FLUX_PRO":      0.05,
    "FLUX_SCHNELL":  0.01,   # FAL flux/schnell — fast, low-cost fallback
    "POLLINATIONS":  0.00,   # free service (last-resort fallback)
    "HIDREAM_I1":    0.06,
    "GEMINI_IMAGE":  0.067,  # gemini-3.1-flash-image (Nano Banana 2) — migrated off gemini-2.5-flash-image (shutdown deadline 2026-10-02, Slice 6b). The provider pricing page (ai.google.dev/gemini-api/docs/pricing, 2026-07-31) publishes the EXACT per-image figure for the 1K resolution this adapter hardcodes (gemini_image_native.py image_size="1K"): $0.067/img (quality review of 3c7714e4 — the earlier $0.077 token-estimate overstated it ~15%). PROVIDER-CLAIMED, recalibrate against invoice per R-MEASURE.
    # Conservative reservation ceiling for one 500-token Claude vision
    # identity decision. Terminal reconciliation uses the SDK's actual token
    # counts and PRICING row, so this is a budget hold rather than booked cost.
    "CLAUDE_VISION_IDENTITY": 0.02,
    # Audio APIs (per clip / per call)
    "STABILITY_FOLEY":   0.03,    # per ~5-60s foley clip via Stable Audio 2.0
    "CARTESIA_SONIC_2":  0.008,   # ~$0.008/shot per descriptor at domain/scene_decomposer.py:67
    "ELEVENLABS":        0.01,    # per ~5s line (typical short dialogue; Eleven v3)
    "SUNO_V5":           0.50,    # per ~60s song via Suno V5 chirp model
    "FAL_STABLE_AUDIO":  0.10,    # per ~47s BGM clip via FAL Stable Audio (production default)
    # Post-processing APIs (per clip / per call)
    # fal-ai/pixverse/swap defaults to a 5s, 720p person swap when the caller
    # supplies only video_url/image_url.  FAL's model page listed that exact
    # tier at $0.20 per request on 2026-08-05.  This remains a reservation /
    # reconciled estimate until invoice ingestion exists.
    "FAL_PIXVERSE_SWAP": 0.20,
    "FAL_RIFE":          0.04,    # per clip RIFE frame-interpolation via fal-ai/rife/video
    # SeedVR2 bills $0.001 per megapixel-frame. This table value is the
    # provider's published 1920x1080 x 121-frame example (~$0.25); the adapter
    # computes the actual reservation estimate from target resolution and the
    # source frame count instead of relying on this representative fallback.
    "FAL_SEEDVR2":       0.25,
    # Lipsync engines (per dialogue clip). The cascade-winning engine is recorded
    # as LIPSYNC_<engine> (namespaced at cinema/shots/controller.py to avoid
    # colliding with same-named video engines, e.g. lipsync "kling" vs video
    # KLING_NATIVE). Lipsync is MANDATORY for dialogue shots (F1b), so an unpriced
    # cascade silently undercounts the budget gate. Estimates; calibrate vs invoice.
    "LIPSYNC_SYNCSOV3":    0.67,   # sync-3 overlay via FAL: $0.107-0.133/s (sync.so docs + fal $8/min, read 2026-07-11) -> ~5s clip
    "LIPSYNC_MUSETALK":    0.02,   # MuseTalk mouth-only overlay via FAL
    "LIPSYNC_LATENTSYNC":  0.03,   # LatentSync overlay fallback via FAL
    "LIPSYNC_SYNCV2":      0.23,   # Sync lipsync-2 (LEGACY tier: 512x512 face region) via FAL: $0.04-0.05/s (sync.so docs 2026-07-11) -> ~5s clip
    "LIPSYNC_KLING":       0.05,   # gate figure for the PLANNED KLING_LIPSYNC_2 overlay engine (scene_decomposer API_REGISTRY, status=planned) — pinned equal by test_cost_tracker::test_lipsync_registry_costs_match_api_cost_usd. NOT the generation cascade: Kling was dropped there in 40bc8c60 (overlay endpoint, needs video_url).
    "LIPSYNC_OMNIHUMAN":   0.80,   # OmniHuman v1.5 via FAL: $0.16/s (fal model page 2026-07-11) -> 5s clip
    "LIPSYNC_AURORA":      0.05,   # Creatify Aurora generation via FAL
    "LIPSYNC_DEFAULT":     0.67,   # fallback when the cascade reports no engine name — assume the sync-3 primary won (undercounting the likely winner is the worse error)
}


# ---------------------------------------------------------------------------
# Per-second cost rates for duration-billed video APIs whose flat
# API_COST_USD estimate above assumes one specific duration.
# record_api_call(duration_seconds=...) computes the TRUE cost from these
# instead of the flat table whenever the caller supplies the actual
# dispatched duration — grepped for an existing duration-aware pattern in
# this module before adding this (money-gate finding 2026-07-30: none
# existed here; the closest precedent is the per-module ``_cost_log``
# helpers in performance/act_two.py, performance/live_portrait.py, and
# performance/driving_video.py, which each compute
# ``cost_usd = round(rate * duration_s, N)`` inline). Pulling the rate up to
# the shared record site (rather than a bespoke per-caller helper) lets any
# duration-billed engine opt in without its own copy of the arithmetic.
# ---------------------------------------------------------------------------

API_COST_PER_SECOND_USD: dict[str, float] = {
    # fal ltx-2.3 $0.06/s audio-off @1080p (fal OpenAPI + model page,
    # read 2026-07-11) — see the API_COST_USD["LTX"] comment above for the
    # flat-table/duration-aware split.
    # Legacy/FAL profile only. Native ltx-2-3-pro pricing is selected through
    # ``estimate_call_cost_usd(..., backend="native", model=...,
    # resolution=...)`` below; collapsing those materially different tiers
    # into this compatibility rate under-counted 4K jobs by more than 80%.
    "LTX": 0.06,
    # SEEDANCE per-second rate DERIVED from the flat API_COST_USD entry
    # above (fal bytedance/seedance-2.0 standard 720p = $0.3024/s, read
    # 2026-07-11) rather than a second hardcoded literal — the two can
    # never drift apart since both read the SAME API_COST_USD["SEEDANCE"]
    # value. Reproduces, bit-for-bit, the arithmetic already shipped in
    # cinema/shots/controller.py::_motion_cost_kwargs's SEEDANCE branch
    # (``round(API_COST_USD["SEEDANCE"] / 5.0 * duration, 4)`` — the
    # post-fact record_api_call cost override for the SEEDANCE winner/
    # billed-reject path) so the pre-spend estimate below and that
    # post-fact record price the SAME clip identically (money-gate
    # finding 2026-07-30/31).
    "SEEDANCE": API_COST_USD["SEEDANCE"] / 5.0,
}


# Exact provider-published LTX 2.3 Pro image/text-to-video rates.  The key is
# deliberately dimensional: a later audio-bearing endpoint or a different
# operation cannot silently inherit the image-to-video, audio-off price.
# FAL remains on the legacy 0.06/s compatibility profile above because it is
# a separate backend/invoice and current callers do not surface its richer
# model metadata.
LTX_PRICING_PER_SECOND_USD: dict[
    tuple[str, str, str, str, bool], float
] = {
    ("native", "image_to_video", "ltx-2-3-pro", "1080p", False): 0.08,
    ("native", "image_to_video", "ltx-2-3-pro", "1440p", False): 0.16,
    ("native", "image_to_video", "ltx-2-3-pro", "4k", False): 0.32,
    ("native", "text_to_video", "ltx-2-3-pro", "1080p", False): 0.08,
    ("native", "text_to_video", "ltx-2-3-pro", "1440p", False): 0.16,
    ("native", "text_to_video", "ltx-2-3-pro", "4k", False): 0.32,
}


PAID_ATTEMPT_ACTIVE_STATES = frozenset({
    "reserved",
    "submitting",
    "accepted_unknown",
    "running",
    "cancel_requested",
})
PAID_ATTEMPT_STATES = frozenset({
    *PAID_ATTEMPT_ACTIVE_STATES,
    "succeeded",
    "failed_billed",
    "failed_unbilled",
    "cancelled",
    "blocked_budget",
})
PAID_ATTEMPT_TERMINAL_STATES = frozenset({
    "succeeded",
    "failed_billed",
    "failed_unbilled",
    "cancelled",
    "blocked_budget",
})

# Paid attempts are monotonic ownership records.  An ambiguous task may become
# observable again and return to ``running``; a cancellation request may also
# lose its acknowledgement and return to ``accepted_unknown``.  Terminal rows,
# however, are immutable and can only be repeated idempotently.
PAID_ATTEMPT_TRANSITIONS = {
    "reserved": frozenset({
        "reserved", "submitting", "running", "accepted_unknown",
        "cancel_requested", "succeeded", "failed_billed",
        "failed_unbilled", "cancelled",
    }),
    "submitting": frozenset({
        "submitting", "running", "accepted_unknown", "cancel_requested",
        "succeeded", "failed_billed", "failed_unbilled", "cancelled",
    }),
    "running": frozenset({
        "running", "accepted_unknown", "cancel_requested", "succeeded",
        "failed_billed", "failed_unbilled", "cancelled",
    }),
    "accepted_unknown": frozenset({
        "accepted_unknown", "running", "cancel_requested", "succeeded",
        "failed_billed", "failed_unbilled", "cancelled",
    }),
    "cancel_requested": frozenset({
        "cancel_requested", "running", "accepted_unknown", "succeeded",
        "failed_billed", "failed_unbilled", "cancelled",
    }),
    "succeeded": frozenset({"succeeded"}),
    "failed_billed": frozenset({"failed_billed"}),
    "failed_unbilled": frozenset({"failed_unbilled"}),
    "cancelled": frozenset({"cancelled"}),
    "blocked_budget": frozenset({"blocked_budget"}),
}


# ---------------------------------------------------------------------------
# Pricing per 1M tokens
# ---------------------------------------------------------------------------

PRICING = {
    # Anthropic
    "claude-sonnet-4-6": {
        "input": 3.00,
        "cache_write_5m": 3.75,
        "cache_read": 0.30,
        "output": 15.00,
    },
    # Deprecated-model row kept for historical cost entries (retires 2026-06-15):
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "cache_write_5m": 3.75,
        "cache_read": 0.30,
        "output": 15.00,
    },
    # claude-opus-4-20250918 row dropped (T-E hygiene): the id never existed at
    # the API (404'd — see ensemble.py item-G scrub), so no historical cost
    # entry can reference it; PRICING is consumed at write time only (:246).
    "claude-opus-4-8": {
        "input": 5.00,
        "cache_write_5m": 6.25,
        "cache_read": 0.50,
        "output": 25.00,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "cache_write_5m": 1.25,
        "cache_read": 0.10,
        "output": 5.00,
    },
    # OpenAI
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Google
    # gemini-2.5-flash / gemini-2.5-pro rows KEPT (not deleted) for historical
    # cost-log math on old records even though both shut down 2026-10-16
    # (Slice 6b migrated the live call sites to their successors below).
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    # Successor rows (Slice 6b, 2026-07-31). PROVIDER-CLAIMED rates from
    # ai.google.dev/gemini-api/docs/pricing (WebFetch 2026-07-31), standard
    # (non-batch) tier, short-context (<=200k tok) band where the provider
    # tiers by prompt length — recalibrate against invoice per R-MEASURE.
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
}


# ---------------------------------------------------------------------------
# Provider detection helper
# ---------------------------------------------------------------------------

def _detect_provider(model: str) -> str:
    """Infer the provider from a model name string."""
    model_lower = model.lower()
    if "claude" in model_lower:
        return "anthropic"
    if "gpt" in model_lower or model_lower.startswith("o"):
        return "openai"
    if "gemini" in model_lower:
        return "google"
    return "unknown"


# ---------------------------------------------------------------------------
# Operator-visible warning helper
# ---------------------------------------------------------------------------

def _warn_operator(msg: str, stacklevel: int = 2) -> None:
    """Emit a load-bearing operator warning on BOTH channels (ADR-066/067).

    ``warnings.warn`` alone is invisible in the production process: the
    TF/Keras import chain (loaded whenever ``from deepface import DeepFace``
    executes — identity/validator, domain/character_manager,
    domain/continuity_engine, phase_c_vision) fronts a blanket
    ('ignore', None, Warning, None, 0) filter, silencing every later warning
    even under ``-W error`` (verified 2026-07-11; pytest.warns still sees
    them because it installs its own filter context — tests stay green while
    production goes silent). stderr survives that stomp, so every money-lane
    warning in this module goes through here.

    ``stacklevel`` is relative to the caller, as if ``warnings.warn`` were
    called inline (the +1 below compensates for this frame).
    """
    print(msg, file=sys.stderr)
    warnings.warn(msg, stacklevel=stacklevel + 1)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class CostEntry:
    """A single cost record for an LLM or API call."""
    timestamp: str          # ISO format
    provider: str           # anthropic, openai, google, fal, kling, sora, veo, ltx, runway, comfyui
    model: str              # specific model name
    operation: str          # e.g. script_generation, video_generation, identity_validation, image_generation
    input_tokens: int       # for LLM calls, 0 for API calls
    output_tokens: int
    cost_usd: float
    shot_id: str = ""       # optional, links to specific shot
    video_id: str = ""      # optional, links to video project


# ---------------------------------------------------------------------------
# Cost tracker
# ---------------------------------------------------------------------------

# A non-finite (NaN/inf) or non-coercible budget cap is data corruption, not a
# deliberate "unlimited" — coerce it onto the negatives-block fail-safe (ADR-026,
# user-endorsed 2026-06-14) so the gate BLOCKS rather than silently disabling
# enforcement. Any non-negative spend exceeds this sentinel.
_NONFINITE_BUDGET_BLOCK: float = -1.0


def _finite_budget_or_block(value) -> float:
    """Coerce a budget cap to a finite float, else the blocking sentinel.

    NaN/inf survive ``float()`` and a NaN defeats every comparison
    (``x > NaN`` is always False), so a non-finite cap silently disables the
    budget gate while ``budget_usd is not None`` masquerades as a set cap. A
    non-coercible value (e.g. a typo'd string) is corruption too. Both map to
    ``_NONFINITE_BUDGET_BLOCK`` so spend is fail-safe BLOCKED, consistent with
    the kept-negatives-block philosophy in ``CostTracker.__init__``.

    A documented-temporary local guard rather than an import of
    ``cinema.context._finite_or``: that import is circular-safe (verified) but
    inverts the layering — ``cost_tracker`` is a low-level root util — and would
    drag the ``cinema.context`` dependency tree into a foundational module;
    consolidation is deferred to the dedicated import-swap pass. (Formerly
    mirrored the ``quality_max:191`` documented-temporary local-copy precedent;
    that module was retired WS1 Task 4.)
    """
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return _NONFINITE_BUDGET_BLOCK
    return v if math.isfinite(v) else _NONFINITE_BUDGET_BLOCK


class CostTracker:
    """
    Persistent cost tracker backed by SQLite.

    Logs every LLM and API call, calculates running totals, enforces budgets,
    and produces spend summaries for the cinema pipeline.
    """

    # Explicit capability marker consumed by paid_provider.  Keeping this a
    # concrete integer prevents MagicMock/loose duck types from accidentally
    # claiming durable paid-call authority.
    paid_attempt_authority_version = 1

    def __init__(
        self,
        db_path: Optional[str] = None,
        budget_usd: Optional[float] = None,
    ):
        # db_path resolution (T7): honor EXPERIMENTS_DB_PATH so the env var —
        # also surfaced as config.settings.experiments_db_path — actually takes
        # effect for every CostTracker, not just the settings object. Explicit
        # db_path arg wins; env var next; legacy default last. Resolved here
        # (not in the signature default) so the env is read at construction
        # time, and to avoid coupling this low-level util to config.settings.
        self.db_path = os.fspath(
            db_path or os.environ.get("EXPERIMENTS_DB_PATH", "data/experiments.db")
        )
        # Falsy budget (0 / 0.0 / None) means NO cap — make_project() defaults
        # budget_limit_usd to 0; the UI documents 0 = unlimited (NF-2,
        # docs/STRATEGIC_REVIEW-2026-06-10.md). Negative values are KEPT
        # deliberately: they block all spend (fail-safe) rather than
        # coercing to unlimited (fail-open on a typo). A non-finite (NaN/inf)
        # cap is corruption, not "unlimited" — it would defeat every comparison
        # (x > NaN is always False) and silently disable the gate; coerce it
        # onto the same negatives-block fail-safe (ADR-026).
        if budget_usd is not None:
            budget_usd = _finite_budget_or_block(budget_usd)
        self.budget_usd = budget_usd if budget_usd else None
        # Fast in-process accumulator for the budget gate.  The SQLite
        # store is the durable record; this counter is reset each process.
        self.spent_usd: float = 0.0
        self._conn_lock = threading.RLock()
        self._closed = False
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 30000")
        # File-backed ledgers use WAL so readers (UI snapshots) do not block
        # the short BEGIN IMMEDIATE reservation transaction. SQLite's special
        # in-memory databases cannot use WAL and intentionally retain their
        # native ``memory`` journal mode (unit tests / ephemeral tools only).
        is_memory_db = self.db_path == ":memory:" or self.db_path.startswith(
            "file::memory:"
        )
        requested_journal = "MEMORY" if is_memory_db else "WAL"
        journal_row = self.conn.execute(
            f"PRAGMA journal_mode = {requested_journal}"
        ).fetchone()
        self.journal_mode = str(journal_row[0] if journal_row else "").lower()
        if not is_memory_db and self.journal_mode != "wal":
            raise RuntimeError(
                f"CostTracker requires WAL for file-backed ledgers; SQLite returned {self.journal_mode!r}"
            )
        self._create_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_table(self):
        with self._conn_lock:
            try:
                # Serialize the additive migration across processes opening the
                # same project database for the first time after upgrade.
                self.conn.execute("BEGIN IMMEDIATE")
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS cost_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT DEFAULT (datetime('now')),
                        provider TEXT,
                        model TEXT,
                        operation TEXT,
                        input_tokens INTEGER DEFAULT 0,
                        output_tokens INTEGER DEFAULT 0,
                        cost_usd REAL DEFAULT 0.0,
                        shot_id TEXT,
                        video_id TEXT,
                        provider_job_id TEXT NOT NULL DEFAULT ''
                    );
                """)
                columns = {
                    row["name"]
                    for row in self.conn.execute("PRAGMA table_info(cost_log)")
                }
                if "provider_job_id" not in columns:
                    self.conn.execute(
                        "ALTER TABLE cost_log ADD COLUMN "
                        "provider_job_id TEXT NOT NULL DEFAULT ''"
                    )
                # A provider job represents one invoice even if recovery sees
                # the completed result more than once.  Empty IDs retain the
                # historical append-every-call behavior.
                self.conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                        idx_cost_log_provider_job_unique
                    ON cost_log(provider, provider_job_id)
                    WHERE provider_job_id <> ''
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS paid_attempts (
                        attempt_id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        engine TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        shot_id TEXT NOT NULL DEFAULT '',
                        video_id TEXT NOT NULL DEFAULT '',
                        request_fingerprint TEXT NOT NULL DEFAULT '',
                        state TEXT NOT NULL,
                        reserved_cost_usd REAL NOT NULL DEFAULT 0.0,
                        reconciled_cost_usd REAL,
                        billed INTEGER,
                        provider_job_id TEXT NOT NULL DEFAULT '',
                        provider_status TEXT NOT NULL DEFAULT '',
                        failure_code TEXT NOT NULL DEFAULT '',
                        detail TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paid_attempts_video_state
                    ON paid_attempts(video_id, state)
                """)
                self.conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                        idx_paid_attempts_provider_job_unique
                    ON paid_attempts(provider, provider_job_id)
                    WHERE provider_job_id <> ''
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS provider_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        engine TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN ('succeeded', 'failed')
                        ),
                        latency_ms REAL NOT NULL,
                        shot_id TEXT NOT NULL DEFAULT '',
                        video_id TEXT NOT NULL DEFAULT ''
                    )
                """)
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_provider_observations_scope
                    ON provider_observations(video_id, engine, timestamp DESC)
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS cost_budget_authority (
                        video_id TEXT PRIMARY KEY,
                        budget_usd REAL,
                        updated_at TEXT NOT NULL
                    )
                """)
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized_provider_job_id(provider_job_id: Optional[str]) -> str:
        """Return a safe exact idempotency key, or ``""`` when not supplied."""
        if provider_job_id is None or provider_job_id == "":
            return ""
        if not isinstance(provider_job_id, str):
            raise ValueError("provider_job_id must be a string when supplied")
        if provider_job_id != provider_job_id.strip():
            raise ValueError("provider_job_id must not contain surrounding whitespace")
        if len(provider_job_id) > 512:
            raise ValueError("provider_job_id must be at most 512 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in provider_job_id):
            raise ValueError("provider_job_id must not contain control characters")
        return provider_job_id

    @staticmethod
    def _normalized_attempt_id(attempt_id: str) -> str:
        """Validate a caller-owned durable idempotency key."""
        if not isinstance(attempt_id, str):
            raise ValueError("attempt_id must be a string")
        if attempt_id != attempt_id.strip() or not attempt_id:
            raise ValueError("attempt_id must be a non-empty trimmed string")
        if len(attempt_id) > 512:
            raise ValueError("attempt_id must be at most 512 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in attempt_id):
            raise ValueError("attempt_id must not contain control characters")
        return attempt_id

    @staticmethod
    def _paid_attempt_row(row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        result = dict(row)
        raw_billed = result.get("billed")
        result["billed"] = None if raw_billed is None else bool(raw_billed)
        result["active"] = result.get("state") in PAID_ATTEMPT_ACTIVE_STATES
        return result

    def reserve_paid_attempt(
        self,
        *,
        attempt_id: str,
        provider: str,
        engine: str,
        operation: str,
        estimated_cost_usd: float,
        shot_id: str = "",
        video_id: str = "",
        request_fingerprint: str = "",
    ) -> dict:
        """Atomically reserve budget and claim one paid submission.

        The insert, durable-spend read, and active-reservation read share one
        ``BEGIN IMMEDIATE`` transaction.  Two processes therefore cannot both
        pass a check-then-submit window.  An existing attempt is never claimed
        again: ``acquired=False`` tells the adapter to resume its recorded
        provider task (when one exists) or fail closed as accepted-unknown.
        """
        normalized_id = self._normalized_attempt_id(attempt_id)
        try:
            estimate = float(estimated_cost_usd)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("estimated_cost_usd must be finite and non-negative") from exc
        if not math.isfinite(estimate) or estimate < 0:
            raise ValueError("estimated_cost_usd must be finite and non-negative")
        now = datetime.now(timezone.utc).isoformat()
        provider = str(provider or "unknown").strip().lower()[:64]
        engine = str(engine or "unknown").strip().upper()[:128]
        operation = str(operation or "paid_generation").strip()[:128]
        shot_id = str(shot_id or "")[:512]
        video_id = str(video_id or "")[:512]
        request_fingerprint = str(request_fingerprint or "")[:128]

        with self._conn_lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                existing = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                if existing is not None:
                    expected_identity = {
                        "provider": provider,
                        "engine": engine,
                        "operation": operation,
                        "shot_id": shot_id,
                        "video_id": video_id,
                        "request_fingerprint": request_fingerprint,
                    }
                    conflicting_fields = [
                        key
                        for key, expected in expected_identity.items()
                        if str(existing[key] or "") != str(expected or "")
                    ]
                    if conflicting_fields:
                        raise ValueError(
                            "paid attempt ID was reused across a different request "
                            f"identity: {', '.join(conflicting_fields)}"
                        )
                    self.conn.commit()
                    snapshot = self._paid_attempt_row(existing) or {}
                    snapshot["acquired"] = False
                    return snapshot

                spend_scope = "WHERE video_id = ?" if video_id else ""
                spend_args = (video_id,) if video_id else ()
                spent_row = self.conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) AS total "
                    f"FROM cost_log {spend_scope}",
                    spend_args,
                ).fetchone()
                reserved_scope = "AND video_id = ?" if video_id else ""
                reserved_args = tuple(PAID_ATTEMPT_ACTIVE_STATES) + (
                    (video_id,) if video_id else ()
                )
                placeholders = ",".join("?" for _ in PAID_ATTEMPT_ACTIVE_STATES)
                reserved_row = self.conn.execute(
                    "SELECT COALESCE(SUM(reserved_cost_usd), 0.0) AS total "
                    f"FROM paid_attempts WHERE state IN ({placeholders}) "
                    f"{reserved_scope}",
                    reserved_args,
                ).fetchone()
                spent = float(spent_row["total"] or 0.0)
                reserved = float(reserved_row["total"] or 0.0)
                authoritative_budget = self.budget_usd
                if video_id:
                    budget_row = self.conn.execute(
                        "SELECT budget_usd FROM cost_budget_authority WHERE video_id = ?",
                        (video_id,),
                    ).fetchone()
                    if budget_row is not None:
                        authoritative_budget = budget_row["budget_usd"]
                blocked = (
                    authoritative_budget is not None
                    and (
                        not math.isfinite(spent)
                        or not math.isfinite(reserved)
                        or spent + reserved + estimate > float(authoritative_budget)
                    )
                )
                state = "blocked_budget" if blocked else "submitting"
                reserved_cost = 0.0 if blocked else estimate
                detail = (
                    "Atomic reservation refused by project budget"
                    if blocked
                    else "Budget reserved; provider submission claimed"
                )
                self.conn.execute(
                    """
                    INSERT INTO paid_attempts (
                        attempt_id, provider, engine, operation, shot_id,
                        video_id, request_fingerprint, state,
                        reserved_cost_usd, detail, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_id, provider, engine, operation, shot_id,
                        video_id, request_fingerprint, state, reserved_cost,
                        detail, now, now,
                    ),
                )
                row = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        snapshot = self._paid_attempt_row(row) or {}
        snapshot["acquired"] = not blocked
        return snapshot

    def update_paid_attempt(
        self,
        attempt_id: str,
        *,
        state: str,
        provider_job_id: Optional[str] = None,
        provider_status: str = "",
        failure_code: str = "",
        detail: str = "",
        billed: Optional[bool] = None,
    ) -> dict:
        """CAS-transition an active attempt without changing its money row.

        Terminal transitions must use :meth:`reconcile_paid_attempt` so the
        cost row, billed flag, and reservation release share one transaction.
        """
        normalized_id = self._normalized_attempt_id(attempt_id)
        if state not in PAID_ATTEMPT_STATES:
            raise ValueError(f"unsupported paid-attempt state: {state!r}")
        if state in PAID_ATTEMPT_TERMINAL_STATES:
            raise ValueError(
                "terminal paid-attempt states must use reconcile_paid_attempt"
            )
        normalized_job_id = (
            self._normalized_provider_job_id(provider_job_id)
            if provider_job_id is not None
            else None
        )
        assignments = [
            "state = ?",
            "provider_status = ?",
            "failure_code = ?",
            "detail = ?",
            "updated_at = ?",
        ]
        values: list[object] = [
            state,
            str(provider_status or "")[:128],
            str(failure_code or "")[:128],
            str(detail or "")[:1000],
            datetime.now(timezone.utc).isoformat(),
        ]
        if normalized_job_id is not None:
            assignments.append("provider_job_id = ?")
            values.append(normalized_job_id)
        if billed is not None:
            assignments.append("billed = ?")
            values.append(1 if billed else 0)
        with self._conn_lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                current = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                if current is None:
                    raise KeyError(f"unknown paid attempt {normalized_id!r}")
                current_state = str(current["state"])
                if state not in PAID_ATTEMPT_TRANSITIONS.get(
                    current_state, frozenset()
                ):
                    raise ValueError(
                        "illegal paid-attempt transition "
                        f"{current_state!r} -> {state!r}"
                    )
                existing_job_id = str(current["provider_job_id"] or "")
                if (
                    normalized_job_id is not None
                    and existing_job_id
                    and normalized_job_id != existing_job_id
                ):
                    raise ValueError(
                        "provider_job_id is immutable once acknowledged"
                    )
                cursor = self.conn.execute(
                    f"UPDATE paid_attempts SET {', '.join(assignments)} "
                    "WHERE attempt_id = ? AND state = ?",
                    tuple(values + [normalized_id, current_state]),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"paid attempt {normalized_id!r} changed concurrently"
                    )
                row = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return self._paid_attempt_row(row) or {}

    def reconcile_paid_attempt(
        self,
        attempt_id: str,
        *,
        state: str,
        actual_cost_usd: Optional[float] = None,
        provider_job_id: Optional[str] = None,
        provider_status: str = "",
        failure_code: str = "",
        detail: str = "",
    ) -> dict:
        """Atomically settle a reservation and create its one cost row.

        ``state`` must be terminal.  The attempt ID becomes the invoice
        idempotency key when a provider job ID is unavailable, so concurrent
        reconciliation cannot double-charge the durable ledger.  Cost insert,
        terminal CAS transition, and reservation release commit together.
        """
        if state not in {"succeeded", "failed_billed", "failed_unbilled", "cancelled"}:
            raise ValueError("reconciliation requires a terminal paid-attempt state")
        normalized_id = self._normalized_attempt_id(attempt_id)
        normalized_job_id = (
            self._normalized_provider_job_id(provider_job_id)
            if provider_job_id is not None
            else None
        )
        requested_cost: Optional[float] = None
        if actual_cost_usd is not None:
            try:
                requested_cost = float(actual_cost_usd)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    "actual_cost_usd must be finite and non-negative"
                ) from exc
            if not math.isfinite(requested_cost) or requested_cost < 0:
                raise ValueError(
                    "actual_cost_usd must be finite and non-negative"
                )

        billed = state in {"succeeded", "failed_billed"}
        inserted_cost = 0.0
        now = datetime.now(timezone.utc).isoformat()
        with self._conn_lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                row = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown paid attempt {normalized_id!r}")
                attempt = self._paid_attempt_row(row) or {}
                current_state = str(attempt.get("state") or "")
                if state not in PAID_ATTEMPT_TRANSITIONS.get(
                    current_state, frozenset()
                ):
                    raise ValueError(
                        "illegal paid-attempt transition "
                        f"{current_state!r} -> {state!r}"
                    )

                existing_job_id = str(attempt.get("provider_job_id") or "")
                if (
                    normalized_job_id is not None
                    and (
                        (
                            current_state in PAID_ATTEMPT_TERMINAL_STATES
                            and normalized_job_id != existing_job_id
                        )
                        or (
                            existing_job_id
                            and normalized_job_id != existing_job_id
                        )
                    )
                ):
                    raise ValueError(
                        "provider_job_id is immutable once acknowledged"
                    )
                final_job_id = (
                    normalized_job_id
                    if normalized_job_id is not None
                    else existing_job_id
                )

                previous_reconciled = attempt.get("reconciled_cost_usd")
                if billed:
                    if requested_cost is not None:
                        cost = requested_cost
                    elif previous_reconciled is not None:
                        cost = float(previous_reconciled)
                    else:
                        cost = float(attempt.get("reserved_cost_usd") or 0.0)
                    if not math.isfinite(cost) or cost < 0:
                        raise ValueError(
                            "actual_cost_usd must be finite and non-negative"
                        )
                    if (
                        current_state == state
                        and previous_reconciled is not None
                        and not math.isclose(
                            float(previous_reconciled), cost,
                            rel_tol=0.0, abs_tol=1e-12,
                        )
                    ):
                        raise ValueError(
                            "terminal paid attempt cannot be reconciled at a different cost"
                        )
                    invoice_key = (
                        final_job_id or f"attempt:{normalized_id[:504]}"
                    )
                    cursor = self.conn.execute(
                        """
                        INSERT OR IGNORE INTO cost_log
                            (timestamp, provider, model, operation, input_tokens,
                             output_tokens, cost_usd, shot_id, video_id,
                             provider_job_id)
                        VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
                        """,
                        (
                            now,
                            attempt["provider"],
                            attempt["engine"],
                            attempt["operation"],
                            cost,
                            attempt["shot_id"],
                            attempt["video_id"],
                            invoice_key,
                        ),
                    )
                    if cursor.rowcount == 1:
                        inserted_cost = cost
                    else:
                        existing_cost = self.conn.execute(
                            "SELECT provider, model, operation, cost_usd, shot_id, "
                            "video_id FROM cost_log WHERE provider = ? "
                            "AND provider_job_id = ?",
                            (attempt["provider"], invoice_key),
                        ).fetchone()
                        if existing_cost is None or any((
                            str(existing_cost["model"]) != str(attempt["engine"]),
                            str(existing_cost["operation"]) != str(attempt["operation"]),
                            str(existing_cost["shot_id"] or "") != str(attempt["shot_id"] or ""),
                            str(existing_cost["video_id"] or "") != str(attempt["video_id"] or ""),
                            not math.isclose(
                                float(existing_cost["cost_usd"]), cost,
                                rel_tol=0.0, abs_tol=1e-12,
                            ),
                        )):
                            raise ValueError(
                                "provider invoice key already belongs to a different cost record"
                            )
                else:
                    cost = 0.0
                    if (
                        current_state == state
                        and previous_reconciled is not None
                        and not math.isclose(
                            float(previous_reconciled), 0.0,
                            rel_tol=0.0, abs_tol=1e-12,
                        )
                    ):
                        raise ValueError(
                            "unbilled terminal attempt has a conflicting reconciled cost"
                        )

                incoming_fields = {
                    "provider_status": str(provider_status or "")[:128],
                    "failure_code": str(failure_code or "")[:128],
                    "detail": str(detail or "")[:1000],
                }
                existing_fields = {
                    key: str(attempt.get(key) or "") for key in incoming_fields
                }
                if current_state in PAID_ATTEMPT_TERMINAL_STATES:
                    for key, incoming in incoming_fields.items():
                        existing = existing_fields[key]
                        if incoming and existing and incoming != existing:
                            raise ValueError(
                                f"terminal paid attempt {key} is immutable"
                            )
                    final_fields = {
                        key: existing_fields[key] or incoming
                        for key, incoming in incoming_fields.items()
                    }
                else:
                    final_fields = {
                        key: incoming or existing_fields[key]
                        for key, incoming in incoming_fields.items()
                    }
                cursor = self.conn.execute(
                    """
                    UPDATE paid_attempts
                    SET state = ?, provider_job_id = ?, provider_status = ?,
                        failure_code = ?, detail = ?, billed = ?,
                        reconciled_cost_usd = ?, reserved_cost_usd = 0.0,
                        updated_at = ?
                    WHERE attempt_id = ? AND state = ?
                    """,
                    (
                        state,
                        final_job_id,
                        final_fields["provider_status"],
                        final_fields["failure_code"],
                        final_fields["detail"],
                        1 if billed else 0,
                        cost,
                        now,
                        normalized_id,
                        current_state,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"paid attempt {normalized_id!r} changed concurrently"
                    )
                settled = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                    (normalized_id,),
                ).fetchone()
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            if inserted_cost:
                self.spent_usd += inserted_cost
        return self._paid_attempt_row(settled) or {}

    def get_paid_attempt(self, attempt_id: str) -> Optional[dict]:
        normalized_id = self._normalized_attempt_id(attempt_id)
        with self._conn_lock:
            row = self.conn.execute(
                "SELECT * FROM paid_attempts WHERE attempt_id = ?",
                (normalized_id,),
            ).fetchone()
        return self._paid_attempt_row(row)

    def get_latest_paid_attempt(
        self,
        *,
        video_id: str,
        shot_id: str,
        engine: str,
        operation: str,
    ) -> Optional[dict]:
        """Return the newest durable attempt for one logical call site."""
        with self._conn_lock:
            row = self.conn.execute(
                """
                SELECT * FROM paid_attempts
                WHERE video_id = ? AND shot_id = ? AND engine = ?
                  AND operation = ?
                ORDER BY created_at DESC, attempt_id DESC
                LIMIT 1
                """,
                (video_id, shot_id, engine.upper(), operation),
            ).fetchone()
        return self._paid_attempt_row(row)

    def get_paid_attempts_snapshot(self, video_id: str = "") -> dict:
        """Return a UI-safe authority snapshot for jobs and reservations."""
        with self._conn_lock:
            if video_id:
                rows = self.conn.execute(
                    "SELECT * FROM paid_attempts WHERE video_id = ? "
                    "ORDER BY created_at, attempt_id",
                    (video_id,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM paid_attempts ORDER BY created_at, attempt_id"
                ).fetchall()
        attempts = [self._paid_attempt_row(row) or {} for row in rows]
        active = [row for row in attempts if row.get("active")]
        return {
            "attempts": attempts,
            "active_reservation_usd": round(
                sum(float(row.get("reserved_cost_usd") or 0.0) for row in active),
                6,
            ),
            "accepted_unknown_count": sum(
                row.get("state") == "accepted_unknown" for row in attempts
            ),
            "billed_failure_count": sum(
                row.get("state") == "failed_billed" for row in attempts
            ),
            "blocked_attempt_count": sum(
                row.get("state") == "blocked_budget" for row in attempts
            ),
        }

    def record_provider_observation(
        self,
        *,
        provider: str,
        engine: str,
        operation: str,
        status: str,
        latency_ms: float,
        shot_id: str = "",
        video_id: str = "",
    ) -> dict:
        """Persist one non-replayable provider request outcome.

        Paid adapters use ``paid_attempts`` because their provider job IDs and
        billing state are durable authorities. Planning LLM SDK calls do not
        expose a resumable job ID, but their success/failure and latency still
        belong in restart-safe analytics rather than only process-local logs.
        """
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"succeeded", "failed"}:
            raise ValueError("provider observation status must be succeeded or failed")
        if isinstance(latency_ms, bool):
            raise ValueError("provider observation latency_ms must be numeric")
        try:
            normalized_latency = float(latency_ms)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "provider observation latency_ms must be numeric"
            ) from exc
        if not math.isfinite(normalized_latency) or normalized_latency < 0:
            raise ValueError(
                "provider observation latency_ms must be finite and non-negative"
            )

        def label(value: object, fallback: str, limit: int) -> str:
            normalized = str(value or fallback).strip()
            return (normalized or fallback)[:limit]

        inherited_video_id = getattr(self, "default_video_id", "")
        scoped_video_id = video_id or (
            inherited_video_id if isinstance(inherited_video_id, str) else ""
        )
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": label(provider, "unknown", 64),
            "engine": label(engine, "UNKNOWN", 128),
            "operation": label(operation, "provider_request", 128),
            "status": normalized_status,
            "latency_ms": normalized_latency,
            "shot_id": label(shot_id, "", 128),
            "video_id": label(scoped_video_id, "", 128),
        }
        with self._conn_lock:
            cursor = self.conn.execute(
                """
                INSERT INTO provider_observations (
                    timestamp, provider, engine, operation, status,
                    latency_ms, shot_id, video_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["timestamp"], row["provider"], row["engine"],
                    row["operation"], row["status"], row["latency_ms"],
                    row["shot_id"], row["video_id"],
                ),
            )
            self.conn.commit()
        row["id"] = int(cursor.lastrowid)
        return row

    def get_provider_usage_analytics(
        self,
        video_id: str = "",
        terminal_limit: int = 200,
    ) -> dict:
        """Aggregate recent durable usage and health by engine and provider.

        ``terminal_limit`` bounds the recent terminal evidence window per
        engine (1..1000). Active reservations are always included because omitting a
        currently owned/billable job would make the financial snapshot false.
        Health uses paid-provider outcomes plus durable planning-provider
        observations. Cancellation and local budget blocks remain visible
        counts but do not improve or poison provider success rate.
        """
        from domain.provider_health import (
            MIN_TERMINAL_SAMPLES,
            assess_provider_health,
        )

        if isinstance(terminal_limit, bool) or not isinstance(terminal_limit, int):
            terminal_limit = 200
        terminal_limit = max(1, min(1000, terminal_limit))
        terminal_states = (
            "succeeded",
            "failed_billed",
            "failed_unbilled",
            "cancelled",
            "blocked_budget",
        )
        active_states = tuple(PAID_ATTEMPT_ACTIVE_STATES)
        terminal_marks = ",".join("?" for _ in terminal_states)
        active_marks = ",".join("?" for _ in active_states)
        scope_clause = "AND video_id = ?" if video_id else ""
        scope_args = (video_id,) if video_id else ()
        observation_where = "WHERE video_id = ?" if video_id else ""
        token_scope_clause = "AND video_id = ?" if video_id else ""
        with self._conn_lock:
            terminal_rows = self.conn.execute(
                "WITH ranked AS ("
                "SELECT *, ROW_NUMBER() OVER ("
                "PARTITION BY engine ORDER BY updated_at DESC, attempt_id DESC"
                ") AS recent_rank FROM paid_attempts "
                f"WHERE state IN ({terminal_marks}) {scope_clause}"
                ") SELECT * FROM ranked WHERE recent_rank <= ? "
                "ORDER BY updated_at DESC, attempt_id DESC",
                terminal_states + scope_args + (terminal_limit,),
            ).fetchall()
            active_rows = self.conn.execute(
                "SELECT * FROM paid_attempts "
                f"WHERE state IN ({active_marks}) {scope_clause} "
                "ORDER BY updated_at DESC, attempt_id DESC",
                active_states + scope_args,
            ).fetchall()
            observation_rows = self.conn.execute(
                "WITH ranked AS ("
                "SELECT *, ROW_NUMBER() OVER ("
                "PARTITION BY engine ORDER BY timestamp DESC, id DESC"
                ") AS recent_rank FROM provider_observations "
                f"{observation_where}"
                ") SELECT * FROM ranked WHERE recent_rank <= ? "
                "ORDER BY timestamp DESC, id DESC",
                scope_args + (terminal_limit,),
            ).fetchall()
            token_cost_rows = self.conn.execute(
                "SELECT provider, model, SUM(cost_usd) AS token_cost_usd "
                "FROM cost_log WHERE (input_tokens > 0 OR output_tokens > 0) "
                f"{token_scope_clause} GROUP BY provider, model",
                scope_args,
            ).fetchall()
        rows = [dict(row) for row in terminal_rows] + [dict(row) for row in active_rows]

        def parse_timestamp(value: object) -> Optional[datetime]:
            if not isinstance(value, str) or not value.strip():
                return None
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        def empty_metric(name: str) -> dict:
            return {
                "key": name,
                "terminal_count": 0,
                "active_count": 0,
                "succeeded": 0,
                "failed_billed": 0,
                "failed_unbilled": 0,
                "failed_observed": 0,
                "cancelled": 0,
                "blocked_budget": 0,
                "accepted_unknown": 0,
                "success_rate": None,
                "average_terminal_latency_s": None,
                "p95_terminal_latency_s": None,
                "charged_cost_usd": 0.0,
                "reconciled_cost_usd": 0.0,
                "active_reservation_usd": 0.0,
                "token_cost_usd": 0.0,
                "consecutive_failures": 0,
                "data_valid": True,
                "_outcomes": [],
                "_latencies": [],
            }

        by_engine: dict[str, dict] = {}
        by_provider: dict[str, dict] = {}

        def add_row(metric: dict, row: dict) -> None:
            state = str(row.get("state") or "")
            if state in terminal_states:
                metric["terminal_count"] += 1
            if state in PAID_ATTEMPT_ACTIVE_STATES:
                metric["active_count"] += 1
            if state in {
                "succeeded", "failed_billed", "failed_unbilled",
                "cancelled", "blocked_budget", "accepted_unknown",
            }:
                metric[state] += 1

            created = parse_timestamp(row.get("created_at"))
            updated = parse_timestamp(row.get("updated_at"))
            if created is None or updated is None or updated < created:
                metric["data_valid"] = False
            elif state in {"succeeded", "failed_billed", "failed_unbilled"}:
                # Operator cancellation latency is a control-path measurement,
                # not provider completion latency. Including it could make a
                # healthy provider look slow after a long user-held job.
                metric["_latencies"].append((updated - created).total_seconds())

            reconciled = row.get("reconciled_cost_usd")
            if reconciled is not None:
                try:
                    reconciled_value = float(reconciled)
                except (TypeError, ValueError, OverflowError):
                    metric["data_valid"] = False
                else:
                    if not math.isfinite(reconciled_value) or reconciled_value < 0:
                        metric["data_valid"] = False
                    else:
                        metric["reconciled_cost_usd"] += reconciled_value
                        if state in {"succeeded", "failed_billed"}:
                            metric["charged_cost_usd"] += reconciled_value
            if state in PAID_ATTEMPT_ACTIVE_STATES:
                try:
                    reserved = float(row.get("reserved_cost_usd") or 0.0)
                except (TypeError, ValueError, OverflowError):
                    metric["data_valid"] = False
                else:
                    if not math.isfinite(reserved) or reserved < 0:
                        metric["data_valid"] = False
                    else:
                        metric["active_reservation_usd"] += reserved
            if state in {"succeeded", "failed_billed", "failed_unbilled"}:
                metric["_outcomes"].append((updated, state))

        for row in rows:
            engine = str(row.get("engine") or "UNKNOWN")[:128]
            provider = str(row.get("provider") or "unknown")[:64]
            add_row(by_engine.setdefault(engine, empty_metric(engine)), row)
            add_row(by_provider.setdefault(provider, empty_metric(provider)), row)

        def add_observation(metric: dict, row: dict) -> None:
            status = str(row.get("status") or "")
            state = "succeeded" if status == "succeeded" else "failed_observed"
            metric["terminal_count"] += 1
            metric[state] += 1
            timestamp = parse_timestamp(row.get("timestamp"))
            try:
                latency_s = float(row.get("latency_ms")) / 1000.0
            except (TypeError, ValueError, OverflowError):
                timestamp = None
                latency_s = -1.0
            if (
                timestamp is None
                or not math.isfinite(latency_s)
                or latency_s < 0
            ):
                metric["data_valid"] = False
            else:
                metric["_latencies"].append(latency_s)
            metric["_outcomes"].append((timestamp, state))

        for raw_row in observation_rows:
            row = dict(raw_row)
            engine = str(row.get("engine") or "UNKNOWN")[:128]
            provider = str(row.get("provider") or "unknown")[:64]
            add_observation(by_engine.setdefault(engine, empty_metric(engine)), row)
            add_observation(
                by_provider.setdefault(provider, empty_metric(provider)), row
            )

        def add_token_cost(metric: dict, value: object) -> None:
            try:
                token_cost = float(value or 0.0)
            except (TypeError, ValueError, OverflowError):
                metric["data_valid"] = False
                return
            if not math.isfinite(token_cost) or token_cost < 0:
                metric["data_valid"] = False
                return
            metric["token_cost_usd"] += token_cost
            metric["charged_cost_usd"] += token_cost
            metric["reconciled_cost_usd"] += token_cost

        for raw_row in token_cost_rows:
            row = dict(raw_row)
            engine = str(row.get("model") or "UNKNOWN")[:128]
            provider = str(row.get("provider") or "unknown")[:64]
            add_token_cost(
                by_engine.setdefault(engine, empty_metric(engine)),
                row.get("token_cost_usd"),
            )
            add_token_cost(
                by_provider.setdefault(provider, empty_metric(provider)),
                row.get("token_cost_usd"),
            )

        def finalize(metric: dict) -> dict:
            outcomes = metric.pop("_outcomes")
            latencies = metric.pop("_latencies")
            sample_count = (
                metric["succeeded"]
                + metric["failed_billed"]
                + metric["failed_unbilled"]
                + metric["failed_observed"]
            )
            metric["sample_count"] = sample_count
            # Report the observed rate whenever an outcome exists. Health still
            # remains UNKNOWN below MIN_TERMINAL_SAMPLES; hiding the raw rate
            # would make the analytics surface incomplete without increasing
            # statistical confidence.
            if sample_count > 0:
                metric["success_rate"] = round(metric["succeeded"] / sample_count, 6)
            if latencies:
                ordered_latency = sorted(latencies)
                metric["average_terminal_latency_s"] = round(
                    sum(ordered_latency) / len(ordered_latency), 3
                )
                p95_index = max(0, math.ceil(0.95 * len(ordered_latency)) - 1)
                metric["p95_terminal_latency_s"] = round(
                    ordered_latency[p95_index], 3
                )
            if metric["data_valid"]:
                ordered_outcomes = sorted(
                    outcomes,
                    key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc),
                )
                streak = 0
                for _timestamp, state in reversed(ordered_outcomes):
                    if state not in {
                        "failed_billed", "failed_unbilled", "failed_observed"
                    }:
                        break
                    streak += 1
                metric["consecutive_failures"] = streak
            for money_key in (
                "charged_cost_usd",
                "reconciled_cost_usd",
                "active_reservation_usd",
                "token_cost_usd",
            ):
                metric[money_key] = round(metric[money_key], 6)
            metric["health"] = assess_provider_health(
                sample_count=sample_count,
                success_rate=metric["success_rate"],
                p95_terminal_latency_s=metric["p95_terminal_latency_s"],
                consecutive_failures=metric["consecutive_failures"],
                billed_failures=metric["failed_billed"],
                accepted_unknown=metric["accepted_unknown"],
                data_valid=metric["data_valid"],
            )
            return metric

        return {
            "scope_video_id": video_id,
            "terminal_limit": terminal_limit,
            # Paid adapters reconcile the repository pricing estimate against
            # the observed terminal outcome. It is not an invoice export.
            "cost_basis": "reconciled_estimate",
            "by_engine": {
                key: finalize(metric) for key, metric in sorted(by_engine.items())
            },
            "by_provider": {
                key: finalize(metric) for key, metric in sorted(by_provider.items())
            },
        }

    def log(
        self,
        provider: str,
        model: str,
        operation: str,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        shot_id: str = "",
        video_id: str = "",
        provider_job_id: Optional[str] = None,
    ) -> CostEntry:
        """Insert a cost record, idempotently when a provider job ID is known."""
        # Timezone-aware UTC; datetime.utcnow() is deprecated in 3.12+.
        ts = datetime.now(timezone.utc).isoformat()
        # Guard against NaN/inf cost_usd: a non-finite value poisons the
        # accumulator (0.0 + NaN = NaN) so that every subsequent gate check
        # silently returns False (NaN > budget is always False in IEEE 754).
        # This is the spend-accumulator sibling of the budget_usd guard
        # (_finite_budget_or_block, ADR-026) — Rule #13 symmetric-endpoint gap
        # (cost-spent-nan-poison, W2:CRITICAL). Coerce to 0.0 (fail-safe: keep
        # the gate ALIVE for real subsequent spend) and emit a WARNING so
        # operators can diagnose the upstream source of the bad cost value.
        if not math.isfinite(cost_usd):
            _warn_operator(
                f"[cost_tracker] Non-finite cost_usd={cost_usd!r} coerced to 0.0 "
                f"in log() (operation={operation!r}); upstream cost calculation "
                f"produced NaN/inf — check the caller for division by zero or "
                f"NaN duration. Gate stays ALIVE for real subsequent spend "
                f"(cost-spent-nan-poison, ADR-026 symmetric-endpoint guard).",
                stacklevel=3,
            )
            cost_usd = 0.0
        normalized_job_id = self._normalized_provider_job_id(provider_job_id)
        inherited_video_id = getattr(self, "default_video_id", "")
        if not video_id and isinstance(inherited_video_id, str):
            video_id = inherited_video_id
        with self._conn_lock:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO cost_log
                    (timestamp, provider, model, operation, input_tokens,
                     output_tokens, cost_usd, shot_id, video_id,
                     provider_job_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, provider, model, operation, input_tokens,
                    output_tokens, cost_usd, shot_id, video_id,
                    normalized_job_id,
                ),
            )
            self.conn.commit()
            # spent_usd mirrors the persisted spend. Increment at this sole write
            # chokepoint (log_api/log_llm both delegate here) so every logged cost
            # reaches the in-process accumulator the budget gate reads
            # (would_exceed/is_over_budget). Placed AFTER commit so a failed INSERT
            # never inflates the accumulator.
            if cursor.rowcount == 1:
                self.spent_usd += cost_usd
        return CostEntry(
            timestamp=ts,
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            shot_id=shot_id,
            video_id=video_id,
        )

    def log_llm(
        self,
        model: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        shot_id: str = "",
        video_id: str = "",
    ) -> CostEntry:
        """
        Log an LLM call.

        Automatically detects the provider and calculates cost from the
        PRICING table. If the model is unknown, warns on both channels
        (warnings + stderr, via _warn_operator) so the cost is not silently
        lost (previously this defaulted to $0.00 with no signal, breaking
        budget governance).
        """
        provider = _detect_provider(model)
        if model not in PRICING:
            _warn_operator(
                f"[cost_tracker] Unknown model {model!r}; recording $0.00 cost. "
                f"Add it to PRICING in cost_tracker.py for accurate budgeting.",
            )
        pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost_usd = (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )
        return self.log(
            provider=provider,
            model=model,
            operation=operation,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            shot_id=shot_id,
            video_id=video_id,
        )

    def log_api(
        self,
        provider: str,
        model: str,
        operation: str,
        cost_usd: float,
        shot_id: str = "",
        video_id: str = "",
        provider_job_id: Optional[str] = None,
    ) -> CostEntry:
        """Direct cost logging for video/image API calls (non-token-based)."""
        return self.log(
            provider=provider,
            model=model,
            operation=operation,
            cost_usd=cost_usd,
            input_tokens=0,
            output_tokens=0,
            shot_id=shot_id,
            video_id=video_id,
            provider_job_id=provider_job_id,
        )

    @staticmethod
    def _duration_aware_cost_usd(
        api_upper: str,
        duration_seconds: Optional[float],
        *,
        backend: Optional[str] = None,
        operation: Optional[str] = None,
        model: Optional[str] = None,
        resolution: Optional[str] = None,
        audio: Optional[bool] = None,
    ) -> Optional[float]:
        """Return the TRUE per-second cost for *api_upper*, or None.

        None means "no opinion" — the caller falls back to the flat
        ``API_COST_USD`` estimate. That happens when ``duration_seconds`` is
        not supplied, is a ``bool``, ``api_upper`` has no
        ``API_COST_PER_SECOND_USD`` entry, or the supplied duration is
        non-numeric/non-finite/non-positive — a bad duration must never
        poison the record (fail safe to the flat table, mirroring the
        NaN-cost guard in ``log()``), never crash.

        The explicit ``bool`` rejection is pinned deliberately: ``bool`` is
        an ``int`` subclass in Python, so ``float(True) == 1.0`` would
        otherwise sail through every check below (finite, positive) and be
        silently read as "duration = 1 second" instead of being rejected as
        the non-duration value it plainly is — a prior reviewer found an
        analogous bool guard shipped unpinned elsewhere (money-gate finding
        2026-07-30/31); this one ships pinned from the start, with a
        dedicated regression case in ``test_cost_tracker.py``.
        """
        if (
            duration_seconds is None
            or isinstance(duration_seconds, bool)
        ):
            return None
        try:
            dur = float(duration_seconds)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(dur) or dur <= 0:
            return None
        if api_upper == "LTX" and backend is not None:
            if not all(
                isinstance(value, str) and value.strip()
                for value in (backend, operation, model, resolution)
            ) or not isinstance(audio, bool):
                raise ValueError(
                    "authoritative LTX pricing requires backend, operation, "
                    "model, resolution, and audio"
                )
            profile_key = (
                backend.strip().lower(),
                operation.strip().lower(),
                model.strip().lower(),
                resolution.strip().lower(),
                audio,
            )
            try:
                rate = LTX_PRICING_PER_SECOND_USD[profile_key]
            except KeyError as exc:
                raise ValueError(
                    f"unsupported LTX pricing profile: {profile_key!r}"
                ) from exc
            return round(rate * dur, 4)
        if api_upper not in API_COST_PER_SECOND_USD:
            return None
        return round(API_COST_PER_SECOND_USD[api_upper] * dur, 4)

    @staticmethod
    def estimate_call_cost_usd(
        api_name: str,
        duration_seconds: Optional[float] = None,
        *,
        backend: Optional[str] = None,
        operation: Optional[str] = None,
        model: Optional[str] = None,
        resolution: Optional[str] = None,
        audio: Optional[bool] = None,
    ) -> float:
        """Return the pre-spend cost estimate for one call to *api_name*.

        Reuses ``_duration_aware_cost_usd`` — the exact same rate/round
        logic ``record_api_call`` uses for its post-fact record — so the
        pre-spend estimate and the eventual recorded cost can never drift
        into two independently-maintained implementations. Falls back to
        the flat ``API_COST_USD`` table under the identical conditions
        ``_duration_aware_cost_usd`` documents (duration absent/bool/
        non-finite/non-positive/non-numeric, or *api_name* has no
        per-second rate) — never zero from a bad duration, never a crash.
        An *api_name* absent from BOTH tables still returns 0.0 (unchanged
        pre-existing flat-table behavior; this helper does not add or
        remove the "unknown API" warning ``record_api_call`` emits).

        Public (unlike ``_duration_aware_cost_usd``) so a caller assembling
        a multi-call ``would_exceed_cost()`` envelope — e.g.
        ``generate_motion_take``'s mandatory-lipsync precheck in
        cinema/shots/controller.py — can duration-price the per-second-
        billed component instead of re-deriving this same
        duration-aware-or-flat choice inline (a parallel copy that could
        drift). ``would_exceed`` below is the other caller.
        """
        api_upper = api_name.upper()
        cost = CostTracker._duration_aware_cost_usd(
            api_upper,
            duration_seconds,
            backend=backend,
            operation=operation,
            model=model,
            resolution=resolution,
            audio=audio,
        )
        if cost is None:
            cost = API_COST_USD.get(api_upper, 0.0)
        return cost

    def record_api_call(
        self,
        api_name: str,
        cost_usd: Optional[float] = None,
        operation: str = "",
        shot_id: str = "",
        video_id: str = "",
        duration_seconds: Optional[float] = None,
        provider_job_id: Optional[str] = None,
        backend: Optional[str] = None,
        model: Optional[str] = None,
        resolution: Optional[str] = None,
        audio: Optional[bool] = None,
        pricing_operation: Optional[str] = None,
    ) -> float:
        """Record a generation API call against the budget.

        Looks up ``api_name`` in ``API_COST_USD`` if ``cost_usd`` is not
        supplied. Updates ``self.spent_usd`` (in-process accumulator) and
        persists to SQLite.  Returns the cost recorded.

        Call for spend the provider actually BILLED: successful generations
        (winner-keyed) and billed-but-rejected attempts (the provider
        returned a video that download/aspect checks then discarded —
        operation="motion_generation_rejected", 2026-07-11). Never call for
        attempts that failed BEFORE the provider produced output.

        Args:
            duration_seconds: the ACTUAL dispatched duration, when the
                caller knows it. For an ``api_name`` with an
                ``API_COST_PER_SECOND_USD`` entry (currently LTX and
                SEEDANCE), this computes the TRUE cost
                (``rate * duration_seconds``) instead of the flat
                ``API_COST_USD`` estimate, which assumes one specific
                duration and silently under/over-records whenever the
                actual dispatched duration differs (e.g. LTX's flat figure
                assumes the 6s enum floor while the dispatcher's shared
                default is 8s — money-gate finding 2026-07-30).
                Ignored whenever ``cost_usd`` is explicitly supplied
                (explicit cost always wins), the api has no per-second rate,
                or the duration is non-finite/non-positive/non-numeric/bool —
                falls back to the flat table exactly as before.
            provider_job_id: Opaque provider-issued job identifier. Repeated
                records for the same provider and non-empty job ID are ignored
                durably, so recovery cannot charge one invoice twice.
        """
        api_upper = api_name.upper()
        if cost_usd is None:
            cost_usd = self._duration_aware_cost_usd(
                api_upper,
                duration_seconds,
                backend=backend,
                operation=pricing_operation,
                model=model,
                resolution=resolution,
                audio=audio,
            )
        if cost_usd is None:
            cost_usd = API_COST_USD.get(api_upper, 0.0)
            if cost_usd == 0.0 and api_upper not in API_COST_USD:
                _warn_operator(
                    f"[cost_tracker] Unknown API {api_name!r}; recording $0.00 cost. "
                    f"Add it to API_COST_USD in cost_tracker.py for accurate budgeting.",
                )

        # Derive a human-readable provider name from the API key.
        # Prefix match in insertion order; first hit wins. Pod (ComfyUI/PuLID)
        # image backends map to a provider DISTINCT from "fal" so cost_log can
        # tell "ran on the pod" from "fell back to FAL".
        _provider_map = {
            # Fal-proxy engines that share a prefix with a native provider must
            # sit BEFORE that prefix (first-prefix-wins) or the fal invoice
            # files under the native provider (review finding 2026-07-11,
            # extended to SORA_2/VEO by the ultrareview symmetric-audit):
            #   KLING_3_0/SORA_2/VEO are fal-billed; KLING_NATIVE→kling,
            #   SORA_NATIVE→openai, VEO_NATIVE→google are the genuine natives.
            "KLING_3_0": "fal",
            "SORA_2": "fal",        # fal-ai/sora-2 — before "SORA"→openai
            "VEO_NATIVE": "google",  # Vertex/Gemini — before "VEO"→fal below
            "GEMINI_OMNI": "google",  # Gemini Developer API only (not on Vertex yet) — shares the "google" cost-log bucket with VEO_NATIVE
            "GEMINI_IMAGE": "google",  # gemini-3.1-flash-image (Nano Banana 2, migrated Slice 6b) — Gemini Developer API only, same "google" bucket
            "VEO": "fal",            # fal-ai/veo3.1 — replaces the old "VEO"→google
            "KLING": "kling", "SORA": "openai",
            "LTX": "ltx", "RUNWAY": "runway",
            "COMFYUI": "comfyui",
            "POLLINATIONS": "pollinations",
            "FLUX": "fal", "HIDREAM": "fal", "SEEDANCE": "fal",
        }
        provider = "unknown"
        for prefix, prov in _provider_map.items():
            if api_upper.startswith(prefix):
                provider = prov
                break

        op = operation or f"{api_upper.lower()}_generation"
        self.log_api(
            provider=provider,
            model=api_upper,
            operation=op,
            cost_usd=cost_usd,
            shot_id=shot_id,
            video_id=video_id,
            provider_job_id=provider_job_id,
        )
        # spent_usd is incremented inside log() (the sole write chokepoint that
        # log_api delegates to), so accumulating it again here would double-count.
        return cost_usd

    # ------------------------------------------------------------------
    # Budget gate
    # ------------------------------------------------------------------

    def would_exceed(
        self,
        api_name: str,
        duration_seconds: Optional[float] = None,
        **pricing_context,
    ) -> bool:
        """Pre-emptive check: would recording this call push us over budget?

        Returns False when ``budget_usd`` is None (no limit).

        Args:
            duration_seconds: the ACTUAL duration the dispatcher is ABOUT to
                request, when the caller knows it ahead of dispatch (e.g.
                ``generate_motion_take`` in cinema/shots/controller.py, for
                the two genuinely per-second-billed video engines LTX and
                SEEDANCE). Reuses ``estimate_call_cost_usd`` — the exact
                same ``_duration_aware_cost_usd`` rate/round logic
                ``record_api_call`` uses for its post-fact record — so this
                pre-check can never drift from what actually gets recorded
                once the call completes. An absent/unknown/non-finite/
                non-positive/bool duration, or an *api_name* with no
                ``API_COST_PER_SECOND_USD`` entry, falls back to the flat
                ``API_COST_USD`` estimate exactly as before this parameter
                existed (money-gate finding 2026-07-30/31: this check was
                flat-only for every engine until now — an LTX/SEEDANCE call
                about to dispatch at 8s or 10s was pre-checked against a
                shorter-duration flat-table UNDER-estimate, even though
                ``record_api_call`` was already duration-aware for the same
                two engines post-fact).

        Defense-in-depth (cost-spent-nan-poison, Rule #13 symmetric guard):
        if spent_usd is somehow non-finite (e.g. from a race or a direct
        assignment bypassing log()), treat it as over-budget (fail-safe FIRES
        the gate) rather than silently returning False (NaN > cap is False).
        """
        if self.budget_usd is None:
            return False
        with self._conn_lock:
            spent = self.spent_usd
        if not math.isfinite(spent):
            return True  # fail-safe: non-finite spend → gate fires
        cost = self.estimate_call_cost_usd(
            api_name,
            duration_seconds,
            **pricing_context,
        )
        return (spent + cost) > self.budget_usd

    def would_exceed_cost(self, estimated_cost_usd: float) -> bool:
        """Pre-emptive check for a caller-computed multi-call spend envelope."""
        if self.budget_usd is None:
            return False
        try:
            cost = float(estimated_cost_usd)
        except (TypeError, ValueError):
            return True
        if not math.isfinite(cost):
            return True
        if cost < 0:
            cost = 0.0
        with self._conn_lock:
            spent = self.spent_usd
        if not math.isfinite(spent):
            return True
        return (spent + cost) > self.budget_usd

    def is_over_budget(self) -> bool:
        """Post-fact check: has cumulative in-process spend exceeded the cap?

        Returns False when ``budget_usd`` is None (no limit).

        Defense-in-depth (cost-spent-nan-poison, Rule #13 symmetric guard):
        if spent_usd is non-finite, treat it as over-budget (fail-safe FIRES
        the gate) rather than silently returning False (NaN > cap is False).
        """
        if self.budget_usd is None:
            return False
        with self._conn_lock:
            spent = self.spent_usd
        if not math.isfinite(spent):
            return True  # fail-safe: non-finite spend → gate fires
        return spent > self.budget_usd

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_shot_spent(self, shot_id: str) -> float:
        """Return the total cost logged against a specific shot_id.

        Queries the durable SQLite store (not the in-process accumulator) so
        the result survives process restarts and is usable for per-shot budget
        veto checks.  Mirrors the get_session_cost COALESCE pattern to handle
        NULL SUM (empty result set) without raising.

        Returns 0.0 for an unknown / empty shot_id or when no rows exist.
        The result is always finite: any non-finite value stored in cost_log
        (e.g. from a pre-fix poison write) is treated as 0.0 so the caller
        receives a safe value (cost-spent-nan-poison, W2:CRITICAL symmetric guard).

        Bridge for the per-shot budget veto: _shot_over_budget in
        cinema/auto_approve.py reads shot_state["spent_usd"] which no production
        code wrote; caller-injection at cinema/review/controller.py before
        check_gate() feeds this return value into shot_state — C-1,
        shot-spent-usd-never-written, W2:CRITICAL.
        """
        if not shot_id:
            return 0.0
        with self._conn_lock:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_log WHERE shot_id = ?",
                (shot_id,),
            ).fetchone()
        total = row["total"] if row else 0.0
        # Defense-in-depth: a pre-fix NaN persisted in cost_log must not poison
        # the caller; coerce to 0.0 (fail-safe: veto fires on real over-cap spend).
        return float(total) if math.isfinite(float(total)) else 0.0

    def rehydrate_spent_usd_from_video(self, video_id: str) -> float:
        """Restore the in-process budget accumulator from durable project rows.

        ``spent_usd`` is the fast value read by ``would_exceed`` and
        ``is_over_budget``. SQLite is the durable source, so checkpoint resume
        must seed the accumulator from rows already recorded for the current
        project/video id before any new paid call is admitted.

        Returns the value assigned to ``self.spent_usd``.
        """
        if not video_id:
            with self._conn_lock:
                self.spent_usd = 0.0
                return self.spent_usd

        with self._conn_lock:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_log WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            total = row["total"] if row else 0.0
            try:
                spent = float(total)
            except (TypeError, ValueError, OverflowError):
                spent = float("inf")
            if not math.isfinite(spent):
                _warn_operator(
                    f"[cost_tracker] Non-finite persisted spend total={total!r} "
                    f"for video_id={video_id!r}; budget gate will fail closed.",
                )
                spent = float("inf")
            self.spent_usd = spent
        self.set_video_budget(video_id, self.budget_usd)
        return self.spent_usd

    def set_video_budget(
        self,
        video_id: str,
        budget_usd: Optional[float],
    ) -> Optional[float]:
        """Publish the current project cap as durable reservation authority.

        Every process performs reservations against this row, so a settings
        mutation takes effect for already-running peers at their next atomic
        admission instead of leaving each process with a divergent local cap.
        ``None`` represents the established unlimited setting.
        """
        if not isinstance(video_id, str) or not video_id:
            raise ValueError("video_id is required for durable budget authority")
        normalized: Optional[float]
        if budget_usd is None:
            normalized = None
        else:
            normalized = _finite_budget_or_block(budget_usd)
        now = datetime.now(timezone.utc).isoformat()
        with self._conn_lock:
            self.conn.execute(
                """
                INSERT INTO cost_budget_authority(video_id, budget_usd, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    budget_usd = excluded.budget_usd,
                    updated_at = excluded.updated_at
                """,
                (video_id, normalized, now),
            )
            self.conn.commit()
        return normalized

    def get_video_cost(self, video_id: str) -> dict:
        """
        Return a cost breakdown for a single video project.

        Returns dict with keys:
            total_usd, llm_usd, api_usd,
            breakdown_by_provider, breakdown_by_operation, shot_count
        """
        with self._conn_lock:
            rows = self.conn.execute(
                "SELECT * FROM cost_log WHERE video_id = ?", (video_id,)
            ).fetchall()

        total_usd = 0.0
        llm_usd = 0.0
        api_usd = 0.0
        by_provider: dict[str, float] = {}
        by_operation: dict[str, float] = {}
        shot_ids: set[str] = set()

        for r in rows:
            cost = r["cost_usd"]
            total_usd += cost

            if r["input_tokens"] > 0 or r["output_tokens"] > 0:
                llm_usd += cost
            else:
                api_usd += cost

            by_provider[r["provider"]] = by_provider.get(r["provider"], 0.0) + cost
            by_operation[r["operation"]] = by_operation.get(r["operation"], 0.0) + cost

            if r["shot_id"]:
                shot_ids.add(r["shot_id"])

        return {
            "total_usd": round(total_usd, 6),
            "llm_usd": round(llm_usd, 6),
            "api_usd": round(api_usd, 6),
            "breakdown_by_provider": {k: round(v, 6) for k, v in by_provider.items()},
            "breakdown_by_operation": {k: round(v, 6) for k, v in by_operation.items()},
            "shot_count": len(shot_ids),
        }

    def get_session_cost(self, lookback_hours: float = 24.0) -> float:
        """Total cost spent in the last ``lookback_hours`` (default 24h).

        Note: this is a rolling-window total, not a true "session" delimited
        by process start. Callers wanting per-process spend should pass a
        smaller window or track their own start timestamp.
        """
        # Timezone-aware UTC; datetime.utcnow() is deprecated in 3.12+.
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
        with self._conn_lock:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_log WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()
        return round(row["total"], 6)

    def get_cost_per_second(self, video_id: str, video_duration_seconds: float) -> float:
        """Production cost per second of final video."""
        info = self.get_video_cost(video_id)
        if video_duration_seconds <= 0:
            return 0.0
        return round(info["total_usd"] / video_duration_seconds, 6)

    # ------------------------------------------------------------------
    # Budget governance
    # ------------------------------------------------------------------

    def check_budget(
        self, budget_remaining_usd: float, estimated_cost_usd: float
    ) -> tuple[bool, list[str]]:
        """
        Check whether an upcoming operation fits within the remaining budget.

        Returns:
            (within_budget, alternatives)
            If over budget, alternatives contains actionable suggestions.
        """
        within_budget = estimated_cost_usd <= budget_remaining_usd
        alternatives: list[str] = []

        if not within_budget:
            alternatives = [
                "Switch portrait shots from KLING_3_0 ($0.56/shot) to LTX ($0.10/shot)",  # prices = API_COST_USD rows
                "Use GPT-4.1-nano instead of GPT-4o for classification tasks",
                "Reduce output token budget by requesting shorter responses",
                "Batch similar operations to reduce per-call overhead",
                "Use Gemini-2.5-flash ($0.30/1M in) instead of GPT-4.1 ($2.00/1M in) for draft generation",
            ]

        return within_budget, alternatives

    # ------------------------------------------------------------------
    # Summary / reporting
    # ------------------------------------------------------------------

    def get_summary(self) -> str:
        """
        Return a formatted text summary of all tracked costs.

        Includes total spend, spend by provider, spend by operation,
        and cost efficiency metrics.
        """
        with self._conn_lock:
            rows = self.conn.execute("SELECT * FROM cost_log").fetchall()
        if not rows:
            return "No cost data recorded yet."

        total = 0.0
        llm_total = 0.0  # LLM-only spend, used by the per-LLM efficiency metrics
        by_provider: dict[str, float] = {}
        by_operation: dict[str, float] = {}
        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        api_calls = 0

        for r in rows:
            cost = r["cost_usd"]
            total += cost
            by_provider[r["provider"]] = by_provider.get(r["provider"], 0.0) + cost
            by_operation[r["operation"]] = by_operation.get(r["operation"], 0.0) + cost
            total_input_tokens += r["input_tokens"]
            total_output_tokens += r["output_tokens"]
            if r["input_tokens"] > 0 or r["output_tokens"] > 0:
                llm_calls += 1
                llm_total += cost
            else:
                api_calls += 1

        lines: list[str] = []
        lines.append("=" * 52)
        lines.append("  CINEMA PIPELINE COST SUMMARY")
        lines.append("=" * 52)
        lines.append(f"  Total Spend:          ${total:.4f}")
        lines.append(f"  LLM Calls:            {llm_calls}")
        lines.append(f"  API Calls:            {api_calls}")
        lines.append(f"  Total Input Tokens:   {total_input_tokens:,}")
        lines.append(f"  Total Output Tokens:  {total_output_tokens:,}")
        lines.append("")

        # Spend by provider
        lines.append("  --- Spend by Provider ---")
        for prov in sorted(by_provider, key=by_provider.get, reverse=True):
            pct = (by_provider[prov] / total * 100) if total else 0
            bar = "#" * int(pct / 2)
            lines.append(f"  {prov:<14} ${by_provider[prov]:>8.4f}  {pct:5.1f}%  {bar}")
        lines.append("")

        # Spend by operation
        lines.append("  --- Spend by Operation ---")
        for op in sorted(by_operation, key=by_operation.get, reverse=True):
            pct = (by_operation[op] / total * 100) if total else 0
            lines.append(f"  {op:<28} ${by_operation[op]:>8.4f}  {pct:5.1f}%")
        lines.append("")

        # Efficiency metrics — use LLM-only totals so API spend doesn't
        # inflate the per-LLM-call averages.
        if llm_calls > 0:
            avg_llm_cost = llm_total / llm_calls
            lines.append("  --- Efficiency Metrics ---")
            lines.append(f"  Avg cost per LLM call:  ${avg_llm_cost:.6f}")
            if total_input_tokens > 0:
                cost_per_1k_in = (llm_total / total_input_tokens) * 1000
                lines.append(f"  Cost per 1K input tok:  ${cost_per_1k_in:.6f}")

        lines.append("=" * 52)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Close the underlying database connection idempotently."""
        with self._conn_lock:
            if self._closed:
                return
            self.conn.close()
            self._closed = True

    def __enter__(self) -> "CostTracker":
        if self._closed:
            raise RuntimeError("CostTracker is already closed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False

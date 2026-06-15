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

Construct ``CostTracker(budget_usd=N)`` to enable the soft cap. Call
``would_exceed(api_name)`` before an API call and ``is_over_budget()``
after to gate the pipeline. Both return False when ``budget_usd`` is None
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
    "KLING_NATIVE":  0.50,
    "KLING_3_0":     0.40,
    "SORA_NATIVE":   0.80,
    "SORA_2":        0.60,
    "VEO_NATIVE":    0.30,
    "VEO":           0.25,
    "LTX":           0.10,
    "RUNWAY_GEN4":   0.50,
    "RUNWAY":        0.40,
    "FAL_SVD":       0.20,    # per ~5s clip via fal-ai/fast-svd (conservative estimate; calibrate against fal.ai invoice)
    "SEEDANCE":      0.30,    # per ~5s clip via Seedance 2.0 (conservative estimate; calibrate against Seedance invoice)
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
    "QUALITY_MAX":   0.40,   # N=8 best-of on the pod, ~8x base cost
    "HIDREAM_I1":    0.06,
    # Audio APIs (per clip / per call)
    "STABILITY_FOLEY":   0.03,    # per ~5-60s foley clip via Stable Audio 2.0
    "CARTESIA_SONIC_2":  0.008,   # ~$0.008/shot per descriptor at domain/scene_decomposer.py:67
    "ELEVENLABS":        0.01,    # per ~5s line (typical short dialogue; Eleven v3)
    "SUNO_V5":           0.50,    # per ~60s song via Suno V5 chirp model
    "FAL_STABLE_AUDIO":  0.10,    # per ~47s BGM clip via FAL Stable Audio (production default)
    # Post-processing APIs (per clip / per call)
    "FAL_RIFE":          0.04,    # per clip RIFE frame-interpolation via fal-ai/rife/video
    # Lipsync engines (per dialogue clip). The cascade-winning engine is recorded
    # as LIPSYNC_<engine> (namespaced at cinema/shots/controller.py to avoid
    # colliding with same-named video engines, e.g. lipsync "kling" vs video
    # KLING_NATIVE). Lipsync is MANDATORY for dialogue shots (F1b), so an unpriced
    # cascade silently undercounts the budget gate. Estimates; calibrate vs invoice.
    "LIPSYNC_SYNCSOV3":    0.05,   # sync.so v3 overlay (best generalist) via FAL
    "LIPSYNC_MUSETALK":    0.02,   # MuseTalk mouth-only overlay via FAL
    "LIPSYNC_LATENTSYNC":  0.03,   # LatentSync overlay fallback via FAL
    "LIPSYNC_SYNCV2":      0.10,   # Sync Lipsync v2 (premium) overlay via FAL
    "LIPSYNC_HEDRA":       0.10,   # Hedra Character-3 generation (native API)
    "LIPSYNC_KLING":       0.05,   # Kling lipsync generation via FAL
    "LIPSYNC_OMNIHUMAN":   0.10,   # Omnihuman v1.5 generation via FAL
    "LIPSYNC_AURORA":      0.05,   # Creatify Aurora generation via FAL
    "LIPSYNC_DEFAULT":     0.05,   # fallback when the cascade reports no engine name
}


# ---------------------------------------------------------------------------
# Pricing per 1M tokens
# ---------------------------------------------------------------------------

PRICING = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    # Deprecated-model row kept for historical cost entries (retires 2026-06-15):
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    # claude-opus-4-20250918 row dropped (T-E hygiene): the id never existed at
    # the API (404'd — see ensemble.py item-G scrub), so no historical cost
    # entry can reference it; PRICING is consumed at write time only (:246).
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    # OpenAI
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Google
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
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
    consolidation is deferred to the dedicated import-swap pass. Mirrors the
    ``quality_max:191`` documented-temporary local-copy precedent.
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
        self.db_path = db_path or os.environ.get("EXPERIMENTS_DB_PATH", "data/experiments.db")
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
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_table(self):
        with self._conn_lock:
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
                    video_id TEXT
                );
            """)
            self.conn.commit()

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

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
    ) -> CostEntry:
        """Insert a cost record into the database."""
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
            warnings.warn(
                f"[cost_tracker] Non-finite cost_usd={cost_usd!r} coerced to 0.0 "
                f"in log() (operation={operation!r}); upstream cost calculation "
                f"produced NaN/inf — check the caller for division by zero or "
                f"NaN duration. Gate stays ALIVE for real subsequent spend "
                f"(cost-spent-nan-poison, ADR-026 symmetric-endpoint guard).",
                stacklevel=3,
            )
            cost_usd = 0.0
        with self._conn_lock:
            self.conn.execute(
                """
                INSERT INTO cost_log
                    (timestamp, provider, model, operation, input_tokens, output_tokens, cost_usd, shot_id, video_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, provider, model, operation, input_tokens, output_tokens, cost_usd, shot_id, video_id),
            )
            self.conn.commit()
            # spent_usd mirrors the persisted spend. Increment at this sole write
            # chokepoint (log_api/log_llm both delegate here) so every logged cost
            # reaches the in-process accumulator the budget gate reads
            # (would_exceed/is_over_budget). Placed AFTER commit so a failed INSERT
            # never inflates the accumulator.
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
        PRICING table. If the model is unknown, emits a warning AND prints
        a banner so the cost is not silently lost (previously this defaulted
        to $0.00 with no signal, breaking budget governance).
        """
        provider = _detect_provider(model)
        if model not in PRICING:
            warnings.warn(
                f"[cost_tracker] Unknown model {model!r}; recording $0.00 cost. "
                f"Add it to PRICING in cost_tracker.py for accurate budgeting.",
                stacklevel=2,
            )
            print(f"⚠️ [COST] Unknown model {model!r} — cost not tracked.")
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
        )

    def record_api_call(
        self,
        api_name: str,
        cost_usd: Optional[float] = None,
        operation: str = "",
        shot_id: str = "",
        video_id: str = "",
    ) -> float:
        """Record a generation API call against the budget.

        Looks up ``api_name`` in ``API_COST_USD`` if ``cost_usd`` is not
        supplied. Updates ``self.spent_usd`` (in-process accumulator) and
        persists to SQLite.  Returns the cost recorded.

        Only call on the *success* path — never for failed API attempts.
        """
        api_upper = api_name.upper()
        if cost_usd is None:
            cost_usd = API_COST_USD.get(api_upper, 0.0)
            if cost_usd == 0.0 and api_upper not in API_COST_USD:
                warnings.warn(
                    f"[cost_tracker] Unknown API {api_name!r}; recording $0.00 cost. "
                    f"Add it to API_COST_USD in cost_tracker.py for accurate budgeting.",
                    stacklevel=2,
                )

        # Derive a human-readable provider name from the API key.
        # Prefix match in insertion order; first hit wins. Pod (ComfyUI/PuLID)
        # image backends map to a provider DISTINCT from "fal" so cost_log can
        # tell "ran on the pod" from "fell back to FAL". QUALITY_MAX is the N=8
        # best-of, which also runs on the pod.
        _provider_map = {
            "KLING": "kling", "SORA": "openai", "VEO": "google",
            "LTX": "ltx", "RUNWAY": "runway",
            "COMFYUI": "comfyui", "QUALITY_MAX": "comfyui",
            "POLLINATIONS": "pollinations",
            "FLUX": "fal", "HIDREAM": "fal",
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
        )
        # spent_usd is incremented inside log() (the sole write chokepoint that
        # log_api delegates to), so accumulating it again here would double-count.
        return cost_usd

    # ------------------------------------------------------------------
    # Budget gate
    # ------------------------------------------------------------------

    def would_exceed(self, api_name: str) -> bool:
        """Pre-emptive check: would recording this call push us over budget?

        Returns False when ``budget_usd`` is None (no limit).

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
        cost = API_COST_USD.get(api_name.upper(), 0.0)
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
                warnings.warn(
                    f"[cost_tracker] Non-finite persisted spend total={total!r} "
                    f"for video_id={video_id!r}; budget gate will fail closed.",
                    stacklevel=2,
                )
                spent = float("inf")
            self.spent_usd = spent
            return self.spent_usd

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
                "Switch portrait shots from KLING_NATIVE ($0.15/shot) to LTX ($0.05/shot)",
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
        """Close the underlying database connection."""
        with self._conn_lock:
            self.conn.close()

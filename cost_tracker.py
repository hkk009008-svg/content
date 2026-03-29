"""
Cost tracking and budget governance system for the cinema pipeline.

Tracks all LLM and API costs across providers, models, and operations.
Provides budget checking, cost-per-second analysis, and spend summaries.
"""

import sqlite3
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Pricing per 1M tokens
# ---------------------------------------------------------------------------

PRICING = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250918": {"input": 5.00, "output": 25.00},
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

class CostTracker:
    """
    Persistent cost tracker backed by SQLite.

    Logs every LLM and API call, calculates running totals, enforces budgets,
    and produces spend summaries for the cinema pipeline.
    """

    def __init__(self, db_path: str = "experiments.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_table(self):
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
        ts = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO cost_log
                (timestamp, provider, model, operation, input_tokens, output_tokens, cost_usd, shot_id, video_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, provider, model, operation, input_tokens, output_tokens, cost_usd, shot_id, video_id),
        )
        self.conn.commit()
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
        PRICING table.  Falls back to $0.00 if the model is unknown.
        """
        provider = _detect_provider(model)
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

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_video_cost(self, video_id: str) -> dict:
        """
        Return a cost breakdown for a single video project.

        Returns dict with keys:
            total_usd, llm_usd, api_usd,
            breakdown_by_provider, breakdown_by_operation, shot_count
        """
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

    def get_session_cost(self) -> float:
        """Total cost of the current session (last 24 hours)."""
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
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
        rows = self.conn.execute("SELECT * FROM cost_log").fetchall()
        if not rows:
            return "No cost data recorded yet."

        total = 0.0
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

        # Efficiency metrics
        if llm_calls > 0:
            avg_llm_cost = total / llm_calls if llm_calls else 0
            lines.append("  --- Efficiency Metrics ---")
            lines.append(f"  Avg cost per LLM call:  ${avg_llm_cost:.6f}")
            if total_input_tokens > 0:
                cost_per_1k_in = (total / total_input_tokens) * 1000
                lines.append(f"  Cost per 1K input tok:  ${cost_per_1k_in:.6f}")

        lines.append("=" * 52)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Close the underlying database connection."""
        self.conn.close()

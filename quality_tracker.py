"""
quality_tracker.py -- Quality tracking and regression detection for the cinema pipeline.

Stores per-shot quality metrics in SQLite (experiments.db) and provides
baseline computation, regression alerts, API leaderboards, and cost summaries
that feed into phase_e_learning.py calibration and workflow_selector routing.
"""

import sqlite3
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# VBench result dataclass -- mirrors the six VBench evaluation dimensions
# plus an overall composite score.  Scores are 0-1 (higher = better).
# ---------------------------------------------------------------------------

@dataclass
class VBenchResult:
    identity_score: float = 0.0
    flicker_score: float = 0.0
    motion_score: float = 0.0
    aesthetic_score: float = 0.0
    prompt_adherence_score: float = 0.0
    physics_score: float = 0.0
    overall_vbench: float = 0.0


# ---------------------------------------------------------------------------
# Regression alert emitted when a dimension drops below baseline - tolerance.
# ---------------------------------------------------------------------------

@dataclass
class RegressionAlert:
    dimension: str
    current: float
    baseline: float
    delta: float


# ---------------------------------------------------------------------------
# Dimension names kept in a single place for iteration.
# ---------------------------------------------------------------------------

VBENCH_DIMENSIONS = [
    "identity_score",
    "flicker_score",
    "motion_score",
    "aesthetic_score",
    "prompt_adherence_score",
    "physics_score",
    "overall_vbench",
]


# ---------------------------------------------------------------------------
# QualityTracker
# ---------------------------------------------------------------------------

class QualityTracker:
    """Persists per-shot quality metrics and surfaces baselines, regressions,
    API rankings, and cost summaries for the cinema pipeline."""

    def __init__(self, db_path: str = "experiments.db"):
        self.db_path = db_path
        # For in-memory DBs, keep a single persistent connection so the
        # schema survives across method calls.  File-backed DBs open a
        # fresh connection each time (safe for multi-process pipelines).
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        self._ensure_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _close(self, conn: sqlite3.Connection) -> None:
        """Close the connection unless it is the persistent in-memory one."""
        if conn is not self._persistent_conn:
            conn.close()

    def _ensure_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shot_quality (
                    shot_id TEXT PRIMARY KEY,
                    video_id TEXT,
                    shot_type TEXT,
                    target_api TEXT,
                    generation_attempt INTEGER DEFAULT 1,
                    -- VBench dimensions (0-1 scale)
                    identity_score REAL DEFAULT 0.0,
                    flicker_score REAL DEFAULT 0.0,
                    motion_score REAL DEFAULT 0.0,
                    aesthetic_score REAL DEFAULT 0.0,
                    prompt_adherence_score REAL DEFAULT 0.0,
                    physics_score REAL DEFAULT 0.0,
                    overall_vbench REAL DEFAULT 0.0,
                    -- Legacy metrics
                    identity_similarity REAL DEFAULT 0.0,
                    coherence_score REAL DEFAULT 0.0,
                    -- Cost tracking
                    generation_cost_usd REAL DEFAULT 0.0,
                    llm_cost_usd REAL DEFAULT 0.0,
                    total_cost_usd REAL DEFAULT 0.0,
                    -- Meta
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            self._close(conn)

    # ------------------------------------------------------------------
    # (a) log_shot_quality
    # ------------------------------------------------------------------

    def log_shot_quality(
        self,
        shot_id: str,
        video_id: str,
        shot_type: str,
        target_api: str,
        vbench_result: Optional[VBenchResult] = None,
        identity_similarity: float = 0.0,
        coherence_score: float = 0.0,
        generation_cost: float = 0.0,
        llm_cost: float = 0.0,
        attempt: int = 1,
    ) -> None:
        """Insert or replace a shot's quality record."""

        vb = vbench_result or VBenchResult()
        total_cost = generation_cost + llm_cost

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO shot_quality (
                    shot_id, video_id, shot_type, target_api, generation_attempt,
                    identity_score, flicker_score, motion_score,
                    aesthetic_score, prompt_adherence_score, physics_score,
                    overall_vbench,
                    identity_similarity, coherence_score,
                    generation_cost_usd, llm_cost_usd, total_cost_usd,
                    created_at
                ) VALUES (?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?,
                          ?, ?,
                          ?, ?, ?,
                          ?)
                """,
                (
                    shot_id, video_id, shot_type, target_api, attempt,
                    vb.identity_score, vb.flicker_score, vb.motion_score,
                    vb.aesthetic_score, vb.prompt_adherence_score, vb.physics_score,
                    vb.overall_vbench,
                    identity_similarity, coherence_score,
                    generation_cost, llm_cost, total_cost,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        finally:
            self._close(conn)

    # ------------------------------------------------------------------
    # (b) get_baseline
    # ------------------------------------------------------------------

    def get_baseline(self, window: int = 20) -> Dict[str, float]:
        """Return mean per-dimension scores over the last *window* shots."""

        cols = ", ".join(f"AVG({d})" for d in VBENCH_DIMENSIONS)
        sql = f"""
            SELECT {cols}
            FROM (
                SELECT * FROM shot_quality
                ORDER BY created_at DESC
                LIMIT ?
            )
        """

        conn = self._connect()
        try:
            row = conn.execute(sql, (window,)).fetchone()
        finally:
            self._close(conn)

        if row is None:
            return {d: 0.0 for d in VBENCH_DIMENSIONS}

        return {
            dim: (row[i] if row[i] is not None else 0.0)
            for i, dim in enumerate(VBENCH_DIMENSIONS)
        }

    # ------------------------------------------------------------------
    # (c) check_regression
    # ------------------------------------------------------------------

    def check_regression(
        self,
        current_vbench: VBenchResult,
        tolerance: float = 0.05,
    ) -> List[RegressionAlert]:
        """Compare *current_vbench* against the rolling baseline and return
        alerts for any dimension that drops below baseline - tolerance."""

        baseline = self.get_baseline()
        alerts: List[RegressionAlert] = []

        for dim in VBENCH_DIMENSIONS:
            current_val = getattr(current_vbench, dim)
            baseline_val = baseline.get(dim, 0.0)
            if current_val < baseline_val - tolerance:
                alerts.append(
                    RegressionAlert(
                        dimension=dim,
                        current=current_val,
                        baseline=baseline_val,
                        delta=current_val - baseline_val,
                    )
                )

        return alerts

    # ------------------------------------------------------------------
    # (d) get_api_quality_stats
    # ------------------------------------------------------------------

    def get_api_quality_stats(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Return nested dict {api: {shot_type: {avg_vbench, avg_identity, count, avg_cost}}}
        consumed by workflow_selector for dynamic API routing."""

        sql = """
            SELECT target_api, shot_type,
                   AVG(overall_vbench)   AS avg_vbench,
                   AVG(identity_score)   AS avg_identity,
                   COUNT(*)              AS cnt,
                   AVG(total_cost_usd)   AS avg_cost
            FROM shot_quality
            GROUP BY target_api, shot_type
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            self._close(conn)

        stats: Dict[str, Dict[str, Dict[str, float]]] = {}
        for r in rows:
            api = r["target_api"]
            stype = r["shot_type"]
            stats.setdefault(api, {})[stype] = {
                "avg_vbench": r["avg_vbench"] or 0.0,
                "avg_identity": r["avg_identity"] or 0.0,
                "count": r["cnt"],
                "avg_cost": r["avg_cost"] or 0.0,
            }

        return stats

    # ------------------------------------------------------------------
    # (e) get_video_cost_summary
    # ------------------------------------------------------------------

    def get_video_cost_summary(self, video_id: str) -> Dict[str, float]:
        """Return cost totals for a single video."""

        sql = """
            SELECT SUM(total_cost_usd)      AS total,
                   SUM(generation_cost_usd)  AS gen,
                   SUM(llm_cost_usd)         AS llm,
                   COUNT(*)                  AS shots
            FROM shot_quality
            WHERE video_id = ?
        """

        conn = self._connect()
        try:
            row = conn.execute(sql, (video_id,)).fetchone()
        finally:
            self._close(conn)

        if row is None or row["shots"] == 0:
            return {
                "total_cost_usd": 0.0,
                "generation_cost_usd": 0.0,
                "llm_cost_usd": 0.0,
                "shot_count": 0,
            }

        return {
            "total_cost_usd": row["total"] or 0.0,
            "generation_cost_usd": row["gen"] or 0.0,
            "llm_cost_usd": row["llm"] or 0.0,
            "shot_count": row["shots"],
        }

    # ------------------------------------------------------------------
    # (f) get_batch_quality_summary
    # ------------------------------------------------------------------

    def get_batch_quality_summary(self, window: int = 50) -> str:
        """Return a human-readable summary of the last *window* shots
        suitable for feeding into phase_e_learning.py calibration."""

        # -- Per-API averages over the window --
        sql_api = """
            SELECT target_api,
                   AVG(overall_vbench)       AS avg_vbench,
                   AVG(identity_score)       AS avg_identity,
                   AVG(flicker_score)        AS avg_flicker,
                   AVG(motion_score)         AS avg_motion,
                   AVG(aesthetic_score)       AS avg_aesthetic,
                   AVG(prompt_adherence_score) AS avg_prompt,
                   AVG(physics_score)        AS avg_physics,
                   AVG(total_cost_usd)       AS avg_cost,
                   COUNT(*)                  AS cnt
            FROM (
                SELECT * FROM shot_quality
                ORDER BY created_at DESC
                LIMIT ?
            )
            GROUP BY target_api
        """

        # -- Trend: compare first half vs second half of the window --
        sql_trend = """
            SELECT half,
                   AVG(overall_vbench)  AS avg_vbench
            FROM (
                SELECT overall_vbench,
                       CASE WHEN rownum <= ? THEN 'recent' ELSE 'older' END AS half
                FROM (
                    SELECT overall_vbench,
                           ROW_NUMBER() OVER (ORDER BY created_at DESC) AS rownum
                    FROM shot_quality
                    ORDER BY created_at DESC
                    LIMIT ?
                )
            )
            GROUP BY half
        """

        conn = self._connect()
        try:
            api_rows = conn.execute(sql_api, (window,)).fetchall()
            half = window // 2
            trend_rows = conn.execute(sql_trend, (half, window)).fetchall()
        finally:
            self._close(conn)

        if not api_rows:
            return "No shot quality data available yet."

        lines: List[str] = []
        lines.append(f"=== Batch Quality Summary (last {window} shots) ===\n")

        # Best / worst per dimension
        dim_labels = {
            "avg_vbench": "Overall VBench",
            "avg_identity": "Identity",
            "avg_flicker": "Flicker",
            "avg_motion": "Motion",
            "avg_aesthetic": "Aesthetic",
            "avg_prompt": "Prompt Adherence",
            "avg_physics": "Physics",
        }
        for col, label in dim_labels.items():
            best_row = max(api_rows, key=lambda r: r[col] or 0.0)
            worst_row = min(api_rows, key=lambda r: r[col] or 0.0)
            lines.append(
                f"  {label}: best={best_row['target_api']} "
                f"({best_row[col]:.3f}), "
                f"worst={worst_row['target_api']} "
                f"({worst_row[col]:.3f})"
            )

        # Trend
        trend_map = {r["half"]: r["avg_vbench"] for r in trend_rows}
        recent = trend_map.get("recent", 0.0) or 0.0
        older = trend_map.get("older", 0.0) or 0.0
        if older > 0:
            pct = ((recent - older) / older) * 100
            direction = "IMPROVING" if pct > 0 else "DECLINING" if pct < 0 else "STABLE"
            lines.append(f"\n  Trend: {direction} ({pct:+.1f}% recent vs older half)")
        else:
            lines.append("\n  Trend: insufficient data for trend analysis")

        # Cost efficiency
        lines.append("\n  Cost Efficiency (quality per dollar):")
        for r in api_rows:
            avg_cost = r["avg_cost"] or 0.0
            avg_q = r["avg_vbench"] or 0.0
            if avg_cost > 0:
                qpd = avg_q / avg_cost
                lines.append(
                    f"    {r['target_api']}: "
                    f"avg_quality={avg_q:.3f}, "
                    f"avg_cost=${avg_cost:.4f}, "
                    f"quality/$ = {qpd:.1f}"
                )
            else:
                lines.append(
                    f"    {r['target_api']}: "
                    f"avg_quality={avg_q:.3f}, "
                    f"avg_cost=$0.0000 (no cost data)"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # (g) get_quality_leaderboard
    # ------------------------------------------------------------------

    def get_quality_leaderboard(self) -> List[Dict[str, float]]:
        """Return API leaderboard sorted by average overall quality."""

        sql = """
            SELECT target_api,
                   AVG(overall_vbench) AS avg_quality,
                   AVG(total_cost_usd) AS avg_cost,
                   AVG(overall_vbench) / NULLIF(AVG(total_cost_usd), 0) AS quality_per_dollar
            FROM shot_quality
            GROUP BY target_api
            ORDER BY avg_quality DESC
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            self._close(conn)

        return [
            {
                "target_api": r["target_api"],
                "avg_quality": r["avg_quality"] or 0.0,
                "avg_cost": r["avg_cost"] or 0.0,
                "quality_per_dollar": r["quality_per_dollar"] or 0.0,
            }
            for r in rows
        ]

"""Backward-compat re-export shim — moved to domain/continuity_engine.py in Phase 8.

This file preserves the legacy ``from continuity_engine import X`` import surface
so external callers (main.py, web_server.py, cinema_pipeline.py,
cleanup.py, tests/) keep working unchanged. New code should import
from ``domain.continuity_engine`` directly.
"""

from domain.continuity_engine import *  # noqa: F401, F403

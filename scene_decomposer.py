"""Backward-compat re-export shim — moved to domain/scene_decomposer.py in Phase 8.

This file preserves the legacy ``from scene_decomposer import X`` import surface
so external callers (main.py, web_server.py, cinema_pipeline.py,
cleanup.py, tests/) keep working unchanged. New code should import
from ``domain.scene_decomposer`` directly.
"""

from domain.scene_decomposer import *  # noqa: F401, F403

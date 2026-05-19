"""Backward-compat re-export shim — moved to domain/character_manager.py in Phase 8.

This file preserves the legacy ``from character_manager import X`` import surface
so external callers (main.py, web_server.py, cinema_pipeline.py,
cleanup.py, tests/) keep working unchanged. New code should import
from ``domain.character_manager`` directly.
"""

from domain.character_manager import *  # noqa: F401, F403

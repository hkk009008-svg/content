"""Backward-compat re-export shim — moved to domain/location_manager.py in Phase 8.

This file preserves the legacy ``from location_manager import X`` import surface
so external callers (main.py, web_server.py, cinema_pipeline.py,
cleanup.py, tests/) keep working unchanged. New code should import
from ``domain.location_manager`` directly.
"""

from domain.location_manager import *  # noqa: F401, F403

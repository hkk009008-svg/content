"""Backward-compat re-export shim — moved to domain/dialogue_writer.py in Phase 8.

This file preserves the legacy ``from dialogue_writer import X`` import surface
so external callers (main.py, web_server.py, cinema_pipeline.py,
cleanup.py, tests/) keep working unchanged. New code should import
from ``domain.dialogue_writer`` directly.
"""

from domain.dialogue_writer import *  # noqa: F401, F403

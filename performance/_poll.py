"""Generic task poller for the performance/ adapters.

Each external engine (Runway / Hedra / Viggle / ComfyUI) exposes a polling
endpoint with its own status enum. This helper normalizes the loop:
case-insensitive status comparison, exception-tolerant single-poll failures,
and a clean None return on terminal-state or timeout.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Set


def poll_task(
    get_status: Callable[[], dict],
    *,
    success_states: Set[str],
    terminal_states: Set[str],
    interval_s: float = 3.0,
    timeout_s: float = 300.0,
) -> Optional[dict]:
    """Poll `get_status()` until success, terminal, or timeout.

    Args:
        get_status: callable returning {"status": "...", ...} per call.
            Exceptions raised here are caught — single-poll failures are
            transient (network blips) and shouldn't abort the loop.
        success_states: states the caller wants to keep polling for. The
            status field is uppercased before comparison; pass uppercase
            states for clarity. (Comparisons are case-insensitive.)
        terminal_states: states that mean "give up, no point continuing".
        interval_s: sleep between polls.
        timeout_s: hard ceiling.

    Returns:
        The status dict on success, or None on terminal/timeout.
    """
    success_upper = {s.upper() for s in success_states}
    terminal_upper = {s.upper() for s in terminal_states}
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            status = get_status()
        except Exception:
            time.sleep(interval_s)
            continue
        state = (status.get("status") or "").upper()
        if state in success_upper:
            return status
        if state in terminal_upper:
            return None
        time.sleep(interval_s)
    return None

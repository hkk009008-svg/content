"""Ownership-safe scopes for optional :class:`cost_tracker.CostTracker` values.

Pipeline adapters frequently accept a caller-owned tracker but also support
standalone use.  The standalone fallback owns the SQLite connection it opens;
the injected path does not.  Keeping that distinction in one context manager
prevents both leaked connections and accidental closure of the pipeline's
shared budget tracker.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional


@contextmanager
def cost_tracker_scope(
    cost_tracker=None,
    *,
    budget_usd: Optional[object] = None,
) -> Iterator[object]:
    """Yield an injected tracker or an owned, automatically closed fallback.

    ``cost_tracker`` remains entirely caller-owned.  When it is ``None``, the
    fallback is imported lazily so best-effort accounting sites keep their
    existing optional-dependency behavior.
    """

    if cost_tracker is not None:
        yield cost_tracker
        return

    from cost_tracker import CostTracker

    with CostTracker(budget_usd=budget_usd) as owned_tracker:
        yield owned_tracker

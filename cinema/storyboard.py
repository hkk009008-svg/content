"""Shared Kling storyboard duration policy.

The provider payload and the local FFmpeg split must use the same allocation.
Keeping the allocator pure and provider-neutral prevents the combined clip
from describing one timeline while the splitter assumes another.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


STORYBOARD_MAX_SHOTS = 6
STORYBOARD_MAX_DURATION_S = 15.0
STORYBOARD_MIN_SHOT_DURATION_S = 1.0

_TENTHS_PER_SECOND = 10
_MAX_DURATION_UNITS = int(
    STORYBOARD_MAX_DURATION_S * _TENTHS_PER_SECOND
)
_MIN_SHOT_UNITS = int(
    STORYBOARD_MIN_SHOT_DURATION_S * _TENTHS_PER_SECOND
)


def allocate_storyboard_durations(
    shots: Sequence[Mapping[str, object]],
) -> list[float]:
    """Return the canonical one-decimal duration plan for up to six shots.

    Requested durations are honored in order while reserving the one-second
    minimum for every remaining shot. Missing durations divide the 15-second
    provider allowance evenly. Integer tenths make the post-minimum total cap
    exact rather than relying on floating-point clamping after allocation.

    Raises:
        ValueError: when an explicit duration is not a finite number.
    """

    active_shots = list(shots[:STORYBOARD_MAX_SHOTS])
    shot_count = len(active_shots)
    if shot_count == 0:
        return []

    default_duration = STORYBOARD_MAX_DURATION_S / shot_count
    remaining_units = _MAX_DURATION_UNITS
    allocations: list[float] = []

    for index, shot in enumerate(active_shots):
        raw_duration = shot.get("duration", default_duration)
        try:
            requested = float(raw_duration)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"storyboard shot {index} duration must be a finite number"
            ) from exc
        if not math.isfinite(requested):
            raise ValueError(
                f"storyboard shot {index} duration must be a finite number"
            )

        remaining_shots = shot_count - index - 1
        reserved_units = remaining_shots * _MIN_SHOT_UNITS
        max_current_units = remaining_units - reserved_units
        # Clamp before scaling/converting.  A finite float can still overflow
        # to infinity when multiplied (for example ``sys.float_info.max *
        # 10``), and ``int(round(inf))`` raises OverflowError.  The provider
        # cap makes values beyond this shot's available units equivalent.
        max_current_duration = max_current_units / _TENTHS_PER_SECOND
        if requested <= STORYBOARD_MIN_SHOT_DURATION_S:
            requested_units = _MIN_SHOT_UNITS
        elif requested >= max_current_duration:
            requested_units = max_current_units
        else:
            requested_units = int(
                round(requested * _TENTHS_PER_SECOND)
            )
        allocated_units = min(requested_units, max_current_units)
        allocations.append(allocated_units / _TENTHS_PER_SECOND)
        remaining_units -= allocated_units

    return allocations


__all__ = [
    "STORYBOARD_MAX_DURATION_S",
    "STORYBOARD_MAX_SHOTS",
    "STORYBOARD_MIN_SHOT_DURATION_S",
    "allocate_storyboard_durations",
]

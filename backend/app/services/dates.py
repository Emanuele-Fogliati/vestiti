"""Spreading days over stops when the traveller did not say how long each one lasts.

The same rule runs in the browser (frontend/src/lib/spread.ts) for the draft, so the
draft and the saved trip agree: stops with known days keep them, the others share
what is left of the total as evenly as possible (earlier stops get the extra day),
and every stop gets at least one day.
"""
from __future__ import annotations

from datetime import date, timedelta

DEFAULT_DAYS = 2  # per place, when nobody said how long the trip is


def spread(known: list[int | None], total: int | None) -> list[int]:
    """Days per stop. known[i] is the stop's days when the traveller said it, else None."""
    free = [i for i, k in enumerate(known) if k is None]
    out = [k or 0 for k in known]
    if not free:
        return out
    if total is None:
        left = DEFAULT_DAYS * len(free)
    else:
        left = max(total - sum(k for k in known if k), len(free))
    base, extra = divmod(left, len(free))
    for j, i in enumerate(free):
        out[i] = base + (1 if j < extra else 0)
    return out


def lay_out(days: list[int], start: date) -> list[tuple[date, date]]:
    """Back-to-back stops: each starts the day after the previous one ends."""
    out, cur = [], start
    for d in days:
        end = cur + timedelta(days=max(d, 1) - 1)
        out.append((cur, end))
        cur = end + timedelta(days=1)
    return out

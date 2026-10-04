# SPDX-License-Identifier: GPL-3.0-or-later
"""Onion skin window math (design/sculpt-ux.md, "Onion skin"). Pure (no bpy).

The ghosts cover the time ruler window ``[f0 − r_past, f0 + r_future]``: one ghost every ``step``
frames on each side, at most ``max_ghosts`` per side. The step is the smallest integer that makes the
longer side fit, and is shared by both sides (the LMP has a single ``onion_step``).
"""

from __future__ import annotations

import math


def window(radius_past: float, radius_future: float, max_ghosts: int = 12) -> tuple[int, int, int]:
    """``(before, after, step)``: ghost counts per side and the frames between ghosts.

    Ghosts sit at ``f0 − step·i`` (i = 1..before) and ``f0 + step·i`` (i = 1..after), all inside the
    window. A radius of 0 (or less than one frame) gives no ghost on that side."""
    max_ghosts = max(1, int(max_ghosts))
    n_past = max(0, int(math.floor(float(radius_past) + 1e-6)))
    n_future = max(0, int(math.floor(float(radius_future) + 1e-6)))
    longest = max(n_past, n_future)
    step = longest // (max_ghosts + 1) + 1       # smallest step with longest // step <= max_ghosts
    return n_past // step, n_future // step, step


def spread_offset(frame: int, current: int, step: int, spacing: float) -> float:
    """Signed distance along the view's right axis of the ghost at ``frame`` (0 at the current frame):
    ``spacing`` per ghost step, past negative (left), future positive (right)."""
    return spacing * (frame - current) / max(1, int(step))

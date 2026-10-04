# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry of the time ruler drawn in the viewport (frame ⇄ pixel, ticks, handle hit-test).

Pure (no bpy) so it is unit-testable; ``interaction/hud.py`` draws it and routes the clicks. The ruler
is centred on the current frame f₀ and shows the gesture window ``[f₀ − r_past, f₀ + r_future]``
(design/ephemeral-rig.md, "Régua de tempo no viewport").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_HALF_SPAN = 20          # frames shown on each side of f₀ at least
MAX_WIDTH_PX = 560.0        # ruler width at UI scale 1
SIDE_MARGIN_PX = 40.0
BOTTOM_PX = 30.0            # strip bottom above the region bottom
HEIGHT_PX = 16.0            # strip height
HANDLE_TOL_PX = 8.0         # horizontal pick tolerance of an end handle
NICE_STEPS = (1, 2, 5, 10, 20, 50, 100, 200, 500)

PAST, FUTURE = "PAST", "FUTURE"


def half_span_for(radius_past: float, radius_future: float) -> int:
    """Frames shown on each side of f₀: the window plus 25 %, rounded up to 5, at least MIN_HALF_SPAN."""
    r = max(float(radius_past), float(radius_future), 0.0)
    return max(MIN_HALF_SPAN, int(math.ceil(r * 1.25 / 5.0)) * 5)


def tick_step(ppf: float, min_px: float) -> int:
    """Smallest "nice" frame step whose ticks are at least ``min_px`` apart."""
    for step in NICE_STEPS:
        if step * ppf >= min_px:
            return step
    return NICE_STEPS[-1]


@dataclass(frozen=True)
class Layout:
    cx: float           # x of f₀ (region pixels)
    y: float            # bottom of the strip
    width: float
    height: float
    ppf: float          # pixels per frame
    f0: float
    half_span: int
    px: float           # UI scale

    @property
    def left(self) -> float:
        return self.cx - self.width / 2.0

    @property
    def right(self) -> float:
        return self.cx + self.width / 2.0

    def x_of(self, frame: float) -> float:
        return self.cx + (float(frame) - self.f0) * self.ppf

    def frame_of(self, x: float) -> float:
        return self.f0 + (float(x) - self.cx) / self.ppf

    def ticks(self):
        """[(frame, is_labelled)] of the integer frames drawn as ticks inside the ruler."""
        major = tick_step(self.ppf, 40.0 * self.px)
        minor = tick_step(self.ppf, 6.0 * self.px)
        lo = int(math.ceil(self.f0 - self.half_span))
        hi = int(math.floor(self.f0 + self.half_span))
        out = []
        for f in range(lo, hi + 1):
            if f % minor == 0:
                out.append((f, f % major == 0))
        return out


def layout(region_width: float, region_height: float, px: float, f0: float, half_span: int) -> Layout | None:
    """Ruler geometry for a region, or None when the region is too small to show it."""
    width = min(float(region_width) - 2.0 * SIDE_MARGIN_PX * px, MAX_WIDTH_PX * px)
    if width < 120.0 * px or region_height < 120.0 * px or half_span <= 0:
        return None
    return Layout(cx=float(region_width) / 2.0, y=BOTTOM_PX * px, width=width, height=HEIGHT_PX * px,
                  ppf=width / (2.0 * half_span), f0=float(f0), half_span=int(half_span), px=float(px))


def handle_x(lay: Layout, side: str, radius_past: float, radius_future: float) -> float:
    """x of an end handle, clamped to the ruler (a window wider than the ruler pins it to the edge)."""
    frame = lay.f0 - radius_past if side == PAST else lay.f0 + radius_future
    return min(max(lay.x_of(frame), lay.left), lay.right)


def hit_handle(lay: Layout, mouse, radius_past: float, radius_future: float) -> str | None:
    """PAST / FUTURE when ``mouse`` is on an end handle, else None.

    Coincident handles (radius 0 on both sides) are split by the side of the mouse: left = PAST.
    """
    mx, my = float(mouse[0]), float(mouse[1])
    tol = HANDLE_TOL_PX * lay.px
    if not (lay.y - tol <= my <= lay.y + lay.height + tol):
        return None
    xp = handle_x(lay, PAST, radius_past, radius_future)
    xf = handle_x(lay, FUTURE, radius_past, radius_future)
    dp, df = abs(mx - xp), abs(mx - xf)
    if min(dp, df) > tol:
        return None
    if dp == df:
        return PAST if mx < xp else FUTURE
    return PAST if dp < df else FUTURE


def radius_from_x(lay: Layout, side: str, x: float, snap: bool = True) -> float:
    """Radius of ``side`` when its handle is dragged to ``x`` (never negative; whole frames if ``snap``)."""
    frame = lay.frame_of(x)
    r = lay.f0 - frame if side == PAST else frame - lay.f0
    r = max(0.0, min(500.0, r))
    return float(round(r)) if snap else r

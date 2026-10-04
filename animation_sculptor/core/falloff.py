# SPDX-License-Identifier: GPL-3.0-or-later
"""Falloff curves for soft operations (pure numpy). Same shapes as Blender's proportional editing."""

from __future__ import annotations

import numpy as np

SHAPES = ("SMOOTH", "LINEAR", "SHARP", "SPHERE", "CONSTANT")


def weight(distance, radius, shape="SMOOTH"):
    """Weight in [0, 1] for ``distance`` (frames) within ``radius``: 1 at 0, 0 at/after the radius.

    ``radius <= 0`` means "only the grabbed point": weight 1 at distance 0, else 0.
    """
    d = np.abs(np.asarray(distance, dtype=np.float64))
    if radius <= 0.0:
        return np.where(d == 0.0, 1.0, 0.0)
    x = np.clip(1.0 - d / float(radius), 0.0, 1.0)     # 1 at the center, 0 at the radius
    if shape == "LINEAR":
        w = x
    elif shape == "SHARP":
        w = x * x
    elif shape == "SPHERE":
        w = np.sqrt(np.clip(2.0 * x - x * x, 0.0, 1.0))
    elif shape == "CONSTANT":
        w = np.where(x > 0.0, 1.0, 0.0)
    elif shape == "SMOOTH":
        w = 3.0 * x * x - 2.0 * x * x * x
    else:
        raise ValueError(f"unknown falloff shape {shape!r}")
    return np.where(d == 0.0, 1.0, w)


def weight_signed(offset, radius_past, radius_future, shape="SMOOTH"):
    """Asymmetric falloff: ``offset`` = frame − f₀ (signed). Negative offsets use ``radius_past``,
    positive ones ``radius_future``; 1 at 0. A side with radius 0 only keeps the centre."""
    o = np.asarray(offset, dtype=np.float64)
    past = weight(o, radius_past, shape)
    future = weight(o, radius_future, shape)
    return np.where(o < 0.0, past, future)

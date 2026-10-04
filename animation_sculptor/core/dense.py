# SPDX-License-Identifier: GPL-3.0-or-later
"""Dense key writing for the ephemeral gesture (pure numpy — ADR 0011, docs/design/ephemeral-rig.md,
"Keys densas: regra de escrita").

One key per integer frame of the window ``[a, b]``. To leave everything outside the window unchanged,
the written range is extended to the nearest existing key on each side (``k_left`` < a, ``k_right`` > b)
with the current values there (weight 0); keys strictly between ``k_left`` and ``k_right`` are replaced.
The two border keys keep their coordinates and their outer handle bit for bit; an ``AUTO*``/``ALIGNED``
border is frozen to ``ALIGNED`` with the inner handle collinear (Blender's ``fcurve.update()`` keeps
collinear ALIGNED handles), so the segments outside ``[k_left, k_right]`` do not move.

Invariants (tests): integer frames outside ``[a, b]`` evaluate as before (1e-6); keys outside
``[k_left, k_right]`` are bit-identical; writing the current values back changes no integer frame.

Dense keys are ``BEZIER`` with ``AUTO_CLAMPED`` handles; their handle coordinates here are an
approximation (Blender recomputes them on write) — only integer frames are exact, which is all the
trail and the invariants use.
"""

from __future__ import annotations

import math

import numpy as np

from . import bezier
from .fcurve_model import ChannelModel

FRAME_EPS = 1e-3
FREEZE = ("AUTO", "AUTO_CLAMPED", "ALIGNED")


def _auto_clamped_handles(x, y):
    """Approximate AUTO_CLAMPED handles for keys one frame apart: slope from the neighbours, flat at
    extremes and at the ends; handle length one third of the segment."""
    k = len(x)
    slope = np.zeros(k)
    if k > 2:
        dy_prev = y[1:-1] - y[:-2]
        dy_next = y[2:] - y[1:-1]
        s = (y[2:] - y[:-2]) / (x[2:] - x[:-2])
        extreme = dy_prev * dy_next <= 0.0
        slope[1:-1] = np.where(extreme, 0.0, s)
    left = np.empty(k)
    right = np.empty(k)
    left[0] = (x[1] - x[0]) / 3.0 if k > 1 else 1.0 / 3.0
    right[-1] = (x[-1] - x[-2]) / 3.0 if k > 1 else 1.0 / 3.0
    if k > 1:
        left[1:] = (x[1:] - x[:-1]) / 3.0
        right[:-1] = (x[1:] - x[:-1]) / 3.0
    hl = np.stack((x - left, y - slope * left), axis=1)
    hr = np.stack((x + right, y + slope * right), axis=1)
    return hl, hr


def _freeze_border(out: ChannelModel, j: int, inner: str, inner_dx: float) -> None:
    """Border key j: keep the outer handle, put the inner one (side ``inner`` = 'R' or 'L') ``inner_dx``
    frames away, collinear when the key is AUTO*/ALIGNED (then both sides become ALIGNED)."""
    key = out.co[j].copy()
    outer = out.hl[j] if inner == "R" else out.hr[j]
    inner_h = out.hr[j] if inner == "R" else out.hl[j]
    sign = 1.0 if inner == "R" else -1.0
    t_inner = out.hr_type[j] if inner == "R" else out.hl_type[j]
    t_outer = out.hl_type[j] if inner == "R" else out.hr_type[j]
    if t_inner in FREEZE or t_outer in FREEZE:
        dx = key[0] - outer[0]
        slope = (key[1] - outer[1]) / dx if abs(dx) > 1e-12 else 0.0
        new = np.array([key[0] + sign * inner_dx, key[1] + slope * sign * inner_dx])
        out.hl_type[j] = "ALIGNED"
        out.hr_type[j] = "ALIGNED"
    elif t_inner == "FREE":
        dx = inner_h[0] - key[0]
        slope = (inner_h[1] - key[1]) / dx if abs(dx) > 1e-12 else 0.0
        new = np.array([key[0] + sign * inner_dx, key[1] + slope * sign * inner_dx])
    else:   # VECTOR: Blender points it at the new neighbour on update; keep a consistent guess
        new = inner_h.copy()
        new[0] = key[0] + sign * inner_dx
    if inner == "R":
        out.hr[j] = new
    else:
        out.hl[j] = new


def window_span(model: ChannelModel, a: int, b: int):
    """(f_start, f_end, k_left, k_right): integer frames that will hold dense keys and the indices of
    the border keys (None when there is no key on that side)."""
    x = model.frames
    left = np.nonzero(x < a - FRAME_EPS)[0]
    right = np.nonzero(x > b + FRAME_EPS)[0]
    k_left = int(left[-1]) if len(left) else None
    k_right = int(right[0]) if len(right) else None
    f_start = int(math.floor(x[k_left] + FRAME_EPS)) + 1 if k_left is not None else int(a)
    f_end = int(math.ceil(x[k_right] - FRAME_EPS)) - 1 if k_right is not None else int(b)
    return min(f_start, int(a)), max(f_end, int(b)), k_left, k_right


def current_values(model: ChannelModel, start: int, count: int):
    """Values of ``model`` at the frames ``write_dense(model, start, <count values>)`` keys from the curve
    itself (the extension to the neighbour keys). Constant during a gesture: compute once, pass as
    ``current`` (the evaluation is most of the cost of a write)."""
    if model.key_count == 0 or count <= 0:
        return None
    f_start, f_end, _kl, _kr = window_span(model, int(start), int(start) + count - 1)
    return bezier.evaluate(model, np.arange(f_start, f_end + 1, dtype=np.float64))


def write_dense(model: ChannelModel, start: int, values, default: float = 0.0, current=None) -> ChannelModel:
    """Dense keys at frames ``start … start + len(values) − 1`` with ``values``; returns a new model.

    ``default`` is the channel value when the model has no key (the property's current value);
    ``current`` the cached ``current_values(model, start, len(values))``."""
    values = np.asarray(values, dtype=np.float64)
    a, b = int(start), int(start) + len(values) - 1
    if len(values) == 0:
        return model.copy()
    if model.key_count == 0:
        x = np.arange(a, b + 1, dtype=np.float64)
        hl, hr = _auto_clamped_handles(x, values)
        k = len(x)
        return ChannelModel(np.stack((x, values), axis=1), hl, hr, ["AUTO_CLAMPED"] * k, ["AUTO_CLAMPED"] * k,
                            ["BEZIER"] * k, model.extrapolation, model.data_path, model.index)

    f_start, f_end, k_left, k_right = window_span(model, a, b)
    frames = np.arange(f_start, f_end + 1, dtype=np.float64)
    if current is None or len(current) != len(frames):
        current = bezier.evaluate(model, frames)
    dense_y = np.where((frames >= a) & (frames <= b), 0.0, current)
    inside = (frames >= a) & (frames <= b)
    dense_y[inside] = values[(frames[inside] - a).astype(int)]

    keep_left = slice(0, k_left + 1) if k_left is not None else slice(0, 0)
    keep_right = slice(k_right, None) if k_right is not None else slice(0, 0)
    n_left = (k_left + 1) if k_left is not None else 0

    # handles of the dense run, with the border keys as neighbours so the slopes see them
    run_x, run_y = frames, dense_y
    if k_left is not None:
        run_x = np.r_[model.co[k_left, 0], run_x]
        run_y = np.r_[model.co[k_left, 1], run_y]
    if k_right is not None:
        run_x = np.r_[run_x, model.co[k_right, 0]]
        run_y = np.r_[run_y, model.co[k_right, 1]]
    hl, hr = _auto_clamped_handles(run_x, run_y)
    lo = 1 if k_left is not None else 0
    hl, hr = hl[lo:lo + len(frames)], hr[lo:lo + len(frames)]

    co = np.concatenate((model.co[keep_left], np.stack((frames, dense_y), axis=1), model.co[keep_right]))
    out_hl = np.concatenate((model.hl[keep_left], hl, model.hl[keep_right]))
    out_hr = np.concatenate((model.hr[keep_left], hr, model.hr[keep_right]))
    k = len(frames)
    out = ChannelModel(co, out_hl, out_hr,
                       model.hl_type[keep_left] + ["AUTO_CLAMPED"] * k + model.hl_type[keep_right],
                       model.hr_type[keep_left] + ["AUTO_CLAMPED"] * k + model.hr_type[keep_right],
                       model.interp[keep_left] + ["BEZIER"] * k + model.interp[keep_right],
                       model.extrapolation, model.data_path, model.index)
    if k_left is not None:
        _freeze_border(out, n_left - 1, "R", (frames[0] - model.co[k_left, 0]) / 3.0)
    if k_right is not None:
        _freeze_border(out, n_left + k, "L", (model.co[k_right, 0] - frames[-1]) / 3.0)
    return out

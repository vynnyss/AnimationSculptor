# SPDX-License-Identifier: GPL-3.0-or-later
"""F-Curve evaluation identical to Blender's, vectorized over frames (pure numpy — ADR 0008).

Ported from Blender 5.2 ``source/blender/blenkernel/intern/fcurve.cc`` (GPL-2.0-or-later):
``fcurve_eval_keyframes`` / ``_extrapolate`` / ``_interpolate``, ``BKE_fcurve_bezt_binarysearch_index_ex``
(0.0001-frame "exact key" threshold), ``BKE_fcurve_correct_bezpart`` (each handle is scaled back
independently when it reaches past the neighbouring key), ``findzero`` / ``solve_cubic`` (first root in
[0, 1] in Blender's order — this matters for looping handles) and ``berekeny``. Blender stores keys as
float32 and mixes float/double arithmetic; the same precision is reproduced here so ``evaluate`` matches
``FCurve.evaluate`` to float32 round-off (parity test in ``tests/blender``).

Key fact used by the sculpt operations (docs/design/motion-sculpt-model.md): with the handle *x*
fixed, ``t(frame)`` is fixed and the value is linear in the key/handle *y* values.
"""

from __future__ import annotations

import numpy as np

from .fcurve_model import ChannelModel

EXACT_KEY_THRESHOLD = 0.0001    # threshold passed to BKE_fcurve_bezt_binarysearch_index_ex
ON_KEY_EPS = np.float32(1e-8)
FLT_EPSILON = np.float32(1.1920929e-07)
SMALL = np.float32(-1.0e-10)
ONE_PLUS = np.float32(1.000001)

f32 = np.float32


def correct_bezpart(v1, v2, v3, v4):
    """``BKE_fcurve_correct_bezpart`` on (..., 2) float arrays: key0, its right handle, left handle of
    key1, key1. Returns corrected (v2, v3) and the per-handle scale factors (1 = untouched)."""
    v1, v2, v3, v4 = (np.asarray(a, dtype=np.float32) for a in (v1, v2, v3, v4))
    h1 = v1 - v2
    h2 = v4 - v3
    length = v4[..., 0] - v1[..., 0]
    len1 = np.abs(h1[..., 0])
    len2 = np.abs(h2[..., 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        fac1 = np.where(len1 > length, length / len1, f32(1.0)).astype(np.float32)
        fac2 = np.where(len2 > length, length / len2, f32(1.0)).astype(np.float32)
    none = (len1 + len2) == 0.0
    fac1 = np.where(none, f32(1.0), fac1)
    fac2 = np.where(none, f32(1.0), fac2)
    v2c = np.where((len1 > length)[..., None] & ~none[..., None], v1 - fac1[..., None] * h1, v2)
    v3c = np.where((len2 > length)[..., None] & ~none[..., None], v4 - fac2[..., None] * h2, v3)
    return v2c.astype(np.float32), v3c.astype(np.float32), fac1, fac2


def _sqrt3d(d):
    out = np.zeros_like(d)
    pos = d > 0.0
    neg = d < 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        out[pos] = np.exp(np.log(d[pos]) / 3.0)
        out[neg] = -np.exp(np.log(-d[neg]) / 3.0)
    return out


def _in_range(r):
    return (r >= SMALL) & (r <= ONE_PLUS)


def solve_cubic(c0, c1, c2, c3):
    """First root in [0, 1] of c0 + c1·t + c2·t² + c3·t³ in Blender's order (``solve_cubic``).

    Arrays of doubles in, (root float32, found bool) out."""
    c0, c1, c2, c3 = np.broadcast_arrays(*(np.asarray(c, dtype=np.float64) for c in (c0, c1, c2, c3)))
    n = c0.shape
    root = np.zeros(n, dtype=np.float32)
    found = np.zeros(n, dtype=bool)

    def take(mask, candidate):
        nonlocal root, found
        cand = np.asarray(candidate, dtype=np.float32)
        ok = mask & ~found & _in_range(cand)
        root = np.where(ok, cand, root)
        found = found | ok

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        cubic = c3 != 0.0
        a = np.where(cubic, c2 / c3, 0.0) / 3.0
        b = np.where(cubic, c1 / c3, 0.0)
        c = np.where(cubic, c0 / c3, 0.0)
        p = b / 3.0 - a * a
        q = (2.0 * a * a * a - a * b + c) / 2.0
        d = q * q + p * p * p
        one = cubic & (d > 0.0)
        t = np.sqrt(np.where(one, d, 0.0))
        take(one, _sqrt3d(-q + t) + _sqrt3d(-q - t) - a)
        two = cubic & (d == 0.0)
        t = _sqrt3d(-q)
        take(two, 2.0 * t - a)
        take(two, -t - a)
        three = cubic & (d < 0.0)
        pp = np.where(three, p, -1.0)
        phi = np.arccos(np.clip(-q / np.sqrt(-(pp * pp * pp)), -1.0, 1.0))
        t = np.sqrt(-pp)
        pc = np.cos(phi / 3.0)
        qq = np.sqrt(np.maximum(3.0 - 3.0 * pc * pc, 0.0))
        take(three, 2.0 * t * pc - a)
        take(three, -t * (pc + qq) - a)
        take(three, -t * (pc - qq) - a)

        quad = ~cubic & (c2 != 0.0)
        disc = c1 * c1 - 4.0 * c2 * c0
        sq = np.sqrt(np.where(quad & (disc > 0.0), disc, 0.0))
        take(quad & (disc > 0.0), (-c1 - sq) / (2.0 * c2))
        take(quad & (disc > 0.0), (-c1 + sq) / (2.0 * c2))
        take(quad & (disc == 0.0), -c1 / (2.0 * c2))

        lin = ~cubic & (c2 == 0.0) & (c1 != 0.0)
        take(lin, -c0 / c1)
        const = ~cubic & (c2 == 0.0) & (c1 == 0.0) & (c0 == 0.0)
        root = np.where(const & ~found, f32(0.0), root)
        found = found | const
    return root, found


def findzero(x, q0, q1, q2, q3):
    """t with x(t) = x for the Bézier x-coordinates q0..q3 (float32 inputs, like ``findzero``)."""
    x, q0, q1, q2, q3 = (np.asarray(v, dtype=np.float32) for v in (x, q0, q1, q2, q3))
    c0 = (q0 - x).astype(np.float64)
    c1 = (f32(3.0) * (q1 - q0)).astype(np.float64)
    c2 = (f32(3.0) * (q0 - f32(2.0) * q1 + q2)).astype(np.float64)
    c3 = (q3 - q0 + f32(3.0) * (q1 - q2)).astype(np.float64)
    return solve_cubic(c0, c1, c2, c3)


def berekeny(f1, f2, f3, f4, t):
    """Bézier y(t) in float32 (``berekeny``)."""
    f1, f2, f3, f4, t = (np.asarray(v, dtype=np.float32) for v in (f1, f2, f3, f4, t))
    c0 = f1
    c1 = f32(3.0) * (f2 - f1)
    c2 = f32(3.0) * (f1 - f32(2.0) * f2 + f3)
    c3 = f4 - f1 + f32(3.0) * (f2 - f3)
    return c0 + t * c1 + t * t * c2 + t * t * t * c3


def bernstein(t):
    """(4, N) cubic Bernstein weights (float64): value = b0·y0 + b1·y_h1 + b2·y_h2 + b3·y1."""
    t = np.asarray(t, dtype=np.float64)
    mt = 1.0 - t
    return np.stack([mt ** 3, 3.0 * mt * mt * t, 3.0 * mt * t * t, t ** 3])


def segment_t(model: ChannelModel, k: int, frames):
    """(t, found) of each frame inside the Bézier segment k → k+1, as Blender computes it."""
    co = model.co.astype(np.float32)
    v2, v3, _f1, _f2 = correct_bezpart(co[k], model.hr[k], model.hl[k + 1], co[k + 1])
    frames = np.asarray(frames, dtype=np.float32)
    return findzero(frames, co[k, 0], v2[0], v3[0], co[k + 1, 0])


def _extrapolate(model: ChannelModel, frames, end: bool):
    """``fcurve_eval_keyframes_extrapolate`` for the first (end=False) or the last key."""
    k = model.key_count
    i = k - 1 if end else 0
    neighbor = i - 1 if end else i + 1
    co = model.co.astype(np.float32)
    x, y = co[i]
    if model.interp[i] == "CONSTANT" or model.extrapolation == "CONSTANT":
        return np.full(frames.shape, y, dtype=np.float32)
    dx = x - frames
    if model.interp[i] == "LINEAR":
        if k == 1:
            return np.full(frames.shape, y, dtype=np.float32)
        fac = co[neighbor, 0] - x
        if fac == 0.0:
            return np.full(frames.shape, y, dtype=np.float32)
        fac = (co[neighbor, 1] - y) / fac
        return y - fac * dx
    handle = (model.hr[i] if end else model.hl[i]).astype(np.float32)
    fac = x - handle[0]
    if fac == 0.0:
        return np.full(frames.shape, y, dtype=np.float32)
    fac = (y - handle[1]) / fac
    return y - fac * dx


def _eqt(a, b, threshold):
    return np.where(a > b, a - b <= threshold, b - a <= threshold)


def evaluate(model: ChannelModel, frames) -> np.ndarray:
    """Values of the channel at ``frames`` like ``FCurve.evaluate`` (keyframes only, no modifiers).

    Returns float64 (holding float32-rounded values, like Blender)."""
    frames = np.atleast_1d(np.asarray(frames, dtype=np.float64)).astype(np.float32)
    out = np.zeros(frames.shape, dtype=np.float32)
    k = model.key_count
    if k == 0:
        return out.astype(np.float64)
    co = model.co.astype(np.float32)
    xs = co[:, 0]
    before = frames <= xs[0]
    after = (xs[-1] <= frames) & ~before
    if before.any():
        out[before] = _extrapolate(model, frames[before], end=False)
    if after.any():
        out[after] = _extrapolate(model, frames[after], end=True)
    inside = ~(before | after)
    if inside.any():
        out[inside] = _interpolate(model, co, frames[inside])
    return out.astype(np.float64)


def _interpolate(model, co, f):
    xs = co[:, 0]
    k = len(xs)
    # binary search with threshold: a key within 0.0001 frames is "exact"
    a = np.searchsorted(xs, f, side="right")          # first key strictly after f
    a = np.clip(a, 1, k - 1)
    exact_prev = _eqt(f, xs[a - 1], f32(EXACT_KEY_THRESHOLD))
    exact_next = _eqt(f, xs[a], f32(EXACT_KEY_THRESHOLD))
    vals = np.zeros(f.shape, dtype=np.float32)
    for s in np.unique(a - 1):
        m = (a - 1) == s
        fs = f[m]
        x0, y0 = co[s]
        x1, y1 = co[s + 1]
        duration = x1 - x0
        ipo = model.interp[s]
        if ipo == "CONSTANT" or duration == 0.0:
            v = np.full(fs.shape, y0, dtype=np.float32)
        elif ipo == "LINEAR":
            v = (y1 - y0) * (fs - x0) / duration + y0
        elif ipo == "BEZIER":
            v2 = model.hr[s].astype(np.float32)
            v3 = model.hl[s + 1].astype(np.float32)
            if abs(y0 - y1) < FLT_EPSILON and abs(v2[1] - v3[1]) < FLT_EPSILON and abs(v3[1] - y1) < FLT_EPSILON:
                v = np.full(fs.shape, y0, dtype=np.float32)
            else:
                v2c, v3c, _f1, _f2 = correct_bezpart(co[s], v2, v3, co[s + 1])
                t, found = findzero(fs, x0, v2c[0], v3c[0], x1)
                v = np.where(found, berekeny(y0, v2c[1], v3c[1], y1, t), f32(0.0))
        else:  # easing presets are not modelled: never edited by the sculpt tool
            v = np.full(fs.shape, y0, dtype=np.float32)
        vals[m] = v
    on_next = np.abs(xs[a] - f) < ON_KEY_EPS
    vals = np.where(exact_next | on_next, co[a, 1], vals)
    vals = np.where(exact_prev, co[a - 1, 1], vals)
    return vals

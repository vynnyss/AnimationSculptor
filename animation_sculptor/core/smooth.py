# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure math of the Smooth brush: temporal smoothing of animation channels.

Samples are taken at consecutive integer frames. One pass blends each sample
toward its Gaussian-filtered value, scaled by the time-window falloff weight
and the brush strength: ``v' = v + w * s * (G*v - v)``. The Gaussian uses the
"nearest" edge mode (the first/last sample is repeated beyond the ends).
"""

from __future__ import annotations

import math

import numpy as np


def gaussian_kernel(sigma: float) -> np.ndarray:
    """Normalized discrete Gaussian; radius ceil(3*sigma), odd length. sigma <= 0 gives [1.0]."""
    if not sigma > 0.0:
        return np.array([1.0])
    radius = max(1, int(math.ceil(3.0 * float(sigma))))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / float(sigma)) ** 2)
    return k / k.sum()


def _convolve_nearest(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Gaussian convolution along axis 0 with edge mode 'nearest'. values is (N, C)."""
    r = (len(kernel) - 1) // 2
    padded = np.concatenate(
        [np.repeat(values[:1], r, axis=0), values, np.repeat(values[-1:], r, axis=0)], axis=0
    )
    n = values.shape[0]
    out = np.zeros_like(values)
    for j, kj in enumerate(kernel):
        out += kj * padded[j : j + n]
    return out


def smooth_pass(values, weights, strength, sigma=1.0) -> np.ndarray:
    """One smoothing pass. values (N,) or (N, C); weights (N,) in [0, 1]; strength in [0, 1].

    Rows with weight 0 (or strength 0) are returned bit-identical.
    """
    v = np.array(values, dtype=np.float64)
    squeeze = v.ndim == 1
    v2 = v.reshape(-1, 1) if squeeze else v
    w = np.clip(np.asarray(weights, dtype=np.float64).reshape(-1), 0.0, 1.0)
    s = float(min(max(strength, 0.0), 1.0))
    if v2.shape[0] == 0 or s == 0.0:
        return v
    factor = (w * s)[:, None]
    smoothed = _convolve_nearest(v2, gaussian_kernel(sigma))
    out = np.where(factor == 0.0, v2, v2 + factor * (smoothed - v2))
    return out.reshape(-1) if squeeze else out


def smooth_quaternions(q, weights, strength, sigma=1.0) -> np.ndarray:
    """Smooth (N, 4) unit quaternions (w, x, y, z), hemisphere-continuously.

    Weight-0 rows return the input row bit-identical; every other row is in the
    input's hemisphere (dot with the input >= 0) and has unit norm.
    """
    src = np.array(q, dtype=np.float64)
    if src.shape[0] == 0:
        return src
    cont = src.copy()
    for i in range(1, cont.shape[0]):
        if float(np.dot(cont[i], cont[i - 1])) < 0.0:
            cont[i] = -cont[i]
    out = smooth_pass(cont, weights, strength, sigma)
    norm = np.linalg.norm(out, axis=1, keepdims=True)
    norm = np.where(norm > 0.0, norm, 1.0)
    out = out / norm
    flip = np.einsum("ij,ij->i", out, src) < 0.0
    out[flip] = -out[flip]
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    untouched = (w <= 0.0) | (float(strength) <= 0.0)
    out[untouched] = src[untouched]
    return out


def passes_for_drag(distance_px: float, px_per_pass: float = 8.0) -> int:
    """Number of passes a stroke of the given length applies (floor, >= 0)."""
    if px_per_pass <= 0.0 or not distance_px > 0.0:
        return 0
    return max(0, int(math.floor(distance_px / px_per_pass)))


def smooth(values, weights, strength, passes, sigma=1.0) -> np.ndarray:
    """Apply smooth_pass `passes` times (0 gives a copy)."""
    out = np.array(values, dtype=np.float64)
    for _ in range(max(0, int(passes))):
        out = smooth_pass(out, weights, strength, sigma)
    return out

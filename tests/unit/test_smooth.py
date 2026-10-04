# SPDX-License-Identifier: GPL-3.0-or-later
"""core.smooth: temporal Smooth brush math (sculpt-ux.md, section Smooth)."""

import numpy as np
import pytest

from animation_sculptor.core.smooth import (
    gaussian_kernel,
    passes_for_drag,
    smooth,
    smooth_pass,
    smooth_quaternions,
)


def _noise(n=60, c=None, seed=3):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n,) if c is None else (n, c))


def _d2var(x):
    return float(np.var(np.diff(x, n=2, axis=0)))


@pytest.mark.parametrize("sigma", [0.5, 1.0, 2.3, 4.0])
def test_kernel_normalized_symmetric_length(sigma):
    k = gaussian_kernel(sigma)
    assert k.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.allclose(k, k[::-1])
    assert len(k) == 2 * int(np.ceil(3 * sigma)) + 1


@pytest.mark.parametrize("sigma", [0.0, -1.0])
def test_kernel_degenerate(sigma):
    assert np.array_equal(gaussian_kernel(sigma), [1.0])


def test_constant_unchanged():
    v = np.full(30, 2.5)
    out = smooth(v, np.ones(30), 1.0, 5, sigma=2.0)
    assert np.allclose(out, v, atol=1e-12)


def test_linear_ramp_unchanged_in_interior():
    sigma = 1.5
    r = int(np.ceil(3 * sigma))
    v = 0.7 * np.arange(40) - 3.0
    out = smooth_pass(v, np.ones(40), 1.0, sigma)
    assert np.allclose(out[r:-r], v[r:-r], atol=1e-12)


def test_zero_strength_and_zero_weight_bit_identical():
    v = _noise(30, 3)
    assert np.array_equal(smooth_pass(v, np.ones(30), 0.0), v)
    w = np.ones(30)
    w[10:20] = 0.0
    out = smooth_pass(v, w, 1.0, 1.5)
    assert np.array_equal(out[10:20], v[10:20])
    assert not np.array_equal(out[:10], v[:10])


def test_noise_reduced_and_more_passes_more_reduction():
    v = _noise(80)
    w = np.ones(80)
    a = smooth(v, w, 1.0, 1)
    b = smooth(v, w, 1.0, 4)
    assert _d2var(a) < _d2var(v)
    assert _d2var(b) < _d2var(a)


def test_weights_scale_effect_per_frame():
    v = _noise(40)
    full = smooth_pass(v, np.ones(40), 1.0) - v
    w = np.linspace(0.0, 1.0, 40)
    part = smooth_pass(v, w, 1.0) - v
    assert np.allclose(part, w * full, atol=1e-12)
    half = smooth_pass(v, np.full(40, 0.5), 1.0) - v
    assert np.allclose(half, 0.5 * full, atol=1e-12)


def test_strength_scales_effect():
    v = _noise(40)
    full = smooth_pass(v, np.ones(40), 1.0) - v
    part = smooth_pass(v, np.ones(40), 0.25) - v
    assert np.allclose(part, 0.25 * full, atol=1e-12)


def test_deterministic():
    v = _noise(50, 2)
    w = np.linspace(0.2, 1.0, 50)
    assert np.array_equal(smooth(v, w, 0.8, 3), smooth(v, w, 0.8, 3))


def test_multichannel_equals_per_channel():
    v = _noise(50, 4)
    w = np.linspace(0.3, 1.0, 50)
    both = smooth(v, w, 0.9, 2, sigma=1.7)
    for c in range(4):
        assert np.allclose(both[:, c], smooth(v[:, c], w, 0.9, 2, sigma=1.7), atol=1e-12)


def test_zero_passes_is_copy():
    v = _noise(10)
    out = smooth(v, np.ones(10), 1.0, 0)
    assert np.array_equal(out, v) and out is not v


def _quats(n=40, seed=5):
    rng = np.random.default_rng(seed)
    ang = np.cumsum(rng.normal(scale=0.05, size=n))
    return np.stack([np.cos(ang / 2), np.sin(ang / 2), np.zeros(n), np.zeros(n)], axis=1)


def test_quaternions_unit_and_same_hemisphere():
    q = _quats()
    out = smooth_quaternions(q, np.ones(len(q)), 1.0, 1.5)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-12)
    assert np.all(np.einsum("ij,ij->i", out, q) >= 0.0)


def test_quaternions_sign_flipped_rows_handled():
    q = _quats()
    w = np.ones(len(q))
    ref = smooth_quaternions(q, w, 1.0)
    flipped = q.copy()
    flipped[15:] *= -1.0
    out = smooth_quaternions(flipped, w, 1.0)
    # same rotations as the continuous sequence (up to sign), in the flipped input's hemisphere
    assert np.allclose(np.abs(np.einsum("ij,ij->i", out, ref)), 1.0, atol=1e-12)
    assert np.all(np.einsum("ij,ij->i", out, flipped) >= 0.0)
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-12)


def test_quaternions_zero_weight_rows_bit_identical():
    q = _quats()
    q[20:30] *= -1.0
    w = np.ones(len(q))
    w[18:32] = 0.0
    out = smooth_quaternions(q, w, 1.0)
    assert np.array_equal(out[18:32], q[18:32])


def test_passes_for_drag():
    assert passes_for_drag(0.0) == 0
    assert passes_for_drag(-5.0) == 0
    assert passes_for_drag(7.9) == 0
    assert passes_for_drag(8.0) == 1
    assert passes_for_drag(25.0) == 3
    assert passes_for_drag(25.0, px_per_pass=5.0) == 5

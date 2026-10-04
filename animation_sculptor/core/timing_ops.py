# SPDX-License-Identifier: GPL-3.0-or-later
"""Timing operations on a set of channels (pure numpy — ADR 0008).

Math: docs/design/motion-sculpt-model.md, operations 3 (retime of a pose key) and 4 (spacing of a
segment). Both only change *x* (time) of keys/handles, so they are safe for any channel, rotations
included. Retime moves the keys at a frame in every channel of the timing scope together, keeping the
order of keys; spacing changes only the x of the inner handles of a segment, equally in every channel,
which keeps the spatial path: the path of a Bézier segment depends only on the y control values.
"""

from __future__ import annotations

import numpy as np

from .fcurve_model import ChannelModel

POSE_KEY_EPS = 1e-3
MIN_LAMBDA = 0.02        # shortest handle, as a fraction of the segment duration
MAX_LAMBDA_SUM = 0.98    # λ_out + λ_in ≤ 1 keeps Blender's handle correction inactive (path exactly kept)

PRESERVE_PATH = "PRESERVE_PATH"
PRESERVE_SMOOTHNESS = "PRESERVE_SMOOTHNESS"


def pose_keys(models) -> np.ndarray:
    """Sorted unique key frames over all channels (the *pose keys* of the timing scope)."""
    frames = [m.co[:, 0] for m in models if m.key_count]
    if not frames:
        return np.empty(0)
    allf = np.sort(np.concatenate(frames))
    keep = np.r_[True, np.diff(allf) > POSE_KEY_EPS]
    return allf[keep]


def retime_limits(models, frame):
    """(low, high) open interval allowed for the pose key at ``frame`` (between its neighbour pose keys)."""
    keys = pose_keys(models)
    before = keys[keys < frame - POSE_KEY_EPS]
    after = keys[keys > frame + POSE_KEY_EPS]
    low = before[-1] if len(before) else -np.inf
    high = after[0] if len(after) else np.inf
    return low, high


def retime(models, frame, new_frame, min_gap=1.0):
    """Move the pose key at ``frame`` to ``new_frame`` in every channel (keys and their handles shift
    together). ``new_frame`` is clamped to stay ``min_gap`` frames from the neighbour pose keys.

    Returns (new_models, applied_frame). Channels without a key at ``frame`` are returned unchanged;
    no key is created or removed and the key order never changes (invariant 4).
    """
    low, high = retime_limits(models, frame)
    target = float(np.clip(new_frame, low + min_gap, high - min_gap)) if high - low > 2 * min_gap else float(frame)
    delta = target - frame
    out = []
    for m in models:
        idx = m.key_index(frame, eps=POSE_KEY_EPS)
        if idx is None or delta == 0.0:
            out.append(m if delta == 0.0 else m.copy())
            continue
        c = m.copy()
        c.co[idx, 0] += delta
        c.hl[idx, 0] += delta
        c.hr[idx, 0] += delta
        out.append(c)
    return out, target


def segment_lambdas(model: ChannelModel, k: int):
    """(λ_out, λ_in) of segment k: handle lengths in time as fractions of its duration."""
    x0, x1 = model.co[k, 0], model.co[k + 1, 0]
    d = x1 - x0
    return (model.hr[k, 0] - x0) / d, (x1 - model.hl[k + 1, 0]) / d


def clamp_lambdas(lam_out, lam_in):
    lam_out = max(MIN_LAMBDA, float(lam_out))
    lam_in = max(MIN_LAMBDA, float(lam_in))
    total = lam_out + lam_in
    if total > MAX_LAMBDA_SUM:
        scale = MAX_LAMBDA_SUM / total
        lam_out, lam_in = lam_out * scale, lam_in * scale
        # keep the floor after scaling: the short side stays at MIN_LAMBDA, the other gets the rest
        if lam_out < MIN_LAMBDA:
            lam_out, lam_in = MIN_LAMBDA, MAX_LAMBDA_SUM - MIN_LAMBDA
        elif lam_in < MIN_LAMBDA:
            lam_out, lam_in = MAX_LAMBDA_SUM - MIN_LAMBDA, MIN_LAMBDA
    return lam_out, lam_in


def _align(model: ChannelModel, key: int, edited: str) -> None:
    """Make the opposite handle of ``key`` collinear with the edited one, keeping its x."""
    kx, ky = model.co[key]
    h_edit = model.hr[key] if edited == "R" else model.hl[key]
    h_opp = model.hl[key] if edited == "R" else model.hr[key]
    dx = h_edit[0] - kx
    if abs(dx) > 1e-12:
        h_opp[1] = ky + (h_edit[1] - ky) / dx * (h_opp[0] - kx)


def set_spacing(model: ChannelModel, k0: float, k1: float, lam_out: float, lam_in: float,
                policy: str = PRESERVE_PATH):
    """Spacing of the segment between the keys at ``k0`` and ``k1`` of one channel.

    Only the x of the two inner handles changes (their y stays), so the segment's path is unchanged.
    PRESERVE_PATH: the edited keys become FREE on both sides (no other value changes; the tangent may
    break at the key). PRESERVE_SMOOTHNESS: both sides ALIGNED, the opposite handle's y is re-aligned
    (keeping its x) — the neighbouring segment's path changes slightly.

    Returns (new_model, reason); reason is '' when applied.
    """
    i0 = model.key_index(k0, eps=POSE_KEY_EPS)
    i1 = model.key_index(k1, eps=POSE_KEY_EPS)
    if i0 is None or i1 is None or i1 != i0 + 1:
        return model, "canal sem esse segmento"
    if model.interp[i0] != "BEZIER":
        return model, f"segmento {model.interp[i0]}"
    lam_out, lam_in = clamp_lambdas(lam_out, lam_in)
    out = model.copy()
    x0, x1 = out.co[i0, 0], out.co[i1, 0]
    d = x1 - x0
    out.hr[i0, 0] = x0 + lam_out * d
    out.hl[i1, 0] = x1 - lam_in * d
    for key, side in ((i0, "R"), (i1, "L")):
        if policy == PRESERVE_SMOOTHNESS:
            out.hl_type[key] = out.hr_type[key] = "ALIGNED"
            _align(out, key, side)
        else:
            out.hl_type[key] = out.hr_type[key] = "FREE"
    return out, ""


def spacing_from_gesture(lam_out, lam_in, favor, ease):
    """Gesture → λ: ``favor`` moves time from one end to the other (positive = toward the second key,
    i.e. longer ease-out), ``ease`` lengthens (positive) or shortens both handles."""
    return clamp_lambdas(lam_out + favor + ease, lam_in - favor + ease)


def retime_frames_from_screen(mouse_delta, trail_screen_dir, pixels_per_frame, fallback_px_per_frame=20.0):
    """Mouse delta (px) → frames: projection on the trail's screen direction at the key, divided by the
    trail's pixels per frame there (Motion Trail's timing mode). Stationary trails use horizontal motion."""
    d = np.asarray(mouse_delta, dtype=np.float64)
    direction = np.asarray(trail_screen_dir, dtype=np.float64)
    n = np.linalg.norm(direction)
    if n < 1e-6 or pixels_per_frame < 1.0:
        return float(d[0] / fallback_px_per_frame)
    return float(d @ (direction / n) / pixels_per_frame)


def remap_frames(old: ChannelModel, new: ChannelModel, k: int, frames):
    """For frames inside segment k of ``new``: the frame of ``old`` with the same Bézier parameter t.
    Since the path depends only on t, ``old_trail(remap(f))`` is where the control is at ``f`` after a
    spacing edit (exact when all channels share the handle x; preview approximation otherwise)."""
    from . import bezier

    frames = np.asarray(frames, dtype=np.float64)
    t, found = bezier.segment_t(new, k, frames)
    v2, v3, _f1, _f2 = bezier.correct_bezpart(old.co[k], old.hr[k], old.hl[k + 1], old.co[k + 1])
    t = t.astype(np.float64)
    mt = 1.0 - t
    x = (mt ** 3 * old.co[k, 0] + 3 * mt * mt * t * float(v2[0]) + 3 * mt * t * t * float(v3[0])
         + t ** 3 * old.co[k + 1, 0])
    return np.where(found, x, frames)

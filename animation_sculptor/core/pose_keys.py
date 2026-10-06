# SPDX-License-Identifier: GPL-3.0-or-later
"""Pose-to-pose key writing (pure numpy — ADR 0015): the sparse alternative to ``core.dense``.

A gesture changes the channel only at a few frames — the frame being posed and, with a reduced weight, the
character's neighbouring pose keys. At each of them the channel gets the new value:

- an existing key moves rigidly (key and both handles by the same Δy; its frame and handle ``x`` never
  change, so the timing is intact);
- a missing key is inserted (``BEZIER``, ``AUTO_CLAMPED``, like Blender's own keyframe insertion; the
  handles here are an approximation that Blender recomputes on ``fcurve.update()``).

A channel that had no key at all was constant: the first key would change every frame, so it is anchored
first at the character's other pose frames with its old (constant) value — the other poses stay put.
"""

from __future__ import annotations

import numpy as np

from .fcurve_model import ChannelModel

FRAME_EPS = 1e-3


def _insert(out: ChannelModel, frame: float, value: float) -> None:
    x = out.co[:, 0]
    j = int(np.searchsorted(x, frame))
    left = x[j - 1] if j > 0 else frame - 3.0
    right = x[j] if j < len(x) else frame + 3.0
    dl, dr = (frame - left) / 3.0, (right - frame) / 3.0
    out.co = np.insert(out.co, j, (frame, value), axis=0)
    out.hl = np.insert(out.hl, j, (frame - dl, value), axis=0)
    out.hr = np.insert(out.hr, j, (frame + dr, value), axis=0)
    out.hl_type.insert(j, "AUTO_CLAMPED")
    out.hr_type.insert(j, "AUTO_CLAMPED")
    out.interp.insert(j, "BEZIER")


def write_keys(model: ChannelModel, frames, values, default: float = 0.0, anchors=()) -> ChannelModel:
    """New model with ``values`` at ``frames`` (moved or inserted keys); every other key bit-identical.
    ``default``: the channel's value when it has no key; ``anchors``: frames that get a key with that
    value first when the channel had none (the character's other poses)."""
    out = model.copy()
    frames = [float(f) for f in np.asarray(frames, dtype=np.float64).reshape(-1)]
    values = [float(v) for v in np.asarray(values, dtype=np.float64).reshape(-1)]
    if model.key_count == 0:
        posed = set(round(f) for f in frames)
        for a in sorted(set(float(a) for a in anchors)):
            if round(a) not in posed:
                _insert(out, a, float(default))
    for f, v in zip(frames, values):
        i = out.key_index(f, FRAME_EPS)
        if i is None:
            _insert(out, f, v)
            continue
        dy = v - out.co[i, 1]
        out.co[i, 1] = v
        out.hl[i, 1] += dy
        out.hr[i, 1] += dy
    return out

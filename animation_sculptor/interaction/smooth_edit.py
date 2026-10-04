# SPDX-License-Identifier: GPL-3.0-or-later
"""The Smooth brush (docs/design/sculpt-ux.md "Smooth"): temporal smoothing of a body part's channels.

While the button is held over a part (modo Corpo) or a trail (modo Trail), every ``core.smooth``
``passes_for_drag`` of mouse travel applies one Gaussian pass to the animated channels of the part's
controls, inside the time ruler's window (falloff weights, strength). Channels are sampled at the integer
frames and written as dense keys (``core.dense``); nothing outside the window changes. One stroke = one
undo step; Esc restores bit for bit.
"""

import math

import bpy
import numpy as np

from ..anim import action_io, spaces
from ..anim.snapshot import Snapshot
from ..core import bezier, dense, falloff, smooth

PAD = 1
MAX_PASSES = 64         # a long stroke stops smoothing further (the cost of a pass stays bounded)
SMOOTHED = ("location", "rotation_quaternion", "rotation_euler", "scale")


class SmoothEdit:
    kind = "SMOOTH"

    def __init__(self, ob, bones, frame, radius_past=0.0, radius_future=0.0, shape="SMOOTH",
                 strength=0.5, sigma=1.5):
        self.ob = ob
        self.bones = list(bones)
        self.bone = self.bones[-1]
        self.frame = int(frame)
        self.strength = float(strength)
        self.sigma = float(sigma)
        self.radius_past, self.radius_future = float(radius_past), float(radius_future)
        self.shape = shape
        self.passes = 0
        self.trail_frames = np.empty(0)
        lo = self.frame - int(math.floor(self.radius_past)) - PAD
        hi = self.frame + int(math.floor(self.radius_future)) + PAD
        self.frames = np.arange(lo, hi + 1)
        self.weights = falloff.weight_signed(self.frames.astype(np.float64) - self.frame, self.radius_past,
                                             self.radius_future, shape)
        self.snapshot = Snapshot(ob)
        self.groups = []    # (bone, channel, [(axis, fcurve, model, current, values)])
        cb = action_io.channelbag(ob)
        rot_channel = {name: spaces.rotation_channel(ob.pose.bones[name])[0] for name in self.bones}
        for name in self.bones:
            pb = ob.pose.bones[name]
            for channel in SMOOTHED:
                if channel.startswith("rotation") and channel != rot_channel[name]:
                    continue
                path = pb.path_from_id(channel)
                size = 4 if channel == "rotation_quaternion" else 3
                axes = []
                for axis in range(size):
                    fc = cb.fcurves.find(path, index=axis) if cb is not None else None
                    if fc is None or len(fc.keyframe_points) == 0 or action_io.refusal(ob, pb, channel):
                        continue
                    model = action_io.read_channel(fc)
                    self.snapshot.capture(path, axis)
                    values = bezier.evaluate(model, self.frames.astype(np.float64))
                    axes.append((axis, fc, model, dense.current_values(model, int(self.frames[0]), len(self.frames)),
                                 values))
                if channel == "rotation_quaternion" and 0 < len(axes) < 4:
                    axes = []           # a partial quaternion cannot be smoothed as a rotation
                if axes:
                    self.groups.append((name, channel, axes))

    @property
    def editable(self):
        return bool(self.groups)

    @property
    def reason(self):
        return "" if self.groups else "parte sem animação para suavizar"

    def apply_passes(self, passes):
        """Write the channels smoothed ``passes`` times from the original curves (0 = original values).
        Incremental: only the passes beyond the last call are computed (capped at MAX_PASSES)."""
        passes = max(0, min(int(passes), MAX_PASSES))
        if passes < self.passes or not hasattr(self, "_smoothed"):
            self._smoothed = [np.stack([a[4] for a in axes], axis=1) for _n, _c, axes in self.groups]
            done = 0
        else:
            done = self.passes
        self.passes = passes
        start = int(self.frames[0])
        for g, (_name, channel, axes) in enumerate(self.groups):
            out = self._smoothed[g]
            for _ in range(passes - done):
                if channel == "rotation_quaternion":
                    out = smooth.smooth_quaternions(out, self.weights, self.strength, self.sigma)
                else:
                    out = smooth.smooth_pass(out, self.weights, self.strength, self.sigma)
            self._smoothed[g] = out
            for k, (_axis, fc, model, current, _values) in enumerate(axes):
                action_io.write_channel(fc, dense.write_dense(model, start, out[:, k], current=current))
        action_io.tag(self.ob)

    def apply(self, _delta=None):
        self.apply_passes(self.passes)

    def prefetch(self, frames):
        pass

    def preview(self):
        return []

    def restore(self):
        self.snapshot.restore()

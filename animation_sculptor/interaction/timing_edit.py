# SPDX-License-Identifier: GPL-3.0-or-later
"""Timing gestures (Ctrl+LMB): retime of a pose key and spacing of a segment (core.timing_ops).

They act on every F-Curve of the *timing scope* — the whole character (default) or the selected
bones — because moving a pose in time must move the whole pose. Only time (x) changes, so they work
for any control, FK included. Snapshot/restore and undo behave like the spatial gestures.
"""

from __future__ import annotations

import numpy as np

from ..anim import action_io
from ..anim.snapshot import Snapshot
from ..core import timing_ops

SCOPES = ("CHARACTER", "SELECTED")


def scope_fcurves(ob, bone, scope):
    """F-Curves edited by a timing gesture started on ``bone``."""
    cb = action_io.channelbag(ob)
    if cb is None:
        return []
    fcurves = [fc for fc in cb.fcurves if not any(m.active and not m.mute for m in fc.modifiers)]
    if scope == "CHARACTER":
        return fcurves
    names = {pb.name for pb in ob.pose.bones if pb.select} | {bone}
    prefixes = tuple(ob.pose.bones[n].path_from_id() for n in names if n in ob.pose.bones)
    return [fc for fc in fcurves if fc.data_path.startswith(prefixes)]


class _TimingBase:
    def __init__(self, ob, pb, frame, scope):
        self.ob = ob
        self.pb = pb
        self.frame = frame
        self.scope = scope
        self.fcurves = scope_fcurves(ob, pb.name, scope)
        self.snapshot = Snapshot(ob)
        self.base = []
        for fc in self.fcurves:
            self.snapshot.capture_fcurve(fc)
            self.base.append(action_io.read_channel(fc))

    def restore(self):
        self.snapshot.restore()


class RetimeEdit(_TimingBase):
    """Move the pose key at ``frame`` (every channel of the scope keyed there) to another frame."""

    kind = "RETIME"

    def __init__(self, ob, pb, frame, scope="CHARACTER"):
        super().__init__(ob, pb, frame, scope)
        self.keyed = [i for i, m in enumerate(self.base) if m.key_index(frame, eps=timing_ops.POSE_KEY_EPS) is not None]
        self.low, self.high = timing_ops.retime_limits(self.base, frame)
        self.target = float(frame)

    @property
    def editable(self):
        return bool(self.keyed)

    def apply(self, new_frame):
        models, self.target = timing_ops.retime([self.base[i] for i in self.keyed], self.frame, new_frame)
        for i, model in zip(self.keyed, models):
            action_io.write_channel(self.fcurves[i], model)
        action_io.tag(self.ob)
        return self.target


class SpacingEdit(_TimingBase):
    """Ease/favor of the segment around ``frame`` between two key frames of the control."""

    kind = "SPACING"

    def __init__(self, ob, pb, frame, scope="CHARACTER", policy=timing_ops.PRESERVE_PATH):
        super().__init__(ob, pb, frame, scope)
        self.policy = policy
        own = [m for fc, m in zip(self.fcurves, self.base) if fc.data_path.startswith(pb.path_from_id())]
        keys = timing_ops.pose_keys(own)
        before, after = keys[keys < frame], keys[keys > frame]
        self.k0 = float(before[-1]) if len(before) else None
        self.k1 = float(after[0]) if len(after) else None
        self.channels = []          # indices of channels that own exactly this segment
        self.reason = ""
        if self.k0 is None or self.k1 is None:
            self.reason = "fora do intervalo de keys"
            return
        for i, m in enumerate(self.base):
            _out, reason = timing_ops.set_spacing(m, self.k0, self.k1, 0.33, 0.33, policy)
            if not reason:
                self.channels.append(i)
            elif not self.reason and fc_is_own(self.fcurves[i], pb):
                self.reason = reason
        # reference channel (the control's own first channel in the segment) for λ and the preview
        self.ref = next((i for i in self.channels if fc_is_own(self.fcurves[i], pb)), None)
        if self.ref is None and self.channels:
            self.ref = self.channels[0]
        if self.ref is not None:
            m = self.base[self.ref]
            k = m.key_index(self.k0, eps=timing_ops.POSE_KEY_EPS)
            self.lam = timing_ops.clamp_lambdas(*timing_ops.segment_lambdas(m, k))
            self.k_index = k
        else:
            self.lam = (1 / 3, 1 / 3)
            self.k_index = None
        self.current = self.lam
        if not self.channels and not self.reason:
            self.reason = "nenhum canal com esse segmento"

    @property
    def editable(self):
        return bool(self.channels)

    def apply(self, favor, ease):
        self.current = timing_ops.spacing_from_gesture(self.lam[0], self.lam[1], favor, ease)
        for i in self.channels:
            model, _reason = timing_ops.set_spacing(self.base[i], self.k0, self.k1, *self.current, self.policy)
            action_io.write_channel(self.fcurves[i], model)
        action_io.tag(self.ob)
        return self.current

    def preview(self, trail_frames, trail_points):
        """Predicted trail points inside the segment: the original trail resampled at the remapped frames
        (the path is kept; only where the control is at each frame changes)."""
        if self.ref is None or trail_points is None or len(trail_frames) < 2:
            return None
        new_model = action_io.read_channel(self.fcurves[self.ref])
        frames = np.asarray(trail_frames, dtype=np.float64)
        inside = (frames > self.k0) & (frames < self.k1)
        old_frames = frames.copy()
        old_frames[inside] = timing_ops.remap_frames(self.base[self.ref], new_model, self.k_index, frames[inside])
        pts = np.asarray(trail_points, dtype=np.float64)
        return np.stack([np.interp(old_frames, frames, pts[:, axis]) for axis in range(3)], axis=1)


def fc_is_own(fc, pb):
    return fc.data_path.startswith(pb.path_from_id())


def refusal(ob):
    adt = ob.animation_data
    if adt is None or adt.action is None:
        return "sem Action (keye a primeira pose com I)"
    if adt.use_nla and any(len(t.strips) and not t.mute for t in adt.nla_tracks):
        return "NLA ativa"
    if adt.action_influence < 1.0 or adt.action_blend_type != 'REPLACE':
        return "Action com influência/blend"
    return ""


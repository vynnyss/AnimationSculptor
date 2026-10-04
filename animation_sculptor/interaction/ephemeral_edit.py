# SPDX-License-Identifier: GPL-3.0-or-later
"""The ephemeral-rig gesture on an FK chain (ADR 0011, docs/design/ephemeral-rig.md, phases 3–4).

``ChainEdit`` has the shape of ``_GrabEdit``/``timing_edit``: ``editable``, ``apply(Δw)``, ``preview()``,
``restore()``. Dragging the tail of a control turns the chain (from ``RigAdapter.ephemeral_chain``) so
the tail follows ``tail(f) + w(f)·Δw`` at every integer frame of the time window (the ruler's past /
future radius), written as dense keys (``core.dense``) on the rotation channels; nothing outside the window
changes. In the ``Corpo`` scope the chain is solved by damped least squares and pinned limbs (legs) are
re-solved so their feet stay put. The "rig" is ``core.ephemeral``: nothing is created in the .blend.
"""

import math

import bpy
import numpy as np

from ..anim import action_io, spaces
from ..anim.snapshot import Snapshot
from ..core import dense, ephemeral, falloff
from ..core.fcurve_model import ChannelModel

PAD = 1     # frames of weight 0 written on each side of the window (curves created by the gesture stay flat outside)
BODY = "BODY"


def refusal(ob, bones) -> str:
    """Why these bones cannot be sculpted ('' when they can)."""
    for name in bones:
        pb = ob.pose.bones[name]
        if pb.rotation_mode == 'AXIS_ANGLE':
            return f"{name}: rotação AXIS_ANGLE não suportada (use quaternion ou Euler)"
        if any(c.enabled and c.influence > 0.0 for c in pb.constraints):
            return f"{name}: bone com constraint"
        channel, _size = spaces.rotation_channel(pb)
        reason = action_io.refusal(ob, pb, channel)
        if reason:
            return reason
    return ""


def _empty_model():
    return ChannelModel(np.empty((0, 2)), np.empty((0, 2)), np.empty((0, 2)))


def _attach_index(ob, chain, limb_root, hint):
    """Index in ``chain`` of the bone the pinned limb hangs from: the adapter's hint, else the first chain
    bone found walking up from the limb root."""
    if hint in chain:
        return chain.index(hint)
    parent = ob.pose.bones[limb_root].parent
    while parent is not None:
        if parent.name in chain:
            return chain.index(parent.name)
        parent = parent.parent
    return None


class ChainEdit:
    kind = "CHAIN"

    def __init__(self, ob, bones, frame, radius_past=0.0, radius_future=0.0, shape="SMOOTH",
                 orientation=ephemeral.WORLD, scope="LIMB", pins=()):
        self.ob = ob
        self.bones = list(bones)
        self.bone = self.bones[-1]
        self.frame = int(frame)
        self.shape = shape
        # Corpo solves the whole chain up to the dragged tail (keeping the dragged bone's world turn would
        # lock the very bone the body leans with); hand/foot orientation applies to limbs only
        self.orientation = ephemeral.LOCAL if scope == BODY else orientation
        self.scope = scope
        self.solver = ephemeral.DLS if scope == BODY else ephemeral.AUTO
        self.radius_past = float(radius_past)
        self.radius_future = float(radius_future)
        self.delta = np.zeros(3)
        self.result = None
        self.trail_frames = np.empty(0)
        self.trail_points = np.empty((0, 3))
        self.reason = ""
        scene = bpy.context.scene
        if scene.frame_current != self.frame:
            scene.frame_set(self.frame)
        # pinned limbs: (index of the chain bone they hang from, limb bones)
        self.pins = []
        for hint, limb in pins:
            j = _attach_index(ob, self.bones, limb[0], hint)
            if j is not None and not set(limb) & set(self.bones):
                self.pins.append((j, list(limb)))
        self.reason = refusal(ob, [b for _j, limb in self.pins for b in limb]) or spaces.chain_rigidity(
            ob, self.bones, [(self.bones[j], limb[0]) for j, limb in self.pins])
        self.edited = self.bones + [b for _j, limb in self.pins for b in limb]
        self.channels = []          # (bone name, channel, axis)
        self.snapshot = Snapshot(ob)
        for name in self.edited:
            pb = ob.pose.bones[name]
            channel, size = spaces.rotation_channel(pb)
            for axis in range(size):
                self.snapshot.capture(pb.path_from_id(channel), axis)
                self.channels.append((name, channel, axis))
        if not self.reason:
            self._prepare()

    @property
    def editable(self):
        return bool(self.channels) and not self.reason

    # -- window -------------------------------------------------------------------------------
    def window_frames(self):
        lo = self.frame - int(math.floor(self.radius_past)) - PAD
        hi = self.frame + int(math.floor(self.radius_future)) + PAD
        return np.arange(lo, hi + 1)

    @staticmethod
    def _chain(data, base=None):
        return ephemeral.Chain(data["base"] if base is None else base, data["links"], data["lengths"], data["loc"],
                               data["rot"], data["modes"], data["scale"], data["locks"])

    def _prepare(self):
        """Sample the chain (and pinned limbs) over the window from the *original* Action; keep the models."""
        scene = bpy.context.scene
        self.frames = self.window_frames()
        self.chain = self._chain(spaces.prefetch_chain(self.ob, self.bones, self.frames, scene))
        world = self.chain.world()
        self.pin_data = []
        for j, limb in self.pins:
            data = spaces.prefetch_chain(self.ob, limb, self.frames, scene)
            rel = np.linalg.inv(world[:, j]) @ data["base"]
            self.pin_data.append(ephemeral.Pin(parent=j, rel=rel, limb=self._chain(data)))
        self.weights = falloff.weight_signed(self.frames.astype(np.float64) - self.frame, self.radius_past,
                                             self.radius_future, self.shape)
        self.tip0 = self.chain.tip()
        cb = action_io.channelbag(self.ob)
        self.models = {}
        self.current = {}
        for name, channel, axis in self.channels:
            path = self.ob.pose.bones[name].path_from_id(channel)
            fc = cb.fcurves.find(path, index=axis) if cb is not None else None
            model = action_io.read_channel(fc) if fc is not None else _empty_model()
            self.models[(name, axis)] = model
            self.current[(name, axis)] = dense.current_values(model, int(self.frames[0]), len(self.frames))

    def set_radii(self, radius_past, radius_future):
        """New window: back to the original curves, sample again, re-apply the current drag."""
        self.restore()
        self.radius_past, self.radius_future = float(radius_past), float(radius_future)
        self._prepare()
        self.apply(self.delta)

    def weights_at_keys(self):
        """[(frame, weight)] of the window frames with weight > 0 (header / overlay)."""
        return [(int(f), float(w)) for f, w in zip(self.frames, self.weights) if w > 0.0]

    # -- edit ---------------------------------------------------------------------------------
    def _rotations(self):
        """{bone name: (N, size) new rotation values} from the last solve."""
        out = dict(zip(self.bones, self.result.rot))
        for (_j, limb), rots in zip(self.pins, self.result.pins):
            out.update(zip(limb, rots))
        return out

    def apply(self, delta_world):
        self.delta = np.asarray(tuple(delta_world), dtype=np.float64)
        self.result = ephemeral.sculpt(self.chain, self.weights, self.delta, self.orientation,
                                       solver=self.solver, pins=self.pin_data)
        rotations = self._rotations()
        start = int(self.frames[0])
        for name, channel, axis in self.channels:
            pb = self.ob.pose.bones[name]
            fc, _created = action_io.ensure_channel(self.ob, pb, channel, axis)
            model = dense.write_dense(self.models[(name, axis)], start, rotations[name][:, axis],
                                      default=getattr(pb, channel)[axis], current=self.current[(name, axis)])
            action_io.write_channel(fc, model)
        action_io.tag(self.ob)

    def prefetch(self, frames):
        """The trail of the dragged control (its tail) as cached when the gesture started."""
        from ..trails import provider

        trail = provider.get_trail(self.ob, self.bone)
        if trail is None or self.reason:
            return
        # only a trail of the tail matches the dragged point (a translation control's trail follows its head)
        here = trail.point_at(self.frame)
        i0 = np.nonzero(self.frames == self.frame)[0]
        if here is None or len(i0) == 0 or np.linalg.norm(np.asarray(here) - self.tip0[i0[0]]) > 1e-3:
            return
        self.trail_frames = trail.frames.astype(np.int64)
        self.trail_points = trail.points.astype(np.float64)

    def world_at(self, frame):
        idx = np.nonzero(self.frames == int(frame))[0]
        if len(idx) == 0:
            return None
        tips = self.result.tip if self.result is not None else self.tip0
        return tuple(tips[idx[0]])

    def preview(self):
        """Predicted trail: the cached trail with the window frames replaced by the new tail positions;
        without a trail (bone dragged directly), the window's tail positions."""
        if self.result is None:
            return []
        if len(self.trail_frames) == 0:
            return [tuple(p) for p in self.result.tip]
        pts = self.trail_points.copy()
        where = {int(f): j for j, f in enumerate(self.frames)}
        for n, f in enumerate(self.trail_frames):
            j = where.get(int(f))
            if j is not None:
                pts[n] = self.result.tip[j]
        return [tuple(p) for p in pts]

    def restore(self):
        self.snapshot.restore()

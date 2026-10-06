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
from ..core import dense, ephemeral, falloff, pose_keys
from ..core import kinematics as kin
from ..core.fcurve_model import ChannelModel

PIVOT_ITERATIONS = 3   # stage 1 of the aim (decision 10): fixed-point steps measured on the rig
PAD = 1     # frames of weight 0 written on each side of the window (curves created by the gesture stay flat outside)
BODY = "BODY"
POSE, DENSE = "POSE", "DENSE"     # key modes (ADR 0015)


def pose_frames(ob) -> list:
    """The character's pose keys: every integer frame that holds a key on any channel of its Action."""
    cb = action_io.channelbag(ob)
    if cb is None:
        return []
    out = set()
    for fc in cb.fcurves:
        n = len(fc.keyframe_points)
        if n:
            co = np.empty(2 * n)
            fc.keyframe_points.foreach_get("co", co)
            out.update(int(round(x)) for x in co[0::2])
    return sorted(out)


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


def window_start(lo, frame) -> int:
    """First frame a gesture may write: ``lo``, cut at frame 0 by default (``Scene.asc_sculpt.clip_negative``;
    a gesture grabbed before 0 keeps its own frame)."""
    settings = getattr(bpy.context.scene, "asc_sculpt", None)
    if settings is None or not settings.clip_negative:
        return int(lo)
    return int(max(lo, min(0, frame)))


def rest_bend_sign(ob, bones) -> float:
    """+1/−1: the side the chain's middle joint (elbow, knee) bends to about the middle bone's X axis, read
    from the rest pose (rigs model a slight natural bend); +1 when the rest pose is straight or the chain
    is shorter than two bones. Keeps the two-bone IK on one side at every frame (no elbow flips)."""
    if len(bones) < 2:
        return 1.0
    a, b = ob.data.bones[bones[0]], ob.data.bones[bones[1]]
    n = (a.tail_local - a.head_local).cross(b.tail_local - b.head_local)
    if n.length < 1e-3 * a.length * b.length:
        return 1.0
    return 1.0 if n.dot(b.matrix_local.to_3x3().col[0]) >= 0.0 else -1.0


def _face_frame(pts):
    """Orthonormal frame (3, 3) (columns: edge, in-plane, normal) of a face from its first three vertices."""
    e1 = pts[1] - pts[0]
    e1 = e1 / max(float(np.linalg.norm(e1)), 1e-12)
    n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    n = n / max(float(np.linalg.norm(n)), 1e-12)
    return np.stack((e1, np.cross(n, e1), n), axis=1)


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
                 orientation=ephemeral.WORLD, scope="LIMB", pins=(), point_world=None, point_bone=None,
                 aim_bones=(), point_deform=None, point_skin=None, key_mode=DENSE, pose_influence=0.25):
        # POSE: pose to pose (ADR 0015) — keys only at the posed frame and, × pose_influence, at the character's
        # neighbouring pose keys in the window; DENSE: one key per frame of the window (ADR 0011)
        self.key_mode = key_mode
        self.pose_influence = float(pose_influence)
        """``point_world``: the grabbed spot on the body (world, at ``frame``), rigid with ``point_bone``
        (default: the chain's last bone); None = the last bone's tail. ``aim_bones`` (decision 10, e.g. Rigify
        ``neck, head``): the chain only leans; ``finish`` then measures the rig and (1) leans further until the
        first aimed bone's head moved by the drag, (2) with two bones aims the first so the second's head lands
        where a two-bone IK puts it, (3) aims the last so the grabbed spot (on it) reaches its target."""
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
        self.point_bone = point_bone or self.bone
        # the grabbed spot as the skin carries it: on its deform bone (Rigify's DEF-spine.00N follows the chest
        # control only partly); measured on the rig on release and corrected (finish)
        self.point_deform = point_deform if point_deform and point_deform in ob.pose.bones else None
        self.deform_local = None
        if point_world is not None and self.point_deform:
            md = np.asarray(ob.matrix_world @ ob.pose.bones[self.point_deform].matrix, dtype=np.float64)
            self.deform_local = (np.linalg.inv(md) @ np.r_[np.asarray(point_world, dtype=np.float64), 1.0])[:3]
        # better: the skin itself (vertices of the hit face: inverse-distance weights + an offset kept in the
        # face's own frame, so it turns with the skin), since a skin vertex blends several deform bones
        self.skin = None
        if point_world is not None and point_skin and len(point_skin[1]) >= 3:
            from . import body_pick

            mesh, face = point_skin
            pts = body_pick.skin_points(mesh, face)
            hit = np.asarray(point_world, dtype=np.float64)
            w = 1.0 / (np.linalg.norm(pts - hit, axis=1) + 1e-6)
            w = w / w.sum()
            frame = _face_frame(pts)
            self.skin = (mesh, tuple(face), w, frame.T @ (hit - w @ pts))
        self.aim_bones = [b for b in aim_bones if b not in self.bones]
        self.aim_bone = self.aim_bones[-1] if self.aim_bones else None
        self.point_local = None             # grabbed point in point_bone's local space (constant)
        if point_world is not None:
            pb = ob.pose.bones[self.point_bone]
            m = np.asarray(ob.matrix_world @ pb.matrix, dtype=np.float64)
            self.point_local = (np.linalg.inv(m) @ np.r_[np.asarray(point_world, dtype=np.float64), 1.0])[:3]
        # pinned limbs: (index of the chain bone they hang from, limb bones)
        self.pins = []
        for hint, limb in pins:
            j = _attach_index(ob, self.bones, limb[0], hint)
            if j is not None and not set(limb) & set(self.bones):
                self.pins.append((j, list(limb)))
        self.reason = (refusal(ob, [b for _j, limb in self.pins for b in limb] + self.aim_bones)
                       or spaces.chain_rigidity(ob, self.bones, [(self.bones[j], limb[0]) for j, limb in self.pins]))
        self.edited = self.bones + [b for _j, limb in self.pins for b in limb]
        self.aim_channels = []      # rotation channels of the aimed bones (written by finish)
        for name in self.aim_bones:
            channel, size = spaces.rotation_channel(ob.pose.bones[name])
            self.aim_channels += [(name, channel, axis) for axis in range(size)]
        self.channels = []          # (bone name, channel, axis)
        self.snapshot = Snapshot(ob)
        for name in self.edited:
            pb = ob.pose.bones[name]
            channel, size = spaces.rotation_channel(pb)
            for axis in range(size):
                self.snapshot.capture(pb.path_from_id(channel), axis)
                self.channels.append((name, channel, axis))
        for name, channel, axis in self.aim_channels:
            self.snapshot.capture(ob.pose.bones[name].path_from_id(channel), axis)
        if not self.reason:
            self._prepare()

    @property
    def editable(self):
        return bool(self.channels) and not self.reason

    # -- window -------------------------------------------------------------------------------
    def window_frames(self):
        lo = self.frame - int(math.floor(self.radius_past)) - PAD
        hi = self.frame + int(math.floor(self.radius_future)) + PAD
        lo = window_start(lo, self.frame)
        if self.key_mode == POSE:     # the posed frame and the pose keys inside the window
            return np.array(sorted({self.frame} | {f for f in self.pose_frames if lo <= f <= hi}), dtype=np.int64)
        return np.arange(lo, hi + 1)

    def _chain(self, data, bones, base=None):
        return ephemeral.Chain(data["base"] if base is None else base, data["links"], data["lengths"], data["loc"],
                               data["rot"], data["modes"], data["scale"], data["locks"],
                               bend_sign=rest_bend_sign(self.ob, bones))

    def _prepare(self):
        """Sample the chain (and pinned limbs) over the window from the *original* Action; keep the models."""
        scene = bpy.context.scene
        self.pose_frames = pose_frames(self.ob)
        self.frames = self.window_frames()
        extra = [self.point_bone] if self.point_local is not None and self.point_bone != self.bone else []
        extra += [b for b in self.aim_bones if b not in extra]
        if self.deform_local is not None and self.point_deform not in extra:
            extra.append(self.point_deform)
        data = spaces.prefetch_chain(self.ob, self.bones, self.frames, scene, extra=extra)
        self.chain = self._chain(data, self.bones)
        world = self.chain.world()
        self.aim_origin = None
        if self.aim_bone and self.point_local is not None:
            # stage 1 drags the chain's tail; the grabbed spot's own path is kept for the aim stage
            self.aim_origin = np.einsum("nij,j->ni", data["extra"][self.aim_bone], np.r_[self.point_local, 1.0])[:, :3]
            self.pivot_origin = data["extra"][self.aim_bones[0]][:, :3, 3].copy()
        elif self.point_local is not None:
            p = np.r_[self.point_local, 1.0]
            if self.point_bone != self.bone:   # the point's bone is outside the chain: re-expressed per frame
                pts = np.einsum("nij,j->ni", data["extra"][self.point_bone], p)
                self.chain.point = np.einsum("nij,nj->ni", np.linalg.inv(world[:, -1]), pts)[:, :3]
            else:
                self.chain.point = self.point_local
        # the grabbed spot's own path before the edit: the goal on the skin is that path + w·Δ (not the
        # chain-rigid approximation, which only coincides at the grabbed frame)
        self.spot_origin = None
        if self.skin is not None:
            self.spot_origin = self._measure_skin()
        elif self.deform_local is not None:
            self.spot_origin = np.einsum("nij,j->ni", data["extra"][self.point_deform],
                                         np.r_[self.deform_local, 1.0])[:, :3]
        self.pin_data = []
        for j, limb in self.pins:
            data = spaces.prefetch_chain(self.ob, limb, self.frames, scene)
            rel = np.linalg.inv(world[:, j]) @ data["base"]
            self.pin_data.append(ephemeral.Pin(parent=j, rel=rel, limb=self._chain(data, limb)))
        self.weights = falloff.weight_signed(self.frames.astype(np.float64) - self.frame, self.radius_past,
                                             self.radius_future, self.shape)
        if self.key_mode == POSE:     # the other poses change only a little ("Influência nas poses")
            self.weights = np.where(self.frames == self.frame, self.weights, self.weights * self.pose_influence)
        self.tip0 = self.chain.tip()
        cb = action_io.channelbag(self.ob)
        self.models = {}
        self.current = {}
        for name, channel, axis in self.channels:
            path = self.ob.pose.bones[name].path_from_id(channel)
            fc = cb.fcurves.find(path, index=axis) if cb is not None else None
            model = action_io.read_channel(fc) if fc is not None else _empty_model()
            self.models[(name, axis)] = model
            if self.key_mode == DENSE:
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

    def apply(self, delta_world, target=None):
        self.delta = np.asarray(tuple(delta_world), dtype=np.float64)
        self.result = ephemeral.sculpt(self.chain, self.weights, self.delta, self.orientation,
                                       solver=self.solver, pins=self.pin_data, target=target)
        self._write()

    def _write(self):
        """Keys of every edited channel from ``self.result`` (dense or pose to pose)."""
        rotations = self._rotations()
        for name, channel, axis in self.channels:
            pb = self.ob.pose.bones[name]
            fc, _created = action_io.ensure_channel(self.ob, pb, channel, axis)
            model = self._keys(self.models[(name, axis)], rotations[name][:, axis], getattr(pb, channel)[axis],
                               self.current.get((name, axis)))
            action_io.write_channel(fc, model)
        action_io.tag(self.ob)

    def _keys(self, model, values, default, current=None):
        """The channel with ``values`` (one per window frame) written in the gesture's key mode; frames of
        weight 0 are left alone."""
        if self.key_mode == POSE:
            on = self.weights > 0.0
            return pose_keys.write_keys(model, self.frames[on], np.asarray(values)[on], default=default,
                                        anchors=self.pose_frames)
        return dense.write_dense(model, int(self.frames[0]), values, default=default, current=current)

    def prefetch(self, frames, trail=None):
        """The trail of the dragged control (its tail) as cached when the gesture started (``trail``: taken
        before the window was sampled — the frame stepping can drop the engine's cache)."""
        from ..trails import provider

        if trail is None:
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
        if self.aim_origin is not None:     # the aimed part follows on release; show where it is going
            return [tuple(p) for p in self.aim_origin + self.weights[:, None] * self.delta[None, :]]
        if len(self.trail_frames) == 0:
            return [tuple(p) for p in self.result.tip]
        pts = self.trail_points.copy()
        where = {int(f): j for j, f in enumerate(self.frames)}
        for n, f in enumerate(self.trail_frames):
            j = where.get(int(f))
            if j is not None:
                pts[n] = self.result.tip[j]
        return [tuple(p) for p in pts]

    def finish(self):
        """Steps after the chain, measured on the rig as it is after each step (frame stepping over the window,
        fixed number of steps): the skin's spot follow-up, then the aim stages (decision 10)."""
        self._follow_skin()
        if not self.aim_bones or self.result is None or self.aim_origin is None:
            return
        active = self.weights > 0.0
        goal = self.aim_origin + self.weights[:, None] * self.delta[None, :]
        first, last = self.aim_bones[0], self.aim_bones[-1]
        # (1) lean further until the first aimed bone's head (base of the neck) moved by w·Δ
        pivot_goal = self.pivot_origin + self.weights[:, None] * self.delta[None, :]
        target = self.result.target.copy()
        for _ in range(PIVOT_ITERATIONS):
            err = np.where(active[:, None], pivot_goal - self._measure([first])[first][:, :3, 3], 0.0)
            if np.abs(err).max() < 1e-5:
                break
            target = target + err
            self.apply(self.delta, target=target)
        p_last = np.r_[self.point_local, 1.0]
        if len(self.aim_bones) > 1:
            # (2) aim the first so the last's head goes where a two-bone IK (first head, last head, spot) puts it
            m = self._measure([first, last])
            a, b = m[first][:, :3, 3], m[last][:, :3, 3]
            c = np.einsum("nij,j->ni", m[last], p_last)[:, :3]
            d1, _d2, _tip = kin.two_bone_ik(a, b, c, goal, m[first][:, :3, 0])
            b_goal = a + np.einsum("nij,nj->ni", d1, b - a)
            b_local = np.einsum("nij,nj->ni", np.linalg.inv(m[first]), np.c_[b, np.ones(len(b))])[:, :3]
            self._aim(first, b_local, b_goal, active)
        # (3) aim the last so the grabbed spot reaches its target
        self._aim(last, np.broadcast_to(self.point_local, (len(self.frames), 3)), goal, active)

    def _follow_skin(self):
        """The grabbed spot is on a deform bone that may not be rigid with the chain (Rigify's spine tweaks):
        re-solve the chain with the target moved by the error measured on the skin (fixed-point steps)."""
        if self.result is None or self.aim_bones:
            return
        if self.skin is None and (self.deform_local is None or self.point_deform == self.point_bone):
            return
        if self.spot_origin is None:
            return
        active = self.weights > 0.0
        p = np.r_[self.deform_local, 1.0] if self.deform_local is not None else None
        goal = self.spot_origin + self.weights[:, None] * self.delta[None, :]
        target = self.result.target.copy()          # tip0 + w·Δ: the chain's own first guess
        gain = np.ones(len(self.frames))      # how much the spot moves per unit of target move (per frame)
        last_spots = last_target = None
        best_err = np.full(len(self.frames), np.inf)
        best_target = target.copy()
        step_limit = max(float(np.linalg.norm(self.delta)), 0.01)   # a correction never jumps more than the drag
        for it in range(PIVOT_ITERATIONS + 1):
            if self.skin is not None:
                spots = self._measure_skin()
            else:
                spots = np.einsum("nij,j->ni", self._measure([self.point_deform])[self.point_deform], p)[:, :3]
            err = np.where(active[:, None], goal - spots, 0.0)
            norm = np.linalg.norm(err, axis=1)
            better = norm < best_err                    # keep, per frame, the best target measured so far
            best_err = np.where(better, norm, best_err)
            best_target = np.where(better[:, None], target, best_target)
            if norm.max() < 5e-5 or it == PIVOT_ITERATIONS:
                break
            if last_spots is not None:      # scalar secant per frame, clamped (deterministic)
                dt = target - last_target
                ds = spots - last_spots
                den = np.sum(dt * dt, axis=1)
                est = np.where(den > 1e-12, np.sum(ds * dt, axis=1) / np.maximum(den, 1e-12), gain)
                gain = np.clip(est, 0.2, 2.0)
            last_spots, last_target = spots, target.copy()
            step = err / gain[:, None]
            size = np.linalg.norm(step, axis=1, keepdims=True)
            step = np.where(size > step_limit, step * (step_limit / np.maximum(size, 1e-12)), step)
            target = target + step
            self.apply(self.delta, target=target)
        if not np.array_equal(best_target, target):     # an unreachable spot (e.g. right at a joint) never gets worse
            self.apply(self.delta, target=best_target)
        self.result.target = self.tip0 + self.weights[:, None] * self.delta[None, :]

    def _own_bones(self):
        return set(self.edited) | set(self.aim_bones)

    def _measure_skin(self):
        """The grabbed skin spot per window frame, on the deformed mesh (frame stepping)."""
        from . import body_pick

        mesh, face, w, offset = self.skin
        scene = bpy.context.scene
        out = np.empty((len(self.frames), 3))
        current, sub = scene.frame_current, scene.frame_subframe
        with spaces.preserve_pose(self.ob, skip=self._own_bones()):
            try:
                for j, f in enumerate(self.frames):
                    scene.frame_set(int(f))
                    pts = body_pick.skin_points(mesh, face)
                    out[j] = w @ pts + _face_frame(pts) @ offset
            finally:
                scene.frame_set(current, subframe=sub)
        return out

    def _measure(self, bones):
        """{bone: (N, 4, 4) world matrix per window frame}, evaluated on the rig (frame stepping)."""
        scene = bpy.context.scene
        mw = np.asarray(self.ob.matrix_world, dtype=np.float64)
        out = {b: np.empty((len(self.frames), 4, 4)) for b in bones}
        current, sub = scene.frame_current, scene.frame_subframe
        with spaces.preserve_pose(self.ob, skip=self._own_bones()):
            try:
                for j, f in enumerate(self.frames):
                    scene.frame_set(int(f))
                    for b in bones:
                        out[b][j] = mw @ np.asarray(self.ob.pose.bones[b].matrix, dtype=np.float64)
            finally:
                scene.frame_set(current, subframe=sub)
        return out

    def _aim(self, bone, local_point, goals, active):
        """Turn ``bone`` about its head (minimal rotation) so its ``local_point`` (N, 3) points at ``goals``
        (N, 3) on every active frame, measured on the rig; written as dense keys on its rotation channels."""
        scene = bpy.context.scene
        ob = self.ob
        pb = ob.pose.bones[bone]
        mode = pb.rotation_mode
        channel, size = spaces.rotation_channel(pb)
        mw = np.asarray(ob.matrix_world, dtype=np.float64)
        old = np.empty((len(self.frames), size))
        new = np.empty((len(self.frames), size))
        current, sub = scene.frame_current, scene.frame_subframe
        with spaces.preserve_pose(ob, skip=self._own_bones()):
            try:
                for j, f in enumerate(self.frames):
                    scene.frame_set(int(f))
                    old[j] = getattr(pb, channel)
                    if not active[j]:
                        new[j] = old[j]
                        continue
                    pose = np.asarray(pb.matrix, dtype=np.float64)
                    world = mw @ pose
                    head, point = world[:3, 3], (world @ np.r_[local_point[j], 1.0])[:3]
                    delta = kin.rotation_between(point - head, goals[j] - head)
                    frame = kin.orthonormalize((mw @ pose @ np.linalg.inv(np.asarray(pb.matrix_basis)))[:3, :3])
                    r = kin.local_rotation_update(frame, delta, kin.rotation_to_mat3(old[j], mode))
                    if mode == "QUATERNION":
                        q = kin.mat3_to_quat(r)
                        new[j] = -q if float(np.dot(q, old[j])) < 0.0 else q
                    else:
                        new[j] = kin.mat3_to_euler(r, mode, compatible=old[j])
            finally:
                scene.frame_set(current, subframe=sub)
        cb = action_io.channelbag(ob)
        for axis in range(size):
            fc_old = cb.fcurves.find(pb.path_from_id(channel), index=axis) if cb is not None else None
            model = action_io.read_channel(fc_old) if fc_old is not None else _empty_model()
            fc, _created = action_io.ensure_channel(ob, pb, channel, axis)
            action_io.write_channel(fc, self._keys(model, new[:, axis], old[0, axis]))
        action_io.tag(ob)

    def restore(self):
        self.snapshot.restore()


class RotateEdit(ChainEdit):
    """The "Girar" gesture (ADR 0014): turn one bone about its head over the time window — about the view
    axis (trackball, the default) or about the bone's own axis (twist). Same snapshot / dense keys / undo /
    Esc as ``ChainEdit``; nothing else of the chain machinery (no skin follow-up, no aim)."""

    kind = "ROTATE"

    def __init__(self, ob, bone, frame, radius_past=0.0, radius_future=0.0, shape="SMOOTH", view_axis=(0.0, 0.0, 1.0),
                 key_mode=DENSE, pose_influence=0.25):
        super().__init__(ob, [bone], frame, radius_past, radius_future, shape, scope="TIP", key_mode=key_mode,
                         pose_influence=pose_influence)
        self.angle = 0.0
        self.twist = False
        self.view_axis = np.asarray(view_axis, dtype=np.float64)

    def apply_rotation(self, angle, twist=False):
        self.angle, self.twist = float(angle), bool(twist)
        if self.angle == 0.0:                     # no turn: the Action stays bit-identical (no dense keys)
            self.result = None
            self.restore()
            return
        axis = self.chain.world()[:, -1, :3, 1] if self.twist else self.view_axis
        self.result = ephemeral.rotate(self.chain, self.weights, axis, self.angle)
        self._write()

    def apply(self, delta_world=None, target=None):
        """Re-apply the current turn (``set_radii`` calls this after sampling the new window)."""
        self.apply_rotation(self.angle, self.twist)

    def finish(self):
        pass


class TrailSmoothEdit(ChainEdit):
    """The Smooth brush on the trail (docs/design/sculpt-ux.md "Smooth da trail"): the grabbed point's world
    path over the window is Gaussian-smoothed (``core.smooth``, falloff weights × strength) and the limb is
    solved at every frame so the point follows the smoothed path (ephemeral rig, per-frame target). Same
    interface as ``smooth_edit.SmoothEdit``: ``apply_passes(n)`` from the original path, incremental."""

    kind = "SMOOTH"
    MAX_PASSES = 64

    def __init__(self, ob, bones, frame, radius_past=0.0, radius_future=0.0, shape="SMOOTH", strength=0.5,
                 sigma=1.5, point_world=None, point_bone=None):
        self.strength, self.sigma = float(strength), float(sigma)
        self.passes = 0
        # WORLD: the last bone keeps its world turn, so the two-bone IK lands the point on the path exactly
        super().__init__(ob, bones, frame, radius_past, radius_future, shape, ephemeral.WORLD, scope="LIMB",
                         key_mode=DENSE,
                         point_world=point_world, point_bone=point_bone)

    def _prepare(self):
        super()._prepare()
        self.path0 = self.chain.tip()
        self._path = self.path0.copy()
        self._done = 0

    def apply_passes(self, passes):
        from ..core import smooth

        passes = max(0, min(int(passes), self.MAX_PASSES))
        if passes < self._done:
            self._path, self._done = self.path0.copy(), 0
        for _ in range(passes - self._done):
            self._path = smooth.smooth_pass(self._path, self.weights, self.strength, self.sigma)
        self._done = self.passes = passes
        if passes == 0:
            self.result = None
            self.restore()
            return
        self.result = ephemeral.sculpt(self.chain, self.weights, np.zeros(3), self.orientation,
                                       solver=self.solver, target=self._path)
        self._write()

    def apply(self, delta_world=None, target=None):
        self.apply_passes(self.passes)

    def finish(self):
        pass

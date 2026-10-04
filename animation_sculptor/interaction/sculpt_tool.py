# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Animation Sculptor" tool (Pose Mode) and its gesture operator (ADR 0010).

One gesture = one modal operator run = one undo step. Esc / RMB restore a snapshot of the edited
F-Curves bit for bit. The trail engine is suspended for the whole gesture and invalidated on release.

Spike scope (agenda item 4): grab of a *key point* of a translation control. The F-Curve access and
the math move to ``anim/`` and ``core/`` in the next items; arc drag, retime and spacing follow.
"""

import time

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

import numpy as np

from .. import rig
from ..anim import action_io, spaces
from ..anim.snapshot import Snapshot
from ..core import bezier, falloff, sculpt_ops
from ..trails import provider
from . import gizmo, picking, state

TOOL_ID = "animation_sculptor.sculpt"
PRECISION = 0.1
RADIUS_KEYS = {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'LEFT_BRACKET', 'RIGHT_BRACKET'}
PASSIVE_KEYS = {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFTMOUSE', 'MIDDLEMOUSE', 'B'} | RADIUS_KEYS


class _EditBase:
    """Shared by the spatial gestures: snapshot of the location channels, P(f) cache, live preview."""

    kind = "BASE"

    def __init__(self, ob, pb, frame):
        self.ob = ob
        self.pb = pb
        self.frame = frame
        self.trail_frames = np.empty(0)
        self.p_cache = np.empty((0, 4, 4))
        self.frame_index = {}
        self.space_constant = False
        scene = bpy.context.scene
        if scene.frame_current != frame:
            scene.frame_set(frame)
        self.snapshot = Snapshot(ob)
        self.path = pb.path_from_id("location")
        for axis in range(3):
            self.snapshot.capture(self.path, axis)
        # base space of `location` at this frame (anim/spaces): Δl = R(f)⁻¹ · Δw
        self.r_inv = spaces.location_space(ob, pb).to_3x3().inverted_safe()

    def _location_fcurves(self):
        cb = action_io.channelbag(self.ob)
        return [cb.fcurves.find(self.path, index=i) if cb is not None else None for i in range(3)]

    def extra_frames(self):
        return []

    def prefetch(self, frames):
        """P(f) for the trail frames (+ frames the edit needs), see anim/spaces."""
        frames = sorted({int(f) for f in frames} | {int(f) for f in self.extra_frames()} | {int(self.frame)})
        scene = bpy.context.scene
        self.p_cache, self.space_constant = spaces.prefetch(self.ob, self.pb, frames, scene)
        self.trail_frames = np.asarray(frames, dtype=np.float64)
        self.frame_index = {f: i for i, f in enumerate(frames)}

    def r_inv_at(self, frame):
        i = self.frame_index.get(int(frame))
        if i is None:
            return self.r_inv
        return Matrix(self.p_cache[i].tolist()).to_3x3().inverted_safe()

    def world_at(self, frame):
        """Current world position of the control at ``frame`` from the edited curves."""
        i = self.frame_index.get(int(frame))
        if i is None:
            return None
        return tuple(self._points(np.array([float(frame)]), self.p_cache[i:i + 1])[0])

    def _points(self, frames, mats):
        loc = np.empty((len(frames), 4))
        loc[:, 3] = 1.0
        for i, fc in enumerate(self._location_fcurves()):
            if fc is not None and len(fc.keyframe_points):
                loc[:, i] = bezier.evaluate(action_io.read_channel(fc), frames)
            else:
                loc[:, i] = self.pb.location[i]
        return np.einsum("nij,nj->ni", mats, loc)[:, :3]

    def preview(self):
        """Predicted world trail P(f) @ location(f), location(f) from the edited curves (core.bezier)."""
        if len(self.trail_frames) == 0:
            return []
        return [tuple(p) for p in self._points(self.trail_frames, self.p_cache)]

    def restore(self):
        self.snapshot.restore()


class _GrabEdit(_EditBase):
    """Grab of the location keys at one frame, optionally *soft*: the other location keys of the control
    within ``radius`` frames follow with a falloff weight, each through its own R(f)⁻¹.

    Every unlocked location axis gets a key at the grabbed frame (inserted with the current value when
    missing, the F-Curve created when absent), so the edit is always stored as keyframes. Neighbour keys
    are never created: soft grab only moves keys that exist.
    """

    kind = "GRAB"

    def __init__(self, ob, pb, frame, radius=0.0, shape="SMOOTH"):
        super().__init__(ob, pb, frame)
        self.radius = float(radius)
        self.shape = shape
        self.channels = []          # (axis, fcurve, key index, base model)
        for axis in range(3):
            if pb.lock_location[axis]:
                continue
            fc, _created = action_io.ensure_channel(ob, pb, "location", axis)
            idx, _inserted = action_io.ensure_key(fc, frame, pb.location[axis])
            self.channels.append((axis, fc, idx, action_io.read_channel(fc)))

    @property
    def editable(self):
        return bool(self.channels)

    def neighbor_frames(self):
        """Other location key frames of the control (union over the edited axes)."""
        frames = set()
        for _axis, _fc, _idx, base in self.channels:
            frames.update(int(round(x)) for x in base.frames)
        frames.discard(int(self.frame))
        return sorted(frames)

    def extra_frames(self):
        return self.neighbor_frames()

    def weights(self):
        """[(frame, weight)] of the neighbour keys inside the radius."""
        frames = self.neighbor_frames()
        if self.radius <= 0 or not frames:
            return []
        w = falloff.weight(np.asarray(frames, dtype=np.float64) - self.frame, self.radius, self.shape)
        return [(f, float(x)) for f, x in zip(frames, w) if x > 0.0]

    def apply(self, delta_world):
        delta_world = Vector(delta_world)
        moves = [(self.frame, self.r_inv @ delta_world)]
        moves += [(f, self.r_inv_at(f) @ (delta_world * w)) for f, w in self.weights()]
        for axis, fc, _idx, base in self.channels:
            model = base
            for f, dl in moves:
                j = model.key_index(f)
                if j is not None:
                    model = sculpt_ops.grab_key(model, j, dl[axis])
            action_io.write_channel(fc, model)
        action_io.tag(self.ob)


class _ArcEdit(_EditBase):
    """Arc drag of an in-between: the inner handles of the segment around ``frame`` are solved so the
    control passes through the dragged point there (core.sculpt_ops.arc_drag). Keys and timing stay."""

    kind = "ARC"

    def __init__(self, ob, pb, frame):
        super().__init__(ob, pb, frame)
        self.break_tangent = False
        self.channels = []          # (axis, fcurve, base model)
        self.refused = {}           # axis -> reason
        cb = action_io.channelbag(ob)
        for axis in range(3):
            if pb.lock_location[axis]:
                continue
            fc = cb.fcurves.find(self.path, index=axis) if cb is not None else None
            if fc is None or len(fc.keyframe_points) < 2:
                self.refused[axis] = "eixo sem animação"
                continue
            base = action_io.read_channel(fc)
            _out, reason = sculpt_ops.arc_drag(base, frame, 1e-3)
            if reason:
                self.refused[axis] = reason
            else:
                self.channels.append((axis, fc, base))

    @property
    def editable(self):
        return bool(self.channels)

    def reason(self):
        return next(iter(self.refused.values()), "nada a editar")

    def apply(self, delta_world):
        dv = self.r_inv @ Vector(delta_world)
        for axis, fc, base in self.channels:
            out, _reason = sculpt_ops.arc_drag(base, self.frame, dv[axis], self.break_tangent)
            action_io.write_channel(fc, out)
        action_io.tag(self.ob)


class ASC_OT_sculpt_gesture(bpy.types.Operator):
    """Sculpt the motion trail: drag a key point (grab, soft with the wheel) or an in-between (arc)"""
    bl_idname = "asc.sculpt_gesture"
    bl_label = "Animation Sculptor"
    bl_options = {'REGISTER', 'UNDO'}

    # parametric form (tests, redo): same edit as the mouse gesture
    obj_name: StringProperty(options={'SKIP_SAVE'})
    bone: StringProperty(options={'SKIP_SAVE'})
    frame: IntProperty(options={'SKIP_SAVE'})
    delta: FloatVectorProperty(size=3, subtype='TRANSLATION', unit='LENGTH', options={'SKIP_SAVE'})
    mode: EnumProperty(items=(('AUTO', "Auto", "Grab on key points, arc drag on in-betweens"),
                              ('GRAB', "Grab", ""), ('ARC', "Arc", "")), default='AUTO', options={'SKIP_SAVE'})
    radius: FloatProperty(name="Raio (frames)", min=0.0, max=500.0, default=0.0, options={'SKIP_SAVE'})
    break_tangent: BoolProperty(name="Quebrar tangente", default=False, options={'SKIP_SAVE'})

    def _begin(self, context, obj_name, bone, frame, mode, radius=0.0):
        ob = bpy.data.objects.get(obj_name)
        pb = ob.pose.bones.get(bone) if ob is not None and ob.pose is not None else None
        if pb is None:
            return "controle não encontrado"
        info = rig.get_adapter(ob).classify(ob, bone)
        if info is None:
            return "não é um controle do rig (MCH/ORG/DEF)"
        if not info.translates:
            return "controle só de rotação: sculpt espacial de FK no Escopo 4 (use tempo: Ctrl+arrastar)"
        reason = action_io.refusal(ob, pb, "location")
        if reason:
            return reason
        if mode == 'AUTO':
            mode = 'GRAB' if action_io.bone_has_key(ob, pb, frame) else 'ARC'
        if mode == 'GRAB':
            if not action_io.bone_has_key(ob, pb, frame):
                return "sem key neste frame"
            self.edit = _GrabEdit(ob, pb, frame, radius, state.SETTINGS["falloff"])
            if not self.edit.editable:
                return "sem key de location editável neste frame"
        else:
            self.edit = _ArcEdit(ob, pb, frame)
            if not self.edit.editable:
                return self.edit.reason()
        self.obj_name, self.bone, self.frame = obj_name, bone, frame
        return ""

    def execute(self, context):
        reason = self._begin(context, self.obj_name, self.bone, self.frame, self.mode, self.radius)
        if reason:
            self.report({'WARNING'}, f"Animation Sculptor: {reason}")
            return {'CANCELLED'}
        with provider.suspended(keys=[(self.obj_name, self.bone)]):
            if self.edit.kind == "GRAB" and self.radius > 0:
                self.edit.prefetch([])
            if self.edit.kind == "ARC":
                self.edit.break_tangent = self.break_tangent
            self.edit.apply(self.delta)
        return {'FINISHED'}

    def invoke(self, context, event):
        hit = state.HOVER
        if hit is None or context.region_data is None:
            return {'PASS_THROUGH'}
        if event.ctrl:
            return self._refuse(context, hit, "tempo (retime/spacing): próximo passo")
        mode = 'GRAB' if hit.is_key else 'ARC'
        reason = self._begin(context, hit.obj_name, hit.bone, hit.frame, mode, state.SETTINGS["radius"])
        if reason:
            return self._refuse(context, hit, reason)
        self.origin = Vector(hit.world)
        self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.accum = Vector((0.0, 0.0, 0.0))
        provider.suspend()
        trail = provider.get_trail_by_key((hit.obj_name, hit.bone))
        t0 = time.perf_counter()
        self.edit.prefetch(trail.frames if trail is not None else [])
        state.STATS["prefetch_ms"] = (time.perf_counter() - t0) * 1000.0
        state.STATS["prefetch_frames"] = len(self.edit.trail_frames)
        state.HOVER = None
        state.REFUSAL = None
        state.GESTURE = {"kind": self.edit.kind, "world": tuple(self.origin), "bone": hit.bone,
                         "frame": hit.frame, "preview": self.edit.preview(), "falloff": []}
        self._update_falloff()
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _refuse(self, context, hit, reason):
        state.MESSAGE = reason
        state.REFUSAL = {"world": hit.world, "frame": hit.frame, "bone": hit.bone, "reason": reason}
        if context.area is not None:
            context.area.header_text_set(f"Animation Sculptor · recusado: {reason}")
            context.area.tag_redraw()
        self.report({'WARNING'}, f"Animation Sculptor: {reason}")
        return {'CANCELLED'}

    def _update_falloff(self):
        if self.edit.kind != "GRAB":
            return
        state.GESTURE["falloff"] = [(self.edit.world_at(f), w) for f, w in self.edit.weights()]

    def _header(self, context):
        d = self.accum
        delta = f"Δ ({d.x:+.3f}, {d.y:+.3f}, {d.z:+.3f}) m"
        if self.edit.kind == "GRAB":
            n = len(self.edit.weights())
            head = (f"Grab {self.bone} @ {self.frame}   {delta}   raio {self.edit.radius:g} frames "
                    f"({n} key(s) vizinha(s)) · roda/[ ]: raio")
        else:
            skipped = ""
            if self.edit.refused:
                skipped = " · eixos recusados: " + ", ".join("XYZ"[a] for a in self.edit.refused)
            tangent = "on" if self.edit.break_tangent else "off"
            head = f"Arco {self.bone} @ {self.frame}   {delta}   B: quebrar tangente [{tangent}]{skipped}"
        context.area.header_text_set(head + "   Shift: precisão · Esc/RMB: cancelar · soltar: confirmar")

    def _reapply(self, context):
        self.edit.apply(self.accum)
        state.GESTURE["world"] = tuple(self.origin + self.accum)
        state.GESTURE["preview"] = self.edit.preview()
        self._update_falloff()
        self._header(context)
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            t0 = time.perf_counter()
            region, rv3d = context.region, context.region_data
            mouse = (event.mouse_region_x, event.mouse_region_y)
            depth = self.origin + self.accum
            step = (picking.screen_to_world(region, rv3d, mouse, depth)
                    - picking.screen_to_world(region, rv3d, self.last_mouse, depth))
            self.accum += step * (PRECISION if event.shift else 1.0)
            self.last_mouse = mouse
            self._reapply(context)
            state.STATS["last_move_ms"] = (time.perf_counter() - t0) * 1000.0
            return {'RUNNING_MODAL'}
        if self.edit.kind == "GRAB" and event.value == 'PRESS' and event.type in RADIUS_KEYS:
            step = 1.0 if event.type in {'WHEELUPMOUSE', 'RIGHT_BRACKET'} else -1.0
            self.edit.radius = max(0.0, min(500.0, self.edit.radius + step))
            state.SETTINGS["radius"] = self.edit.radius
            self._reapply(context)
            return {'RUNNING_MODAL'}
        if self.edit.kind == "ARC" and event.type == 'B' and event.value == 'PRESS':
            self.edit.break_tangent = not self.edit.break_tangent
            self._reapply(context)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE' or (
                event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
            self._end(context, cancel=False)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.edit.restore()
            self._end(context, cancel=True)
            return {'CANCELLED'}
        if event.value == 'PRESS' and event.type not in PASSIVE_KEYS:
            # a lost mouse release must never leave the gesture (and the trail engine) hanging:
            # any other key confirms the gesture and is passed on (e.g. I still inserts keys)
            self._end(context, cancel=False)
            return {'FINISHED', 'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _end(self, context, cancel):
        state.GESTURE = None
        context.area.header_text_set(None)
        context.area.tag_redraw()
        # cancel restored the F-Curves bit for bit: the cached trail is still the truth
        provider.resume(keys=[] if cancel else [(self.obj_name, self.bone)])
        if not cancel:
            # recompute the edited trail now instead of waiting for the engine's timer
            t0 = time.perf_counter()
            provider.update_now()
            state.STATS["refresh_ms"] = (time.perf_counter() - t0) * 1000.0


class ASC_WT_sculpt(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'POSE'
    bl_idname = TOOL_ID
    bl_label = "Animation Sculptor"
    bl_description = "Esculpe o movimento direto nas trajetórias: arraste pontos da trail"
    bl_icon = "ops.pose.breakdowner"
    bl_widget = gizmo.ASC_GGT_trails.bl_idname
    # clicks that miss the trail keep the usual bone selection
    bl_keymap = (
        ("view3d.select", {"type": 'LEFTMOUSE', "value": 'CLICK'}, {"properties": [("deselect_all", True)]}),
        ("view3d.select", {"type": 'LEFTMOUSE', "value": 'CLICK', "shift": True}, {"properties": [("toggle", True)]}),
        ("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )


classes = (ASC_OT_sculpt_gesture,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(ASC_WT_sculpt, after={"builtin.transform"}, separator=True, group=False)


def unregister():
    try:
        bpy.utils.unregister_tool(ASC_WT_sculpt)
    except Exception as exc:
        print(f"[Animation Sculptor] unregister_tool: {exc}")
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

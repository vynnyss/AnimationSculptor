# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Animation Sculptor" tool (Pose Mode) and its gesture operator (ADR 0010).

One gesture = one modal operator run = one undo step. Esc / RMB restore a snapshot of the edited
F-Curves bit for bit. The trail engine is suspended for the whole gesture and invalidated on release.

Spike scope (agenda item 4): grab of a *key point* of a translation control. The F-Curve access and
the math move to ``anim/`` and ``core/`` in the next items; arc drag, retime and spacing follow.
"""

import time

import bpy
from bpy.props import FloatVectorProperty, IntProperty, StringProperty
from mathutils import Vector

import numpy as np

from ..anim import action_io, spaces
from ..anim.snapshot import Snapshot
from ..core import bezier, sculpt_ops
from ..trails import provider
from . import gizmo, picking, state

TOOL_ID = "animation_sculptor.sculpt"
PRECISION = 0.1


class _GrabEdit:
    """Rigid grab of the location keys at one frame: snapshot, auto-key, apply, restore, live preview.

    Every unlocked location axis gets a key at the frame (inserted with the current value when missing,
    the F-Curve created when absent), so the edit is always stored as keyframes. Cancel restores the
    snapshot: inserted keys and created curves disappear, the rest is bit for bit.
    """

    def __init__(self, ob, pb, frame):
        self.ob = ob
        self.pb = pb
        self.frame = frame
        self.trail_frames = np.empty(0)
        self.p_cache = np.empty((0, 4, 4))
        scene = bpy.context.scene
        if scene.frame_current != frame:
            scene.frame_set(frame)
        self.snapshot = Snapshot(ob)
        path = pb.path_from_id("location")
        self.channels = []          # (axis, fcurve, key index, base model)
        for axis in range(3):
            self.snapshot.capture(path, axis)
            if pb.lock_location[axis]:
                continue
            fc, _created = action_io.ensure_channel(ob, pb, "location", axis)
            idx, _inserted = action_io.ensure_key(fc, frame, pb.location[axis])
            self.channels.append((axis, fc, idx, action_io.read_channel(fc)))
        cb = action_io.channelbag(ob)
        self.loc_fcurves = [cb.fcurves.find(path, index=i) for i in range(3)]
        # base space of `location` at this frame (anim/spaces): Δl = R(f)⁻¹ · Δw
        self.r_inv = spaces.location_space(ob, pb).to_3x3().inverted_safe()

    @property
    def editable(self):
        return bool(self.channels)

    def prefetch(self, frames):
        """P(f) for every trail frame (frame stepping; the edited control never drives its own parent).
        Returns to the gesture frame."""
        scene = bpy.context.scene
        mats = []
        for f in frames:
            scene.frame_set(int(f))
            mats.append(np.array(spaces.location_space(self.ob, self.pb), dtype=np.float64))
        scene.frame_set(self.frame)
        self.trail_frames = np.asarray(frames, dtype=np.float64)
        self.p_cache = np.array(mats).reshape(-1, 4, 4)

    def preview(self):
        """Predicted world trail P(f) @ location(f); location(f) from the edited curves (core.bezier)."""
        if len(self.trail_frames) == 0:
            return []
        loc = np.empty((len(self.trail_frames), 4))
        loc[:, 3] = 1.0
        for i, fc in enumerate(self.loc_fcurves):
            if fc is not None and len(fc.keyframe_points):
                loc[:, i] = bezier.evaluate(action_io.read_channel(fc), self.trail_frames)
            else:
                loc[:, i] = self.pb.location[i]
        pts = np.einsum("nij,nj->ni", self.p_cache, loc)[:, :3]
        return [tuple(p) for p in pts]

    def apply(self, delta_world):
        dl = self.r_inv @ Vector(delta_world)
        for axis, fc, idx, base in self.channels:
            action_io.write_channel(fc, sculpt_ops.grab_key(base, idx, dl[axis]))
        action_io.tag(self.ob)

    def restore(self):
        self.snapshot.restore()


class ASC_OT_sculpt_gesture(bpy.types.Operator):
    """Sculpt the motion trail: drag a key point to move the pose at that frame"""
    bl_idname = "asc.sculpt_gesture"
    bl_label = "Animation Sculptor"
    bl_options = {'REGISTER', 'UNDO'}

    # parametric form (tests, redo): grab the key of `bone` at `frame` by `delta` (world space, meters)
    obj_name: StringProperty(options={'SKIP_SAVE'})
    bone: StringProperty(options={'SKIP_SAVE'})
    frame: IntProperty(options={'SKIP_SAVE'})
    delta: FloatVectorProperty(size=3, subtype='TRANSLATION', unit='LENGTH', options={'SKIP_SAVE'})

    def _begin(self, context, obj_name, bone, frame):
        ob = bpy.data.objects.get(obj_name)
        pb = ob.pose.bones.get(bone) if ob is not None and ob.pose is not None else None
        if pb is None:
            return "controle não encontrado"
        reason = action_io.refusal(ob, pb, "location")
        if reason:
            return reason
        if not action_io.bone_has_key(ob, pb, frame):
            return "sem key neste frame (arc drag de in-between: próximo passo)"
        if all(pb.lock_location):
            return "location travada nos 3 eixos"
        self.edit = _GrabEdit(ob, pb, frame)
        if not self.edit.editable:
            return "sem key de location editável neste frame"
        self.obj_name, self.bone, self.frame = obj_name, bone, frame
        return ""

    def execute(self, context):
        reason = self._begin(context, self.obj_name, self.bone, self.frame)
        if reason:
            self.report({'WARNING'}, f"Animation Sculptor: {reason}")
            return {'CANCELLED'}
        with provider.suspended(keys=[(self.obj_name, self.bone)]):
            self.edit.apply(self.delta)
        return {'FINISHED'}

    def invoke(self, context, event):
        hit = state.HOVER
        if hit is None or context.region_data is None:
            return {'PASS_THROUGH'}
        if event.ctrl:
            return self._refuse(context, "tempo (retime/spacing): ainda não implementado")
        if not hit.is_key:
            return self._refuse(context, "arc drag de in-between: ainda não implementado")
        reason = self._begin(context, hit.obj_name, hit.bone, hit.frame)
        if reason:
            return self._refuse(context, reason)
        self.origin = Vector(hit.world)
        self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.accum = Vector((0.0, 0.0, 0.0))
        provider.suspend()
        trail = provider.get_trail_by_key((hit.obj_name, hit.bone))
        t0 = time.perf_counter()
        self.edit.prefetch(trail.frames if trail is not None else [hit.frame])
        state.STATS["prefetch_ms"] = (time.perf_counter() - t0) * 1000.0
        state.STATS["prefetch_frames"] = len(self.edit.trail_frames)
        state.HOVER = None
        state.GESTURE = {"kind": "GRAB", "world": tuple(self.origin), "bone": hit.bone, "frame": hit.frame,
                         "preview": self.edit.preview(), "ghost": None if trail is None else trail.points.copy()}
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _refuse(self, context, reason):
        state.MESSAGE = reason
        self.report({'WARNING'}, f"Animation Sculptor: {reason}")
        return {'CANCELLED'}

    def _header(self, context):
        d = self.accum
        context.area.header_text_set(
            f"Grab {self.bone} @ {self.frame}   Δ ({d.x:+.3f}, {d.y:+.3f}, {d.z:+.3f}) m   "
            "Shift: precisão · Esc/RMB: cancelar · soltar: confirmar"
        )

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            t0 = time.perf_counter()
            region, rv3d = context.region, context.region_data
            mouse = (event.mouse_region_x, event.mouse_region_y)
            depth = self.origin + self.accum
            step = picking.screen_to_world(region, rv3d, mouse, depth) - picking.screen_to_world(region, rv3d, self.last_mouse, depth)
            self.accum += step * (PRECISION if event.shift else 1.0)
            self.last_mouse = mouse
            self.edit.apply(self.accum)
            state.GESTURE["world"] = tuple(self.origin + self.accum)
            state.GESTURE["preview"] = self.edit.preview()
            self._header(context)
            context.area.tag_redraw()
            state.STATS["last_move_ms"] = (time.perf_counter() - t0) * 1000.0
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE' or (
                event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
            self._end(context, cancel=False)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.edit.restore()
            self._end(context, cancel=True)
            return {'CANCELLED'}
        if event.value == 'PRESS' and event.type not in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFTMOUSE',
                                                          'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
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

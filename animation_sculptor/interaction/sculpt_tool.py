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
from ..core import bezier, falloff, ruler, sculpt_ops, timing_ops
from ..trails import provider
from ..ui import prefs, props
from . import ephemeral_edit, gizmo, hud, picking, smooth_edit, state, timing_edit


def _settings():
    return props.get()

TOOL_ID = "animation_sculptor.sculpt"          # Membro (kept id: keymaps and files of 0.3–0.6 point to it)
TOOL_TIP = "animation_sculptor.tip"
TOOL_BODY = "animation_sculptor.body"
TOOL_SMOOTH = "animation_sculptor.smooth"
TOOL_IDS = (TOOL_TIP, TOOL_ID, TOOL_BODY, TOOL_SMOOTH)
TOOL_SCOPES = {TOOL_TIP: "TIP", TOOL_ID: "LIMB", TOOL_BODY: "BODY"}


def active_tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return None
    return tool.idname if tool is not None else None
RADIUS_KEYS = {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'LEFT_BRACKET', 'RIGHT_BRACKET'}
PASSIVE_KEYS = {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_ALT', 'RIGHT_ALT',
                'OSKEY', 'LEFTMOUSE', 'MIDDLEMOUSE', 'B'} | RADIUS_KEYS


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
    within ``radius_past`` frames before / ``radius_future`` frames after follow with a falloff weight
    (core.falloff.weight_signed), each through its own R(f)⁻¹.

    Every unlocked location axis gets a key at the grabbed frame (inserted with the current value when
    missing, the F-Curve created when absent), so the edit is always stored as keyframes. Neighbour keys
    are never created: soft grab only moves keys that exist.
    """

    kind = "GRAB"

    def __init__(self, ob, pb, frame, radius_past=0.0, radius_future=0.0, shape="SMOOTH"):
        super().__init__(ob, pb, frame)
        self.radius_past = float(radius_past)
        self.radius_future = float(radius_future)
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
        """[(frame, weight)] of the neighbour keys inside the window (past / future radius)."""
        frames = self.neighbor_frames()
        if (self.radius_past <= 0 and self.radius_future <= 0) or not frames:
            return []
        w = falloff.weight_signed(np.asarray(frames, dtype=np.float64) - self.frame, self.radius_past,
                                  self.radius_future, self.shape)
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
    # UNDO without REGISTER: one undo step per gesture, no "Adjust Last Operation" panel (a redo would re-run
    # execute() without the drag, the grabbed point or the Smooth passes of the interactive gesture)
    bl_options = {'UNDO'}

    # parametric form (tests, redo): same edit as the mouse gesture
    obj_name: StringProperty(options={'SKIP_SAVE'})
    bone: StringProperty(options={'SKIP_SAVE'})
    frame: IntProperty(options={'SKIP_SAVE'})
    delta: FloatVectorProperty(size=3, subtype='TRANSLATION', unit='LENGTH', options={'SKIP_SAVE'})
    mode: EnumProperty(items=(('AUTO', "Auto", "Grab on key points, arc drag on in-betweens"),
                              ('GRAB', "Grab", ""), ('ARC', "Arc", ""),
                              ('CHAIN', "Cadeia FK", "Ephemeral rig on a rotation-only control (dense keys)"),
                              ('SMOOTH', "Smooth", "Smooth brush: `passes` Gaussian passes in the time window"),
                              ('RETIME', "Retime", "Move the pose key at frame to new_frame"),
                              ('SPACING', "Spacing", "Ease/favor of the segment around frame")),
                       default='AUTO', options={'SKIP_SAVE'})
    radius: FloatProperty(name="Raio (frames)", min=0.0, max=500.0, default=0.0, options={'SKIP_SAVE'})
    radius_past: FloatProperty(name="Raio passado", min=-1.0, max=500.0, default=-1.0, options={'SKIP_SAVE'},
                               description="Raio para trás (frames); -1 = usar Raio")
    radius_future: FloatProperty(name="Raio futuro", min=-1.0, max=500.0, default=-1.0, options={'SKIP_SAVE'},
                                 description="Raio para frente (frames); -1 = usar Raio")
    break_tangent: BoolProperty(name="Quebrar tangente", default=False, options={'SKIP_SAVE'})
    chain_scope: EnumProperty(items=(('SCENE', "Cena", "Use Scene.asc_sculpt.ephemeral_scope"),
                                     ('LIMB', "Membro", ""), ('TIP', "Ponta", ""), ('BODY', "Corpo", "")),
                              default='SCENE', options={'SKIP_SAVE'})
    point: FloatVectorProperty(size=3, subtype='TRANSLATION', unit='LENGTH', options={'SKIP_SAVE'},
                               description="Grabbed spot on the body (world, at frame); with use_point")
    use_point: BoolProperty(default=False, options={'SKIP_SAVE'})
    passes: IntProperty(default=1, min=0, options={'SKIP_SAVE'}, description="Smooth passes (execute)")
    from_bone: BoolProperty(default=False, options={'SKIP_SAVE'},
                            description="The gesture grabs the bone's tail at the current frame (no trail)")
    orientation: EnumProperty(items=(('SCENE', "Cena", "Use Scene.asc_sculpt.tip_orientation"),
                                     ('WORLD', "Mundo", ""), ('LOCAL', "Local", "")),
                              default='SCENE', options={'SKIP_SAVE'})
    new_frame: FloatProperty(options={'SKIP_SAVE'})
    favor: FloatProperty(options={'SKIP_SAVE'})
    ease: FloatProperty(options={'SKIP_SAVE'})
    scope: EnumProperty(items=(('CHARACTER', "Personagem", "Todas as F-Curves do rig"),
                               ('SELECTED', "Selecionados", "Só os bones selecionados")),
                        default='CHARACTER', options={'SKIP_SAVE'})
    policy: EnumProperty(items=(('PRESERVE_PATH', "Preservar caminho", ""),
                                ('PRESERVE_SMOOTHNESS', "Preservar suavidade", "")),
                         default='PRESERVE_PATH', options={'SKIP_SAVE'})

    def _begin_timing(self, context, obj_name, bone, frame, mode, scope, policy):
        ob = bpy.data.objects.get(obj_name)
        pb = ob.pose.bones.get(bone) if ob is not None and ob.pose is not None else None
        if pb is None:
            return "controle não encontrado"
        if rig.get_adapter(ob).classify(ob, bone) is None:
            return "não é um controle do rig (MCH/ORG/DEF)"
        reason = timing_edit.refusal(ob)
        if reason:
            return reason
        if mode == 'RETIME':
            self.edit = timing_edit.RetimeEdit(ob, pb, frame, scope)
            if not self.edit.editable:
                return "nenhuma key nesse frame"
        else:
            self.edit = timing_edit.SpacingEdit(ob, pb, frame, scope, policy)
            if not self.edit.editable:
                return self.edit.reason
        self.obj_name, self.bone, self.frame = obj_name, bone, frame
        return ""

    def _begin(self, context, obj_name, bone, frame, mode, radii=(0.0, 0.0)):
        ob = bpy.data.objects.get(obj_name)
        pb = ob.pose.bones.get(bone) if ob is not None and ob.pose is not None else None
        if pb is None:
            return "controle não encontrado"
        info = rig.get_adapter(ob).classify(ob, bone)
        if info is None:
            return "não é um controle do rig (MCH/ORG/DEF)"
        if not info.translates or mode == 'CHAIN':       # CHAIN: also a translation control dragged by its tail
            return self._begin_chain(ob, obj_name, bone, frame, radii)
        reason = action_io.refusal(ob, pb, "location")
        if reason:
            return reason
        if mode == 'AUTO':
            mode = 'GRAB' if action_io.bone_has_key(ob, pb, frame) else 'ARC'
        if mode == 'GRAB':
            if not action_io.bone_has_key(ob, pb, frame):
                return "sem key neste frame"
            self.edit = _GrabEdit(ob, pb, frame, radii[0], radii[1],
                                  _settings().falloff if _settings() else "SMOOTH")
            if not self.edit.editable:
                return "sem key de location editável neste frame"
        else:
            self.edit = _ArcEdit(ob, pb, frame)
            if not self.edit.editable:
                return self.edit.reason()
        self.obj_name, self.bone, self.frame = obj_name, bone, frame
        return ""

    def _scope(self):
        """Gesture scope: the operator's, else the active tool's (Ponta/Membro/Corpo), else the scene's."""
        if self.chain_scope != 'SCENE':
            return self.chain_scope
        scope = TOOL_SCOPES.get(active_tool_id(bpy.context))
        if scope is not None:
            return scope
        settings = _settings()
        return settings.ephemeral_scope if settings is not None else rig.LIMB

    def _grab_point(self):
        return Vector(self.point) if self.use_point else getattr(self, "_point", None)

    def _begin_smooth(self, ob, obj_name, bones, frame, radii):
        settings = _settings()
        for name in bones:
            if ob.pose.bones.get(name) is None:
                return "controle não encontrado"
        self.edit = smooth_edit.SmoothEdit(ob, bones, frame, radii[0], radii[1],
                                           settings.falloff if settings is not None else "SMOOTH",
                                           settings.smooth_strength if settings is not None else 0.5,
                                           settings.smooth_sigma if settings is not None else 1.5)
        if not self.edit.editable:
            return self.edit.reason
        self.obj_name, self.bone, self.frame = obj_name, bones[-1], frame
        return ""

    def _begin_chain(self, ob, obj_name, bone, frame, radii):
        """The ephemeral rig turns the control's chain (ADR 0011): rotation-only controls, or any control
        whose tail is dragged in the Corpo scope."""
        settings = _settings()
        scope = self._scope()
        orientation = self.orientation if self.orientation != 'SCENE' else (
            settings.tip_orientation if settings is not None else "WORLD")
        adapter = rig.get_adapter(ob)
        bones, reason = adapter.ephemeral_chain(ob, bone, scope)
        if reason:
            return reason
        reason = ephemeral_edit.refusal(ob, bones)
        if reason:
            return reason
        pins = adapter.ephemeral_pins(ob, bones)[0] if scope == rig.BODY else []
        aim = adapter.ephemeral_aim(ob, bone, scope)
        point = self._grab_point()
        if point is None and bone not in bones:     # the dragged control is aimed after the chain: its tail
            if bpy.context.scene.frame_current != frame:
                bpy.context.scene.frame_set(frame)
            point = ob.matrix_world @ ob.pose.bones[bone].tail
        t0 = time.perf_counter()
        self.edit = ephemeral_edit.ChainEdit(ob, bones, frame, radii[0], radii[1],
                                             settings.falloff if settings is not None else "SMOOTH", orientation,
                                             scope=scope, pins=pins, point_world=point,
                                             point_bone=bone if point is not None else None, aim_bones=aim,
                                             point_deform=getattr(self, "_deform", None),
                                             point_skin=getattr(self, "_skin", None))
        state.STATS["prefetch_ms"] = (time.perf_counter() - t0) * 1000.0
        if self.edit.reason:
            return self.edit.reason
        if not self.edit.editable:
            return "sem canais de rotação"
        self.obj_name, self.bone, self.frame = obj_name, bone, frame
        return ""

    def execute(self, context):
        if self.mode == 'SMOOTH':
            ob = bpy.data.objects.get(self.obj_name)
            if ob is None:
                return {'CANCELLED'}
            radii = (self.radius if self.radius_past < 0 else self.radius_past,
                     self.radius if self.radius_future < 0 else self.radius_future)
            reason = self._begin_smooth(ob, self.obj_name, [self.bone], self.frame, radii)
            if reason:
                self.report({'WARNING'}, f"Animation Sculptor: {reason}")
                return {'CANCELLED'}
            with provider.suspended(keys=None):
                self.edit.apply_passes(self.passes)
            return {'FINISHED'}
        if self.mode in {'RETIME', 'SPACING'}:
            reason = self._begin_timing(context, self.obj_name, self.bone, self.frame, self.mode, self.scope,
                                        self.policy)
            if reason:
                self.report({'WARNING'}, f"Animation Sculptor: {reason}")
                return {'CANCELLED'}
            with provider.suspended(keys=None):
                if self.mode == 'RETIME':
                    self.edit.apply(self.new_frame)
                else:
                    self.edit.apply(self.favor, self.ease)
            return {'FINISHED'}
        radii = (self.radius if self.radius_past < 0 else self.radius_past,
                 self.radius if self.radius_future < 0 else self.radius_future)
        reason = self._begin(context, self.obj_name, self.bone, self.frame, self.mode, radii)
        if reason:
            self.report({'WARNING'}, f"Animation Sculptor: {reason}")
            return {'CANCELLED'}
        with provider.suspended(keys=None if self.edit.kind == "CHAIN" else [(self.obj_name, self.bone)]):
            if self.edit.kind == "GRAB" and max(radii) > 0:
                self.edit.prefetch([])
            if self.edit.kind == "ARC":
                self.edit.break_tangent = self.break_tangent
            self.edit.apply(self.delta)
            if self.edit.kind == "CHAIN":
                self.edit.finish()
        return {'FINISHED'}

    def invoke(self, context, event):
        if state.RULER_HOVER is not None:
            # the gizmo routes every click here: a click on an end handle of the time ruler is not a sculpt
            # gesture, it starts the ruler modal (its own undo step); this operator ends without one
            bpy.ops.asc.time_window('INVOKE_DEFAULT', side=state.RULER_HOVER, shift=event.shift)
            return {'CANCELLED'}
        hit = state.HOVER
        if hit is None or context.region_data is None:
            return {'PASS_THROUGH'}
        if hit.reason:
            return self._refuse(context, hit, hit.reason)
        tool = active_tool_id(context)
        if tool in TOOL_IDS:
            state.LAST_TOOL = tool
        settings = _settings()
        radii = (settings.radius_past, settings.radius_future) if settings is not None else (0.0, 0.0)
        if tool == TOOL_SMOOTH:
            return self._invoke_smooth(context, event, hit, radii)
        if event.ctrl and not hit.on_body:
            return self._invoke_timing(context, event, hit)
        mode = 'GRAB' if hit.is_key else 'ARC'
        self.from_bone = bool(getattr(hit, "on_bone", False))
        self._point = None
        self._deform = None
        self._skin = None
        if self.from_bone:
            mode = 'CHAIN'
        if hit.on_body:
            # grabbing the body: an IK control is grabbed (key at this frame) or arced; anything else turns
            # its chain with the ephemeral rig, dragging the grabbed spot (ADR 0013)
            if hit.kind == rig.IK:
                mode = 'GRAB' if hit.is_key else 'ARC'
            else:
                mode, self._point = 'CHAIN', Vector(hit.world)
            self._deform = hit.deform
            self._skin = (hit.mesh, hit.face) if hit.face else None
        reason = self._begin(context, hit.obj_name, hit.bone, hit.frame, mode, radii)
        if reason:
            return self._refuse(context, hit, reason)
        self.origin = Vector(hit.world)
        self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.accum = Vector((0.0, 0.0, 0.0))
        provider.suspend()
        trail = provider.get_trail_by_key((hit.obj_name, hit.bone))
        t0 = time.perf_counter()
        self.edit.prefetch(trail.frames if trail is not None else [])
        if self.edit.kind != "CHAIN":         # the chain sampled its window in _begin_chain
            state.STATS["prefetch_ms"] = (time.perf_counter() - t0) * 1000.0
        state.STATS["prefetch_frames"] = len(self.edit.trail_frames)
        state.HOVER = None
        state.REFUSAL = None
        state.GESTURE = {"kind": self.edit.kind, "world": tuple(self.origin), "bone": hit.bone,
                         "frame": hit.frame, "preview": self.edit.preview(), "falloff": [],
                         "mesh": hit.mesh, "deform": hit.deform}
        self._update_falloff()
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _invoke_smooth(self, context, event, hit, radii):
        ob = bpy.data.objects.get(hit.obj_name)
        if ob is None:
            return {'CANCELLED'}
        if context.scene.frame_current != hit.frame:
            context.scene.frame_set(hit.frame)
        reason = self._begin_smooth(ob, hit.obj_name, [hit.bone], hit.frame, radii)
        if reason:
            return self._refuse(context, hit, reason)
        self.origin = Vector(hit.world)
        self.last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self.accum = Vector((0.0, 0.0, 0.0))
        self.stroke = 0.0
        provider.suspend()
        state.HOVER = None
        state.REFUSAL = None
        state.GESTURE = {"kind": "SMOOTH", "world": tuple(self.origin), "bone": hit.bone, "frame": hit.frame,
                         "preview": None, "falloff": [], "mesh": hit.mesh, "deform": hit.deform, "label": ""}
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _move_smooth(self, context, event):
        from ..core import smooth

        mouse = (event.mouse_region_x, event.mouse_region_y)
        self.stroke += ((mouse[0] - self.last_mouse[0]) ** 2 + (mouse[1] - self.last_mouse[1]) ** 2) ** 0.5
        self.last_mouse = mouse
        passes = smooth.passes_for_drag(self.stroke)
        if passes != self.edit.passes:
            self.edit.apply_passes(passes)
            state.GESTURE["label"] = f"smooth ×{passes}"
        self._header(context)
        context.area.tag_redraw()

    def _invoke_timing(self, context, event, hit):
        mode = 'RETIME' if hit.is_key else 'SPACING'
        settings = _settings()
        scope = settings.timing_scope if settings is not None else "CHARACTER"
        policy = settings.spacing_policy if settings is not None else timing_ops.PRESERVE_PATH
        reason = self._begin_timing(context, hit.obj_name, hit.bone, hit.frame, mode, scope, policy)
        if reason:
            return self._refuse(context, hit, reason)
        self.origin = Vector(hit.world)
        self.mouse0 = Vector((event.mouse_region_x, event.mouse_region_y))
        self.last_mouse = self.mouse0.copy()
        self.mdelta = Vector((0.0, 0.0))
        self.accum = Vector((0.0, 0.0, 0.0))
        self.trail = provider.get_trail_by_key((hit.obj_name, hit.bone))
        self.dir, self.ppf = Vector((1.0, 0.0)), 0.0
        if mode == 'RETIME' and self.trail is not None:
            before = self.trail.point_at(hit.frame - 1)
            after = self.trail.point_at(hit.frame + 1)
            a = picking.world_to_screen(context.region, context.region_data, before if before is not None else hit.world)
            b = picking.world_to_screen(context.region, context.region_data, after if after is not None else hit.world)
            if a is not None and b is not None:
                span = 2.0 if before is not None and after is not None else 1.0
                self.dir = b - a
                self.ppf = self.dir.length / span
        provider.suspend()
        state.HOVER = None
        state.REFUSAL = None
        state.GESTURE = {"kind": self.edit.kind, "world": tuple(self.origin), "bone": hit.bone,
                         "frame": hit.frame, "preview": None, "falloff": [], "label": ""}
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _move_timing(self, context, event):
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self.mdelta += (mouse - self.last_mouse) * (prefs.value("precision") if event.shift else 1.0)
        self.last_mouse = mouse
        if self.edit.kind == "RETIME":
            frames = timing_ops.retime_frames_from_screen(self.mdelta, self.dir, self.ppf,
                                                          prefs.value("retime_px_per_frame"))
            target = self.frame + frames
            if not event.shift:
                target = round(target)
            applied = self.edit.apply(target)
            frame_int = int(round(applied))
            if context.scene.frame_current != frame_int:
                context.scene.frame_set(frame_int)
            state.GESTURE["label"] = f"{self.frame} → {applied:g}"
        else:
            favor = self.mdelta.x / prefs.value("spacing_px")
            ease = self.mdelta.y / prefs.value("spacing_px")
            self.edit.apply(favor, ease)
            if self.trail is not None:
                pts = self.edit.preview(self.trail.frames, self.trail.points)
                state.GESTURE["preview"] = None if pts is None else [tuple(p) for p in pts]
                state.GESTURE["speed"] = True
            lo, li = self.edit.current
            state.GESTURE["label"] = f"saída {lo:.0%} · chegada {li:.0%}"
        self._header(context)
        context.area.tag_redraw()

    def _refuse(self, context, hit, reason):
        state.MESSAGE = reason
        state.REFUSAL = {"world": hit.world, "frame": hit.frame, "bone": hit.bone, "reason": reason}
        if context.area is not None:
            context.area.header_text_set(f"Animation Sculptor · recusado: {reason}")
            context.area.tag_redraw()
        self.report({'WARNING'}, f"Animation Sculptor: {reason}")
        return {'CANCELLED'}

    @staticmethod
    def _store_radii(radius_past, radius_future):
        """Remember the window in the scene (saved with the file); both sides written as they are."""
        settings = _settings()
        if settings is None:
            return
        linked = settings.radius_linked
        settings.radius_linked = False
        settings.radius_past = radius_past
        settings.radius_future = radius_future
        settings.radius_linked = linked

    def _update_falloff(self):
        if self.edit.kind == "CHAIN":
            # rings on the control's key frames inside the window (all frames get keys; these are the poses)
            trail = provider.get_trail_by_key((self.obj_name, self.bone))
            keys = set(trail.keyframes) if trail is not None else set()
            state.GESTURE["falloff"] = [(self.edit.world_at(f), w) for f, w in self.edit.weights_at_keys()
                                        if f in keys and f != self.frame]
            return
        if self.edit.kind != "GRAB":
            return
        state.GESTURE["falloff"] = [(self.edit.world_at(f), w) for f, w in self.edit.weights()]

    def _header(self, context):
        hint = "   Shift: precisão · Esc/RMB: cancelar · soltar: confirmar"
        if self.edit.kind == "SMOOTH":
            e = self.edit
            context.area.header_text_set(
                f"Smooth {e.bone} @ {self.frame}   passes {e.passes} · força {e.strength:.0%} · janela "
                f"←{e.radius_past:g} · {e.radius_future:g}→   (arraste sobre a parte para suavizar mais)" + hint)
            return
        if self.edit.kind == "RETIME":
            e = self.edit
            limits = f"entre {e.low:g} e {e.high:g}" if e.high != float("inf") and e.low != float("-inf") else ""
            context.area.header_text_set(
                f"Retime da pose {self.frame} → {e.target:g}   {len(e.keyed)} canal(is) · {e.scope.lower()} "
                f"{limits}   (arraste ao longo da trail; Shift: sub-frame)" + hint)
            return
        if self.edit.kind == "SPACING":
            e = self.edit
            lo, li = e.current
            policy = "preservar caminho" if e.policy == timing_ops.PRESERVE_PATH else "preservar suavidade"
            context.area.header_text_set(
                f"Spacing {e.k0:g}→{e.k1:g}   saída {lo:.0%} · chegada {li:.0%}   {len(e.channels)} canal(is) · "
                f"{policy}   (horizontal: favorecer · vertical: ease)" + hint)
            return
        d = self.accum
        delta = f"Δ ({d.x:+.3f}, {d.y:+.3f}, {d.z:+.3f}) m"
        if self.edit.kind == "CHAIN":
            e = self.edit
            frames = e.frames[e.weights > 0.0]
            span = f"{int(frames[0])}–{int(frames[-1])}" if len(frames) else str(self.frame)
            pinned = f" · pés presos: {len(e.pins)}" if e.pins else ""
            name = "Corpo" if e.scope == rig.BODY else "Cadeia FK"
            head = (f"{name} {' → '.join(e.bones)}{pinned} @ {self.frame}   {delta}   janela {span} "
                    f"(←{e.radius_past:g} · {e.radius_future:g}→) · keys em todo frame · roda/[ ]: raio")
            if e.result is not None and not e.result.reached[e.frames == self.frame].all():
                head += " · fora de alcance"
            if e.result is not None and e.result.pins_reached is not None and not e.result.pins_reached.all():
                head += " · pé fora de alcance (perna esticada)"
            context.area.header_text_set(head + "   Shift: precisão · Esc/RMB: cancelar · soltar: confirmar")
            return
        if self.edit.kind == "GRAB":
            n = len(self.edit.weights())
            head = (f"Grab {self.bone} @ {self.frame}   {delta}   raio ←{self.edit.radius_past:g} · "
                    f"{self.edit.radius_future:g}→ frames ({n} key(s) vizinha(s)) · roda/[ ]: raio")
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
        if self.edit.kind == "SMOOTH":
            return self._modal_smooth(context, event)
        if event.type == 'MOUSEMOVE' and self.edit.kind in {"RETIME", "SPACING"}:
            t0 = time.perf_counter()
            self._move_timing(context, event)
            state.STATS["last_move_ms"] = (time.perf_counter() - t0) * 1000.0
            return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            t0 = time.perf_counter()
            region, rv3d = context.region, context.region_data
            mouse = (event.mouse_region_x, event.mouse_region_y)
            depth = self.origin + self.accum
            step = (picking.screen_to_world(region, rv3d, mouse, depth)
                    - picking.screen_to_world(region, rv3d, self.last_mouse, depth))
            self.accum += step * (prefs.value("precision") if event.shift else 1.0)
            self.last_mouse = mouse
            self._reapply(context)
            state.STATS["last_move_ms"] = (time.perf_counter() - t0) * 1000.0
            return {'RUNNING_MODAL'}
        if self.edit.kind == "CHAIN" and event.value == 'PRESS' and event.type in RADIUS_KEYS:
            step = 1.0 if event.type in {'WHEELUPMOUSE', 'RIGHT_BRACKET'} else -1.0
            rp = max(0.0, min(500.0, self.edit.radius_past + step))
            rf = max(0.0, min(500.0, self.edit.radius_future + step))
            self._store_radii(rp, rf)
            self.edit.set_radii(rp, rf)           # samples the new window (frame stepping), re-applies the drag
            self._reapply(context)
            return {'RUNNING_MODAL'}
        if self.edit.kind == "GRAB" and event.value == 'PRESS' and event.type in RADIUS_KEYS:
            # both sides move by the same step (linked radii stay equal, unlinked keep their difference)
            step = 1.0 if event.type in {'WHEELUPMOUSE', 'RIGHT_BRACKET'} else -1.0
            self.edit.radius_past = max(0.0, min(500.0, self.edit.radius_past + step))
            self.edit.radius_future = max(0.0, min(500.0, self.edit.radius_future + step))
            self._store_radii(self.edit.radius_past, self.edit.radius_future)
            self._reapply(context)
            return {'RUNNING_MODAL'}
        if self.edit.kind == "ARC" and event.type == 'B' and event.value == 'PRESS':
            self.edit.break_tangent = not self.edit.break_tangent
            self._reapply(context)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE' or (
                event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
            if self.edit.kind in {"GRAB", "ARC", "CHAIN"} and self.accum.length == 0.0:
                self.edit.restore()                 # a click without a drag writes nothing
                self._end(context, cancel=True)
                return {'CANCELLED'}
            self._end(context, cancel=False)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.edit.restore()
            if self.edit.kind == "RETIME" and context.scene.frame_current != self.frame:
                context.scene.frame_set(self.frame)
            self._end(context, cancel=True)
            return {'CANCELLED'}
        if event.value == 'PRESS' and event.type not in PASSIVE_KEYS:
            # a lost mouse release must never leave the gesture (and the trail engine) hanging:
            # any other key confirms the gesture and is passed on (e.g. I still inserts keys)
            if self.edit.kind in {"GRAB", "ARC", "CHAIN"} and self.accum.length == 0.0:
                self.edit.restore()                 # nothing was dragged: nothing is written
                self._end(context, cancel=True)
                return {'CANCELLED', 'PASS_THROUGH'}
            self._end(context, cancel=False)
            return {'FINISHED', 'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _modal_smooth(self, context, event):
        if event.type == 'MOUSEMOVE':
            t0 = time.perf_counter()
            self._move_smooth(context, event)
            state.STATS["last_move_ms"] = (time.perf_counter() - t0) * 1000.0
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.edit.passes == 0:
                self.edit.restore()
                self._end(context, cancel=True)
                return {'CANCELLED'}
            self._end(context, cancel=False)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.edit.restore()
            self._end(context, cancel=True)
            return {'CANCELLED'}
        if event.value == 'PRESS' and event.type not in PASSIVE_KEYS:     # a lost release never hangs the brush
            if self.edit.passes == 0:
                self.edit.restore()
                self._end(context, cancel=True)
                return {'CANCELLED', 'PASS_THROUGH'}
            self._end(context, cancel=False)
            return {'FINISHED', 'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def _end(self, context, cancel):
        state.GESTURE = None
        context.area.header_text_set(None)
        context.area.tag_redraw()
        # cancel restored the F-Curves bit for bit: the cached trail is still the truth. Timing gestures
        # change every channel of the scope, so every trail is recomputed.
        if not cancel and self.edit.kind == "CHAIN":
            try:
                self.edit.finish()              # skin follow-up / aim stages, measured on the rig
            except Exception as exc:            # never leave half a gesture (nor the trail engine) behind
                print(f"[Animation Sculptor] gesture finish failed: {exc}")
                self.edit.restore()
                cancel = True
                self.report({'WARNING'}, f"Animation Sculptor: o gesto foi desfeito ({exc})")
        timing = self.edit.kind in {"RETIME", "SPACING", "CHAIN", "SMOOTH"}     # several bones change
        provider.resume(keys=[] if cancel else (None if timing else [(self.obj_name, self.bone)]))
        if not cancel:
            # recompute the edited trail now instead of waiting for the engine's timer
            t0 = time.perf_counter()
            provider.update_now()
            state.STATS["refresh_ms"] = (time.perf_counter() - t0) * 1000.0


class ASC_OT_time_window(bpy.types.Operator):
    """Drag an end of the time ruler: radius of the gesture window before (red) / after (green) the frame"""
    bl_idname = "asc.time_window"
    bl_label = "Janela de tempo"
    bl_options = {'REGISTER', 'UNDO'}

    side: EnumProperty(items=(('PAST', "Passado", ""), ('FUTURE', "Futuro", "")), default='FUTURE',
                       options={'SKIP_SAVE'})
    shift: BoolProperty(name="Os dois lados", default=False, options={'SKIP_SAVE'},
                        description="Edita passado e futuro juntos (Shift)")
    radius: FloatProperty(name="Raio", min=0.0, max=500.0, default=0.0, options={'SKIP_SAVE'})

    def _set(self, settings, radius, both):
        if both or settings.radius_linked:
            linked = settings.radius_linked
            settings.radius_linked = False
            settings.radius_past = radius
            settings.radius_future = radius
            settings.radius_linked = linked
        elif self.side == 'PAST':
            settings.radius_past = radius
        else:
            settings.radius_future = radius

    def execute(self, context):
        settings = _settings()
        if settings is None:
            return {'CANCELLED'}
        self._set(settings, self.radius, self.shift)
        return {'FINISHED'}

    def invoke(self, context, event):
        settings = _settings()
        lay = hud.current_layout(context)
        if settings is None or lay is None or context.area is None:
            return {'CANCELLED'}
        self.before = (settings.radius_past, settings.radius_future, settings.radius_linked)
        state.RULER_SPAN = lay.half_span            # the scale stays put while the handle moves
        state.RULER_DRAG = self.side
        state.RULER_HOVER = None
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _header(self, context):
        s = _settings()
        context.area.header_text_set(
            f"Janela de tempo   passado {s.radius_past:g} · futuro {s.radius_future:g} frames"
            f"{' (ligados)' if s.radius_linked else ''}   Shift: os dois lados · Esc/RMB: cancelar · soltar: confirmar")

    def modal(self, context, event):
        settings = _settings()
        if event.type == 'MOUSEMOVE':
            self._follow(context, event, settings)
            return {'RUNNING_MODAL'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'RELEASE' or (
                event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS'):
            if event.type == 'LEFTMOUSE':
                self._follow(context, event, settings)    # the release position counts (moves may coalesce)
            self._end(context)
            return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            past, future, linked = self.before
            settings.radius_linked = False
            settings.radius_past, settings.radius_future = past, future
            settings.radius_linked = linked
            self._end(context)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _follow(self, context, event, settings):
        lay = hud.current_layout(context)
        if lay is not None:
            self.radius = ruler.radius_from_x(lay, self.side, event.mouse_region_x)
            self._set(settings, self.radius, event.shift or self.shift)
            self._header(context)
            context.area.tag_redraw()

    def _end(self, context):
        state.RULER_DRAG = None
        state.RULER_SPAN = 0
        context.area.header_text_set(None)
        context.area.tag_redraw()


def _draw_settings(context, layout, tool):
    """Tool settings bar (top of the viewport, View › Tool Settings): the gesture window."""
    s = props.get(context)
    if s is None:
        return
    row = layout.row(align=True)
    row.prop(s, "radius_past", text="Passado")
    row.prop(s, "radius_linked", text="", icon='LINKED' if s.radius_linked else 'UNLINKED')
    row.prop(s, "radius_future", text="Futuro")
    layout.prop(s, "falloff", text="")
    if tool is not None and tool.idname == TOOL_SMOOTH:
        layout.prop(s, "smooth_strength", text="Força")
    elif tool is not None and tool.idname in (TOOL_ID, TOOL_BODY):
        layout.prop(s, "tip_orientation", text="")


class _SculptTool:
    """Common to the Animation Sculptor tools (left toolbar, Pose Mode): same gizmo group and operator;
    the tool sets the gesture's scope (ADR 0013, docs/design/sculpt-ux.md)."""
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'POSE'
    bl_widget = gizmo.ASC_GGT_trails.bl_idname
    # clicks that miss the body / the trail keep the usual bone selection
    bl_keymap = (
        ("view3d.select", {"type": 'LEFTMOUSE', "value": 'CLICK'}, {"properties": [("deselect_all", True)]}),
        ("view3d.select", {"type": 'LEFTMOUSE', "value": 'CLICK', "shift": True}, {"properties": [("toggle", True)]}),
        ("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
    )
    draw_settings = staticmethod(_draw_settings)


class ASC_WT_tip(_SculptTool, bpy.types.WorkSpaceTool):
    bl_idname = TOOL_TIP
    bl_label = "Ponta"
    bl_description = ("Arraste uma parte do corpo: só aquela parte gira para seguir o mouse (keys em todo frame "
                      "da janela da régua). Num membro em IK, move o controle IK")
    bl_icon = "ops.pose.relax"


class ASC_WT_sculpt(_SculptTool, bpy.types.WorkSpaceTool):
    bl_idname = TOOL_ID
    bl_label = "Membro"
    bl_description = ("Arraste uma parte do corpo: o membro inteiro até ela (braço, perna) gira para seguir o "
                      "mouse. Num membro em IK, move o controle IK")
    bl_icon = "ops.pose.breakdowner"


class ASC_WT_body(_SculptTool, bpy.types.WorkSpaceTool):
    bl_idname = TOOL_BODY
    bl_label = "Corpo"
    bl_description = ("Arraste o tronco, o pescoço ou a cabeça: a coluna inclina para seguir o mouse e os pés "
                      "ficam no lugar")
    bl_icon = "ops.pose.push"


class ASC_WT_smooth(_SculptTool, bpy.types.WorkSpaceTool):
    bl_idname = TOOL_SMOOTH
    bl_label = "Smooth"
    bl_description = "Pincel: arraste sobre uma parte do corpo para suavizar o movimento dela na janela da régua"
    bl_icon = "ops.gpencil.sculpt_blur"


TOOLS = (ASC_WT_tip, ASC_WT_sculpt, ASC_WT_body, ASC_WT_smooth)


class ASC_OT_activate_tool(bpy.types.Operator):
    """Ativa a última ferramenta do Animation Sculptor usada (Membro na primeira vez)"""
    bl_idname = "asc.activate_tool"
    bl_label = "Animation Sculptor: ferramenta"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE'

    def execute(self, context):
        tool = state.LAST_TOOL if state.LAST_TOOL in TOOL_IDS else TOOL_ID
        return bpy.ops.wm.tool_set_by_id(name=tool)


classes = (ASC_OT_sculpt_gesture, ASC_OT_time_window, ASC_OT_activate_tool)
TOOL_HOTKEY = {"type": 'K', "value": 'PRESS', "shift": True, "alt": True}   # free in the default keymap (5.2)
_keymaps = []


def _register_keymap():
    """Shift+Alt+K in Pose Mode activates the last used tool (editable in Preferences › Keymap › Pose)."""
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:          # background mode
        return
    km = kc.keymaps.new(name="Pose", space_type='EMPTY')
    kmi = km.keymap_items.new("asc.activate_tool", **TOOL_HOTKEY)
    _keymaps.append((km, kmi))


def _unregister_keymap():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    previous = None
    for tool in TOOLS:
        if previous is None:
            bpy.utils.register_tool(tool, after={"builtin.transform"}, separator=True, group=False)
        else:
            bpy.utils.register_tool(tool, after={previous}, group=False)
        previous = tool.bl_idname
    _register_keymap()


def unregister():
    _unregister_keymap()
    try:
        for tool in reversed(TOOLS):
            bpy.utils.unregister_tool(tool)
    except Exception as exc:
        print(f"[Animation Sculptor] unregister_tool: {exc}")
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

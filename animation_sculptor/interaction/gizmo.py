# SPDX-License-Identifier: GPL-3.0-or-later
"""Hover/picking on the trails through a Python gizmo (ADR 0010).

The gizmo has no geometry of its own: ``test_select`` hit-tests the trail points in screen space and
reports a hit, which makes Blender highlight it; clicking the highlighted gizmo runs the gesture
operator (``target_set_operator``). Drawing of the hover ring lives in ``overlay.py``.
"""

import bpy

from ..trails import provider
from . import body_pick, hud, picking, state

GESTURE_OPERATOR = "asc.sculpt_gesture"


def candidate_keys(context):
    """Trails that can be picked: the ones of the active armature in Pose Mode."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'POSE':
        return []
    return [key for key in provider.targets() if key[0] == ob.name and key[1]]


def _mode(context):
    from ..ui import props

    settings = props.get(context)
    return settings.interaction_mode if settings is not None else 'TRAIL'


def body_hit(context, location):
    """Modo Corpo: the body spot under the mouse, mapped to the control that moves it (ADR 0013)."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'POSE':
        return None
    spot = body_pick.pick(context, context.region, context.region_data, location, ob)
    if spot is None:
        return None
    from .. import rig
    from ..anim import action_io

    control, kind, reason = rig.get_adapter(ob).control_for_deform(ob, spot.deform)
    frame = context.scene.frame_current
    pb = ob.pose.bones.get(control) if control else None
    return picking.Hit(obj_name=ob.name, bone=control or spot.deform, frame=frame,
                       is_key=bool(pb is not None and action_io.bone_has_key(ob, pb, frame)), world=spot.world,
                       screen=(float(location[0]), float(location[1])), distance=0.0, on_body=True,
                       deform=spot.deform, kind=kind or "", mesh=spot.mesh, reason=reason)


def draggable_bones(context):
    """Selected pose bones whose tail can be dragged directly: rotation-only controls, and in the Corpo
    scope the controls the adapter turns the body with (``body_override``)."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'POSE':
        return []
    from .. import rig
    from ..ui import props

    from .sculpt_tool import TOOL_SCOPES, active_tool_id

    settings = props.get(context)
    scope = TOOL_SCOPES.get(active_tool_id(context)) or (settings.ephemeral_scope if settings is not None else None)
    body = scope == rig.BODY
    adapter = rig.get_adapter(ob)
    out = []
    for pb in ob.pose.bones:
        if not pb.select:
            continue
        info = adapter.classify(ob, pb.name)
        if info is None or not info.rotates:
            continue
        if not info.translates or (body and adapter.body_override(ob, pb.name)):
            out.append(pb.name)
    return out


def _header(context, hit):
    area = context.area
    if area is None:
        return
    if hit is None:
        area.header_text_set(None)
        return
    if hit.on_body:
        if hit.reason:
            area.header_text_set(f"Animation Sculptor · {hit.deform} · {hit.reason}")
            return
        what = "grab/arco do controle IK" if hit.kind == "IK" else "gira a cadeia (keys em todo frame da janela)"
        area.header_text_set(f"Animation Sculptor · {hit.deform} → {hit.bone} · frame {hit.frame}   "
                             f"LMB arrastar: {what}")
        return
    if hit.on_bone:
        area.header_text_set(f"Animation Sculptor · {hit.bone} · ponta do bone, frame {hit.frame}   "
                             "LMB arrastar: girar a cadeia (janela da régua)")
        return
    kind = "key" if hit.is_key else "in-between"
    area.header_text_set(
        f"Animation Sculptor · {hit.bone} · frame {hit.frame} ({kind})   "
        "LMB arrastar: espaço · Ctrl+LMB: tempo"
    )


class ASC_GT_trail_points(bpy.types.Gizmo):
    bl_idname = "ASC_GT_trail_points"

    def setup(self):
        self.use_draw_modal = False
        self.use_draw_hover = False

    def test_select(self, context, location):
        if state.GESTURE is not None or state.RULER_DRAG is not None:
            return -1
        # the time ruler comes first: its end handles sit over the viewport, maybe over a trail
        try:
            side = hud.hit(context, location)
        except Exception as exc:
            print(f"[Animation Sculptor] ruler picking failed: {exc}")
            side = None
        left_ruler = state.RULER_HOVER is not None and side is None
        if side != state.RULER_HOVER:
            state.RULER_HOVER = side
            context.area.tag_redraw()
        if side is not None:
            if state.HOVER is not None:
                state.HOVER = None
            context.area.header_text_set(
                f"Animation Sculptor · régua de tempo: raio do {'passado' if side == 'PAST' else 'futuro'}   "
                "LMB arrastar: mudar · Shift: os dois lados")
            return 0
        try:
            if _mode(context) == 'BODY':
                hit = body_hit(context, location)
            else:
                hit = picking.hit_test(context.region, context.region_data, location, candidate_keys(context))
            if hit is None:     # nothing else: the tail of a selected bone the ephemeral gesture can turn
                ob = context.active_object
                hit = picking.bone_tip_hit(context.region, context.region_data, location, ob,
                                           draggable_bones(context), context.scene.frame_current)
        except Exception as exc:  # never break the viewport event loop
            print(f"[Animation Sculptor] picking failed: {exc}")
            hit = None
        if hit != state.HOVER or left_ruler:
            state.HOVER = hit
            refusal = state.REFUSAL
            if refusal is not None and (hit is None or (hit.bone, hit.frame) != (refusal["bone"], refusal["frame"])):
                state.REFUSAL = None
            _header(context, hit)
            context.area.tag_redraw()
        return -1 if hit is None else 0

    def draw(self, context):
        pass  # overlay.py draws the hover ring (2D, pixel sized)


def _tool_active(context) -> bool:
    from .sculpt_tool import TOOL_IDS

    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return False
    return tool is not None and tool.idname in TOOL_IDS


class ASC_GGT_trails(bpy.types.GizmoGroup):
    bl_idname = "ASC_GGT_trails"
    bl_label = "Animation Sculptor Trails"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE' and _tool_active(context)

    def setup(self, context):
        gz = self.gizmos.new(ASC_GT_trail_points.bl_idname)
        gz.target_set_operator(GESTURE_OPERATOR)
        self.points = gz
        # The tool shows the trails; ID properties cannot be written from a draw/refresh context.
        scene_name = context.scene.name

        def enable_trails():
            scene = bpy.data.scenes.get(scene_name)
            if scene is not None:
                sculpt_settings = getattr(scene, "asc_sculpt", None)
                if sculpt_settings is None or sculpt_settings.interaction_mode == 'TRAIL':
                    provider.set_enabled(scene, True)     # the Corpo mode keeps the viewport clean
                sculpt = getattr(scene, "asc_sculpt", None)
                if sculpt is not None and not sculpt.palette_applied:   # once per scene: user colours win after
                    provider.apply_palette(scene)
                    sculpt.palette_applied = True
            return None

        bpy.app.timers.register(enable_trails, first_interval=0.0)


classes = (ASC_GT_trail_points, ASC_GGT_trails)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    state.reset()

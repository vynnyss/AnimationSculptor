# SPDX-License-Identifier: GPL-3.0-or-later
"""Hover/picking on the trails through a Python gizmo (ADR 0010).

The gizmo has no geometry of its own: ``test_select`` hit-tests the trail points in screen space and
reports a hit, which makes Blender highlight it; clicking the highlighted gizmo runs the gesture
operator (``target_set_operator``). Drawing of the hover ring lives in ``overlay.py``.
"""

import bpy

from ..trails import provider
from . import picking, state

GESTURE_OPERATOR = "asc.sculpt_gesture"


def candidate_keys(context):
    """Trails that can be picked: the ones of the active armature in Pose Mode."""
    ob = context.active_object
    if ob is None or ob.type != 'ARMATURE' or ob.mode != 'POSE':
        return []
    return [key for key in provider.targets() if key[0] == ob.name and key[1]]


def _header(context, hit):
    area = context.area
    if area is None:
        return
    if hit is None:
        area.header_text_set(None)
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
        if state.GESTURE is not None:
            return -1
        try:
            hit = picking.hit_test(context.region, context.region_data, location, candidate_keys(context))
        except Exception as exc:  # never break the viewport event loop
            print(f"[Animation Sculptor] picking failed: {exc}")
            hit = None
        if hit != state.HOVER:
            state.HOVER = hit
            _header(context, hit)
            context.area.tag_redraw()
        return -1 if hit is None else 0

    def draw(self, context):
        pass  # overlay.py draws the hover ring (2D, pixel sized)


def _tool_active(context) -> bool:
    from .sculpt_tool import TOOL_ID

    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except Exception:
        return False
    return tool is not None and tool.idname == TOOL_ID


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
                provider.set_enabled(scene, True)
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

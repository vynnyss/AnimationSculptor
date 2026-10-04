# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (3D Viewport › N › Animation Sculptor)."""

import bpy

CATEGORY = "Animation Sculptor"


class ASC_PT_main(bpy.types.Panel):
    bl_idname = "ASC_PT_main"
    bl_label = "Animation Sculptor"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY

    def draw(self, context):
        layout = self.layout
        ob = context.active_object
        col = layout.column(align=True)
        if ob is None or ob.type != 'ARMATURE':
            col.label(text="Selecione uma armature", icon='INFO')
        elif ob.mode != 'POSE':
            col.label(text="Entre em Pose Mode", icon='INFO')
        else:
            col.label(text=f"Rig: {ob.name}", icon='ARMATURE_DATA')
        trails = getattr(context.scene, "asc_trails", None)
        if trails is not None:
            row = layout.row(align=True)
            row.scale_y = 1.2
            row.prop(trails, "enabled", text="Mostrar trails", toggle=True,
                     icon='IPO_BEZIER' if trails.enabled else 'CURVE_PATH')


classes = (ASC_PT_main,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

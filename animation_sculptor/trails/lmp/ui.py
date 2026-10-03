# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (ui.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""Panels, lists and header/overlay integration."""

import bpy

from . import engine
from .engine import CACHE, STATE

# ASC-PATCH P5: the panels live in the Animation Sculptor sidebar tab, nested under its main panel.
# No preferences of their own, no header button, no entries in the Overlays popover.
DEFAULT_CATEGORY = "Animation Sculptor"
PARENT_PANEL = "ASC_PT_main"


# ---------------------------------------------------------------------------
# Pinned list
# ---------------------------------------------------------------------------

class ASC_TR_UL_pinned(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        ob = item.obj
        row = layout.row(align=True)
        if ob is None:
            row.label(text="<missing object>", icon='ERROR')
            return
        icon = 'OBJECT_DATA'
        if ob.type == 'ARMATURE':
            icon = 'BONE_DATA' if item.bone else 'ARMATURE_DATA'
        elif ob.type == 'MESH':
            icon = 'MESH_DATA'
        elif ob.type == 'CAMERA':
            icon = 'CAMERA_DATA'
        elif ob.type == 'EMPTY':
            icon = 'EMPTY_DATA'
        elif ob.type == 'LIGHT':
            icon = 'LIGHT_DATA'
        text = ob.name if not item.bone else "%s : %s" % (ob.name, item.bone)
        row.label(text=text, icon=icon)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = DEFAULT_CATEGORY


class ASC_TR_PT_main(_Base, bpy.types.Panel):
    bl_label = "Trails"  # ASC-PATCH P5
    bl_idname = "ASC_TR_PT_main"
    bl_parent_id = PARENT_PANEL  # ASC-PATCH P5

    def draw_header(self, context):
        s = context.scene.asc_trails
        self.layout.prop(s, "enabled", text="")

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled

        row = layout.row(align=True)
        row.prop(s, "target_mode", expand=True)

        if s.target_mode == 'PINNED':
            row = layout.row()
            row.template_list("ASC_TR_UL_pinned", "", s, "pinned", s, "pinned_index", rows=3)
            col = row.column(align=True)
            col.operator("asc_trails.pin_add", text="", icon='ADD')
            col.operator("asc_trails.pin_remove", text="", icon='REMOVE')
            col.separator()
            col.operator("asc_trails.pin_select", text="", icon='RESTRICT_SELECT_OFF')
            col.operator("asc_trails.pin_clear", text="", icon='TRASH')
        else:
            layout.operator("asc_trails.pin_add", text="Pin Selection", icon='PINNED')

        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("asc_trails.refresh", icon='FILE_REFRESH')
        row.operator("asc_trails.bake", text="Bake", icon='RENDER_ANIMATION')
        row.operator("asc_trails.clear_cache", text="", icon='TRASH')

        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(s, "live_update")
        sub = col.column(align=True)
        sub.active = s.live_update
        sub.prop(s, "update_delay")
        col.prop(s, "eval_mode")

        if s.show_stats:
            box = layout.box()
            col = box.column(align=True)
            n_targets = len(STATE.targets)
            n_ghosts = 0
            n_paths = 0
            errors = []
            for t in STATE.targets:
                c = CACHE.get(t.key)
                if c is None:
                    continue
                n_ghosts += len(c.onion)
                if c.path_points is not None:
                    n_paths += 1
                if c.onion_error and t.want_onion:
                    errors.append("%s: %s" % (t.obj_name, c.onion_error))
            info = "%d target(s), %d path(s), %d cached ghost(s)" % (n_targets, n_paths, n_ghosts)
            col.label(text=info, icon='INFO')
            if STATE.last_engine_info:
                col.label(text="Last update: %.0f ms (%s)" % (STATE.last_compute_ms, STATE.last_engine_info), icon='TIME')
            if STATE.job is not None and STATE.job.remaining:
                col.label(text="Evaluating... %d frame(s) left" % STATE.job.remaining, icon='SORTTIME')
            for e in errors[:4]:
                col.label(text=e, icon='ERROR')
            if getattr(STATE, "path_clamped", False):
                col.label(text="Path range clamped to %d frames" % engine.MAX_PATH_FRAMES, icon='INFO')
            if STATE.shaded_shader_failed and s.onion_shading == 'SHADED':
                col.label(text="Shaded ghosts unavailable on this GPU backend (flat used)", icon='ERROR')


class ASC_TR_PT_path(_Base, bpy.types.Panel):
    bl_label = "Motion Path"
    bl_idname = "ASC_TR_PT_path"
    bl_parent_id = "ASC_TR_PT_main"

    def draw_header(self, context):
        s = context.scene.asc_trails
        self.layout.prop(s, "path_show", text="")

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.path_show
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(s, "path_range_mode")
        if s.path_range_mode == 'AROUND':
            col.prop(s, "path_before")
            col.prop(s, "path_after")
        elif s.path_range_mode == 'CUSTOM':
            col.prop(s, "path_start")
            col.prop(s, "path_end")
            col.operator("asc_trails.range_from_scene", icon='PREVIEW_RANGE')
        col.prop(s, "path_step")
        row = layout.row(align=True, heading="Show")
        row.prop(s, "path_show_past", toggle=True)
        row.prop(s, "path_show_future", toggle=True)
        col = layout.column(align=True)
        col.prop(s, "path_bone_point")
        col.prop(s, "path_engine")


class ASC_TR_PT_path_style(_Base, bpy.types.Panel):
    bl_label = "Appearance"
    bl_idname = "ASC_TR_PT_path_style"
    bl_parent_id = "ASC_TR_PT_path"

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.path_show
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "path_line_width")
        col.prop(s, "path_alpha")
        col.prop(s, "path_fade")
        col = layout.column(align=True)
        col.prop(s, "path_color_mode")
        mode = s.path_color_mode
        if mode == 'SINGLE':
            col.prop(s, "path_color")
        elif mode == 'GRADIENT':
            col.prop(s, "path_color_start")
            col.prop(s, "path_color_end")
        elif mode == 'SPEED':
            col.prop(s, "path_color_slow")
            col.prop(s, "path_color_fast")
        else:
            col.prop(s, "path_color_past")
            col.prop(s, "path_color_future")
        layout.prop(s, "path_xray")


class ASC_TR_PT_path_markers(_Base, bpy.types.Panel):
    bl_label = "Points, Keyframes & Numbers"
    bl_idname = "ASC_TR_PT_path_markers"
    bl_parent_id = "ASC_TR_PT_path"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.path_show
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(s, "path_show_points")
        sub = col.column(align=True)
        sub.active = s.path_show_points
        sub.prop(s, "path_point_size")

        col = layout.column(align=True)
        col.prop(s, "path_show_keyframes")
        sub = col.column(align=True)
        sub.active = s.path_show_keyframes
        sub.prop(s, "path_keyframe_shape", text="Shape")
        sub.prop(s, "path_keyframe_size", text="Size")
        sub.prop(s, "path_keyframe_color", text="Color")

        col = layout.column(align=True)
        col.prop(s, "path_show_current")
        sub = col.column(align=True)
        sub.active = s.path_show_current
        sub.prop(s, "path_current_size", text="Size")
        sub.prop(s, "path_current_color", text="Color")

        col = layout.column(align=True)
        col.prop(s, "path_show_numbers")
        sub = col.column(align=True)
        sub.active = s.path_show_numbers
        sub.prop(s, "path_number_step")
        sub.prop(s, "path_numbers_keyframes")
        sub.prop(s, "path_number_size")
        sub.prop(s, "path_number_offset")
        sub.prop(s, "path_number_color")


class ASC_TR_PT_onion(_Base, bpy.types.Panel):
    bl_label = "Onion Skin"
    bl_idname = "ASC_TR_PT_onion"
    bl_parent_id = "ASC_TR_PT_main"

    def draw_header(self, context):
        s = context.scene.asc_trails
        self.layout.prop(s, "onion_show", text="")

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.onion_show
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "onion_mode")
        col.prop(s, "onion_before")
        col.prop(s, "onion_after")
        col.prop(s, "onion_step")
        col = layout.column(align=True)
        col.prop(s, "onion_clamp_range")
        col.prop(s, "onion_show_current")


class ASC_TR_PT_onion_style(_Base, bpy.types.Panel):
    bl_label = "Appearance"
    bl_idname = "ASC_TR_PT_onion_style"
    bl_parent_id = "ASC_TR_PT_onion"

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.onion_show
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(s, "onion_opacity")
        col.prop(s, "onion_falloff")

        col = layout.column(align=True)
        col.prop(s, "onion_color_mode")
        mode = s.onion_color_mode
        if mode == 'SINGLE':
            col.prop(s, "onion_color")
        elif mode == 'GRADIENT':
            col.prop(s, "onion_color_near")
            col.prop(s, "onion_color_far")
        else:
            col.prop(s, "onion_color_before")
            col.prop(s, "onion_color_after")

        col = layout.column(align=True)
        col.prop(s, "onion_draw_type")
        sub = col.column(align=True)
        sub.active = s.onion_draw_type != 'WIRE'
        sub.prop(s, "onion_shading")
        if s.onion_shading == 'SHADED':
            sub.prop(s, "onion_light_strength")
            sub.prop(s, "onion_rim")
        sub = col.column(align=True)
        sub.active = s.onion_draw_type != 'SOLID'
        sub.prop(s, "onion_wire_width")
        sub.prop(s, "onion_wire_opacity")

        col = layout.column(align=True)
        col.prop(s, "onion_xray")
        col.prop(s, "onion_backface_culling")
        col.prop(s, "onion_depth_write")


class ASC_TR_PT_onion_eval(_Base, bpy.types.Panel):
    bl_label = "Evaluation"
    bl_idname = "ASC_TR_PT_onion_eval"
    bl_parent_id = "ASC_TR_PT_onion"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled and s.onion_show
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "onion_use_modifiers")
        col.prop(s, "onion_include_armature_meshes")
        col.prop(s, "onion_vertex_limit")
        col.prop(s, "cache_max_frames")
        layout.operator("asc_trails.bake", icon='RENDER_ANIMATION')


class ASC_TR_PT_advanced(_Base, bpy.types.Panel):
    bl_label = "Performance & Playback"
    bl_idname = "ASC_TR_PT_advanced"
    bl_parent_id = "ASC_TR_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.asc_trails
        layout.active = s.enabled
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(s, "compute_budget")
        col.prop(s, "pause_on_playback")
        col.prop(s, "hide_onion_on_playback")
        col.prop(s, "hide_path_on_playback")
        col = layout.column(align=True)
        col.prop(s, "respect_overlays")
        col.prop(s, "show_stats")
        layout.operator("asc_trails.reset_settings", icon='LOOP_BACK')


# ---------------------------------------------------------------------------

panel_classes = (
    ASC_TR_PT_main,
    ASC_TR_PT_path,
    ASC_TR_PT_path_style,
    ASC_TR_PT_path_markers,
    ASC_TR_PT_onion,
    ASC_TR_PT_onion_style,
    ASC_TR_PT_onion_eval,
    ASC_TR_PT_advanced,
)

classes = (ASC_TR_UL_pinned,) + panel_classes

# ASC-PATCH P5: header button, Overlays popover entries and the movable sidebar tab were removed.


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

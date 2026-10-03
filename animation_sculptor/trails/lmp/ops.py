# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (ops.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""Operators for the Live Motion Path & Onion Skin add-on."""

import time

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty

from . import compat, engine


class ASC_TR_OT_toggle(bpy.types.Operator):
    """Toggle the live motion path and onion skin overlay"""
    bl_idname = "asc_trails.toggle"
    bl_label = "Toggle Live Motion Path & Onion Skin"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.asc_trails
        s.enabled = not s.enabled
        return {'FINISHED'}


class ASC_TR_OT_refresh(bpy.types.Operator):
    """Recompute the motion paths and onion skins of all targets now"""
    bl_idname = "asc_trails.refresh"
    bl_label = "Refresh"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.asc_trails
        if not s.enabled:
            s.enabled = True
        t0 = time.perf_counter()
        engine.refresh_now()
        dt = (time.perf_counter() - t0) * 1000.0
        n = len(engine.STATE.targets)
        self.report({'INFO'}, "Live Motion Onion: %d target(s) updated in %.0f ms" % (n, dt))
        return {'FINISHED'}


class ASC_TR_OT_clear_cache(bpy.types.Operator):
    """Free all cached ghosts and paths (they are rebuilt on the next update)"""
    bl_idname = "asc_trails.clear_cache"
    bl_label = "Clear Cache"
    bl_options = {'REGISTER'}

    def execute(self, context):
        engine.clear_all()
        engine.schedule(delay=0.0)
        return {'FINISHED'}


class ASC_TR_OT_bake(bpy.types.Operator):
    """Pre-compute onion skins for a whole frame range so scrubbing and playback never wait"""
    bl_idname = "asc_trails.bake"
    bl_label = "Bake Onion Range"
    bl_options = {'REGISTER'}

    range_mode: EnumProperty(
        name="Range",
        items=(
            ('SCENE', "Scene Range", "Scene / preview frame range"),
            ('PATH', "Path Range", "Same range as the motion path"),
        ),
        default='SCENE',
    )

    def execute(self, context):
        scene = context.scene
        s = scene.asc_trails
        if not s.enabled:
            s.enabled = True
        if self.range_mode == 'PATH':
            lo, hi = engine.path_display_range(scene, s)
        else:
            lo, hi = engine.scene_frame_range(scene)
        frames = list(range(int(lo), int(hi) + 1))
        if len(frames) > s.cache_max_frames:
            s.cache_max_frames = len(frames)
        wm = context.window_manager
        t0 = time.perf_counter()
        try:
            wm.progress_begin(0, 100)
            n = engine.bake_frames(scene, frames)
        finally:
            wm.progress_end()
        dt = time.perf_counter() - t0
        self.report({'INFO'}, "Baked %d frame(s) in %.1f s" % (n, dt))
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


# ---------------------------------------------------------------------------
# Pinned targets
# ---------------------------------------------------------------------------

class ASC_TR_OT_pin_add(bpy.types.Operator):
    """Pin the selected objects (or selected pose bones in Pose Mode) as targets"""
    bl_idname = "asc_trails.pin_add"
    bl_label = "Pin Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.asc_trails
        existing = {(it.obj.name if it.obj else "", it.bone) for it in s.pinned}
        added = 0

        def add(ob, bone=""):
            nonlocal added
            key = (ob.name, bone)
            if key in existing:
                return
            item = s.pinned.add()
            item.obj = ob
            item.bone = bone
            existing.add(key)
            added += 1

        ob = context.active_object
        if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'POSE':
            for pb in ob.pose.bones:
                if compat.pose_bone_selected(pb):
                    add(ob, pb.name)
            if added == 0:
                add(ob)
        else:
            for o in context.selected_objects:
                add(o)
            if added == 0 and ob is not None:
                add(ob)
        if added:
            s.pinned_index = len(s.pinned) - 1
            s.target_mode = 'PINNED'
        engine.targets_changed()
        self.report({'INFO'}, "Pinned %d target(s)" % added)
        return {'FINISHED'}


class ASC_TR_OT_pin_remove(bpy.types.Operator):
    """Remove the highlighted pinned target"""
    bl_idname = "asc_trails.pin_remove"
    bl_label = "Unpin"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.asc_trails
        if 0 <= s.pinned_index < len(s.pinned):
            s.pinned.remove(s.pinned_index)
            s.pinned_index = min(s.pinned_index, max(0, len(s.pinned) - 1))
        engine.targets_changed()
        return {'FINISHED'}


class ASC_TR_OT_pin_clear(bpy.types.Operator):
    """Remove all pinned targets"""
    bl_idname = "asc_trails.pin_clear"
    bl_label = "Clear Pins"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.asc_trails
        s.pinned.clear()
        s.pinned_index = 0
        engine.targets_changed()
        return {'FINISHED'}


class ASC_TR_OT_pin_select(bpy.types.Operator):
    """Select the highlighted pinned object in the viewport"""
    bl_idname = "asc_trails.pin_select"
    bl_label = "Select Pinned"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.asc_trails
        if not (0 <= s.pinned_index < len(s.pinned)):
            return {'CANCELLED'}
        ob = s.pinned[s.pinned_index].obj
        if ob is None:
            return {'CANCELLED'}
        try:
            for o in context.selected_objects:
                o.select_set(False)
            ob.select_set(True)
            context.view_layer.objects.active = ob
        except Exception:
            return {'CANCELLED'}
        return {'FINISHED'}


class ASC_TR_OT_reset_settings(bpy.types.Operator):
    """Reset every motion path / onion skin setting of this scene to its default value"""
    bl_idname = "asc_trails.reset_settings"
    bl_label = "Reset Settings"
    bl_options = {'REGISTER', 'UNDO'}

    keep_targets: BoolProperty(name="Keep Targets & Pins", default=True)

    def execute(self, context):
        s = context.scene.asc_trails
        skip = {"pinned", "pinned_index", "target_mode"} if self.keep_targets else set()
        for prop in s.bl_rna.properties:
            name = prop.identifier
            if name in ("rna_type", "enabled") or name in skip:
                continue
            try:
                s.property_unset(name)
            except Exception:
                pass
        engine.invalidate(path=True, onion=True)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class ASC_TR_OT_set_range_from_scene(bpy.types.Operator):
    """Copy the scene / preview range into the custom path range"""
    bl_idname = "asc_trails.range_from_scene"
    bl_label = "Use Scene Range"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        s = scene.asc_trails
        s.path_start, s.path_end = engine.scene_frame_range(scene)
        return {'FINISHED'}


classes = (
    ASC_TR_OT_toggle,
    ASC_TR_OT_refresh,
    ASC_TR_OT_clear_cache,
    ASC_TR_OT_bake,
    ASC_TR_OT_pin_add,
    ASC_TR_OT_pin_remove,
    ASC_TR_OT_pin_clear,
    ASC_TR_OT_pin_select,
    ASC_TR_OT_reset_settings,
    ASC_TR_OT_set_range_from_scene,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

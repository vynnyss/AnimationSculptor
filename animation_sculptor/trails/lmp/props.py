# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (props.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""Scene-level settings for the Live Motion Path & Onion Skin add-on."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


# ---------------------------------------------------------------------------
# Update callbacks (import engine lazily to avoid circular imports)
# ---------------------------------------------------------------------------

def _upd_redraw(self, context):
    from . import engine
    engine.request_redraw()


def _upd_path(self, context):
    """A setting that changes how the path is *computed* changed."""
    from . import engine
    engine.invalidate(path=True, onion=False)


def _upd_onion(self, context):
    from . import engine
    engine.invalidate(path=False, onion=True)


def _upd_all(self, context):
    from . import engine
    engine.invalidate(path=True, onion=True)


def _upd_enabled(self, context):
    from . import engine
    if self.enabled:
        engine.invalidate(path=True, onion=True)
    else:
        engine.request_redraw()


def _upd_targets(self, context):
    from . import engine
    engine.targets_changed()


# ---------------------------------------------------------------------------
# Pinned targets
# ---------------------------------------------------------------------------

class ASC_TR_PinnedItem(bpy.types.PropertyGroup):
    obj: PointerProperty(
        name="Object",
        type=bpy.types.Object,
        update=_upd_targets,
    )
    bone: StringProperty(
        name="Bone",
        description="Optional pose bone name (armatures only)",
        default="",
        update=_upd_targets,
    )


# ---------------------------------------------------------------------------
# Main settings
# ---------------------------------------------------------------------------

class ASC_TR_Settings(bpy.types.PropertyGroup):
    # --- General -----------------------------------------------------------
    enabled: BoolProperty(
        name="Live Motion Path & Onion Skin",
        description="Master switch for the live motion path and onion skin overlays",
        default=False,
        update=_upd_enabled,
    )
    target_mode: EnumProperty(
        name="Targets",
        description="Which objects / bones get a motion path and onion skin",
        items=(
            ('SELECTED', "Selected", "Selected objects (selected pose bones while in Pose Mode)", 'RESTRICT_SELECT_OFF', 0),
            ('ACTIVE', "Active", "Only the active object (active pose bone while in Pose Mode)", 'OBJECT_DATA', 1),
            ('PINNED', "Pinned", "Only the objects / bones in the pinned list below", 'PINNED', 2),
        ),
        default='SELECTED',
        update=_upd_targets,
    )
    pinned: CollectionProperty(type=ASC_TR_PinnedItem)
    pinned_index: IntProperty(default=0, min=0)

    eval_mode: EnumProperty(
        name="Evaluation",
        description="How the animation is evaluated at other frames",
        items=(
            ('AUTO', "Auto", "F-Curve evaluation for simple transform animation, full depsgraph evaluation when constraints, parents, armatures or deforming modifiers are involved"),
            ('FAST', "F-Curves Only", "Evaluate transform F-Curves directly (very fast, ignores constraints, drivers, NLA, parenting and deformation)"),
            ('FULL', "Full (Depsgraph)", "Evaluate every frame through the dependency graph (exact, slower)"),
        ),
        default='AUTO',
        update=_upd_all,
    )
    live_update: BoolProperty(
        name="Live Update",
        description="Automatically refresh when the animation, selection or frame changes",
        default=True,
        update=_upd_all,
    )
    update_delay: FloatProperty(
        name="Update Delay",
        description="Seconds to wait after the last change before recomputing (prevents recomputing on every mouse move)",
        default=0.12, min=0.0, max=2.0, step=1, precision=2,
    )
    compute_budget: FloatProperty(
        name="Time Slice",
        description="Maximum seconds of evaluation per update tick. Longer ranges are computed progressively over several ticks so the UI stays responsive",
        default=0.25, min=0.02, max=5.0, step=5, precision=2,
    )
    pause_on_playback: BoolProperty(
        name="Pause Evaluation During Playback",
        description="Do not evaluate new frames while the animation is playing (cached frames are still drawn)",
        default=True,
    )
    hide_onion_on_playback: BoolProperty(
        name="Hide Onion Skin During Playback",
        default=True,
        update=_upd_redraw,
    )
    hide_path_on_playback: BoolProperty(
        name="Hide Motion Path During Playback",
        default=False,
        update=_upd_redraw,
    )
    respect_overlays: BoolProperty(
        name="Follow Viewport Overlays Toggle",
        description="Hide everything when the viewport's overlays are switched off",
        default=True,
        update=_upd_redraw,
    )
    cache_max_frames: IntProperty(
        name="Cache Limit",
        description="Maximum number of cached onion skin frames per object (frames farthest from the current frame are dropped first)",
        default=240, min=8, max=4000,
    )
    show_stats: BoolProperty(
        name="Show Statistics",
        description="Show evaluation timing and cache statistics in the panel",
        default=True,
        update=_upd_redraw,
    )

    # --- Motion path -------------------------------------------------------
    path_show: BoolProperty(
        name="Motion Path",
        description="Draw a live motion path for the targets",
        default=True,
        update=_upd_path,
    )
    path_range_mode: EnumProperty(
        name="Range",
        description="Frame range of the motion path",
        items=(
            ('SCENE', "Scene", "Scene frame range (preview range when it is enabled)"),
            ('AROUND', "Around Frame", "A window of frames before and after the current frame"),
            ('CUSTOM', "Custom", "Custom start and end frame"),
        ),
        default='SCENE',
        update=_upd_path,
    )
    path_before: IntProperty(name="Before", description="Frames before the current frame", default=24, min=0, max=10000, update=_upd_path)
    path_after: IntProperty(name="After", description="Frames after the current frame", default=24, min=0, max=10000, update=_upd_path)
    path_start: IntProperty(name="Start", default=1, min=-1048574, max=1048574, update=_upd_path)
    path_end: IntProperty(name="End", default=250, min=-1048574, max=1048574, update=_upd_path)
    path_step: IntProperty(
        name="Step",
        description="Only evaluate every Nth frame (1 = every frame)",
        default=1, min=1, max=50, update=_upd_path,
    )
    path_engine: EnumProperty(
        name="Path Engine",
        description="Which method computes the path when full evaluation is needed",
        items=(
            ('AUTO', "Auto", "F-Curves when possible, otherwise Blender's native motion-path solver, falling back to frame stepping"),
            ('FCURVE', "F-Curves", "Evaluate transform F-Curves only (fast, ignores constraints / parents / drivers)"),
            ('NATIVE', "Native Solver", "Use Blender's built-in motion path solver on a minimal dependency graph (fast and exact for objects and bones)"),
            ('STEP', "Frame Stepping", "Step the scene through every frame (exact, slowest, supports everything)"),
        ),
        default='AUTO',
        update=_upd_path,
    )
    path_bone_point: EnumProperty(
        name="Bone Point",
        description="Which point of a bone the path follows",
        items=(('HEAD', "Head", ""), ('TAIL', "Tail", ""), ('CENTER', "Center", "")),
        default='HEAD',
        update=_upd_path,
    )
    path_show_past: BoolProperty(name="Past", description="Draw the part of the path before the current frame", default=True, update=_upd_redraw)
    path_show_future: BoolProperty(name="Future", description="Draw the part of the path after the current frame", default=True, update=_upd_redraw)

    path_line_width: FloatProperty(name="Line Width", default=2.0, min=0.5, max=20.0, step=10, precision=1, update=_upd_redraw)
    path_alpha: FloatProperty(name="Opacity", default=1.0, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw)
    path_fade: FloatProperty(
        name="Fade",
        description="Fade the path out with distance from the current frame",
        default=0.0, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw,
    )
    path_color_mode: EnumProperty(
        name="Color",
        items=(
            ('PAST_FUTURE', "Past / Future", "One color before the current frame, another after it"),
            ('SINGLE', "Single", "One color for the whole path"),
            ('GRADIENT', "Gradient", "Blend from the start color to the end color along the path"),
            ('SPEED', "Speed", "Color by speed (distance travelled per frame)"),
        ),
        default='PAST_FUTURE',
        update=_upd_redraw,
    )
    path_color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_upd_redraw)
    path_color_past: FloatVectorProperty(name="Past", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 0.55, 0.15), update=_upd_redraw)
    path_color_future: FloatVectorProperty(name="Future", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.2, 0.7, 1.0), update=_upd_redraw)
    path_color_start: FloatVectorProperty(name="Start", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.1, 0.1, 0.1), update=_upd_redraw)
    path_color_end: FloatVectorProperty(name="End", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_upd_redraw)
    path_color_slow: FloatVectorProperty(name="Slow", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.1, 0.4, 1.0), update=_upd_redraw)
    path_color_fast: FloatVectorProperty(name="Fast", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 0.15, 0.1), update=_upd_redraw)
    path_xray: BoolProperty(name="In Front", description="Draw the path on top of everything (no depth test)", default=False, update=_upd_redraw)

    path_show_points: BoolProperty(name="Frame Dots", description="Draw a dot at every evaluated frame", default=True, update=_upd_redraw)
    path_point_size: FloatProperty(name="Dot Size", default=4.0, min=1.0, max=30.0, step=10, precision=1, update=_upd_redraw)
    path_show_keyframes: BoolProperty(name="Keyframes", description="Highlight frames that have keyframes", default=True, update=_upd_redraw)
    path_keyframe_size: FloatProperty(name="Keyframe Size", default=9.0, min=1.0, max=40.0, step=10, precision=1, update=_upd_redraw)
    path_keyframe_color: FloatVectorProperty(name="Keyframe Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 0.9, 0.1), update=_upd_redraw)
    path_keyframe_shape: EnumProperty(
        name="Keyframe Shape",
        items=(('DIAMOND', "Diamond", ""), ('SQUARE', "Square", ""), ('CIRCLE', "Circle", "")),
        default='DIAMOND',
        update=_upd_redraw,
    )
    path_show_current: BoolProperty(name="Current Frame", description="Draw a marker at the current frame", default=True, update=_upd_redraw)
    path_current_size: FloatProperty(name="Current Size", default=12.0, min=1.0, max=50.0, step=10, precision=1, update=_upd_redraw)
    path_current_color: FloatVectorProperty(name="Current Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_upd_redraw)
    path_show_numbers: BoolProperty(name="Frame Numbers", description="Draw frame numbers along the path", default=False, update=_upd_redraw)
    path_number_step: IntProperty(name="Every Nth Frame", default=5, min=1, max=500, update=_upd_redraw)
    path_numbers_keyframes: BoolProperty(name="Number Keyframes", description="Always label keyframes", default=True, update=_upd_redraw)
    path_number_size: IntProperty(name="Text Size", default=11, min=6, max=48, update=_upd_redraw)
    path_number_color: FloatVectorProperty(name="Text Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 1.0, 1.0), update=_upd_redraw)
    path_number_offset: IntProperty(name="Text Offset", description="Pixel offset of the labels from the path", default=8, min=-100, max=100, update=_upd_redraw)

    # --- Onion skin --------------------------------------------------------
    onion_show: BoolProperty(
        name="Onion Skin",
        description="Draw ghosted copies of the mesh at other frames",
        default=False,  # ASC-PATCH P5: trails first; onion skin is opt-in (deformed meshes need frame stepping)
        update=_upd_onion,
    )
    onion_mode: EnumProperty(
        name="Mode",
        items=(
            ('FRAMES', "Frames", "Ghosts at a fixed number of frames before / after the current frame"),
            ('KEYFRAMES', "Keyframes", "Ghosts at the previous / next keyframes of the target"),
        ),
        default='FRAMES',
        update=_upd_onion,
    )
    onion_before: IntProperty(name="Before", description="Number of ghosts before the current frame", default=3, min=0, max=100, update=_upd_onion)
    onion_after: IntProperty(name="After", description="Number of ghosts after the current frame", default=3, min=0, max=100, update=_upd_onion)
    onion_step: IntProperty(name="Step", description="Frames (or keyframes) between ghosts", default=1, min=1, max=100, update=_upd_onion)
    onion_clamp_range: BoolProperty(name="Clamp to Scene Range", description="Never show ghosts outside the scene / preview range", default=True, update=_upd_onion)

    onion_opacity: FloatProperty(name="Opacity", default=0.35, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw)
    onion_falloff: FloatProperty(
        name="Falloff",
        description="How much the opacity decreases for ghosts farther from the current frame",
        default=0.6, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw,
    )
    onion_color_mode: EnumProperty(
        name="Color",
        items=(
            ('PAST_FUTURE', "Past / Future", "One color for ghosts before the current frame and another for ghosts after it"),
            ('SINGLE', "Single", "One color for all ghosts"),
            ('GRADIENT', "Gradient", "Blend from the near color to the far color with distance"),
        ),
        default='PAST_FUTURE',
        update=_upd_redraw,
    )
    onion_color_before: FloatVectorProperty(name="Before", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.145, 0.62, 0.2), update=_upd_redraw)
    onion_color_after: FloatVectorProperty(name="After", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.2, 0.35, 1.0), update=_upd_redraw)
    onion_color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.8, 0.8, 0.8), update=_upd_redraw)
    onion_color_near: FloatVectorProperty(name="Near", subtype='COLOR', size=3, min=0.0, max=1.0, default=(1.0, 0.8, 0.2), update=_upd_redraw)
    onion_color_far: FloatVectorProperty(name="Far", subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.3, 0.1, 0.6), update=_upd_redraw)
    onion_draw_type: EnumProperty(
        name="Display",
        items=(
            ('SOLID', "Solid", "Ghost surfaces", 'SHADING_SOLID', 0),
            ('WIRE', "Wire", "Ghost wireframes", 'SHADING_WIRE', 1),
            ('BOTH', "Solid + Wire", "Surfaces with wireframe on top", 'MOD_WIREFRAME', 2),
        ),
        default='SOLID',
        update=_upd_redraw,
    )
    onion_shading: EnumProperty(
        name="Shading",
        items=(
            ('SHADED', "Shaded", "Simple lighting so the ghost's volume reads well"),
            ('FLAT', "Flat", "Flat, unlit color"),
        ),
        default='SHADED',
        update=_upd_redraw,
    )
    onion_light_strength: FloatProperty(name="Light", default=0.65, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw)
    onion_rim: FloatProperty(name="Rim", description="Fresnel-like edge brightening", default=0.35, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw)
    onion_wire_width: FloatProperty(name="Wire Width", default=1.0, min=0.5, max=10.0, step=10, precision=1, update=_upd_redraw)
    onion_wire_opacity: FloatProperty(name="Wire Opacity", description="Wire opacity relative to the ghost opacity", default=0.8, min=0.0, max=1.0, subtype='FACTOR', update=_upd_redraw)
    onion_xray: BoolProperty(name="In Front", description="Draw ghosts on top of everything (no depth test)", default=False, update=_upd_redraw)
    onion_backface_culling: BoolProperty(name="Backface Culling", description="Hide the inside of ghosts (much cleaner for closed meshes)", default=True, update=_upd_redraw)
    onion_depth_write: BoolProperty(name="Write Depth", description="Ghosts occlude each other (and the path). Off gives a softer, additive look", default=False, update=_upd_redraw)
    onion_use_modifiers: BoolProperty(name="Use Modifiers", description="Evaluate modifiers (armatures, shape keys, subdivision...). Off only ghosts the base mesh with the object transform", default=True, update=_upd_onion)
    onion_include_armature_meshes: BoolProperty(
        name="Armature Meshes",
        description="When an armature (or its bones) is targeted, ghost the meshes it deforms",
        default=True,
        update=_upd_targets,
    )
    onion_vertex_limit: IntProperty(
        name="Vertex Limit",
        description="Skip meshes with more evaluated vertices than this (protects against very heavy meshes)",
        default=400000, min=100, max=50000000, update=_upd_onion,
    )
    onion_show_current: BoolProperty(
        name="Current Frame Ghost",
        description="Also draw a ghost at the current frame (useful with In Front to see the mesh through other objects)",
        default=False,
        update=_upd_onion,
    )


# ---------------------------------------------------------------------------

classes = (
    ASC_TR_PinnedItem,
    ASC_TR_Settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asc_trails = PointerProperty(type=ASC_TR_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "asc_trails"):
        del bpy.types.Scene.asc_trails
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

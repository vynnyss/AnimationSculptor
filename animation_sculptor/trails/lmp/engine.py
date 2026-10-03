# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (engine.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""
Evaluation engine and cache for the Live Motion Path & Onion Skin add-on.

Three evaluation strategies are combined:

* **F-Curve** (fast): transform F-Curves are evaluated directly with
  ``FCurve.evaluate`` and composed into world matrices.  No dependency graph
  update is needed, so this can run on every change without side effects.
  Only valid for objects without constraints / drivers / NLA / non-object
  parenting.
* **Native**: Blender's own motion-path solver (``object.paths_calculate`` /
  ``pose.paths_calculate``) run on a minimal dependency graph.  Exact for
  anything (bones included) and much faster than stepping the whole scene.
  The temporary native path is read into numpy and removed again.
* **Frame stepping**: ``Scene.frame_set`` over the requested frames.  Used
  for deforming meshes (onion skins need the evaluated geometry) and as a
  universal fallback.  Work is time-sliced from a timer so long ranges are
  filled in progressively while the UI stays responsive.

Nothing from ``bpy`` is stored across timer ticks except names: caches hold
plain numpy arrays and are looked up by (object name, bone name).
"""

import time

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

from . import compat

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MESHLIKE = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

TRANSFORM_PATHS = {
    "location": 3,
    "rotation_euler": 3,
    "rotation_quaternion": 4,
    "rotation_axis_angle": 4,
    "scale": 3,
    "delta_location": 3,
    "delta_rotation_euler": 3,
    "delta_rotation_quaternion": 4,
    "delta_scale": 3,
}

# Modifiers that never change the geometry over time by themselves.
RIGID_SAFE_MODIFIERS = {
    'SUBSURF', 'BEVEL', 'MIRROR', 'SOLIDIFY', 'TRIANGULATE', 'WEIGHTED_NORMAL',
    'EDGE_SPLIT', 'DECIMATE', 'MULTIRES', 'WIREFRAME', 'MASK', 'NORMAL_EDIT',
    'WELD', 'SCREW', 'SKIN', 'REMESH', 'ARRAY', 'UV_PROJECT', 'UV_WARP',
    'VERTEX_WEIGHT_EDIT', 'VERTEX_WEIGHT_MIX',
}

_OB_DEP_ATTRS = ("object", "object_from", "object_to", "target", "auxiliary_target",
                 "mirror_object", "offset_object", "start_cap", "end_cap", "curve",
                 "origin", "texture_coords_object")


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

class _State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.computing = False
        self.generation = 0
        self.timer_fn = None
        self.playing = False
        self.targets = []              # list[Target] snapshot for drawing
        self.target_keys = frozenset()
        self.selection_sig = None
        self.dirty_path = True
        self.dirty_onion = True
        self.job = None                # StepJob in progress
        self.last_compute_ms = 0.0
        self.last_engine_info = ""
        self.shaded_shader_failed = False
        self.native_failed = set()     # object names where the native solver failed
        self.tick = 0
        self.deform_cache = {}         # armature name -> [mesh names]
        self.path_clamped = False
        # ASC-PATCH P3: external edits (Animation Sculptor gestures) suspend recomputation.
        self.suspended = 0             # nesting depth of suspend()
        self.pending_while_suspended = False
        # ASC-PATCH P4: IDs whose next depsgraph update was caused by our own settings restore
        self.self_tagged = set()


STATE = _State()
CACHE = {}          # (obj_name, bone_name) -> TargetCache


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

class SkinData:
    """Geometry of one ghost.  Arrays are numpy, GPU batches are created lazily by draw.py."""
    __slots__ = ("pos", "nor", "tris", "edges", "flip", "batches", "nverts")

    def __init__(self, pos, nor, tris, edges, flip=False):
        self.pos = pos          # float32 (N, 3)
        self.nor = nor          # float32 (N, 3)
        self.tris = tris        # int32 (T, 3)
        self.edges = edges      # int32 (E, 2)
        self.flip = flip        # negative-scale transform (culling must flip)
        self.batches = {}
        self.nverts = int(len(pos))

    def clear_gpu(self):
        self.batches = {}


class Target:
    __slots__ = ("obj_name", "bone", "want_path", "want_onion", "deps", "key", "type")

    def __init__(self, ob, bone=None, want_path=True, want_onion=True):
        self.obj_name = ob.name
        self.bone = bone or ""
        self.want_path = want_path
        self.want_onion = want_onion
        self.key = (ob.name, self.bone)
        self.type = ob.type
        self.deps = build_deps(ob)

    @property
    def obj(self):
        return bpy.data.objects.get(self.obj_name)


class TargetCache:
    def __init__(self, key):
        self.key = key
        self.obj_name, self.bone = key
        self.is_bone = bool(self.bone)
        # path
        self.mats = {}             # frame -> np.float64 (4,4)   (objects, F-Curve / stepping)
        self.pts = {}              # frame -> (x, y, z)          (bones / native solver)
        self.path_engine = ""
        self.path_frames = None    # np.int32 (N,)
        self.path_points = None    # np.float32 (N, 3)
        self.path_dirty = True
        self.path_complete = False
        self.keyframes = []        # sorted ints, keyframes of the target itself
        self.onion_keyframes = []  # sorted ints, keyframes that drive the ghosted mesh
        # onion
        self.onion = {}            # frame -> SkinData (world space)
        self.onion_source = 'DEFORM'
        self.rigid_base = None     # SkinData in local space (RIGID source)
        self.onion_dirty = True
        self.onion_error = ""
        # misc
        self.eval_sig = None
        self.color_cache = None
        self.last_touch = 0

    # -- helpers ----------------------------------------------------------
    def clear_path(self):
        self.mats.clear()
        self.pts.clear()
        self.path_frames = None
        self.path_points = None
        self.path_complete = False
        self.path_dirty = True
        self.path_engine = ""
        self.color_cache = None
        # rigid ghosts were derived from the matrices
        if self.onion_source == 'RIGID':
            self.onion.clear()

    def clear_onion(self):
        self.onion.clear()
        self.rigid_base = None
        self.onion_dirty = True
        self.onion_error = ""

    def has_frame_point(self, f):
        return f in self.mats or f in self.pts

    def point_at(self, f):
        p = self.pts.get(f)
        if p is not None:
            return p
        m = self.mats.get(f)
        if m is not None:
            return (float(m[0, 3]), float(m[1, 3]), float(m[2, 3]))
        return None

    def rebuild_path_arrays(self, frames):
        avail = [f for f in frames if self.has_frame_point(f)]
        self.path_complete = len(avail) == len(frames)
        self.color_cache = None
        if not avail:
            self.path_frames = None
            self.path_points = None
            return
        pts = np.empty((len(avail), 3), dtype=np.float32)
        for i, f in enumerate(avail):
            pts[i] = self.point_at(f)
        self.path_frames = np.array(avail, dtype=np.int32)
        self.path_points = pts

    def world_skin(self, f):
        """World-space ghost for frame *f* (None when not evaluated yet)."""
        skin = self.onion.get(f)
        if skin is not None:
            return skin
        if self.onion_source == 'RIGID' and self.rigid_base is not None:
            m = self.mats.get(f)
            if m is not None:
                skin = transform_skin(self.rigid_base, m)
                self.onion[f] = skin
                return skin
        return None


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _log(msg):
    print("[Live Motion Onion] " + msg)


def request_redraw():
    compat.tag_redraw_all()


def _scene():
    win = compat.main_window()
    if win is not None:
        try:
            return win.scene
        except Exception:
            pass
    try:
        return bpy.context.scene
    except Exception:
        return None


def _settings(scene=None):
    if scene is None:
        scene = _scene()
    return getattr(scene, "asc_trails", None) if scene is not None else None


def _view_layer(scene):
    win = compat.main_window()
    if win is not None:
        try:
            if win.scene == scene and win.view_layer is not None:
                return win.view_layer
        except Exception:
            pass
    try:
        vl = bpy.context.view_layer
        if vl is not None:
            return vl
    except Exception:
        pass
    return scene.view_layers[0] if len(scene.view_layers) else None


def scene_frame_range(scene):
    if scene.use_preview_range:
        return scene.frame_preview_start, scene.frame_preview_end
    return scene.frame_start, scene.frame_end


def build_deps(ob):
    """Set of (id_type, name) keys whose update should invalidate this target."""
    deps = set()
    try:
        deps.add(compat.id_key(ob))
        data = ob.data
        if data is not None:
            deps.add(compat.id_key(data))
            sk = getattr(data, "shape_keys", None)
            if sk is not None:
                deps.add(compat.id_key(sk))
        p = ob.parent
        depth = 0
        while p is not None and depth < 64:
            deps.add(compat.id_key(p))
            if p.data is not None:
                deps.add(compat.id_key(p.data))
            p = p.parent
            depth += 1
        arm = ob.find_armature()
        if arm is not None:
            deps.add(compat.id_key(arm))
            if arm.data is not None:
                deps.add(compat.id_key(arm.data))
        for m in ob.modifiers:
            for attr in _OB_DEP_ATTRS:
                o = getattr(m, attr, None)
                if isinstance(o, bpy.types.Object):
                    deps.add(compat.id_key(o))
                    if o.data is not None:
                        deps.add(compat.id_key(o.data))
        for c in ob.constraints:
            t = getattr(c, "target", None)
            if isinstance(t, bpy.types.Object):
                deps.add(compat.id_key(t))
            targets = getattr(c, "targets", None)
            if targets is not None:
                try:
                    for st in targets:
                        if st.target is not None:
                            deps.add(compat.id_key(st.target))
                except Exception:
                    pass
        if ob.type == 'ARMATURE' and ob.pose is not None:
            for pb in ob.pose.bones:
                for c in pb.constraints:
                    t = getattr(c, "target", None)
                    if isinstance(t, bpy.types.Object) and t != ob:
                        deps.add(compat.id_key(t))
    except Exception:
        pass
    return deps


def deformed_meshes(arm_ob):
    """Mesh-like objects deformed by *arm_ob* (armature modifier or armature parenting)."""
    names = STATE.deform_cache.get(arm_ob.name)
    if names is None:
        names = []
        try:
            for ob in bpy.data.objects:
                if ob.type not in MESHLIKE:
                    continue
                hit = False
                if ob.parent == arm_ob and ob.parent_type == 'ARMATURE':
                    hit = True
                else:
                    for m in ob.modifiers:
                        if m.type == 'ARMATURE' and m.object == arm_ob and m.show_viewport:
                            hit = True
                            break
                if hit:
                    names.append(ob.name)
        except Exception:
            pass
        STATE.deform_cache[arm_ob.name] = names
    out = []
    for n in names:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            out.append(ob)
    return out


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def _selected_objects(view_layer, context):
    if context is not None:
        try:
            return list(context.selected_objects)
        except Exception:
            pass
    return [o for o in view_layer.objects if o.select_get(view_layer=view_layer)]


def selection_signature(scene, view_layer, context=None):
    """Cheap hashable description of what the targets depend on (for the draw handler)."""
    s = _settings(scene)
    if s is None:
        return None
    if s.target_mode == 'PINNED':
        pins = tuple((it.obj.name if it.obj else "", it.bone) for it in s.pinned)
        return ('PINNED', pins, s.onion_show, s.path_show, s.onion_include_armature_meshes)
    if view_layer is None:
        return None
    active = view_layer.objects.active
    aname = active.name if active else ""
    amode = active.mode if active else ""
    bones = ()
    if active is not None and active.type == 'ARMATURE' and amode == 'POSE':
        try:
            bones = tuple(pb.name for pb in active.pose.bones if compat.pose_bone_selected(pb))
        except Exception:
            bones = ()
    if s.target_mode == 'ACTIVE':
        return ('ACTIVE', aname, amode, bones[:1] if bones else compat.active_pose_bone_name(active) if active else "",
                s.onion_show, s.path_show, s.onion_include_armature_meshes)
    sel = tuple(sorted(o.name for o in _selected_objects(view_layer, context)))
    return ('SELECTED', sel, aname, amode, bones, s.onion_show, s.path_show, s.onion_include_armature_meshes)


def resolve_targets(scene, view_layer, context=None):
    s = _settings(scene)
    if s is None:
        return []
    targets = []
    seen = {}

    def add(ob, bone=None, want_path=True, want_onion=True):
        if ob is None:
            return
        want_onion = bool(want_onion and s.onion_show and ob.type in MESHLIKE)
        want_path = bool(want_path and s.path_show)
        if not (want_onion or want_path):
            return
        key = (ob.name, bone or "")
        existing = seen.get(key)
        if existing is not None:
            existing.want_path = existing.want_path or want_path
            existing.want_onion = existing.want_onion or want_onion
            return
        t = Target(ob, bone, want_path, want_onion)
        seen[key] = t
        targets.append(t)

    def add_object(ob):
        if ob.type == 'ARMATURE':
            add(ob, None, True, False)
            if s.onion_include_armature_meshes:
                for m in deformed_meshes(ob):
                    add(m, None, False, True)
        else:
            add(ob)

    def add_armature_bones(arm, bone_names):
        for b in bone_names:
            add(arm, b, True, False)
        if s.onion_include_armature_meshes:
            for m in deformed_meshes(arm):
                add(m, None, False, True)

    if s.target_mode == 'PINNED':
        for item in s.pinned:
            ob = item.obj
            if ob is None:
                continue
            try:
                ob.name
            except ReferenceError:
                continue
            if item.bone:
                if ob.type == 'ARMATURE' and item.bone in ob.pose.bones:
                    add_armature_bones(ob, [item.bone])
            else:
                add_object(ob)
        return targets

    if view_layer is None:
        return targets
    active = view_layer.objects.active
    if s.target_mode == 'ACTIVE':
        objs = [active] if active is not None else []
    else:
        objs = _selected_objects(view_layer, context)
        if active is not None and active.mode == 'POSE' and active not in objs:
            objs.append(active)

    for ob in objs:
        if ob is None:
            continue
        try:
            if not ob.visible_get(view_layer=view_layer):
                continue
        except Exception:
            pass
        if ob.type == 'ARMATURE' and ob.mode == 'POSE':
            if s.target_mode == 'ACTIVE':
                name = compat.active_pose_bone_name(ob)
                bones = [name] if name and name in ob.pose.bones else []
            else:
                bones = [pb.name for pb in ob.pose.bones
                         if compat.pose_bone_selected(pb) and not compat.pose_bone_hidden(pb)]
            if bones:
                add_armature_bones(ob, bones)
            else:
                add_object(ob)
        else:
            add_object(ob)
    return targets


def targets_changed():
    """Called when the target list may have changed (pin list edits, settings)."""
    STATE.selection_sig = None
    STATE.target_keys = frozenset()
    STATE.deform_cache.clear()
    schedule(delay=0.0)


def get_draw_targets(context):
    """Targets for the draw handler.  Re-resolved only when the selection changes."""
    scene = context.scene
    vl = context.view_layer
    try:
        sig = selection_signature(scene, vl, context)
    except Exception:
        sig = None
    if sig is not None and sig == STATE.selection_sig:
        return STATE.targets
    try:
        targets = resolve_targets(scene, vl, context)
    except Exception:
        return STATE.targets
    keys = frozenset(t.key for t in targets)
    STATE.selection_sig = sig
    if keys != STATE.target_keys:
        STATE.targets = targets
        STATE.target_keys = keys
        schedule(delay=0.0)
    return STATE.targets


# ---------------------------------------------------------------------------
# Keyframes
# ---------------------------------------------------------------------------

def _keys_from_fcurves(fcurves, bone=None):
    keys = set()
    prefix = 'pose.bones["%s"]' % bone if bone else None
    for fc in fcurves:
        try:
            if prefix is not None and not fc.data_path.startswith(prefix):
                continue
            n = len(fc.keyframe_points)
            if n == 0:
                continue
            arr = np.empty(n * 2, dtype=np.float32)
            fc.keyframe_points.foreach_get("co", arr)
            keys.update(int(round(float(v))) for v in arr[0::2])
        except Exception:
            continue
    return keys


def collect_keyframes(ob, bone=None):
    """Keyframes of the object itself (or of one of its pose bones)."""
    if ob is None:
        return []
    return sorted(_keys_from_fcurves(compat.get_fcurves(ob.animation_data), bone))


def collect_onion_keyframes(ob):
    """Keyframes of everything that can deform / move the ghosted mesh."""
    if ob is None:
        return []
    keys = set()
    keys.update(_keys_from_fcurves(compat.get_fcurves(ob.animation_data)))
    try:
        data = ob.data
        if data is not None:
            keys.update(_keys_from_fcurves(compat.get_fcurves(data.animation_data)))
            sk = getattr(data, "shape_keys", None)
            if sk is not None:
                keys.update(_keys_from_fcurves(compat.get_fcurves(sk.animation_data)))
    except Exception:
        pass
    try:
        arm = ob.find_armature()
        if arm is not None:
            keys.update(_keys_from_fcurves(compat.get_fcurves(arm.animation_data)))
    except Exception:
        pass
    try:
        p = ob.parent
        depth = 0
        while p is not None and depth < 16:
            keys.update(_keys_from_fcurves(compat.get_fcurves(p.animation_data)))
            p = p.parent
            depth += 1
    except Exception:
        pass
    return sorted(keys)


# ---------------------------------------------------------------------------
# F-Curve (fast) evaluation
# ---------------------------------------------------------------------------

class _FastNode:
    __slots__ = ("obj_name", "fcurves", "parent_inverse", "static_parent")

    def __init__(self, obj_name, fcurves, parent_inverse, static_parent=None):
        self.obj_name = obj_name
        self.fcurves = fcurves                # list of (FCurve, data_path, index)
        self.parent_inverse = parent_inverse  # Matrix
        self.static_parent = static_parent    # Matrix or None (unsupported parent -> frozen)


def _fast_node(ob, force):
    """Fast-evaluation node for *ob*, or None when F-Curves alone cannot describe its motion."""
    static_parent = None
    if ob.parent is not None and ob.parent_type != 'OBJECT':
        if not force:
            return None
        static_parent = ob.parent.matrix_world.copy()
    if not force:
        for c in ob.constraints:
            if c.mute or not getattr(c, "enabled", True) or c.influence <= 0.0:
                continue
            return None
    adt = ob.animation_data
    fcs = []
    if adt is not None:
        if not force:
            if compat.get_drivers(adt):
                return None
            if compat.has_nla_strips(adt):
                return None
            if adt.action is not None:
                if getattr(adt, "action_influence", 1.0) < 1.0:
                    return None
                if getattr(adt, "action_blend_type", 'REPLACE') != 'REPLACE':
                    return None
        for fc in compat.get_fcurves(adt):
            try:
                if fc.mute:
                    continue
                dp = fc.data_path
                n = TRANSFORM_PATHS.get(dp)
                if n is None:
                    continue
                idx = fc.array_index
                if 0 <= idx < n:
                    fcs.append((fc, dp, idx))
            except Exception:
                continue
    return _FastNode(ob.name, fcs, ob.matrix_parent_inverse.copy(), static_parent)


def build_fast_chain(ob, force=False):
    """List of nodes (root first) or None.  Must be rebuilt for every job (holds F-Curve refs)."""
    nodes = []
    cur = ob
    depth = 0
    while cur is not None and depth < 64:
        node = _fast_node(cur, force)
        if node is None:
            return None
        nodes.append(node)
        if node.static_parent is not None:
            break
        cur = cur.parent
        depth += 1
    nodes.reverse()
    return nodes


def _basis_at(ob, fcurves, f):
    loc = list(ob.location)
    dloc = list(ob.delta_location)
    scale = list(ob.scale)
    dscale = list(ob.delta_scale)
    mode = ob.rotation_mode
    if mode == 'QUATERNION':
        rot = list(ob.rotation_quaternion)
        drot = list(ob.delta_rotation_quaternion)
    elif mode == 'AXIS_ANGLE':
        rot = list(ob.rotation_axis_angle)
        drot = None
    else:
        rot = list(ob.rotation_euler)
        drot = list(ob.delta_rotation_euler)

    for fc, dp, idx in fcurves:
        try:
            v = fc.evaluate(f)
        except Exception:
            continue
        if dp == "location":
            loc[idx] = v
        elif dp == "scale":
            scale[idx] = v
        elif dp == "delta_location":
            dloc[idx] = v
        elif dp == "delta_scale":
            dscale[idx] = v
        elif dp == "rotation_euler":
            if mode not in ('QUATERNION', 'AXIS_ANGLE'):
                rot[idx] = v
        elif dp == "rotation_quaternion":
            if mode == 'QUATERNION':
                rot[idx] = v
        elif dp == "rotation_axis_angle":
            if mode == 'AXIS_ANGLE':
                rot[idx] = v
        elif dp == "delta_rotation_euler":
            if drot is not None and mode not in ('QUATERNION', 'AXIS_ANGLE'):
                drot[idx] = v
        elif dp == "delta_rotation_quaternion":
            if drot is not None and mode == 'QUATERNION':
                drot[idx] = v

    if mode == 'QUATERNION':
        q = Quaternion(rot)
        if q.magnitude > 1e-8:
            q.normalize()
        rmat = q.to_matrix()
        dq = Quaternion(drot)
        if dq.magnitude > 1e-8:
            dq.normalize()
        dmat = dq.to_matrix()
    elif mode == 'AXIS_ANGLE':
        axis = Vector(rot[1:4])
        if axis.length < 1e-8:
            axis = Vector((0.0, 1.0, 0.0))
        rmat = Matrix.Rotation(rot[0], 3, axis)
        dmat = Matrix.Identity(3)
    else:
        rmat = Euler(rot, mode).to_matrix()
        dmat = Euler(drot, mode).to_matrix()
    rot3 = dmat @ rmat
    sc = Vector((scale[0] * dscale[0], scale[1] * dscale[1], scale[2] * dscale[2]))
    return Matrix.LocRotScale(Vector(loc) + Vector(dloc), rot3, sc)


def fast_matrix_at(chain, f):
    """World matrix (mathutils) of the chain's leaf object at frame *f*."""
    mat = None
    for node in chain:
        ob = bpy.data.objects.get(node.obj_name)
        if ob is None:
            return None
        basis = _basis_at(ob, node.fcurves, f)
        if node.static_parent is not None:
            mat = node.static_parent @ node.parent_inverse @ basis
        elif mat is None:
            mat = basis
        else:
            mat = mat @ node.parent_inverse @ basis
    return mat


# ---------------------------------------------------------------------------
# Onion source classification
# ---------------------------------------------------------------------------

def onion_is_rigid(ob, use_modifiers):
    """True when the evaluated mesh does not change over time (only its transform does)."""
    if ob.type == 'META':
        return False
    if not use_modifiers:
        return True
    data = ob.data
    if data is None:
        return True
    try:
        if data.animation_data is not None:
            return False
        sk = getattr(data, "shape_keys", None)
        if sk is not None and sk.animation_data is not None:
            return False
        for m in ob.modifiers:
            if not m.show_viewport:
                continue
            if m.type not in RIGID_SAFE_MODIFIERS:
                return False
            if m.type == 'ARRAY' and (m.offset_object is not None or m.curve is not None
                                      or m.fit_type == 'FIT_CURVE'):
                return False
            if m.type == 'MIRROR' and m.mirror_object is not None:
                return False
        adt = ob.animation_data
        if adt is not None:
            for fc in compat.get_fcurves(adt):
                if fc.data_path not in TRANSFORM_PATHS:
                    return False
            for d in compat.get_drivers(adt):
                if d.data_path not in TRANSFORM_PATHS:
                    return False
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Mesh extraction
# ---------------------------------------------------------------------------

def extract_skin(ob_eval, ob_orig, use_modifiers, limit):
    """Local-space geometry of *ob_eval* (or of the base mesh) as numpy arrays.

    Returns (SkinData or None, error string).
    """
    me = None
    owner = None
    tmp = False
    try:
        if use_modifiers:
            if ob_orig.type == 'MESH':
                me = ob_eval.data
            else:
                owner = ob_eval
                me = ob_eval.to_mesh()
                tmp = True
        else:
            if ob_orig.type == 'MESH':
                me = ob_orig.data
            else:
                owner = ob_orig
                me = ob_orig.to_mesh()
                tmp = True
        if me is None:
            return None, "no mesh data"
        n = len(me.vertices)
        if n == 0:
            return None, "empty mesh"
        if n > limit:
            return None, "over vertex limit (%d > %d)" % (n, limit)
        pos = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", pos)
        pos.shape = (n, 3)
        nor = np.empty(n * 3, dtype=np.float32)
        try:
            me.vertex_normals.foreach_get("vector", nor)
        except Exception:
            nor[:] = 0.0
        nor.shape = (n, 3)
        try:
            me.calc_loop_triangles()
        except Exception:
            pass
        nt = len(me.loop_triangles)
        tris = np.empty(nt * 3, dtype=np.int32)
        if nt:
            me.loop_triangles.foreach_get("vertices", tris)
        tris.shape = (nt, 3)
        ne = len(me.edges)
        edges = np.empty(ne * 2, dtype=np.int32)
        if ne:
            me.edges.foreach_get("vertices", edges)
        edges.shape = (ne, 2)
        return SkinData(pos, nor, tris, edges), ""
    except Exception as e:
        return None, str(e)
    finally:
        if tmp and owner is not None:
            try:
                owner.to_mesh_clear()
            except Exception:
                pass


def transform_skin(base, matrix):
    """World-space copy of a local-space SkinData.  *matrix* is a 4x4 (numpy or mathutils)."""
    m = np.asarray(matrix, dtype=np.float64).reshape(4, 4)
    r = m[:3, :3]
    t = m[:3, 3]
    pos = (base.pos.astype(np.float64) @ r.T + t).astype(np.float32)
    try:
        rn = np.linalg.inv(r).T
    except np.linalg.LinAlgError:
        rn = r
    nor = base.nor.astype(np.float64) @ rn.T
    length = np.linalg.norm(nor, axis=1)
    length[length < 1e-12] = 1.0
    nor = (nor / length[:, None]).astype(np.float32)
    flip = bool(np.linalg.det(r) < 0.0)
    return SkinData(pos, nor, base.tris, base.edges, flip)


# ---------------------------------------------------------------------------
# Frame lists
# ---------------------------------------------------------------------------

def path_display_range(scene, s):
    """(start, end) of frames shown for the path."""
    cf = scene.frame_current
    if s.path_range_mode == 'AROUND':
        return cf - s.path_before, cf + s.path_after
    if s.path_range_mode == 'CUSTOM':
        a, b = s.path_start, s.path_end
        return (a, b) if a <= b else (b, a)
    return scene_frame_range(scene)


def _frames(start, end, step):
    return list(range(int(start), int(end) + 1, max(1, int(step))))


MAX_PATH_FRAMES = 6000


def _clamp_range(start, end, step, cf):
    """Keep at most MAX_PATH_FRAMES evaluated frames, centred on the current frame."""
    n = (end - start) // step + 1
    if n <= MAX_PATH_FRAMES:
        return start, end, False
    half = (MAX_PATH_FRAMES // 2) * step
    a = max(start, cf - half)
    b = min(end, a + MAX_PATH_FRAMES * step)
    a = max(start, b - MAX_PATH_FRAMES * step)
    return a, b, True


def display_frames(scene, s):
    """Frames shown for the path (clamped like path_frames_needed)."""
    step = max(1, s.path_step)
    start, end = path_display_range(scene, s)
    start, end, _clamped = _clamp_range(start, end, step, scene.frame_current)
    return _frames(start, end, step)


def path_frames_needed(scene, s, cheap_engine):
    """Frames the path cache should contain.

    Cheap engines (F-Curve / native) also cover the whole scene range so that
    scrubbing in 'Around Frame' mode never triggers a recompute."""
    cf = scene.frame_current
    step = max(1, s.path_step)
    start, end = path_display_range(scene, s)
    start, end, clamped = _clamp_range(start, end, step, cf)
    frames = _frames(start, end, step)
    if cheap_engine and s.path_range_mode == 'AROUND':
        a, b = scene_frame_range(scene)
        if (b - a) // step + 1 <= MAX_PATH_FRAMES:
            extra = [f for f in _frames(a, b, step) if f < start or f > end]
            frames = sorted(set(frames) | set(extra))
    STATE.path_clamped = clamped
    return frames


def onion_frame_list(cache, s, scene, cf=None):
    """[(frame, side, index, count)] for the ghosts around the current frame.

    side is -1 (before), +1 (after) or 0 (current); index is 1..count (1 = closest)."""
    if cf is None:
        cf = scene.frame_current
    out = []
    step = max(1, s.onion_step)
    if s.onion_mode == 'KEYFRAMES':
        keys = cache.onion_keyframes
        before = [k for k in keys if k < cf][::-1][::step][:s.onion_before]
        after = [k for k in keys if k > cf][::step][:s.onion_after]
    else:
        before = [cf - step * i for i in range(1, s.onion_before + 1)]
        after = [cf + step * i for i in range(1, s.onion_after + 1)]
    if s.onion_clamp_range:
        lo, hi = scene_frame_range(scene)
        before = [f for f in before if lo <= f <= hi]
        after = [f for f in after if lo <= f <= hi]
    nb, na = len(before), len(after)
    for i, f in enumerate(before):
        out.append((f, -1, i + 1, nb))
    for i, f in enumerate(after):
        out.append((f, 1, i + 1, na))
    if s.onion_show_current:
        out.append((cf, 0, 0, 1))
    return out


def eval_signature(s):
    return (s.eval_mode, s.path_engine, s.path_bone_point, s.path_step,
            s.onion_use_modifiers, s.onion_vertex_limit)


# ---------------------------------------------------------------------------
# Native motion path solver
# ---------------------------------------------------------------------------

def _override_kwargs(ob, extra=None):
    win = compat.main_window()
    if win is None:
        return None
    kw = dict(window=win, active_object=ob, object=ob, selected_objects=[ob],
              selected_editable_objects=[ob], editable_objects=[ob])
    try:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                kw["area"] = area
                for region in area.regions:
                    if region.type == 'WINDOW':
                        kw["region"] = region
                        break
                break
    except Exception:
        pass
    if extra:
        kw.update(extra)
    return kw


def _read_motion_path(mp):
    n = mp.length
    if n <= 0:
        return None
    arr = np.empty(n * 3, dtype=np.float32)
    mp.points.foreach_get("co", arr)
    arr.shape = (n, 3)
    f0 = int(mp.frame_start)
    return {f0 + i: (float(arr[i, 0]), float(arr[i, 1]), float(arr[i, 2])) for i in range(n)}


# ASC-PATCH P4: the native solver configures the persistent motion-path settings of the object/pose
# (type, range, frames, bake location). Save and restore them so the .blend is not modified.
_AVS_ATTRS = ("type", "range", "frame_start", "frame_end", "bake_location")


def _avs_save(avs):
    saved = {}
    for attr in _AVS_ATTRS:
        try:
            saved[attr] = getattr(avs, attr)
        except Exception:
            pass
    return saved


def _avs_restore(avs, saved, owner=None):
    """Restore the settings. Writing them tags *owner* for update; that update must not invalidate the
    trail we just computed (it would recompute forever), so it is ignored once by depsgraph_changed."""
    changed = False
    for attr, value in saved.items():
        try:
            if getattr(avs, attr) != value:
                setattr(avs, attr, value)
                changed = True
        except Exception:
            pass
    if changed and owner is not None:
        STATE.self_tagged.add(compat.id_key(owner))
        if owner.data is not None:
            STATE.self_tagged.add(compat.id_key(owner.data))


def native_object_path(ob, start, end):
    """{frame: (x, y, z)} from Blender's motion path solver, or None on failure."""
    if end <= start:
        end = start + 1
    kw = _override_kwargs(ob)
    if kw is None:
        return None
    avs = None
    saved = {}
    try:
        had_path = ob.motion_path is not None
        avs = ob.animation_visualization.motion_path
        saved = _avs_save(avs)  # ASC-PATCH P4
        avs.type = 'RANGE'
        avs.range = 'MANUAL'
        avs.frame_start = int(start)
        avs.frame_end = int(end)
        with bpy.context.temp_override(**kw):
            res = bpy.ops.object.paths_calculate('EXEC_DEFAULT', False, display_type='RANGE', range='MANUAL')
            mp = ob.motion_path
            out = _read_motion_path(mp) if ('FINISHED' in res and mp is not None) else None
            if not had_path and ob.motion_path is not None:
                bpy.ops.object.paths_clear('EXEC_DEFAULT', False, only_selected=True)
        return out
    except Exception as e:
        _log("native solver failed for %r: %s" % (ob.name, e))
        return None
    finally:
        if avs is not None:
            _avs_restore(avs, saved, ob)  # ASC-PATCH P4


def native_bone_paths(arm, bone_names, start, end, point):
    """{bone: {frame: (x, y, z)}} via pose.paths_calculate.  The armature must be in Pose Mode."""
    if end <= start:
        end = start + 1
    if arm.mode != 'POSE' or arm.pose is None:
        return None
    pbones = [arm.pose.bones[n] for n in bone_names if n in arm.pose.bones]
    if not pbones:
        return None
    kw = _override_kwargs(arm, dict(selected_pose_bones=pbones, active_pose_bone=pbones[0],
                                    selected_pose_bones_from_active_object=pbones))
    if kw is None:
        return None
    bake_location = 'TAILS' if point == 'TAIL' else 'HEADS'
    avs = None
    saved = {}
    try:
        had_paths = any(pb.motion_path is not None for pb in pbones)
        avs = arm.pose.animation_visualization.motion_path
        saved = _avs_save(avs)  # ASC-PATCH P4
        avs.type = 'RANGE'
        avs.range = 'MANUAL'
        avs.frame_start = int(start)
        avs.frame_end = int(end)
        avs.bake_location = bake_location
        result = {}
        with bpy.context.temp_override(**kw):
            res = bpy.ops.pose.paths_calculate('EXEC_DEFAULT', False, display_type='RANGE',
                                               range='MANUAL', bake_location=bake_location)
            if 'FINISHED' in res:
                for pb in pbones:
                    mp = pb.motion_path
                    if mp is not None:
                        pts = _read_motion_path(mp)
                        if pts:
                            result[pb.name] = pts
            if not had_paths:
                bpy.ops.pose.paths_clear('EXEC_DEFAULT', False, only_selected=True)
        return result if result else None
    except Exception as e:
        _log("native bone solver failed for %r: %s" % (arm.name, e))
        return None
    finally:
        if avs is not None:
            _avs_restore(avs, saved, arm)  # ASC-PATCH P4


# ---------------------------------------------------------------------------
# Stepping job
# ---------------------------------------------------------------------------

class StepJob:
    """Frames that need a real depsgraph evaluation, grouped per frame."""

    def __init__(self, scene_name):
        self.scene_name = scene_name
        self.pending = {}      # frame -> list of (key, want_point, want_skin)
        self.order = []
        self.processed = 0

    def add(self, frame, key, want_point, want_skin):
        lst = self.pending.setdefault(frame, [])
        for i, (k, wp, ws) in enumerate(lst):
            if k == key:
                lst[i] = (k, wp or want_point, ws or want_skin)
                return
        lst.append((key, want_point, want_skin))

    def sort(self, cf):
        # frames closest to the playhead first: ghosts near the current frame appear first
        self.order = sorted(self.pending.keys(), key=lambda f: (abs(f - cf), f))

    @property
    def remaining(self):
        return len(self.pending)


def _bone_point(pb_eval, mat_world, point):
    if point == 'TAIL':
        v = mat_world @ pb_eval.tail
    elif point == 'CENTER':
        v = mat_world @ ((pb_eval.head + pb_eval.tail) * 0.5)
    else:
        v = mat_world @ pb_eval.head
    return (v.x, v.y, v.z)


def run_step_job(job, scene, s, budget):
    """Evaluate pending frames for at most *budget* seconds.  Returns True when the job is empty."""
    vl = _view_layer(scene)
    if vl is None:
        job.pending.clear()
        return True
    orig_frame = scene.frame_current
    orig_sub = scene.frame_subframe
    t0 = time.perf_counter()
    use_mod = s.onion_use_modifiers
    limit = s.onion_vertex_limit
    point = s.path_bone_point
    job.sort(orig_frame)
    try:
        for f in job.order:
            reqs = job.pending.pop(f, None)
            if not reqs:
                continue
            scene.frame_set(f)
            dg = vl.depsgraph
            if dg is None:
                dg = bpy.context.evaluated_depsgraph_get()
            for key, want_point, want_skin in reqs:
                cache = CACHE.get(key)
                if cache is None:
                    continue
                ob = bpy.data.objects.get(key[0])
                if ob is None:
                    continue
                try:
                    ob_eval = ob.evaluated_get(dg)
                except Exception:
                    continue
                if want_point:
                    if cache.is_bone:
                        pb = ob_eval.pose.bones.get(cache.bone) if ob_eval.pose is not None else None
                        if pb is not None:
                            cache.pts[f] = _bone_point(pb, ob_eval.matrix_world, point)
                    else:
                        cache.mats[f] = np.array(ob_eval.matrix_world, dtype=np.float64)
                if want_skin:
                    if cache.onion_source == 'RIGID':
                        cache.mats[f] = np.array(ob_eval.matrix_world, dtype=np.float64)
                    else:
                        base, err = extract_skin(ob_eval, ob, use_mod, limit)
                        if base is not None:
                            cache.onion[f] = transform_skin(base, ob_eval.matrix_world)
                            cache.onion_error = ""
                        else:
                            cache.onion_error = err
            job.processed += 1
            if time.perf_counter() - t0 > budget:
                break
    finally:
        try:
            scene.frame_set(orig_frame, subframe=orig_sub)
        except Exception:
            pass
    return not job.pending


# ---------------------------------------------------------------------------
# Main update
# ---------------------------------------------------------------------------

def _touch(cache):
    STATE.tick += 1
    cache.last_touch = STATE.tick


def _evict_onion(cache, keep_frames, limit, cf):
    if len(cache.onion) <= limit:
        return
    keep = set(keep_frames)
    extra = [f for f in cache.onion if f not in keep]
    extra.sort(key=lambda f: abs(f - cf), reverse=True)
    for f in extra[: max(0, len(cache.onion) - limit)]:
        cache.onion.pop(f, None)


def _prune_caches(targets):
    keys = {t.key for t in targets}
    if len(CACHE) <= max(32, len(keys) * 2):
        return
    stale = [k for k in CACHE if k not in keys]
    stale.sort(key=lambda k: CACHE[k].last_touch)
    for k in stale[: len(stale) // 2]:
        CACHE.pop(k, None)


def _choose_path_engine(s, ob, t):
    if t.bone:
        if (s.path_engine != 'STEP' and s.path_bone_point != 'CENTER' and ob.mode == 'POSE'
                and ob.name not in STATE.native_failed):
            pb = ob.pose.bones.get(t.bone) if ob.pose is not None else None
            if pb is not None and pb.motion_path is None:
                return 'NATIVE'
        return 'STEP'
    if s.eval_mode == 'FAST' or s.path_engine == 'FCURVE':
        return 'FCURVE'
    if s.path_engine == 'STEP':
        return 'STEP'
    native_ok = ob.name not in STATE.native_failed and ob.motion_path is None
    if s.path_engine == 'NATIVE':
        return 'NATIVE' if native_ok else 'STEP'
    # AUTO
    if s.eval_mode != 'FULL' and build_fast_chain(ob) is not None:
        return 'FCURVE'
    return 'NATIVE' if native_ok else 'STEP'


def _rigid_base(ob, vl, s):
    """Local-space geometry for a rigid ghost source (evaluated at the current frame)."""
    try:
        if s.onion_use_modifiers:
            dg = None
            try:
                dg = bpy.context.evaluated_depsgraph_get()
            except Exception:
                dg = vl.depsgraph if vl is not None else None
            if dg is None:
                return None
            base, _err = extract_skin(ob.evaluated_get(dg), ob, True, s.onion_vertex_limit)
        else:
            base, _err = extract_skin(ob, ob, False, s.onion_vertex_limit)
        return base
    except Exception:
        return None


def update(budget=None, force_full=False):
    """Bring the caches up to date.

    Returns the delay in seconds until the next tick, or None when nothing is left to do."""
    scene = _scene()
    if scene is None:
        return None
    s = _settings(scene)
    if s is None or not s.enabled:
        return None
    vl = _view_layer(scene)
    if budget is None:
        budget = s.compute_budget
    t_start = time.perf_counter()

    STATE.deform_cache.clear()
    targets = resolve_targets(scene, vl, None)
    STATE.targets = targets
    STATE.target_keys = frozenset(t.key for t in targets)
    STATE.selection_sig = None
    _prune_caches(targets)
    if not targets:
        STATE.dirty_path = False
        STATE.dirty_onion = False
        STATE.job = None
        request_redraw()
        return None

    cf = scene.frame_current
    sig = eval_signature(s)
    playing = STATE.playing or compat.is_playing()
    modal = compat.blocking_modal_running()
    retry = False

    job = STATE.job
    if job is None or job.scene_name != scene.name:
        job = StepJob(scene.name)

    engines_used = set()
    native_bone_requests = {}   # arm name -> {bone: [frames]}

    for t in targets:
        ob = t.obj
        if ob is None:
            continue
        cache = CACHE.get(t.key)
        if cache is None:
            cache = TargetCache(t.key)
            CACHE[t.key] = cache
        _touch(cache)
        if cache.eval_sig != sig:
            cache.clear_path()
            cache.clear_onion()
            cache.eval_sig = sig
        if STATE.dirty_path:
            cache.clear_path()
        if STATE.dirty_onion:
            cache.clear_onion()

        # ------------------------------------------------------------ path
        if t.want_path:
            if cache.path_dirty:
                cache.mats.clear()
                cache.pts.clear()
                cache.keyframes = collect_keyframes(ob, t.bone or None)
                cache.path_engine = _choose_path_engine(s, ob, t)
                cache.path_dirty = False
            engine = cache.path_engine
            frames = path_frames_needed(scene, s, engine in ('FCURVE', 'NATIVE'))
            missing = [f for f in frames if not cache.has_frame_point(f)]
            if missing:
                if engine == 'FCURVE':
                    chain = build_fast_chain(ob, force=(s.eval_mode == 'FAST' or s.path_engine == 'FCURVE'))
                    if chain is None:
                        engine = cache.path_engine = 'STEP'
                    else:
                        for f in missing:
                            m = fast_matrix_at(chain, f)
                            if m is not None:
                                cache.mats[f] = np.array(m, dtype=np.float64)
                if engine == 'NATIVE':
                    if modal and not force_full:
                        retry = True
                    elif t.bone:
                        native_bone_requests.setdefault(ob.name, {})[t.bone] = missing
                    else:
                        # +1: the solver's end frame is exclusive in some versions
                        pts = native_object_path(ob, min(missing), max(missing) + 1)
                        if pts:
                            cache.pts.update(pts)
                            for f in missing:
                                if not cache.has_frame_point(f):
                                    job.add(f, t.key, True, False)
                        else:
                            STATE.native_failed.add(ob.name)
                            engine = cache.path_engine = 'STEP'
                if engine == 'STEP':
                    for f in missing:
                        job.add(f, t.key, True, False)
            engines_used.add(engine)
            cache.rebuild_path_arrays(display_frames(scene, s))

        # ----------------------------------------------------------- onion
        if t.want_onion:
            if cache.onion_dirty:
                cache.onion_keyframes = collect_onion_keyframes(ob)
                rigid = onion_is_rigid(ob, s.onion_use_modifiers)
                if s.eval_mode == 'FULL' and s.onion_use_modifiers:
                    rigid = False
                cache.onion_source = 'RIGID' if rigid else 'DEFORM'
                cache.onion.clear()
                cache.rigid_base = None
                cache.onion_dirty = False
                cache.onion_error = ""
            ghosts = onion_frame_list(cache, s, scene, cf)
            ghost_frames = [g[0] for g in ghosts]
            if cache.onion_source == 'RIGID':
                if cache.rigid_base is None:
                    base = _rigid_base(ob, vl, s)
                    if base is None:
                        cache.onion_source = 'DEFORM'
                    else:
                        cache.rigid_base = base
            if cache.onion_source == 'RIGID':
                missing = [f for f in ghost_frames if f not in cache.mats]
                if missing:
                    chain = None
                    if s.eval_mode != 'FULL':
                        chain = build_fast_chain(ob, force=(s.eval_mode == 'FAST'))
                    if chain is not None:
                        for f in missing:
                            m = fast_matrix_at(chain, f)
                            if m is not None:
                                cache.mats[f] = np.array(m, dtype=np.float64)
                    else:
                        for f in missing:
                            job.add(f, t.key, False, True)
            else:
                for f in ghost_frames:
                    if f not in cache.onion:
                        job.add(f, t.key, False, True)
            _evict_onion(cache, ghost_frames, s.cache_max_frames, cf)

    STATE.dirty_path = False
    STATE.dirty_onion = False

    # --------------------------------------------------- native bone paths
    for arm_name, bones in native_bone_requests.items():
        arm = bpy.data.objects.get(arm_name)
        if arm is None:
            continue
        lo = min(min(fr) for fr in bones.values())
        hi = max(max(fr) for fr in bones.values())
        res = native_bone_paths(arm, list(bones.keys()), lo, hi + 1, s.path_bone_point)
        for bone, frames in bones.items():
            cache = CACHE.get((arm_name, bone))
            if cache is None:
                continue
            pts = res.get(bone) if res else None
            if pts:
                cache.pts.update(pts)
                for f in frames:
                    if not cache.has_frame_point(f):
                        job.add(f, cache.key, True, False)
            else:
                STATE.native_failed.add(arm_name)
                cache.path_engine = 'STEP'
                for f in frames:
                    job.add(f, cache.key, True, False)
            cache.rebuild_path_arrays(display_frames(scene, s))

    # ------------------------------------------------------------ stepping
    delay = None
    if job.pending:
        if playing and s.pause_on_playback and not force_full:
            STATE.job = None
        elif modal and not force_full:
            STATE.job = job
            delay = 0.2
        else:
            done = run_step_job(job, scene, s, budget if not force_full else 1e9)
            for t in targets:
                cache = CACHE.get(t.key)
                if cache is not None and t.want_path:
                    cache.rebuild_path_arrays(display_frames(scene, s))
            if done:
                STATE.job = None
            else:
                STATE.job = job
                delay = 0.01
            engines_used.add('STEP')
    else:
        STATE.job = None
    if retry and delay is None:
        delay = 0.2

    STATE.last_compute_ms = (time.perf_counter() - t_start) * 1000.0
    if engines_used:
        STATE.last_engine_info = "/".join(sorted(engines_used))
    request_redraw()
    return delay


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _cancel_timer():
    fn = STATE.timer_fn
    if fn is not None:
        try:
            if bpy.app.timers.is_registered(fn):
                bpy.app.timers.unregister(fn)
        except Exception:
            pass
    STATE.timer_fn = None


def schedule(delay=None):
    """(Re)start the debounced update timer."""
    # ASC-PATCH P3: while suspended, only remember that an update was requested.
    if STATE.suspended:
        STATE.pending_while_suspended = True
        return
    s = _settings()
    if s is None or not s.enabled:
        return
    if not s.live_update:
        return
    if delay is None:
        delay = s.update_delay
    STATE.generation += 1
    gen = STATE.generation
    _cancel_timer()

    def _tick():
        if gen != STATE.generation:
            return None
        # ASC-PATCH P3: a tick that fires during a suspension is deferred to resume().
        if STATE.suspended:
            STATE.pending_while_suspended = True
            STATE.timer_fn = None
            return None
        if STATE.computing:
            return 0.05
        STATE.computing = True
        try:
            nxt = update()
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log("update failed: %s" % e)
            nxt = None
        finally:
            STATE.computing = False
        if nxt is None:
            STATE.timer_fn = None
        return nxt

    STATE.timer_fn = _tick
    try:
        bpy.app.timers.register(_tick, first_interval=max(0.0, float(delay)))
    except Exception as e:
        _log("could not register timer: %s" % e)


def invalidate(path=True, onion=True):
    """Settings changed: drop the affected caches and recompute."""
    STATE.dirty_path = STATE.dirty_path or path
    STATE.dirty_onion = STATE.dirty_onion or onion
    STATE.native_failed.clear()
    STATE.job = None
    schedule()
    request_redraw()


# ASC-PATCH P3: suspend()/resume()/invalidate_keys() for external edits. During a sculpt gesture the
# F-Curves change on every mouse move; the trail engine must neither recompute (frame stepping would fight
# the modal operator) nor drop the cached trail (it is drawn as the "ghost" of the original motion).

def suspend():
    """Stop reacting to depsgraph/frame changes until the matching resume(). Nests."""
    if STATE.suspended == 0:
        _cancel_timer()
        STATE.pending_while_suspended = False
    STATE.suspended += 1


def resume(keys=None):
    """End one suspend() level. On the last level, invalidate *keys* ((obj, bone) tuples; None = all
    targets) and schedule an update."""
    if STATE.suspended == 0:
        return
    STATE.suspended -= 1
    if STATE.suspended:
        return
    pending = STATE.pending_while_suspended
    STATE.pending_while_suspended = False
    if keys is None:
        keys = [t.key for t in STATE.targets]
    if keys or pending:
        invalidate_keys(keys or ())


def is_suspended():
    return STATE.suspended > 0


def invalidate_keys(keys):
    """Drop the path/onion caches of the given (obj_name, bone) keys and schedule a recompute."""
    for key in keys:
        c = CACHE.get(tuple(key))
        if c is not None:
            c.clear_path()
            c.clear_onion()
    STATE.job = None
    STATE.native_failed.clear()
    STATE.selection_sig = None
    schedule(delay=0.0)
    request_redraw()


def update_now(budget=1e9, force_full=True):
    """Run one synchronous update with the handler guard set (operators / tests)."""
    was = STATE.computing
    STATE.computing = True
    try:
        return update(budget=budget, force_full=force_full)
    finally:
        STATE.computing = was


def refresh_now():
    """Synchronous full recompute (Refresh operator)."""
    STATE.dirty_path = True
    STATE.dirty_onion = True
    STATE.native_failed.clear()
    STATE.job = None
    STATE.selection_sig = None
    _cancel_timer()
    return update_now(budget=1e9, force_full=True)


def clear_all():
    CACHE.clear()
    STATE.job = None
    STATE.dirty_path = True
    STATE.dirty_onion = True
    STATE.native_failed.clear()
    STATE.selection_sig = None
    STATE.deform_cache.clear()
    request_redraw()


def frame_changed(scene):
    """frame_change_post handler body."""
    if STATE.computing:
        return
    if STATE.suspended:  # ASC-PATCH P3
        STATE.pending_while_suspended = True
        return
    s = _settings(scene)
    if s is None or not s.enabled or not s.live_update:
        return
    if (STATE.playing or compat.is_playing()) and s.pause_on_playback:
        request_redraw()
        return
    schedule(delay=0.0)


def depsgraph_changed(scene, depsgraph):
    """depsgraph_update_post handler body."""
    if STATE.computing:
        return
    if STATE.suspended:  # ASC-PATCH P3: keep the cached trail; resume() invalidates explicitly
        STATE.pending_while_suspended = True
        return
    s = _settings(scene)
    if s is None or not s.enabled or not s.live_update:
        return
    STATE.deform_cache.clear()
    vl = _view_layer(scene)
    ctx = bpy.context
    changed = False
    try:
        sig = selection_signature(scene, vl, ctx)
    except Exception:
        sig = None
    if sig is None or sig != STATE.selection_sig:
        try:
            new_targets = resolve_targets(scene, vl, ctx)
        except Exception:
            new_targets = STATE.targets
        new_keys = frozenset(t.key for t in new_targets)
        changed = new_keys != STATE.target_keys
        if changed:
            STATE.targets = new_targets
            STATE.target_keys = new_keys
        STATE.selection_sig = sig
    targets = STATE.targets

    dirty = set()
    try:
        updates = depsgraph.updates
    except Exception:
        updates = ()
    self_tagged = STATE.self_tagged  # ASC-PATCH P4
    STATE.self_tagged = set()
    for upd in updates:
        try:
            if not (upd.is_updated_transform or upd.is_updated_geometry):
                continue
            k = compat.id_key(upd.id)
        except Exception:
            continue
        if k in self_tagged:  # ASC-PATCH P4: our own restore of the motion-path settings
            continue
        for t in targets:
            if k in t.deps:
                dirty.add(t.key)
    if dirty:
        for key in dirty:
            c = CACHE.get(key)
            if c is not None:
                c.clear_path()
                c.clear_onion()
        STATE.job = None
        STATE.native_failed.clear()
        schedule()
    elif changed:
        schedule(delay=0.0)


def playback_started(scene):
    STATE.playing = True
    request_redraw()


def playback_stopped(scene):
    STATE.playing = False
    schedule(delay=0.0)


def bake_frames(scene, frames):
    """Synchronously evaluate ghosts for all *frames* of every onion target (Bake operator).

    Returns the number of frames evaluated."""
    s = _settings(scene)
    if s is None:
        return 0
    STATE.computing = True
    try:
        update(budget=1e9, force_full=True)
        job = StepJob(scene.name)
        n = 0
        for t in STATE.targets:
            if not t.want_onion:
                continue
            cache = CACHE.get(t.key)
            if cache is None:
                continue
            if cache.onion_source == 'RIGID':
                ob = t.obj
                chain = build_fast_chain(ob, force=(s.eval_mode == 'FAST')) if (ob and s.eval_mode != 'FULL') else None
                for f in frames:
                    if f in cache.mats:
                        continue
                    if chain is not None:
                        m = fast_matrix_at(chain, f)
                        if m is not None:
                            cache.mats[f] = np.array(m, dtype=np.float64)
                            continue
                    job.add(f, t.key, False, True)
                    n += 1
            else:
                for f in frames:
                    if f not in cache.onion:
                        job.add(f, t.key, False, True)
                        n += 1
        if job.pending:
            run_step_job(job, scene, s, 1e9)
        return n
    finally:
        STATE.computing = False
        request_redraw()

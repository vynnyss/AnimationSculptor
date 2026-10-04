# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable façade over the vendored Live Motion Path engine (``trails/lmp``).

The rest of Animation Sculptor reads trails and controls the engine only through this module, so the
engine can be patched or replaced without touching the sculpt code (ADR 0001).

Trails are derived data: everything here may be dropped at any time and rebuilt from the Action.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

from .lmp import engine


@dataclass(frozen=True)
class Trail:
    """World-space trail of one target at the frames evaluated so far."""

    obj_name: str
    bone: str
    frames: np.ndarray      # int32 (N,)
    points: np.ndarray      # float32 (N, 3), world space
    keyframes: tuple        # frames (ints) where the target itself has keys
    complete: bool          # every displayed frame is evaluated
    engine: str             # 'FCURVE' | 'NATIVE' | 'STEP' | ''

    def point_at(self, frame):
        idx = np.nonzero(self.frames == int(frame))[0]
        return None if len(idx) == 0 else self.points[idx[0]]


def settings(scene):
    """Scene trail settings (``Scene.asc_trails``) or None when the add-on is not registered."""
    return getattr(scene, "asc_trails", None)


def is_enabled(scene) -> bool:
    s = settings(scene)
    return bool(s and s.enabled)


def set_enabled(scene, enabled: bool = True) -> None:
    s = settings(scene)
    if s is not None and s.enabled != enabled:
        s.enabled = enabled


def key_for(obj, bone: str | None = None) -> tuple:
    return (obj.name, bone or "")


def get_trail(obj, bone: str | None = None) -> Trail | None:
    """Cached trail for ``obj`` (or one of its pose bones), or None when nothing is cached yet."""
    return get_trail_by_key(key_for(obj, bone))


def get_trail_by_key(key: tuple) -> Trail | None:
    """Same as get_trail() for an (obj_name, bone) key."""
    cache = engine.CACHE.get(tuple(key))
    if cache is None or cache.path_frames is None or cache.path_points is None:
        return None
    return Trail(
        obj_name=cache.obj_name,
        bone=cache.bone,
        frames=cache.path_frames.copy(),
        points=cache.path_points.copy(),
        keyframes=tuple(cache.keyframes),
        complete=bool(cache.path_complete),
        engine=cache.path_engine,
    )


def targets() -> list[tuple]:
    """(obj_name, bone) of the current trail targets."""
    return [t.key for t in engine.STATE.targets]


def update_now() -> None:
    """Synchronous full update of the current targets (tests, operators). No-op while suspended."""
    if engine.is_suspended():
        return
    engine.update_now(budget=1e9, force_full=True)


def refresh() -> None:
    """Drop every cache and recompute synchronously."""
    if engine.is_suspended():
        return
    engine.refresh_now()


def invalidate(keys=None) -> None:
    """Recompute the given (obj_name, bone) keys (None = all current targets) on the next tick."""
    if keys is None:
        keys = targets()
    engine.invalidate_keys(keys)


def suspend() -> None:
    """Freeze the engine: no recompute, cached trails stay drawn as they were. Nests."""
    engine.suspend()


def resume(keys=None) -> None:
    """End one suspend(); on the outermost level invalidate ``keys`` (None = all targets)."""
    engine.resume(keys)


def is_suspended() -> bool:
    return engine.is_suspended()


@contextmanager
def suspended(keys=None):
    """``with provider.suspended(keys): ...`` — always resumes, even on error."""
    suspend()
    try:
        yield
    finally:
        resume(keys)


def _adapter_bone_point(ob, bone):
    """Trail point of a control from its rig adapter: TAIL for rotation-only (FK) controls, HEAD for
    translation controls; None (global setting) for anything that is not a control."""
    if ob.type != 'ARMATURE':
        return None
    from .. import rig

    info = rig.get_adapter(ob).classify(ob, bone)
    return None if info is None else info.reference


def use_adapter_bone_points(enabled: bool = True) -> None:
    engine.BONE_POINT_RESOLVER = _adapter_bone_point if enabled else None


# Past / future convention of Animation Sculptor (design/ephemeral-rig.md, "Paleta passado/futuro"):
# past red, future green, current frame white — trails, onion skin and the time ruler alike.
PAST_COLOR = (0.95, 0.22, 0.18)
FUTURE_COLOR = (0.25, 0.85, 0.32)
CURRENT_COLOR = (1.0, 1.0, 1.0)


def apply_palette(scene) -> bool:
    """Set the LMP past/future colours of the trails and the onion skin to the Animation Sculptor
    palette (plain settings, no patch: the user may change them afterwards in the Trails panel)."""
    s = settings(scene)
    if s is None:
        return False
    s.path_color_past = PAST_COLOR
    s.path_color_future = FUTURE_COLOR
    s.path_current_color = CURRENT_COLOR
    s.onion_color_before = PAST_COLOR
    s.onion_color_after = FUTURE_COLOR
    return True


# --- Onion skin (design/sculpt-ux.md, "Onion skin") ---------------------------------------------------

_LMP_DEFAULT_BEFORE = (0.145, 0.62, 0.2)


def set_onion(scene, show: bool) -> None:
    """Turn the LMP onion skin on or off (``Scene.asc_trails.onion_show``). On turn-on the past/future
    palette is applied only while the onion colours are still the LMP defaults, so user colours win."""
    s = settings(scene)
    if s is None:
        return
    if show and tuple(round(c, 3) for c in s.onion_color_before) == _LMP_DEFAULT_BEFORE:
        s.onion_color_before = PAST_COLOR
        s.onion_color_after = FUTURE_COLOR
    if s.onion_show != bool(show):
        s.onion_show = bool(show)


def sync_onion_window(scene, radius_past: float, radius_future: float, max_ghosts: int = 12) -> tuple:
    """Ghosts per frame covering ``[f0 − radius_past, f0 + radius_future]`` (at most ``max_ghosts`` per
    side, one shared step). Returns ``(before, after, step)``. Radius 0 on a side: no ghost there."""
    from ..core import onion

    before, after, step = onion.window(radius_past, radius_future, max_ghosts)
    s = settings(scene)
    if s is None:
        return before, after, step
    if s.onion_mode != 'FRAMES':
        s.onion_mode = 'FRAMES'          # ghosts per frame, never per keyframe
    if s.onion_step != step:
        s.onion_step = step
    if s.onion_before != before:
        s.onion_before = before
    if s.onion_after != after:
        s.onion_after = after
    return before, after, step


class _Spread:
    spacing = None      # explicit spacing per ghost step (None = automatic)
    auto = {}           # obj_name -> spacing measured when the spread was enabled


def _character_width(obj_name: str) -> float:
    """Max of the world bounding-box X/Y extent of the object and its mesh children (rest bounds)."""
    import bpy
    from mathutils import Vector

    ob = bpy.data.objects.get(obj_name)
    if ob is None:
        return 1.0
    meshes = [c for c in ob.children_recursive if c.type == 'MESH']
    pts = []
    for o in (meshes or [ob]):      # the body, not the rig widgets (control shapes are wider than the character)
        pts.extend(o.matrix_world @ Vector(c) for c in o.bound_box)
    ext = max(max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts))
    return ext if ext > 1e-6 else 1.0


def spread_spacing(obj_name: str) -> float:
    """World distance between consecutive ghosts: the explicit spacing, else 1.1 × the character width
    (measured once per enable, so scrubbing does not make the ghosts breathe)."""
    if _Spread.spacing is not None:
        return float(_Spread.spacing)
    sp = _Spread.auto.get(obj_name)
    if sp is None:
        sp = _Spread.auto[obj_name] = _character_width(obj_name) * 1.1
    return sp


def ghost_offset(context, obj_name: str, frame: int, current_frame: int, rv3d=None):
    """World-space offset of the ghost at ``frame``: along the view's right axis (row 0 of
    ``rv3d.view_matrix``), past to the left, future to the right. None when the ghost stays in place
    (the current frame, or no 3D view)."""
    from mathutils import Vector

    from ..core import onion

    if frame == current_frame:
        return None
    if rv3d is None:
        rv3d = getattr(context, "region_data", None)
    if rv3d is None:
        return None
    s = settings(context.scene)
    step = s.onion_step if s is not None else 1
    dist = onion.spread_offset(frame, current_frame, step, spread_spacing(obj_name))
    v = Vector(rv3d.view_matrix[0][:3]).normalized() * dist
    return (v.x, v.y, v.z)


def set_onion_spread(enabled: bool, spacing: float | None = None) -> None:
    """Expanded onion: each ghost drawn shifted sideways on screen ∝ (f − f₀), a film strip (drawing
    hook only, LMP patch P11). ``spacing`` per ghost step in world units; None = from the character width."""
    import bpy

    from .lmp import draw

    _Spread.spacing = None if spacing is None else float(spacing)
    _Spread.auto = {}
    draw.GHOST_OFFSET = ghost_offset if enabled else None
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


def onion_spread_enabled() -> bool:
    from .lmp import draw

    return draw.GHOST_OFFSET is not None


def stats() -> dict:
    st = engine.STATE
    return {
        "targets": len(st.targets),
        "last_compute_ms": st.last_compute_ms,
        "engines": st.last_engine_info,
        "pending_frames": st.job.remaining if st.job is not None else 0,
        "suspended": st.suspended,
    }

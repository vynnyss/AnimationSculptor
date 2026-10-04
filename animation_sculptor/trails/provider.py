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
    cache = engine.CACHE.get(key_for(obj, bone))
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


def stats() -> dict:
    st = engine.STATE
    return {
        "targets": len(st.targets),
        "last_compute_ms": st.last_compute_ms,
        "engines": st.last_engine_info,
        "pending_frames": st.job.remaining if st.job is not None else 0,
        "suspended": st.suspended,
    }

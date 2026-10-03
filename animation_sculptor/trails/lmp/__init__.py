# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (__init__.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
"""
Live Motion Path & Onion Skin (vendored)
========================================

Live-updating motion paths for objects and pose bones, plus mesh onion
skinning. Vendored into Animation Sculptor; the rest of the add-on talks to it
only through ``animation_sculptor.trails.provider``.
"""

# ASC-PATCH P2: imports stay package-relative; ``prefs`` was dropped (P5) and registration is driven by
# ``animation_sculptor.trails`` instead of being an add-on entry point.
from . import compat, props, engine, draw, ops, ui, handlers  # noqa: F401

_modules = (props, ops, ui, handlers, draw)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        try:
            m.unregister()
        except Exception as e:
            print("[Live Motion Onion] unregister error in %s: %s" % (m.__name__, e))
    try:
        engine.clear_all()
    except Exception:
        pass

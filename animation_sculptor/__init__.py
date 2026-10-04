# SPDX-License-Identifier: GPL-3.0-or-later
"""Animation Sculptor — deterministic motion sculpting for Blender 5.2.

The package top level deliberately does not import ``bpy``: ``core`` must stay
importable (and unit-testable) outside Blender. Blender-facing modules are
imported lazily inside ``register()`` / ``unregister()``.
"""

_modules = []


def _blender_modules():
    from .ui import prefs, panels
    from . import trails

    # panels before trails: the trail panels are nested under the main panel
    return (prefs, panels, trails)


def register():
    global _modules
    _modules = list(_blender_modules())
    for module in _modules:
        module.register()


def unregister():
    global _modules
    for module in reversed(_modules):
        try:
            module.unregister()
        except Exception as exc:  # never block disabling the add-on
            print(f"[Animation Sculptor] unregister error in {module.__name__}: {exc}")
    _modules = []

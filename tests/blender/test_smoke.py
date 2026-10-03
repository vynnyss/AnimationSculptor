# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke tests inside Blender 5.2: the extension installs, registers and unregisters cleanly."""

import importlib

import addon_utils
import bpy


def _raise(exc):
    raise exc


def test_blender_is_5_2():
    assert bpy.app.version[:2] == (5, 2)


def test_addon_enabled(addon_module):
    _loaded_default, loaded_state = addon_utils.check(addon_module)
    assert loaded_state, f"{addon_module} is not enabled"
    assert addon_module in bpy.context.preferences.addons


def test_panel_and_preferences_registered(addon_module):
    assert hasattr(bpy.types, "ASC_PT_main")
    assert bpy.context.preferences.addons[addon_module].preferences is not None


def test_disable_enable_cycle(addon_module):
    addon_utils.disable(addon_module, default_set=True)
    assert not hasattr(bpy.types, "ASC_PT_main")
    addon_utils.enable(addon_module, default_set=True, handle_error=_raise)
    assert hasattr(bpy.types, "ASC_PT_main")


def test_core_importable_from_installed_extension(addon_module):
    core = importlib.import_module(addon_module + ".core")
    assert core.__name__.endswith("animation_sculptor.core")

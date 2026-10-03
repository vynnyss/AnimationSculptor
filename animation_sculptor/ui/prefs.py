# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences."""

import bpy

# ``__package__`` is "<root package>.ui"; preferences are keyed by the root
# add-on module name (``bl_ext.<repo>.animation_sculptor`` when installed).
ADDON_ID = __package__.rpartition(".")[0]


class ASC_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Animation Sculptor: painel em 3D Viewport › Sidebar (N) › Animation Sculptor.")


def get_prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


classes = (ASC_Preferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

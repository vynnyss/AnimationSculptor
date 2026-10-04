# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences (per user, not saved in the .blend)."""

import bpy
from bpy.props import FloatProperty, IntProperty

# ``__package__`` is "<root package>.ui"; preferences are keyed by the root
# add-on module name (``bl_ext.<repo>.animation_sculptor`` when installed).
ADDON_ID = __package__.rpartition(".")[0]

DEFAULTS = {"hit_radius_px": 12, "precision": 0.1, "spacing_px": 250.0, "retime_px_per_frame": 20.0}


class ASC_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    hit_radius_px: IntProperty(
        name="Raio de clique (px)",
        description="Distância em pixels para pegar um ponto da trail",
        default=DEFAULTS["hit_radius_px"], min=4, max=40,
    )
    precision: FloatProperty(
        name="Precisão com Shift",
        description="Fator aplicado ao movimento do mouse com Shift pressionado",
        default=DEFAULTS["precision"], min=0.01, max=1.0,
    )
    spacing_px: FloatProperty(
        name="Sensibilidade do spacing (px)",
        description="Pixels de arrasto para uma mudança total de favor/ease",
        default=DEFAULTS["spacing_px"], min=50.0, max=2000.0,
    )
    retime_px_per_frame: FloatProperty(
        name="Retime em trail parada (px/frame)",
        description="Pixels de arrasto horizontal por frame quando o controle não se move perto da key",
        default=DEFAULTS["retime_px_per_frame"], min=2.0, max=200.0,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        col = layout.column()
        col.prop(self, "hit_radius_px")
        col.prop(self, "precision")
        col.prop(self, "spacing_px")
        col.prop(self, "retime_px_per_frame")
        layout.label(text="Configurações por cena (raio, falloff, escopo, spacing) ficam no painel N › Animation Sculptor.",
                     icon='INFO')
        layout.label(text="Atalhos: Preferences › Keymap › Pose › 'Animation Sculptor' e '3D View Tool: Pose, Animation Sculptor'.",
                     icon='KEYINGSET')


def get_prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def value(name):
    """Preference value, or its default when the add-on preferences are not available."""
    prefs = get_prefs()
    return getattr(prefs, name, DEFAULTS[name]) if prefs is not None else DEFAULTS[name]


classes = (ASC_Preferences,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

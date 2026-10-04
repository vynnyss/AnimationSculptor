# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings of the sculpt tool (``Scene.asc_sculpt``). Saved with the .blend like any scene
setting; the only state Animation Sculptor persists besides the Action (project rule)."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty

FALLOFF_ITEMS = (
    ('SMOOTH', "Suave", "Transição suave (como o proportional editing do Blender)"),
    ('SPHERE', "Esfera", ""),
    ('SHARP', "Agudo", ""),
    ('LINEAR', "Linear", ""),
    ('CONSTANT', "Constante", "Todas as keys no raio movem por inteiro"),
)
SCOPE_ITEMS = (
    ('CHARACTER', "Personagem", "Retime/spacing movem todas as F-Curves do rig (a pose inteira)"),
    ('SELECTED', "Selecionados", "Retime/spacing só nos bones selecionados (+ o arrastado)"),
)
POLICY_ITEMS = (
    ('PRESERVE_PATH', "Preservar caminho", "Spacing nunca muda o caminho; a tangente pode quebrar na key"),
    ('PRESERVE_SMOOTHNESS', "Preservar suavidade",
     "Spacing mantém a tangente contínua na key; o segmento vizinho muda um pouco"),
)


class ASC_SculptSettings(bpy.types.PropertyGroup):
    soft_radius: FloatProperty(
        name="Raio",
        description="Raio do soft grab em frames (0 = só a key arrastada). Roda do mouse ou [ ] durante o arrasto",
        default=0.0, min=0.0, max=500.0, step=100, precision=0,
    )
    falloff: EnumProperty(name="Falloff", items=FALLOFF_ITEMS, default='SMOOTH',
                          description="Forma do falloff do soft grab")
    timing_scope: EnumProperty(name="Escopo do tempo", items=SCOPE_ITEMS, default='CHARACTER')
    spacing_policy: EnumProperty(name="Spacing", items=POLICY_ITEMS, default='PRESERVE_PATH')
    hide_on_playback: BoolProperty(
        name="Esconder overlay no playback",
        description="Não desenhar o realce/preview do sculpt enquanto a animação toca",
        default=True,
    )


def get(context=None):
    """Settings of the current scene (None outside a scene / before registration)."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    return getattr(scene, "asc_sculpt", None) if scene is not None else None


classes = (ASC_SculptSettings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asc_sculpt = PointerProperty(type=ASC_SculptSettings)


def unregister():
    if hasattr(bpy.types.Scene, "asc_sculpt"):
        del bpy.types.Scene.asc_sculpt
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

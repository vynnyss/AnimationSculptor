# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings of the sculpt tool (``Scene.asc_sculpt``). Saved with the .blend like any scene
setting; the only state Animation Sculptor persists besides the Action (project rule)."""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

SETTINGS_VERSION = 1    # 1 = asymmetric radius (0.4.0); 0 = files saved by 0.3.0 (single soft_radius)

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


def _sync_linked(source, target):
    def update(self, _context):
        if self.radius_linked and getattr(self, target) != getattr(self, source):
            setattr(self, target, getattr(self, source))
    return update


def _upd_linked(self, _context):
    if self.radius_linked and self.radius_future != self.radius_past:
        self.radius_future = self.radius_past


class ASC_SculptSettings(bpy.types.PropertyGroup):
    soft_radius: FloatProperty(
        name="Raio (0.3.0)",
        description="Raio simétrico salvo pela versão 0.3.0; ao abrir o arquivo vira o raio passado e o futuro",
        default=0.0, min=0.0, max=500.0, step=100, precision=0,
    )
    radius_past: FloatProperty(
        name="Passado",
        description="Raio do soft grab para trás do frame arrastado, em frames (0 = nenhuma key anterior). "
                    "Arraste a ponta vermelha da régua, ou roda do mouse / [ ] durante o arrasto",
        default=0.0, min=0.0, max=500.0, step=100, precision=0, update=_sync_linked("radius_past", "radius_future"),
    )
    radius_future: FloatProperty(
        name="Futuro",
        description="Raio do soft grab para frente do frame arrastado, em frames (0 = nenhuma key seguinte). "
                    "Arraste a ponta verde da régua, ou roda do mouse / [ ] durante o arrasto",
        default=0.0, min=0.0, max=500.0, step=100, precision=0, update=_sync_linked("radius_future", "radius_past"),
    )
    radius_linked: BoolProperty(
        name="Ligar raios",
        description="Passado e futuro com o mesmo raio",
        default=True, update=_upd_linked,
    )
    show_time_ruler: BoolProperty(
        name="Régua de tempo",
        description="Mostrar a régua de tempo (janela do soft grab) embaixo do viewport com a ferramenta ativa",
        default=True,
    )
    ephemeral_scope: EnumProperty(
        name="Escopo FK",
        items=(('LIMB', "Membro", "Arrastar a ponta de um controle FK gira o membro inteiro até ele (braço, perna)"),
               ('TIP', "Ponta", "Arrastar a ponta de um controle FK gira só aquele bone, para apontar"),
               ('BODY', "Corpo", "Arrastar a ponta do bone (tronco, pescoço, cabeça) gira a coluna; "
                                 "pernas FK ficam com os pés no lugar")),
        default='LIMB',
        description="O que o gesto em controles só de rotação (FK) pode girar",
    )
    tip_orientation: EnumProperty(
        name="Orientação da ponta",
        items=(('WORLD', "Mundo", "A mão/pé mantém a orientação no mundo (como ao arrastar um controle IK)"),
               ('LOCAL', "Local", "A mão/pé mantém a rotação local e gira junto com o antebraço/canela")),
        default='WORLD',
    )
    palette_applied: BoolProperty(
        name="Paleta aplicada",
        description="A paleta passado/futuro já foi aplicada às trails desta cena (só na primeira vez)",
        default=False, options={'HIDDEN'},
    )
    settings_version: IntProperty(default=0, options={'HIDDEN'})
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


def migrate(scene) -> bool:
    """Files saved by 0.3.0 have one symmetric ``soft_radius``: it becomes both sides. Idempotent."""
    s = getattr(scene, "asc_sculpt", None)
    if s is None or s.settings_version >= SETTINGS_VERSION:
        return False
    if s.soft_radius > 0.0:
        s.radius_linked = True
        s.radius_past = s.soft_radius
        s.radius_future = s.soft_radius
    s.settings_version = SETTINGS_VERSION
    return True


def migrate_all():
    for scene in bpy.data.scenes:
        try:
            migrate(scene)
        except Exception as exc:  # a read-only/linked scene must not break loading
            print(f"[Animation Sculptor] settings migration skipped for {scene.name!r}: {exc}")


@persistent
def _load_post(*_args):
    migrate_all()


def _migrate_timer():
    migrate_all()
    return None


classes = (ASC_SculptSettings,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asc_sculpt = PointerProperty(type=ASC_SculptSettings)
    if _load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post)
    # enabling the add-on with a file already open: bpy.data is restricted during register()
    bpy.app.timers.register(_migrate_timer, first_interval=0.0)


def unregister():
    while _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    if bpy.app.timers.is_registered(_migrate_timer):
        bpy.app.timers.unregister(_migrate_timer)
    if hasattr(bpy.types.Scene, "asc_sculpt"):
        del bpy.types.Scene.asc_sculpt
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

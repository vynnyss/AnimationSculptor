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


def _provider():
    from ..trails import provider

    return provider


def _sync_onion(self, context):
    """Onion skin follows the toggles and covers the time ruler's window (design/sculpt-ux.md)."""
    provider = _provider()
    scene = context.scene if context is not None else None
    if scene is None:
        return
    if hasattr(provider, "set_onion"):
        provider.set_onion(scene, self.onion_show)
    if self.onion_show and hasattr(provider, "sync_onion_window"):
        # a window of 0 frames would show no ghost at all: fall back to a few frames each side
        rp, rf = (self.radius_past, self.radius_future) if self.radius_past or self.radius_future else (6.0, 6.0)
        provider.sync_onion_window(scene, rp, rf)
    if hasattr(provider, "set_onion_spread"):
        provider.set_onion_spread(self.onion_show and self.onion_spread)


def _upd_radius(source, target):
    linked = _sync_linked(source, target)

    def update(self, context):
        linked(self, context)
        if self.onion_show:
            _sync_onion(self, context)
    return update


def _upd_show_rig(self, context):
    """Show/hide the bones (and the Rigify control shapes) in every 3D viewport: grab the body with the rig
    out of the way; the animation keeps going to the controls (ADR 0013)."""
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                overlay = getattr(area.spaces.active, "overlay", None)
                if overlay is not None and overlay.show_bones != self.show_rig:
                    overlay.show_bones = self.show_rig


def _upd_mode(self, context):
    """The Trail mode needs the trails: switching to it turns them on (the Corpo mode leaves them as they are)."""
    scene = getattr(context, "scene", None)
    if scene is not None and self.interaction_mode == 'TRAIL':
        _provider().set_paths(scene, True)
    provider = _provider()
    if hasattr(provider, "engine"):
        provider.engine.targets_changed()       # Corpo shows the character's targets, Trail the selection's


def _upd_trails(self, context):
    scene = getattr(context, "scene", None)
    if scene is not None:
        _provider().set_paths(scene, self.show_trails)


def _upd_retarget(self, _context):
    provider = _provider()
    if hasattr(provider, "engine"):
        provider.engine.targets_changed()


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
        default=0.0, min=0.0, max=500.0, step=100, precision=0, update=_upd_radius("radius_past", "radius_future"),
    )
    radius_future: FloatProperty(
        name="Futuro",
        description="Raio do soft grab para frente do frame arrastado, em frames (0 = nenhuma key seguinte). "
                    "Arraste a ponta verde da régua, ou roda do mouse / [ ] durante o arrasto",
        default=0.0, min=0.0, max=500.0, step=100, precision=0, update=_upd_radius("radius_future", "radius_past"),
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
    show_trails: BoolProperty(
        name="Trails", description="Mostrar as trajetórias (trails) dos controles selecionados",
        default=True, update=_upd_trails,
    )
    trail_all: BoolProperty(
        name="Todas as trails",
        description="Mostrar as trails de todas as partes do personagem (no modo Trail, todas podem ser editadas). "
                    "Desligado: só a da parte do corpo tocada por último",
        default=False, update=_upd_retarget,
    )
    interaction_mode: EnumProperty(
        name="Modo",
        items=(('BODY', "Corpo", "Agarre o corpo do personagem: pose e arco no frame atual"),
               ('TRAIL', "Trail", "Agarre a trajetória: timing e spacing (Ctrl+arrastar), como nas trails")),
        default='BODY', update=_upd_mode,
    )
    show_rig: BoolProperty(
        name="Esqueleto",
        description="Mostrar os bones do esqueleto (ou os controles do Rigify) no viewport. Desligado, o corpo é "
                    "agarrado pela malha e a animação continua sendo gravada nos bones",
        default=True, update=_upd_show_rig,
    )
    onion_show: BoolProperty(
        name="Onion skin", description="Fantasmas da pose nos frames da janela da régua (passado vermelho, futuro verde)",
        default=False, update=_sync_onion,
    )
    onion_spread: BoolProperty(
        name="Onion expandida",
        description="Espalha os fantasmas para os lados da tela (passado à esquerda, futuro à direita)",
        default=False, update=_sync_onion,
    )
    clip_negative: BoolProperty(
        name="Cortar no frame 0",
        description="Os gestos nunca escrevem keys antes do frame 0 (a janela da régua é cortada ali)",
        default=True,
    )
    key_mode: EnumProperty(
        name="Keys",
        items=(('POSE', "Pose a pose", "Arrastar muda a pose do frame atual (uma key por canal ali); as poses "
                                        "vizinhas na janela mudam só um pouco (Influência nas poses)"),
               ('DENSE', "Densas", "Arrastar grava uma key por frame em toda a janela da régua (rig efêmero)")),
        default='POSE',
    )
    pose_influence: FloatProperty(
        name="Influência nas poses",
        description="Quanto as poses-chave vizinhas (dentro da janela da régua) acompanham um arrasto feito em "
                    "outro frame (0 = travadas)",
        default=0.25, min=0.0, max=1.0, subtype='FACTOR',
    )
    smooth_mode: EnumProperty(
        name="Suavizar",
        items=(('TRAIL', "Trail", "Suaviza o caminho da parte no espaço (a trail) e resolve o membro para segui-lo"),
               ('ROTATION', "Rotações", "Suaviza as curvas de rotação dos bones do membro, frame a frame")),
        default='TRAIL',
    )
    smooth_strength: FloatProperty(
        name="Força do Smooth", description="Quanto cada passe do pincel Smooth aproxima a curva da média",
        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    )
    smooth_sigma: FloatProperty(
        name="Largura do Smooth", description="Desvio padrão do filtro gaussiano, em frames",
        default=1.5, min=0.25, max=10.0,
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


def resync_all():
    """Derived drawing state that lives outside the file (the expanded-onion hook) follows the saved toggles."""
    import bpy

    scene = bpy.context.scene if bpy.context is not None else None
    s = getattr(scene, "asc_sculpt", None) if scene is not None else None
    if s is None:
        return
    provider = _provider()
    if hasattr(provider, "set_onion_spread"):
        provider.set_onion_spread(s.onion_show and s.onion_spread)


@persistent
def _load_post(*_args):
    migrate_all()
    try:
        resync_all()
    except Exception as exc:
        print(f"[Animation Sculptor] resync after load: {exc}")


def _migrate_timer():
    migrate_all()
    try:
        resync_all()
    except Exception:
        pass
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

# Motion Trail (Bart Crouch) — análise

- Fonte: https://github.com/sobotka/blender-addons-contrib/blob/master/animation_motion_trail.py (espelho de addons-contrib, último commit do espelho 2023-01-30).
- `bl_info`: versão 3.1.3, Blender 2.80, aviso "Needs bgl draw update". 1.833 linhas, arquivo único.
- Licença: **GPL-2.0-or-later** (bloco de licença no cabeçalho) — compatível com GPL-3.
- Estratégia: **extrair algoritmos e portar** para `core/` com APIs 5.2. Nada de arquitetura/renderização reaproveitada ([ADR 0007](../decisions/0007-gpl-and-reuse-policy.md)).

## Estrutura

| Função | O que faz | Estado | Uso |
|---|---|---|---|
| `get_curves` | Acha F-Curves `location` de objeto/pose bone via `action.fcurves` (ou NLA) | API removida no 5.x | substituído por `anim/action_io` |
| `fake_fcurve` | Curva constante quando falta um eixo | ok | ideia reaproveitada (canal sem F-Curve) |
| `screen_to_world` / `world_to_screen` | Tela ⇄ mundo com `view3d_utils`; correção de canto para `w<0` | usa `*` para matmul (2.7x) | **portado** para `interaction/picking` com `@` |
| `get_location` | Posição por frame (F-Curve direto ou `frame_set`) | — | substituído pelo LMP |
| `get_original_animation_data` | Snapshot de keys/handles no início do drag | — | ideia → `anim/snapshot` |
| `calc_callback` / `draw_callback` | Cálculo e desenho (bgl) | obsoleto | descartado |
| `drag` modo *location*, key | Δ mundo → espaço do bone → soma Δ em key e handles | ver limitação abaixo | **algoritmo base do Grab** |
| `drag` modo *location*, handle | Move handle, converte `AUTO*`→`ALIGNED`, `VECTOR`→`FREE`, espelha o oposto mantendo proporção | ok | **regras de handle portadas** |
| `drag` modo *timing*, timebead | Move frame escalando proporcionalmente keys entre extremos do range (`shift_low/high`) | ok | **Retime com stretch** (Escopo 2) |
| `drag` modo *timing*, key | Move key no tempo limitado aos vizinhos; direção pelo ângulo entre Δ e vizinhos na trail; intensidade normalizada pela região | ok | **mapeamento tela→tempo do Retime** |
| `drag` modo *speed*, timebead | Ajusta `handle.x` (comprimento temporal) do key mais próximo ⇒ muda velocidade | ok | **base do Spacing** |
| `cancel_drag` | Restaura snapshot | ok | ideia → cancel |
| `insert_keyframe`, `set_handle_type` | utilitários | API antiga | reescritos |
| `MotionTrailOperator.modal` | Modal de longa duração com `PASS_THROUGH` | padrão válido | fallback de interação ([ADR 0010](../decisions/0010-tool-gizmo-modal-interaction.md)) |

## Limitações a não herdar

- **Espaço do bone**: usa `action_ob.matrix_world.inverted() * edit_bone.matrix` (pose de *repouso*). Ignora a pose animada dos pais ⇒ errado quando o pai se move/gira. Nós usamos `P(f)` por frame (algoritmo do Motiontrail3D).
- Só canais `location`; rotação não é tratada.
- Edita uma key de cada vez; sem falloff.
- Timing por controle (desincroniza poses). Nós fazemos timing por pose key no escopo do personagem.
- `bgl`, `*` como matmul, `action.fcurves`: tudo obsoleto no 5.x.

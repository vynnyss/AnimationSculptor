# Editable Motion Trails 3D (port 4.1) — análise

- Repo: https://github.com/eternal2dlife/Editable_Motion_Trails_3D_Blender4.1_Update (último commit 2025-04-12).
- **Achado importante**: não é um port do Motion Trail do Bart Crouch. É uma atualização para Blender 4.1 do **Motiontrail3D**, de **Wayde Brandon Moss** (`bl_info.author`), originalmente vendido na Blender Market/Superhive sob GPL. Arquivo único `motion_trail_3D_B41_FIXED.py`, 7.563 linhas, "Build as of 8/26/24".
- Licença: **GPL-3.0** (`LICENSE` no repo; cabeçalho diz "provided under GNU General Public License").
- Estratégia: **referência de port + extrair algoritmos específicos**. Arquitetura **não** reaproveitada.

## Arquitetura do Motiontrail3D (e por que não seguimos)

- Cria **objetos reais na cena** (empties/meshes em grupo `__gen_motiontrail3d__`) como controles arrastáveis para cada key e handle; usa os gizmos de transform do Blender para movê-los e sincroniza de volta para as F-Curves num `depsgraph_update` handler.
- Vantagem: reaproveita G/R/S, snapping e proporcional nativos.
- Problemas para nós: estado na cena (frágil em save/reload/undo, poluição do outliner), sincronização bidirecional complexa (flags `ignore_control_update_once`, `ignore_time_sync_once`), um operador modal gigante (~4.000 linhas), `action.fcurves` (removido no 5.x), ainda importa `bgl`.
- Conclusão: contraria o princípio "nada de estado frágil" de [project.md](../project.md).

## O que extrair

| Algoritmo | Onde (no arquivo) | Uso |
|---|---|---|
| ~~**Matriz de espaço-pai por frame** `P(f) = arm.matrix_world @ pb.matrix @ pb.matrix_basis.inverted()`~~ — **não reutilizada** (ver limitação abaixo) | `calculate_parent_matrix_cache` (~l. 6643) | só referência; `anim/spaces.py` usa `Object.convert_space` |
| Escrita mundo→local: `local = (P(f)⁻¹ @ M_basis_novo).to_translation()`, offsets aplicados a handles não selecionados | `write_controls_to_channels` (~l. 5323) | Grab |
| Utilitários Bézier: `evaluate_bezier`, `bezier_split`, `bezier_search_frame` (acha `t` para um frame), `split_bezier_keys` | ~l. 416–520 | `core/bezier.py` |
| "Triplets" (key + 2 handles) e valores de controle por canal alinhando keys de canais diferentes | `calculate_triplet_control_values`, `append_triplets_from_channel` | referência p/ canais com keys desalinhadas |
| Regras de handle: `align_left/right_handle`, `offset_*_handle`, `is_handle_type_editable` | ~l. 827–880 | regras de handle |
| Trail relativa a outro objeto/bone (*relative parent*) | `relative_parent_*` | Escopo pós-MVP (trail no espaço do personagem/root) |
| Trails de rotação (modo ROTATION, tracking points) | vários | referência para FK (Escopo 4) |
| Profiler embutido | `ProfilerStack` | ideia para debugging |

## Diferenças de API 2.9 → 4.1 que o port mostra

Matmul `@`, `gpu`/`batch_for_shader` no lugar de `bgl` (parcial), `context.temp_override` vs dict override. O salto 4.1 → 5.2 (slotted actions, `PoseBone.select`, remoção de `bgl`) **não** está coberto — o LMP é a referência para isso.

## Limitação encontrada: `P(f)` errada com `use_local_location = False`

A fórmula `arm.matrix_world @ pb.matrix @ pb.matrix_basis.inverted()` só reproduz o espaço em que `location` atua quando `Bone.use_local_location` é `True`. Com `False` — caso dos controles IK do Rigify (`hand_ik`, `foot_ik`; o `torso` tem `True`) — `location` age ao longo dos eixos do pai e não dos do bone, e o delta de mundo convertido com a fórmula sai na direção errada (pego pelo teste de grab do spike, 2026-10-03). Por isso `anim/spaces.py::location_space` não porta esse algoritmo: pede ao Blender (`Object.convert_space` LOCAL → POSE com `location` 0 e eixos unitários; 4 conversões bastam porque o head é afim em `location`), o que respeita `use_local_location`, herança de rotação/escala e a pose do pai. Coberto por `test_location_space_maps_location_to_head` (tol 1e-5). O Motiontrail3D segue útil só como referência dos demais algoritmos desta tabela.

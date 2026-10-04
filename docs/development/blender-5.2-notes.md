# Notas de API — Blender 5.2

> O que usamos e o que confirmar. ✅ = confirmado em código que roda no 5.x (LMP) ou documentação oficial; ⏳ = confirmar no Blender 5.2 da máquina no primeiro dia de implementação (marcar ✅ e corrigir aqui).

## Versão

- 5.2 é **LTS** ✅ (notas oficiais). Mudanças de Python API do 5.1/5.2 não tocam animação/F-Curves ✅; 5.2 adiciona `gpu.init()` para usar GPU em `--background` ✅; 5.1 adiciona `bpy.app.handlers.exit_pre` ✅.

## Extension Manifest

- `blender_manifest.toml` com `schema_version = "1.0.0"`, `id`, `version`, `blender_version_min`, `license` SPDX, `[build] paths_exclude_pattern` ✅ (LMP, template).
- Pacote importado como `bl_ext.<repo>.<id>`; usar `__package__` para preferências ✅.
- `blender --command extension build|validate|install-file` ✅ (template).

## Slotted Actions / Channelbags

- `Action.fcurves` removido no 5.0 ✅ (LMP compat).
- `AnimData.action_slot` ✅; `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)` ✅ (usado pelo LMP).
- `anim_utils.action_ensure_channelbag_for_slot(action, slot)` ✅ (5.2.1: garante layer + keyframe strip e devolve o channelbag; usado por `scripts/make_test_assets.py`).
- `Action.slots.new(id_type='OBJECT', name=...)` ✅ → identificador `OB<name>`; atribuir com `adt.action = action` e `adt.action_slot = slot` ✅.
- `ActionChannelbag.fcurves.new(data_path, index=0, group_name="")`, `.ensure(data_path, index=0, group_name="")`, `.find(data_path, index=0)`, `.remove(fcurve)`, `.clear()`, `.new_from_fcurve(source, data_path=...)` ✅ (5.2.1). `group_name` cria/usa o grupo no channelbag ✅.
- Iterar todas as F-Curves de uma Action: `action.layers[i].strips[j].channelbags[k].fcurves` (+ `channelbag.slot`) ✅.
- Padrão de keys novas (preferências de fábrica): interpolação `BEZIER`, handles `AUTO_CLAMPED` ✅.
- `Action.layers[i].strips[j].channelbag(slot)` ✅ (LMP).
- Inserção de keys: `FCurve.keyframe_points.insert(frame, value, options={'FAST'})`, `foreach_get/foreach_set` em `co`, `handle_left`, `handle_right` ✅ (API estável); `FCurve.update()` ✅.

## Background / render

- `blender --background <arquivo> --python script.py -- args` + `bpy.ops.render.render(write_still=True)` com `BLENDER_WORKBENCH` funciona no Windows (5.2.1) ✅ — usado pelos previews de `dev.py assets --preview`.
- `bpy.ops.wm.open_mainfile` dentro dos testes mantém a extensão habilitada ✅; `bpy.data.libraries.load(path, link=False)` para ler Actions de outro arquivo ✅.
- `save_as_mainfile(copy=True, compress=True)` grava cópia sem mudar `bpy.data.filepath` ✅.

## Pose / bones

- Seleção em `PoseBone.select` (5.0+) ✅; visibilidade também por pose bone ✅ (notas 5.0).
- `PoseBone.matrix`, `matrix_basis`, `Object.matrix_world`, `evaluated_get(depsgraph)` ✅.
- `pose.paths_calculate` com `temp_override(window, area, region, …)` e `bake_location` ✅ (LMP); exige UI ⇒ indisponível em background.

## Depsgraph / handlers

- `depsgraph_update_post`, `frame_change_post`, `animation_playback_pre/post`, `load_post`, `undo_post`, `redo_post` com `@persistent` ✅ (LMP).
- `depsgraph.updates[i].is_updated_transform / is_updated_geometry` ✅.
- `Window.modal_operators` para detectar transform em andamento ✅ (LMP).
- `bpy.app.timers` para trabalho time-sliced ✅.

## GPU / desenho

- Sem `bgl` ✅. `gpu.shader.from_builtin('POLYLINE_SMOOTH_COLOR' | 'POINT_UNIFORM_COLOR' | 'UNIFORM_COLOR' …)` ✅ (LMP). Shader custom via `GPUShaderCreateInfo`, push constants ≤ 128 bytes (Vulkan) ✅.
- `gpu.state.*` para blend/depth/line width ✅.

## Operadores modais, gizmos, tools, undo

- `bpy.types.WorkSpaceTool` (`bl_context_mode = 'POSE'`), `bpy.utils.register_tool(tool, after={...}, separator=...)` ✅ (spike, 5.2.1): a tool aparece depois de Transform; `bl_keymap` define clique/shift+clique/caixa; o grupo de gizmos é ligado à tool por `bl_widget` e o `poll` checa a tool ativa.
- `bpy.types.Gizmo` customizado com `test_select(context, location)` ✅ (spike): serve para hover em pontos arbitrários em espaço de tela (retorna índice ou -1); `Gizmo.target_set_operator(idname)` entrega LMB e Ctrl+LMB sobre o gizmo sob hover a um operador (modal). Propriedades de ID **não** podem ser escritas no `setup` do grupo ⇒ usar um timer. Ver [ADR 0010](../decisions/0010-tool-gizmo-modal-interaction.md#resultado-do-spike-2026-10-03).
- `Window.event_simulate(type, value, x, y, shift=, ctrl=, alt=, ...)` ✅ (spike): só funciona com o Blender iniciado com `--enable-event-simulate`; usado por `tests/ui/` (gerador que cede entre eventos, via timer).
- `Object.convert_space(pose_bone=, matrix=, from_space='LOCAL', to_space='POSE')` ✅: aplica as regras reais de herança (`use_local_location`, inherit rotation/scale, pose do pai). É a base de `anim/spaces.location_space`; a fórmula `M_arm · M_pose · M_basis⁻¹` é incorreta com `use_local_location = False` (controles IK do Rigify).
- `bpy.ops.ed.undo` chamado de um timer com `temp_override` falha no poll ✅ (spike) ⇒ nos testes de UI usar Ctrl+Z / Ctrl+Shift+Z simulados.
- Operador modal com `bl_options={'REGISTER','UNDO'}` ⇒ 1 passo de undo ao retornar `FINISHED` ✅ (comportamento padrão).
- `area.header_text_set()` ✅.

## glTF exporter (Escopo 2)

Nomes de propriedades de `bpy.ops.export_scene.gltf` a confirmar ⏳: `export_format`, `use_selection`, `export_animations`, `export_animation_mode` (`'ACTIONS'`), `export_def_bones`, `export_force_sampling`, `export_frame_step`, `export_anim_slide_to_zero`, `export_optimize_animation_size`, `export_leaf_bone`, `export_hierarchy_flatten_bones`, `export_rest_position_armature`.

## Rigify no 5.2

- Bundled ✅ (módulo de add-on `rigify` presente no 5.2.1; não é extensão). Rig gerado abre e avalia no 5.2.1 ✅.
- Nomes de controles e props `IK_FK` (0 = IK, 1 = FK), `IK_parent`, `pole_parent`, `IK_Stretch`, `FK_limb_follow`, `pole_vector` em `upper_arm_parent.*`/`thigh_parent.*` ✅ — tabela em [rig-adapter](../design/rig-adapter.md#rigifyadapter).
- Controles principais em `QUATERNION` ✅; exceções em `YXZ` (shoulder, breast) e `ZXY` (tweaks, `*_ik` de upper_arm/thigh, `foot_heel_ik`).
- `rig_ui.py` (operadores de snap) só registra com auto-exec de scripts ligado; em `--background --factory-startup` não existe ✅.

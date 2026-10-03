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
- `anim_utils.action_ensure_channelbag_for_slot(action, slot)` ⏳.
- `ActionChannelbag.fcurves.new(data_path, index=0, group_name="")`, `.ensure(...)`, `.find(data_path, index=0)`, `.remove(fcurve)` ⏳ (assinaturas exatas).
- `Action.layers[i].strips[j].channelbag(slot)` ✅ (LMP).
- Inserção de keys: `FCurve.keyframe_points.insert(frame, value, options={'FAST'})`, `foreach_get/foreach_set` em `co`, `handle_left`, `handle_right` ✅ (API estável); `FCurve.update()` ✅.

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

- `bpy.types.WorkSpaceTool` (context `'POSE'`), `bpy.utils.register_tool` ⏳ (API estável há várias versões; confirmar).
- `bpy.types.Gizmo` customizado com `test_select(context, location)` e `draw_select` ⏳ — **objeto do spike (ADR 0010)**.
- Operador modal com `bl_options={'REGISTER','UNDO'}` ⇒ 1 passo de undo ao retornar `FINISHED` ✅ (comportamento padrão).
- `area.header_text_set()` ✅.

## glTF exporter (Escopo 2)

Nomes de propriedades de `bpy.ops.export_scene.gltf` a confirmar ⏳: `export_format`, `use_selection`, `export_animations`, `export_animation_mode` (`'ACTIONS'`), `export_def_bones`, `export_force_sampling`, `export_frame_step`, `export_anim_slide_to_zero`, `export_optimize_animation_size`, `export_leaf_bone`, `export_hierarchy_flatten_bones`, `export_rest_position_armature`.

## Rigify no 5.2

- Bundled e funcional ⏳ (manual do 5.1 ainda documenta Rigify como add-on de rigging).
- Nomes de controles e props `IK_FK`, `IK_parent` em `*_parent.L/R` ⏳ — validar no rig gerado.
- Controles em `QUATERNION` por padrão ⏳.

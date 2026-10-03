# Dados de animação (Actions, slots, F-Curves)

> Como o addon lê e escreve animação no Blender 5.2 sem sair do formato nativo ([ADR 0003](../decisions/0003-native-blender-animation-output.md)).

## Modelo do Blender 5.x

```
Object.animation_data (AnimData)
 ├── action       : Action (layered/slotted)
 ├── action_slot  : ActionSlot           ← qual "trilho" da Action este objeto usa
 └── nla_tracks
Action
 └── layers[0].strips[0] (KEYFRAME)
      └── channelbag(slot) : ActionChannelbag
           ├── fcurves : ActionChannelbagFCurves  (new / ensure / find / remove)
           └── groups
```

- `Action.fcurves` (API legada) **não existe no 5.x**. Toda leitura passa por channelbag.
- Helpers oficiais: `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot)` e `action_ensure_channelbag_for_slot(action, slot)`.
- Seleção de bones: `PoseBone.select` (5.0+), não `Bone.select`.

Itens a confirmar no Blender 5.2 real estão em [development/blender-5.2-notes.md](../development/blender-5.2-notes.md).

## Regras de leitura

- Canais de um bone: `data_path` começa com `pose.bones["<nome>"].` — resolver com `pb.path_from_id("location")` em vez de montar string à mão (nomes com aspas).
- Ignorar F-Curves `mute`, com modificadores ativos (aviso na UI: não editamos curvas com modificadores no MVP), ou travadas (`lock`).
- NLA ativa / influência < 1 / blend ≠ REPLACE: a trail mostra o resultado avaliado, mas o sculpt **recusa** editar (aviso). Escopo do MVP é "uma Action ativa".
- Drivers no canal: recusado.

## Regras de escrita

1. Carregar canais em `core/fcurve_model` (`foreach_get` de `co`, `handle_left`, `handle_right`; tipos e interpolação por key).
2. Operação pura no core.
3. Escrever de volta com `foreach_set` e chamar `fcurve.update()` uma vez por canal (recalcula handles automáticos e ordenação).
4. Inserir key: `keyframe_points.insert(frame, value, options={'FAST'})` só quando necessário; depois reescrever arrays.
5. Criar F-Curve ausente (ex.: `location[2]` nunca keyado): `channelbag.fcurves.ensure(data_path, index=i, group_name=<bone>)`.
6. Nunca criar Action nova silenciosamente. Se o rig não tem Action, o sculpt pede para o usuário keyar a primeira pose (fluxo normal do Blender: `I`).
7. Tag de redraw/depsgraph: `action.id_data` tag + `area.tag_redraw()`; o LMP recalcula pela via normal ao final do gesto.

## Handles

| Situação | Política |
|---|---|
| Grab de key | Move key e ambos handles juntos (translação rígida). Tipos preservados. |
| Arc drag | Lado editado: `AUTO`/`AUTO_CLAMPED` → `ALIGNED`. Oposto girado p/ colinearidade (ou `FREE` com modificador). |
| Spacing | Só `x` dos handles; política `PRESERVE_PATH`/`PRESERVE_SMOOTHNESS` a decidir ([modelo](motion-sculpt-model.md#4-spacing-de-segmento-escopo-de-timing)). |
| Retime | `x` de key e handles deslocados juntos. |
| `VECTOR` | Tratado como `FREE` quando editado (mesma regra do Motion Trail). |

Risco conhecido: a correção automática de `ALIGNED` do Blender usa flags de seleção de handle para decidir qual lado manter. Escrevemos ambos já colineares e testamos que `update()` não os altera (teste de integração dedicado).

## Rotação

- Iteração 1 não escreve rotação (exceto retime/spacing, que só mexem em tempo — seguros para qualquer canal, inclusive quaternions).
- Escopo 4 (FK): quaternions editados como 4 canais com renormalização por frame-key após o solve; Euler direto. Nunca trocar `rotation_mode` do usuário.

## Undo e cancel

- **Undo**: o operador modal tem `bl_options = {'REGISTER', 'UNDO'}`; cada gesto termina com `FINISHED` ⇒ um passo no histórico global do Blender (undo de memfile inclui a Action).
- **Cancel** (Esc / botão direito) durante o gesto: `anim/snapshot` restaura arrays salvos no início — não depende do undo.
- `undo_post`/`redo_post`: caches derivados (trails, `P(f)`, seleção de pontos por índice) são descartados. Seleção de pontos é guardada por **frame**, não por índice, para sobreviver a undo.

## Persistência

Persistem no `.blend`: a Action (é animação comum) e o `PropertyGroup` da cena com preferências de exibição. Não persistem: caches, trails, seleção de pontos, estado do modal. Reabrir o arquivo reconstrói tudo a partir das F-Curves.

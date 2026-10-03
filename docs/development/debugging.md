# Debugging

## Console e logs

- Windows: Window › Toggle System Console. Logger `animation_sculptor` (módulo `logging`), nível configurável nas preferências; o LMP vendorizado imprime com prefixo próprio.
- Exceções em handlers/timers não podem derrubar o Blender: sempre `try/except` com log (padrão do LMP).

## Estatísticas no painel

"Show Statistics" (herdado do LMP): alvos, engines usados, último tempo de update. Acrescentar: custo do último gesto por mouse move, tempo de prefetch de `P(f)`, frames em cache.

## Debug com breakpoints

VS Code + "Blender Development" (start/attach com debugpy). Alternativa: `import debugpy; debugpy.listen(5678)` atrás de uma flag de preferência.

## Problemas típicos previstos

| Sintoma | Causa provável | Onde olhar |
|---|---|---|
| Trail não atualiza | engine suspenso não retomado; dependência não detectada | `trails/provider`, `build_deps` do LMP |
| Preview ≠ trail final | `P(f)` desatualizado (pai animado mudou) ou controle influencia o próprio pai | `anim/spaces`, invalidação |
| Handles "pulam" após soltar | `fcurve.update()` corrigindo `ALIGNED` | `anim/action_io`, teste de handles |
| Undo desfaz demais/de menos | modal terminando sem `FINISHED` / undo push extra | `interaction/sculpt_tool` |
| Native solver falha | sem window/area no override, armature fora de Pose Mode | `trails/lmp/engine.native_bone_paths` |
| Lentidão ao arrastar | depsgraph sendo reavaliado durante gesto | checar suspensão do engine e escrita só no fim |

## Inspeção via Blender MCP

Para estado que só existe com UI aberta: pedir ao agente que, via MCP, liste `scene.asc_*`, caches do provider, F-Curves de um bone, handlers registrados. Ver [testing/blender-tests.md](../testing/blender-tests.md#blender-mcp-inspeção-interativa).

# Testes de integração no Blender

## Execução

```
python scripts/dev.py test blender            # todos
python scripts/dev.py test blender -k spaces  # filtro pytest
```

Fluxo (adaptado do BlenderAddonTemplate):

1. `dev.py` localiza o Blender e confere que é 5.2 ([setup](../development/setup.md#configuração-local)).
2. Perfil **isolado**: `BLENDER_USER_RESOURCES=./.blender_test_profile/` — nunca toca no perfil real do usuário.
3. Instala `pytest` (puro Python) em `.blender_test_profile/pydeps` com o **Python do sistema** (`pip install --target`), uma vez. Não escreve na instalação do Blender (que no Windows fica em Program Files, sem permissão).
4. Cria junction/symlink do working tree em `<perfil>/extensions/user_default/animation_sculptor` — sem build/zip, código atual sempre.
5. Roda `blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- <args pytest>`; o `run.py` habilita `bl_ext.user_default.animation_sculptor` (falha se o registro der erro) e chama `pytest.main`.
6. (A partir dos assets) cada teste abre um `.blend` de `tests/assets/` com `bpy.ops.wm.open_mainfile` — estado limpo por teste.

Testes existentes: `tests/blender/test_smoke.py` (versão 5.2, extensão habilitada, painel e preferências registrados, ciclo disable/enable, `core` importável a partir da extensão instalada).

## Fixtures planejadas (`tests/blender/conftest.py`)

- `rigify_rig` — abre `rigify_humanoid.blend`, retorna o objeto do rig gerado.
- `attack_action` — abre `attack_test.blend`, rig com Action de ataque em key poses.
- `simple_rig` — armature de 3 bones sem Rigify (adapter genérico).
- `force_step_engine` — configura o engine do LMP em `STEP` (native solver exige janela).

## Casos por tema

| Tema | Testes |
|---|---|
| Action I/O | ler canais por slot/channelbag; `ensure` de F-Curve ausente; ida e volta `fcurve_model` sem perdas; recusa com drivers/NLA/modificadores |
| Paridade Bézier | `core.bezier.evaluate` vs `FCurve.evaluate` em curvas aleatórias (seed fixa), todos os tipos de handle |
| Handles | escrever ALIGNED colinear + `update()` ⇒ inalterado; conversão AUTO→ALIGNED |
| `P(f)` | para `hand_ik.L`: `P(f) · local(f)` = posição avaliada do head em todos os frames (tol 1e-5); detecção de `P` constante |
| Rigify adapter | detecção; conceitos → bones existentes; capacidades; `IK_FK`; nenhum controle `MCH/ORG/DEF` |
| Grab/Arc (via core + escrita) | Δw aplicado ⇒ head avaliado no frame move Δw (tol 1e-4); keys/timing preservados no arc |
| Retime/Spacing | todos os canais do personagem movidos; ordem preservada; caminho preservado (amostrado) |
| Operador | `invoke` com evento sintético não é viável em background ⇒ operador expõe `execute` paramétrico (mesma lógica do gesto) para teste |
| Undo | `bpy.ops.ed.undo_push` + operação + `ed.undo` restaura (onde suportado em background; senão coberto no manual) |
| Save/reload | salvar em tmp, reabrir, Action idêntica, nenhuma propriedade extra além de `Scene.asc_*` |
| Trails | engine STEP produz pontos = posições avaliadas; invalidação após edição |

## Blender MCP (inspeção interativa)

O Blender MCP instalado na máquina permite que um agente execute Python numa sessão **com UI** do Blender. Uso previsto: diagnosticar problemas que só aparecem com janela (native solver, desenho, gizmo), inspecionar estado de uma cena do usuário, reproduzir bugs. **Não** substitui os testes automatizados (não é reproduzível em CI); qualquer descoberta feita via MCP vira teste automatizado ou item do checklist manual.

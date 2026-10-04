# Testes de integração no Blender

## Execução

```
python scripts/dev.py test blender            # todos
python scripts/dev.py test blender -k spaces  # filtro pytest
python scripts/dev.py test ui                 # GUI com eventos simulados (local; ver abaixo)
```

Fluxo (adaptado do BlenderAddonTemplate):

1. `dev.py` localiza o Blender e confere que é 5.2 ([setup](../development/setup.md#configuração-local)).
2. Perfil **isolado**: `BLENDER_USER_RESOURCES=./.blender_test_profile/` — nunca toca no perfil real do usuário.
3. Instala `pytest` (puro Python) em `.blender_test_profile/pydeps` com o **Python do sistema** (`pip install --target`), uma vez. Não escreve na instalação do Blender (que no Windows fica em Program Files, sem permissão).
4. Cria junction/symlink do working tree em `<perfil>/extensions/user_default/animation_sculptor` — sem build/zip, código atual sempre.
5. Roda `blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py -- <args pytest>`; o `run.py` habilita `bl_ext.user_default.animation_sculptor` (falha se o registro der erro) e chama `pytest.main`.
6. Testes de asset abrem o `.blend` com `bpy.ops.wm.open_mainfile` (fixture de módulo). `dev.py` passa `ASC_TEST_ASSET` e, se configurado, `ASC_TEST_CHARACTER`; sem o arquivo, os testes pulam.

Testes existentes:
- `tests/blender/test_smoke.py` — versão 5.2, extensão habilitada, painel e preferências registrados, ciclo disable/enable, `core` importável a partir da extensão instalada.
- `tests/blender/test_attack_asset.py` — asset local de ataque ([regression-assets](regression-assets.md)): metadados e markers, Action no slot do rig, controles keyados, keys nos frames das key poses, Bézier/auto-clamped, valores = literais do script, `IK_FK` (braço esquerdo FK), animação move de fato a mão da espada, tudo exceto o rig oculto, Actions anteriores preservadas na cópia e intactas no original.

- `tests/blender/test_trails.py` (9 testes) — trails/LMP: namespace `asc_trails` registrado e coexistindo com o LMP original; onion skin desligado por padrão; trail (engine STEP em background) = posições avaliadas do head no rig público (tol 1e-5); `suspend` mantém o cache e `resume` invalida; `suspend` aninhado; restauração das configurações do P4; regressão do self-tag do P4 (`STATE.self_tagged`); trail no asset local de ataque (`hand_ik.R`, `foot_ik.L`, tol 1e-4 — pula sem o asset); `test_action_update_invalidates_trail` (patch P7: atualizar a Action invalida a trail).
- `tests/blender/test_bezier_parity.py` (2 testes) — paridade bit a bit de `core.bezier.evaluate` com `FCurve.evaluate`: 300 curvas aleatórias (seed fixa; todos os tipos de handle, CONSTANT/LINEAR/BEZIER, extrapolação CONSTANT/LINEAR, handles FREE longos que criam sobreposição e laços) × 801 tempos, erro máximo 0; e todas as curvas do rig público.
- `tests/blender/test_action_io.py` (7 testes) — `anim/action_io` e `anim/snapshot`: channelbag e F-Curves do bone; ida e volta sem perdas; escrita muda o número de keys; handles `ALIGNED` colineares sobrevivem ao `update()`; `ensure_channel`/`ensure_key`; snapshot restaura bit a bit (incluindo curvas criadas e keys inseridas); recusas.
- `tests/blender/test_sculpt_gesture.py` (14 funções, 27 casos com parametrização) — spike de interação via `execute` paramétrico do operador (`obj_name`, `bone`, `frame`, `delta`), no rig público: classes registradas (tool, gizmo, operador); o grab move o controle pelo delta de mundo (< 1e-4 m) em `hand_ik.L` (frame 12), `foot_ik.R` (24) e `torso` (12); só a key do frame editado muda; delta zero = identidade (invariante 1); eixo travado não se move; recusas com driver em `location`, NLA ativa e frame sem key; trails retomadas após o gesto; `location_space` mapeia `location` → head (`hand_ik.L`, `foot_ik.R`, `torso`, `upper_arm_fk.R` × frames 1/7/12, tol 1e-5).

## Testes de UI (eventos simulados)

`python scripts/dev.py test ui [filtro]` gera o rig público, abre um Blender **com janela** (`--enable-event-simulate --factory-startup --addons bl_ext.user_default.animation_sculptor`, perfil isolado) e roda os cenários `tests/ui/scenario_*.py` (geradores que dirigem `Window.event_simulate`: mouse e teclas). `tests/ui/run_ui.py` é o runner; resultados em JSON e screenshots em `.blender_test_profile/ui/`. Precisa de display e **não roda no CI** (local apenas). O runner habilita auto-exec de scripts, porque o popup do `rig_ui.py` do Rigify bloqueia o primeiro evento simulado.

`scenario_spike.py` (18 checagens, todas passando): a tool liga a trail (engine NATIVE); o hover escolhe a key; o press inicia o modal; o engine fica suspenso durante o arrasto; soltar encerra o gesto; o key point cai sob o cursor (erro 0,00 px); custo do mouse move 0,19 ms (só operador: escrita + atualização da F-Curve; exclui reavaliação do depsgraph e redesenho); as keys mudaram; nenhuma key criada e timing intacto; a trail recalculada após soltar coincide com o rig (1e-4); um Ctrl+Z restaura as keys exatamente; Ctrl+Shift+Z reaplica; Esc restaura bit a bit; nenhum gesto fica rodando; Ctrl+LMB não faz grab mas chega ao operador (recusa "tempo (retime/spacing): ainda não implementado").

`scenario_release_refresh.py` (6 checagens, asset da Vale): ao soltar o grab a trail é recalculada sem I/Refresh.

`scenario_native_edit_refresh.py` (3 checagens, asset da Vale): regressão do patch P7 — G (Move) + I duas vezes; a trail acompanha a pose keyada (erro 0,154 m antes do patch, 0,0 depois).

## Fixtures (`tests/blender/conftest.py`)

Existentes:
- `addon` — garante a extensão habilitada/registrada.
- `public_rig_path` (sessão) — gera uma vez o rig Rigify público via `tests/blender/public_rig.py`: metarig Human → `pose.rigify_generate` num subprocesso Blender de fundo separado (~6 s). Action `asc_public_test` com keys em 1/12/24 em `hand_ik.L` (loc+quat), `foot_ik.R` (loc), `torso` (loc) e `upper_arm_fk.R` (quat); frames 1–24. Nenhum binário no repo; roda no CI.
- `public_rig` — abre uma cópia nova do rig gerado e devolve o objeto.
- `attack_rig` — abre o asset local de ataque (Vale); pula se não existir.

Planejadas:
- `simple_rig` — armature de 3 bones sem Rigify (adapter genérico).
- `force_step_engine` — configura o engine do LMP em `STEP` (native solver exige janela).

## Casos por tema

| Tema | Testes |
|---|---|
| Action I/O | **feito** (`test_action_io.py`): ler canais por slot/channelbag; `ensure` de F-Curve ausente; ida e volta `fcurve_model` sem perdas; snapshot bit a bit; recusa com drivers/NLA/modificadores |
| Paridade Bézier | **feito** (`test_bezier_parity.py`): `core.bezier.evaluate` vs `FCurve.evaluate` em curvas aleatórias (seed fixa), todos os tipos de handle, erro 0 |
| Handles | **feito**: escrever ALIGNED colinear + `update()` ⇒ inalterado. Falta: conversão AUTO→ALIGNED |
| `P(f)` | **feito** (`test_location_space_maps_location_to_head`): `P · location` = head avaliado para `hand_ik.L`, `foot_ik.R`, `torso`, `upper_arm_fk.R` em vários frames (tol 1e-5), incluindo bones com `use_local_location = False`. Falta: `P(f) · local(f)` em todos os frames via cache/prefetch e detecção de `P` constante |
| Rigify adapter | detecção; conceitos → bones existentes; capacidades; `IK_FK`; nenhum controle `MCH/ORG/DEF` |
| Grab/Arc (via core + escrita) | Δw aplicado ⇒ head avaliado no frame move Δw (tol 1e-4); keys/timing preservados no arc |
| Retime/Spacing | todos os canais do personagem movidos; ordem preservada; caminho preservado (amostrado) |
| Operador | `invoke` com evento sintético não é viável em background ⇒ operador expõe `execute` paramétrico (mesma lógica do gesto) para teste; o fluxo real (hover, press, drag, release, Esc) é coberto pelos testes de UI com eventos simulados |
| Undo | coberto na UI com Ctrl+Z / Ctrl+Shift+Z simulados (`scenario_spike.py`: 1 passo por gesto); `ed.undo` chamado de um timer com override falha no poll ⇒ usar o evento simulado. `bpy.ops.ed.undo_push` + `ed.undo` em background só onde suportado |
| Save/reload | salvar em tmp, reabrir, Action idêntica, nenhuma propriedade extra além de `Scene.asc_*` |
| Trails | engine STEP produz pontos = posições avaliadas; invalidação após edição |

## Blender MCP (inspeção interativa)

O Blender MCP instalado na máquina permite que um agente execute Python numa sessão **com UI** do Blender. Uso previsto: diagnosticar problemas que só aparecem com janela (native solver, desenho, gizmo), inspecionar estado de uma cena do usuário, reproduzir bugs. **Não** substitui os testes automatizados (não é reproduzível em CI); qualquer descoberta feita via MCP vira teste automatizado ou item do checklist manual.

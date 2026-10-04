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

- `tests/blender/test_trails.py` (10 testes) — trails/LMP: namespace `asc_trails` registrado e coexistindo com o LMP original; onion skin desligado por padrão; trail (engine STEP em background) = posições avaliadas do head no rig público (tol 1e-5); `suspend` mantém o cache e `resume` invalida; `suspend` aninhado; restauração das configurações do P4; regressão do self-tag do P4 (`STATE.self_tagged`); trail no asset local de ataque (`hand_ik.R`, `foot_ik.L`, tol 1e-4 — pula sem o asset); `test_action_update_invalidates_trail` (patch P7: atualizar a Action invalida a trail); `test_native_points_validated_against_live_bone` (patch P8: o resultado do native solver é validado contra o bone vivo; um bone que o solver não enxerga cai para frame stepping).
- `tests/blender/test_bezier_parity.py` (2 testes) — paridade bit a bit de `core.bezier.evaluate` com `FCurve.evaluate`: 300 curvas aleatórias (seed fixa; todos os tipos de handle, CONSTANT/LINEAR/BEZIER, extrapolação CONSTANT/LINEAR, handles FREE longos que criam sobreposição e laços) × 801 tempos, erro máximo 0; e todas as curvas do rig público.
- `tests/blender/test_action_io.py` (7 testes) — `anim/action_io` e `anim/snapshot`: channelbag e F-Curves do bone; ida e volta sem perdas; escrita muda o número de keys; handles `ALIGNED` colineares sobrevivem ao `update()`; `ensure_channel`/`ensure_key`; snapshot restaura bit a bit (incluindo curvas criadas e keys inseridas); recusas.
- `tests/blender/test_sculpt_gesture.py` (14 funções, 27 casos com parametrização) — spike de interação via `execute` paramétrico do operador (`obj_name`, `bone`, `frame`, `delta`), no rig público: classes registradas (tool, gizmo, operador); o grab move o controle pelo delta de mundo (< 1e-4 m) em `hand_ik.L` (frame 12), `foot_ik.R` (24) e `torso` (12); só a key do frame editado muda; delta zero = identidade (invariante 1); eixo travado não se move; recusas com driver em `location`, NLA ativa e frame sem key; trails retomadas após o gesto; `location_space` mapeia `location` → head (`hand_ik.L`, `foot_ik.R`, `torso`, `upper_arm_fk.R` × frames 1/7/12, tol 1e-5).
- `tests/blender/test_soft_grab_arc.py` (6 funções, parametrizadas) — arc drag e soft grab via `execute` paramétrico (`mode`, `radius`, `break_tangent`) no rig público: o in-between se move exatamente o delta de mundo (< 0,1 mm) em `hand_ik.L`, `foot_ik.R` e `torso`, com keys e timing intactos; key poses preservadas; "quebrar tangente" mantém o outro segmento; segmento LINEAR recusado; soft grab move as keys vizinhas por `w·Δ` (nenhuma key criada); raio 0 = grab simples.
- `tests/blender/test_rig_adapter.py` (4 testes) — `rig/`: adapter Rigify no rig público gerado (detecção, conceitos → bones existentes, capacidades, `IK_FK`, nenhum `MCH/ORG/DEF` entre os controles; roda no CI); o mesmo no personagem local (`attack_rig`; pula sem o asset); armature simples sem Rigify ⇒ adapter genérico; o gesto recusa FK e mecanismos (`MCH-`) com os motivos do adapter.
- `tests/blender/test_spaces.py` (5 funções, 7 casos; `prefetch` parametrizado em 3 bones) — `anim/spaces`: `prefetch` reproduz `P(f) · location(f)` = head avaliado em todos os frames (`hand_ik.L`, `foot_ik.R`, `torso`); controle IK do Rigify nunca é constante; `root` sem animação é constante e usa uma única avaliação; animação no objeto do armature quebra a constância; profiling do prefetch no personagem local (não bloqueante, só falha acima de 50 ms/frame; mediu 0,69 ms/frame; pula sem o asset).

## Testes de UI (eventos simulados)

`python scripts/dev.py test ui [filtro]` gera o rig público, abre um Blender **com janela** (`--enable-event-simulate --factory-startup --addons bl_ext.user_default.animation_sculptor`, perfil isolado) e roda os cenários `tests/ui/scenario_*.py` (geradores que dirigem `Window.event_simulate`: mouse e teclas). `tests/ui/run_ui.py` é o runner; resultados em JSON e screenshots em `.blender_test_profile/ui/`. Precisa de display e **não roda no CI** (local apenas). O runner habilita auto-exec de scripts, porque o popup do `rig_ui.py` do Rigify bloqueia o primeiro evento simulado.

`scenario_spike.py` (18 checagens, todas passando): a tool liga a trail (engine NATIVE); o hover escolhe a key; o press inicia o modal; o engine fica suspenso durante o arrasto; soltar encerra o gesto; o key point cai sob o cursor (erro 0,00 px); custo do mouse move 0,19 ms (só operador: escrita + atualização da F-Curve; exclui reavaliação do depsgraph e redesenho); as keys mudaram; nenhuma key criada e timing intacto; a trail recalculada após soltar coincide com o rig (1e-4); um Ctrl+Z restaura as keys exatamente; Ctrl+Shift+Z reaplica; Esc restaura bit a bit; nenhum gesto fica rodando; Ctrl+LMB não faz grab mas chega ao operador (recusa "tempo (retime/spacing): ainda não implementado").

`scenario_release_refresh.py` (6 checagens, asset da Vale): ao soltar o grab a trail é recalculada sem I/Refresh.

`scenario_native_edit_refresh.py` (3 checagens, asset da Vale): regressão do patch P7 — G (Move) + I duas vezes; a trail acompanha a pose keyada (erro 0,154 m antes do patch, 0,0 depois).

`scenario_arc_soft.py` (10 checagens, asset da Vale): hover num in-between; gesto de arc — o in-between termina sob o cursor (0,00 px) e nenhuma key é adicionada; a roda do mouse ajusta o raio e a key vizinha acompanha o grab; um key de FK é recusado com motivo (anel vermelho/header) e nada muda; regressão do patch P8 (a trail de um controle FK de coleção oculta não vai para a origem).

## Fixtures (`tests/blender/conftest.py`)

Existentes:
- `addon` — garante a extensão habilitada/registrada.
- `public_rig_path` (sessão) — gera uma vez o rig Rigify público via `tests/blender/public_rig.py`: metarig Human → `pose.rigify_generate` num subprocesso Blender de fundo separado (~6 s). Action `asc_public_test` com keys em 1/12/24 em `hand_ik.L` (loc+quat), `foot_ik.R` (loc), `torso` (loc) e `upper_arm_fk.R` (quat); frames 1–24. Nenhum binário no repo; roda no CI.
- `public_rig` — abre uma cópia nova do rig gerado e devolve o objeto.
- `attack_rig` — abre o asset local de ataque (Vale); pula se não existir.

Planejadas:
- `simple_rig` — armature de 3 bones sem Rigify (adapter genérico). Hoje o teste do genérico monta o armature dentro do próprio teste.
- `force_step_engine` — configura o engine do LMP em `STEP` (native solver exige janela).

## Casos por tema

| Tema | Testes |
|---|---|
| Action I/O | **feito** (`test_action_io.py`): ler canais por slot/channelbag; `ensure` de F-Curve ausente; ida e volta `fcurve_model` sem perdas; snapshot bit a bit; recusa com drivers/NLA/modificadores |
| Paridade Bézier | **feito** (`test_bezier_parity.py`): `core.bezier.evaluate` vs `FCurve.evaluate` em curvas aleatórias (seed fixa), todos os tipos de handle, erro 0 |
| Handles | **feito**: escrever ALIGNED colinear + `update()` ⇒ inalterado; conversão AUTO→ALIGNED e FREE no arc drag (`test_arc_and_falloff.py`: oposto colinear mantendo `x`; "quebrar tangente" deixa os vizinhos bit a bit idênticos) |
| `P(f)` | **feito** (`test_location_space_maps_location_to_head`, `test_spaces.py`): `P · location` = head avaliado para `hand_ik.L`, `foot_ik.R`, `torso`, `upper_arm_fk.R` em vários frames (tol 1e-5), incluindo bones com `use_local_location = False`; `prefetch` = head avaliado em todos os frames; detecção de `P` constante (positivo, negativo e atalho de uma avaliação); custo no personagem |
| Rigify adapter | **feito** (`test_rig.py` unit com armatures falsos; `test_rig_adapter.py`): detecção; conceitos → bones existentes; capacidades; `IK_FK`; nenhum controle `MCH/ORG/DEF`; FK só de rotação; genérico no armature simples; recusas do gesto |
| Grab/Arc (via core + escrita) | **feito** (`test_sculpt_gesture.py`, `test_soft_grab_arc.py`, `test_arc_and_falloff.py`): Δw aplicado ⇒ head avaliado no frame move Δw (grab 1e-4, arc < 0,1 mm); keys/timing preservados no arc; soft grab por `w·Δ`; falloff (formas, raio 0) |
| Retime/Spacing | todos os canais do personagem movidos; ordem preservada; caminho preservado (amostrado) |
| Operador | `invoke` com evento sintético não é viável em background ⇒ operador expõe `execute` paramétrico (mesma lógica do gesto) para teste; o fluxo real (hover, press, drag, release, Esc) é coberto pelos testes de UI com eventos simulados |
| Undo | coberto na UI com Ctrl+Z / Ctrl+Shift+Z simulados (`scenario_spike.py`: 1 passo por gesto); `ed.undo` chamado de um timer com override falha no poll ⇒ usar o evento simulado. `bpy.ops.ed.undo_push` + `ed.undo` em background só onde suportado |
| Save/reload | salvar em tmp, reabrir, Action idêntica, nenhuma propriedade extra além de `Scene.asc_*` |
| Trails | engine STEP produz pontos = posições avaliadas; invalidação após edição |

## Blender MCP (inspeção interativa)

O Blender MCP instalado na máquina permite que um agente execute Python numa sessão **com UI** do Blender. Uso previsto: diagnosticar problemas que só aparecem com janela (native solver, desenho, gizmo), inspecionar estado de uma cena do usuário, reproduzir bugs. **Não** substitui os testes automatizados (não é reproduzível em CI); qualquer descoberta feita via MCP vira teste automatizado ou item do checklist manual.

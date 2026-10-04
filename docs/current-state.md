# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — `core/bezier` + `core/fcurve_model` (paridade bit a bit com o Blender), `anim/action_io` + `anim/snapshot`, grab migrado, correção das trails após edição nativa (PR `feat/core-bezier-action-io`).

## Resumo

Planejamento (PR #1), esqueleto (PR #2), assets de ataque (PR #3), trails com o LMP vendorizado (PR #4), spike de interação (PR #5, [ADR 0010](decisions/0010-tool-gizmo-modal-interaction.md) validado) e os ajustes do grab (PR #6: edição sempre vira keyframe, trail prevista ao vivo, refresh ao soltar) estão na `main`. Em revisão (PR `feat/core-bezier-action-io`): o **`core/` puro** (modelo de canal, avaliação Bézier idêntica à do Blender, `grab_key`), a camada **`anim/`** (`action_io`, `snapshot`) com o grab migrado do spike, a **correção do bug das trails após edição nativa** (G + I, Graph Editor) e o pedido de **Loop** no roadmap. Ainda sem arc drag, retime, spacing, `rig/`.

## O que funciona hoje

- Extensão `animation_sculptor` 0.2.0 (Blender 5.2): registra preferências, painéis, trails e interação (nessa ordem), em 3D Viewport › N › Animation Sculptor.
- `scripts/dev.py`: `link`/`unlink`, `test unit|blender|ui|all`, `build`, `validate`, `fetch-blender`. `test ui` abre um Blender com janela e roda cenários com eventos simulados (local, precisa de display; ver [blender-tests](testing/blender-tests.md#testes-de-ui-eventos-simulados)).
- `scripts/checks.py`: regras estáticas (core sem bpy, nomes de bones só em `rig/`, manifest, links da documentação).
- CI no GitHub verde: job `unit` (pytest real) e job `blender` (baixa o Blender 5.2.x, roda os testes de Blender — smoke + trails no rig público gerado — e `extension validate`).
- `python scripts/dev.py assets [--preview]`: gera `tests/assets/local/attack_test.blend` (gitignored) a partir do personagem configurado em `scripts/.dev.toml` (`character = '...'`) ou `ASC_TEST_CHARACTER`. Só o control rig visível; Action `asc_test_attack` (slot `OBrig`, key poses 1/10/16/18/26/40: idle → anticipation → attack → impact → follow-through → recovery; braço direito IK com a espada, braço esquerdo FK). Detalhes: [regression-assets](testing/regression-assets.md).
- `tests/blender/test_attack_asset.py` (11 testes) — pulam quando o asset não existe (caso do CI).
- **Trails** (`animation_sculptor/trails/`): `lmp/` é o Live Motion Path vendorizado (namespace `Scene.asc_trails`, classes `ASC_TR_*`, operadores `asc_trails.*`; patches P1–P5 e P7, sem P6) e `provider.py` é a façade: `Trail` (dataclass: `obj_name`, `bone`, `frames` int32, `points` float32 em mundo, `keyframes`, `complete`, `engine`, `point_at(frame)`), `settings/is_enabled/set_enabled/key_for/get_trail/targets/update_now/refresh/invalidate/suspend/resume/is_suspended`, context manager `suspended()` e `stats()`. O painel principal tem o toggle "Mostrar trails" (`scene.asc_trails.enabled`); os painéis do LMP ficam aninhados como "Trails"; onion skin desligado por padrão.
- Rig público de teste gerado em tempo de teste por `tests/blender/public_rig.py` (metarig Human → `pose.rigify_generate` num Blender de fundo separado, ~6 s, uma vez por sessão), com Action `asc_public_test` ([regression-assets](testing/regression-assets.md)). Nenhum binário no repo; roda no CI.
- `tests/blender/test_trails.py` (9 testes): ver [blender-tests](testing/blender-tests.md).
- **Interação (spike)** (`animation_sculptor/interaction/`): tool `ASC_WT_sculpt` (id `animation_sculptor.sculpt`, Pose Mode, depois de Transform; clique seleciona bone, shift+clique alterna, arrasto em vazio = caixa) com o grupo de gizmos `ASC_GGT_trails` (ligado à tool; liga as trails ao ativar) e o gizmo `ASC_GT_trail_points` (hover por `test_select`, 12 px, keys favorecidas; texto no header; anel desenhado por `overlay.py`: branco = key, azul claro = in-between, laranja no gesto). LMB num ponto sob hover inicia o operador modal `asc.sculpt_gesture`: em key point de **controle de translação** faz o **grab** (delta de mouse no plano da vista → `Δl = R(f)⁻¹Δw`, aplicado rígido em key+handles do frame, eixos travados pulados, Shift = precisão ×0,1; soltar = 1 passo de undo + `provider.resume`; Esc/RMB = restaura o snapshot bit a bit). Recusas com motivo: sem Action, NLA ativa, influence/blend, driver em `location`, modificador de F-Curve, sem key de `location` no frame, ponto in-between ("arc drag: próximo"), Ctrl+LMB ("tempo (retime/spacing): ainda não implementado" — prova que o Ctrl+LMB chega ao operador via gizmo).
- `anim/spaces.py::location_space(ob, pb)`: espaço-base `P` por `Object.convert_space` (ver "Achado" abaixo).
- **Grab (ajustes pós-teste)**: a edição é sempre gravada como keyframe — eixos livres de `location` sem key no frame do key point recebem uma (valor avaliado) e F-Curves ausentes são criadas (`channelbag.fcurves.ensure`); Esc remove o que foi inserido (bit a bit). No início do gesto `P(f)` é pré-calculado para todos os frames da trail (frame stepping + `location_space`) e o overlay desenha a **trail prevista ao vivo** (`P(f) @ location(f)`, amarela) sobre a trail antiga (fantasma). Ao soltar, `provider.resume` + **`update_now()` síncrono** recalculam a trail do controle. Qualquer tecla que não seja de navegação durante o gesto confirma o gesto e é repassada (um release perdido nunca deixa o gesto/engine pendurado).
- `tests/blender/test_sculpt_gesture.py` (14 funções, parametrizadas) e `tests/ui/` (`run_ui.py`, `scenario_spike.py` 18 checagens, `scenario_release_refresh.py` 6, `scenario_native_edit_refresh.py` 3; os dois últimos no asset da Vale quando existe): ver [blender-tests](testing/blender-tests.md).
- **`core/` (puro, sem `bpy`)**: `fcurve_model.ChannelModel` (arrays float64 `co`/`hl`/`hr`, tipos de handle, interpolação por key, extrapolação; `copy`, `same_as` bit a bit, `key_index`, `segment_of`); `bezier` (porte da avaliação de `fcurve.cc` do Blender 5.2, vetorizada, reproduzindo a precisão float32/double: `evaluate`, `bernstein`, `segment_t`); `sculpt_ops.grab_key` (key + handles rígidos; delta 0 = identidade). Paridade com `FCurve.evaluate`: 300 curvas aleatórias (todos os tipos de handle, CONSTANT/LINEAR/BEZIER, extrapolação CONSTANT/LINEAR, handles FREE longos com sobreposição) × 801 tempos, **erro máximo 0 (bit a bit)**, e todas as curvas do rig público.
- **`anim/`**: `action_io` (`channelbag`, `bone_fcurves`, `key_index`, `bone_has_key`, `refusal` — movido de `interaction` —, `read_channel`/`write_channel` com `foreach_get/set`, `ensure_channel` (cria no grupo do bone), `ensure_key`, `tag`) e `snapshot.Snapshot.capture/restore` (bit a bit, inclusive removendo curvas criadas e keys inseridas). O `fcurve.update()` do Blender **mantém** handles `ALIGNED` que escrevemos colineares (testado).
- **Grab migrado**: `sculpt_tool.py` usa `action_io` + `snapshot` + `core.sculpt_ops`; o preview ao vivo é avaliado com `core.bezier` (vetorizado) em vez de `FCurve.evaluate`; `P(f)` em cache numpy `(N,4,4)`.
- **Trails após edição nativa (bug corrigido, patch P7)**: G (Move) seguido de I, ou edição no Graph Editor, só atualizava a Action — o update de depsgraph da Action não traz `is_updated_transform`/`is_updated_geometry` e a Action não estava nas dependências do alvo —, então a trail ficava no caminho antigo até o Refresh. `build_deps` agora inclui a Action do objeto e `depsgraph_changed` aceita updates de Action. Regressão: `scenario_native_edit_refresh.py` (G+I duas vezes na Vale: erro 0,154 m antes, 0,0 depois) e `test_trails.py::test_action_update_invalidates_trail`.
- **Loop** (pedido do mantenedor, só roadmap/design nesta branch): parte 1 no Escopo 2 (marcar Action cíclica, "Fechar loop" com última pose = primeira e tangentes casadas, validação, export como loop), parte 2 no Escopo 3 (trail fechada, edição propagada nas pontas). Ver [roadmap](roadmap.md) e [modelo](design/motion-sculpt-model.md).

## Parcialmente implementado

Nada.

## Quebrado

Nada conhecido.

## Limitações conhecidas (do plano)

- O native solver do LMP precisa de janela: em background/CI o engine é `STEP`. As trails seguem os modos de alvo do LMP (bones selecionados em Pose Mode ou fixados/pinned).
- A tool só faz **grab** de key point de translação; arc drag, retime, spacing e soft grab ainda não existem. A trail prevista ao vivo é avaliada com `core.bezier` (exata para o controle editado); a trail real só é recalculada ao soltar.
- O prefetch de `P(f)` (frame stepping, ~0,65 ms/frame) ainda mora em `sculpt_tool.py`; sem detecção de `P` constante. Vai para `anim/spaces` no próximo item.
- `core/` ainda não tem `falloff`, `timing_ops`, `solve`; não há `rig/` (adapters) nem `pipeline/`.
- Custo medido por mouse move: 0,19 ms só do operador no rig público; o custo de frame completo (reavaliação do Rigify + redesenho) **não** foi medido.
- Os testes de UI exigem display e não rodam no CI.
- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache. `location_space` hoje dá `P` só para o frame avaliado atual; para o preview analítico é preciso avançar o frame (frame stepping) — estratégia de prefetch e custo a medir no próximo item.
- O LMP upstream não tem testes e foi publicado há ~1 mês; nossos testes cobrem só o que usamos (engine STEP, provider, patches P3/P4). Native solver e desenho só verificados na GUI.

## Última implementação realizada

**`core/` + `anim/` + correção das trails** (esta branch, `feat/core-bezier-action-io`): ver os itens correspondentes em "O que funciona hoje". Achados que corrigem docs: no Blender 5.2 `BKE_fcurve_correct_bezpart` escala **cada handle independentemente**, só quando aquele handle sozinho ultrapassa o key vizinho no tempo (não a regra "soma dos dois > comprimento"), e o limiar de key exata na avaliação é **0,0001 frame** (não 0,01); a primeira versão do port, escrita de memória, divergia do Blender em até 1,8 com handles sobrepostos — corrigida lendo o fonte 5.2 (ver [blender-5.2-notes](development/blender-5.2-notes.md#avaliação-de-f-curve-fcurvecc)).

Antes (PR #5, `feat/interaction-spike`), **spike de interação** (agenda item 4, ADR 0010): `interaction/` (tool, gizmo, overlay, picking, estado, operador modal de grab), `anim/spaces.py`, harness de UI (`dev.py test ui`, `tests/ui/`), 23 testes de Blender novos. O ADR 0010 foi validado (opção 3, sem fallback).

**Achado importante**: a fórmula documentada `P(f) = M_arm · M_pose · M_basis⁻¹` (Motiontrail3D) está **errada** para bones com `Bone.use_local_location = False`, caso dos controles IK do Rigify (`hand_ik`, `foot_ik`; o `torso` tem `True`) — com ela o grab andou na direção errada (pego por teste). `location_space` pergunta ao Blender: `Object.convert_space(LOCAL → POSE)` com `location` 0 e eixos unitários (4 conversões; o head é afim em `location`) dá `P` exato, respeitando local location, herança e pose do pai. Docs corrigidas em `design/motion-sculpt-model.md`, `architecture.md`, `reference/editable-motion-trails.md`, `open-source-provenance.md` e `testing/blender-tests.md`.

Verificação de GUI (eventos simulados, 18 checagens passando): a tool liga a trail (engine NATIVE); hover escolhe a key; press inicia o modal; engine suspenso durante o drag; key point cai sob o cursor (erro 0,00 px); 0,19 ms por mouse move (operador); trail recalculada após soltar = rig (1e-4); um Ctrl+Z restaura as keys exatamente e Ctrl+Shift+Z reaplica; Esc restaura bit a bit; Ctrl+LMB não faz grab mas chega ao operador.

Antes (PR #4, `feat/vendor-lmp`): vendorização do LMP (`0e173fd`) em `trails/lmp/` com P1–P5 e a façade `trails/provider.py`; registro em `trails/__init__.py` e `__init__.py` (prefs, painéis, trails); toggle "Mostrar trails"; versão 0.2.0. Rig Rigify público gerado em tempo de teste e 8 testes de trails.

Destaque do P4: além de salvar/restaurar `animation_visualization.motion_path` em volta do solver nativo, o restore marca o rig para atualização; por isso o engine registra os IDs em `STATE.self_tagged` e `depsgraph_changed` ignora esse único update. Sem isso a trail recomputava para sempre na UI (bug achado por screenshot da GUI; coberto por teste de regressão).

Verificação visual: instância GUI do Blender (perfil de teste isolado, dirigida por script, pois o Blender MCP na porta 9876 deu timeout) abriu o asset local de ataque e habilitou trails em `hand_ik.R`, `foot_ik.L/R` e `torso`: trails desenhadas pelo engine NATIVE (40 frames cada), keys como losangos amarelos e marcadores do frame atual.

Antes: assets de teste de ataque (PR #3; inspeção do rig Rigify em [rig-adapter](design/rig-adapter.md#inspeção-do-rig-de-teste-2026-10-03)), esqueleto do repositório (PR #2) e planejamento (PR #1).

## Testes

| Suite | Passa | Falha | Observação |
|---|---|---|---|
| unit | 38 | 0 | CI (pytest, Python 3.13); local Python 3.12. 8 project + 9 `fcurve_model` + 17 `core_bezier` + 4 `sculpt_ops` |
| blender | 61 | 0 | Windows, Blender 5.2.1, com o asset local gerado. Sem o asset (CI) os testes que dependem dele pulam (`test_attack_asset.py` e parte de `test_trails.py`), o resto passa — inclui paridade Bézier, `action_io`, trails e grab no rig público gerado |
| ui | 27 checagens | 0 | `dev.py test ui` (`scenario_spike.py` 18 + `scenario_release_refresh.py` 6 + `scenario_native_edit_refresh.py` 3), Windows, Blender 5.2.1 com janela; local, não roda no CI |
| manual | — | — | M0 (instalação) aplicável; verificação visual das trails feita pelo agente via GUI (não substitui o checklist do mantenedor) |
| godot | — | — | Escopo 2 |

## Ambiente conhecido

- Windows, Blender 5.2.1 instalado, Blender MCP instalado na máquina (útil para inspeção interativa por agentes; ver [testing/blender-tests.md](testing/blender-tests.md)). Para sessões do Claude Code, o MCP precisa estar registrado na configuração do Claude Code (extensão do Claude Desktop só aparece na aba Chat); só uma instância do Blender ocupa a porta 9876.
- Personagem de teste local: `D:\Projetos\Vale_Rig_Animations.blend` (não versionado; não modificar — tem uma idle antiga que os testes não usam).
- Godot **4.7.2**.
- Nome de exibição **Animation Sculptor**, ID `animation_sculptor`.
- Todo trabalho entra por PR para `main`; merge só pelo mantenedor ([workflow](development/workflow.md)).

## Medições (rig da Vale, Windows, Blender 5.2.1)

| Medida | Valor |
|---|---|
| Prefetch de `P(f)` no início do grab (40 frames, frame stepping + `convert_space`) | 25,9 ms (≈ 0,65 ms/frame) |
| Custo por mouse move do grab (escrita + `fcurve.update` + trail prevista), sem reavaliação do Rigify/redesenho | 0,44 ms (meta < 16 ms) |
| Refresh síncrono da trail ao soltar (native solver) | 43 ms |

## Próximo objetivo

1. Mantenedor: revisar o PR `feat/core-bezier-action-io` (`test all` + `test ui`; no Blender: mover um controle com G e keyar com I — a trail deve atualizar sem Refresh —, e arrastar um key point com a tool Animation Sculptor como antes).
2. Próximo item: `anim/spaces` — `P(f)` com prefetch e detecção de `P` constante — + `rig/` adapters Rigify e genérico, validados contra o rig gerado (agenda › Próximo).

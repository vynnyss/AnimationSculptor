# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — grab grava keys automaticamente, trail prevista ao vivo e refresh ao soltar (PR `fix/grab-autokey-live-trail`).

## Resumo

Planejamento (PR #1), esqueleto (PR #2), assets de ataque (PR #3), trails com o LMP vendorizado (PR #4) e o spike de interação (PR #5, [ADR 0010](decisions/0010-tool-gizmo-modal-interaction.md) validado) estão na `main`. Em revisão: **ajustes do grab pedidos no teste do mantenedor** — a edição sempre vira keyframe (eixos de `location` sem key no frame ganham key; F-Curve ausente é criada), a trail prevista é desenhada ao vivo durante o arrasto e a trail real é recalculada de forma síncrona ao soltar (antes dependia do timer do engine e, na máquina do mantenedor, só aparecia com I + Refresh). Ainda sem `core/`, arc drag, retime, spacing.

## O que funciona hoje

- Extensão `animation_sculptor` 0.2.0 (Blender 5.2): registra preferências, painéis, trails e interação (nessa ordem), em 3D Viewport › N › Animation Sculptor.
- `scripts/dev.py`: `link`/`unlink`, `test unit|blender|ui|all`, `build`, `validate`, `fetch-blender`. `test ui` abre um Blender com janela e roda cenários com eventos simulados (local, precisa de display; ver [blender-tests](testing/blender-tests.md#testes-de-ui-eventos-simulados)).
- `scripts/checks.py`: regras estáticas (core sem bpy, nomes de bones só em `rig/`, manifest, links da documentação).
- CI no GitHub verde: job `unit` (pytest real) e job `blender` (baixa o Blender 5.2.x, roda os testes de Blender — smoke + trails no rig público gerado — e `extension validate`).
- `python scripts/dev.py assets [--preview]`: gera `tests/assets/local/attack_test.blend` (gitignored) a partir do personagem configurado em `scripts/.dev.toml` (`character = '...'`) ou `ASC_TEST_CHARACTER`. Só o control rig visível; Action `asc_test_attack` (slot `OBrig`, key poses 1/10/16/18/26/40: idle → anticipation → attack → impact → follow-through → recovery; braço direito IK com a espada, braço esquerdo FK). Detalhes: [regression-assets](testing/regression-assets.md).
- `tests/blender/test_attack_asset.py` (11 testes) — pulam quando o asset não existe (caso do CI).
- **Trails** (`animation_sculptor/trails/`): `lmp/` é o Live Motion Path vendorizado (namespace `Scene.asc_trails`, classes `ASC_TR_*`, operadores `asc_trails.*`; patches P1–P5, sem P6) e `provider.py` é a façade: `Trail` (dataclass: `obj_name`, `bone`, `frames` int32, `points` float32 em mundo, `keyframes`, `complete`, `engine`, `point_at(frame)`), `settings/is_enabled/set_enabled/key_for/get_trail/targets/update_now/refresh/invalidate/suspend/resume/is_suspended`, context manager `suspended()` e `stats()`. O painel principal tem o toggle "Mostrar trails" (`scene.asc_trails.enabled`); os painéis do LMP ficam aninhados como "Trails"; onion skin desligado por padrão.
- Rig público de teste gerado em tempo de teste por `tests/blender/public_rig.py` (metarig Human → `pose.rigify_generate` num Blender de fundo separado, ~6 s, uma vez por sessão), com Action `asc_public_test` ([regression-assets](testing/regression-assets.md)). Nenhum binário no repo; roda no CI.
- `tests/blender/test_trails.py` (8 testes): ver [blender-tests](testing/blender-tests.md).
- **Interação (spike)** (`animation_sculptor/interaction/`): tool `ASC_WT_sculpt` (id `animation_sculptor.sculpt`, Pose Mode, depois de Transform; clique seleciona bone, shift+clique alterna, arrasto em vazio = caixa) com o grupo de gizmos `ASC_GGT_trails` (ligado à tool; liga as trails ao ativar) e o gizmo `ASC_GT_trail_points` (hover por `test_select`, 12 px, keys favorecidas; texto no header; anel desenhado por `overlay.py`: branco = key, azul claro = in-between, laranja no gesto). LMB num ponto sob hover inicia o operador modal `asc.sculpt_gesture`: em key point de **controle de translação** faz o **grab** (delta de mouse no plano da vista → `Δl = R(f)⁻¹Δw`, aplicado rígido em key+handles do frame, eixos travados pulados, Shift = precisão ×0,1; soltar = 1 passo de undo + `provider.resume`; Esc/RMB = restaura o snapshot bit a bit). Recusas com motivo: sem Action, NLA ativa, influence/blend, driver em `location`, modificador de F-Curve, sem key de `location` no frame, ponto in-between ("arc drag: próximo"), Ctrl+LMB ("tempo (retime/spacing): ainda não implementado" — prova que o Ctrl+LMB chega ao operador via gizmo).
- `anim/spaces.py::location_space(ob, pb)`: espaço-base `P` por `Object.convert_space` (ver "Achado" abaixo).
- **Grab (ajustes pós-teste)**: a edição é sempre gravada como keyframe — eixos livres de `location` sem key no frame do key point recebem uma (valor avaliado) e F-Curves ausentes são criadas (`channelbag.fcurves.ensure`); Esc remove o que foi inserido (bit a bit). No início do gesto `P(f)` é pré-calculado para todos os frames da trail (frame stepping + `location_space`) e o overlay desenha a **trail prevista ao vivo** (`P(f) @ location(f)`, amarela) sobre a trail antiga (fantasma). Ao soltar, `provider.resume` + **`update_now()` síncrono** recalculam a trail do controle. Qualquer tecla que não seja de navegação durante o gesto confirma o gesto e é repassada (um release perdido nunca deixa o gesto/engine pendurado).
- `tests/blender/test_sculpt_gesture.py` (27 testes) e `tests/ui/` (`run_ui.py`, `scenario_spike.py` 18 checagens, `scenario_release_refresh.py` 6 checagens no asset da Vale quando existe): ver [blender-tests](testing/blender-tests.md).

## Parcialmente implementado

Nada.

## Quebrado

Nada conhecido.

## Limitações conhecidas (do plano)

- O native solver do LMP precisa de janela: em background/CI o engine é `STEP`. As trails seguem os modos de alvo do LMP (bones selecionados em Pose Mode ou fixados/pinned).
- A tool só faz **grab** de key point de translação; arc drag, retime, spacing, soft grab e preview analítico da trail durante o gesto ainda não existem (a trail só é recalculada ao soltar).
- Código de F-Curves do spike mora em `interaction/sculpt_tool.py` (sem `core/`, sem `anim/action_io`); migra no próximo item (dívida técnica na [agenda](agenda.md#dívida-técnica)).
- Custo medido por mouse move: 0,19 ms só do operador no rig público; o custo de frame completo (reavaliação do Rigify + redesenho) **não** foi medido.
- Os testes de UI exigem display e não rodam no CI.
- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache. `location_space` hoje dá `P` só para o frame avaliado atual; para o preview analítico é preciso avançar o frame (frame stepping) — estratégia de prefetch e custo a medir no próximo item.
- O LMP upstream não tem testes e foi publicado há ~1 mês; nossos testes cobrem só o que usamos (engine STEP, provider, patches P3/P4). Native solver e desenho só verificados na GUI.

## Última implementação realizada

**Spike de interação** (esta branch, agenda item 4, ADR 0010): `interaction/` (tool, gizmo, overlay, picking, estado, operador modal de grab), `anim/spaces.py`, harness de UI (`dev.py test ui`, `tests/ui/`), 23 testes de Blender novos. O ADR 0010 foi validado (opção 3, sem fallback).

**Achado importante**: a fórmula documentada `P(f) = M_arm · M_pose · M_basis⁻¹` (Motiontrail3D) está **errada** para bones com `Bone.use_local_location = False`, caso dos controles IK do Rigify (`hand_ik`, `foot_ik`; o `torso` tem `True`) — com ela o grab andou na direção errada (pego por teste). `location_space` pergunta ao Blender: `Object.convert_space(LOCAL → POSE)` com `location` 0 e eixos unitários (4 conversões; o head é afim em `location`) dá `P` exato, respeitando local location, herança e pose do pai. Docs corrigidas em `design/motion-sculpt-model.md`, `architecture.md`, `reference/editable-motion-trails.md`, `open-source-provenance.md` e `testing/blender-tests.md`.

Verificação de GUI (eventos simulados, 18 checagens passando): a tool liga a trail (engine NATIVE); hover escolhe a key; press inicia o modal; engine suspenso durante o drag; key point cai sob o cursor (erro 0,00 px); 0,19 ms por mouse move (operador); trail recalculada após soltar = rig (1e-4); um Ctrl+Z restaura as keys exatamente e Ctrl+Shift+Z reaplica; Esc restaura bit a bit; Ctrl+LMB não faz grab mas chega ao operador.

Antes (PR #4, `feat/vendor-lmp`): vendorização do LMP (`0e173fd`) em `trails/lmp/` com P1–P5 e a façade `trails/provider.py`; registro em `trails/__init__.py` e `__init__.py` (prefs, painéis, trails); toggle "Mostrar trails"; versão 0.2.0. Rig Rigify público gerado em tempo de teste e 8 testes de trails.

Destaque do P4: além de salvar/restaurar `animation_visualization.motion_path` em volta do solver nativo, o restore marca o rig para atualização; por isso o engine registra os IDs em `STATE.self_tagged` e `depsgraph_changed` ignora esse único update. Sem isso a trail recomputava para sempre na UI (bug achado por screenshot da GUI; coberto por teste de regressão).

Verificação visual: instância GUI do Blender (perfil de teste isolado, dirigida por script, pois o Blender MCP na porta 9876 deu timeout) abriu o asset local de ataque e habilitou trails em `hand_ik.R`, `foot_ik.L/R` e `torso`: trails desenhadas pelo engine NATIVE (40 frames cada), keys como losangos amarelos e marcadores do frame atual.

Antes: assets de teste de ataque (PR #3; inspeção do rig Rigify em [rig-adapter](design/rig-adapter.md#inspeção-do-rig-de-teste-2026-10-03)), esqueleto do repositório (PR #2) e planejamento (PR #1).

## Testes

| Suite | Passa | Falha | Observação |
|---|---|---|---|
| unit | 8 | 0 | CI (pytest, Python 3.13); local Python 3.12 |
| blender | 51 | 0 | Windows, Blender 5.2.1, com o asset local gerado. Sem o asset (CI): 12 pulam (11 em `test_attack_asset.py` + 1 em `test_trails.py`), o resto passa — inclui trails e grab no rig público gerado |
| ui | 24 checagens | 0 | `dev.py test ui` (`scenario_spike.py` + `scenario_release_refresh.py`), Windows, Blender 5.2.1 com janela; local, não roda no CI |
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

1. Mantenedor: revisar o PR `fix/grab-autokey-live-trail` (`test all` + `test ui`; no Blender: arrastar um key point de `hand_ik.R` e ver a trail amarela ao vivo e a trail recalculada ao soltar, sem I/Refresh).
2. Próximo item: `core/fcurve_model` + `core/bezier` (paridade com `FCurve.evaluate`, já em andamento) + `anim/action_io` + `anim/snapshot`, migrando o código de F-Curves do spike.

# 0010 — Interação: WorkSpaceTool + Gizmo (hover) + modal (gesto)

- Status: aceito — validado pelo spike em 2026-10-03; o *que* o picking procura é estendido pelo [ADR 0013](0013-body-and-trail-interaction.md) (malha no modo Corpo)
- Data: 2026-10-03

## Contexto e problema

Precisamos de hover contínuo sobre pontos da trail, clique/arrasto com um passo de undo por gesto, cancel, e convivência com o resto do viewport (seleção de bones, transform, navegação, autosave).

## Opções consideradas

1. Objetos reais na cena como controles (Motiontrail3D) — rejeitado por [ADR 0003](0003-native-blender-animation-output.md).
2. Modal de longa duração com `PASS_THROUGH` (Motion Trail). Simples; mas bloqueia autosave enquanto ativo e intercepta eventos o tempo todo.
3. **`WorkSpaceTool` em Pose Mode + `Gizmo` customizado** (hover/picking via `test_select`, desenho do realce) **+ operador modal disparado no clique** para o gesto.

## Decisão

Opção 3, com a 2 como fallback documentado.

## Justificativa

Tool e gizmo são o mecanismo moderno do Blender para ferramentas de viewport (o fork IMP também usa gizmo); hover fica nativo; o modal só existe durante o gesto ⇒ undo limpo e sem bloquear autosave.

## Consequências

- Primeiro item da Iteração 1: spike provando hover + drag + undo com gizmo Python num rig Rigify (feito, ver "Resultado do spike" abaixo; o fallback não foi necessário).
- Desenho das trails continua no draw handler do LMP; o gizmo desenha só o realce/estado.
- Detalhes de UX: [design/viewport-interaction.md](../design/viewport-interaction.md).

## Resultado do spike (2026-10-03)

**Opção 3 confirmada; o fallback (opção 2) não é necessário.** Validado no Blender 5.2.1 (Windows), num rig Rigify público, por 23 testes de Blender em background (`tests/blender/test_sculpt_gesture.py`) e por um cenário de GUI com eventos simulados (`tests/ui/scenario_spike.py`, 18 checagens, todas passando; ver [testing/blender-tests](../testing/blender-tests.md#testes-de-ui-eventos-simulados)).

O que foi construído: `WorkSpaceTool` `animation_sculptor.sculpt` (Pose Mode) + grupo de gizmos `ASC_GGT_trails` com o gizmo `ASC_GT_trail_points` + operador modal `asc.sculpt_gesture` (grab de key point de controle de translação).

Fatos aprendidos:

- **Hover**: `Gizmo.test_select(context, location)` funciona para hover em pontos arbitrários em espaço de tela (hit-test próprio em `interaction/picking.py`, 12 px, keys favorecidas por 2 px); o resultado vai para `interaction/state.HOVER` e o desenho do anel é um handler POST_PIXEL separado (`overlay.py`).
- **Clique**: `Gizmo.target_set_operator("asc.sculpt_gesture")` entrega ao nosso operador modal o LMB e também o Ctrl+LMB sobre o ponto sob hover (necessário para retime/spacing); sobre espaço vazio, o keymap da tool (clique, shift+clique, caixa) segue com a seleção nativa de bones.
- **Undo**: operador modal com `REGISTER` + `UNDO` que termina com `FINISHED` produz **exatamente um passo de undo**, verificado com Ctrl+Z e Ctrl+Shift+Z simulados. `Esc`/RMB restauram o snapshot das F-Curves bit a bit.
- **Vínculo à tool**: o grupo de gizmos usa `bl_widget` na tool e `poll` que checa a tool ativa; só existe com a tool ativa.
- **Limitação**: propriedades de ID não podem ser escritas no `setup` do gizmo (contexto restrito) ⇒ o `setup` agenda um timer que liga as trails.
- **Harness**: `Window.event_simulate` (exige `--enable-event-simulate`) permite regressão de GUI automatizada (`dev.py test ui`); só local, precisa de display.
- **Custo**: 0,19 ms por mouse move no rig público (só a parte do operador: escrita + atualização da F-Curve; não inclui reavaliação do depsgraph/Rigify nem redesenho). Meta < 16 ms atendida para essa parte; o custo de frame completo ainda não foi medido.

Achado paralelo, que corrige a documentação: a fórmula `P(f) = M_arm · M_pose · M_basis⁻¹` (Motiontrail3D) está **errada** para bones com `use_local_location = False` (controles IK do Rigify), o que fez o grab andar na direção errada nos testes. O espaço-base passou a ser obtido perguntando ao Blender (`Object.convert_space` LOCAL → POSE); ver [design/motion-sculpt-model](../design/motion-sculpt-model.md#conceitos).

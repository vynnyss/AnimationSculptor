# 0010 — Interação: WorkSpaceTool + Gizmo (hover) + modal (gesto)

- Status: aceito, a validar com spike no início da Iteração 1
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

- Primeiro item da Iteração 1: spike de 1–2 dias provando hover + drag + undo com gizmo Python num rig Rigify. Se falhar, registrar resultado aqui e usar a opção 2.
- Desenho das trails continua no draw handler do LMP; o gizmo desenha só o realce/estado.
- Detalhes de UX: [design/viewport-interaction.md](../design/viewport-interaction.md).

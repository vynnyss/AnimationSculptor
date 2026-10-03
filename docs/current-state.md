# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — planejamento inicial + decisões de nome/ID/Godot + fluxo de PR.

## Resumo

Fase de **planejamento concluída**; **nenhum código** existe. Repositório: `vynnyss/AnimationSculptor`. `main` contém só o commit inicial; o planejamento (`docs/`, `README.md`, `CLAUDE.md`) está no PR `docs/planning` aguardando revisão do mantenedor.

## O que funciona hoje

Nada executável.

## Parcialmente implementado

Nada.

## Quebrado

Nada.

## Limitações conhecidas (do plano)

- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache (custo de prefetch a medir).
- O LMP vendorizado não tem testes e foi publicado há ~1 mês.

## Última implementação realizada

Planejamento: análise de LMP, Motion Trail, Motiontrail3D (o repo "Editable Motion Trails" é port dele, não do Motion Trail), Interactive Motion Path, BlenderAddonTemplate, GameRig, Rigodotify e addons comerciais; arquitetura, roadmap, ADRs 0001–0010, estratégia de testes.

## Testes

| Suite | Passa | Falha |
|---|---|---|
| unit | — | — |
| blender | — | — |
| manual | — | — |
| godot | — | — |

## Ambiente conhecido

- Windows, Blender 5.2 instalado, Blender MCP instalado na máquina (útil para inspeção interativa por agentes; ver [testing/blender-tests.md](testing/blender-tests.md)).
- Godot **4.7.2**.
- Nome de exibição **Animation Sculptor**, ID `animation_sculptor`.
- Todo trabalho entra por PR para `main`; merge só pelo mantenedor ([workflow](development/workflow.md)).

## Próximo objetivo

Merge do PR de planejamento pelo mantenedor → Agenda › **Agora**: esqueleto do repo (PR próprio) + `dev.py` + testes rodando no Blender 5.2 → assets de teste → vendorizar LMP → spike de interação.

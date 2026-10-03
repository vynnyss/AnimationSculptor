# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — esqueleto do repositório (PR `feat/repo-skeleton`).

## Resumo

Planejamento mergeado na `main` (PR #1). Em revisão: **esqueleto do repositório** — extensão vazia instalável, `scripts/dev.py`, testes unitários e de Blender, CI. Nenhuma funcionalidade de animação ainda.

## O que funciona hoje

- Extensão `animation_sculptor` 0.1.0 (Blender 5.2): registra preferências e um painel informativo em 3D Viewport › N › Animation Sculptor.
- `scripts/dev.py`: `link`/`unlink`, `test unit|blender|all`, `build`, `validate`, `fetch-blender`.
- `scripts/checks.py`: regras estáticas (core sem bpy, nomes de bones só em `rig/`, manifest, links da documentação).
- CI no GitHub verde: job `unit` (pytest real) e job `blender` (baixa o Blender 5.2.x, roda os testes de smoke dentro dele e `extension validate`).

## Parcialmente implementado

Nada.

## Quebrado

Nada conhecido.

## Limitações conhecidas (do plano)

- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache (custo de prefetch a medir).
- O LMP vendorizado não tem testes e foi publicado há ~1 mês.

## Última implementação realizada

Esqueleto do repositório: pacote `animation_sculptor/` (manifest, `__init__` sem `bpy` no topo, `core/`, `ui/prefs.py`, `ui/panels.py`, `THIRD_PARTY_NOTICES.md`), `scripts/dev.py`, `scripts/checks.py`, `tests/unit`, `tests/blender` (runner + smoke), `pyproject.toml`, `.github/workflows/tests.yml`. Antes disso: planejamento completo (PR #1).

## Testes

| Suite | Passa | Falha | Observação |
|---|---|---|---|
| unit | 8 | 0 | CI (pytest, Python 3.13) |
| blender | 5 | 0 | CI Linux com Blender 5.2.x; falta confirmar no Windows do mantenedor |
| manual | — | — | M0 (instalação) aplicável a partir deste PR |
| godot | — | — | Escopo 2 |

## Ambiente conhecido

- Windows, Blender 5.2 instalado, Blender MCP instalado na máquina (útil para inspeção interativa por agentes; ver [testing/blender-tests.md](testing/blender-tests.md)).
- Godot **4.7.2**.
- Nome de exibição **Animation Sculptor**, ID `animation_sculptor`.
- Todo trabalho entra por PR para `main`; merge só pelo mantenedor ([workflow](development/workflow.md)).

## Próximo objetivo

Merge do esqueleto (após `python scripts/dev.py test all` passar na máquina do mantenedor) → Agenda › **Agora**: assets de teste reproduzíveis → vendorizar LMP → spike de interação.

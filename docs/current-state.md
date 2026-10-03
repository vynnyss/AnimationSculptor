# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — assets de teste de ataque (PR `test/attack-test-assets`).

## Resumo

Planejamento (PR #1) e esqueleto do repositório (PR #2) mergeados na `main`. Em revisão: **assets de teste** — `scripts/make_test_assets.py` gera, a partir do personagem Rigify local do usuário, uma cópia com a Action de ataque `asc_test_attack` + testes de Blender que a usam. Nenhuma funcionalidade de animação no addon ainda.

## O que funciona hoje

- Extensão `animation_sculptor` 0.1.0 (Blender 5.2): registra preferências e um painel informativo em 3D Viewport › N › Animation Sculptor.
- `scripts/dev.py`: `link`/`unlink`, `test unit|blender|all`, `build`, `validate`, `fetch-blender`.
- `scripts/checks.py`: regras estáticas (core sem bpy, nomes de bones só em `rig/`, manifest, links da documentação).
- CI no GitHub verde: job `unit` (pytest real) e job `blender` (baixa o Blender 5.2.x, roda os testes de smoke dentro dele e `extension validate`).
- `python scripts/dev.py assets [--preview]`: gera `tests/assets/local/attack_test.blend` (gitignored) a partir do personagem configurado em `scripts/.dev.toml` (`character = '...'`) ou `ASC_TEST_CHARACTER`. Só o control rig visível; Action `asc_test_attack` (slot `OBrig`, key poses 1/10/16/18/26/40: idle → anticipation → attack → impact → follow-through → recovery; braço direito IK com a espada, braço esquerdo FK). Detalhes: [regression-assets](testing/regression-assets.md).
- `tests/blender/test_attack_asset.py` (11 testes) — pulam quando o asset não existe (caso do CI).

## Parcialmente implementado

Nada.

## Quebrado

Nada conhecido.

## Limitações conhecidas (do plano)

- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache (custo de prefetch a medir).
- O LMP vendorizado não tem testes e foi publicado há ~1 mês.

## Última implementação realizada

Assets de teste: inspeção do rig Rigify do personagem de teste (mapa de controles/props/rotation modes confirmado em [rig-adapter](design/rig-adapter.md#inspeção-do-rig-de-teste-2026-10-03); APIs de Slotted Actions confirmadas em [blender-5.2-notes](development/blender-5.2-notes.md)), `scripts/make_test_assets.py`, comando `dev.py assets`, testes do asset. Antes: esqueleto do repositório (PR #2) e planejamento (PR #1).

## Testes

| Suite | Passa | Falha | Observação |
|---|---|---|---|
| unit | 8 | 0 | CI (pytest, Python 3.13); local Python 3.12 |
| blender | 16 | 0 | Windows, Blender 5.2.1, com o asset local gerado. Sem o asset (CI): 5 passam, 11 pulam |
| manual | — | — | M0 (instalação) aplicável a partir deste PR |
| godot | — | — | Escopo 2 |

## Ambiente conhecido

- Windows, Blender 5.2.1 instalado, Blender MCP instalado na máquina (útil para inspeção interativa por agentes; ver [testing/blender-tests.md](testing/blender-tests.md)). Para sessões do Claude Code, o MCP precisa estar registrado na configuração do Claude Code (extensão do Claude Desktop só aparece na aba Chat); só uma instância do Blender ocupa a porta 9876.
- Personagem de teste local: `D:\Projetos\Vale_Rig_Animations.blend` (não versionado; não modificar — tem uma idle antiga que os testes não usam).
- Godot **4.7.2**.
- Nome de exibição **Animation Sculptor**, ID `animation_sculptor`.
- Todo trabalho entra por PR para `main`; merge só pelo mantenedor ([workflow](development/workflow.md)).

## Próximo objetivo

Merge dos assets de teste (mantenedor: `dev.py assets --preview` + `test all`) → Agenda › **Agora**: vendorizar LMP com trails no rig de teste → spike de interação.

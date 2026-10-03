# Estado atual

> Leia primeiro. Responde "onde estamos" para qualquer sessão/agente nova. Atualizar ao final de cada sessão significativa.

**Última atualização:** 2026-10-03 — LMP vendorizado com patches P1–P5 + `trails/provider.py` (PR `feat/vendor-lmp`).

## Resumo

Planejamento (PR #1), esqueleto do repositório (PR #2) e assets de teste de ataque (PR #3) mergeados na `main`. Em revisão: **trails** — o Live Motion Path (`0e173fd`) está vendorizado em `animation_sculptor/trails/lmp/` com os patches P1–P5, atrás da façade `trails/provider.py`, e o painel principal ganhou o toggle "Mostrar trails". Os testes de trails rodam no CI sobre um rig Rigify **público** gerado em tempo de teste. Ainda não há ferramenta/gizmo próprio nem edição de animação.

## O que funciona hoje

- Extensão `animation_sculptor` 0.2.0 (Blender 5.2): registra preferências, painéis e trails (nessa ordem), em 3D Viewport › N › Animation Sculptor.
- `scripts/dev.py`: `link`/`unlink`, `test unit|blender|all`, `build`, `validate`, `fetch-blender`.
- `scripts/checks.py`: regras estáticas (core sem bpy, nomes de bones só em `rig/`, manifest, links da documentação).
- CI no GitHub verde: job `unit` (pytest real) e job `blender` (baixa o Blender 5.2.x, roda os testes de Blender — smoke + trails no rig público gerado — e `extension validate`).
- `python scripts/dev.py assets [--preview]`: gera `tests/assets/local/attack_test.blend` (gitignored) a partir do personagem configurado em `scripts/.dev.toml` (`character = '...'`) ou `ASC_TEST_CHARACTER`. Só o control rig visível; Action `asc_test_attack` (slot `OBrig`, key poses 1/10/16/18/26/40: idle → anticipation → attack → impact → follow-through → recovery; braço direito IK com a espada, braço esquerdo FK). Detalhes: [regression-assets](testing/regression-assets.md).
- `tests/blender/test_attack_asset.py` (11 testes) — pulam quando o asset não existe (caso do CI).
- **Trails** (`animation_sculptor/trails/`): `lmp/` é o Live Motion Path vendorizado (namespace `Scene.asc_trails`, classes `ASC_TR_*`, operadores `asc_trails.*`; patches P1–P5, sem P6) e `provider.py` é a façade: `Trail` (dataclass: `obj_name`, `bone`, `frames` int32, `points` float32 em mundo, `keyframes`, `complete`, `engine`, `point_at(frame)`), `settings/is_enabled/set_enabled/key_for/get_trail/targets/update_now/refresh/invalidate/suspend/resume/is_suspended`, context manager `suspended()` e `stats()`. O painel principal tem o toggle "Mostrar trails" (`scene.asc_trails.enabled`); os painéis do LMP ficam aninhados como "Trails"; onion skin desligado por padrão.
- Rig público de teste gerado em tempo de teste por `tests/blender/public_rig.py` (metarig Human → `pose.rigify_generate` num Blender de fundo separado, ~6 s, uma vez por sessão), com Action `asc_public_test` ([regression-assets](testing/regression-assets.md)). Nenhum binário no repo; roda no CI.
- `tests/blender/test_trails.py` (8 testes): ver [blender-tests](testing/blender-tests.md).

## Parcialmente implementado

Nada.

## Quebrado

Nada conhecido.

## Limitações conhecidas (do plano)

- O native solver do LMP precisa de janela: em background/CI o engine é `STEP`. As trails seguem os modos de alvo do LMP (bones selecionados em Pose Mode ou fixados/pinned).
- Ainda não existe ferramenta/gizmo próprio (próximo item: spike de interação, ADR 0010).
- Iteração 1 esculpe espacialmente só **controles de translação** (IK de mão/pé, poles, torso, root). FK recebe apenas timing/spacing até o Escopo 4.
- Bones de Rigify não têm avaliação barata no engine do LMP: preview durante o gesto depende de `P(f)` em cache (custo de prefetch a medir).
- O LMP upstream não tem testes e foi publicado há ~1 mês; nossos testes cobrem só o que usamos (engine STEP, provider, patches P3/P4). Native solver e desenho só verificados na GUI.

## Última implementação realizada

Vendorização do LMP (`0e173fd`) em `trails/lmp/` com P1–P5 e a façade `trails/provider.py`; registro em `trails/__init__.py` e `__init__.py` (prefs, painéis, trails); toggle "Mostrar trails"; versão 0.2.0. Rig Rigify público gerado em tempo de teste e 8 testes de trails.

Destaque do P4: além de salvar/restaurar `animation_visualization.motion_path` em volta do solver nativo, o restore marca o rig para atualização; por isso o engine registra os IDs em `STATE.self_tagged` e `depsgraph_changed` ignora esse único update. Sem isso a trail recomputava para sempre na UI (bug achado por screenshot da GUI; coberto por teste de regressão).

Verificação visual: instância GUI do Blender (perfil de teste isolado, dirigida por script, pois o Blender MCP na porta 9876 deu timeout) abriu o asset local de ataque e habilitou trails em `hand_ik.R`, `foot_ik.L/R` e `torso`: trails desenhadas pelo engine NATIVE (40 frames cada), keys como losangos amarelos e marcadores do frame atual.

Antes: assets de teste de ataque (PR #3; inspeção do rig Rigify em [rig-adapter](design/rig-adapter.md#inspeção-do-rig-de-teste-2026-10-03)), esqueleto do repositório (PR #2) e planejamento (PR #1).

## Testes

| Suite | Passa | Falha | Observação |
|---|---|---|---|
| unit | 8 | 0 | CI (pytest, Python 3.13); local Python 3.12 |
| blender | 24 | 0 | Windows, Blender 5.2.1, com o asset local gerado. Sem o asset (CI): 12 pulam (11 em `test_attack_asset.py` + 1 em `test_trails.py`), o resto passa — inclui os testes de trails no rig público gerado |
| manual | — | — | M0 (instalação) aplicável; verificação visual das trails feita pelo agente via GUI (não substitui o checklist do mantenedor) |
| godot | — | — | Escopo 2 |

## Ambiente conhecido

- Windows, Blender 5.2.1 instalado, Blender MCP instalado na máquina (útil para inspeção interativa por agentes; ver [testing/blender-tests.md](testing/blender-tests.md)). Para sessões do Claude Code, o MCP precisa estar registrado na configuração do Claude Code (extensão do Claude Desktop só aparece na aba Chat); só uma instância do Blender ocupa a porta 9876.
- Personagem de teste local: `D:\Projetos\Vale_Rig_Animations.blend` (não versionado; não modificar — tem uma idle antiga que os testes não usam).
- Godot **4.7.2**.
- Nome de exibição **Animation Sculptor**, ID `animation_sculptor`.
- Todo trabalho entra por PR para `main`; merge só pelo mantenedor ([workflow](development/workflow.md)).

## Próximo objetivo

Merge do PR `feat/vendor-lmp` (mantenedor: `test all` + abrir o asset, habilitar "Mostrar trails" e selecionar controles em Pose Mode) → Agenda › **Agora**: **spike de interação** (tool + gizmo hover + modal drag + 1 undo por gesto; ADR 0010).

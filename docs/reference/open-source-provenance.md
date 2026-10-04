# Proveniência de código open-source

> Registro obrigatório de todo código copiado, portado ou adaptado. Regra: **verificar licença antes de copiar**; preservar copyright e notices; marcar o código no fonte. Política em [ADR 0007](../decisions/0007-gpl-and-reuse-policy.md).

## Estado

Código de terceiros no repo: **algoritmos de avaliação de F-Curve do Blender** (`fcurve.cc` 5.2, GPL-2+) portados em `animation_sculptor/core/bezier.py` e `compat.get_fcurves` do LMP adaptado em `anim/action_io.py`; e o **Live Motion Path** (`0e173fd`, GPL-3+, copyright "2026 Experience Elysian") vendorizado em `animation_sculptor/trails/lmp/` (`__init__.py`, `compat.py`, `engine.py`, `draw.py`, `handlers.py`, `props.py`, `ops.py`, `ui.py`), na branch `feat/vendor-lmp`. O `LICENSE` upstream é idêntico ao da raiz. O `prefs.py` upstream **não** foi vendorizado; o `ui.py` foi vendorizado com P5. A fachada `trails/provider.py` é código nosso.

Patches aplicados (todos marcados `# ASC-PATCH Pn` no código):

- **P1**: namespace renomeado em todos os arquivos: `Scene.motion_onion` → `Scene.asc_trails`, classes `LMO_*` → `ASC_TR_*` (não `ASC_*`, pois `ASC_PT_main` é painel nosso), operadores `motion_onion.*` → `asc_trails.*`.
- **P2**: imports já eram relativos ao pacote no upstream; `lmp/__init__.py` adaptado (sem `prefs`; registro feito por `animation_sculptor/trails/__init__.py`).
- **P3**: `engine.suspend()`, `engine.resume(keys)`, `engine.is_suspended()`, `engine.invalidate_keys(keys)`; suspenso, `schedule()`, ticks do timer, `frame_changed` e `depsgraph_changed` só registram uma atualização pendente; trails em cache continuam desenhadas (fantasma durante o gesto de sculpt).
- **P4**: o native solver (`native_object_path`, `native_bone_paths`) salva e restaura `animation_visualization.motion_path` (type, range, frame_start, frame_end, bake_location).
- **P5**: painéis na aba Animation Sculptor, aninhados em `ASC_PT_main` (painel LMP principal renomeado "Trails"); sem botão no header, sem entradas no popover Overlays, sem preferências próprias; `onion_show` padrão False.
- **P6** (remover ramos < 5.0 de `compat.py`): **não aplicado**.
- **P7**: `build_deps` inclui a Action do objeto nas dependências do alvo e `depsgraph_changed` aceita updates de `bpy.types.Action` além de `is_updated_transform`/`is_updated_geometry`. Sem isso, keyar (I) ou editar no Graph Editor após um G nativo só atualizava a Action e a trail ficava no caminho antigo até o Refresh.
- **P9**: ponto de referência por alvo: `engine.BONE_POINT_RESOLVER` + `engine.bone_point`; os native solves são agrupados por (armature, ponto) e o marcador do frame atual segue o mesmo ponto. O resolvedor é nosso (`trails/provider.py`, a partir do adapter do rig); sem ele vale o "Bone Point" global do upstream. Sem isso a trail de controles FK seguia o HEAD (a junta) e quase não se movia.
- **P8**: o resultado do native solver (`pose.paths_calculate`) é rejeitado quando todos os pontos estão na origem (falha silenciosa para bones que o solver não enxerga, ex.: controles FK numa coleção de bones oculta); só aquele bone cai para frame stepping (`(obj, bone)` em `STATE.native_failed`). Revisado no PR #11: a comparação original com o bone vivo rejeitava trails válidas quando havia pose não keyada.
- **P10**: o frame stepping (`run_step_job`) preserva a pose não keyada dos armatures envolvidos (salva antes, devolve depois de voltar ao frame; o update dessa escrita é ignorado via `self_tagged`).

`scripts/dev.py` segue a *estrutura* do BlenderAddonTemplate (subcomandos build/test, pytest dentro do Blender), com código escrito do zero. As demais linhas da tabela abaixo são o **plano**; mudar a coluna "status" quando o código entrar no repo, com o commit de origem.

| Componente | Projeto origem | Arquivo origem (commit) | Licença | Estratégia | Destino | Status |
|---|---|---|---|---|---|---|
| Engine de trails, cache, scheduler | Live Motion Path | `engine.py` (`0e173fd`) | GPL-3+ | reutilizado + patches P1–P4, P7–P9 | `animation_sculptor/trails/lmp/engine.py` | no repo (`feat/vendor-lmp`) |
| Desenho GPU de paths/onion | Live Motion Path | `draw.py` (`0e173fd`) | GPL-3+ | reutilizado + P1, P9 | `trails/lmp/draw.py` | no repo (`feat/vendor-lmp`) |
| Compat 5.x, handlers, props, ops, ui | Live Motion Path | `compat.py`, `handlers.py`, `props.py`, `ops.py`, `ui.py` (`0e173fd`) | GPL-3+ | reutilizado + P1/P3/P5 (`ui.py` com P5; `prefs.py` não vendorizado; P6 não aplicado) | `trails/lmp/` | no repo (`feat/vendor-lmp`) |
| Acesso a F-Curves via channelbag | Live Motion Path | `compat.get_fcurves` (`0e173fd`) | GPL-3+ | adaptado (só 5.2, + escrita) | `anim/action_io.py` | no repo (`feat/core-bezier-action-io`) |
| Tela ⇄ mundo | Motion Trail | `animation_motion_trail.py`: `screen_to_world`, `world_to_screen` (`14ab927` do espelho) | GPL-2+ | portado | `interaction/picking.py` | planejado (o spike usa `bpy_extras.view3d_utils` direto, sem código portado) |
| Regras de tipo de handle ao editar | Motion Trail | `drag()` modo location/handle | GPL-2+ | portado | `core/sculpt_ops.py` | planejado |
| Retime de key / time beads | Motion Trail | `drag()` modo timing | GPL-2+ | portado | `core/timing_ops.py` | planejado |
| Speed via `handle.x` | Motion Trail | `drag()` modo speed | GPL-2+ | adaptado (pose-wide, x idêntico entre canais) | `core/timing_ops.py` | planejado |
| Espaço-base `P(f)` | Motiontrail3D (port 4.1) | `calculate_parent_matrix_cache` (`aa13ea9`) | GPL-3 | **algoritmo substituído**: a fórmula do Motiontrail3D é incorreta com `use_local_location = False`; `location_space` usa `Object.convert_space` (código nosso). Motiontrail3D só como referência — nada portado | `anim/spaces.py` | no repo (`feat/interaction-spike`, código próprio) |
| Busca de `t` por frame / split Bézier | Motiontrail3D (port 4.1) | `bezier_search_frame`, `bezier_split*` (`aa13ea9`) | GPL-3 | **não usado**: substituído pelo `findzero`/`solve_cubic` do próprio Blender (porte exato, ver linha abaixo); nada do Motiontrail3D entrou. O split Bézier só voltará se um operador precisar | — | não usado |
| Avaliação Bézier de F-Curve | Blender | `fcurve.cc` (5.2): `fcurve_eval_keyframes`/`_extrapolate`/`_interpolate`, `binarysearch`, `BKE_fcurve_correct_bezpart`, `findzero`/`solve_cubic`, `berekeny` | GPL-2+ | algoritmo portado (reproduz float32/double; paridade bit a bit no teste) | `core/bezier.py` | no repo (`feat/core-bezier-action-io`) |
| Solver tangent-space + pins | Interactive Motion Path | `pose_anim_motion_curve.cc`: `MCSolver::solve`, `my_quadprog` (`4b5a6e7`) | GPL-2+ | algoritmo portado (Escopo 4) | `core/solve.py` | planejado |
| Gaussian/Butterworth smooth | Blender | operadores `graph.gaussian_smooth`, `graph.butterworth_smooth` (5.2) | GPL-2+ | algoritmo portado (Escopo 2) | `core/timing_ops.py` | planejado |
| Estrutura dev/test | BlenderAddonTemplate | `dev.py`, `run_tests.py` (`2b91ae1`) | GPL-3 | estrutura adaptada, código próprio | `scripts/dev.py`, `tests/blender/run.py` | no repo (esqueleto) |

## Regras de marcação no código

- Arquivo vendorizado inteiro: manter cabeçalho original (`SPDX-License-Identifier`, copyright) e adicionar abaixo:
  `# Vendored from <repo>@<commit> (<arquivo>). Modified for Animation Sculptor: see docs/reference/open-source-provenance.md`
- Trecho portado: comentário acima da função: `# Ported from <projeto> (<arquivo>:<função>, <licença>).`
- Patch em código vendorizado: `# ASC-PATCH Pn: <motivo>`.
- `animation_sculptor/THIRD_PARTY_NOTICES.md` lista projetos, autores, licenças e links; incluído no pacote da extensão.
- `blender_manifest.toml`: `license = ["SPDX:GPL-3.0-or-later"]` e `copyright` incluindo os autores do código vendorizado.

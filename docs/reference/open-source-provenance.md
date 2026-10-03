# Proveniência de código open-source

> Registro obrigatório de todo código copiado, portado ou adaptado. Regra: **verificar licença antes de copiar**; preservar copyright e notices; marcar o código no fonte. Política em [ADR 0007](../decisions/0007-gpl-and-reuse-policy.md).

## Estado

Nenhum código copiado ainda (fase de planejamento). A tabela abaixo é o **plano**; mudar a coluna "status" quando o código entrar no repo, com o commit de origem.

| Componente | Projeto origem | Arquivo origem (commit) | Licença | Estratégia | Destino | Status |
|---|---|---|---|---|---|---|
| Engine de trails, cache, scheduler | Live Motion Path | `engine.py` (`0e173fd`) | GPL-3+ | reutilizado + patches P1–P4 | `animation_sculptor/trails/lmp/engine.py` | planejado |
| Desenho GPU de paths/onion | Live Motion Path | `draw.py` (`0e173fd`) | GPL-3+ | reutilizado + P1 | `trails/lmp/draw.py` | planejado |
| Compat 5.x, handlers, props, ops | Live Motion Path | `compat.py`, `handlers.py`, `props.py`, `ops.py` (`0e173fd`) | GPL-3+ | reutilizado + P1/P3/P5 | `trails/lmp/` | planejado |
| Acesso a F-Curves via channelbag | Live Motion Path | `compat.get_fcurves` (`0e173fd`) | GPL-3+ | adaptado (só 5.2, + escrita) | `anim/action_io.py` | planejado |
| Tela ⇄ mundo | Motion Trail | `animation_motion_trail.py`: `screen_to_world`, `world_to_screen` (`14ab927` do espelho) | GPL-2+ | portado | `interaction/picking.py` | planejado |
| Regras de tipo de handle ao editar | Motion Trail | `drag()` modo location/handle | GPL-2+ | portado | `core/sculpt_ops.py` | planejado |
| Retime de key / time beads | Motion Trail | `drag()` modo timing | GPL-2+ | portado | `core/timing_ops.py` | planejado |
| Speed via `handle.x` | Motion Trail | `drag()` modo speed | GPL-2+ | adaptado (pose-wide, x idêntico entre canais) | `core/timing_ops.py` | planejado |
| Matriz espaço-pai por frame `P(f)` | Motiontrail3D (port 4.1) | `calculate_parent_matrix_cache` (`aa13ea9`) | GPL-3 | portado | `anim/spaces.py` | planejado |
| Busca de `t` por frame / split Bézier | Motiontrail3D (port 4.1) | `bezier_search_frame`, `bezier_split*` (`aa13ea9`) | GPL-3 | portado (vetorizado numpy) | `core/bezier.py` | planejado |
| Avaliação Bézier de F-Curve | Blender | `BKE_fcurve` / `fcurve.cc` (5.2) | GPL-2+ | algoritmo portado | `core/bezier.py` | planejado |
| Solver tangent-space + pins | Interactive Motion Path | `pose_anim_motion_curve.cc`: `MCSolver::solve`, `my_quadprog` (`4b5a6e7`) | GPL-2+ | algoritmo portado (Escopo 4) | `core/solve.py` | planejado |
| Gaussian/Butterworth smooth | Blender | operadores `graph.gaussian_smooth`, `graph.butterworth_smooth` (5.2) | GPL-2+ | algoritmo portado (Escopo 2) | `core/timing_ops.py` | planejado |
| Estrutura dev/test | BlenderAddonTemplate | `dev.py`, `run_tests.py` (`2b91ae1`) | GPL-3 | adaptado | `scripts/dev.py` | planejado |

## Regras de marcação no código

- Arquivo vendorizado inteiro: manter cabeçalho original (`SPDX-License-Identifier`, copyright) e adicionar abaixo:
  `# Vendored from <repo>@<commit> (<arquivo>). Modified for Animation Sculptor: see docs/reference/open-source-provenance.md`
- Trecho portado: comentário acima da função: `# Ported from <projeto> (<arquivo>:<função>, <licença>).`
- Patch em código vendorizado: `# ASC-PATCH Pn: <motivo>`.
- `animation_sculptor/THIRD_PARTY_NOTICES.md` lista projetos, autores, licenças e links; incluído no pacote da extensão.
- `blender_manifest.toml`: `license = ["SPDX:GPL-3.0-or-later"]` e `copyright` incluindo os autores do código vendorizado.

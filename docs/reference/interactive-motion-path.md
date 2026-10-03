# Interactive Motion Path (Tangent-Space) — análise

- Repo: https://github.com/JiahuiCai/Blender_Interactive_Motion_Path — **fork do Blender** (2.9x/3.0 dev, último commit 2022-02-09).
- Arquivo principal: `source/blender/editors/armature/pose_anim_motion_curve.cc` (2.127 linhas, C++ com Eigen).
- Licença: GPL do Blender (`COPYING`; Blender é GPL-2.0-or-later). O arquivo não tem cabeçalho próprio.
- O próprio README: "presented for reference only… not ready for production… quaternions do not work at all".
- Estratégia: **referência / portar algoritmo** para numpy no Escopo 4. Nunca dependência ([ADR 0005](../decisions/0005-extension-not-fork.md), [ADR 0006](../decisions/0006-tangent-space-deferred.md)).

## O que o fork faz

Gizmo group (`POSE_GGT_motion_curve`) desenha motion paths dos bones selecionados e permite:

- **Arrastar** um ponto ⇒ altera a pose **no frame atual** (não no frame clicado). Se há key no frame: ajusta o valor; senão: ajusta **tangentes** das F-Curves vizinhas (é o "tangent-space").
- **Ctrl+clique**: pin de ponto (ou da trail inteira). **Shift+arrastar** em segmento: interpolação linear em mundo entre duas posições.
- Por bone: filtrar F-Curves envolvidas, tamanho da cadeia (2 = IK de braço/perna; 0 = corpo inteiro).

## Algoritmo (`MCSolver::solve`)

1. **Parâmetros**: para cada segmento de F-Curve envolvido, 1 parâmetro (valor da key, se há key no frame) ou 4 (x e y dos dois handles internos do segmento).
2. **Jacobiano** por alvo, `3 × n_params`, montado por regra da cadeia:
   - `∂p/∂c` (posição ↔ valor do canal), analítico por tipo de canal:
     - `rotation_euler[i]` (ponto TAIL): `gimbal_axisᵢ × (p − head)` com eixos de gimbal por frame em cache;
     - `location[i]` (ponto HEAD, só o próprio bone): coluna `i` da matriz local.
   - `∂c/∂param` (canal ↔ handle): **diferença finita central** com `dT = 1e-6` re-avaliando a F-Curve (`dc_dp`). *Nota*: com x fixo isso é exatamente o coeficiente de Bernstein — no port calculamos analiticamente.
3. **QP**: minimizar `w₁·Σ‖J·x − Δs‖² + w_d·‖x‖²` (w₁ = 100, w_d = 1) ⇒ `Q = 2(Σ JᵀJ·w₁ + I·w_d)`, `c = −2w₁ JᵀΔs`. Modo interativo limita `‖Δs‖ ≤ 0.01` por passo (estabilidade).
4. **Pins** como restrições `J_c·x = ΔP` resolvidas por `my_quadprog` (Newton com penalidade/barreira + LLT, regularização 1e-7).
5. Aplica `x` nos `bezt` (handles viram `HD_FREE`), `RNA_property_update`, tag de depsgraph.
6. Gerência de segmentos: conjuntos ordenados (`set_union/difference/intersection`) para separar segmentos primários, ignorados (pins em pais) e rígidos (pins só com rotação).
7. `FrameData` por (objeto, bone, frame): matrizes de pose/objeto, head/tail, gimbal, matriz local — obtidos re-avaliando o depsgraph (`DEG_update`).

## Mapeamento para o nosso addon

| Parte | Reproduzível em Python? | Plano |
|---|---|---|
| QP denso pequeno (dezenas de parâmetros) | **sim** — `numpy.linalg.solve`/`lstsq`, KKT para pins | `core/solve.py` |
| `∂c/∂param` | sim, **analítico** (Bernstein) | `core/bezier.py` |
| Jacobiano Euler / location | sim | `core/solve.py` + `anim/spaces.py` |
| Jacobiano quaternion | **não existe no fork**; derivável (rotação infinitesimal ⇒ `∂q`, renormalização) | novo, Escopo 4 — Rigify usa quaternions |
| `FrameData` por frame (depsgraph) | sim, mas custo = frame stepping do Rigify | cache prefetch, igual a `P(f)` |
| Constraints do Blender (IK, Copy*, Armature) | fork não suporta | nós: só editar **controles**; FK sculpt opera em cadeias FK sem constraints entre si (Rigify FK é limpo). IK continua por translação do controle IK (Iteração 1) |
| Gizmo nativo C | não necessário | Gizmo Python (`test_select`) ou modal |
| Extensão nativa (C/C++/Eigen) | só se profiling provar gargalo | não planejado |

## Limitações registradas

Somente location e Euler; só interpolação Bézier; exige keys alinhadas (pose global); sem transform de objeto; sem twist ao longo do eixo Y do bone; código "hackeado" para comportamentos de gizmo.

## Por que não na Iteração 1

Para controles de translação, o problema é linear e exato (ver [modelo](../design/motion-sculpt-model.md#2-arc-drag-de-sampled-point-controles-de-translação)): mesma capacidade de "arrastar in-between ⇒ ajusta tangentes", sem otimizador nem Jacobiano. O valor real do tangent-space está em **FK**, que depende de suporte a quaternion — Escopo 4.

# Modelo do Animation Sculptor

> O que é editado, em que espaço e com que matemática. Toda operação aqui é determinística e tem teste unitário em `tests/unit/`.

## Conceitos

| Conceito | Definição |
|---|---|
| **Controle** | Pose bone que o animador keya (no Rigify: bones sem prefixo `ORG-`/`MCH-`/`DEF-`). Tem *capacidades*: `TRANSLATION` (tem canais `location` não travados), `ROTATION` (canais de rotação). |
| **Ponto de referência** | Onde a trail é medida: `head` para controles de translação; `tail` para bones FK (a ponta da mão, não a junta). Configurável. |
| **Trail** | Sequência de pontos em espaço de mundo do ponto de referência de um controle, um por frame amostrado. Fornecida pelo engine do LMP; durante um gesto, prevista analiticamente. |
| **Key point** | Ponto da trail num frame onde o controle tem key em algum canal relevante. Desenhado diferente dos amostrados. |
| **Sampled point** | Ponto da trail num frame sem key (in-between). |
| **Segmento** | Intervalo entre dois key points consecutivos de um controle. |
| **Pose key** | Frame onde o *escopo* (personagem inteiro ou bones selecionados) tem keys. Unidade das operações de timing. |
| **Escopo de timing** | `CHARACTER` (todas as F-Curves do slot do rig) ou `SELECTED` (só bones selecionados). Padrão: `CHARACTER` — mexer no tempo de uma pose mexe na pose inteira. |
| **Espaço-base `P(f)`** | Mapa afim 4×4 de `location` para a posição de mundo do head no frame `f`: `head_world = P(f) · location`, com rotação/escala do bone fixas. Obtido **perguntando ao Blender** (`Object.convert_space` LOCAL → POSE com `location` 0 e três eixos unitários; o head é afim em `location`, então 4 conversões dão `P` exato) e cacheado por frame. **Não** usar `M_arm · M_pose · M_basis⁻¹` (Motiontrail3D): só vale com `Bone.use_local_location = True`; controles IK do Rigify (`hand_ik`, `foot_ik`) têm `False` (o `torso` tem `True`), e com a fórmula antiga o grab andou na direção errada (achado do spike, 2026-10-03; teste `test_location_space_maps_location_to_head`). |

## Representação de um canal (`core/fcurve_model`)

Arrays numpy por canal: `x[k], y[k]` (keys), `hl[k,2], hr[k,2]` (handles), `hl_type[k], hr_type[k]`, `interp[k]`. Ida e volta com a F-Curve via `foreach_get/foreach_set`. Avaliação Bézier idêntica à do Blender, bit a bit (`core/bezier`), incluindo a correção de handles: no 5.2 cada handle é escalado **independentemente**, só quando aquele handle sozinho ultrapassa o key vizinho no tempo.

Fato que sustenta quase tudo abaixo: **num segmento Bézier, com as coordenadas de tempo (x) dos handles fixas, o parâmetro `t(f)` de cada frame é fixo, e o valor `v(f)` é linear nos valores (y) de keys e handles**:

```
v(f) = (1−t)³·y₀ + 3(1−t)²t·yₕ₁ + 3(1−t)t²·yₕ₂ + t³·y₁      (t = t(f), fixo se os x não mudam)
```

A linearidade em `y` vale também com a correção de handles do Blender (`BKE_fcurve_correct_bezpart`): o `y` do handle corrigido é `y_key − fac·(y_key − y_handle)`, com `fac` dependendo só dos `x`.

Logo editar valores sem mexer no tempo é um problema **linear e exato** — sem Jacobianos aproximados, sem iteração.

## Operações da Iteração 1

### 1. Grab de key point (controles de translação)

Entrada: key point no frame `f`, delta de mundo `Δw` (do mouse, no plano da vista que passa pelo ponto).

1. `Δl = R(f)⁻¹ · Δw`, com `R(f)` = parte 3×3 de `P(f)` (`anim/spaces.location_space`, que respeita `use_local_location`, herança e pose do pai; inclui escala do pai).
2. Eixos travados (`lock_location`) e canais sem F-Curve-editável: componente zerado (o ponto se move só nos eixos livres; a trail prevista mostra isso).
3. Em cada canal `location[i]`: key em `f` recebe `y += Δlᵢ` e os dois handles `y += Δlᵢ` (translação rígida — preserva a forma local, como no Motion Trail). Se o canal não tem key em `f`, insere-se uma com o valor avaliado (handles `AUTO_CLAMPED` recalculados) antes de aplicar.
4. **Soft grab** (falloff): os outros key points do mesmo controle a até `r` frames recebem `w(|fₖ−f|/r)·Δw`, cada um convertido pelo seu próprio `R(fₖ)⁻¹`. `r` ajustável com a roda do mouse durante o gesto; `r = 0` ⇒ só o ponto. Curvas de `core/falloff`.

### 2. Arc drag de sampled point (controles de translação)

Entrada: sampled point no frame `f` entre keys `k₀ < f < k₁` (por canal), delta de mundo `Δw`.

1. `Δv = R(f)⁻¹ · Δw` (desejado por canal).
2. Por canal: `a = 3(1−t)²t`, `b = 3(1−t)t²`. Solução de norma mínima: `Δyₕ₁ = Δvᵢ·a/(a²+b²)`, `Δyₕ₂ = Δvᵢ·b/(a²+b²)`. Keys e timing **não mudam**; só os valores dos handles internos do segmento.
3. Tipos de handle: o lado editado vira `ALIGNED` (se era `AUTO*`) e o handle oposto do mesmo key é girado para manter colinearidade preservando seu comprimento — continuidade de tangente no key, como no Motion Trail/Motiontrail3D. Isso altera levemente o segmento vizinho. Modificador "quebrar tangente" ⇒ `FREE`, vizinho intocado.
4. Segmentos `LINEAR`/`CONSTANT`: operação recusada com aviso no overlay (não convertemos interpolação silenciosamente).

É a versão linear, exata, do *Tangent-Space Optimization* restrita a canais de `location` — cobre o caso mais comum (arcos de mão/pé IK, torso) sem otimizador.

### 3. Retime de pose key (qualquer controle, escopo de timing)

Arrastar um key point com o modificador de tempo move a **pose key** `f → f'`:

- `f'` inteiro por padrão (sub-frame com modificador), limitado a `(f_prev+1, f_next−1)` entre pose keys vizinhas.
- Em toda F-Curve do escopo: keys em `|x−f| < ε` recebem `x += Δ`, handles `x += Δ`. Keys fora de `f` não se movem (overlap/offset existentes são preservados).
- Mapeamento tela→tempo: projeção do movimento do mouse na direção da trail no ponto (mover "para frente na trail" = mais tarde), algoritmo do modo *timing* do Motion Trail.
- Funciona para FK, IK, qualquer canal — é só tempo.

### 4. Spacing de segmento (escopo de timing)

Entre duas pose keys `k₀, k₁` (duração `D`): definir os comprimentos temporais dos handles `λ_out·D` (saindo de `k₀`) e `λ_in·D` (chegando em `k₁`), com `λ_out + λ_in ≤ 1` (evita a correção automática de handles sobrepostos do Blender).

- Mudando **só o x** dos handles e aplicando os **mesmos x em todos os canais** do segmento, os valores de controle (y) não mudam ⇒ o **caminho espacial é preservado exatamente**; só o spacing (`t(f)`) muda. Ease-out forte = `λ_out` grande.
- Gesto: arrasto horizontal sobre o segmento = *favor* (transfere entre `λ_out` e `λ_in`); vertical = *ease* (soma). Feedback: pontos amostrados se redistribuem ao vivo + cor de velocidade do LMP.
- Efeito colateral a decidir no protótipo: mudar só x altera a inclinação da tangente no key; com `ALIGNED` o handle oposto teria que girar (mudando o segmento vizinho). Duas políticas: `PRESERVE_PATH` (handles `FREE` só quando a colinearidade quebra; direção espacial contínua, velocidade pode ter salto) e `PRESERVE_SMOOTHNESS` (mantém `ALIGNED`, ajusta o vizinho). Em poses com ease (inclinação ≈ 0) as duas coincidem. Decisão registrada em ADR após teste com o usuário — ver [agenda](../agenda.md).

### Reuso nativo na Iteração 1

Sem reimplementar: **Breakdowner / Push / Relax / Blend to Neighbor** de pose (`pose.breakdown`, `pose.push`, `pose.relax`, `pose.blend_to_neighbor`) expostos no painel para criar breakdowns favorecendo poses. São operadores nativos de 3D View, seguros de chamar.

## Operações futuras (Escopos 2–4)

| Operação | Modelo | Fonte |
|---|---|---|
| Smooth espacial (relax) | Laplaciano sobre key points em mundo (pins excluídos), volta por `R(f)⁻¹`. Modo *straighten* (puxa para a reta entre vizinhos). | novo; UX do Motion Sculpt (JB FX) como referência |
| Smooth temporal | Gaussian / Butterworth sobre amostras, reamostrado em keys. Algoritmos dos operadores nativos `graph.gaussian_smooth`/`graph.butterworth_smooth` (portados para `core/`, porque exigem contexto de Graph Editor). | Blender (GPL-2+) |
| Make Arc | Círculo pelos extremos e ponto médio selecionado; projeta key points intermediários; parâmetro de altura. | novo |
| Pins | Pontos de mundo fixos ⇒ restrições lineares no `core/solve` (mínimos quadrados com restrições, KKT). | `MCSolver` do Interactive Motion Path |
| Tangent handles no viewport | Handles Bézier desenhados como tangentes 3D: `R(f)·(hᵧ − y)` por canal; arrastar ⇒ edita y do handle. | Motion Trail (handles), Motiontrail3D |
| Ranges | Operações limitadas a um intervalo de frames selecionado na trail. | novo |
| **FK chain sculpt** | Alvo = ponta da cadeia; parâmetros = keys/handles de rotação dos bones da cadeia; Jacobiano `∂p/∂θ` (Euler: `eixo × (p − junta)`; quaternion: analítico com renormalização) × coeficientes de Bernstein (`∂v/∂y`, exatos — o fork usa diferenças finitas). Mínimos quadrados amortecidos; reavaliação pelo depsgraph ao soltar. | Tangent-Space Optimization (Ciccone et al. 2019), port do fork para numpy |
| **Loop** (Escopos 2–3) | Action marcada como cíclica. *Fechar loop*: para cada F-Curve do escopo, key em `f_end` com o valor da key em `f_start` (inserida se faltar) e tangentes casadas: handle esquerdo de `f_end` = handle esquerdo de `f_start` deslocado de `f_end − f_start` (e o direito de `f_start` espelha o direito de `f_end`), assim a curva é C¹ na emenda. Decisão: a última pose é **explícita** (key duplicada), porque o glTF não tem modificador Cycles — o Godot recebe as amostras e só precisa do modo loop. Edições em `f_start` ou `f_end` se propagam para a outra ponta. | novo; ideia de edição cíclica de *Authoring Motion Cycles* (Ciccone et al. 2017) |
| Retime com stretch | Mover pose key escalando proporcionalmente keys até as vizinhas (time beads). | Motion Trail |

## Invariantes (viram testes)

1. Grab com `Δw = 0` não altera nenhum valor.
2. Arc drag nunca altera `x` de keys/handles nem keys fora do segmento editado (exceto handle oposto em modo alinhado).
3. Spacing preserva o conjunto de pontos `{(Bx(t), By(t), Bz(t))}` do segmento (amostrado em `t`) quando os canais compartilham keys.
4. Retime preserva a ordem das keys em toda F-Curve e não cria keys.
5. Toda operação é idempotente em relação a cancel: snapshot → op → restore = F-Curves bit a bit iguais.
6. A trail prevista durante o gesto coincide (tolerância 1e-4 m) com a trail recalculada pelo depsgraph depois de soltar, para controles de translação.

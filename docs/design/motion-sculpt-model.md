# Modelo do Animation Sculptor

> O que é editado, em que espaço e com que matemática. Toda operação aqui é determinística e tem teste unitário em `tests/unit/`.

## Conceitos

| Conceito | Definição |
|---|---|
| **Controle** | Pose bone que o animador keya (no Rigify: bones sem prefixo `ORG-`/`MCH-`/`DEF-`). Tem *capacidades*: `TRANSLATION` (tem canais `location` não travados), `ROTATION` (canais de rotação). |
| **Ponto de referência** | Onde a trail é medida: `head` para controles de translação; `tail` para bones FK (a ponta da mão, não a junta). **Implementado** (patch P9 do LMP): vem do adapter do rig por alvo (`ControlInfo.reference`); fora dos controles vale a configuração global "Bone Point" do LMP. |
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
4. **Soft grab** (falloff): os outros key points do mesmo controle a até `r` frames recebem `w(|fₖ−f|/r)·Δw`, cada um convertido pelo seu próprio `R(fₖ)⁻¹` e aplicado rígido (key + handles) como no passo 3. **Só keys de `location` que já existem se movem; keys vizinhas nunca são criadas** (diferente do ponto agarrado, que ganha key se faltar). `r` ajustável com a roda do mouse ou `[`/`]` durante o gesto; `r = 0` ⇒ só o ponto (grab simples). Curvas de `core/falloff.weight` (`SMOOTH` padrão, `LINEAR`, `SHARP`, `SPHERE`, `CONSTANT`): peso 1 a distância 0, 0 no raio.

### 2. Arc drag de sampled point (controles de translação)

Entrada: sampled point no frame `f` entre keys `k₀ < f < k₁` (por canal), delta de mundo `Δw`.

1. `Δv = R(f)⁻¹ · Δw` (desejado por canal).
2. Por canal: `a = 3(1−t)²t`, `b = 3(1−t)t²`. Solução de norma mínima: `Δyₕ₁ = Δvᵢ·a/(a²+b²)`, `Δyₕ₂ = Δvᵢ·b/(a²+b²)`. Keys e timing **não mudam**; só os valores dos handles internos do segmento.
3. Tipos de handle (como implementado em `core/sculpt_ops.arc_drag`): se o handle editado é `AUTO`/`AUTO_CLAMPED`/`ALIGNED`, **os dois lados do key passam a `ALIGNED`** e o handle oposto é girado para manter a colinearidade **mantendo o seu `x`** — não o comprimento. Preservar `x` honra a invariante 2 (o timing nunca muda); o comprimento do handle oposto pode mudar. Continuidade de tangente no key, como no Motion Trail/Motiontrail3D; isso altera levemente o segmento vizinho. Handles `FREE`/`VECTOR`, ou o modificador "quebrar tangente" (`B`) ⇒ os dois lados `FREE` e os segmentos vizinhos ficam **bit a bit idênticos**.
4. Recusas: segmentos `LINEAR`/`CONSTANT` ("segmento LINEAR"/"CONSTANT"; não convertemos interpolação silenciosamente), keys e frames fora do intervalo de keys do canal. O solve é exato (norma mínima, coeficientes Bernstein × fator da correção de handles do Blender), inclusive com handles sobrepostos.

É a versão linear, exata, do *Tangent-Space Optimization* restrita a canais de `location` — cobre o caso mais comum (arcos de mão/pé IK, torso) sem otimizador.

### 3. Retime de pose key (qualquer controle, escopo de timing)

**Implementado** (`core/timing_ops.retime`, `interaction/timing_edit.RetimeEdit`). Arrastar um key point com Ctrl move a **pose key** `f → f'`:

- `f'` inteiro por padrão (sub-frame com Shift), limitado a ≥ 1 frame das pose keys vizinhas: `(f_prev+1, f_next−1)`. Se o intervalo é estreito demais para caber, a key não se move.
- Pose keys = frames onde algum canal do escopo tem key (`pose_keys`, uniões com tolerância 1e-3).
- Em toda F-Curve do escopo: a key em `|x−f| < ε` recebe `x += Δ` e seus handles `x += Δ` (os valores `y` não mudam). Keys fora de `f` não se movem (overlap/offset existentes são preservados). **Nunca cria nem remove keys; a ordem das keys se mantém** (invariante 4).
- Mapeamento tela→tempo (`retime_frames_from_screen`): projeção do movimento do mouse na direção da trail em tela no ponto (mover "para frente na trail" = mais tarde) dividida pelos pixels por frame da trail ali (modo *timing* do Motion Trail); sem direção útil (trail parada), o movimento horizontal vale 20 px por frame. Frames inteiros, exceto com Shift.
- Funciona para FK, IK, qualquer canal — é só tempo. Escopo de timing `CHARACTER` (todas as F-Curves do slot do rig sem modificador ativo; padrão) ou `SELECTED` (bones selecionados + o arrastado).
- Verificado: no rig Rigify gerado, depois de mover a pose de 12 para 15 a pose avaliada no frame 15 é igual à pose antiga do frame 12 em mão, pé e torso, e só as keys foram deslocadas.

### 4. Spacing de segmento (escopo de timing)

**Implementado** (`core/timing_ops.set_spacing`, `interaction/timing_edit.SpacingEdit`). Entre duas keys `k₀, k₁` do controle arrastado (duração `D`): definir os comprimentos temporais dos handles `λ_out·D` (saindo de `k₀`) e `λ_in·D` (chegando em `k₁`), com `MIN_LAMBDA = 0,02` e `λ_out + λ_in ≤ 0,98` (`clamp_lambdas`; o piso é mantido depois da escala). Com a soma < 1 a correção de handles sobrepostos do Blender nunca entra em ação, então o resultado é exato.

- Mudando **só o x** dos handles e aplicando os **mesmos x em todos os canais** do segmento, os valores de controle (y) não mudam ⇒ o **caminho espacial é preservado exatamente**; só o spacing (`t(f)`) muda. Ease-out forte = `λ_out` grande. O spacing se aplica a todo canal do escopo que tem exatamente o segmento `[k₀, k₁]` do controle arrastado; recusa segmento `LINEAR`/`CONSTANT` e arrastos fora do intervalo de keys.
- **Achado (2026-10-04)**: o caminho **em mundo** só é preservado exatamente quando os canais **compartilham o `x` dos handles** do segmento. Os handles `AUTO`/`AUTO_CLAMPED` do Blender têm `x` que depende apenas dos frames das keys (o cálculo de handles da F-Curve usa distâncias em `x`), então canais keyados nos mesmos frames os compartilham; e depois de uma edição de spacing todos os canais do segmento têm o mesmo `λ`, qualquer que fosse o ponto de partida. Verificado no rig Rigify gerado (`test_spacing_keeps_the_world_path`, amostragem densa em sub-frames: < 0,2 mm, três variantes de gesto). Se um canal tivesse `x` diferente, o caminho em mundo mudaria um pouco (o preview, que reamostra o caminho antigo, seria só aproximado).
- Um ease **simétrico** (`λ_out = λ_in`) deixa o frame do meio no lugar, por simetria; o efeito aparece nos demais frames do segmento.
- Gesto (`spacing_from_gesture`): arrasto horizontal sobre o segmento = *favor* (transfere entre `λ_out` e `λ_in`; positivo = para a segunda key, saída mais longa); vertical = *ease* (soma aos dois); 250 px por 1,0. Feedback: pontos amostrados da trail prevista se redistribuem ao vivo, coloridos por velocidade (azul → vermelho), obtidos reamostrando o caminho original nos frames remapeados (`remap_frames`: para cada frame do segmento, o frame antigo com o mesmo parâmetro `t`).
- Efeito colateral: mudar só x altera a inclinação da tangente no key; com `ALIGNED` o handle oposto teria que girar (mudando o segmento vizinho). Duas políticas, ambas implementadas e testadas:
  - `PRESERVE_PATH` (**padrão**): as duas keys do segmento viram `FREE` nos dois lados; nenhum outro valor muda; a tangente pode quebrar na key (direção espacial contínua, velocidade pode ter salto).
  - `PRESERVE_SMOOTHNESS`: as duas keys ficam `ALIGNED`, o `y` do handle oposto é realinhado mantendo o seu `x`; o segmento vizinho muda um pouco.
  Em poses com ease (inclinação ≈ 0) as duas coincidem. **Decisão em aberto** — vira ADR depois do teste do mantenedor (M1); ver [agenda](../agenda.md).

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
2. Arc drag nunca altera `x` de keys/handles nem keys fora do segmento editado (exceto o `y` do handle oposto, girado em modo alinhado; seu `x` também não muda).
3. Spacing preserva o conjunto de pontos `{(Bx(t), By(t), Bz(t))}` do segmento (amostrado em `t`) quando os canais compartilham o `x` dos handles do segmento (o caso de canais keyados nos mesmos frames com handles automáticos; ver o achado na operação 4). Teste: `test_spacing_keeps_the_world_path`.
4. Retime preserva a ordem das keys em toda F-Curve e não cria nem remove keys (`test_timing_ops.py`, `test_timing.py`).
5. Toda operação é idempotente em relação a cancel: snapshot → op → restore = F-Curves bit a bit iguais.
6. A trail prevista durante o gesto coincide (tolerância 1e-4 m) com a trail recalculada pelo depsgraph depois de soltar, para controles de translação.

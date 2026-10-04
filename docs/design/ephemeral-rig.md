# Rig efêmero e UI de tempo

> Plano pós-Escopo 1 (depois do PR #11). Decisão: [ADR 0011](../decisions/0011-ephemeral-rig-dense-keys.md). Origem: palestra *Motion Sculpting: A New Animation Paradigm* (Nacho de Andrés, BCON26 — [video.blender.org](https://video.blender.org/w/66d78fe0-0211-4067-b133-88c3f77eb7de), [YouTube](https://www.youtube.com/watch?v=M2J_fQNLDfg)); ver [reference/open-source-projects.md](../reference/open-source-projects.md). O código dele não foi publicado (busca em 2026-10-04): só a ideia e a UX servem de referência.

Capturas de referência (17:26, 23:41, 29:15) ficam **só no repositório local**, em `docs/reference/local/motion-sculpting-bcon26/` (pasta no `.gitignore`, fora do remoto, como `tests/assets/local/`).

## A ideia

Na palestra não há control rig: o esqueleto é um Mixamo puro (bones `mixamorig:*`), e o "rig denso de FK" é o próprio esqueleto. Quando o animador arrasta um ponto, um IK/cadeia **temporário** é resolvido sobre as rotações FK dentro de uma **janela de tempo** com falloff, e o resultado é gravado como **keys em todo frame** da janela. Ao soltar, o "rig" deixa de existir. Pontos de UI observados:

| Observado (capturas 17:26, 23:41, 29:15) | Leitura |
|---|---|
| Mini-timeline dentro do viewport, frame atual no meio, degradê **vermelho** até um marcador no passado e **verde** até um no futuro | Janela de tempo do gesto com falloff assimétrico, bordas arrastáveis |
| Trail da cabeça vermelha antes do frame atual e verde depois; onion skin quente/frio | Uma convenção de cor só: passado vermelho, futuro verde |
| Toolbar flutuante embaixo do viewport: modo `Sculpt`, seletor `Full`, ícones, `Smooth` | Configurações da ferramenta à mão; `Full` parece ser o escopo do corpo que o solve pode mexer (inferência) |
| Ferramenta de spline: curva roxa com pontos de controle em 3D; toolbar vira `Strength 100% · Aim 0% · X`; faixa roxa com pontas na timeline | Curva-guia aplicada num trecho de tempo; *Aim* = quanto a orientação segue a tangente (inferência) |

## Encaixe no projeto

O Animation Sculptor já tem o princípio ("o único estado persistente é a Action") e quase toda a infraestrutura: `P(f)` com prefetch (`anim/spaces`), falloff (`core/falloff`), snapshot bit a bit, `RigAdapter.chain()`, trails de FK pela ponta do bone (patch P9). O que falta é a matemática de rotação.

**O rig efêmero é matemática, não dados.** Não criamos bones, constraints nem Actions temporárias no `.blend` (a alternativa "gerar bones + IK constraint e fazer `nla.bake` ao soltar" foi descartada no ADR 0011: lenta, com estado, ruim para undo/cancel). O solve vive em `core/` (numpy, sem `bpy`, [ADR 0008](../decisions/0008-pure-python-core.md)); o Blender só fornece as matrizes de repouso e do pai por frame e recebe as F-Curves. Isso também mantém o não objetivo "rig próprio": nada é um rig persistente.

**Com Rigify, sem jogar nada fora.** A camada FK densa são os controles FK do Rigify (`upper_arm_fk → forearm_fk → hand_fk`, pernas, coluna, pescoço/cabeça). Bake para `DEF-*` e glTF não mudam. Membro em modo IK (`ik_fk_state = 0`) continua com o sculpt de translação atual (esparso); sobre um membro IK o gesto efêmero é recusado com motivo ("membro em IK: arraste a mão IK ou mude o membro para FK"). Em esqueleto sem control rig (Mixamo, adapter genérico) a cadeia vem da hierarquia, sem nomes — o mesmo mecanismo serve aos dois casos e tira o Rigify do caminho crítico sem removê-lo.

**Keys densas (decidido).** O gesto efêmero grava uma key por frame inteiro em toda a janela, nos canais de rotação dos bones da cadeia. Os gestos atuais de translação (grab, arc, retime, spacing) continuam esparsos e com suas invariantes. Consequências e mitigação na seção "Keys densas".

## Comportamento

1. Ferramenta Animation Sculptor ativa; o animador arrasta (LMB) um ponto da trail de um **controle só de rotação** (hoje recusado: "controle só de rotação…") ou, na fase 4, a ponta do bone direto no viewport.
2. O adapter devolve a **cadeia efêmera** para o escopo escolhido: `Ponta` (só o bone; gira para apontar), `Membro` (cadeia até a raiz do membro: 2 bones + ponta), `Corpo` (fase 4: coluna/raiz com pins nos pés).
3. Janela de tempo `[f₀ − r_passado, f₀ + r_futuro]`, pesos `w(f)` por `core/falloff` com distância com sinal (raios assimétricos).
4. Para cada frame inteiro `f` da janela: alvo `t(f) = ponta(f) + w(f)·Δw` (Δw = delta do mouse no plano da vista em `f₀`, como no grab); solve da cadeia no espaço do pai da raiz da cadeia em `f`; novas rotações locais.
5. Preview ao vivo: trail prevista da ponta (FK em numpy) sobre a trail fantasma, como no grab; a janela aparece na régua de tempo.
6. Soltar: escreve as keys densas (1 passo de undo), `provider.resume` + refresh síncrono. Esc/RMB: snapshot bit a bit.

### Solve (determinístico)

- **2 bones (braço, perna)**: IK analítico fechado (lei dos cossenos). Plano do joelho/cotovelo = plano atual da cadeia em `f` (o pole é a pose existente), então o membro não "vira". Ponta fora de alcance ⇒ estica até o limite (sem escala). Sem iteração.
- **Ponta (1 bone)**: rotação mínima (`rotation_difference`) que leva a direção head→tail ao alvo.
- **Cadeias > 2 (coluna, pescoço, `Corpo`)**: mínimos quadrados amortecidos com número **fixo** de iterações, partindo da pose atual, Jacobiano analítico (`eixo × (p − junta)`), mesma entrada ⇒ mesma saída. Base de `core/solve.py`, que já estava planejado para pins.
- **Orientação da ponta**: opção "manter orientação" `Mundo` (padrão; a mão não gira com o braço, como no grab de um IK) ou `Local`.
- **Pins** (fase 4): pontos em mundo fixos por frame (ex.: pés no `Corpo`), resolvidos depois do movimento da raiz com o mesmo IK de 2 bones.
- **Rotação**: quaternions com continuidade de hemisfério frame a frame (`q·q_prev < 0 ⇒ −q`); Euler com compatibilidade com o frame anterior (equivalente a `Euler.make_compatible`); eixos travados (`lock_rotation`) projetados fora; `AXIS_ANGLE` recusado.

### Keys densas: regra de escrita

- Em cada canal de rotação dos bones da cadeia: key em todo frame inteiro de `[a, b]` (a janela), interpolação `BEZIER`, handles `AUTO_CLAMPED`; canais sem F-Curve são criados (`action_io.ensure_channel`).
- **Fora da janela nada muda**: para não alterar os segmentos que cruzam a borda, a janela escrita é estendida até a key existente mais próxima de cada lado (`k_esq`, `k_dir`) com os valores atuais (peso 0), e essas duas keys de borda têm o tipo de handle `AUTO*` congelado para `ALIGNED` com os handles atuais. Invariante: valores em frames inteiros fora de `[a, b]` iguais aos de antes (tolerância 1e-6), keys fora de `[k_esq, k_dir]` bit a bit iguais.
- Interação com os gestos esparsos numa região densa: arc drag e spacing perdem sentido (tudo é key); grab com raio continua útil; retime de uma key isolada vira deslocamento de um frame. Mitigações planejadas: **smooth temporal** (Escopo 3) e **simplificar** (reduzir a região densa a keys esparsas; `graph.decimate` nativo exige Graph Editor ⇒ chamar com `temp_override` ou portar o algoritmo — decidir na fase 3).

## UI

### Régua de tempo no viewport (HUD)

- Faixa horizontal desenhada pelo overlay (POST_PIXEL, `gpu` + `blf`) acima da borda inferior do viewport, centrada no frame atual: ticks e números de frame, marcador do frame atual, degradê **vermelho** de `f₀ − r_passado` até `f₀` e **verde** de `f₀` até `f₀ + r_futuro` com alfa = `w(f)`, pontas arrastáveis.
- Vale para o **soft grab** existente e para o gesto efêmero (mesma janela, mesmo falloff).
- Interação: o `test_select` do gizmo (`ASC_GT_trail_points`) testa primeiro a régua e depois os pontos da trail; LMB numa ponta inicia um modal curto `asc.time_window` que edita `r_passado`/`r_futuro`; Shift = edita os dois juntos; durante o gesto a roda e `[ ]` continuam mudando o raio (os dois lados, se ligados).
- Configurações (`Scene.asc_sculpt`): `radius_past`, `radius_future`, `radius_linked` (padrão ligado); o `soft_radius` atual vira o valor dos dois lados na migração (versão da extensão sobe; arquivos 0.3.0 abrem com os dois lados iguais ao raio salvo). `show_time_ruler` (padrão ligado).

### Paleta passado/futuro

- Convenção única: passado **vermelho**, futuro **verde**, frame atual branco. Aplicada às trails (`path_color_past/future` do LMP, que já existem — só mudar os padrões quando a nossa extensão liga as trails, sem patch), ao onion skin (`onion_color_before/after`) e à régua de tempo.
- Botão "Paleta Animation Sculptor" no painel Trails para reaplicar; o usuário pode trocar as cores no LMP normalmente.

### Barra da ferramenta

- **Fase 1 (nativo)**: `WorkSpaceTool.draw_settings` em `ASC_WT_sculpt` — a barra de configurações da ferramenta do Blender, no topo do viewport: escopo do gesto efêmero (`Ponta`/`Membro`/`Corpo`), orientação da ponta, raio passado/futuro (com cadeado), falloff. Zero widget próprio, acessível, mesma pilha de undo. Os mesmos campos seguem no painel "Gestos".
- **Depois (opcional)**: toolbar flutuante desenhada pelo HUD, como a da palestra, só se a barra nativa se mostrar insuficiente no uso real (custo: hit-test e desenho próprios).

### Spline de movimento

Curva-guia com pontos de controle aplicada a um trecho de tempo (faixa roxa na régua), com `Strength` e `Aim`. Entra no **Escopo 3** junto com make arc e tangent handles (mesma família: editar o caminho por uma curva). Fora deste plano.

## Onde no código

| Onde | O quê | Fase |
|---|---|---|
| `core/falloff.py` | `weight_signed(d, r_passado, r_futuro, forma)` (raios assimétricos) | 1 |
| `ui/props.py` | `radius_past`, `radius_future`, `radius_linked`, `show_time_ruler`, `ephemeral_scope`, `tip_orientation`; migração do `soft_radius` | 1 / 3 |
| `interaction/hud.py` (novo) | geometria da régua (frame ⇄ px), desenho e hit-test; sem estado próprio | 1 |
| `interaction/overlay.py` | chama o HUD; cores da paleta | 1 |
| `interaction/gizmo.py` | `test_select` testa a régua antes dos pontos | 1 |
| `interaction/sculpt_tool.py` | `draw_settings` da tool; modal `asc.time_window`; roteia controle só de rotação para o gesto efêmero em vez de recusar | 1 / 3 |
| `trails/provider.py` | aplica a paleta passado/futuro ao ligar as trails | 1 |
| `core/kinematics.py` (novo) | FK em numpy (repouso + TRS local ⇒ mundo, cadeias), conversões quaternion/Euler com continuidade, IK analítico de 2 bones, rotação mínima | 2 |
| `core/solve.py` (novo) | mínimos quadrados amortecidos com iterações fixas e pins | 2 / 4 |
| `core/ephemeral.py` (novo) | o gesto puro: cadeia + matrizes por frame + rotações atuais + pesos + Δ ⇒ rotações novas por frame | 2 |
| `core/dense.py` (novo) | escrita densa num `ChannelModel` com bordas preservadas (regra acima) | 2 |
| `rig/adapter.py` + `rigify.py` + `generic.py` | `ephemeral_chain(arm_ob, bone, scope) → (bones raiz→ponta, pins)`; Rigify: cadeias FK, recusa membro em IK; genérico: caminhada pela hierarquia até ramificação ou N bones | 3 |
| `anim/spaces.py` | `prefetch_chain(ob, bones, frames)`: matriz do pai da raiz da cadeia por frame + matrizes de repouso (generaliza o `prefetch` de `P(f)`) | 3 |
| `anim/action_io.py` | leitura/escrita dos canais de rotação (`rotation_quaternion` 4, `rotation_euler` 3) | 3 |
| `interaction/ephemeral_edit.py` (novo) | `ChainEdit` (mesma forma de `_GrabEdit`/`timing_edit`: `editable`, `apply(Δw)`, `preview`, `restore`) | 3 |

## Fases (um PR cada, a partir da `main` depois do merge do #11)

1. **UI de tempo** — régua de tempo no viewport com raio assimétrico (soft grab passa a usá-la), paleta passado/futuro, barra nativa da ferramenta. Independe do solve; melhora já o que existe. *Pronto quando:* soft grab com raios diferentes para passado e futuro, editáveis arrastando as pontas da régua, salvos no arquivo; trails vermelho/verde.
2. **`core/kinematics` + `core/ephemeral` + `core/dense`** (puro, só testes). *Pronto quando:* FK em numpy bate com o Blender no rig público (< 1e-5 m, teste de Blender); IK de 2 bones atinge o alvo exato dentro do alcance e preserva o plano; escrita densa respeita a invariante de borda; quaternions sem flip.
3. **Gesto efêmero `Membro`/`Ponta`** nos controles FK do Rigify e no adapter genérico, keys densas na janela, preview, undo/cancel, recusas. *Pronto quando:* swing de espada com braço FK esculpido no viewport (o critério que fechava o Escopo 4).
4. **`Corpo` + pins + arrastar o bone direto** (ponta do bone no frame atual como alvo, sem precisar mirar na trail) + orientação `Local`/`Mundo`.

## Testes (viram critérios)

- Unit: FK numpy ⇄ referência analítica; IK de 2 bones (alcance, fora de alcance, plano preservado, determinismo bit a bit em duas execuções); continuidade de quaternion; `weight_signed` (assimetria, 0 nas bordas, 1 em `f₀`); escrita densa (fora da janela inalterado, bordas `ALIGNED`, Δ = 0 ⇒ valores iguais aos atuais em todo frame).
- Blender: FK numpy = depsgraph no rig público; gesto efêmero em `forearm_fk`/`hand_fk` ⇒ ponta em `f₀` sob o cursor (< 1 mm), trail recalculada = preview (1e-4 m), keys densas só na janela, um passo de undo, Esc bit a bit; membro em IK recusado; adapter genérico num esqueleto sem Rigify.
- UI (`dev.py test ui`): arrastar ponta da régua muda o raio; soft grab assimétrico move só as keys do lado certo; gesto efêmero na Vale.

## Riscos e perguntas abertas

- **Desempenho do preview**: N frames × solve por mouse move. IK de 2 bones vetorizado em numpy deve caber em < 16 ms para 200 frames; medir na fase 2. `Corpo` (DLS) pode exigir preview só do frame `f₀` + amostras.
- **Hierarquia do Rigify**: o pai de `upper_arm_fk` passa por `MCH-` com hinge; o espaço do pai vem do prefetch (frame stepping), não da hierarquia — por isso `prefetch_chain` e não FK desde a raiz.
- **Região densa × ferramentas esparsas**: definir na fase 3 se "Simplificar" entra junto (provável) ou no Escopo 3.
- **Ordem no roadmap**: hoje o gesto efêmero substitui o Tangent-Space do Escopo 4. Puxá-lo para antes do Escopo 2 é decisão do mantenedor (a fase 1 pode entrar em qualquer momento).

# Reforma de UX: agarrar o corpo, ferramentas na lateral, régua, onion skin

> Plano aprovado em conversa com o mantenedor em 2026-10-04 (decisões abaixo). **Implementado na 0.7.0** em um único PR (`feat/ux-reform`, pedido do mantenedor: entregas maiores); diferenças em relação ao plano em "Notas da implementação". Decisão de arquitetura: [ADR 0013](../decisions/0013-body-and-trail-interaction.md). Referência: palestra *Motion Sculpting* (BCON26), capturas 17:26, 23:41 e 29:15 em `docs/reference/local/motion-sculpting-bcon26/` (só local).

## Por que

A 0.6.0 tem a matemática do rig efêmero inteira, mas a experiência ficou diferente da palestra:
- tudo partia de pontos da trail, com bone selecionado;
- as configurações estavam no painel N e numa barra nativa escondida;
- a régua era pequena;
- o onion skin vinha desligado.

Na palestra, o animador agarra **o corpo**, as ferramentas ficam à mão no viewport e o control rig fica fora de vista.

## Decisões do mantenedor (2026-10-04)

| # | Decisão |
|---|---|
| 1 | Dois modos: **Corpo** (agarrar a malha: pose e arco) e **Trail** (agarrar a trajetória: timing e spacing). Troca no **painel N**; talvez unidos no futuro. |
| 2 | Ferramentas na **barra lateral esquerda** do viewport, com ícone: **Ponta**, **Membro**, **Corpo**, **Smooth**. Interface limpa, ferramentas ao alcance do viewport. O painel N fica para depuração de usabilidade e parâmetros muito específicos. |
| 3 | Régua de tempo **mais larga**, em **frames** (não segundos), no mesmo lugar (embaixo, centro). |
| 4 | Onion skin com **toggle** e dois modos: o **atual** (fantasmas no lugar) e o **expandido** (os fantasmas dos frames da janela da régua espalhados para os lados, como na captura de 23:41). |
| 5 | Reforma de UX **agora**, antes do Escopo 2. |
| 6 | Agarrar o corpo com o **Rigify escondido**: toggle "Ligar Rigify" no painel N. A animação continua nos controles do Rigify (para voltar a eles em ajustes finos). |
| 7 | Spacing: `PRESERVE_PATH` como padrão ([ADR 0012](../decisions/0012-spacing-policy-preserve-path.md)). |
| 8 | O mantenedor testa animando com a ferramenta antes de aprovar cada PR (substitui o M1 formal). Reinstalar o zip a cada vez fica para o futuro. |
| 9 | Keys densas não são problema (ferramenta "estilo ZBrush"); **Simplificar** fica para o futuro. |
| 10 | `Corpo` arrastando pescoço/cabeça no Rigify: **inclina pelo chest e depois aponta a cabeça** (duas etapas automáticas). |

## Modos e gestos

| Modo (painel N) | O que o mouse procura | LMB arrastar | Ctrl+LMB arrastar |
|---|---|---|---|
| **Corpo** | a **malha** do personagem (e, sem malha, a ponta dos bones) | esculpe a **pose no frame atual** com a ferramenta ativa: Ponta/Membro/Corpo (rig efêmero, ou grab/arco num membro IK); Smooth suaviza | — (reservado) |
| **Trail** | pontos da **trail** (como até a 0.6.0) | grab / arco / gesto FK, como hoje, com o escopo da ferramenta ativa | **retime** (key) e **spacing** (in-between), como hoje |

Nos dois modos: a janela de tempo é a da régua (raios passado/futuro, falloff), um gesto é um passo de undo, Esc/RMB cancela bit a bit e um clique sem arrasto não escreve nada.

## Ferramentas na barra lateral

Cada uma é um `WorkSpaceTool` em Pose Mode, com ícone, no mesmo grupo da barra (como Move/Rotate). Todas usam o mesmo grupo de gizmos e o mesmo operador de gesto; a ferramenta ativa define o **escopo**:

| Ferramenta | Escopo | No modo Corpo | No modo Trail |
|---|---|---|---|
| **Ponta** | só a parte agarrada | gira o bone da parte para apontar ao mouse (IK: grab/arco do controle IK) | gesto FK de ponta na trail de um FK; grab/arco nos de translação |
| **Membro** | o membro até a parte agarrada (braço, perna) | rig efêmero `LIMB` (FK/esqueleto puro) ou grab/arco do controle IK | como na 0.5.0 |
| **Corpo** | a coluna até a parte, pés presos | rig efêmero `BODY` com pins | como na 0.6.0 (ponta do bone) |
| **Smooth** | a parte agarrada (membro) | suaviza no tempo os canais da parte dentro da janela (abaixo) | idem, a partir da trail |

- `Shift+Alt+K` ativa a última ferramenta do Animation Sculptor usada (hoje ativa a única).
- `Scene.asc_sculpt.ephemeral_scope` deixa de aparecer na UI: vira o escopo da ferramenta ativa.
- O header da área continua mostrando a operação e os atalhos.
- A barra nativa de configurações da ferramenta (`draw_settings`) continua existindo, mas não é o caminho principal.

## Agarrar o corpo (modo Corpo)

1. **Picking**: no `test_select` do gizmo, um raycast na malha avaliada sob o cursor (`Scene.ray_cast` com o depsgraph; ou `BVHTree` em cache por frame/pose se o raycast for caro — medir) devolve objeto, face e ponto.
2. **Bone sob o cursor**:
   - malha deformada pela armature ativa (modificador Armature) e topologia avaliada igual à original: o bone deformador com **maior peso** nos vértices da face atingida;
   - topologia diferente (subdivisão etc.): o bone deformador **mais próximo** do ponto (distância ao segmento head–tail).
3. **Realce**: a região da malha daquela parte (triângulos com peso dominante desse bone, índices em cache por bone, posições da malha avaliada a cada redesenho) desenhada em azul translúcido, como na palestra; header `Animation Sculptor · <parte> · <controle>`.
4. **Bone deformador → controle**: `RigAdapter.control_for_deform(arm_ob, deform_bone, escopo)` → (controle, tipo de gesto):
   - **Genérico** (Mixamo, esqueleto sem control rig): o próprio bone. O rig efêmero atua direto nele.
   - **Rigify**, braço/perna em **FK**: o controle FK do segmento (`DEF-forearm.L(.001)` → `forearm_fk.L`). O rig efêmero usa o escopo da ferramenta.
   - **Rigify**, braço/perna em **IK**: mão/antebraço (pé/canela) → o controle IK (`hand_ik`/`foot_ik`), com **grab** se o frame atual tem key e **arco** se não tem (esparso, como na trail); braço de cima/coxa → o **pole** (`upper_arm_ik_target`/`thigh_ik_target`).
   - **Rigify**, tronco: `DEF-spine`/`.001` → `hips`; `.002`/`.003` → `chest`; `.004`/`.005` → `neck`; `.006` → `head`; ombro → `shoulder`; dedos → o controle FK do dedo (escopo Ponta).
5. **Ponto arrastado** = o ponto atingido na superfície, rígido com o último bone da cadeia (deixa de ser só a cauda): `core/ephemeral` recebe um **deslocamento local** do ponto no espaço desse bone. Δ em mundo no plano da vista pelo ponto, como hoje.
6. **Frame**: o frame atual da cena (não há ponto de trail). Preview: a pose muda ao vivo no viewport (o Blender reavalia o frame atual depois de cada escrita) e a trail prevista da parte, se estiver visível.
7. **Duas etapas no pescoço/cabeça do Rigify** (decisão 10), na ferramenta Corpo:
   1. inclina `torso → chest` (rígidos) para levar a base do pescoço na direção do alvo;
   2. aponta `neck`/`head` (Ponta) para o ponto agarrado.

   Os links não rígidos (Neck/Head Follow) são resolvidos medindo de novo a base do pescoço no frame atual depois da etapa 1, uma reavaliação do depsgraph por frame da janela. Se for caro demais para o mouse move, o preview faz só o frame atual e a janela inteira é aplicada ao soltar.

## Painel N (aba Animation Sculptor)

```
Animation Sculptor
  Modo:  [ Corpo | Trail ]
  ─ Visualização ─────────────────
  [x] Trails   [ ] Onion skin   [ ] Onion expandida   [x] Ligar Rigify
  ▸ Parâmetros   (fechado: raios, falloff, orientação da ponta, escopo de timing, spacing, Smooth…)
  ▸ Breakdown    (fechado, nativos)
  ▸ Estatísticas (fechado, depuração)
  ▸ Trails (LMP) (fechado, configurações finas)
```

## Régua de tempo v2

- Mais larga: até a largura útil do viewport menos as margens (antes, 560 px), em **frames**.
- Pontas em **triângulo** (vermelho/verde), como na palestra, além das barras.
- Uma **faixa de keys** logo abaixo da régua, com as keys da parte em hover ou em gesto.
- Mesma posição (embaixo, centro), mesma interação (arrastar as pontas, Shift = os dois lados, 1 passo de undo).

## Onion skin

- **Toggle "Onion skin"**: liga o onion skin do LMP (`asc_trails.onion_show`) com a paleta passado/futuro. Os frames vêm da **janela da régua**: `onion_before`/`onion_after` = raios passado/futuro, com `onion_step` automático para no máximo ~12 fantasmas de cada lado.
- **Toggle "Onion expandida"**: os mesmos fantasmas, cada um deslocado para o lado na tela proporcionalmente a `f − f₀` (passado à esquerda, futuro à direita, eixo horizontal da vista). O espaçamento automático vem da largura do personagem, como na captura de 23:41.
  - Exige um gancho no desenho do onion do LMP: **patch P11** em `trails/lmp/draw.py`, um deslocamento por fantasma vindo de `provider`, registrado em [live-motion-path.md](../reference/live-motion-path.md) e na proveniência.
  - O frame atual não se desloca. As trails não se deslocam.

## "Ligar Rigify"

- **Desligado**: esconde os bones (e as formas dos controles do Rigify) em todos os viewports 3D, pela opção de overlay `show_bones`; a malha fica. O modo Corpo continua funcionando, porque o picking é na malha.
- **Ligado**: mostra de novo.
- (Implementação: o plano previa esconder as coleções de bones e guardar quais estavam visíveis; o overlay faz o mesmo sem guardar estado, vale para esqueletos sem coleções e é trivialmente reversível.)
- Nada é desabilitado no rig e nenhuma animação muda; o modo Trail continua disponível.
- Em esqueletos sem Rigify, o mesmo toggle esconde ou mostra o esqueleto.

## Smooth

Pincel temporal:
- Com o botão pressionado sobre uma parte (modo Corpo) ou trail (modo Trail), cada 8 px de arrasto aplica **um passe** de suavização gaussiana aos canais dos controles da parte, dentro da janela da régua.
- Cada passe é ponderado pelo falloff e por uma **força** (parâmetro; o "Smooth" da toolbar da palestra): `v'(f) = v(f) + w(f)·s·(G*v(f) − v(f))`.
- Os canais são amostrados nos frames inteiros e gravados como keys densas (`core/dense`).
- Quaternions: componente a componente com hemisfério contínuo e renormalização.
- É determinístico: o número de passes depende só do comprimento do arrasto.
- O algoritmo é um gaussiano discreto próprio, no espírito do `graph.gaussian_smooth` do Blender (registrar em proveniência se portar).

## Fases (um PR cada; no máximo 3 empilhados)

1. **UX-1 — Ferramentas e painel**:
   - as quatro ferramentas na barra lateral (Smooth ainda inativa, com aviso);
   - o seletor de modo Corpo/Trail;
   - o painel N reorganizado (toggles + seções fechadas);
   - a régua v2.

   No modo Corpo desta fase, o picking é a ponta do bone (0.6.0), até a UX-2.
2. **UX-2 — Agarrar o corpo**:
   - raycast + bone sob o cursor + realce;
   - `control_for_deform` (genérico e Rigify);
   - ponto arrastado na superfície (`core/ephemeral` com deslocamento local);
   - grab/arco IK pelo corpo;
   - toggle "Ligar Rigify".
3. **UX-3 — Onion skin**: os toggles, a janela da régua como range, o onion expandido (patch P11).
4. **UX-4 — Smooth e cabeça em duas etapas**: o pincel Smooth e a decisão 10.

## Notas da implementação (0.7.0)

- **Um PR só** com UX-1 a UX-4 (pedido do mantenedor). Régua v2, onion skin (provider + patch P11) e o núcleo do Smooth (`core/smooth.py`) feitos por agentes em worktrees isolados e integrados.
- **Ferramentas**: `animation_sculptor.tip` (Ponta), `.sculpt` (Membro — mantém o id antigo, que keymaps e arquivos da 0.3–0.6 usam), `.body` (Corpo), `.smooth` (Smooth); ícones nativos (`ops.pose.relax`, `ops.pose.breakdowner`, `ops.pose.push`, `ops.gpencil.sculpt_blur`). O escopo do gesto vem da ferramenta ativa; `Shift+Alt+K` → `asc.activate_tool` (a última usada, Membro na primeira vez).
- **Modo** (`Scene.asc_sculpt.interaction_mode`, padrão **Corpo**): trocar para Trail liga as trails; no modo Corpo a ferramenta não liga as trails sozinha (viewport limpo).
- **Picking na malha** (`interaction/body_pick.py`): `Scene.ray_cast` no depsgraph; malha deformada pela armature ativa (modificador Armature) ou presa a um bone dela (adereço, ex.: espada → o bone do adereço); bone deformador = maior peso somado na face (topologia igual) ou o segmento mais próximo; realce = triângulos com peso dominante do bone (cache por malha), desenhados em POST_VIEW sobre a malha avaliada.
- **Mapa DEF → controle** (`RigAdapter.control_for_deform`, `rig.CHAIN`/`rig.IK`): genérico = o próprio bone; Rigify como no passo 4 de "Agarrar o corpo" (dedos e rosto: o controle de mesmo nome, senão a cabeça).
- **Ponto agarrado**: `core/ephemeral.Chain.point` (ponto no espaço local do último bone, constante ou por frame); `ChainEdit(point_world=…)`.
- **Pescoço/cabeça do Rigify no Corpo** (decisão 10), ao soltar, medido no rig (frame stepping, passos fixos): (1) o chest inclina até a base do pescoço andar `w·Δ` (3 iterações de ponto fixo); (2) cabeça: o pescoço aponta para levar o pivô da cabeça ao ponto do IK de 2 bones; (3) o bone agarrado aponta o ponto para o alvo. Medido no rig gerado: cabeça 0,00 mm, pescoço 0,78 mm. Durante o arrasto o preview mostra só a inclinação.
- **Smooth**: `interaction/smooth_edit.SmoothEdit` sobre os canais animados do controle da parte (location, rotação do modo, escala); quaternions em bloco; 8 px de arrasto = 1 passe; força e largura (σ) nos Parâmetros.
- **Testes veem a malha** (pedido do mantenedor): o asset local mantém as malhas da Vale visíveis (gerador v2) e o rig público ganhou um corpo simples pesado (`tests/blender/body_mesh.py`); `tests/blender/deform_check.py` confere a deformação da pele nos gestos.

## Testes (por fase)

- Unit:
  - mapa DEF → controle (armatures falsos);
  - deslocamento local do ponto arrastado (o ponto cai no alvo);
  - passe de Smooth (Δ = 0 ⇒ identidade, peso 0 ⇒ bit a bit, determinismo);
  - deslocamento do onion expandido.
- Blender:
  - raycast + bone sob o cursor no rig público com uma malha simples pesada (gerada no teste);
  - gesto pelo corpo no Rigify (FK ⇒ cadeia; IK ⇒ grab/arco; pole) e no genérico;
  - "Ligar Rigify" restaura exatamente as coleções;
  - Smooth.
- UI (`dev.py test ui`):
  - na Vale: hover na malha realça a parte;
  - arrastar o antebraço FK gira o braço e a mão IK move o `hand_ik`;
  - a ferramenta ativa muda o escopo;
  - os toggles do painel;
  - a régua v2;
  - os screenshots de cada fase vão para a conversa.
- Manual: o mantenedor anima com cada PR (decisão 8); cada PR traz o roteiro clique a clique.

## Esqueleto simples e Girar (0.8.0, [ADR 0014](../decisions/0014-skeleton-first.md))

- **Esqueleto primeiro**: o personagem usa um esqueleto de deformação simples (`scripts/make_basic_rig.py`, `dev.py basic-rig`: 53 bones com dedos, quaternions; `root` só translada, `hips` translada e gira, o resto só gira). Os bones de deformação são os controles: todo gesto do modo Corpo é o rig efêmero sobre eles, pelo adapter genérico. O Rigify continua disponível ("Ligar Rigify"), em segundo plano.
- **Girar** — duas formas, para o mantenedor comparar a usabilidade:
  - a **ferramenta Girar** (barra lateral, ícone de rotação): LMB no corpo + arrastar gira o bone sob o cursor em volta da junta (cabeça do bone), no plano da vista;
  - **segurar R** com qualquer ferramenta de sculpt: R + arrastar faz o mesmo; apertar R **no meio** de um arrasto de Membro/Corpo troca o gesto para Girar (a parte já arrastada é desfeita).
  - O ângulo segue o mouse em volta do pivô na tela (acumulado pelo menor caminho, sem saltos em ±180°). **Shift** no início = **torção** (gira em volta do eixo do próprio bone; arrastar na horizontal). Roda/`[ ]` mudam a janela; Esc/RMB cancela bit a bit; soltar sem girar não escreve nada; um passo de undo. Header: `Girar <bone> +30°` e a janela.
  - Escreve keys densas de rotação na janela da régua, com o falloff (`core/ephemeral.rotate`: peso 0 deixa a key idêntica).
- **Trails no modo Corpo**: com as trails ligadas, os pontos da trail são agarráveis também no modo Corpo (o picking testa a régua, depois a trail, depois a malha); os gestos de trail são os mesmos do modo Trail.
- **Onion expandido**: um espaçamento por **personagem** (armature que deforma as malhas), medido na caixa de todas as malhas visíveis dele: malhas separadas do mesmo esqueleto (cabeça, tronco, pernas) andam juntas.

## Fluxo do modo Corpo (0.9.0, depois do walk cycle do mantenedor)

- **Sem clicar no esqueleto**: no modo Corpo os alvos de trail e onion não dependem da seleção (patch P12 do LMP): as malhas do personagem (o armature ativo, o que deforma o objeto ativo ou todos os que deformam malhas visíveis) recebem o onion, e a **parte do corpo tocada por último** mostra a trail (antes de tocar: os bones selecionados, como antes). Alvos fixados (`PINNED`) e o modo Trail seguem o LMP.
- **Botão Animar** (painel N, quando não se está em Pose Mode no personagem): entra em Pose Mode no esqueleto que deforma o objeto ativo (mesmo escondido) e ativa a última ferramenta (Corpo na primeira vez). O toggle "Ligar Rigify" passou a se chamar **Esqueleto**.
- **Começar do zero**: o primeiro gesto num personagem sem animação cria a Action (com slot); um clique sem arrasto, um Esc ou uma recusa a removem de novo.
- **Corte no frame 0** (`Scene.asc_sculpt.clip_negative`, ligado; Parâmetros › "Cortar no frame 0"): a janela de um gesto nunca escreve keys antes do frame 0.
- **Smooth no membro inteiro**: o pincel suaviza a cadeia `Membro` até a parte (braço inteiro no antebraço), porque o caminho do cotovelo depende do braço de cima.
- **Smooth da trail** (padrão; barra da ferramenta e Parâmetros › Suavizar: **Trail** | Rotações): o caminho do ponto agarrado no mundo (a trail) é suavizado com o mesmo filtro gaussiano (falloff da régua × força) e o membro é resolvido em cada frame para o ponto seguir o caminho suavizado (rig efêmero com alvo por frame; a mão mantém a orientação no mundo, então o alvo é exato). Rotações = o Smooth anterior (curvas de rotação frame a frame). Controles que transladam (hips, IK do Rigify) usam sempre a suavização das curvas, que já é a trail deles. `ephemeral_edit.TrailSmoothEdit`.
- **Cotovelo/joelho sem saltos**: ver [ephemeral-rig](ephemeral-rig.md) ("Membro quase reto").

## Riscos e perguntas abertas

- **Custo do raycast por mouse move** em malhas densas: medir; cache de `BVHTree` por pose e frame; meta < 16 ms com o realce.
- **Malha com modificadores que mudam a topologia** (subdivisão): o fallback pelo segmento de bone é menos preciso nas juntas.
- **Rigify com nomes diferentes** (metarigs customizados): o mapa DEF → controle cobre o metarig Human; o resto cai no genérico, sobre os bones DEF (avisar no header).
- **Preview no modo Corpo**: a pose ao vivo exige reavaliar o rig a cada mouse move (Rigify) — medir; se passar do orçamento, mostrar só a trail prevista durante o arrasto e a pose ao soltar.
- **Unir os modos no futuro** (decisão 1): ex. Ctrl no modo Corpo = timing da parte agarrada.
- **Eixos do Girar** (feedback de 2026-10-04): o mantenedor achou os eixos de rotação ruins e vai propor uma forma melhor — revisitar.

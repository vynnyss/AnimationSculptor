# 0013 — Interação em dois modos: agarrar o corpo (pose/arco) e agarrar a trail (tempo)

- Status: proposto
- Data: 2026-10-04

## Contexto e problema

Até a versão 0.6.0, toda a interação partia de **pontos da trail** (herança do Motion Trail, [ADR 0010](0010-tool-gizmo-modal-interaction.md)): era preciso selecionar um bone, esperar a trail dele e mirar num ponto. A palestra *Motion Sculpting* (BCON26), referência do [rig efêmero](0011-ephemeral-rig-dense-keys.md), mostra outro modelo, inspirado no ZBrush: o animador passa o mouse **sobre o corpo do personagem**, a parte sob o cursor é realçada e arrastar já esculpe a pose. Não há bone selecionado nem trail a mirar, as ferramentas ficam à mão no viewport e o control rig fica fora de vista. O mantenedor testou a 0.6.0 e a interface ficou diferente do que esperava.

## Opções consideradas

1. Só trail (como até a 0.6.0).
2. Só corpo (como na palestra).
3. **Os dois, em modos**: no modo **Corpo** agarra-se a malha (pose e arco); no modo **Trail** agarra-se a trajetória (timing e spacing, como hoje). A troca de modo fica no painel N.

## Decisão

Opção 3 (decisão do mantenedor, 2026-10-04). Detalhes em [design/sculpt-ux.md](../design/sculpt-ux.md). Em resumo:

- **Ferramentas na barra lateral** (toolbar do viewport, com ícone): **Ponta**, **Membro**, **Corpo** e **Smooth**. O escopo do gesto passa a ser a ferramenta ativa, e não mais um campo do painel.
- **Painel N** com o seletor de modo **Corpo ↔ Trail** e uma seção de **toggles simples** (Trails, Onion skin, Onion skin expandida, Ligar Rigify). Os parâmetros detalhados e a depuração ficam recolhidos abaixo.
- **Agarrar o corpo** = raycast na malha avaliada → bone deformador sob o cursor → **controle** que o adapter associa a ele, conforme o estado do membro (IK: o controle IK, com grab/arco esparsos; FK ou esqueleto sem control rig: o rig efêmero, com keys densas). O ponto agarrado na superfície é o ponto arrastado.
- **"Ligar Rigify"** só mostra ou esconde o control rig. A animação continua sendo gravada nos controles do Rigify, para permitir voltar a eles para ajuste fino.
- O mecanismo técnico do ADR 0010 continua o mesmo (WorkSpaceTool + Gizmo para hover/picking + modal por gesto, um passo de undo): muda **o que** o picking procura (malha no modo Corpo, trail no modo Trail).

## Justificativa

- O modo Corpo dá a experiência da palestra e dispensa selecionar bones e mirar trails, que eram o atrito maior.
- O modo Trail continua sendo o melhor lugar para timing e spacing (ver e mexer na distribuição dos frames).
- Escrever nos controles do Rigify preserva a [ADR 0002](0002-rigify-first-rig-adapter.md) e o pipeline (bake → glTF); o mesmo mecanismo serve a esqueletos sem control rig (Mixamo) pelo adapter genérico.

## Consequências

- Novos módulos: picking na malha (raycast + pesos/segmentos de bone) e realce da parte do corpo; o mapa "bone deformador → controle" entra no Rig Adapter; o ponto arrastado do rig efêmero deixa de ser só a cauda do bone e passa a ser qualquer ponto rígido com ele.
- As ferramentas Ponta/Membro/Corpo substituem `Scene.asc_sculpt.ephemeral_scope` como seletor de escopo (o campo vira estado interno da ferramenta ativa).
- Keys densas ficam mais frequentes (quase todo gesto no modo Corpo usa o rig efêmero). O mantenedor considera isso aceitável (ferramenta "estilo ZBrush"); "Simplificar" fica para o futuro.
- O mantenedor pode querer, no futuro, unir os dois modos numa interação só.

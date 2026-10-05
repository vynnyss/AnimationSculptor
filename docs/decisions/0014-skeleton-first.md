# 0014 — Esqueleto primeiro: o esqueleto de deformação simples é o controle; Rigify em segundo plano

- Status: aceito (2026-10-04, pedido do mantenedor; implementado na 0.8.0). Substitui em parte a [ADR 0002](0002-rigify-first-rig-adapter.md).
- Data: 2026-10-04

## Contexto e problema

A [ADR 0002](0002-rigify-first-rig-adapter.md) fez do Rigify o rig principal: o sculpt escrevia nos controles do control rig (IK/FK, pole, follow). Depois da reforma de UX ([ADR 0013](0013-body-and-trail-interaction.md)) quase todo gesto é feito **agarrando o corpo**, e o rig efêmero ([ADR 0011](0011-ephemeral-rig-dense-keys.md)) já resolve a cadeia sozinho. Nesse fluxo o control rig mais atrapalha do que ajuda: bones auxiliares que não seguem rígido (Neck/Head Follow, `hips` com pernas FK), estados IK/FK, pole, duas etapas no pescoço. O mantenedor testou a 0.7.0 e pediu para deixar o Rigify de lado e trabalhar com um esqueleto simples (estilo Mixamo) em que os controles do corpo **são** os bones de deformação. Esse esqueleto também é o que vai para o Godot.

## Opções consideradas

1. Continuar Rigify primeiro (como na ADR 0002).
2. **Esqueleto primeiro**: um esqueleto de deformação simples (hierarquia humanoide, rotações em quaternion, `root` só translada, `hips` translada e gira, os outros só giram), em que o adapter genérico e o rig efêmero fazem tudo. O Rigify continua funcionando como adapter secundário.
3. Gerar um control rig próprio.

## Decisão

Opção 2 (decisão do mantenedor, 2026-10-04).

- O fluxo principal é o **esqueleto simples**: os bones de deformação são os controles; o gesto é sempre o rig efêmero (keys densas) sobre eles, e o gerador é `scripts/make_basic_rig.py` (`python scripts/dev.py basic-rig`): 53 bones com dedos, juntas encaixadas no centro da seção da malha e pesos automáticos. O gerador lê a malha do usuário e grava **outro** arquivo (por exemplo `Vale_new_Basic_rigged.blend`); o original nunca é alterado.
- O **adapter genérico** atende esse esqueleto sem nomes de bones: as capacidades vêm dos locks; `Membro` para numa bifurcação; `Corpo` atravessa bifurcações até 8 bones; os pinos são os membros de filho único que pendem da raiz da cadeia (as pernas).
- O **Rigify não é removido**: o adapter, os testes no rig público gerado e o toggle "Ligar Rigify" continuam, mas novos recursos são feitos e testados primeiro no esqueleto simples.
- Novo gesto **Girar** (orientação do bone), oferecido de duas formas para o mantenedor comparar: a ferramenta dedicada **Girar** e **segurar R** com qualquer ferramenta de sculpt (inclusive no meio de um arrasto).

## Justificativa

- Com o rig efêmero, um esqueleto simples já tem tudo o que o gesto precisa: cadeia rígida, pinos e locks.
- Os dados animados são os que vão para o Godot: não há bake de control rig para deform.
- Sem bones auxiliares que não seguem rígido, os casos especiais do Rigify (pescoço/cabeça em duas etapas, recusas por rigidez) deixam de aparecer no fluxo principal.

## Consequências

- O asset de teste local passa a ser `basic_rig_test.blend` (gerado por `dev.py basic-rig`); a fixture `simple_rig` monta o mesmo esqueleto num corpo de teste e roda no CI.
- O onion expandido passa a espalhar **um fantasma por personagem** (armature que deforma as malhas), e não por malha: malhas separadas do mesmo esqueleto (cabeça, tronco, pernas) ficam juntas.
- As trails também podem ser agarradas no modo Corpo, quando estão visíveis.
- IK/FK, snapping e o caminho de bake do Rigify ficam congelados até o mantenedor pedir; o Escopo 2 (pipeline Godot) parte do esqueleto simples.
- A ADR 0002 recebe "substituída em parte por 0014".

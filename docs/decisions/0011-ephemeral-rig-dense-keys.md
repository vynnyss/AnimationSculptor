# 0011 — FK por rig efêmero (solve em `core/`) com keys densas na janela de tempo

- Status: aceito (2026-10-04: o mantenedor decidiu implementar o rig efêmero logo depois da UI de tempo, antes do Escopo 2)
- Data: 2026-10-04

## Contexto e problema

O MVP precisa esculpir cadeias FK (swing de espada com braço FK). O plano era portar o Tangent-Space Optimization (Escopo 4, [ADR 0006](0006-tangent-space-deferred.md)): QP com Jacobianos sobre keys e handles esparsos, só Euler no fork de referência, complexo. A palestra *Motion Sculpting* (Nacho de Andrés, BCON26) mostrou outra abordagem, já validada com animadores: rig **descartável** — um IK/cadeia temporário resolvido durante o gesto sobre as rotações FK, numa janela de tempo com falloff, gravando keys em todo frame. Ver [design/ephemeral-rig.md](../design/ephemeral-rig.md).

## Opções consideradas

1. Tangent-Space portado para numpy (plano original), keys esparsas.
2. **Rig efêmero como matemática em `core/`** (IK analítico de 2 bones, rotação mínima, mínimos quadrados amortecidos com iterações fixas para cadeias longas), escrevendo **keys densas** na janela de tempo.
3. Rig efêmero como dados do Blender: criar bones/constraints temporários, avaliar pelo depsgraph e `nla.bake` ao soltar.
4. Opção 2 com keys esparsas (solve só nos frames com key).

## Decisão

Opção 2. Os gestos de translação existentes continuam esparsos (invariantes do modelo inalteradas); o gesto efêmero sobre controles só de rotação grava uma key por frame inteiro da janela e preserva tudo fora dela. O Tangent-Space deixa de ser o caminho do FK e fica como referência.

## Justificativa

- IK de 2 bones tem solução fechada e mesma entrada ⇒ mesma saída: honra a filosofia determinística melhor que um QP.
- Keys densas: decisão do mantenedor (2026-10-04), igual ao comportamento da palestra; a mão segue o arrasto exatamente em todo frame, o que a opção 4 não garante (rotação interpolada não é linear em posição).
- (3) cria estado no `.blend`, custa um bake por gesto e complica undo/cancel; contraria "o único estado persistente é a Action" e o [ADR 0008](0008-pure-python-core.md).
- Funciona igual em Rigify (controles FK) e em esqueletos sem control rig (adapter genérico), sem nomes de bones fora de `rig/`.

## Consequências

- ADR 0006 passa a "substituído por 0011" na parte de FK (o solve linear de translação continua valendo).
- Regiões editadas pelo gesto efêmero ficam densas: arc drag e spacing perdem sentido ali; smooth temporal e "Simplificar" ganham prioridade.
- Critério 10 do Escopo 1 ("editável no Graph Editor") continua verdadeiro, mas a curva densa é menos confortável de editar à mão.
- Novos módulos: `core/kinematics`, `core/ephemeral`, `core/dense`, `core/solve`, `interaction/ephemeral_edit`, `RigAdapter.ephemeral_chain`, `anim/spaces.prefetch_chain`.

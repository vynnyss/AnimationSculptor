# 0006 — Tangent-Space fora da Iteração 1; solve linear para translação

- Status: aceito (solve linear de translação). A parte de FK (Tangent-Space no Escopo 4) foi substituída pelo [ADR 0011](0011-ephemeral-rig-dense-keys.md) (aceito em 2026-10-04).
- Data: 2026-10-03

## Contexto e problema

"Arrastar um ponto in-between e o movimento se ajustar sem novas keys" é o coração do motion sculpting. O método de referência (Tangent-Space Optimization, fork IMP) usa Jacobianos e QP, só suporta Euler, e é complexo.

## Opções consideradas

1. Portar o tangent-space completo já na Iteração 1.
2. **Iteração 1 só com controles de translação**, usando a linearidade exata da Bézier com x fixo; tangent-space para FK depois.
3. Inserir keys novas no frame arrastado (simples, mas suja a animação).

## Decisão

Opção 2. Arc drag resolve os valores dos handles do segmento por mínimos quadrados de norma mínima (fórmula fechada por canal). Tangent-Space (com suporte a quaternion) entra no Escopo 4 para cadeias FK.

## Justificativa

Para `location`, o problema **é** linear: resultado exato, determinístico, sem iteração, testável. Cobre IK de mão/pé, torso, root, poles — a maior parte de um ataque com IK. (1) concentra risco onde ainda não há workflow; (3) contraria a ideia de esculpir sem keys extras.

## Consequências

- Iteração 1 não esculpe trails de bones FK (só timing/spacing, que são agnósticos).
- `core/solve.py` nasce pequeno e cresce para o QP com pins (Escopo 2) e Jacobianos de rotação (Escopo 4).
- Detalhes matemáticos: [design/motion-sculpt-model.md](../design/motion-sculpt-model.md).

# 0005 — Extensão Python, não fork nem módulo nativo

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

O Interactive Motion Path mostra que um gizmo nativo em C++ com Eigen funciona bem, mas exige fork do Blender. Python pode ser lento para solvers grandes.

## Opções consideradas

1. Fork do Blender.
2. Extensão com módulo nativo compilado (wheel C/C++).
3. **Extensão Python pura + numpy** (embarcado no Blender).

## Decisão

Opção 3.

## Justificativa

Instalação trivial (zip de extensão), sem build por plataforma, sem manter fork. Os problemas do MVP são pequenos (dezenas de parâmetros): numpy basta. Avaliação pesada (rig) é feita pelo próprio Blender.

## Consequências

- Performance é tratada com cache, preview analítico e time slicing, não com código nativo.
- Reavaliar (2) somente se profiling do Escopo 4 mostrar gargalo no solver que numpy não resolva — registrar novo ADR.

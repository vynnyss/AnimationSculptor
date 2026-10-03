# 0008 — Core puro (numpy, sem bpy) separado da integração

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

Testes que exigem Blender são lentos e chatos de rodar; a matemática do sculpt (Bézier, falloff, solves, timing) é onde bugs sutis nascem.

## Opções consideradas

1. Código organizado por feature, com `bpy` em todo lugar.
2. **`core/` sem `bpy`/`mathutils`**, com dados em numpy/dataclasses; adaptadores finos em `anim/`, `rig/`, `interaction/`.

## Decisão

Opção 2.

## Justificativa

Testes unitários em milissegundos com pytest comum (CI barata, iteração rápida de agentes); invariantes matemáticas verificáveis; a avaliação Bézier do core pode ser validada contra `FCurve.evaluate` num teste de integração.

## Consequências

- `core/bezier.py` precisa reproduzir fielmente a avaliação do Blender (inclusive correção de handles) — teste de paridade obrigatório.
- Conversões `mathutils` ⇄ numpy concentradas em `anim/`.
- Regra verificada por `scripts/dev.py validate` (nenhum `import bpy` em `core/`).

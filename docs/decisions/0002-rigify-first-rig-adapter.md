# 0002 — Rigify primeiro, por trás de um Rig Adapter

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

Precisamos de um rig humanoide com IK/FK, separação control/deform e caminho de bake. Não queremos construir rig próprio, mas também não queremos o core preso a nomes do Rigify.

## Opções consideradas

1. Rig próprio.
2. Rigify com nomes de bones espalhados pelo código.
3. **Rigify via interface `RigAdapter`** + adapter genérico de fallback.
4. Suportar vários rigs (Mixamo, genéricos) desde o início.

## Decisão

Opção 3. O core e a interação trabalham com conceitos (`hand_ik.L`, `forearm.L`…) e capacidades (translação/rotação). `RigifyAdapter` traduz. `GenericAdapter` (qualquer bone com `location` = controle de translação) garante funcionamento básico em qualquer armature.

## Justificativa

Rigify é nativo, mantido, tem IK/FK, snapping, DEF separados. A interface custa pouco agora e evita reescrita quando outros rigs vierem. (4) multiplica testes sem servir ao MVP.

## Consequências

- Nenhum literal de nome de bone fora de `rig/` (checagem em `scripts/dev.py validate`).
- O mapa Rigify precisa ser validado contra um rig gerado no 5.2 (teste de integração).
- Mixamo/Generic Humanoid ficam pós-MVP. Spec: [design/rig-adapter.md](../design/rig-adapter.md).

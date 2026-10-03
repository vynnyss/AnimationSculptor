# Instruções para agentes

Este repositório usa `docs/` como memória persistente. Antes de qualquer mudança significativa:

1. Leia `docs/project.md`, `docs/current-state.md`, `docs/architecture.md`, `docs/agenda.md`.
2. Consulte os ADRs relacionados em `docs/decisions/`.
3. Antes de implementar um sistema, verifique `docs/reference/open-source-projects.md` — reutilizar antes de implementar.

Depois de mudanças significativas: atualize `current-state.md` e `agenda.md`; `architecture.md` se a estrutura mudou; ADR só para decisão arquitetural relevante; proveniência em `docs/reference/open-source-provenance.md` se entrou código de terceiros.

Fluxo Git (obrigatório): repositório `vynnyss/AnimationSculptor`. Nunca commitar/push direto na `main`. Branch nova a partir da `main` → PR para `main` → parar; o mantenedor testa, aprova e faz o merge. Detalhes: `docs/development/workflow.md`.

Regras de código:
- Blender 5.2 apenas. Slotted Actions (nunca `Action.fcurves`), `PoseBone.select`, só módulo `gpu`.
- `animation_sculptor/core/` não importa `bpy` nem `mathutils`.
- Nenhum nome de bone fora de `animation_sculptor/rig/`.
- O único estado persistente é a Action (+ configurações da cena).
- Código vendorizado: preservar cabeçalhos; patches marcados `# ASC-PATCH Pn`.
- Rodar `python scripts/dev.py test all` antes de declarar algo pronto.

Se código e docs divergirem: verifique o comportamento real e corrija a documentação.

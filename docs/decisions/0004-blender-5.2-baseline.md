# 0004 — Blender 5.2 LTS como baseline único

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

As APIs de animação mudaram muito entre 4.x e 5.x (slotted actions, remoção de `Action.fcurves`, `PoseBone.select`, remoção de `bgl`). Suportar versões antigas duplica caminhos de código.

## Opções consideradas

1. Suportar 4.2+ (como o LMP faz).
2. **Somente 5.2** (`blender_version_min = "5.2.0"`).

## Decisão

Opção 2. 5.2 é LTS, o usuário usa 5.2, e é a versão mais recente com notas de release estáveis.

## Justificativa

Código mais simples; testes contra uma versão; nenhuma razão de produto para versões antigas.

## Consequências

- Ramos `< 5.0` do `compat.py` vendorizado podem ser removidos (patch opcional P6).
- Novas versões (5.3+) são avaliadas quando saírem; diferenças vão para [development/blender-5.2-notes.md](../development/blender-5.2-notes.md).

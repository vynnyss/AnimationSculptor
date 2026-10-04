# 0012 — Política de spacing: `PRESERVE_PATH` como padrão

- Status: aceito
- Data: 2026-10-04

## Contexto e problema

O gesto de spacing (Ctrl+arrastar um in-between) muda a distribuição dos frames num segmento entre duas keys mexendo no `x` dos handles internos (`core/timing_ops.set_spacing`). Na key onde o segmento encosta há duas formas de tratar a tangente ([motion-sculpt-model](../design/motion-sculpt-model.md)). As duas foram implementadas e testadas no Escopo 1 e ficaram trocáveis no painel até o mantenedor decidir.

## Opções consideradas

1. **`PRESERVE_PATH`**: só o `x` dos dois handles internos muda; as keys viram `FREE`. O caminho nunca muda e o segmento vizinho fica intocado, mas a velocidade pode "quebrar" na key (chega rápido, sai devagar).
2. **`PRESERVE_SMOOTHNESS`**: handles `ALIGNED`, com o handle oposto realinhado mantendo o seu `x`. A passagem pela key fica lisa, mas o segmento vizinho muda um pouco.

## Decisão

Opção 1 como padrão (decisão do mantenedor, 2026-10-04). A opção 2 continua disponível como parâmetro (`Scene.asc_sculpt.spacing_policy`).

## Justificativa

É previsível e local: muda só o trecho que o animador tocou. Uma quebra de velocidade na key é visível na cor de velocidade e fácil de corrigir com outro gesto; uma mudança silenciosa no segmento vizinho não é.

## Consequências

- O padrão de `spacing_policy` continua `PRESERVE_PATH` (nenhuma mudança de código).
- A investigação "política de spacing" sai da agenda.

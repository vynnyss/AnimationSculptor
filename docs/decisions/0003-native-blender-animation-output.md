# 0003 — Saída é animação Blender nativa (Action/F-Curves)

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

Ferramentas de "motion sculpt" poderiam manter uma representação própria (curvas paramétricas, camadas, dados em custom properties) e gerar keys a partir dela. Isso cria estado paralelo que pode divergir das F-Curves, quebra Graph Editor e complica save/undo/export.

## Opções consideradas

1. Representação própria persistida + geração de keys.
2. Objetos/empties de controle na cena (estilo Motiontrail3D).
3. **Editar diretamente keys e handles das F-Curves da Action ativa.**

## Decisão

Opção 3. A Action é a única fonte de verdade persistente. Tudo que o addon mostra é derivado dela; tudo que o addon faz é escrever keys/handles/tipos de handle.

## Justificativa

Graph Editor, Dope Sheet, NLA, bake, glTF e Godot funcionam sem saber do Animation Sculptor. Save/reload e undo são os do Blender. Desinstalar o addon não perde nada.

## Consequências

- Operações têm de ser expressas como edições de Bézier (limita "pincéis" arbitrários; ok para o escopo).
- Recusar edição onde não há F-Curve editável (drivers, NLA ativa, modificadores) em vez de "dar um jeito".
- Regras de escrita: [design/animation-data.md](../design/animation-data.md).

# 0009 — Export via bake/amostragem nativa + glTF; sem conversor de esqueleto

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

O MVP termina no Godot. Rigify tem problemas conhecidos em engines (DEF sem hierarquia única, escala, B-Bones, root não-deform).

## Opções consideradas

1. Escrever nosso conversor Rigify → esqueleto de jogo + exportador.
2. **Exportador glTF oficial** (amostragem + Deform Bones Only), `nla.bake` opcional, validação prévia, e recomendar **GameRig**/**Rigodotify** para rigs game-ready.
3. Formato próprio + importador Godot.

## Decisão

Opção 2.

## Justificativa

O problema de esqueleto já foi resolvido por projetos mantidos; o exportador oficial já faz bake por amostragem. (3) viola o objetivo "Godot não sabe do Animation Sculptor".

## Consequências

- `pipeline/` é fino: presets, validação, bake opcional, root motion.
- Teste final valida dois caminhos (Rigify puro e rig game-ready) — compatibilidade de GameRig/Rigodotify com 5.2 a verificar.
- Detalhes: [design/godot-pipeline.md](../design/godot-pipeline.md).

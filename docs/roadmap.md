# Roadmap

> Escopos funcionais grandes. Detalhe operacional fica em [agenda.md](agenda.md). Cada escopo termina com algo que dá para **usar fazendo animação**.

```mermaid
flowchart LR
    E1["Escopo 1<br/>Primeira versão utilizável"] --> E2["Escopo 2<br/>Do Blender ao Godot"]
    E2 --> E3["Escopo 3<br/>Escultura completa"]
    E3 --> E4["Escopo 4<br/>FK e IK/FK"]
    E4 --> MVP(["MVP: ataque completo<br/>Rigify → Godot"])
    MVP --> E5["Escopo 5<br/>Pós-MVP"]
```

Ordem: o pipeline até o Godot (baixo risco técnico) vem cedo para fechar o ciclo de ponta a ponta antes do trabalho mais arriscado (FK/tangent-space). **Exceção decidida pelo mantenedor em 2026-10-04**: o FK pelo rig efêmero (fases 2–4 de [design/ephemeral-rig.md](design/ephemeral-rig.md), parte do Escopo 4) vem logo depois da UI de tempo, antes do Escopo 2.

---

## Escopo 1 — Primeira versão utilizável

**Workflow disponível:**

```
Blender 5.2 → abrir personagem Rigify → keyar key poses (I, normal)
→ ativar tool "Animation Sculptor" em Pose Mode → trails das mãos/pés IK, torso, root, poles aparecem
→ arrastar key point: muda a pose naquele frame (soft grab com raio)
→ arrastar ponto in-between: esculpe o arco sem criar keys
→ Ctrl+arrastar key point: move a pose inteira no tempo
→ Ctrl+arrastar segmento: ease/favor (spacing) com o caminho preservado; cor de velocidade mostra o efeito
→ breakdowner/push/relax nativos no painel para breakdowns
→ Space: playback → Ctrl+Z desfaz gestos → salvar, fechar, reabrir: tudo continua (é só uma Action)
→ (manual, documentado) bake/export com ferramentas nativas → Godot
```

**Inclui:** trails do LMP vendorizado; adapters Rigify + genérico; grab/soft grab, arc drag (translação); retime e spacing (qualquer controle, escopo personagem); preview analítico; undo/cancel; painel; keymap; testes unitários + integração + checklist manual.

**Não inclui:** sculpt espacial de FK, smooth, make arc, pins, tangent handles 3D, ranges, export automatizado.

**Critérios de aceitação (todos):**

1. Instala como extensão (zip) no Blender 5.2 e habilita sem erro; desinstala sem resíduos.
2. Detecta um rig Rigify gerado do metarig Human e lista os controles com capacidades corretas; em armature não-Rigify cai no adapter genérico.
3. Trails atualizam ao trocar seleção, mudar frame, keyar, editar no Graph Editor.
4. Grab de key point em `hand_ik.L` move a mão para onde o mouse indica (erro < 1 mm no plano da vista) e a trail recalculada coincide com o preview.
5. Arc drag num in-between altera o arco sem adicionar keys nem mudar timing (verificado no Dope Sheet).
6. Retime move a pose inteira (todos os canais do personagem naquele frame) e Spacing altera a distribuição dos pontos sem mudar o caminho (verificação visual + teste automático da invariante).
7. Cada gesto = exatamente 1 passo de undo; Esc cancela restaurando as F-Curves bit a bit.
8. Salvar → fechar → reabrir: Action idêntica, ferramenta funciona, nenhum objeto/propriedade extra além das configurações da cena.
9. Playback em tempo real não piora perceptivelmente com a tool ativa (trails ocultas no playback se configurado).
10. Nenhuma dependência de IA/rede; resultado editável normalmente no Graph Editor.
11. Checklist manual "Bloqueio de ataque" ([testing/manual-tests.md](testing/manual-tests.md)) completado pelo usuário num personagem real, com feedback registrado.

---

## UI de tempo (entre o Escopo 1 e o 2) — implementada (0.4.0, em revisão)

Fase 1 do [rig efêmero](design/ephemeral-rig.md#fases-um-pr-cada-a-partir-da-main-depois-do-merge-do-11), independente do solve: **régua de tempo no viewport** (janela do gesto com falloff assimétrico, passado em vermelho e futuro em verde, pontas arrastáveis; o soft grab passa a usá-la), **paleta passado/futuro** nas trails e no onion skin, e as configurações do gesto na **barra nativa da ferramenta** (`WorkSpaceTool.draw_settings`).

**Pronto quando:** soft grab com raios diferentes para passado e futuro, editáveis arrastando as pontas da régua e salvos no arquivo; trails vermelho/verde.

---

## Escopo 2 — Do Blender ao Godot

Fechar o teste do MVP de ponta a ponta com o que o Escopo 1 já permite animar.

- Painel "Export": validação (escala em DEF, B-Bones, múltiplas raízes, modificadores), bake opcional, export glTF com preset Godot, marcação de quais Actions exportar.
- Root motion: decisão e implementação (root deform vs extração).
- Projeto Godot de teste no repo + validação headless automatizada (posições de referência).
- Verificação com GameRig e/ou Rigodotify no 5.2.
- **Loop (Action cíclica)** — parte 1: marcar a Action como loop; operador "Fechar loop" (o último frame recebe exatamente a pose do primeiro em todas as F-Curves do personagem, com tangentes iguais nas duas pontas, para não haver tranco na emenda); validação antes do export (primeira = última pose); export como loop no Godot (sufixo de nome reconhecido pelo importador, conferido no teste headless). Detalhes em [design/motion-sculpt-model.md](design/motion-sculpt-model.md#operações-futuras-escopos-24).

**Pronto quando:** o ataque do Escopo 1 chega ao Godot com posições conferidas automaticamente, pelos dois caminhos de esqueleto suportados.

---

## Escopo 3 — Escultura completa (controles de translação)

Ferramentas para polir o movimento sem Graph Editor.

- Smooth espacial (Relax/Straighten) e temporal (Gaussian/Butterworth portados).
- Make Arc; Pins (restrições no `core/solve`); tangent handles 3D editáveis; **spline de movimento** (curva-guia com `Strength`/`Aim` aplicada a um trecho de tempo — ver [design/ephemeral-rig.md](design/ephemeral-rig.md#spline-de-movimento)).
- Seleção de pontos (box, range), operações em ranges, restrição de eixo, multi-controle.
- Retime com stretch (time beads), timing avançado (offset/overlap de partes), política final de spacing.
- Refinos de UX (pie menu, feedback, preferências).
- **Loop** — parte 2: trail de uma Action em loop desenhada fechada; editar a primeira ou a última key (grab, arc, spacing) mantém as duas pontas iguais; spacing atravessa a emenda.

**Pronto quando:** o ataque pode ser polido (arcos limpos, spacing intencional, sem tremidos) usando só o viewport em controles IK/torso/root.

---

## Escopo 4 — FK e IK/FK

- FK chain sculpt pelo **rig efêmero** ([design/ephemeral-rig.md](design/ephemeral-rig.md), [ADR 0011](decisions/0011-ephemeral-rig-dense-keys.md)): arrastar a ponta de uma cadeia FK (braço com espada, cabeça, coluna) ⇒ IK temporário resolvido em `core/` (2 bones analítico; cadeias longas por mínimos quadrados com iterações fixas), **com quaternions**, numa janela de tempo com falloff, gravando **keys densas** (uma por frame) só na janela. Escopos `Ponta`/`Membro`/`Corpo`. Funciona em Rigify (controles FK) e no adapter genérico (esqueleto sem control rig). Substitui o port do Tangent-Space.
- Arrastar o bone direto no viewport (sem mirar na trail); orientação da ponta `Mundo`/`Local`.
- Trails cientes do estado IK/FK (mostrar o controle ativo do membro).
- Snapping IK↔FK reutilizando os operadores do Rigify; bake de switch.
- Pins no FK (ex.: segurar a mão parada enquanto o tronco gira; pés fixos no escopo `Corpo`).
- "Simplificar" uma região densa de volta a keys esparsas (decidir na fase 3 do rig efêmero se entra aqui ou no Escopo 3).

**Pronto quando:** um ataque com braço FK (swing de espada) pode ser esculpido no viewport ⇒ **MVP completo** (teste de aceitação de [project.md](project.md)).

---

## Escopo 5 — Pós-MVP (candidatos)

Outros adapters (Mixamo, humanoide genérico), trails relativas (espaço do personagem/root), camadas/NLA, performance profunda, publicação na extensions.blender.org.

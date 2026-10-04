# Testes manuais de workflow

> Checklists reproduzíveis feitos por um humano no Blender 5.2 com UI. Registrar resultado (data, build, ✔/✘, observações) no fim de cada execução — feedback vira item na [agenda](../agenda.md).

## M0 — Instalação (2 min)

1. Preferences › Get Extensions › Install from Disk › zip do build.
2. Extensão habilita sem erro no console.
3. Painel N › "Animation Sculptor" aparece em Pose Mode; tool aparece no toolbar.
4. Desabilitar e remover: sem erro, sem painéis órfãos.

## M1 — Bloqueio de ataque (Escopo 1, ~30 min) ★ teste principal

Asset: `tests/assets/local/attack_test.blend` (`python scripts/dev.py assets`) ou personagem Rigify do usuário.

1. Pose Mode. Criar key poses nos frames 1 (idle), 10 (antecipação), 16 (ataque), 18 (impacto), 26 (follow-through), 40 (recuperação) com a mão IK, pés IK, torso e root (keyar com `I` como sempre).
2. Ativar a tool Animation Sculptor; selecionar `hand_ik.R` (mão do golpe): trail aparece; keys como losangos; frame atual marcado.
3. **Grab**: arrastar o key point do impacto para mais longe do corpo. Mão segue o mouse; ao soltar a trail recalculada coincide com o preview.
4. **Soft grab**: repetir o grab e, **durante o arrasto**, girar a roda do mouse (ou `[`/`]`) até raio ≈ 6 frames (lido no header; anéis laranja mostram as keys afetadas); as keys vizinhas acompanham suavemente e nenhuma key nova aparece. Raio 0 = só o ponto.
5. **Arc**: arrastar um ponto (in-between) entre antecipação e ataque para fora: o arco abre e o ponto fica sob o cursor; Dope Sheet mostra as mesmas keys, nos mesmos frames. Repetir com `B` pressionado durante o arrasto (quebrar tangente): o segmento vizinho não muda.
6. **Retime**: Ctrl+arrastar o key point do ataque para o frame 14: a pose inteira (pés, torso…) mudou de frame.
7. **Spacing**: Ctrl+arrastar o segmento antecipação→ataque: ligar cor *Speed*, ver o ease mudar sem o caminho mudar.
8. **Breakdown**: no frame 13, usar Breakdowner do painel favorecendo o ataque.
9. Playback (Space): animação toca normal; trails seguem configuração.
10. Ctrl+Z várias vezes: cada gesto desfaz isoladamente. Esc durante um gesto: nada muda.
11. Abrir Graph Editor: curvas normais, editáveis; editar uma key lá ⇒ trail atualiza.
12. Salvar, fechar Blender, reabrir: tudo igual, tool funciona.
13. **Avaliação qualitativa** (anotar): consegui melhorar o ataque sem o Graph Editor? O que mais faltou? O que irritou?

## M2 — Recusas e casos-limite (Escopo 1, 10 min)

1. Controle com driver / NLA ativa / F-Curve com modificador: sculpt recusa com mensagem clara.
2. Segmento LINEAR: arc drag recusado com aviso (anel vermelho no ponto + "recusado: segmento LINEAR" no header); o aviso some ao mover o hover para outro ponto.
3. Eixo travado (`lock_location`): grab move só nos eixos livres.
4. Armature não-Rigify simples: adapter genérico, grab funciona.
5. Trocar de arquivo com a tool ativa: sem erro.

## M3 — Export manual para Godot (Escopo 1, com ferramentas nativas; 15 min)

1. File › Export › glTF: GLB, Animation ✔ (Actions), Sampling ✔, Armature › "Export Deformation Bones Only" ✔.
2. Importar no Godot 4.7.2: Skeleton3D com `DEF-*`, AnimationPlayer com a animação; tocar e comparar visualmente.
3. Anotar problemas (escala, B-Bones, root). Alimenta o Escopo 2.

## M4 — Pipeline automatizado (Escopo 2)

_(a escrever no Escopo 2)_

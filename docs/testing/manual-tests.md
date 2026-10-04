# Testes manuais de workflow

> Checklists reproduzíveis feitos por um humano no Blender 5.2 com UI. Registrar resultado (data, build, ✔/✘, observações) no fim de cada execução — feedback vira item na [agenda](../agenda.md).

## M0 — Instalação (5 min)

Pré-requisito: `python scripts/dev.py build` gera `dist/animation_sculptor-0.3.0.zip` (ver [setup](../development/setup.md#instalação-do-zip-m0)). Se o desenvolvimento estiver instalado por `dev.py link`, rode `python scripts/dev.py unlink` e reinicie o Blender antes, para testar só o zip.

1. Edit › Preferences › Get Extensions › menu **⌄** (canto superior direito) › **Install from Disk…** › escolher o zip › Install.
2. A extensão "Animation Sculptor" aparece habilitada (Edit › Preferences › Add-ons); sem erro no console (Window › Toggle System Console).
3. Abrir `tests/assets/local/attack_test.blend`, selecionar o armature, Pose Mode. No viewport, `N` › aba **Animation Sculptor**: painel principal, "Gestos", "Breakdown", "Estatísticas" e "Trails". Na toolbar (esquerda) aparece a ferramenta **Animation Sculptor** logo depois de Transform.
4. Com o mouse no viewport, **Shift+Alt+K** ativa a ferramenta (o painel mostra "Ferramenta ativa"). Edit › Preferences › Keymap: buscar "Animation Sculptor" mostra o atalho editável em Pose.
5. Desinstalar: Preferences › Add-ons › Animation Sculptor › ⌄ › Uninstall (ou Get Extensions › Remove). Sem erro; painel e ferramenta somem; o atalho some do Keymap; o `.blend` ainda abre e a Action continua intacta.

## M1 — Bloqueio de ataque (Escopo 1, ~30 min) ★ teste principal

Build **0.3.0**. Asset: `tests/assets/local/attack_test.blend` (`python scripts/dev.py assets`): ataque já keyado nos frames **1, 10, 16, 18, 26 e 40**; mão da espada = `hand_ik.R` (controle IK); braço esquerdo em FK. **Não salve por cima do asset** (o passo 2 já salva uma cópia com outro nome). Variante com o seu personagem: ver o fim desta seção.

**Preparação**

1. `git fetch origin && git switch <branch do PR>`; `python scripts/dev.py link`; reiniciar o Blender (ou instalar o zip como no M0).
2. File › Open `tests/assets/local/attack_test.blend`; File › Save As `attack_m1.blend` (outra pasta/nome).
3. Selecionar o armature, Pose Mode. Timeline no frame 1. Abrir também um Dope Sheet (ou Graph Editor) numa área lateral para conferir as keys.

**Ferramenta e trails**

4. Ativar a ferramenta: clicar em **Animation Sculptor** na toolbar **ou** passar o mouse no viewport e apertar **Shift+Alt+K**. Esperado: o painel N mostra "Ferramenta ativa"; trails aparecem.
5. Selecionar `hand_ik.R` (clique no bone ou pelo Outliner). Esperado: trail da mão com losangos nas keys (1, 10, 16, 18, 26, 40), pontos pequenos nos in-betweens e marcador no frame atual. O botão **Trails** do painel desliga e liga a trail. O painel principal mostra "Rig: … (rigify)" e o conceito/capacidades do bone ativo.
6. Mover o mouse sobre um losango: anel branco e texto no header; sobre um ponto pequeno: anel azul claro.

**Grab e soft grab (espaço)**

7. **Grab**: arrastar o losango do impacto (frame 18) para longe do corpo e soltar. Esperado: a mão segue o mouse (anel laranja); ao soltar, a trail nova coincide com o preview amarelo; Dope Sheet: nenhuma key nova. Ctrl+Z volta ao caminho antigo.
8. **Soft grab com a roda**: arrastar o mesmo losango e, **sem soltar**, girar a roda do mouse (ou `[`/`]`) até o header mostrar raio ≈ 6 frames. Esperado: anéis laranja nas keys vizinhas (10, 16, 26, conforme o raio), que acompanham suavemente; nenhuma key nova. Soltar; Ctrl+Z.
9. **Raio no painel**: em N › Animation Sculptor › **Gestos**, definir **Raio (frames)** = 6 e testar o **Falloff** (Suave, Esfera, Agudo, Linear, Constante); arrastar o losango de novo: o raio vem do painel; girar a roda durante o gesto muda o valor do painel (é salvo no arquivo). Raio 0 = só a key arrastada.

**Arc (arco entre keys)**

10. **Arc**: arrastar um ponto pequeno (in-between) entre a antecipação (10) e o ataque (16) para fora. Esperado: o arco abre e o ponto fica sob o cursor; Dope Sheet com as mesmas keys nos mesmos frames. Soltar; Ctrl+Z.
11. **Arc com B**: repetir e apertar **B** durante o arrasto (header: "quebrar tangente [on]"): o segmento vizinho não muda.

**Recusa**

12. Selecionar um controle FK do braço esquerdo (ex.: `hand_fk.L`; as coleções FK do rig da Vale estão ocultas: selecione pelo Outliner ou mostre a coleção em Bone Collections). **Sem Ctrl**, arrastar um losango dele. Esperado: **anel vermelho** no ponto e, no header, "Animation Sculptor · recusado: controle só de rotação…"; nada muda (Ctrl+Z não tem o que desfazer). A trail do controle FK não vai para a origem.

**Retime e spacing (tempo)**

13. **Retime**: voltar a `hand_ik.R`. **Ctrl**+arrastar o losango do ataque (frame 16) até o frame **14**. Esperado: rótulo `16 → 14`; a cena vai para o frame novo e a **pose inteira** (pés, torso, braço FK) muda de frame; Dope Sheet: as keys de todos os controles do frame 16 foram para o 14, nenhuma key nova. Limites: tentar passar do frame 17 (a 1 frame do impacto, em 18) ou abaixo de 11 (a 1 frame da antecipação, em 10): trava ali (o header mostra "entre 11 e 17"). Soltar; um Ctrl+Z restaura o frame 16.
14. **Spacing**: **Ctrl**+arrastar um in-between do segmento antecipação (10) → ataque (16): horizontal = favorecer a saída/chegada, vertical = ease; o header mostra "saída x% · chegada y%". Esperado: os pontos se redistribuem (agrupam/afastam) **sem o caminho mudar**, sem key nova nem key movida. Soltar; Ctrl+Z.
15. Em N › Gestos, **Cor da trail** = **Speed**: a trail mostra a velocidade (lento → rápido); repetir o spacing e ver o ease mudar a cor sem mudar a linha. Voltar a cor ao modo anterior se preferir.
16. **Política de spacing** (decisão do mantenedor): em Gestos › **Spacing**, fazer o mesmo spacing (ex.: ease forte na saída do 10→16) com **Preservar caminho** e depois com **Preservar suavidade** (Ctrl+Z entre as tentativas). Observar a trail e o Graph Editor (curva de `hand_ik.R`): com *Preservar caminho* o caminho nunca muda, mas a tangente pode quebrar na key (curva com "quina"); com *Preservar suavidade* a tangente fica contínua na key, mas o segmento vizinho muda um pouco. Anotar qual preferiria como padrão e por quê.
17. Em Gestos › **Escopo do tempo**: testar **Personagem** (padrão: retime/spacing movem todos os controles) e **Selecionados** (só os bones selecionados + o arrastado).

**Breakdown e playback**

18. **Breakdowner**: ir ao **frame 13** (entre 10 e 16), selecionar os bones, abrir N › Animation Sculptor › **Breakdown** (fechado por padrão; só aparece em Pose Mode), clicar **Breakdowner** e arrastar o mouse para favorecer o **ataque** (pose do 16); confirmar com clique. Testar também Push, Relax e Blend to Neighbor. Ctrl+Z desfaz cada um. (São operadores nativos do Blender, só atalhados no painel.)
19. **Playback**: Space com a ferramenta ativa. Esperado: a animação toca normal e o **realce/preview do sculpt some** durante o playback (opção "Esconder overlay no playback" em Gestos; desligar para ver a diferença); as trails seguem a configuração "Hide Motion Path During Playback" do Live Motion Path (painel Trails). Anotar se o playback ficou mais lento do que sem a ferramenta. Space para parar.

**Undo e cancelar**

20. Para cada gesto (grab, soft grab, arc, retime, spacing): **Esc** ou RMB **durante** o arrasto = nada muda; depois de solto, **um** Ctrl+Z desfaz o gesto inteiro (e Ctrl+Shift+Z refaz). Fazer três gestos seguidos e desfazê-los um a um.

**Edição nativa**

21. **Graph Editor**: abrir o Graph Editor e editar uma key de `hand_ik.R` (arrastar ou G): a trail do viewport se atualiza sozinha (sem Refresh). As curvas são normais e editáveis.
22. **G + I (Tweak)**: trocar para a ferramenta **Tweak** (toolbar), mover o bone com **G** e apertar **I**: a trail acompanha a nova key. Voltar à ferramenta Animation Sculptor (Shift+Alt+K).

**Salvar e reabrir**

23. Em **Gestos**, deixar raio = 6 e uma política escolhida. File › Save. Fechar o Blender e reabrir `attack_m1.blend`: Action idêntica (conferir no Dope Sheet/Graph Editor), raio e política mantidos, ferramenta funciona (Shift+Alt+K, um grab de teste).
24. **Estatísticas** (N › Animation Sculptor › Estatísticas, fechado por padrão): depois de alguns gestos, ler "Último mouse move" (meta < 16 ms), "Pré-cálculo de P(f)" e frames, "Refresh ao soltar" e "Trails: N alvo(s)… (engine)"; anotar os números.

**O que NÃO deve mudar em nenhum passo:** o número de keys no Dope Sheet (exceto o que você keyar de propósito), os frames das keys fora do retime, outros objetos, o arquivo original `attack_test.blend` em disco.

**Se algo falhar, anotar:** o passo, o texto do header ou do console (Window › Toggle System Console), o bone e o frame, e se reproduz após reiniciar o Blender.

### Variante: seu personagem (opcional, sem salvar)

Abrir o seu `.blend` Rigify com uma animação já bloqueada (File › Open; **não** salvar ao final, ou usar Save As antes). Repetir os passos 4–6, 7, 10, 13, 14, 16, 18 e 19 com a mão IK do golpe; conferir que o rig aparece como `rigify` no painel e que um controle FK é recusado (passo 12). Descartar com File › Revert.

### Resultado do M1 (preencher)

- **Data:**
- **Build/versão:** 0.3.0
- **Personagem usado:** `attack_test.blend` (Vale) / outro: ______
- **Decisão de spacing:** PRESERVE_PATH / PRESERVE_SMOOTHNESS — motivo: ______

| Passo | ✔/✘ | Observação |
|---|---|---|
| 1–3 Preparação | | |
| 4 Ativar ferramenta (toolbar / Shift+Alt+K) | | |
| 5 Trails e info do rig | | |
| 6 Hover | | |
| 7 Grab | | |
| 8 Soft grab (roda / `[ ]`) | | |
| 9 Raio e falloff no painel | | |
| 10 Arc | | |
| 11 Arc com B | | |
| 12 Recusa (FK sem Ctrl) | | |
| 13 Retime 16 → 14 e limites | | |
| 14 Spacing | | |
| 15 Cor Speed | | |
| 16 Política de spacing | | |
| 17 Escopo do tempo | | |
| 18 Breakdowner / Push / Relax / Blend | | |
| 19 Playback (overlay escondido) | | |
| 20 Ctrl+Z por gesto e Esc | | |
| 21 Edição no Graph Editor | | |
| 22 G + I com Tweak | | |
| 23 Salvar, fechar, reabrir | | |
| 24 Estatísticas (números) | | |

**Avaliação qualitativa:**

1. Consegui melhorar o ataque sem usar o Graph Editor?
2. O que faltou?
3. O que irritou?

## M2 — Recusas e casos-limite (Escopo 1, 10 min)

Toda recusa mostra um **anel vermelho** no ponto e `Animation Sculptor · recusado: <motivo>` no header (mais um warning no console); nada é alterado e o aviso some quando o hover vai para outro ponto. Usar o `attack_test.blend` (cópia salva com outro nome) e desfazer cada preparação depois.

1. **Driver**: adicionar um driver em `location` de um controle (botão direito no campo › Add Driver); grab nele recusa com "canal com driver".
2. **NLA**: empurrar a Action para uma faixa NLA (Dope Sheet › Action Editor › Push Down); qualquer gesto recusa com "NLA ativa".
3. **Modificador de F-Curve**: no Graph Editor, adicionar um modificador (ex.: Noise) numa curva de `location`; recusa com "F-Curve com modificador".
4. **Segmento LINEAR**: no Graph Editor, interpolação Linear num segmento (T › Linear); arc drag nesse segmento recusa com "segmento LINEAR" (spacing idem).
5. **Eixo travado**: em Bone › Transform, travar um eixo de `location` (cadeado); o grab move só nos eixos livres e o arc lista os eixos recusados no header.
6. **Controle FK**: grab (sem Ctrl) em `hand_fk.L` recusa com "controle só de rotação…"; Ctrl+arrastar (retime/spacing) funciona.
7. **Bone MCH/ORG/DEF**: selecionar um bone `MCH-*` (coleções ocultas): "não é um controle do rig (MCH/ORG/DEF)".
8. **Sem Action / frame sem key**: objeto sem animação: "sem Action (keye a primeira pose com I)"; ponto de um frame sem key de `location`: recusa com o motivo.
9. Armature não-Rigify simples: o painel mostra o adapter `generic` e o grab funciona.
10. Trocar de arquivo (File › Open outro `.blend`) com a ferramenta ativa: sem erro no console; a ferramenta continua selecionável.

## M3 — Export manual para Godot (Escopo 1, com ferramentas nativas; 15 min)

1. File › Export › glTF: GLB, Animation ✔ (Actions), Sampling ✔, Armature › "Export Deformation Bones Only" ✔.
2. Importar no Godot 4.7.2: Skeleton3D com `DEF-*`, AnimationPlayer com a animação; tocar e comparar visualmente.
3. Anotar problemas (escala, B-Bones, root). Alimenta o Escopo 2.

## M4 — Pipeline automatizado (Escopo 2)

_(a escrever no Escopo 2)_

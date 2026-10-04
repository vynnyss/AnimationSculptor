# Agenda

> Backlog operacional orientado a resultado. Não é arquitetura. Atualizar ao fim de cada sessão significativa. Itens grandes; detalhe técnico mora em `design/`.

## Agora — início do Escopo 1

1. ~~Esqueleto do repositório~~ — mergeado (PR #2).
2. **[mergeado — PR #3] Assets de teste reproduzíveis**: `scripts/make_test_assets.py` (`dev.py assets`) gera `tests/assets/local/attack_test.blend` a partir do personagem Rigify local do usuário (fora do repo público), com Action `asc_test_attack` em key poses literais; testes de Blender que pulam sem o asset. *Resultado: animação de ataque determinística para trails/sculpt, sem tocar no arquivo do usuário.*
3. **[mergeado — PR #4] Vendorizar LMP** com patches P1–P5 + `trails/provider.py`; trails aparecendo nos controles do rig de teste a partir do painel do Animation Sculptor. *Resultado: visualização funcionando dentro do nosso addon (feito: `trails/lmp/` + façade, toggle "Mostrar trails", 8 testes no rig público gerado, verificação visual na GUI).*
4. **[mergeado — PR #5] Spike de interação** (ADR 0010): tool + gizmo hover + modal drag + 1 undo por gesto no rig de teste. *Resultado: ADR 0010 confirmado (opção 3, sem fallback). Feito: `interaction/` (tool, gizmo, overlay, picking, grab modal), `anim/spaces.location_space` (corrige a fórmula de `P(f)`), harness `dev.py test ui`, 23 testes de Blender + 18 checagens de UI.*

5. **[em revisão — PR `fix/grab-autokey-live-trail`] Ajustes do grab após teste do mantenedor**: edição sempre gravada como keyframe (insere key/cria F-Curve de `location` quando falta), trail prevista ao vivo (prefetch de `P(f)`), refresh síncrono da trail ao soltar, gesto nunca fica pendurado. *Resultado: arrastar → soltar mostra a trail nova sem I/Refresh.*

6. **[em revisão — PR `feat/core-bezier-action-io`] `core/` + `anim/`**: `core/fcurve_model`, `core/bezier` (porte da avaliação do Blender 5.2, paridade bit a bit), `core/sculpt_ops.grab_key`, `anim/action_io`, `anim/snapshot`; grab migrado (dívida do spike resolvida; preview ao vivo avaliado com `core.bezier` vetorizado); **bug das trails após edição nativa corrigido** (patch P7 do LMP). *Resultado: matemática do sculpt testável fora do Blender e idêntica ao `FCurve.evaluate`.*

7. **[em revisão — PR `feat/spaces-rig-adapters`, empilhado sobre #7] `rig/` + `anim/spaces`**: adapters Rigify e genérico validados contra o rig gerado (e o personagem local); `P(f)` com prefetch e detecção de espaço constante; a tool recusa não-controles e controles só de rotação; painel mostra rig/adapter/conceito. *Resultado: o gesto só age em controles de translação reconhecidos; P(f) custa 0,69 ms/frame no Rigify.*

## Próximo — completar o Escopo 1

- Asset **público** para o CI — **parcialmente atendido**: `tests/blender/public_rig.py` gera em tempo de teste um rig Rigify público (metarig Human → generate) com a Action `asc_public_test` (4 controles, frames 1/12/24) e os testes de trails já rodam no CI com ele. Falta: ataque completo (key poses próprias para as proporções do metarig) e mesh simples, se algum teste precisar.
- ~~`core/bezier` + `core/fcurve_model` com paridade com `FCurve.evaluate`~~ — feito (PR `feat/core-bezier-action-io`): 300 curvas aleatórias × 801 tempos, erro máximo 0 (bit a bit).
- ~~`anim/action_io` (slotted actions) + `anim/snapshot`~~ — feito (mesmo PR).
- ~~`anim/spaces` (`P(f)` com prefetch e detecção de constante)~~ — feito [em revisão — PR `feat/spaces-rig-adapters`, empilhado sobre #7].
- ~~`rig/` adapters Rigify e genérico, validados contra o rig gerado~~ — feito [em revisão — PR `feat/spaces-rig-adapters`, empilhado sobre #7].
- Grab + soft grab; Arc drag; preview analítico; recusas com motivo e overlay (próximo).
- Retime e Spacing (escopo personagem) + cor de velocidade.
- Painel (trails, ferramenta, breakdowner/push/relax nativos), preferências, keymap.
- Checklist manual "Bloqueio de ataque" executado pelo usuário; feedback → agenda.

## Depois

- Escopo 2: pipeline Godot (validação, bake opcional, preset glTF, root motion, teste headless) + **Loop parte 1** (marcar Action cíclica, "Fechar loop", export como loop) — pedido do mantenedor em 2026-10-03.
- Escopo 3: smooth, make arc, pins, tangent handles, ranges, retime com stretch, **Loop parte 2** (trail fechada, edição propagada nas pontas).
- Escopo 4: FK sculpt com quaternions, trails IK/FK, snapping Rigify.

## Investigação


- Confirmar no Blender 5.2 real os itens restantes de [development/blender-5.2-notes.md](development/blender-5.2-notes.md) (nomes de opções glTF). Channelbag/slots/Rigify, gizmo `test_select` e `WorkSpaceTool`: ✅ 2026-10-03.
- Política de spacing `PRESERVE_PATH` vs `PRESERVE_SMOOTHNESS` — decidir com o usuário testando o protótipo; registrar ADR.
- ~~Comportamento de `fcurve.update()` com handles `ALIGNED` escritos por nós~~ — ✅ 2026-10-03: `update()` mantém handles `ALIGNED` escritos colineares (`test_aligned_handles_written_collinear_survive_update`).
- ~~Custo de `P(f)` por frame via frame stepping no rig Rigify (ms/frame)~~ — ✅ 2026-10-03: 0,69 ms/frame no `hand_ik.R` do personagem (40 frames; meta < 5 ms); o prefetch de uma trail inteira custa ~28 ms, e a detecção de constante evita o frame stepping quando o espaço não muda. Em aberto: custo de frame completo do gesto (reavaliação do Rigify + redesenho), pois o 0,19 ms medido no spike é só do operador.
- GameRig e Rigodotify funcionam no 5.2? (antes do Escopo 2).
- Ler Ciccone et al. 2019 na íntegra (antes do Escopo 4).
- Obter (ou não) o Motion Sculpt da JB FX como referência de UX/código GPL.

## Decididas

- 2026-10-03: nome de exibição **Animation Sculptor**, ID `animation_sculptor`; Godot alvo **4.7.2**; repositório `vynnyss/AnimationSculptor`; todo trabalho entra por PR para `main`, aprovado pelo mantenedor após os testes dele ([workflow](development/workflow.md)).

## Bugs

_(nenhum aberto)_ — corrigido nesta branch: trail não atualizava após edição nativa (G + I, Graph Editor) até o Refresh; patch P7 do LMP (Action nas dependências do alvo e `depsgraph_changed` aceita updates de Action). Regressão: `tests/ui/scenario_native_edit_refresh.py` (erro 0,154 m → 0,0) e `test_action_update_invalidates_trail`.

## Dívida técnica

- ~~Spike: acesso a F-Curves em `interaction/sculpt_tool.py`~~ — resolvida (PR `feat/core-bezier-action-io`): migrou para `core/` + `anim/action_io` + `anim/snapshot`.
- ~~`location_space` devolve `P` só para o frame avaliado atual; o prefetch de `P(f)` do grab ainda mora em `sculpt_tool.py`~~ — resolvida (PR `feat/spaces-rig-adapters`): `anim/spaces.prefetch` + `is_space_constant`; `location_space` segue válido só para o frame atual, por desenho.
- Adapter genérico sem conceitos e sem heurística de FK vs IK: qualquer bone com `location` livre é controle de translação. Suficiente para a iteração 1; humanoides não-Rigify (Mixamo etc.) ficam para depois do MVP.
- Testes de UI só rodam localmente (precisam de display); sem cobertura de GUI no CI.
- O CI agora roda os testes de trails no rig público gerado, mas os testes do asset de ataque (Vale) continuam só locais (pulam no CI). Resolver com um ataque completo no rig público (Agenda › Próximo).
- Key poses do ataque são literais locais do rig do Vale: outro personagem Rigify com proporções diferentes gera poses estranhas (o script falha se faltar algum controle, mas não valida plausibilidade).

# Agenda

> Backlog operacional orientado a resultado. Não é arquitetura. Atualizar ao fim de cada sessão significativa. Itens grandes; detalhe técnico mora em `design/`.

## Agora — início do Escopo 1

1. ~~Esqueleto do repositório~~ — mergeado (PR #2).
2. **[mergeado — PR #3] Assets de teste reproduzíveis**: `scripts/make_test_assets.py` (`dev.py assets`) gera `tests/assets/local/attack_test.blend` a partir do personagem Rigify local do usuário (fora do repo público), com Action `asc_test_attack` em key poses literais; testes de Blender que pulam sem o asset. *Resultado: animação de ataque determinística para trails/sculpt, sem tocar no arquivo do usuário.*
3. **[mergeado — PR #4] Vendorizar LMP** com patches P1–P5 + `trails/provider.py`; trails aparecendo nos controles do rig de teste a partir do painel do Animation Sculptor. *Resultado: visualização funcionando dentro do nosso addon (feito: `trails/lmp/` + façade, toggle "Mostrar trails", 8 testes no rig público gerado, verificação visual na GUI).*
4. **[mergeado — PR #5] Spike de interação** (ADR 0010): tool + gizmo hover + modal drag + 1 undo por gesto no rig de teste. *Resultado: ADR 0010 confirmado (opção 3, sem fallback). Feito: `interaction/` (tool, gizmo, overlay, picking, grab modal), `anim/spaces.location_space` (corrige a fórmula de `P(f)`), harness `dev.py test ui`, 23 testes de Blender + 18 checagens de UI.*

5. **[em revisão — PR `fix/grab-autokey-live-trail`] Ajustes do grab após teste do mantenedor**: edição sempre gravada como keyframe (insere key/cria F-Curve de `location` quando falta), trail prevista ao vivo (prefetch de `P(f)`), refresh síncrono da trail ao soltar, gesto nunca fica pendurado. *Resultado: arrastar → soltar mostra a trail nova sem I/Refresh.*

## Próximo — completar o Escopo 1

- Asset **público** para o CI — **parcialmente atendido**: `tests/blender/public_rig.py` gera em tempo de teste um rig Rigify público (metarig Human → generate) com a Action `asc_public_test` (4 controles, frames 1/12/24) e os testes de trails já rodam no CI com ele. Falta: ataque completo (key poses próprias para as proporções do metarig) e mesh simples, se algum teste precisar.
- `core/bezier` + `core/fcurve_model` com paridade com `FCurve.evaluate` (teste de integração).
- `anim/action_io` (slotted actions) + `anim/snapshot` + `anim/spaces` (`P(f)` com prefetch e detecção de constante).
- `rig/` adapters Rigify e genérico, validados contra o rig gerado.
- Grab + soft grab; Arc drag; preview analítico; recusas com motivo.
- Retime e Spacing (escopo personagem) + cor de velocidade.
- Painel (trails, ferramenta, breakdowner/push/relax nativos), preferências, keymap.
- Checklist manual "Bloqueio de ataque" executado pelo usuário; feedback → agenda.

## Depois

- Escopo 2: pipeline Godot (validação, bake opcional, preset glTF, root motion, teste headless).
- Escopo 3: smooth, make arc, pins, tangent handles, ranges, retime com stretch.
- Escopo 4: FK sculpt com quaternions, trails IK/FK, snapping Rigify.

## Investigação


- Confirmar no Blender 5.2 real os itens restantes de [development/blender-5.2-notes.md](development/blender-5.2-notes.md) (nomes de opções glTF). Channelbag/slots/Rigify, gizmo `test_select` e `WorkSpaceTool`: ✅ 2026-10-03.
- Política de spacing `PRESERVE_PATH` vs `PRESERVE_SMOOTHNESS` — decidir com o usuário testando o protótipo; registrar ADR.
- Comportamento de `fcurve.update()` com handles `ALIGNED` escritos por nós (corrige ou não?).
- Custo de `P(f)` por frame (`location_space` exige o frame avaliado; para o preview analítico precisa de frame stepping) no rig Rigify de teste (ms/frame) — define estratégia de prefetch. Medir também o custo de frame completo do gesto (reavaliação do Rigify + redesenho), pois o 0,19 ms medido no spike é só do operador.
- GameRig e Rigodotify funcionam no 5.2? (antes do Escopo 2).
- Ler Ciccone et al. 2019 na íntegra (antes do Escopo 4).
- Obter (ou não) o Motion Sculpt da JB FX como referência de UX/código GPL.

## Decididas

- 2026-10-03: nome de exibição **Animation Sculptor**, ID `animation_sculptor`; Godot alvo **4.7.2**; repositório `vynnyss/AnimationSculptor`; todo trabalho entra por PR para `main`, aprovado pelo mantenedor após os testes dele ([workflow](development/workflow.md)).

## Bugs

_(nenhum aberto)_

## Dívida técnica

- Spike: o acesso a F-Curves (snapshot, escrita de key+handles, recusas) está em `interaction/sculpt_tool.py`, sem `core/` nem `anim/action_io`. Mover para `core/fcurve_model` + `anim/action_io` + `anim/snapshot` no próximo item (Próximo › `core/bezier` + `fcurve_model`, `anim/action_io`).
- `location_space` devolve `P` só para o frame avaliado atual; o preview analítico precisa de `P(f)` por frame (frame stepping) — estratégia de prefetch no próximo item.
- Testes de UI só rodam localmente (precisam de display); sem cobertura de GUI no CI.
- O CI agora roda os testes de trails no rig público gerado, mas os testes do asset de ataque (Vale) continuam só locais (pulam no CI). Resolver com um ataque completo no rig público (Agenda › Próximo).
- Key poses do ataque são literais locais do rig do Vale: outro personagem Rigify com proporções diferentes gera poses estranhas (o script falha se faltar algum controle, mas não valida plausibilidade).

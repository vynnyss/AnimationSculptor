# Agenda

> Backlog operacional orientado a resultado. Não é arquitetura. Atualizar ao fim de cada sessão significativa. Itens grandes; detalhe técnico mora em `design/`.

## Agora — início do Escopo 1

1. ~~Esqueleto do repositório~~ — mergeado (PR #2).
2. **[em revisão — PR `test/attack-test-assets`] Assets de teste reproduzíveis**: `scripts/make_test_assets.py` (`dev.py assets`) gera `tests/assets/local/attack_test.blend` a partir do personagem Rigify local do usuário (fora do repo público), com Action `asc_test_attack` em key poses literais; testes de Blender que pulam sem o asset. *Resultado: animação de ataque determinística para trails/sculpt, sem tocar no arquivo do usuário.*
3. **Vendorizar LMP** com patches P1–P5 + `trails/provider.py`; trails aparecendo nos controles do rig de teste a partir do painel do Animation Sculptor. *Resultado: visualização funcionando dentro do nosso addon.*
4. **Spike de interação** (ADR 0010): tool + gizmo hover + modal drag + 1 undo por gesto no rig de teste. *Resultado: decisão confirmada ou fallback registrado.*

## Próximo — completar o Escopo 1

- Asset **público** para o CI: `rigify_humanoid.blend` (metarig Human → generate, mesh simples) + ataque aplicado pelo mesmo script, para que os testes de integração rodem no CI sem o personagem do usuário (as key poses atuais usam valores locais do rig do Vale; o rig gerado do metarig tem proporções diferentes ⇒ poses próprias).
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


- Confirmar no Blender 5.2 real os itens restantes de [development/blender-5.2-notes.md](development/blender-5.2-notes.md) (nomes de opções glTF, gizmo Python `test_select`, `WorkSpaceTool`). Channelbag/slots/Rigify: ✅ 2026-10-03.
- Política de spacing `PRESERVE_PATH` vs `PRESERVE_SMOOTHNESS` — decidir com o usuário testando o protótipo; registrar ADR.
- Comportamento de `fcurve.update()` com handles `ALIGNED` escritos por nós (corrige ou não?).
- Custo de `P(f)` via frame stepping no rig Rigify de teste (ms/frame) — define estratégia de prefetch.
- GameRig e Rigodotify funcionam no 5.2? (antes do Escopo 2).
- Ler Ciccone et al. 2019 na íntegra (antes do Escopo 4).
- Obter (ou não) o Motion Sculpt da JB FX como referência de UX/código GPL.

## Decididas

- 2026-10-03: nome de exibição **Animation Sculptor**, ID `animation_sculptor`; Godot alvo **4.7.2**; repositório `vynnyss/AnimationSculptor`; todo trabalho entra por PR para `main`, aprovado pelo mantenedor após os testes dele ([workflow](development/workflow.md)).

## Bugs

_(nenhum — não há código)_

## Dívida técnica

- Testes do asset de ataque dependem do personagem local ⇒ no CI só os smoke tests rodam. Resolver com o asset público (Agenda › Próximo).
- Key poses do ataque são literais locais do rig do Vale: outro personagem Rigify com proporções diferentes gera poses estranhas (o script falha se faltar algum controle, mas não valida plausibilidade).

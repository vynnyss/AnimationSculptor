# Agenda

> Backlog operacional orientado a resultado. Não é arquitetura. Atualizar ao fim de cada sessão significativa. Itens grandes; detalhe técnico mora em `design/`.

## Agora — início do Escopo 1

1. **Esqueleto do repositório** (PR próprio): `LICENSE` GPL-3, `README.md`, `.gitignore`, `animation_sculptor/` com manifest, `scripts/dev.py` (`link`, `test`, `build`, `validate`), `tests/unit` + `tests/blender` rodando um teste trivial dentro do Blender 5.2 da máquina. *Resultado: extensão vazia instala e os dois tipos de teste rodam com um comando.*
2. **Assets de teste reproduzíveis**: `scripts/make_test_assets.py` gera `rigify_humanoid.blend` (metarig Human → generate, mesh simples) e `attack_test.blend` (key poses de ataque pré-definidas). *Resultado: testes não dependem de arquivo do usuário.*
3. **Vendorizar LMP** com patches P1–P5 + `trails/provider.py`; trails aparecendo nos controles do rig de teste a partir do painel do Animation Sculptor. *Resultado: visualização funcionando dentro do nosso addon.*
4. **Spike de interação** (ADR 0010): tool + gizmo hover + modal drag + 1 undo por gesto no rig de teste. *Resultado: decisão confirmada ou fallback registrado.*

## Próximo — completar o Escopo 1

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

- Confirmar no Blender 5.2 real os itens de [development/blender-5.2-notes.md](development/blender-5.2-notes.md) (assinaturas de channelbag, nomes de opções glTF, gizmo Python `test_select`, `Window.modal_operators`).
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

_(nenhuma ainda)_ — registrar aqui atalhos conscientes tomados durante a implementação.

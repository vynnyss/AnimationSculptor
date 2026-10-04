# Estratégia de testes

> Cinco camadas. Unit tests sozinhos não bastam: o que importa é a ferramenta funcionando dentro do Blender e a animação chegando no Godot.

| Camada | Onde roda | O que cobre | Comando (planejado) | Quando |
|---|---|---|---|---|
| **Unit** | Python comum + numpy + pytest | `core/`: Bézier (paridade), falloff, grab/arc/retime/spacing, solve, rig mapping (com dados fake), serialização de estado | `python scripts/dev.py test unit` | todo commit; segundos |
| **Integração Blender** | `blender --background` + pytest dentro do Blender | Actions/slots/channelbags, F-Curves, `P(f)`, avaliação de pose, adapter Rigify em rig gerado, trails (engine STEP), operadores (via `bpy.ops` com override), undo, save/reload | `python scripts/dev.py test blender` | todo commit que toca `anim/ rig/ trails/ interaction/ pipeline/` |
| **UI (eventos simulados)** | Blender **com janela** + `Window.event_simulate` (`--enable-event-simulate`) | Interação real: hover do gizmo, press/drag/release, undo/redo, Esc, Ctrl+LMB, métricas de custo por mouse move | `python scripts/dev.py test ui` | local, ao tocar `interaction/`; **não roda no CI** (precisa de display) |
| **Manual (workflow)** | Blender 5.2 com UI, humano | Usabilidade real: fazer uma animação | checklist em [manual-tests.md](manual-tests.md) | fim de cada escopo e antes de entregar build |
| **Ponta a ponta Godot** | Blender background + Godot headless | Export + import + posições conferidas | `python scripts/dev.py test godot` | Escopo 2 em diante |

Detalhes: [blender-tests.md](blender-tests.md) (inclui os testes de UI), [godot-export-test.md](godot-export-test.md), assets em [regression-assets.md](regression-assets.md).

## Princípios

1. **Invariantes antes de exemplos.** Cada operação do [modelo](../design/motion-sculpt-model.md#invariantes-viram-testes) tem suas invariantes como testes (incluindo property-based simples com seeds fixas).
2. **Paridade com o Blender.** `core/bezier` é testado contra `FCurve.evaluate` em centenas de curvas geradas (tipos de handle, interpolação, handles sobrepostos) — **feito**: `tests/blender/test_bezier_parity.py`, 300 curvas × 801 tempos, erro máximo 0 (bit a bit).
3. **Assets gerados por script.** `.blend` de teste são reconstruíveis (`scripts/make_test_assets.py`). O asset do personagem do usuário é local (gitignored) e os testes que dependem dele pulam quando ele não existe.
4. **Background ≠ UI.** O native solver do LMP e o desenho exigem janela. Em `--background`: forçar engine `STEP`; desenho testado com `gpu.init()` (novo no 5.2) em offscreen quando valer a pena; interação coberta por testes de operador + checklist manual.
5. **Sem flakiness de tempo.** Nada de `sleep`; chamar `engine.update_now()` síncrono nos testes.
6. **Regressão de bug = teste.** Todo bug corrigido ganha teste na camada mais baixa possível.

## Matriz de cobertura mínima por tema

| Tema | Unit | Blender | Manual |
|---|---|---|---|
| Matemática Bézier/falloff/interp | ✔ | paridade | |
| Manipulação de F-Curves | ✔ (modelo) | ✔ (escrita real, handles, `update()`) | |
| Timing algorithms | ✔ | ✔ (pose-wide em rig real) | ✔ |
| Rig mapping | ✔ (fake) | ✔ (Rigify gerado) | |
| Serialização/estado | ✔ | ✔ (save/reload, undo) | ✔ |
| Pose evaluation / `P(f)` | | ✔ | |
| Motion paths (engine) | | ✔ (STEP) | ✔ |
| Operators / modal | | ✔ (execute) | ✔ |
| Interação (hover, press/drag, undo, cancel) | | ✔ (UI, local) | ✔ |
| UX (hover, feedback) | | ✔ (UI: posição/estado) | ✔ |
| Export/Godot | | ✔ (export) | ✔ | 

## Profiling

Desde a Iteração 1, sem otimizar prematuramente:

- Contadores simples (`time.perf_counter`) em: custo por mouse move do gesto, prefetch de `P(f)` por frame, tick do engine LMP. Exibidos no painel com "Show Statistics" (o LMP já tem a base).
- Teste de integração de performance (não-bloqueante, só registra): gesto sintético de 100 passos no `hand_ik.L` do rig de teste com 240 frames. Meta inicial: < 16 ms por passo; `P(f)` < 5 ms/frame.
- Resultados registrados em `current-state.md` quando mudarem significativamente.

## CI

GitHub Actions (`.github/workflows/tests.yml`), em todo PR para `main`:

- **unit** (obrigatório): Python 3.13, `dev.py test unit` + `scripts/checks.py`.
- **blender**: baixa o Blender 5.2.x mais recente (`dev.py fetch-blender`, cacheado) e roda `dev.py test blender` + `validate`. Obrigatório (confirmado verde em 2026-10-03). Se falhar, o final da saída vira anotação de erro do check (`scripts/ci_annotate.py`).
- Os testes de UI (`dev.py test ui`) **não** rodam no CI: exigem display e janela do Blender. Rodam localmente (mantenedor/agente) antes de declarar pronto algo que toque `interaction/`; os testes de Blender em background cobrem a mesma lógica via `execute`.
- Godot headless entra no Escopo 2.

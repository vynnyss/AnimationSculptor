# Estratégia de testes

> Quatro camadas. Unit tests sozinhos não bastam: o que importa é a ferramenta funcionando dentro do Blender e a animação chegando no Godot.

| Camada | Onde roda | O que cobre | Comando (planejado) | Quando |
|---|---|---|---|---|
| **Unit** | Python comum + numpy + pytest | `core/`: Bézier (paridade), falloff, grab/arc/retime/spacing, solve, rig mapping (com dados fake), serialização de estado | `python scripts/dev.py test unit` | todo commit; segundos |
| **Integração Blender** | `blender --background` + pytest dentro do Blender | Actions/slots/channelbags, F-Curves, `P(f)`, avaliação de pose, adapter Rigify em rig gerado, trails (engine STEP), operadores (via `bpy.ops` com override), undo, save/reload | `python scripts/dev.py test blender` | todo commit que toca `anim/ rig/ trails/ interaction/ pipeline/` |
| **Manual (workflow)** | Blender 5.2 com UI, humano | Usabilidade real: fazer uma animação | checklist em [manual-tests.md](manual-tests.md) | fim de cada escopo e antes de entregar build |
| **Ponta a ponta Godot** | Blender background + Godot headless | Export + import + posições conferidas | `python scripts/dev.py test godot` | Escopo 2 em diante |

Detalhes: [blender-tests.md](blender-tests.md), [godot-export-test.md](godot-export-test.md), assets em [regression-assets.md](regression-assets.md).

## Princípios

1. **Invariantes antes de exemplos.** Cada operação do [modelo](../design/motion-sculpt-model.md#invariantes-viram-testes) tem suas invariantes como testes (incluindo property-based simples com seeds fixas).
2. **Paridade com o Blender.** `core/bezier` é testado contra `FCurve.evaluate` em centenas de curvas geradas (tipos de handle, interpolação, handles sobrepostos).
3. **Assets gerados por script.** `.blend` de teste são reconstruíveis (`scripts/make_test_assets.py`); o binário versionado é cache.
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
| Operators / modal | | ✔ (invoke/execute) | ✔ |
| UX (hover, feedback) | | | ✔ |
| Export/Godot | | ✔ (export) | ✔ | 

## Profiling

Desde a Iteração 1, sem otimizar prematuramente:

- Contadores simples (`time.perf_counter`) em: custo por mouse move do gesto, prefetch de `P(f)` por frame, tick do engine LMP. Exibidos no painel com "Show Statistics" (o LMP já tem a base).
- Teste de integração de performance (não-bloqueante, só registra): gesto sintético de 100 passos no `hand_ik.L` do rig de teste com 240 frames. Meta inicial: < 16 ms por passo; `P(f)` < 5 ms/frame.
- Resultados registrados em `current-state.md` quando mudarem significativamente.

## CI

GitHub Actions (`.github/workflows/tests.yml`), em todo PR para `main`:

- **unit** (obrigatório): Python 3.13, `dev.py test unit` + `scripts/checks.py`.
- **blender**: baixa o Blender 5.2.x mais recente (`dev.py fetch-blender`, cacheado) e roda `dev.py test blender` + `validate`. Marcado `continue-on-error` até passar a primeira vez (não confirmado ainda) — depois vira obrigatório.
- Godot headless entra no Escopo 2.

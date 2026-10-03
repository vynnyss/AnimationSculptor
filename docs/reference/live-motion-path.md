# Live Motion Path & Onion Skin — análise

- Repo: https://github.com/daim1993/blender-live-motion-path
- Commit analisado: `0e173fd` (2026-08-27, "Publish Blender Live Motion Path") — **commit único**, sem histórico, sem testes.
- Licença: **GPL-3.0-or-later** (SPDX em todos os arquivos; `LICENSE` presente). Copyright "2026 Experience Elysian".
- Tamanho: ~3.700 linhas Python. Extension manifest, `blender_version_min = 4.2.0`, verificado contra 5.x.
- Estratégia: **reutilizar diretamente (vendorizar)** — [ADR 0001](../decisions/0001-live-motion-path-foundation.md).

## Arquivos

| Arquivo | Linhas | Conteúdo | Uso no Animation Sculptor |
|---|---|---|---|
| `engine.py` | 1654 | Estratégias de avaliação, caches, alvos, scheduler | **vendorizado** (núcleo das trails) |
| `draw.py` | 633 | Desenho GPU: paths (cores incl. Speed), onion skin (shader próprio ≤128 bytes de push constants), marcadores 2D, números | **vendorizado** |
| `compat.py` | 223 | Diferenças 4.2↔5.x (channelbag, `PoseBone.select`, `Window.modal_operators`) | **vendorizado**, ramos < 5.0 podem ser removidos depois |
| `handlers.py` | 79 | depsgraph/frame/playback/load/undo/redo, `@persistent` | **vendorizado** |
| `props.py` | 362 | `Scene.motion_onion` (todas as opções) | **vendorizado com renomeação** |
| `ops.py` | 254 | refresh, clear cache, bake onion, pins, reset | vendorizado (operadores renomeados) |
| `ui.py` | 457 | Painéis sidebar, botão no header, entradas no popover Overlays | **adaptado**: integrado ao painel do Animation Sculptor |
| `prefs.py` | 53 | aba da sidebar, botão no header | substituído pelas prefs do Animation Sculptor |

## Engine — como funciona

**Alvos** (`resolve_targets`): modo `SELECTED` / `ACTIVE` / `PINNED`. Em Pose Mode, cada bone selecionado vira alvo `(objeto, bone)`; meshes deformadas pela armature viram alvos de onion. Assinatura barata de seleção evita re-resolver a cada redraw.

**Três estratégias de path** (`_choose_path_engine`):

| Engine | Quando | Custo | Observação para nós |
|---|---|---|---|
| `FCURVE` | Objetos com só keys de transform (sem constraints/drivers/NLA/parent não-objeto) | instantâneo | **não se aplica a bones** |
| `NATIVE` | Bones em Pose Mode com ponto HEAD/TAIL; objetos genéricos | rápido | `pose.paths_calculate` via `temp_override` com **window/area** — não roda em `--background` |
| `STEP` | Fallback, ponto CENTER, onion de mesh deformada | lento, mas *time-sliced* | `scene.frame_set` frame a frame; nunca roda durante modal de transform |

Implicação central: **para bones de Rigify não existe caminho barato no LMP**. Native solver por arrasto de mouse é caro demais. Por isso o preview durante o gesto é nosso (analítico via `P(f)`), e o LMP só recalcula ao soltar.

**Cache**: `CACHE[(obj, bone)] → TargetCache` com dicionários `frame → ponto` (bones) / `frame → matriz` (objetos), arrays numpy reconstruídos para desenho, keyframes do alvo, ghosts. Só nomes são guardados entre ticks (nada de referências `bpy` pendentes). Poda LRU simples.

**Dirty state**: `depsgraph_changed` cruza `depsgraph.updates` (transform/geometry) com o conjunto de dependências de cada alvo (`build_deps`: pais, armature, alvos de constraints e modificadores) e limpa só os caches afetados.

**Scheduler**: `schedule(delay)` com geração incremental (debounce), `bpy.app.timers`, `compute_budget` por tick (time slicing), frames mais próximos do playhead primeiro. Pausa em playback. Espera modais de transform (`Window.modal_operators` com prefixos `TRANSFORM_OT_`, `ANIM_OT_`, …).

**Keyframes**: lidos das F-Curves do slot via channelbag, filtrados por prefixo `pose.bones["nome"]`.

**Range**: cena/preview, *around frame*, custom; `MAX_PATH_FRAMES = 6000`; engines baratos pré-calculam a cena toda em modo *around*.

## Desenho

- Só `gpu` + `gpu_extras.batch` (sem `bgl`). `POLYLINE_SMOOTH_COLOR`/`POINT_*` para paths, `UNIFORM_COLOR` para marcadores, `blf` para números.
- Modos de cor: Past/Future, Single, Gradient, **Speed** (distância por frame, normalizada pelo percentil 95) — leitura de spacing que reaproveitamos.
- Marcador do frame atual segue o objeto mesmo durante drag.
- Overlays: respeita toggle de overlays do viewport, *in front*, fade.

## Lacunas para o nosso caso

1. Sem API para "suspender" recomputação durante uma operação externa (só detecta modais do Blender por prefixo) → **patch**: flag `external_edit` checada em `schedule`/`depsgraph_changed`, ou incluir o prefixo do nosso operador na lista de bloqueio.
2. Sem API pública de leitura → façade `trails/provider.py` lê `CACHE` diretamente.
3. Picking/seleção de pontos inexistente (é só visualização) → nosso `interaction/`.
4. Namespace `Scene.motion_onion` e idnames `motion_onion.*` colidem se o usuário instalar o LMP original → **renomear** para `asc_trails`.
5. Native solver deixa `animation_visualization.motion_path` do rig alterado (range/frame_start/end) — efeito colateral persistente no `.blend`. Avaliar restauração dos valores originais (patch).
6. Sem testes; maturidade desconhecida (publicado há ~1 mês). Nossos testes de integração cobrem o que usamos.

## Patches planejados (registrar cada um em [open-source-provenance.md](open-source-provenance.md))

| # | Patch | Motivo |
|---|---|---|
| P1 | Renomear `motion_onion`/`LMO_*`/`motion_onion.*` → `asc_trails`/`ASC_*`/`asc_trails.*` | coexistência com LMP instalado |
| P2 | Imports relativos dentro de `trails/lmp/` | vendorização |
| P3 | Hook `suspend()/resume()` + `invalidate(keys)` | sculpt sem recomputação concorrente |
| P4 | Restaurar `animation_visualization.motion_path` após native solver | não sujar o `.blend` |
| P5 | Remover painéis próprios / header button; expor via nosso `ui/` | UI única |
| P6 | (opcional) remover ramos < 5.0 em `compat.py` | baseline 5.2 |

Manter cada patch pequeno e marcado com `# ASC-PATCH Pn` para facilitar diff com upstream.

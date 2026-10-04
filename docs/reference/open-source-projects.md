# Projetos de referência

> Consultar **antes** de implementar qualquer sistema significativo. Atualizar quando um projeto novo for avaliado. Proveniência de código efetivamente copiado: [open-source-provenance.md](open-source-provenance.md).

## Matriz de decisão

| Projeto | Licença | Estado (out/2026) | Parte relevante | Estratégia |
|---|---|---|---|---|
| [Live Motion Path & Onion Skin](live-motion-path.md) | GPL-3+ | 5.x, publicado ago/2026, sem testes | Engine de trails, cache, scheduler, handlers, GPU, onion, cor de velocidade | **Reutilizar (vendorizar)** |
| [Motion Trail — Bart Crouch](motion-trail.md) | GPL-2+ | 2.80, `bgl` | Grab de key, regras de handle, timing/time beads, speed via `handle.x`, tela⇄mundo | **Portar algoritmos** |
| [Motiontrail3D — W. B. Moss (port 4.1)](editable-motion-trails.md) | GPL-3 | 4.1, `action.fcurves` | `P(f)` espaço-pai por frame, utilitários Bézier, triplets, regras de handle | **Extrair algoritmos**; arquitetura rejeitada |
| [Interactive Motion Path (fork)](interactive-motion-path.md) | GPL-2+ (Blender) | fork 2022, C++/Eigen | Tangent-Space solver, pins, Jacobianos | **Referência → port numpy (Escopo 4)** |
| [BlenderAddonTemplate](https://github.com/j10er/BlenderAddonTemplate) | GPL-3 | set/2025, Blender 4.4/4.5 | `dev.py` (build/test), pytest dentro do Blender, CI | **Adaptar** padrão (não copiar como dependência) |
| [GameRig](https://github.com/Arminando/GameRig) | GPL-2 | fev/2026, Blender 4.5/5.0 | Feature set Rigify com DEF em hierarquia única, sem escala/B-Bones | **Recomendar/usar** no pipeline (não reimplementar) |
| [Rigodotify](https://github.com/catprisbrey/Rigodotify) | MIT | set/2026 | Converte rig Rigify em esqueleto compatível Godot/Unity/Unreal | **Recomendar/usar** no pipeline |
| Blender (nativo) | GPL-2+ | 5.2 LTS | `pose.breakdown/push/relax/blend_to_neighbor`, `graph.ease/blend_*`, `graph.gaussian_smooth`, `graph.butterworth_smooth`, `nla.bake`, `pose.paths_calculate`, exportador glTF, snapping IK/FK do Rigify | **Usar operadores** quando chamáveis do 3D View; **portar algoritmo** quando exigem Graph Editor |

## Outros encontrados (não open-source acessível ou fora de escopo)

| Projeto | Licença / acesso | Por que importa |
|---|---|---|
| **Motion Sculpt V1 — JB FX** (Superhive, US$ 17,99) | GPL-3, código só para compradores | **Mesmo nome e mesma proposta**: soft grab com raio na roda, smooth Relax/Straighten, Make Arc, tangent handles, pins, presets de interpolação. Só canais de `location`. Ótima **referência de UX**; colisão de nome (ver [agenda](../agenda.md#investigação)). Por ser GPL, o código poderia ser reutilizado se obtido legitimamente. |
| *Motion Sculpting: A New Animation Paradigm* — Nacho de Andrés, BCON26 ([video.blender.org](https://video.blender.org/w/66d78fe0-0211-4067-b133-88c3f77eb7de), [YouTube](https://www.youtube.com/watch?v=M2J_fQNLDfg)) | palestra; código não publicado (busca em 2026-10-04) | Rig **descartável**: IK temporário sobre um esqueleto FK denso, janela de tempo com falloff, keys em todo frame; régua de tempo vermelho/verde no viewport, toolbar flutuante, spline de movimento. **Referência de ideia e UX** para o [rig efêmero](../design/ephemeral-rig.md). |
| Motion Path Ultimate — Hoa Vu (Superhive, US$ 10) | GPL, pago | Edição com gizmos G/R/S, proporcional, smooth/spacing/redução de keys; Blender 5.0–5.1. Referência de features. |
| Motion Path Pro / Real-time Paths — Hamdi Amer (extensions.blender.org) | GPL-3+ | Paths em tempo real + handles editáveis (5.0+). Review relata lag com handles em modelos complexos — confirma o risco de performance. Fonte acessível via extensions platform; avaliar se surgir necessidade. |
| Easy Motion Trail, QuickPath | pagos/variados | Visualização/edição simples; nada além do já coberto. |
| AnimAide (aresdevo) | GPL | Ferramentas de F-Curve (ease, blend, offset). Hoje boa parte existe nativamente no Graph Editor (sliders do 4.x). Consultar se precisarmos de operações de curva que o Blender não tem. |

## Conclusões da análise

1. **Fundação de trails** existe e é moderna (LMP). Não reimplementar cache/scheduler/GPU.
2. **Edição de trail** não existe em forma moderna e reutilizável: Motion Trail é antigo e limitado, Motiontrail3D tem arquitetura frágil, IMP é fork. Os **algoritmos** são reutilizáveis; a camada de interação é nossa.
3. **Bones de Rigify não têm caminho barato de avaliação** no LMP ⇒ precisamos de preview analítico próprio durante o gesto (`P(f)` + Bézier em numpy).
4. **Controles de translação são lineares** ⇒ o primeiro escopo não precisa de otimizador.
5. **Rigify FK usa quaternions** e o fork Tangent-Space só suporta Euler ⇒ FK sculpt exige trabalho novo (Escopo 4).
6. **Export de Rigify para engines** já tem soluções (GameRig, Rigodotify, opções do glTF) ⇒ não construir conversor de esqueleto.
7. **Muitas operações temporais existem nativas** (breakdowner, ease/blend, smooth) ⇒ expor/portar em vez de inventar.

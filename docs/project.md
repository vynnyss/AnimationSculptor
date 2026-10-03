# Projeto — Animation Sculptor para Blender 5.2

> Fonte concisa de verdade. Não é histórico. Mudou o escopo? Edite este arquivo e registre um ADR.

## Objetivo

Ferramenta **determinística** de *Motion Sculpting* para Blender 5.2, focada em **animação de personagens humanoides**. O animador vê o movimento no espaço e no tempo (trajetórias no viewport) e o edita diretamente: arrasta pontos da trajetória, esculpe arcos, altera timing e spacing, suaviza — sem alternar o tempo todo com o Graph Editor.

O resultado é sempre **animação Blender convencional**: uma Action com F-Curves normais no control rig, editável no Graph Editor/Dope Sheet, que pode ser "bakeada" para os deform bones e exportada via glTF para o Godot. O Godot não sabe que o Animation Sculptor existiu.

```
Animation Sculptor → Blender Action → F-Curves → Rigify control rig → Bake → deform bones → glTF → Godot
```

## Escopo

O usuário deve conseguir, com um humanoide rigado (preferencialmente Rigify):

1. criar key poses numa Action normal;
2. visualizar trajetórias (motion trails) e spacing no viewport;
3. manipular diretamente trajetórias: mover pontos, esculpir arcos, suavizar;
4. alterar timing (mover poses no tempo) e spacing (easing entre poses);
5. trabalhar com controles IK e FK;
6. fazer bake para os deform bones e exportar glTF;
7. importar a animação no Godot sem nada específico do Animation Sculptor.

Teste de aceitação do MVP: **uma animação de ataque completa** (idle → antecipação → ataque → impacto → follow-through → recuperação) num humanoide Rigify, editada com Animation Sculptor, bakeada e importada corretamente no Godot.

## Não objetivos (primeiro ciclo)

- IA, LLM, machine learning, geração automática de animação.
- Rig próprio, auto-rigging próprio, substituição do Rigify.
- Criaturas / não-humanoides.
- Runtime ou plugin no Godot; formato próprio de animação.
- Compatibilidade com Blender < 5.2.
- Fork do Blender ou extensão nativa (C/C++) — ver [ADR 0005](decisions/0005-extension-not-fork.md).

## Alvos

| Item | Alvo |
|---|---|
| Blender | **5.2 LTS** (baseline único) — [ADR 0004](decisions/0004-blender-5.2-baseline.md) |
| Formato de distribuição | Blender Extension (`blender_manifest.toml`), Python puro + numpy (já embarcado no Blender) |
| Rig suportado | **Rigify** (humanoide gerado do metarig "Human"), via *Rig Adapter* — [ADR 0002](decisions/0002-rigify-first-rig-adapter.md) |
| Saída | Action/F-Curves nativas — [ADR 0003](decisions/0003-native-blender-animation-output.md) |
| Destino | glTF 2.0 (exportador oficial do Blender) → **Godot 4.7.2** |
| Licença | **GPL-3.0-or-later** (obrigatória pelo código reutilizado) — [ADR 0007](decisions/0007-gpl-and-reuse-policy.md) |
| Fluxo de trabalho | PRs para `main`; o mantenedor testa e faz o merge — [development/workflow.md](development/workflow.md) |

## Filosofia

**Determinística.** Mesma entrada + mesma operação = mesma F-Curve. Sem heurística estatística, sem aleatoriedade. Toda operação de sculpt é uma função matemática documentada em [design/motion-sculpt-model.md](design/motion-sculpt-model.md) e coberta por teste unitário.

**Reutilizar antes de implementar.** Antes de qualquer sistema significativo: (1) consultar [reference/open-source-projects.md](reference/open-source-projects.md); (2) verificar se já existe — inclusive como operador nativo do Blender; (3) decidir entre reutilizar, adaptar, portar, extrair algoritmo ou só referenciar; (4) implementar do zero só sem alternativa. Registrar em [reference/open-source-provenance.md](reference/open-source-provenance.md).

**Workflow antes de features.** Cada entrega tem que permitir *fazer uma animação*, não testar uma função isolada.

**Nada de estado frágil.** O único estado persistente é a Action (mais configurações de UI na cena). Trails, caches e seleção de pontos são derivados e podem ser descartados a qualquer momento (undo, reload, troca de arquivo).

## Nome

- Nome de exibição: **Animation Sculptor**. ID da extensão e pacote Python: **`animation_sculptor`**. Repositório: https://github.com/vynnyss/AnimationSculptor
- "Motion sculpting" continua sendo o nome do *conceito*. Evitamos "Motion Sculpt" como nome de produto porque existe um addon comercial homônimo (JB FX) — ver [reference/open-source-projects.md](reference/open-source-projects.md).

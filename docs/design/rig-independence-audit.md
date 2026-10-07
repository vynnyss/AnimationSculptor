# Auditoria: ferramentas × Rigify (modelo efêmero)

> Auditoria **só de documentação** (2026-10-07), feita sobre a `main` em `7a7fb7d` (0.9.0, depois do #21). Origem: um prompt de "migração das ferramentas legadas do Rigify para o modelo efêmero", analisado contra o código. Nenhuma mudança de código aqui. As propostas abaixo dependem de decisão do mantenedor; cada uma vira um PR próprio.

## Conclusão

A dependência do Rigify **já está confinada a `rig/`**:

- A [ADR 0014](../decisions/0014-skeleton-first.md) pôs o Rigify em segundo plano e o congelou.
- O `scripts/checks.py` (`check_no_bone_names_outside_rig`) roda no CI e reprova qualquer nome de bone fora de `rig/`.
- Fora de `rig/`, "Rigify" só aparece em comentários e textos de ajuda (`ui/props.py`, `anim/spaces.py`, `core/kinematics.py`, `interaction/ephemeral_edit.py`).

O que sobra não são nomes. É um **vazamento de conceito**: o tipo `IK` que o adapter devolve faz a ferramenta escolher entre dois caminhos (ver "Vazamentos"). A maior parte do que o prompt pedia para "migrar" já segue o modelo efêmero.

## Fluxo atual (encontrado no código)

```
gizmo (hover)  ── modo Corpo: body_pick.pick → RigAdapter.control_for_deform → (controle, CHAIN | IK)
               └─ modo Trail: ponto da trail (provider) ou ponta do bone selecionado
        ↓
ASC_OT_sculpt_gesture.invoke  (interaction/sculpt_tool.py: roteia por ferramenta e por edit.kind)
        ↓
Edit: ChainEdit / RotateEdit / TrailSmoothEdit (ephemeral_edit) · SmoothEdit · _GrabEdit / _ArcEdit · RetimeEdit / SpacingEdit
        ↓
core/ (ephemeral, kinematics, solve, pose_keys | dense, sculpt_ops, smooth, timing_ops) — sem bpy
        ↓
anim/action_io → Action (pose a pose ou densa: ADR 0015)
```

O adapter só **responde perguntas** (`classify`, `ephemeral_chain`, `ephemeral_pins`, `ephemeral_aim`, `body_override`, `control_for_deform`). Ele nunca escreve animação.

## Ferramenta por ferramenta

| Ferramenta | Onde | Estado | Classificação |
|---|---|---|---|
| Grab no corpo (Ponta/Membro/Corpo) | `ChainEdit` | Rig efêmero, janela da régua, falloff, pinos, `key_mode` e `pose_influence` (ADR 0015) | **já migrado** |
| Soft Grab "temporal" no corpo | `ChainEdit` | É o próprio `ChainEdit`: o deslocamento desejado na janela, com falloff, resolve a cadeia | **já migrado** |
| Grab / Soft Grab de translação | `_GrabEdit` (`sculpt_tool.py`) | Move keys de `location` existentes. Serve root/hips do esqueleto simples e controles IK do Rigify. **Não depende do Rigify** | **manter** (é o caminho de translação, não legado) |
| Arc Drag | `_ArcEdit` + `core/sculpt_ops.arc_drag` | Bézier de `location`, solução exata, keys e timing intactos. Só em controles que transladam | **manter**; a versão para cadeias de rotação precisa de decisão (abaixo) |
| Smooth | `TrailSmoothEdit` (modo Trail, padrão) / `SmoothEdit` (modo Rotações) | O modo Trail já suaviza o caminho no mundo e resolve o membro. O modo Rotações é por canal, por opção | **já migrado** |
| Girar | `RotateEdit(ChainEdit)` | Janela, falloff, modo de key | **já migrado** |
| Breakdowner / Push / Relax / Blend to Neighbor | `ui/panels.py` → `pose.breakdown`, `pose.push`, `pose.relax`, `pose.blend_to_neighbor` | Operadores nativos sobre os **bones selecionados**. Não é Rigify, mas depende de seleção | **lacuna**: versão por parte do corpo |
| Retime / Spacing | `timing_edit.scope_fcurves`, `core/timing_ops` | Escopos `CHARACTER` / `SELECTED` (filtro por `data_path`). Algoritmos independentes do rig | **adaptar só o escopo** |
| Tecla I (`asc.key_pose`) | `sculpt_tool.py` | Grava a pose inteira nos controles do adapter | **já genérico** |

## Vazamentos

1. **`kind == IK`**: `interaction/sculpt_tool.py` (invoke: `if hit.kind == rig.IK`) e `interaction/gizmo.py` (texto do header). Quando o adapter diz que a parte é um controle IK, a ferramenta faz grab/arco nas F-Curves de `location` daquele controle. Proposta: o adapter devolve o **tipo de gesto** em termos genéricos (por exemplo `TRANSLATE`, "translada este controle", e `CHAIN`, "gira esta cadeia"). A ferramenta deixa de saber que existe IK. Só o `RigifyAdapter` (e um futuro adapter com IK) usa `TRANSLATE` para partes do corpo.
2. **`RigAdapter.ik_fk_state(arm_ob, 'arm.L')`** na interface base: os nomes de membro (`'arm.L'`, `'leg.R'`) são vocabulário do Rigify, e ninguém chama o método fora de `rig/`. Proposta: torná-lo um detalhe interno do `RigifyAdapter`.
3. **Comentários** que citam o Rigify como exemplo (`MCH-hand_fk`, `DEF-spine`) em `core/` e `anim/`: inofensivos e úteis como exemplo. Não precisam mudar.

## Pontos que precisam de decisão (não são migração)

### Arc em cadeias de rotação

Numa cadeia de rotação, a trajetória da mão entre duas keys **não é uma Bézier de posição**. Para fazer o movimento passar por um ponto sem criar key, seria preciso otimizar os handles das rotações. Isso é o Tangent-Space, adiado pela [ADR 0006](../decisions/0006-tangent-space-deferred.md). As opções:

- **(a)** Em pose a pose, o "arco" num in-between cria uma pose ali. É o comportamento atual do `ChainEdit` num frame sem key, mas muda a estrutura de poses.
- **(b)** Em `DENSE`, já é o `ChainEdit`.
- **(c)** Otimizar os handles das rotações para seguir a trajetória desejada, mantendo keys e timing. É o caminho do Tangent-Space e também a base de um futuro Tangent Sculpt.

Preservar keys e timing **e** resolver pelo rig efêmero só é possível com (c).

### Escopo de tempo por parte

Retime e spacing por parte (Membro, Corpo) custam pouco: `scope_fcurves` passaria a usar `RigAdapter.ephemeral_chain`. Mas pela [ADR 0015](../decisions/0015-pose-to-pose-keys.md), pose-chave é **qualquer frame com key em algum canal**. Retimar só um braço cria poses novas para o resto do corpo e muda os frames em que o próximo arrasto escreve. É preciso decidir entre aceitar isso ou restringir as poses-chave ao escopo do gesto.

### MotionTarget

Não proposto como hierarquia de classes. Os alvos já existem sem nome:
- `ChainEdit.apply(delta, target=...)`: posição por frame;
- `ephemeral.Pin`: restrição;
- `RotateEdit`: orientação;
- `TrailSmoothEdit`: trajetória suavizada.

A duplicação real está no roteamento do `sculpt_tool.py` (~1300 linhas, decisões por `edit.kind` em string no `invoke`, no `modal` e no `_end`). Se houver refatoração, o ganho maior é um **protocolo comum de edição** (`editable`, `apply`, `preview`, `restore`, `finish`, mais as capacidades: raio, `B`, tecla R…) e uma tabela de roteamento.

## Fora do escopo (por decisão anterior)

- Paridade de recursos no Rigify: congelado pela ADR 0014 (IK/FK, snapping e bake só se o mantenedor pedir). Testes "mesma operação no Rigify e no genérico" devem comparar **propriedades** (ponto sob o cursor, nada muda fora da janela, pés parados), não posições: o rig público e o esqueleto simples têm proporções diferentes.
- Smooth por velocidade, aceleração ou jerk, e Rotation Trail: futuro, sem pedido.

## Ordem sugerida (um PR cada, depois da aprovação)

1. Vazamentos 1 e 2: tipo de gesto genérico vindo do adapter; `ik_fk_state` só no `RigifyAdapter`. Testes: a interação não importa `IK`; o Rigify continua com grab/arco nos controles IK.
2. Breakdown / Push / Relax por parte do corpo (picking + `ephemeral_chain(LIMB)` + `core/pose_keys`), sem depender de seleção.
3. Escopo de tempo por parte, depois da decisão sobre poses-chave.
4. Arc em cadeias de rotação: ADR escolhendo entre (a), (b) e (c).
5. (Opcional) Protocolo comum de edição no `sculpt_tool.py`, sem mudar comportamento.

# 0015 — Pose a pose como padrão; keys densas viram opção; modos Corpo e Trail separados

- Status: aceito (2026-10-05, decisões do mantenedor; implementado na 0.9.0). Substitui em parte a [ADR 0011](0011-ephemeral-rig-dense-keys.md) (as keys densas deixam de ser o padrão) e ajusta a [ADR 0013](0013-body-and-trail-interaction.md) (cada modo só agarra o que é dele).
- Data: 2026-10-05

## Contexto e problema

Com a 0.9.0 o mantenedor fez um walk cycle arrastando o corpo e relatou que "as animações estão saindo de controle muito rápido, mesmo com smooth nas trails".

- **Keys densas:** cada arrasto grava uma key por frame em toda a janela da régua. Arrastos seguidos com janelas largas se sobrepõem e reescrevem os mesmos frames. O resultado é uma timeline cheia de keys e um movimento difícil de controlar.
- **Pedido do mantenedor:** voltar a algo como "aperto I para definir um keyframe". Esse frame é a pose daquele frame, e os arrastos feitos em outros frames mexem pouco nele.
- **Modos misturados:** no modo Corpo as trails também eram agarráveis (0.8.0). Com isso, um gesto de corpo podia pegar a trail sem querer, e o mantenedor pediu para separar as ferramentas de corpo das de trail.

## Opções consideradas

1. Manter as keys densas e só limitar a janela às poses-chave.
2. **Pose a pose**: o arrasto muda só a pose do frame atual, com uma key por canal ali. As poses vizinhas mudam pouco, e o Blender interpola entre as poses.
3. As duas, com uma opção.

## Decisão

Opção 3, com pose a pose como padrão (decisões do mantenedor, 2026-10-05):

- **`Scene.asc_sculpt.key_mode`**: `POSE` (padrão) ou `DENSE`, na barra da ferramenta e em Parâmetros.
- **Pose a pose** (`core/pose_keys.write_keys`):
  - **Frames escritos:** o frame do arrasto e as **poses-chave do personagem** dentro da janela da régua (todo frame que tem key em algum canal da Action).
  - **Pesos:** o frame do arrasto tem peso 1. As outras poses têm o falloff da régua × **Influência nas poses** (`pose_influence`, padrão 25%; 0 = travadas).
  - **Keys:** uma key existente se move rígida (key e handles com o mesmo Δy; o `x` não muda, então o timing fica intacto). Num frame sem key, a key é **criada ali**, como o auto-key.
  - **Canal sem nenhuma key:** recebe antes keys nas outras poses do personagem com o valor antigo, para que as outras poses não mudem.
- **Keys densas** continuam como na ADR 0011, para quem quiser esculpir o movimento entre poses. Também usam keys densas o Smooth (limpeza, por natureza denso) e os testes que verificam as invariantes densas.
- **Tecla I** com a ferramenta ativa (`asc.key_pose`): grava a pose inteira do personagem no frame atual, nos canais de rotação e translação dos controles do adapter, sem precisar selecionar bones.
- **Modos separados**:
  - **Corpo** agarra só o corpo, ou a ponta de um bone selecionado quando o esqueleto está visível. As trails ficam só para ver.
  - **Trail** agarra só os pontos da trail.

## Justificativa

- Pose a pose é o fluxo que o animador conhece (poses-chave + interpolação) e deixa a timeline legível.
- Cada arrasto mexe em poucos frames, então o movimento não "sai de controle" por sobreposição de janelas.
- A influência nas poses vizinhas mantém o "sculpt" suave pedido (os arrastos mexem pouco nas poses), sem impor o mesmo efeito a todas.
- Com os modos separados, a mesma tecla e o mesmo arrasto fazem sempre o mesmo tipo de coisa.

## Consequências

- **Pinos:** em pose a pose, os pinos (pés no `Corpo`) e o alvo da pele são exatos nos frames das poses. Entre as poses vale a interpolação do Blender, bone a bone, então um pé pode deslizar um pouco entre duas poses. Os testes dessas garantias "em todo frame" rodam em `DENSE`.
- **Começar do zero:** o primeiro arrasto num personagem sem animação cria uma pose só; o personagem fica parado nela até a próxima.
- **Testes:** o comportamento antigo das keys densas segue testado com `key_mode = 'DENSE'`. Pose a pose tem testes próprios: `tests/unit/test_pose_keys.py`, `tests/blender/test_body_workflow.py` e `tests/ui/scenario_pose_keys.py`.

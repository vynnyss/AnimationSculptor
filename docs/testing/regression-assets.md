# Assets de regressão

> Arquivos `.blend` usados pelos testes. Sempre reconstruíveis por script.

## Personagem do usuário (local, fora do repositório)

O repositório é **público** e o personagem de teste é do usuário (direitos/tamanho): ele **não entra no repo**. O caminho é configurável e o arquivo gerado fica em `tests/assets/local/` (gitignored). Testes que dependem dele **pulam** quando o arquivo não existe — o CI continua verde sem ele.

```toml
# scripts/.dev.toml (não versionado)
character = 'D:\Projetos\Vale_Rig_Animations.blend'
```

ou a variável de ambiente `ASC_TEST_CHARACTER`. Depois:

```
python scripts/dev.py assets            # gera tests/assets/local/attack_test.blend
python scripts/dev.py assets --preview  # + renders Workbench das key poses em tests/assets/local/preview/
```

O arquivo original **só é lido** (`save_as_mainfile(copy=True)` para outro caminho; o script recusa sobrescrever o original). O teste `test_original_actions_untouched` confere que as Actions do original continuam idênticas às registradas na geração.

| Asset | Conteúdo | Gerado por | Usado em |
|---|---|---|---|
| `tests/assets/local/attack_test.blend` (local) | Cópia do personagem; tudo exceto o control rig Rigify oculto (viewport e render: meshes, espada, armatures auxiliares); Action `asc_test_attack` no slot `OB<rig>`; markers das key poses; Actions anteriores preservadas (fake user) e com fingerprint | `python scripts/dev.py assets` (`scripts/make_test_assets.py`) | `tests/blender/test_attack_asset.py`; integração futura (trails, `P(f)`, sculpt); manual M1 |
| rig Rigify público (gerado em tempo de teste; **sem binário** no repo) | Metarig "Human" do Rigify 5.2 → `pose.rigify_generate` num Blender de fundo (~6 s, uma vez por sessão); Action `asc_public_test`, frames 1–24, keys em 1/12/24: `hand_ik.L` (loc+quat), `foot_ik.R` (loc), `torso` (loc), `upper_arm_fk.R` (quat). **Asset público para o CI** | `tests/blender/public_rig.py` (fixtures `public_rig_path`/`public_rig`) | `tests/blender/test_trails.py`; roda no CI |
| `tests/assets/simple_rig.blend` | Armature de 3 bones + objeto animado simples, sem Rigify | planejado | adapter genérico, paridade |
| `tests/assets/edge_cases.blend` | Canais com driver, NLA ativa, modificador de F-Curve, segmento LINEAR, eixo travado | planejado | recusas |

## Animação `asc_test_attack`

Ataque com espada (mão direita), 24 fps, frames 1–40, markers na timeline:

| Frame | Fase | Pose |
|---|---|---|
| 1 | `idle` | guarda (mesma pose do frame 1 da idle do personagem, copiada como literais) |
| 10 | `anticipation` | espada erguida atrás do ombro, torso torcido para trás e agachado, pé esquerdo levantado |
| 16 | `attack` | espada vertical por cima da cabeça, passo à frente com o pé esquerdo |
| 18 | `impact` | lâmina à frente apontando para baixo, torso inclinado para a frente, mais baixo |
| 26 | `follow_through` | lâmina continua para baixo e para a esquerda, torso girado além do alvo |
| 40 | `recovery` | volta à guarda, com o pé esquerdo à frente |

- Canais (todos Bézier, handles `AUTO_CLAMPED`, keys em todos os 6 frames): `root`, `torso` (loc+quat), `chest`, `head` (quat), `hand_ik.R` (loc+quat), `upper_arm_ik_target.R` (loc), `foot_ik.L/R` (loc+quat), `thigh_ik_target.L/R` (loc), `upper_arm_fk.L`, `forearm_fk.L`, `hand_fk.L` (quat).
- `IK_FK` keyado (CONSTANT, frame 1): braço direito **IK** (0), braço esquerdo **FK** (1), pernas IK. Assim há controles FK com efeito visível; `hand_ik.L` não é keyado (inativo).
- `root` é keyado mas constante (sem root motion por enquanto).
- Valores literais no script; quaternions com sinal contínuo entre keys (caminho curto). As poses foram autoradas como intenções em espaço de mundo (posição da mão, direção da lâmina, yaw/pitch do torso, cabeça olhando o alvo em (0, −3, 1.3)), convertidas uma vez para valores locais e conferidas por render (frames-chave e intermediários).
- Custom properties na cena: `asc_asset_version` (versão do Blender, ex. `5.2.1 LTS`), `asc_asset_script_version`, `asc_asset_source` (só o nome do arquivo), `asc_asset_rig`, `asc_asset_previous_action`, `asc_source_action_fingerprints` (JSON nome → sha256 das keys).
- A animação de idle do personagem **não** é usada pelos testes (só a pose do frame 1 foi copiada como literais) e fica intacta na cópia.

## Regras

- Valores de poses no script (números literais), nada aleatório.
- Gerar no Blender 5.2; versão do Blender gravada no próprio arquivo (`asc_asset_version`).
- Mudou o script ⇒ incrementar `SCRIPT_VERSION`, regenerar (`dev.py assets`) e rodar `test all`.
- Personagem real do usuário **não** entra no repo sem confirmação explícita do mantenedor; pode ser usado no teste manual.

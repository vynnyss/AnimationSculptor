# Assets de regressão

> Arquivos `.blend` usados pelos testes. Sempre reconstruíveis por script; o binário no repo é conveniência.

| Asset | Conteúdo | Gerado por | Usado em |
|---|---|---|---|
| `tests/assets/rigify_humanoid.blend` | Metarig "Human" do Rigify 5.2 gerado (rig `rig`), mesh simples (cápsulas por bone, parent com pesos automáticos ou por bone), sem animação | `scripts/make_test_assets.py rigify` | integração, manual M1 |
| `tests/assets/attack_test.blend` | O anterior + Action `attack` com key poses fixas (frames 1/10/16/18/26/40) em `hand_ik.R/L`, `foot_ik.*`, `torso`, `root`, alguns FK (`upper_arm_fk.R`…) | `scripts/make_test_assets.py attack` | integração, e2e Godot |
| `tests/assets/simple_rig.blend` | Armature de 3 bones + objeto animado simples, sem Rigify | `scripts/make_test_assets.py simple` | adapter genérico, paridade |
| `tests/assets/edge_cases.blend` | Canais com driver, NLA ativa, modificador de F-Curve, segmento LINEAR, eixo travado | `scripts/make_test_assets.py edge` | recusas |

## Regras

- Valores de poses no script (números literais), nada aleatório.
- Gerar no Blender 5.2; registrar versão do Blender/Rigify no próprio arquivo (custom property `asc_asset_version`).
- Mudou o script ⇒ regenerar e commitar o `.blend` no mesmo commit.
- Personagem real do usuário **não** entra no repo (direitos/tamanho); pode ser usado no teste manual.

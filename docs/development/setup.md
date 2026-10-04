# Setup de desenvolvimento

## Requisitos

- Windows (máquina principal); scripts em Python, portáveis para Linux/macOS.
- Blender **5.2** instalado.
- Python **3.11+** do sistema com `pytest` (`pip install pytest numpy`) — usado por `dev.py`, pelos testes unitários e para instalar o pytest do perfil de teste do Blender.
- Git.
- Godot **4.7.2** (Escopo 2).
- Opcional: VS Code + extensão "Blender Development" (Jacques Lucke) para reload e debug; Blender MCP (já instalado) para inspeção por agentes.

## Configuração local

`dev.py` procura o Blender nesta ordem: variável `BLENDER_EXE`, arquivo `scripts/.dev.toml`, caminho padrão do Windows (`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`), `blender` no PATH. Se o seu Blender está em outro lugar, crie `scripts/.dev.toml` (não versionado):

```toml
blender = 'D:\Programas\Blender 5.2\blender.exe'
godot   = 'C:\Tools\Godot\Godot_v4.7.2-stable_win64.exe'
character = 'D:\Projetos\Vale_Rig_Animations.blend'   # personagem de teste local (ou $ASC_TEST_CHARACTER)
```

`dev.py` confere que a versão encontrada é 5.2 antes de qualquer ação.

## Instalação para desenvolvimento (sem reempacotar)

```
python scripts/dev.py link
```

Pergunta ao próprio Blender onde fica o repositório de extensões `user_default` (`bpy.utils.user_resource('EXTENSIONS', path='user_default')`, normalmente `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default`) e cria ali uma **junction** (Windows, sem admin) / symlink `animation_sculptor` → `<repo>\animation_sculptor`. Depois: reiniciar o Blender e habilitar "Animation Sculptor" em Edit › Preferences › Add-ons. Editou código ⇒ F3 › "Reload Scripts". `python scripts/dev.py unlink` remove a junction (nunca apaga uma pasta real — se existir uma pasta comum com esse nome, o script se recusa).

## Instalação do zip (M0)

Para testar a instalação como o usuário final (checklist [M0](../testing/manual-tests.md#m0--instalação-5-min)): `python scripts/dev.py build`, depois, no Blender, Edit › Preferences › Get Extensions › ⌄ › Install from Disk… › `dist/animation_sculptor-0.3.0.zip`. Antes, `python scripts/dev.py unlink` e reinicie o Blender, para não misturar com a junction de desenvolvimento. Também dá para instalar sem GUI num perfil limpo: `blender --command extension install-file -r user_default -e dist/animation_sculptor-0.3.0.zip` (e `extension remove animation_sculptor` para desinstalar). O zip contém só `animation_sculptor/` (39 arquivos; sem `tests/` nem `__pycache__`).

## Comandos (`scripts/dev.py`)

| Comando | Faz | Estado |
|---|---|---|
| `link` / `unlink` | instala/remove a extensão por junction/symlink no seu perfil do Blender | ✅ |
| `test unit [args pytest]` | pytest em `tests/unit` com o Python do sistema | ✅ |
| `test blender [args pytest]` | pytest dentro do Blender em background, **perfil isolado** (`.blender_test_profile/`) | ✅ |
| `test ui [filtro]` | Blender **com janela** (`--enable-event-simulate`, perfil isolado) rodando os cenários `tests/ui/scenario_*.py` com `Window.event_simulate`; resultados e screenshots em `.blender_test_profile/ui/`. Precisa de display; só local, fora do CI ([detalhes](../testing/blender-tests.md#testes-de-ui-eventos-simulados)) | ✅ |
| `test all` | unit + blender (não inclui `ui`) | ✅ |
| `build` | `blender --command extension build` ⇒ `dist/animation_sculptor-<versão>.zip` (versão atual **0.3.0**: `dist/animation_sculptor-0.3.0.zip`, o build do Escopo 1) | ✅ |
| `validate` | regras estáticas (`scripts/checks.py`) + `blender --command extension validate` | ✅ |
| `fetch-blender` | (CI Linux) baixa o Blender 5.2.x mais recente para `.blender/` | ✅ |
| `test godot` | e2e export + import headless | Escopo 2 |
| `assets [--preview]` | gera `tests/assets/local/attack_test.blend` a partir do personagem configurado ([assets](../testing/regression-assets.md)) | ✅ |

## Regras estáticas (`scripts/checks.py`)

Rodadas por `validate` e pelos testes unitários (o CI falha se quebrar):

1. `animation_sculptor/core/` não importa módulos do Blender (`bpy`, `mathutils`, `gpu`, …) — ADR 0008.
2. Nomes de bones de rig (`"DEF-`, `"ORG-`, `"MCH-`, `*_fk.L`, `*_ik.R`…) só em `rig/` (e no vendor `trails/lmp/`) — ADR 0002.
3. Manifest: ID, nome, `blender_version_min >= 5.2.0`, licença GPL-3.0-or-later.
4. Links e âncoras entre arquivos Markdown resolvem.

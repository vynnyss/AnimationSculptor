# Setup de desenvolvimento

> Planejado; scripts ainda não existem (agenda › Agora, item 2).

## Requisitos

- Windows (máquina principal) — scripts em Python, portáveis para Linux/macOS.
- Blender **5.2** instalado.
- Python 3.11+ do sistema para `dev.py` e testes unitários (`pip install numpy pytest`); o Blender usa o próprio Python.
- Git.
- Godot **4.7.2** (Escopo 2).
- Opcional: VS Code + extensão "Blender Development" (Jacques Lucke) para reload e debug; Blender MCP (já instalado) para inspeção por agentes.

## Configuração local

`scripts/.dev.toml` (não versionado):

```toml
blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
godot   = 'C:\Tools\Godot\Godot_v4.7.2-stable_win64.exe'
```

Ou variáveis `BLENDER_EXE` / `GODOT_EXE`.

## Instalação para desenvolvimento (sem reempacotar)

```
python scripts/dev.py link
```

Cria uma **junction** (Windows, sem admin) de
`%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\<id>` → `<repo>\animation_sculptor`. Editou código ⇒ no Blender: F3 › "Reload Scripts" (ou a extensão do VS Code). `python scripts/dev.py unlink` remove.

## Comandos (`scripts/dev.py`)

| Comando | Faz |
|---|---|
| `link` / `unlink` | instala/remove a extensão por junction/symlink |
| `test unit` | pytest em `tests/unit` com Python do sistema |
| `test blender [-k ...]` | pytest dentro do Blender em background, perfil isolado |
| `test godot` | e2e export + import headless (Escopo 2) |
| `test all` | unit + blender (+ godot se configurado) |
| `build` | `blender --command extension build` ⇒ `dist/<id>-<versão>.zip` |
| `validate` | `blender --command extension validate`, regras estáticas (sem `bpy` em `core/`, sem nomes de bones fora de `rig/`), links de `docs/` |
| `assets [nome]` | roda `make_test_assets.py` no Blender |

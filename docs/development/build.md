# Build e empacotamento

## Pacote

A extensão é a pasta `animation_sculptor/` com `blender_manifest.toml`. Build oficial do Blender:

```
blender --command extension build --source-dir animation_sculptor --output-dir dist
blender --command extension validate dist/<id>-<versão>.zip
```

Encapsulado em `python scripts/dev.py build`.

## Manifest (esboço)

```toml
schema_version = "1.0.0"
id = "animation_sculptor"
version = "0.1.0"
name = "Animation Sculptor"
tagline = "Sculpt character motion trails directly in the viewport"
maintainer = "<autor>"
type = "add-on"
tags = ["Animation", "3D View", "Rigging"]
blender_version_min = "5.2.0"
license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 <autor>", "2026 Experience Elysian (Live Motion Path)", "Bart Crouch (Motion Trail)", "Wayde Brandon Moss (Motiontrail3D)"]

[build]
paths_exclude_pattern = ["__pycache__/", "/.git/", "*.zip", "/tests/"]
```

Sem `permissions` (não acessamos rede/arquivos fora do `.blend`, exceto export iniciado pelo usuário — confirmar se o export precisa de `files`).

## Versionamento

SemVer `0.x` até o MVP. Cada build entregue para teste manual: tag `v0.N.M`, changelog curto em `current-state.md`.

## Builds de teste

`dev.py build` + `dev.py test all` antes de entregar um zip ao usuário. O zip vai para `dist/` (ignorado no git).

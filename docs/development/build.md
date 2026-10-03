# Build e empacotamento

## Pacote

A extensão é a pasta `animation_sculptor/` com `blender_manifest.toml`. Build oficial do Blender:

```
blender --command extension build --source-dir animation_sculptor --output-dir dist
blender --command extension validate dist/<id>-<versão>.zip
```

Encapsulado em `python scripts/dev.py build`.

## Manifest

Arquivo real: [`animation_sculptor/blender_manifest.toml`](../../animation_sculptor/blender_manifest.toml). Ao vendorizar código de terceiros, acrescentar os autores em `copyright` (Experience Elysian — Live Motion Path; Bart Crouch — Motion Trail; Wayde Brandon Moss — Motiontrail3D) e em `THIRD_PARTY_NOTICES.md`.

Sem `permissions` (não acessamos rede/arquivos fora do `.blend`, exceto export iniciado pelo usuário — confirmar se o export precisa de `files`).

## Versionamento

SemVer `0.x` até o MVP. Cada build entregue para teste manual: tag `v0.N.M`, changelog curto em `current-state.md`.

## Builds de teste

`dev.py build` + `dev.py test all` antes de entregar um zip ao usuário. O zip vai para `dist/` (ignorado no git).

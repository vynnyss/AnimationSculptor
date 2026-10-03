# 0007 — GPL-3.0-or-later e política de reutilização

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

Todo o código de referência é GPL (LMP GPL-3+, Motion Trail GPL-2+, Motiontrail3D GPL-3, Blender GPL-2+). Addons Blender que usam `bpy` já são tratados como GPL pela Blender Foundation.

## Opções consideradas

1. Licença permissiva e reimplementação "clean room".
2. **GPL-3.0-or-later**, reutilizando código diretamente com proveniência registrada.

## Decisão

Opção 2. Projeto licenciado GPL-3.0-or-later. Código de terceiros só entra após verificar licença compatível (GPL-2+/GPL-3+/MIT/BSD/Apache-2.0 ok; GPL-2-only, proprietário ou sem licença: não).

## Justificativa

Permite reutilizar sem reescrever; coerente com o ecossistema Blender; GPL-2-or-later combina com GPL-3.

## Consequências

- `LICENSE` (GPL-3) na raiz e `license = ["SPDX:GPL-3.0-or-later"]` no manifest.
- Toda cópia/port registrada em [reference/open-source-provenance.md](../reference/open-source-provenance.md) e em `THIRD_PARTY_NOTICES.md`; cabeçalhos preservados; marcações no código.
- Código de produto pago (ex.: Motion Sculpt JB FX) só se obtido legitimamente e com a licença verificada no pacote.

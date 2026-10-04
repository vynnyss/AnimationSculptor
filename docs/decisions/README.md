# Architecture Decision Records

ADRs leves inspirados em [MADR](https://github.com/adr/madr). Um arquivo por decisão significativa; decisões triviais não viram ADR.

## Índice

| # | Decisão | Status |
|---|---|---|
| [0001](0001-live-motion-path-foundation.md) | Live Motion Path vendorizado como fundação das trails | aceito |
| [0002](0002-rigify-first-rig-adapter.md) | Rigify primeiro, por trás de um Rig Adapter | aceito |
| [0003](0003-native-blender-animation-output.md) | Saída é animação Blender nativa (Action/F-Curves) | aceito |
| [0004](0004-blender-5.2-baseline.md) | Blender 5.2 LTS como baseline único | aceito |
| [0005](0005-extension-not-fork.md) | Extensão Python, não fork nem módulo nativo | aceito |
| [0006](0006-tangent-space-deferred.md) | Tangent-Space fora da Iteração 1; solve linear para translação | aceito; a parte de FK foi substituída por 0011 (2026-10-04) |
| [0007](0007-gpl-and-reuse-policy.md) | GPL-3.0-or-later e política de reutilização | aceito |
| [0008](0008-pure-python-core.md) | Core puro (numpy, sem bpy) separado da integração | aceito |
| [0009](0009-export-native-bake-gltf.md) | Export via bake/amostragem nativa + glTF; sem conversor de esqueleto | aceito |
| [0010](0010-tool-gizmo-modal-interaction.md) | Interação: WorkSpaceTool + Gizmo (hover) + modal (gesto) | aceito — validado pelo spike (2026-10-03) |
| [0011](0011-ephemeral-rig-dense-keys.md) | FK por rig efêmero (solve em `core/`) com keys densas na janela de tempo | aceito (2026-10-04) |
| [0012](0012-spacing-policy-preserve-path.md) | Política de spacing: `PRESERVE_PATH` como padrão | aceito (2026-10-04) |
| [0013](0013-body-and-trail-interaction.md) | Interação em dois modos: agarrar o corpo (pose/arco) e a trail (tempo); ferramentas na lateral; Rigify escondido | proposto |

## Modelo

```markdown
# NNNN — Título

- Status: proposto | aceito | substituído por NNNN
- Data: AAAA-MM-DD

## Contexto e problema
## Opções consideradas
## Decisão
## Justificativa
## Consequências
```

Ao substituir uma decisão: novo ADR, e o antigo recebe "substituído por NNNN" (não apagar).

# docs/ — memória técnica do projeto

Esta pasta é a memória persistente do Animation Sculptor. Código e documentação não podem divergir: se divergirem, verifique o comportamento real e corrija a documentação.

## Ordem de leitura para uma sessão nova

1. [project.md](project.md) — objetivo, escopo, não-objetivos.
2. [current-state.md](current-state.md) — o que existe e funciona **hoje**.
3. [architecture.md](architecture.md) — módulos, fluxo de dados, estrutura do repo.
4. [agenda.md](agenda.md) — o que fazer agora.
5. ADRs relacionados ao que vai mexer — [decisions/](decisions/README.md).

## Depois de uma mudança significativa

1. Atualizar `current-state.md`.
2. Atualizar `agenda.md`.
3. Atualizar `architecture.md` se a estrutura mudou.
4. ADR novo **só** se houve decisão arquitetural significativa.
5. Atualizar testes/docs afetados (`design/`, `testing/`, `reference/open-source-provenance.md` se código de terceiros entrou).

## Mapa

| Pasta / arquivo | Para quê |
|---|---|
| `project.md` | fonte concisa de verdade (não é histórico) |
| `architecture.md` | arquitetura atual + estrutura do repositório |
| `roadmap.md` | escopos funcionais grandes e critérios de aceitação |
| `agenda.md` | backlog operacional (agora / próximo / depois / investigação / bugs / dívida) |
| `current-state.md` | estado real, testes, próximo objetivo |
| `reference/` | análise dos projetos open-source, artigos, proveniência de código |
| `design/` | specs: modelo de sculpt, rig adapter, dados de animação, UX, pipeline Godot |
| `decisions/` | ADRs (MADR leve) |
| `testing/` | estratégia, testes Blender, checklists manuais, e2e Godot, assets |
| `development/` | fluxo de PR, setup, build, debugging, notas da API 5.2 |

Mudanças em relação à estrutura proposta originalmente: acrescentados `reference/open-source-provenance.md` e `decisions/0004…0010`; `scripts/` consolidado em um `dev.py` (ver [architecture.md](architecture.md#estrutura-do-repositório-alvo)).

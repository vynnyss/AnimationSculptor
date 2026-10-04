# Fluxo de trabalho (Git e PRs)

> Regra do mantenedor: **nada entra na `main` sem PR aprovado por ele**, depois de passar nos testes dele.

- Repositório: https://github.com/vynnyss/AnimationSculptor
- Branch protegida (por convenção): `main`. Nunca commitar nem fazer push direto na `main` (exceto o commit inicial que a criou).

## Ciclo

1. Atualizar a `main` local (`git fetch origin && git switch main && git pull --ff-only`).
2. Criar branch a partir da `main`: `<tipo>/<assunto-curto>` — tipos: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`. Ex.: `feat/repo-skeleton`, `docs/planning`.
3. Trabalhar seguindo [CLAUDE.md](../../CLAUDE.md) (ler docs antes; atualizar `current-state.md`/`agenda.md` depois).
4. Rodar `python scripts/dev.py test all` (quando existir) e `validate`.
5. Push da branch e abrir PR **para `main`** com a descrição no modelo abaixo.
6. **Parar.** Não fazer merge. O mantenedor testa, comenta ou aprova e faz o merge.
7. Comentários de revisão: corrigir na mesma branch (novos commits, sem force-push salvo pedido) e avisar no PR.
8. Depois do merge: apagar a branch, atualizar a `main` local. Trabalho seguinte parte da `main` nova.

Um PR = um resultado funcional coerente (alinhado aos itens da [agenda](../agenda.md)). PRs que dependem de outro PR ainda aberto: basear na branch do anterior e deixar isso explícito na descrição — ou esperar o merge.

## Modelo de descrição de PR

```markdown
## O que muda
<resultado funcional, 1–3 frases>

## Como testar (para o mantenedor)
<resumo de uma ou duas linhas do que testar; o passo a passo fica no roteiro abaixo>

## Roteiro de teste manual (Blender 5.2)
**Preparação**
1. `git fetch origin && git switch <branch>` (PR empilhado: confirmar antes que a branch-base está atualizada).
2. `python scripts/dev.py link`; reiniciar o Blender e habilitar "Animation Sculptor" se necessário.
3. Abrir <arquivo, ex.: `tests/assets/local/attack_test.blend`>; modo <Pose Mode>; selecionar <bone>; ferramenta <ativa/qual>.

**Ações** (uma por passo, em ordem)
4. <clique/tecla/arrasto exato> → **Esperado:** <o que se vê no viewport/header/painel>.
5. <...> → **Esperado:** <...>

**Cancelar/desfazer:** <Esc/RMB durante o gesto, Ctrl+Z depois>; o que deve voltar.
**NÃO deve mudar:** <keys, timing, seleção, objetos, arquivo em disco…>.
**Regressões a conferir:** <comportamentos de PRs anteriores que este toca>.
**Pré-requisitos (PR empilhado):** <PRs que precisam estar na branch>.
**Se falhar, anotar:** passo, o que apareceu (header/console: Window › Toggle System Console), frame/bone, e se reproduz após reiniciar o Blender.

## Testes automatizados
- unit: <passou/falhou/N/A>
- blender: <passou/falhou/N/A>

## Docs atualizados
- current-state.md, agenda.md, ...

## Fora do escopo / limitações conhecidas
- ...
```

### Roteiro de teste manual: obrigatório em todo PR

Pedido do mantenedor em 2026-10-04: **todo PR traz a seção "Roteiro de teste manual (Blender 5.2)"** na descrição, escrita para quem vai clicar no próprio Blender sem conhecer o código. Regras:

- Passos **numerados e no nível do clique** (menu, painel, tecla, arrasto), na ordem em que serão executados.
- **Preparação** completa: `git fetch`/`switch` da branch, `python scripts/dev.py link`, reiniciar o Blender, qual arquivo abrir (de preferência `tests/assets/local/attack_test.blend`), modo, seleção e ferramenta ativa.
- Cada ação com o **resultado esperado visível** (viewport, header, painel, Dope Sheet/Graph Editor).
- Como **cancelar/desfazer** (Esc/RMB, Ctrl+Z) e o que deve voltar ao estado anterior.
- O que **não** deve mudar (keys, timing, seleção, objetos, dados do arquivo).
- **Regressões** de PRs anteriores a conferir, e **pré-requisitos** quando o PR é empilhado (qual PR/branch precisa estar aplicado).
- **O que anotar se falhar** (passo, mensagem do header/console, frame, bone, se reproduz após reiniciar).
- Mudanças sem efeito visível (docs, refactor) trazem o roteiro mínimo de verificação (ex.: abrir o arquivo, ativar a ferramenta, um gesto) ou "N/A: só documentação".
- Checklists permanentes (M0–M2) ficam em [testing/manual-tests.md](../testing/manual-tests.md); o roteiro do PR pode remeter a eles mas não substitui os passos novos.

## Commits

Mensagens curtas no imperativo, em inglês ou português (consistente dentro do PR). Sem arquivos gerados (`dist/`, `.blender_test_profile/`, `__pycache__/`).

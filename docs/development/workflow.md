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
1. <passos reproduzíveis no Blender 5.2 / Godot 4.7.2>
2. Resultado esperado: ...

## Testes automatizados
- unit: <passou/falhou/N/A>
- blender: <passou/falhou/N/A>

## Docs atualizados
- current-state.md, agenda.md, ...

## Fora do escopo / limitações conhecidas
- ...
```

## Commits

Mensagens curtas no imperativo, em inglês ou português (consistente dentro do PR). Sem arquivos gerados (`dist/`, `.blender_test_profile/`, `__pycache__/`).

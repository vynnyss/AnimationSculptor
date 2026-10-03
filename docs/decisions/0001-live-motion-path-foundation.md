# 0001 — Live Motion Path vendorizado como fundação das trails

- Status: aceito
- Data: 2026-10-03

## Contexto e problema

Animation Sculptor precisa de trajetórias ao vivo para bones de Rigify: avaliação correta (constraints, IK), cache, invalidação seletiva, agendamento que não trave a UI, desenho GPU moderno (sem `bgl`), compatível com Slotted Actions. Escrever isso do zero é semanas de trabalho e risco de performance.

## Opções consideradas

1. Implementar engine próprio.
2. Depender do LMP como extensão separada instalada pelo usuário.
3. **Vendorizar o LMP** (copiar para `animation_sculptor/trails/lmp/`) com patches mínimos e uma façade.
4. Usar só os motion paths nativos do Blender (`pose.paths_calculate`) sem cache próprio.

## Decisão

Opção 3. Copiar o LMP (`0e173fd`, GPL-3+) para dentro do pacote, renomear namespace (`asc_trails`), aplicar patches pequenos e marcados (`# ASC-PATCH Pn`), e acessar só via `trails/provider.py`.

## Justificativa

- Já resolve engine (native solver/frame stepping), cache, dirty-tracking por dependências, debounce + time slicing, handlers `@persistent`, GPU `gpu`-only, slotted actions, cor de velocidade, onion skin.
- (2) amarra nossa UX a um projeto externo sem API e sem histórico; colisão de `Scene.motion_onion`.
- (4) não tem cache/scheduler nem desenho customizável; o LMP já embrulha o solver nativo.
- Licença compatível (GPL-3+).

## Consequências

- Somos donos do código vendorizado: bugs dele são nossos; testes de integração cobrem o que usamos.
- O LMP **não** tem caminho barato para bones ⇒ o preview durante o gesto é nosso (analítico via `P(f)`), e o engine é suspenso durante o arrasto (patch P3).
- Atualizações do upstream são aplicadas manualmente por diff (patches marcados facilitam).
- A façade permite trocar o engine no futuro sem tocar no sculpt.
- Detalhes: [reference/live-motion-path.md](../reference/live-motion-path.md).

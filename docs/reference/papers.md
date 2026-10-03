# Artigos de referência

> Base teórica. Marcar ✅ quando a referência for conferida na fonte primária (DOI/PDF); ⏳ = citação de memória, conferir antes de depender dela.

| Artigo | Relevância | Status |
|---|---|---|
| Ciccone, Öztireli, Sumner. **Tangent-Space Optimization for Interactive Animation Control.** ACM TOG (SIGGRAPH 2019). Página Disney Research: https://studios.disneyresearch.com/2019/07/12/tangent-space-optimization-of-controls-for-character-animation/ | Otimiza tangentes/valores de F-Curves para satisfazer arrastos na trail, sem adicionar keys. Base do fork Interactive Motion Path e do FK sculpt (Escopo 4). | link confirmado pelo README do fork; conteúdo ⏳ |
| Ciccone, Guay, Nitti, Sumner. **Authoring Motion Cycles.** SCA 2017. | Edição de ciclos por trajetórias; mesmo grupo, antecessor do anterior. | ⏳ |
| Guay, Ronfard, Gleicher, Cani. **Space-time Sketching of Character Animation.** ACM TOG (SIGGRAPH 2015). | Esboço de trajetória + timing como unidade de edição. Inspiração de UX (não algoritmo). | ⏳ |
| Gleicher. **Motion Path Editing.** I3D 2001. | Edição de caminho de locomoção preservando detalhe — ideia de "deslocamento suave" aplicável a smooth/arc. | ⏳ |
| Terra, Metoyer. **Performance Timing for Keyframe Animation.** SCA 2004. | Retiming de animação por performance; referência para timing avançado. | ⏳ |

## Uso no projeto

- Iteração 1 **não** depende de nenhum artigo: as operações são lineares e derivadas diretamente da forma Bézier das F-Curves ([modelo](../design/motion-sculpt-model.md)).
- Antes de implementar o Escopo 4, ler Ciccone 2019 na íntegra e registrar aqui: formulação exata, pesos, tratamento de rotações e diferenças em relação ao fork.

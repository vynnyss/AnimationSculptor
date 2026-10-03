# Animation Sculptor

Ferramenta determinística de *motion sculpting* para **Blender 5.2**: edite o movimento de personagens humanoides (Rigify) direto nas trajetórias do viewport — arcos, timing, spacing — produzindo Actions/F-Curves normais, prontas para bake e export glTF → Godot.

**Status:** esqueleto instalável (sem ferramentas de animação ainda). Veja [docs/current-state.md](docs/current-state.md).

## Começo rápido (desenvolvimento)

```
pip install pytest numpy
python scripts/dev.py test unit      # sem Blender
python scripts/dev.py test blender   # dentro do Blender 5.2, perfil isolado
python scripts/dev.py link           # instala o working tree no seu Blender
python scripts/dev.py build          # gera dist/animation_sculptor-<versão>.zip
```

Detalhes: [docs/development/setup.md](docs/development/setup.md). Contribuição: PR para `main` ([workflow](docs/development/workflow.md)).

- O que é e o que não é: [docs/project.md](docs/project.md)
- Arquitetura: [docs/architecture.md](docs/architecture.md)
- Roadmap: [docs/roadmap.md](docs/roadmap.md)
- Toda a documentação: [docs/README.md](docs/README.md)

Licença: GPL-3.0-or-later (reutiliza código GPL — ver [docs/reference/open-source-provenance.md](docs/reference/open-source-provenance.md)).

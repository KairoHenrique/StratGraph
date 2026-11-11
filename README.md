# StratGraph

Otimização de rotas estratégicas em mapas de jogos digitais modelados como **Dígrafos Ponderados Expandidos em Camadas**, equilibrando tempo/dificuldade de travessia, desvio estratégico para obtenção de arma (*power-up*) e coleta de itens.

> Trabalho Final da disciplina **Estruturas em Árvores e Teoria dos Grafos** (Prof. Michel Pires da Silva — UFCI-MG).
>
> * **Autores:** Heitor Henrique Zonho, Kairo Henrique Ferreira Martins e Michel Pires da Silva
> * **Repositório Oficial (GitHub):** https://github.com/KairoHenrique/StratGraph
> * **Dataset Oficial Publicado (Zenodo):** https://doi.org/10.5281/zenodo.24147071 (`https://zenodo.org/records/24147071`)

## Estrutura do Repositório

```text
├── src/                  # Núcleo algorítmico em Python 3.12 (apenas biblioteca padrão)
├── docs/                 # Documentação técnica, modelagem e guias de execução
├── datasets/             # Mapas tratados em CSV (Celeste, Cuphead e benchmarks sintéticos)
├── scripts/              # Geração de benchmarks, execução em lote e plotagem para o artigo
├── tests/                # Testes unitários e de integração
├── results/              # Resultados experimentais exportados (CSV/JSON)
└── article/              # Rascunho LaTeX (IEEE Conference Template), referências e figuras
```

Consulte [docs/plano_implementacao.md](docs/plano_implementacao.md) para ver o plano completo do projeto, [docs/INDICE.md](docs/INDICE.md) para a lista de documentos e [docs/execucao_linux_windows.md](docs/execucao_linux_windows.md) para o guia de execução.

## Execução Multiplataforma (Linux Ubuntu 24.04 e Windows)

O núcleo do **StratGraph** (`src/`) utiliza **exclusivamente a biblioteca padrão do Python 3.12**, funcionando tanto no **Linux (Ubuntu 24.04)** quanto no **Windows** sem compilação ou dependências externas:

```bash
# Linux (Ubuntu 24.04)
python3 -m src.main --dataset datasets/sample_toy --alpha 0.5

# Windows (PowerShell / CMD)
python -m src.main --dataset datasets/sample_toy --alpha 0.5
```

### Dependências opcionais (gráficos do artigo e testes)

```bash
pip install -r requirements-dev.txt
```

## Licença

Este projeto é distribuído sob a licença **MIT** — veja o arquivo [LICENSE](LICENSE) para mais detalhes.

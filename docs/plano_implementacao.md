# Plano de Implementação — **StratGraph**

Plano completo do projeto **StratGraph** (*Otimização de Rotas Estratégicas em Jogos Digitais via Grafo Ponderado Expandido em Camadas*), alinhado integralmente aos requisitos de [pratica (1).pdf](pratica%20(1).pdf) para entrega no AVA até **22/11/2026** e apresentação oral (*Pitch* de 10 min sem slides) a partir de **25/11/2026**.

---

## 1. Identidade, Equipe e Entregáveis

* **Nome do software / pesquisa:** **StratGraph** ([KairoHenrique/StratGraph](https://github.com/KairoHenrique/StratGraph)).
* **Autores e ordem oficial no artigo:**
  1. `Kairo Henrique Ferreira Martins` (UFCI-MG)
  2. `Heitor Henrique Zonho` (UFCI-MG)
  3. `Michel Pires da Silva` (UFCI-MG — **último autor obrigatório**)
  *(Nota: confirmar entre a equipe se a contribuição é igualitária — caso seja, a Seção 3.1 pede ordem alfabética: Heitor antes de Kairo).*
* **Licenciamento:** **MIT License** em [LICENSE](../LICENSE) com os dois autores alunos (`Copyright (c) 2026 Kairo Henrique Ferreira Martins, Heitor Henrique Zonho`).
* **Compatibilidade Multiplataforma (Linux Ubuntu 24.04 e Windows):**
  * Núcleo `src/` em **Python 3.12 usando exclusivamente a biblioteca padrão** (`csv`, `heapq`, `collections`, `argparse`, `pathlib`, `time`, `dataclasses`, `json`) — roda nativamente no Ubuntu 24.04 (`python3`) e no Windows (`python`) sem compilação ou pacotes extras.
  * Todos os caminhos tratados com `pathlib.Path`, leitura/escrita CSV com `encoding="utf-8"` e `newline=""`, e saída de terminal protegida para UTF-8 no Windows (`sys.stdout.reconfigure`).

---

## 2. Estrutura Consolidada no Repositório

* Raiz: [README.md](../README.md), [LICENSE](../LICENSE), [requirements-dev.txt](../requirements-dev.txt), [.gitignore](../.gitignore).
* Documentação (`docs/`): [INDICE.md](INDICE.md), [arquitetura_e_modelagem.md](arquitetura_e_modelagem.md), [execucao_linux_windows.md](execucao_linux_windows.md), [plano_implementacao.md](plano_implementacao.md), [pratica (1).pdf](pratica%20(1).pdf).
* Código principal (`src/`): [models.py](../src/models.py), [loader.py](../src/loader.py), [preprocessing.py](../src/preprocessing.py), [layered_graph.py](../src/layered_graph.py), [algorithms.py](../src/algorithms.py), [metrics.py](../src/metrics.py), [main.py](../src/main.py).
* Datasets (`datasets/`): [ESQUEMA_DATASET.md](../datasets/ESQUEMA_DATASET.md), `sample_toy/`, `celeste/`, `cuphead/`, `synthetic/`.
* Scripts e testes: [generate_benchmarks.py](../scripts/generate_benchmarks.py), [run_experiments.py](../scripts/run_experiments.py), [plot_results.py](../scripts/plot_results.py), [test_pipeline.py](../tests/test_pipeline.py).
* Artigo IEEE (`article/`): [main.tex](../article/main.tex), [references.bib](../article/references.bib), [GUIA_OVERLEAF.md](../article/GUIA_OVERLEAF.md), `figures/`.

---

## 3. Fases de Execução

### Fase 1 — Fechamento da Modelagem (Regras Finais)
1. **Contração de becos sem saída (`src/preprocessing.py`):**
   * Contrair sala `COLETAVEL` (sem `possui_arma`) conectada exclusivamente a um vizinho $B$ com ida e volta válidas, somando o tempo/dificuldade de ida e volta e transferindo o coletável para $B$.
   * Manter a flag `--no-contract` para estudo de ablação nos experimentos.
2. **Prevenção de dupla contagem entre camadas:**
   * A contabilização de `collectibles_count` e `collectibles_total_value` em `RouteResult` usará o conjunto único `collected_room_ids` (`set` de `id_sala`), impedindo somar o mesmo item nas camadas `0` e `1`.
3. **Papel distinto dos 3 algoritmos:**
   * **BFS ($O(V + E)$):** *baseline* por menor número de transições (ignora pesos, arma e coletáveis).
   * **DFS *Branch-and-Bound*:** busca exata com estado `(node, collected_frozenset)` rastreando itens já pegos sem dupla contagem, com poda por custo e `--bnb-timeout` para mapear o gargalo exponencial.
   * **Dijkstra no Grafo em Camadas ($O((V + E)\log V)$):** solução principal escalável usando `heapq` sobre a função positiva:
     $$w(u, v, k) = \frac{\text{TempoBase}(u, v) + \text{Dificuldade}(u, v, k)}{1 + \alpha \cdot \text{ValorColetavel}(v)}, \quad \alpha > 0$$

### Fase 2 — Loader, Pré-processamento e Grafo em Camadas
* Implementar `src/loader.py`: leitura UTF-8 de `vertices.csv` e `arestas.csv`, validação de tipos, existência de `INICIO` e `FIM`, integridade de vértices nas arestas e expansão de `mao_dupla = 1`.
* Implementar `src/preprocessing.py`: `contract_dead_ends` preservando auditoria das salas contraídas.
* Implementar `src/layered_graph.py`: `compute_effective_weight` e `build_layered_graph` criando camadas `0` e `1` e aresta de custo zero $(u_{\text{arma}}, 0) \to (u_{\text{arma}}, 1)$.

### Fase 3 — Algoritmos, Métricas e CLI Multiplataforma
* Implementar `src/algorithms.py`: `run_bfs`, `run_dfs_branch_and_bound` e `run_dijkstra`.
* Implementar `src/metrics.py` e finalizar `src/main.py`: tabela comparativa no terminal (Linux/Windows) exibindo rota, custo real, peso efetivo, coletáveis únicos, estados visitados e tempo (`ms`), além de exportação opcional para CSV/JSON (`--output`).

### Fase 4 — Datasets Reais (*Celeste*, *Cuphead*), Sintéticos e Zenodo
* Mapear **2 a 3 cenários reais de *Celeste*** em `datasets/celeste/` (salas, morangos como coletáveis, quedas unidirecionais e chaves/habilidades como `possui_arma=1`).
* Mapear **2 a 3 fases *Run-and-Gun* de *Cuphead*** em `datasets/cuphead/` (rotas alta/baixa, moedas como coletáveis e arma/Super reduzindo `dificuldade_com_arma`).
* Implementar `scripts/generate_benchmarks.py` gerando cenários determinísticos (`seed=42`) em `datasets/synthetic/` com $V \in \{15, 30, 60, 150, 500, 1500, 5000\}$.
* Publicar o pacote `datasets/` no **Zenodo** ou **Mendeley Data** e inserir o link/DOI em `article/references.bib`.

### Fase 5 — Experimentos, Figuras e Fluxograma Obrigatório
* Implementar `scripts/run_experiments.py`: rodar comparativo em *Celeste*, *Cuphead*, benchmarks de escalabilidade, sensibilidade de $\alpha \in \{0.0, 0.25, 0.5, 1.0, 2.0\}$ e comparação com/sem `--no-contract`.
* Implementar `scripts/plot_results.py`: gerar em `article/figures/`:
  1. **Fluxograma obrigatório** da metodologia (`fluxograma_proposta.pdf`).
  2. Gráfico de escalabilidade (tempo em `ms` × $|V|$ em escala log).
  3. Comparativo de custo real e coletáveis entre BFS, B&B e Dijkstra em *Celeste* e *Cuphead*.
  4. Curva de sensibilidade do parâmetro $\alpha$.

### Fase 6 — Artigo IEEE, Validação Final e Pitch
* Completar `article/main.tex` e `article/references.bib`, compilar no Overleaf (**IEEE Conference Template**), validar todas as referências no Google Scholar (`scholar.google.com`) e garantir que `repo_codigo` e `dataset_zenodo` estejam citados no texto e nas referências.
* Submeter apenas o **PDF final no AVA** até **22/11/2026** e ensaiar o **Pitch oral de 10 minutos sem slides** (a partir de **25/11/2026**).

---

## 4. Plano de Verificação

* **Testes automatizados (`python -m pytest -v` / `python3 -m pytest -v`):**
  * Validação de CSVs válidos/inválidos, contração de becos sem saída, positividade de $w(u, v, k)$ e regressão no `datasets/sample_toy` garantindo desvio de Dijkstra/B&B para a arma `S3` sem dupla contagem de `S2`.
* **Validação multiplataforma:**
  * Executar `python -m src.main --dataset datasets/sample_toy` no **Windows** e `python3 -m src.main --dataset datasets/sample_toy` no **Linux (Ubuntu 24.04)** usando apenas biblioteca padrão do Python 3.12.

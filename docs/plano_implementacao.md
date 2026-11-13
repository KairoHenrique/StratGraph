# Plano de Implementação — **StratGraph**

Plano completo do projeto **StratGraph** (*Otimização de Rotas Estratégicas em Jogos Digitais via Grafo Ponderado Expandido em Camadas*), alinhado integralmente aos requisitos de [pratica (1).pdf](pratica%20(1).pdf) para entrega no AVA até **22/11/2026** e apresentação oral (*Pitch* de 10 min sem slides) a partir de **25/11/2026**.

---

## Status Geral do Projeto

- [x] **Fase 1 — Modelagem Matemática e Regras Finais**
- [x] **Fase 2 — Loader, Pré-processamento e Grafo em Camadas**
- [x] **Fase 3 — Algoritmos (`BFS`, `DFS Branch-and-Bound`, `Dijkstra`), Métricas e CLI**
- [x] **Fase 4 — Extratores Binários Oficiais (*Celeste* e *Cuphead*), Benchmarks Sintéticos e Publicação no Zenodo (`doi:10.5281/zenodo.24147071`)**
- [x] **Fase 5 — Bateria Experimental, Fluxograma Obrigatório e Gráficos Científicos**
- [ ] **Fase 6 — Compilação do Artigo IEEE no Overleaf e Validação no Ubuntu 24.04**
- [x] **Fase 7 (Extras — Antes da Entrega Final) — Simulador Visual 2D, Exportação CelesteTAS e Guia HUD (*Celeste* & *Cuphead*)**
- [ ] **Etapa Final (Última Coisa) — Envio do PDF no AVA (até 22/11/2026) e Pitch Oral (a partir de 25/11/2026)**

---

## 1. Identidade, Equipe e Entregáveis

* **Nome do software / pesquisa:** **StratGraph** ([KairoHenrique/StratGraph](https://github.com/KairoHenrique/StratGraph)).
* **Autores e ordem oficial no artigo (ordem alfabética):**
  1. `Heitor Henrique Zonho` (UFCI-MG)
  2. `Kairo Henrique Ferreira Martins` (UFCI-MG)
  3. `Michel Pires da Silva` (UFCI-MG — **último autor obrigatório**)
* **Licenciamento:** **MIT License** em [LICENSE](../LICENSE) com os dois autores alunos (`Copyright (c) 2026 Heitor Henrique Zonho, Kairo Henrique Ferreira Martins`).
* **Compatibilidade Multiplataforma (Linux Ubuntu 24.04 e Windows):**
  * Núcleo `src/` em **Python 3.12 usando exclusivamente a biblioteca padrão** (`argparse`, `collections`, `csv`, `dataclasses`, `heapq`, `json`, `math`, `pathlib`, `sys`, `time`) — roda nativamente no Ubuntu 24.04 (`python3`) e no Windows (`python`) sem compilação ou pacotes externos em produção.
  * Todos os caminhos tratados com `pathlib.Path`, leitura/escrita CSV com `encoding="utf-8"` e `newline=""`, e saída de terminal protegida para UTF-8 no Windows (`sys.stdout.reconfigure`).

---

## 2. Estrutura Consolidada no Repositório

* Raiz: [README.md](../README.md), [LICENSE](../LICENSE), [requirements-dev.txt](../requirements-dev.txt), [.gitignore](../.gitignore).
* Documentação (`docs/`): [INDICE.md](INDICE.md), [arquitetura_e_modelagem.md](arquitetura_e_modelagem.md), [execucao_linux_windows.md](execucao_linux_windows.md), [plano_implementacao.md](plano_implementacao.md), [pratica (1).pdf](pratica%20(1).pdf).
* Código principal (`src/`): [models.py](../src/models.py), [loader.py](../src/loader.py), [preprocessing.py](../src/preprocessing.py), [layered_graph.py](../src/layered_graph.py), [algorithms.py](../src/algorithms.py), [metrics.py](../src/metrics.py), [main.py](../src/main.py).
* Datasets (`datasets/`): [ESQUEMA_DATASET.md](../datasets/ESQUEMA_DATASET.md), `sample_toy/`, `celeste/` (8 capítulos oficiais), `cuphead/` (6 fases *Run-and-Gun*), `synthetic/` (7 instâncias `v_0015` a `v_5000`).
* Scripts e testes: [export_gephi.py](../scripts/export_gephi.py), [extract_celeste_maps.py](../scripts/extract_celeste_maps.py), [extract_cuphead_maps.py](../scripts/extract_cuphead_maps.py), [generate_benchmarks.py](../scripts/generate_benchmarks.py), [run_experiments.py](../scripts/run_experiments.py), [plot_results.py](../scripts/plot_results.py), [simulate_route.py](../scripts/simulate_route.py), [export_celeste_tas.py](../scripts/export_celeste_tas.py), [build_mods.py](../scripts/build_mods.py), [test_pipeline.py](../tests/test_pipeline.py).
* Artigo IEEE (`article/`): [main.tex](../article/main.tex), [references.bib](../article/references.bib), [GUIA_OVERLEAF.md](../article/GUIA_OVERLEAF.md), `figures/` (`fluxograma_proposta`, `comparacao_custos`, `escalabilidade_tempo`, `contracao_becos` em `.pdf` e `.png`).

---

## 3. Fases de Execução (Detalhamento do Progresso)

### Fase 1 — Fechamento da Modelagem (Concluída)
- [x] **Contração de becos sem saída ([src/preprocessing.py](../src/preprocessing.py)):**
  * Implementada `contract_dead_ends` para fundir salas `COLETAVEL` originais (sem `possui_arma`) conectadas exclusivamente a um único vizinho bidirecional $B$ (não `INICIO`, `FIM` ou `ARMA`), somando custo de ida e volta às arestas de entrada de $B$, transferindo o valor do coletável e registrando auditoria em `contracted_into[B]`.
  * Flag `--no-contract` implementada em [src/main.py](../src/main.py) para permitir ablação via CLI.
- [x] **Prevenção de dupla contagem entre camadas ([src/algorithms.py](../src/algorithms.py)):**
  * `evaluate_path` e `run_dfs_branch_and_bound` controlam salas já pontuadas (`seen_rooms_for_discount` / `seen_rooms`) e contabilizam itens únicos via `collected_room_ids` (`set`), incluindo salas contraídas via `contracted_into`.
- [x] **Papel distinto dos 3 algoritmos:**
  * **BFS ($O(V + E)$):** `run_bfs` como *baseline* de menor número de transições (ignora pesos e `ARMA`).
  * **DFS *Branch-and-Bound*:** `run_dfs_branch_and_bound` com ordenação por menor peso efetivo, poda por limite superior (`best_eff_cost`), controle de `seen_rooms` e `--bnb-timeout` (`timeout_seconds`).
  * **Dijkstra no Grafo em Camadas ($O((V + E)\log V)$):** `run_dijkstra` usando `heapq` sobre a função estritamente positiva:
    $$w(u, v, k) = \frac{\text{TempoBase}(u, v) + \text{Dificuldade}(u, v, k)}{1 + \alpha \cdot \text{ValorColetavel}(v)}, \quad \alpha > 0$$

### Fase 2 — Loader, Pré-processamento e Grafo em Camadas (Concluída)
- [x] [src/models.py](../src/models.py): dataclasses `RoomType`, `Vertex`, `Edge`, `LayeredNode`, `LayeredEdge`, `GameGraph` e `RouteResult`.
- [x] [src/loader.py](../src/loader.py): `load_graph_from_csv` com leitura UTF-8 de `vertices.csv` e `arestas.csv`, validação de tipos/valores, verificação de `INICIO`/`FIM` e expansão de `mao_dupla = 1`.
- [x] [src/preprocessing.py](../src/preprocessing.py): `contract_dead_ends` preservando auditoria em `contracted_into` e `original_collectibles`.
- [x] [src/layered_graph.py](../src/layered_graph.py): `compute_effective_weight` ($w > 0$) e `build_layered_graph` criando camadas `0` e `1` e transição de custo zero $(u_{\text{arma}}, 0) \to (u_{\text{arma}}, 1)$.

### Fase 3 — Algoritmos, Métricas e CLI Multiplataforma (Concluída)
- [x] [src/algorithms.py](../src/algorithms.py): `run_bfs`, `run_dijkstra` e `run_dfs_branch_and_bound`.
- [x] [src/metrics.py](../src/metrics.py) e [src/main.py](../src/main.py): tabela comparativa no terminal (Linux/Windows) exibindo custo real, peso efetivo, coletáveis únicos, uso da camada armada, estados visitados, tempo (`ms`) e rotas, além de exportação `--output-csv` e `--output-json`.

### Fase 4 — Datasets Reais (*Celeste*, *Cuphead*), Sintéticos e Zenodo (Concluída)
- [x] ***Celeste* ([scripts/extract_celeste_maps.py](../scripts/extract_celeste_maps.py)):** extração direta dos arquivos binários oficiais `BinaryPacker` (`.bin`) da instalação Steam local (`D:\SteamLibrary\steamapps\common\Celeste\Content\Maps\`), gerando todos os **8 capítulos principais** em `datasets/celeste/` (`1_forsaken_city` a `9_core`) com conectividade filtrada por passagens livres em `<solids>`, coletáveis e obstáculos reais.
- [x] ***Cuphead* ([scripts/extract_cuphead_maps.py](../scripts/extract_cuphead_maps.py)):** extração direta das cenas binárias Unity `SerializedFile` v17 (`level41` a `level46`) da instalação Steam local (`D:\SteamLibrary\steamapps\common\Cuphead\Cuphead_Data\`), gerando todas as **6 fases *Run-and-Gun*** em `datasets/cuphead/` (`1_1f_forest_follies` a `3_2f_rugged_ridge`) com setores, plataformas, *spawners* de inimigos e as 5 moedas douradas (`Level_Coin`).
- [x] **Sintéticos ([scripts/generate_benchmarks.py](../scripts/generate_benchmarks.py)):** geração determinística (`seed=42`) em `datasets/synthetic/` com $V \in \{15, 30, 60, 150, 500, 1500, 5000\}$ (20% em becos sem saída).
- [x] **Publicação externa (Zenodo):** dataset publicado oficialmente em https://zenodo.org/records/24147071 com DOI permanente `10.5281/zenodo.24147071` (https://doi.org/10.5281/zenodo.24147071), devidamente citado em `dataset_zenodo` de [article/references.bib](../article/references.bib).

### Fase 5 — Experimentos, Figuras e Fluxograma Obrigatório (Concluída)
- [x] **Bateria experimental ([scripts/run_experiments.py](../scripts/run_experiments.py)):** executada nos 21 datasets (8 *Celeste*, 6 *Cuphead*, 7 sintéticos) com $\alpha = 0{,}05$, ablação `--no-contract`, mediana de 5 repetições e *timeout* de 150 ms no DFS B&B, exportando `results/benchmark_summary.csv` e `results/benchmark_summary.json`.
- [x] **Sensibilidade de $\alpha$ e ablação `--no-contract` ([scripts/run_experiments.py](../scripts/run_experiments.py)):** executada para $\alpha \in \{0.0, 0.02, 0.05, 0.10, 0.25, 0.50\}$, exportando `results/alpha_sensitivity.csv` e `results/alpha_sensitivity.json`.
- [x] **Figuras e fluxograma ([scripts/plot_results.py](../scripts/plot_results.py)):** gerados em `.pdf` e `.png` dentro de `article/figures/`:
  1. `fluxograma_proposta.pdf` / `.png` (**fluxograma obrigatório** da metodologia);
  2. `comparacao_custos.pdf` / `.png` (BFS vs. Dijkstra em *Celeste* e *Cuphead*);
  3. `escalabilidade_tempo.pdf` / `.png` (tempo mediano em ms × $|V|$ em escala log-log);
  4. `contracao_becos.pdf` / `.png` (redução de vértices $|V| \to |V'|$);
  5. `sensibilidade_alpha.pdf` / `.png` (curva de itens coletados e peso efetivo vs. $\alpha$ com e sem contração).

### Fase 6 — Artigo IEEE e Pacotes de Entrega (Código/LaTeX Prontos)
- [x] Artigo completo em [article/main.tex](../article/main.tex) com as 3 tabelas experimentais reais (`tab:celeste`, `tab:cuphead`, `tab:sinteticos`) 100% sincronizadas com `results/benchmark_summary.csv`, análise de sensibilidade de $\alpha$ e ablação `--no-contract` (`fig:sensibilidade`), resumo verificado (217 palavras, limite de 250) e DOI publicado `10.5281/zenodo.24147071` em [article/references.bib](../article/references.bib).
- [x] Script empacotador [scripts/package_deliverables.py](../scripts/package_deliverables.py) gerando `results/stratgraph_overleaf.zip` (pronto para upload no Overleaf) e `results/stratgraph_datasets_zenodo.zip` (publicado no Zenodo em https://zenodo.org/records/24147071).
- [ ] Subir `results/stratgraph_overleaf.zip` no **Overleaf**, validar referências no Google Scholar (`scholar.google.com`) e compilar o PDF.
- [ ] Testar a execução final via terminal em **Linux (Ubuntu 24.04)**.

### Fase 7 — Visualização no Gephi (.gexf), Simulador Visual 2D, CelesteTAS (`.tas`) e Guia HUD (Concluída)
* **Extensões visuais e de validação:**
  - [x] **Exportador de Grafos Gephi (.gexf) ([scripts/export_gephi.py](../scripts/export_gephi.py) → [docs/gephi_guia.md](gephi_guia.md)):** exportação automatizada no formato oficial GEXF 1.2 com 66 grafos individuais (`_base.gexf`, `_optimal_route.gexf`, `_layered.gexf`) e grafos panorâmicos unificados por jogo ([stratgraph_celeste_all.gexf](../results/gephi/stratgraph_celeste_all.gexf) com 429 nós e [stratgraph_cuphead_all.gexf](../results/gephi/stratgraph_cuphead_all.gexf) com 152 nós), permitindo inspecionar no Gephi 0.9/0.10 os nós coloridos e rotas ótimas destacadas.
  - [x] **Pathfinding Físico Intra-Sala ([scripts/extract_celeste_maps.py](../scripts/extract_celeste_maps.py) e [scripts/extract_cuphead_maps.py](../scripts/extract_cuphead_maps.py)):** simulação do deslocamento do player bloco a bloco ($A^*$ no grid 8×8 de colisão `<solids>`, plataformas `jumpThru`, molas `spring` e impulsos `booster`/`zipMover` em *Celeste*; cadeia de plataformas e moedas em *Cuphead*), gerando `tempo_base`, `dificuldade` e os `waypoints.json` não-letais de cada transição.
  - [x] **Simulador Visual Interativo 2D ([scripts/simulate_route.py](../scripts/simulate_route.py)):** gera a aplicação interativa HTML5 Canvas autocontida (`results/stratgraph_simulator.html`) animando o player ao longo dos waypoints físicos dentro das salas reais para **BFS ($L_0$)** vs. **Dijkstra `--no-contract`** vs. **StratGraph ($L_0 \to L_1$ + contração de becos)**.
  - [x] **Exportação CelesteTAS 60 FPS ([scripts/export_celeste_tas.py](../scripts/export_celeste_tas.py) → [tas/celeste/](../tas/celeste/README_CELESTETAS.md)):** traduz as rotas ótimas (`stratgraph` vs `bfs`) dos 8 capítulos de *Celeste* em 16 scripts `.tas` (60 FPS) compatíveis com **Everest + CelesteTAS (`CelesteStudio.exe`)**, utilizando rótulos `#lvl_<sala>` e âncoras `console load <id> <sala>` sob `Unsafe` para inspeção segmentada mantendo `Celeste.exe` vanilla intacto.
  - [x] **Mods Opcionais de Guia Visual HUD ([mods/cuphead_stratgraph/](../mods/cuphead_stratgraph/StratGraphCupheadHud.cs) e [scripts/build_mods.py](../scripts/build_mods.py)):** overlay HUD opcional em C#/.NET (`[F5]` oculta/mostra HUD e `[F6]` alterna StratGraph vs BFS) para conferência visual humana no *Cuphead* (que não possui motor TAS).

### Etapa Final (Última Coisa a Fazer)
- [ ] Revisar/gerar o **PDF final no Overleaf** e enviar no **AVA até 22/11/2026**.
- [ ] Preparar e ensaiar o **Pitch oral de 10 minutos sem slides** (a partir de **25/11/2026**).

---

## 4. Plano de Verificação

* **Testes automatizados executados (`python -m pytest -v` no Windows, Python 3.12.10):**
  * [x] `tests/test_pipeline.py` com **15/15 testes aprovados** (100% *offline*, ~5.5s): modelos base, leitura CSV e contração de becos em `datasets/sample_toy`, positividade de $w(u, v, k)$, prevenção de dupla contagem entre camadas, execução via CLI (`--output-csv` e `--output-json`), validação dos **8 capítulos de *Celeste***, validação das **6 fases *Run-and-Gun* de *Cuphead***, validação dos **7 benchmarks sintéticos** (`v_0015` a `v_5000`), existência dos resultados/figuras em `article/figures/`, exportação do simulador/mods, geração e validação dos **16 arquivos CelesteTAS (`.tas`)**, síntese ao vivo do Capítulo 1 e validação XML/atributos da exportação **Gephi (.gexf)** incluindo grafos unificados dedicados.
* **Validação multiplataforma pendente:**
  * [ ] Rodar `python3 -m src.main --dataset datasets/sample_toy` e `python3 -m pytest -v` nativamente no **Linux (Ubuntu 24.04)**.

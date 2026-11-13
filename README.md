# StratGraph

Otimização de rotas estratégicas em mapas de jogos digitais modelados como **Dígrafos Ponderados Expandidos em Camadas**, equilibrando tempo/dificuldade física de travessia, desvio estratégico para obtenção de arma (*power-up* $L_0 \to L_1$) e coleta de itens com execução estilo **TAS (*Tool-Assisted Speedrun*)**.

> Trabalho Final da disciplina **Estruturas em Árvores e Teoria dos Grafos** (Prof. Michel Pires da Silva — UFCI-MG).
>
> * **Autores:** Heitor Henrique Zonho, Kairo Henrique Ferreira Martins e Michel Pires da Silva
> * **Repositório Oficial (GitHub):** https://github.com/KairoHenrique/StratGraph
> * **Dataset Oficial Publicado (Zenodo):** https://doi.org/10.5281/zenodo.24147071 (`https://zenodo.org/records/24147071`)

## Estrutura do Repositório

```text
├── src/                  # Núcleo algorítmico em Python 3.12 (apenas biblioteca padrão)
├── docs/                 # Documentação técnica, modelagem matemática e guias de execução
├── datasets/             # Mapas tratados em CSV (Celeste, Cuphead e benchmarks sintéticos)
├── scripts/              # Extratores A* físicos, benchmarks, gráficos, simulador 2D, exportador TAS e mods
├── tas/                  # Scripts CelesteTAS (.tas, 60 FPS) por capítulo para validação no Everest / Celeste Studio
├── mods/                 # Mods C# opcionais de HUD visual (F5/F6) — foco em guia visual manual (Cuphead / legado)
├── tests/                # Testes unitários e de integração automatizados (17 testes 100% offline)
├── results/              # Resultados experimentais (CSV/JSON), simulador HTML5, pacotes .zip e Gephi
│   └── gephi/            # 66 grafos GEXF + grafos unificados (Celeste, Cuphead e Geral)
└── article/              # Artigo científico LaTeX (IEEE Conference Template), referências e figuras
```

Consulte [docs/plano_implementacao.md](docs/plano_implementacao.md) para o plano completo, [docs/INDICE.md](docs/INDICE.md) para o índice de documentos, [docs/arquitetura_e_modelagem.md](docs/arquitetura_e_modelagem.md) para a modelagem matemática, [docs/gephi_guia.md](docs/gephi_guia.md) para o guia do Gephi, [docs/roteiro_defesa_pitch.md](docs/roteiro_defesa_pitch.md) para o roteiro da apresentação oral de 10 min e [docs/execucao_linux_windows.md](docs/execucao_linux_windows.md) para o guia de execução.

## Execução Multiplataforma (Linux Ubuntu 24.04 e Windows)

O núcleo do **StratGraph** (`src/`) é **100% genérico, agnóstico a jogos ou engines** e utiliza **exclusivamente a biblioteca padrão do Python 3.12**, funcionando tanto no **Linux (Ubuntu 24.04)** quanto no **Windows** sem compilação ou dependências externas sobre qualquer dataset no formato `vertices.csv` e `arestas.csv`:

```bash
# Linux (Ubuntu 24.04)
python3 -m src.main --dataset datasets/sample_toy --alpha 0.5
python3 -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05
python3 -m src.main --dataset datasets/cuphead/1_1f_forest_follies --alpha 0.05

# Windows (PowerShell / CMD)
python -m src.main --dataset datasets/sample_toy --alpha 0.5
python -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05
python -m src.main --dataset datasets/cuphead/1_1f_forest_follies --alpha 0.05
```

## Visualização de Grafos no Gephi (.gexf)

O StratGraph exporta automaticamente os dígrafos ponderados em camadas para o formato padrão **GEXF 1.2** ([`scripts/export_gephi.py`](scripts/export_gephi.py)), 100% compatível com **Gephi 0.9.x e 0.10.x**, com nós coloridos por papel funcional (`INICIO`, `FIM`, `ARMA`, `COLETAVEL`, `COMUM`), layout 2D topológico sem sobreposição e arestas da rota ótima destacadas em laranja:

* **Grafos Unificados por Jogo:**
  * [`results/gephi/stratgraph_celeste_all.gexf`](results/gephi/stratgraph_celeste_all.gexf): os **8 capítulos de *Celeste*** reunidos em grade (429 nós, 827 arestas).
  * [`results/gephi/stratgraph_cuphead_all.gexf`](results/gephi/stratgraph_cuphead_all.gexf): as **6 fases *Run-and-Gun* de *Cuphead*** reunidas em grade (152 nós, 300 arestas).
  * [`results/gephi/stratgraph_unified_all.gexf`](results/gephi/stratgraph_unified_all.gexf): todos os 22 datasets reunidos em grade panorâmica geral.
* **Trio por Fase/Instância Individual (66 arquivos):** para cada dataset em `datasets/`, gera `<instancia>_base.gexf`, `<instancia>_optimal_route.gexf` e `<instancia>_layered.gexf` (espaço em camadas $L_0 \to L_1$ com transição intercamadas).
* **Comandos CLI para Exportação:**
  ```bash
  python -m scripts.export_gephi --all       # Exporta todos os 66 grafos individuais + unificados
  python -m scripts.export_gephi --celeste   # Exporta apenas Celeste unificado
  python -m scripts.export_gephi --cuphead   # Exporta apenas Cuphead unificado
  python -m scripts.export_gephi --unified   # Exporta todos os grafos unificados
  ```
Consulte o [Guia de Visualização no Gephi](docs/gephi_guia.md) para instruções passo a passo de como abrir, configurar e apresentar na banca.

## Simulador Visual 2D, Exportação CelesteTAS e Guia HUD (*Celeste* & *Cuphead*)

> **Nota para avaliação acadêmica:** O avaliador **não** precisa dos jogos, Everest ou CelesteTAS instalados. Todo o motor em Python (`src/`), os grafos extraídos (`datasets/`) e os testes (`tests/`) rodam integralmente *offline* no terminal Ubuntu 24.04 / Windows.

* **Simulador Visual Interativo 2D (HTML5 Canvas — Linux e Windows):**
  Anima os agentes de **BFS**, **DFS *Branch-and-Bound***, **Dijkstra `--no-contract`** e **StratGraph ($L_0 \to L_1$ + Contração de Becos)** percorrendo os *waypoints* físicos reais ($A^*$ em espaço de estados no grid 8×8 `<solids>` de *Celeste* e plataformas de *Cuphead*):
  ```bash
  python -m scripts.simulate_route --open
  ```
* **Exportação CelesteTAS 60 FPS ([`scripts/export_celeste_tas.py`](scripts/export_celeste_tas.py) → [`tas/celeste/`](tas/celeste/README_CELESTETAS.md)):**
  Converte as rotas ótimas (`stratgraph` vs `bfs`) dos 8 capítulos de *Celeste* em arquivos `.tas` (60 FPS) validados sintaticamente para uso no **Everest + CelesteTAS (`CelesteStudio.exe`)**, utilizando rótulos `#lvl_<sala>` e âncoras `console load <id> <sala>` (`Unsafe`) por segmento de sala:
  ```bash
  python -m scripts.export_celeste_tas
  ```
* **Sintetizador Closed-Loop Ao Vivo para Capítulo 1 ([`scripts/solve_live_celeste_tas.py`](scripts/solve_live_celeste_tas.py) + [`scripts/celeste_sim.py`](scripts/celeste_sim.py)):**
  Executa a rota do **StratGraph** passo a passo contra o **Everest + CelesteTAS DebugRC** (`http://localhost:32270/`) com horizonte deslizante a 60 FPS, `SaveState`/`ClearState` rolantes, regra real de 1 *dash* (incluindo proibição em morangos alados), colisão real e poda imediata de mortes. No teste completo do Capítulo 1 (`1_forsaken_city` → artefato dedicado [`tas/celeste/1_forsaken_city_live.tas`](tas/celeste/1_forsaken_city_live.tas) e relatório [`results/live_celeste_ch1_validation.json`](results/live_celeste_ch1_validation.json), separados das exportações *offline* `*_{bfs,stratgraph}.tas`), percorreu todas as **51 visitas de sala** até `lvl_end` em **16.492 quadros** com **0 mortes**, **26 transições contínuas**, **24 retomadas limpas via `console load`** e **4 morangos confirmados no motor**:
  ```bash
  python -m scripts.solve_live_celeste_tas --chapter 1_forsaken_city --alpha 0.05
  ```
* **Mod Opcional de Guia Visual HUD *In-Game* (Steam / Windows — foco *Cuphead*):**
  Como *Cuphead* não possui ferramenta equivalente ao *CelesteTAS*, [`mods/cuphead_stratgraph/`](mods/cuphead_stratgraph/StratGraphCupheadHud.cs) oferece desenho passivo da rota na tela (`F5` exibe/oculta HUD e `F6` alterna `StratGraph` vs `BFS`). Para *Celeste*, mantenha o binário vanilla restaurado ao usar **Everest + CelesteTAS**:
  ```powershell
  # Compilar DLLs / instalar HUD e garantir Celeste.exe vanilla limpo para Everest + CelesteTAS
  python -m scripts.build_mods
  python -m scripts.build_mods --uninstall-celeste
  ```

### Dependências opcionais (gráficos do artigo e testes)

```bash
pip install -r requirements-dev.txt
python -m pytest -v    # 17 testes automatizados (100% offline; gera results/ se ausente em clone limpo)
```

## Resultados Experimentais (14 Fases Reais, $\alpha = 0{,}05$)

Graças à **contração topológica iterativa de becos sem saída** (`contract_dead_ends`), **BFS**, **DFS *Branch-and-Bound*** e **StratGraph (Dijkstra em Camadas $L_0 \to L_1$)** capturam **100% dos coletáveis nas 14 fases reais** (onde os itens opcionais ficam em alcovas terminais ou sobre o eixo percorrido; em grafos sintéticos com ciclos paralelos, garante-se cobertura integral apenas das folhas terminais associadas aos vértices visitados). Mesmo comparando pelo **Custo Real** bruto (sem ponderação por $\alpha$), o StratGraph reduz expressivamente o custo de travessia frente ao BFS:

| Instância (*Celeste* / *Cuphead*) | $\|V\| \to \|V'\|$ | BFS Real | StratGraph Real (Red. Real) | BFS Efetivo | StratGraph Efetivo (Red. $w$) | Itens (`B/D/--no-contract`) | Tempo Dijkstra |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| *Celeste* `1_forsaken_city` | $38 \to 21$ | 746,7 | **664,1** (**-11,1%**) | 533,11 | **466,51** (-12,5%) | **21 / 21** / 9 | 0,045 ms |
| *Celeste* `2_old_site` | $33 \to 9$ | 2.440,5 | **1.385,2** (**-43,2%**) | 845,38 | **472,96** (-44,1%) | **18 / 18** / 1 | 0,022 ms |
| *Celeste* `3_celestial_resort` | $65 \to 23$ | 2.540,4 | **1.456,2** (**-42,7%**) | 989,27 | **545,49** (-44,9%) | **24 / 24** / 7 | 0,056 ms |
| *Celeste* `4_golden_ridge` | $49 \to 35$ | 1.549,2 | **1.019,0** (**-34,2%**) | 936,94 | **557,80** (-40,5%) | **29 / 29** / 16 | 0,089 ms |
| *Celeste* `5_mirror_temple` | $45 \to 15$ | 1.981,7 | **1.234,0** (**-37,7%**) | 742,08 | **442,91** (-40,3%) | **22 / 22** / 1 | 0,041 ms |
| *Celeste* `6_reflection` | $63 \to 48$ | 910,5 | **447,3** (**-50,9%**) | 882,59 | **419,39** (-52,5%) | **2 / 2** / 0 | 0,117 ms |
| *Celeste* `7_summit` | $97 \to 63$ | 3.308,3 | **1.715,6** (**-48,1%**) | 2.395,30 | **1.229,26** (-48,7%) | **41 / 41** / 19 | 0,174 ms |
| *Celeste* `9_core` | $39 \to 30$ | 835,3 | **497,4** (**-40,4%**) | 651,12 | **343,94** (-47,2%) | **7 / 7** / 2 | 0,081 ms |
| *Cuphead* `1_1f_forest_follies` | $26 \to 21$ | 611,5 | **267,7** (**-56,2%**) | 490,90 | **210,04** (-57,2%) | **5 / 5** / 0 | 0,064 ms |
| *Cuphead* `1_2f_treetop_trouble` | $26 \to 21$ | 1.478,5 | **497,2** (**-66,4%**) | 1.252,62 | **402,21** (-67,9%) | **5 / 5** / 0 | 0,063 ms |
| *Cuphead* `2_1f_funfair_fever` | $26 \to 21$ | 577,9 | **257,8** (**-55,4%**) | 461,91 | **205,22** (-55,6%) | **5 / 5** / 0 | 0,073 ms |
| *Cuphead* `2_2f_funhouse_frazzle` | $26 \to 21$ | 2.100,5 | **666,9** (**-68,3%**) | 1.662,24 | **532,88** (-67,9%) | **5 / 5** / 0 | 0,061 ms |
| *Cuphead* `3_1f_perilous_piers` | $22 \to 17$ | 1.246,4 | **411,3** (**-67,0%**) | 968,22 | **320,71** (-66,9%) | **5 / 5** / 0 | 0,038 ms |
| *Cuphead* `3_2f_rugged_ridge` | $26 \to 21$ | 1.268,1 | **540,5** (**-57,4%**) | 1.059,72 | **429,17** (-59,5%) | **5 / 5** / 0 | 0,060 ms |

## Licença

Este projeto é distribuído sob a licença **MIT** — veja o arquivo [LICENSE](LICENSE) para mais detalhes.

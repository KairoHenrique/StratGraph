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
├── scripts/              # Extratores A* físicos, benchmarks, gráficos, simulador 2D e builder de mods
├── mods/                 # Mods C# In-Game com HUD e Bot TAS (F5/F6) para Celeste e Cuphead
├── tests/                # Testes unitários e de integração (12 testes automatizados)
├── results/              # Resultados experimentais (CSV/JSON), simulador HTML5 e pacotes .zip
└── article/              # Artigo científico LaTeX (IEEE Conference Template), referências e figuras
```

Consulte [docs/plano_implementacao.md](docs/plano_implementacao.md) para ver o plano completo do projeto, [docs/INDICE.md](docs/INDICE.md) para a lista de documentos, [docs/arquitetura_e_modelagem.md](docs/arquitetura_e_modelagem.md) para a modelagem matemática e [docs/execucao_linux_windows.md](docs/execucao_linux_windows.md) para o guia completo de execução.

## Execução Multiplataforma (Linux Ubuntu 24.04 e Windows)

O núcleo do **StratGraph** (`src/`) utiliza **exclusivamente a biblioteca padrão do Python 3.12**, funcionando tanto no **Linux (Ubuntu 24.04)** quanto no **Windows** sem compilação ou dependências externas:

```bash
# Linux (Ubuntu 24.04)
python3 -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05

# Windows (PowerShell / CMD)
python -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05
```

## Calibração de Física & Cache (`datasets/`)

Na primeira execução (ou com `--force`), o calibrador extrai e valida as constantes físicas reais de **Celeste** (1 dash por salto, gravidade/pulo, ancoragem de piso e desvio não-letal de espinhos/spinners em A* de espaço de estados) e **Cuphead** (plataformas, saltos segurados e moedas), salvando `datasets/physics_calibration.json` e os `waypoints.json`. Nas execuções seguintes, o cache em `datasets/` é reutilizado automaticamente sem recalibrar:

```powershell
# Reutiliza calibração em cache se já existir em datasets/physics_calibration.json
python -m scripts.calibrate_physics

# Força recalibração completa e regeneração dos datasets
python -m scripts.calibrate_physics --force
```

## Simulador Visual 2D TAS e Mods *In-Game* (*Celeste* & *Cuphead*)

* **Simulador Visual Interativo 2D (HTML5 Canvas — Linux e Windows):**
  Anima os agentes de **BFS**, **DFS *Branch-and-Bound***, **Dijkstra `--no-contract`** e **StratGraph ($L_0 \to L_1$ + Contração de Becos)** percorrendo os *waypoints* físicos reais ($A^*$ em espaço de estados no grid 8×8 `<solids>` de *Celeste* e plataformas de *Cuphead*):
  ```bash
  python -m scripts.simulate_route --open
  ```
* **Mods de Teste *In-Game* com Bot TAS Sem Trapaças (Steam / Windows):**
  Compila os mods em C# ([`mods/celeste_stratgraph/`](mods/celeste_stratgraph/StratGraphCelesteHud.cs) e [`mods/cuphead_stratgraph/`](mods/cuphead_stratgraph/StratGraphCupheadHud.cs)) e instala nos binários da Steam (com backup automático `.stratgraph.bak`). O bot injeta controles reais (incluindo pulo segurado via `VirtualButton.get_Check` / Rewired e escalada dentro da estamina, com **dano/morte reais e apenas 1 dash**). Dentro do jogo, **`F5`** liga/desliga o **Bot TAS** e **`F6`** alterna ao vivo entre a **Rota StratGraph ($L_0 \to L_1$)** e a **Rota BFS ($L_0$)** (ambas coletando os itens):
  ```powershell
  # Compilar e instalar nos jogos da Steam (calibra caso ainda não esteja em cache)
  python -m scripts.build_mods --install-games

  # Forçar recalibração + recompilar mods
  python -m scripts.build_mods --calibrate --install-games

  # Restaurar binários originais da Steam quando desejar
  python -m scripts.build_mods --uninstall-games
  ```

### Dependências opcionais (gráficos do artigo e testes)

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

## Resultados Experimentais (Coleta 100% — *All Collectibles TAS*, $\alpha = 0{,}05$)

Graças à **contração topológica iterativa de becos sem saída** (`contract_dead_ends`), **BFS**, **DFS *Branch-and-Bound*** e **StratGraph (Dijkstra em Camadas $L_0 \to L_1$)** coletam **literalmente 100% de todos os coletáveis** em cada mapa (enquanto a ablação `--no-contract` perde os itens das ramificações laterais), permitindo uma comparação estritamente justa sob o mesmo objetivo de 100% de coleta:

| Instância (*Celeste* / *Cuphead*) | $\|V\| \to \|V'\|$ | BFS ($L_0$) Efetivo | StratGraph ($L_0 \to L_1$) Efetivo | Redução $w$ (%) | Coletáveis (`BFS / DFS / StratGraph / --no-contract`) | Tempo Dijkstra |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| *Celeste* `1_forsaken_city` | $38 \to 21$ | 533,11 | **466,51** | **-12,5%** | **21 / 21 / 21** / 9 (100%) | 0,055 ms |
| *Celeste* `2_old_site` | $33 \to 9$ | 845,38 | **472,96** | **-44,1%** | **18 / 18 / 18** / 1 (100%) | 0,026 ms |
| *Celeste* `3_celestial_resort` | $65 \to 23$ | 989,27 | **545,49** | **-44,9%** | **24 / 24 / 24** / 7 (100%) | 0,054 ms |
| *Celeste* `4_golden_ridge` | $49 \to 35$ | 936,94 | **557,80** | **-40,5%** | **29 / 29 / 29** / 16 (100%) | 0,089 ms |
| *Celeste* `5_mirror_temple` | $45 \to 15$ | 742,08 | **442,91** | **-40,3%** | **22 / 22 / 22** / 1 (100%) | 0,051 ms |
| *Celeste* `6_reflection` | $63 \to 48$ | 882,59 | **419,39** | **-52,5%** | **2 / 2 / 2** / 0 (100%) | 0,112 ms |
| *Celeste* `7_summit` | $97 \to 63$ | 2395,30 | **1229,26** | **-48,7%** | **41 / 41 / 41** / 19 (100%) | 0,163 ms |
| *Celeste* `9_core` | $39 \to 30$ | 651,12 | **343,94** | **-47,2%** | **7 / 7 / 7** / 2 (100%) | 0,097 ms |
| *Cuphead* `1_1f_forest_follies` | $26 \to 21$ | 490,90 | **210,04** | **-57,2%** | **5 / 5 / 5** / 0 (100%) | 0,063 ms |
| *Cuphead* `1_2f_treetop_trouble` | $26 \to 21$ | 1252,62 | **402,21** | **-67,9%** | **5 / 5 / 5** / 0 (100%) | 0,087 ms |
| *Cuphead* `2_1f_funfair_fever` | $26 \to 21$ | 461,91 | **205,22** | **-55,6%** | **5 / 5 / 5** / 0 (100%) | 0,073 ms |
| *Cuphead* `2_2f_funhouse_frazzle` | $26 \to 21$ | 1662,24 | **532,88** | **-67,9%** | **5 / 5 / 5** / 0 (100%) | 0,059 ms |
| *Cuphead* `3_1f_perilous_piers` | $22 \to 17$ | 968,22 | **320,71** | **-66,9%** | **5 / 5 / 5** / 0 (100%) | 0,038 ms |
| *Cuphead* `3_2f_rugged_ridge` | $26 \to 21$ | 1059,72 | **429,17** | **-59,5%** | **5 / 5 / 5** / 0 (100%) | 0,072 ms |

## Licença

Este projeto é distribuído sob a licença **MIT** — veja o arquivo [LICENSE](LICENSE) para mais detalhes.

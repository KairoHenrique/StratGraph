# Guia de Execução — Linux (Ubuntu 24.04) e Windows

O núcleo algorítmico do **StratGraph** (`src/`) utiliza **exclusivamente a biblioteca padrão do Python 3.12**, garantindo execução idêntica no **Linux (Ubuntu 24.04)** e no **Windows** sem compilação manual ou dependências externas obrigatórias.

## 1. Linux (Ubuntu 24.04 — Ambiente de Validação)

O Ubuntu 24.04 já inclui o Python 3.12 por padrão:

```bash
# Verificar versão
python3 --version

# Ver opções do CLI
python3 -m src.main --help

# Executar cenário didático ou capítulo real do Celeste / Cuphead
python3 -m src.main --dataset datasets/sample_toy --alpha 0.5
python3 -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05
python3 -m src.main --dataset datasets/cuphead/1_1f_forest_follies --alpha 0.05

# Gerar e abrir o Simulador Visual 2D TAS no navegador
python3 -m scripts.simulate_route --open

# Exportar grafos para Gephi (.gexf) individuais e unificados
python3 -m scripts.export_gephi --all
python3 -m scripts.export_gephi --celeste
python3 -m scripts.export_gephi --cuphead

# Exportar os 16 scripts CelesteTAS (.tas, 60 FPS) para tas/celeste/
python3 -m scripts.export_celeste_tas
```

## 2. Windows (PowerShell / Terminal)

Com Python 3.12 instalado e adicionado ao `PATH`:

```powershell
# Executar um cenário via terminal
python -m src.main --dataset datasets\celeste\1_forsaken_city --alpha 0.05

# Exportar grafos para visualização no Gephi (.gexf)
python -m scripts.export_gephi --all
python -m scripts.export_gephi --celeste
python -m scripts.export_gephi --cuphead

# Abrir o Simulador Visual 2D TAS (HTML5 Canvas)
python -m scripts.simulate_route --open

# Exportar os 16 scripts CelesteTAS (.tas, 60 FPS) para Everest / Celeste Studio
python -m scripts.export_celeste_tas

# Compilar os Mods C# em mods/dist/ e garantir Celeste.exe vanilla limpo (Everest/CelesteTAS)
python -m scripts.build_mods
python -m scripts.build_mods --uninstall-celeste
```

## 3. Divisão de Validação: Professor (*Offline*) vs. Motor Real (*CelesteTAS* Ao Vivo)

* **Parte A — Reprodução 100% *Offline* (Professor / Avaliador, Linux Ubuntu 24.04 ou Windows):**
  Não requer jogos, Everest ou dependências externas para o núcleo (`src/`):
  * `python -m src.main --dataset datasets/celeste/1_forsaken_city --alpha 0.05` (resolução nos grafos CSV)
  * `python -m scripts.run_experiments` (regera `results/benchmark_summary.*` e `results/alpha_sensitivity.*`)
  * `python -m scripts.simulate_route --open` (simulador visual 2D HTML5 em `results/stratgraph_simulator.html`)
  * `python -m scripts.export_celeste_tas` (exporta e valida sintaticamente os 16 `.tas` estruturais `*_{bfs,stratgraph}.tas` sem sobrescrever `tas/celeste/1_forsaken_city_live.tas`)
  * `python -m pytest -v` (**15 testes automatizados 100% *offline***, validando algoritmos, benchmarks, exportador TAS, simulador 60 Hz sintético, exportador Gephi XML e atributos, sintaxe do `.tas` ao vivo e o relatório em `results/live_celeste_ch1_validation.json`).

* **Parte B — Validação Empírica Ao Vivo (*Celeste* + Everest + CelesteTAS DebugRC — Windows):**
  Utilizada pelos autores para gerar/auditar o artefato real [`tas/celeste/1_forsaken_city_live.tas`](../tas/celeste/1_forsaken_city_live.tas) e [`results/live_celeste_ch1_validation.json`](../results/live_celeste_ch1_validation.json) com o jogo aberto em `http://localhost:32270/`:
  ```powershell
  python -m scripts.solve_live_celeste_tas --chapter 1_forsaken_city --alpha 0.05
  ```

## 4. Dependências Opcionais (Gráficos do Artigo e Testes)

Tanto no Linux quanto no Windows, para rodar os 15 testes automatizados e regerar os gráficos do artigo (`scripts/`):

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

*(No Linux, caso necessário, utilize `python3 -m pip` e `python3 -m pytest -v`.)*

## Parâmetros do CLI (`src.main`)

* `--dataset`: diretório contendo `vertices.csv` e `arestas.csv`.
* `--alpha`: fator de importância dos coletáveis (`alpha > 0`, padrão `0.5`).
* `--no-contract`: desativa a contração de becos sem saída no pré-processamento (estudo de ablação).
* `--bnb-timeout`: limite máximo (em segundos) para o DFS *Branch-and-Bound*.
* `--output-csv` / `--output-json`: exporta as métricas e rotas detalhadas para arquivo.

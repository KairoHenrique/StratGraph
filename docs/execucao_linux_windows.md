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

# Exportar os 16 scripts CelesteTAS (.tas, 60 FPS) para tas/celeste/
python3 -m scripts.export_celeste_tas
```

## 2. Windows (PowerShell / Terminal)

Com Python 3.12 instalado e adicionado ao `PATH`:

```powershell
# Executar um cenário via terminal
python -m src.main --dataset datasets\celeste\1_forsaken_city --alpha 0.05

# Abrir o Simulador Visual 2D TAS (HTML5 Canvas)
python -m scripts.simulate_route --open

# Exportar os 16 scripts CelesteTAS (.tas, 60 FPS) para Everest / Celeste Studio
python -m scripts.export_celeste_tas

# Compilar os Mods C# em mods/dist/ e garantir Celeste.exe vanilla limpo (Everest/CelesteTAS)
python -m scripts.build_mods
python -m scripts.build_mods --uninstall-celeste
```

## 3. Dependências Opcionais (Gráficos do Artigo e Testes)

Tanto no Linux quanto no Windows, para rodar os 12 testes automatizados e regerar os gráficos do artigo (`scripts/`):

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

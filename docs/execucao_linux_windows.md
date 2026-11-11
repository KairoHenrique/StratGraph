# Guia de Execução — Linux (Ubuntu 24.04) e Windows

O núcleo algorítmico do **StratGraph** (`src/`) utiliza **exclusivamente a biblioteca padrão do Python 3.12**, garantindo execução idêntica no **Linux (Ubuntu 24.04)** e no **Windows** sem compilação manual ou dependências externas obrigatórias.

## 1. Linux (Ubuntu 24.04 — Ambiente de Validação)

O Ubuntu 24.04 já inclui o Python 3.12 por padrão:

```bash
# Verificar versão
python3 --version

# Ver opções do CLI
python3 -m src.main --help

# Executar um cenário via terminal (após conclusão das Fases 2 e 3)
python3 -m src.main --dataset datasets/sample_toy --alpha 0.5
```

## 2. Windows (PowerShell / Terminal)

Com Python 3.12 instalado e adicionado ao `PATH`:

```powershell
# Verificar versão
python --version

# Ver opções do CLI
python -m src.main --help

# Executar um cenário via terminal (após conclusão das Fases 2 e 3)
python -m src.main --dataset datasets\sample_toy --alpha 0.5
```

## 3. Dependências Opcionais (Gráficos do Artigo e Testes)

Tanto no Linux quanto no Windows, para rodar testes automatizados e gerar os gráficos do artigo (`scripts/`):

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```

*(No Linux, caso necessário, utilize `python3 -m pip` e `python3 -m pytest -v`.)*

## Parâmetros do CLI

* `--dataset`: diretório contendo `vertices.csv` e `arestas.csv`.
* `--alpha`: fator de importância dos coletáveis (`alpha > 0`, padrão `0.5`).
* `--no-contract`: desativa a contração de becos sem saída no pré-processamento.
* `--bnb-timeout`: limite máximo (em segundos) para o DFS *Branch-and-Bound*.


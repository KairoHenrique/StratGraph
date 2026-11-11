"""Ponto de entrada CLI multiplataforma (Linux Ubuntu 24.04 e Windows) do StratGraph."""

import argparse
import sys


def _configure_stdio() -> None:
    """Garante saída UTF-8 segura no terminal do Windows e Linux."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    """Configura os argumentos de linha de comando do StratGraph."""
    parser = argparse.ArgumentParser(
        prog="stratgraph",
        description="StratGraph: roteamento estratégico em jogos via Grafo Ponderado em Camadas.",
    )
    parser.add_argument("--dataset", required=True, help="Diretório contendo vertices.csv e arestas.csv")
    parser.add_argument("--alpha", type=float, default=0.5, help="Fator de importância dos coletáveis (alpha > 0)")
    parser.add_argument("--no-contract", action="store_true", help="Desativa contração de becos sem saída")
    parser.add_argument("--bnb-timeout", type=float, default=10.0, help="Limite em segundos para DFS Branch-and-Bound")
    return parser


def main() -> int:
    """Executa o pipeline completo para o dataset informado."""
    _configure_stdio()
    _ = build_parser().parse_args()
    raise NotImplementedError("Pipeline CLI a ser conectado na Fase 3.")


if __name__ == "__main__":
    raise SystemExit(main())

"""Ponto de entrada CLI multiplataforma (Linux Ubuntu 24.04 e Windows) do StratGraph."""

import argparse
from pathlib import Path
import sys

from src.algorithms import run_bfs, run_dfs_branch_and_bound, run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.metrics import export_results_csv, export_results_json, format_comparison_table
from src.preprocessing import contract_dead_ends


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
    parser.add_argument(
        "--dataset",
        required=True,
        help="Diretório contendo vertices.csv e arestas.csv",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.5,
        help="Fator de importância dos coletáveis (alpha >= 0, padrão: 0.5)",
    )
    parser.add_argument(
        "--no-contract",
        action="store_true",
        help="Desativa a contração de becos sem saída no pré-processamento",
    )
    parser.add_argument(
        "--bnb-timeout",
        type=float,
        default=10.0,
        help="Limite em segundos para DFS Branch-and-Bound (padrão: 10.0)",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="",
        help="Caminho opcional para exportar resultados em CSV",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Caminho opcional para exportar resultados em JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Executa o pipeline completo para o dataset informado."""
    _configure_stdio()
    args = build_parser().parse_args(argv)

    dataset_path = Path(args.dataset)
    raw_graph = load_graph_from_csv(dataset_path)
    num_raw_vertices = len(raw_graph.vertices)

    if args.no_contract:
        working_graph = raw_graph
    else:
        working_graph = contract_dead_ends(raw_graph)

    contracted_count = num_raw_vertices - len(working_graph.vertices)
    layered = build_layered_graph(working_graph, alpha=args.alpha)

    print(f"=== StratGraph | Dataset: {dataset_path} ===")
    print(
        f"Salas originais: {num_raw_vertices} | "
        f"Salas após pré-processamento: {len(working_graph.vertices)} "
        f"(Becos contraídos: {contracted_count}) | "
        f"Alpha: {args.alpha}"
    )

    bfs_res = run_bfs(layered)
    bnb_res = run_dfs_branch_and_bound(
        layered,
        alpha=args.alpha,
        timeout_seconds=args.bnb_timeout,
    )
    dijkstra_res = run_dijkstra(layered)

    results = [bfs_res, bnb_res, dijkstra_res]
    print(format_comparison_table(results))

    if args.output_csv:
        export_results_csv(results, args.output_csv)
        print(f"\nCSV exportado para: {args.output_csv}")
    if args.output_json:
        export_results_json(results, args.output_json)
        print(f"JSON exportado para: {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

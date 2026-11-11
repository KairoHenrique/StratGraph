"""Executa a bateria completa de experimentos do StratGraph (Celeste, Cuphead e Sintéticos).

Consolida as métricas comparativas de BFS, DFS Branch-and-Bound e Dijkstra no
Grafo Expandido em Camadas, além da redução de vértices pela contração de becos
sem saída (`contract_dead_ends`), exportando `results/benchmark_summary.csv` e
`results/benchmark_summary.json`.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics

from src.algorithms import run_bfs, run_dfs_branch_and_bound, run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.preprocessing import contract_dead_ends

ALPHA_DEFAULT = 0.05
ALPHA_GRID = (0.0, 0.02, 0.05, 0.10, 0.25, 0.50)
REPEATS = 5


def evaluate_dataset(category: str, name: str, dataset_dir: Path, alpha: float = ALPHA_DEFAULT) -> dict[str, object]:
    """Executa o pipeline completo sobre um dataset com múltiplas repetições para precisão de tempo."""
    raw_graph = load_graph_from_csv(dataset_dir)
    v_orig = len(raw_graph.vertices)
    e_orig = sum(len(v) for v in raw_graph.adjacency.values())

    # Ablação sem contração de becos (--no-contract)
    layered_no_contract = build_layered_graph(raw_graph, alpha=alpha)
    dijk_no_contract = run_dijkstra(layered_no_contract)

    contracted_graph = contract_dead_ends(raw_graph)
    contracted_count = sum(len(v) for v in contracted_graph.contracted_into.values())
    v_after = len(contracted_graph.vertices)
    e_after = sum(len(v) for v in contracted_graph.adjacency.values())
    layered = build_layered_graph(contracted_graph, alpha=alpha)

    bfs_times: list[float] = []
    dfs_times: list[float] = []
    dijk_times: list[float] = []

    bfs_res = run_bfs(layered)
    dfs_res = run_dfs_branch_and_bound(layered, timeout_seconds=0.15)
    dijk_res = run_dijkstra(layered)

    for _ in range(REPEATS):
        bfs_times.append(run_bfs(layered).elapsed_ms)
        dfs_times.append(run_dfs_branch_and_bound(layered, timeout_seconds=0.15).elapsed_ms)
        dijk_times.append(run_dijkstra(layered).elapsed_ms)

    reduction_pct = round(100.0 * (v_orig - v_after) / max(1, v_orig), 1)
    cost_saving_pct = round(
        100.0 * (bfs_res.real_cost - dijk_res.real_cost) / max(1e-9, bfs_res.real_cost), 1
    )
    eff_saving_pct = round(
        100.0 * (bfs_res.effective_cost - dijk_res.effective_cost) / max(1e-9, bfs_res.effective_cost), 1
    )

    return {
        "category": category,
        "dataset": name,
        "v_orig": v_orig,
        "e_orig": e_orig,
        "v_after": v_after,
        "e_after": e_after,
        "dead_ends_contracted": contracted_count,
        "reduction_pct": reduction_pct,
        "bfs_real_cost": round(bfs_res.real_cost, 2),
        "bfs_eff_cost": round(bfs_res.effective_cost, 2),
        "bfs_items": bfs_res.collectibles_count,
        "bfs_value": round(bfs_res.collectibles_total_value, 1),
        "bfs_states": bfs_res.visited_states,
        "bfs_time_ms": round(statistics.median(bfs_times), 4),
        "dfs_real_cost": round(dfs_res.real_cost, 2),
        "dfs_eff_cost": round(dfs_res.effective_cost, 2),
        "dfs_items": dfs_res.collectibles_count,
        "dfs_value": round(dfs_res.collectibles_total_value, 1),
        "dfs_states": dfs_res.visited_states,
        "dfs_time_ms": round(statistics.median(dfs_times), 4),
        "dijkstra_real_cost": round(dijk_res.real_cost, 2),
        "dijkstra_eff_cost": round(dijk_res.effective_cost, 2),
        "dijkstra_items": dijk_res.collectibles_count,
        "dijkstra_value": round(dijk_res.collectibles_total_value, 1),
        "dijkstra_used_weapon": int(dijk_res.used_weapon),
        "dijkstra_states": dijk_res.visited_states,
        "dijkstra_time_ms": round(statistics.median(dijk_times), 4),
        "no_contract_real_cost": round(dijk_no_contract.real_cost, 2),
        "no_contract_eff_cost": round(dijk_no_contract.effective_cost, 2),
        "no_contract_items": dijk_no_contract.collectibles_count,
        "no_contract_value": round(dijk_no_contract.collectibles_total_value, 1),
        "no_contract_states": dijk_no_contract.visited_states,
        "real_cost_saving_pct": cost_saving_pct,
        "eff_cost_saving_pct": eff_saving_pct,
    }


def evaluate_alpha_sensitivity() -> list[dict[str, object]]:
    """Executa análise de sensibilidade variando alpha em instâncias representativas."""
    targets = [
        ("celeste", "1_forsaken_city", Path("datasets/celeste/1_forsaken_city")),
        ("celeste", "3_celestial_resort", Path("datasets/celeste/3_celestial_resort")),
        ("celeste", "7_summit", Path("datasets/celeste/7_summit")),
        ("cuphead", "1_1f_forest_follies", Path("datasets/cuphead/1_1f_forest_follies")),
        ("cuphead", "2_2f_funhouse_frazzle", Path("datasets/cuphead/2_2f_funhouse_frazzle")),
        ("synthetic", "v_0150", Path("datasets/synthetic/v_0150")),
    ]
    sens_rows: list[dict[str, object]] = []
    for cat, name, ddir in targets:
        if not ddir.exists():
            continue
        raw_graph = load_graph_from_csv(ddir)
        contracted = contract_dead_ends(raw_graph)
        for alpha in ALPHA_GRID:
            layered_c = build_layered_graph(contracted, alpha=alpha)
            layered_nc = build_layered_graph(raw_graph, alpha=alpha)
            dijk_c = run_dijkstra(layered_c)
            dijk_nc = run_dijkstra(layered_nc)
            sens_rows.append(
                {
                    "category": cat,
                    "dataset": name,
                    "alpha": alpha,
                    "contracted_real_cost": round(dijk_c.real_cost, 2),
                    "contracted_eff_cost": round(dijk_c.effective_cost, 2),
                    "contracted_items": dijk_c.collectibles_count,
                    "contracted_value": round(dijk_c.collectibles_total_value, 1),
                    "contracted_states": dijk_c.visited_states,
                    "no_contract_real_cost": round(dijk_nc.real_cost, 2),
                    "no_contract_eff_cost": round(dijk_nc.effective_cost, 2),
                    "no_contract_items": dijk_nc.collectibles_count,
                    "no_contract_value": round(dijk_nc.collectibles_total_value, 1),
                    "no_contract_states": dijk_nc.visited_states,
                }
            )
    return sens_rows


def main() -> int:
    rows: list[dict[str, object]] = []

    for cat, root in [
        ("celeste", Path("datasets/celeste")),
        ("cuphead", Path("datasets/cuphead")),
        ("synthetic", Path("datasets/synthetic")),
    ]:
        if not root.exists():
            continue
        for sub in sorted(p for p in root.iterdir() if p.is_dir()):
            if (sub / "vertices.csv").exists() and (sub / "arestas.csv").exists():
                row = evaluate_dataset(cat, sub.name, sub, alpha=ALPHA_DEFAULT)
                rows.append(row)
                print(
                    f"[{cat:9s}] {sub.name:22s} | V: {row['v_orig']:4d}->{row['v_after']:4d} "
                    f"(-{row['reduction_pct']:4.1f}%) | Itens c/ contr.: {row['dijkstra_items']:3d} "
                    f"vs s/ contr.: {row['no_contract_items']:3d} | Dijk: {row['dijkstra_eff_cost']:7.2f} "
                    f"({row['dijkstra_time_ms']:6.3f}ms, -{row['eff_cost_saving_pct']:4.1f}%)"
                )

    out_dir = Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "benchmark_summary.csv"
    json_path = out_dir / "benchmark_summary.json"

    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

    sens_rows = evaluate_alpha_sensitivity()
    sens_csv = out_dir / "alpha_sensitivity.csv"
    sens_json = out_dir / "alpha_sensitivity.json"
    if sens_rows:
        with sens_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(sens_rows[0].keys()))
            writer.writeheader()
            for r in sens_rows:
                writer.writerow(r)
        with sens_json.open("w", encoding="utf-8") as f:
            json.dump(sens_rows, f, ensure_ascii=False, indent=2)

    print(f"\nResumo experimental exportado para: {csv_path}, {json_path}, {sens_csv} e {sens_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

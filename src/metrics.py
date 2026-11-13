"""Cálculo de métricas (custo real, coletáveis únicos, gap) e exportação de resultados."""

import csv
import json
from pathlib import Path

from src.models import RouteResult


def summarize_results(results: list[RouteResult]) -> list[dict[str, object]]:
    """Formata métricas comparativas entre algoritmos para tabela, CSV ou JSON."""
    bnb_ref = next(
        (
            r
            for r in results
            if r.algorithm == "DFS Branch-and-Bound" and r.found and not r.timed_out
        ),
        None,
    )
    ref_eff = bnb_ref.effective_cost if bnb_ref is not None else None

    rows: list[dict[str, object]] = []
    for res in results:
        if res.found and ref_eff is not None and ref_eff > 0.0:
            gap_pct: float | None = ((res.effective_cost - ref_eff) / ref_eff) * 100.0
        else:
            gap_pct = None

        rows.append(
            {
                "algorithm": res.algorithm,
                "found": res.found,
                "real_cost": round(res.real_cost, 4) if res.found else None,
                "effective_cost": round(res.effective_cost, 4) if res.found else None,
                "optimality_gap_pct": (
                    round(gap_pct, 4) if res.found and gap_pct is not None else None
                ),
                "collectibles_count": res.collectibles_count,
                "collectibles_total_value": round(res.collectibles_total_value, 4),
                "collected_rooms": ",".join(sorted(res.collected_room_ids)),
                "used_weapon": res.used_weapon,
                "visited_states": res.visited_states,
                "elapsed_ms": round(res.elapsed_ms, 4),
                "timed_out": res.timed_out,
                "path": res.format_path(),
            }
        )
    return rows


def format_comparison_table(results: list[RouteResult]) -> str:
    """Gera tabela textual alinhada para impressão no terminal Linux/Windows."""
    rows = summarize_results(results)
    headers = [
        "Algoritmo",
        "Custo Real",
        "Peso Efetivo",
        "Coletáveis (Valor)",
        "Usou Arma",
        "Estados",
        "Tempo (ms)",
    ]
    table_data: list[list[str]] = []
    for row in rows:
        if not row["found"]:
            table_data.append(
                [
                    str(row["algorithm"]),
                    "N/A",
                    "N/A",
                    "0 (0.0)",
                    "Não",
                    str(row["visited_states"]),
                    f"{row['elapsed_ms']:.3f}",
                ]
            )
            continue

        status_suffix = " (TIMEOUT)" if row["timed_out"] else ""
        table_data.append(
            [
                f"{row['algorithm']}{status_suffix}",
                f"{row['real_cost']:.2f}",
                f"{row['effective_cost']:.4f}",
                f"{row['collectibles_count']} ({row['collectibles_total_value']:.1f})",
                "Sim" if row["used_weapon"] else "Não",
                str(row["visited_states"]),
                f"{row['elapsed_ms']:.3f}",
            ]
        )

    col_widths = [len(h) for h in headers]
    for line in table_data:
        for idx, cell in enumerate(line):
            col_widths[idx] = max(col_widths[idx], len(cell))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    out_lines = [sep, header_line, sep]
    for line in table_data:
        out_lines.append(
            "| " + " | ".join(line[i].ljust(col_widths[i]) for i in range(len(headers))) + " |"
        )
    out_lines.append(sep)

    out_lines.append("\nRotas Escolhidas:")
    for res in results:
        collected_str = (
            ", ".join(sorted(res.collected_room_ids)) if res.collected_room_ids else "nenhum"
        )
        out_lines.append(
            f"  - {res.algorithm}: {res.format_path()} [Itens: {collected_str}]"
        )
    return "\n".join(out_lines)


def export_results_csv(results: list[RouteResult], output_path: Path | str) -> None:
    """Exporta resultados comparativos para arquivo CSV UTF-8."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = summarize_results(results)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with target.open(mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_results_json(results: list[RouteResult], output_path: Path | str) -> None:
    """Exporta resultados comparativos para arquivo JSON UTF-8."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = summarize_results(results)
    with target.open(mode="w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

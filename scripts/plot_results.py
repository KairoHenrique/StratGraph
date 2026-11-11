"""Gerador de figuras científicas (PDF/PNG) para o artigo IEEE do StratGraph.

Lê `results/benchmark_summary.json` e produz em `article/figures/`:
1. `comparacao_custos.pdf` / `.png`: Custo efetivo BFS vs. Dijkstra em Camadas (Celeste e Cuphead);
2. `escalabilidade_tempo.pdf` / `.png`: Curva de escalabilidade (tempo em ms vs. |V|) para BFS, Dijkstra e DFS B&B;
3. `contracao_becos.pdf` / `.png`: Redução topológica de vértices (|V| original vs. |V'| contraído).

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt


def generate_all_figures(
    summary_path: Path = Path("results/benchmark_summary.json"),
    out_dir: Path = Path("article/figures"),
) -> list[Path]:
    """Gera os gráficos científicos em PDF e PNG a partir do resumo experimental."""
    if not summary_path.exists():
        raise FileNotFoundError(f"Resumo experimental não encontrado: {summary_path}")

    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
        }
    )

    # 1. Comparação de Custo Efetivo (Celeste + Cuphead)
    celeste_rows = [r for r in rows if r["category"] == "celeste"]
    cuphead_rows = [r for r in rows if r["category"] == "cuphead"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.9), constrained_layout=True)

    # Subplot Celeste
    c_labels = [r["dataset"].split("_", 1)[0] + "-" + r["dataset"].split("_", 1)[1][:6].title() for r in celeste_rows]
    x1 = list(range(len(celeste_rows)))
    w = 0.38
    ax1.bar([i - w / 2 for i in x1], [r["bfs_eff_cost"] for r in celeste_rows], width=w, label="BFS (L0)", color="#8c96c6", edgecolor="black", linewidth=0.5)
    ax1.bar([i + w / 2 for i in x1], [r["dijkstra_eff_cost"] for r in celeste_rows], width=w, label="Dijkstra (L0->L1)", color="#2b8cbe", edgecolor="black", linewidth=0.5)
    ax1.set_yscale("log")
    ax1.set_title("(a) Capítulos Oficiais — Celeste")
    ax1.set_ylabel("Custo Efetivo Total (escala log)")
    ax1.set_xticks(x1)
    ax1.set_xticklabels(c_labels, rotation=35, ha="right")
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Subplot Cuphead
    u_labels = [r["dataset"].split("_")[0] + "_" + r["dataset"].split("_")[1].upper() for r in cuphead_rows]
    x2 = list(range(len(cuphead_rows)))
    ax2.bar([i - w / 2 for i in x2], [r["bfs_eff_cost"] for r in cuphead_rows], width=w, label="BFS (L0)", color="#fd8d3c", edgecolor="black", linewidth=0.5)
    ax2.bar([i + w / 2 for i in x2], [r["dijkstra_eff_cost"] for r in cuphead_rows], width=w, label="Dijkstra (L0->L1)", color="#d94701", edgecolor="black", linewidth=0.5)
    ax2.set_title("(b) Fases Run-and-Gun — Cuphead")
    ax2.set_ylabel("Custo Efetivo Total")
    ax2.set_xticks(x2)
    ax2.set_xticklabels(u_labels, rotation=35, ha="right")
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right")

    for ext in ("pdf", "png"):
        p = out_dir / f"comparacao_custos.{ext}"
        fig.savefig(p, dpi=300)
        generated.append(p)
    plt.close(fig)

    # 2. Curva de Escalabilidade nos Grafos Sintéticos (V = 15 a 5000)
    syn_rows = [r for r in rows if r["category"] == "synthetic"]
    v_sizes = [int(r["v_orig"]) for r in syn_rows]
    bfs_t = [float(r["bfs_time_ms"]) for r in syn_rows]
    dijk_t = [float(r["dijkstra_time_ms"]) for r in syn_rows]
    dfs_t = [float(r["dfs_time_ms"]) for r in syn_rows]

    fig, ax = plt.subplots(figsize=(3.8, 2.7), constrained_layout=True)
    ax.plot(v_sizes, bfs_t, marker="o", linewidth=1.5, markersize=4, label="BFS O(V+E)", color="#2ca25f")
    ax.plot(v_sizes, dijk_t, marker="s", linewidth=1.5, markersize=4, label="Dijkstra Camadas O((V+E) log V)", color="#2b8cbe")
    ax.plot(v_sizes, dfs_t, marker="^", linestyle="--", linewidth=1.5, markersize=4, label="DFS B&B (timeout 150 ms)", color="#de2d26")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(0.01, 1200.0)
    ax.set_xlabel("Número de Salas Originais |V| (log)")
    ax.set_ylabel("Tempo Mediano (ms, log)")
    ax.set_title("Escalabilidade (Grafos Sintéticos)")
    ax.grid(True, which="both", linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", fontsize=7.2, framealpha=0.92)

    for ext in ("pdf", "png"):
        p = out_dir / f"escalabilidade_tempo.{ext}"
        fig.savefig(p, dpi=300)
        generated.append(p)
    plt.close(fig)

    # 3. Redução de Vértices pela Contração de Becos Sem Saída
    real_rows = celeste_rows + cuphead_rows
    r_labels = [
        ("C" + r["dataset"].split("_", 1)[0])
        if r["category"] == "celeste"
        else (r["dataset"].split("_")[0] + "-" + r["dataset"].split("_")[1].upper())
        for r in real_rows
    ]
    xr = list(range(len(real_rows)))
    fig, ax = plt.subplots(figsize=(3.8, 2.7), constrained_layout=True)
    ax.bar([i - w / 2 for i in xr], [r["v_orig"] for r in real_rows], width=w, label="|V| Original (LCC)", color="#bdbdbd", edgecolor="black", linewidth=0.5)
    ax.bar([i + w / 2 for i in xr], [r["v_after"] for r in real_rows], width=w, label="|V'| Após Contração", color="#31a354", edgecolor="black", linewidth=0.5)
    ax.set_ylim(0, 118)
    ax.set_xlabel("Instâncias Reais (Celeste C1–C9 e Cuphead 1-1F–3-2F)")
    ax.set_ylabel("Quantidade de Salas")
    ax.set_title("Redução Topológica por Contração de Becos")
    ax.set_xticks(xr)
    ax.set_xticklabels(r_labels, rotation=45, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper right", fontsize=7.5, framealpha=0.92)

    for ext in ("pdf", "png"):
        p = out_dir / f"contracao_becos.{ext}"
        fig.savefig(p, dpi=300)
        generated.append(p)
    plt.close(fig)

    # 4. Fluxograma da Metodologia Proposta (obrigatório conforme especificação do artigo)
    fig, ax = plt.subplots(figsize=(4.4, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    steps = [
        (8.8, "1. Ingestão e Extração Binária (Celeste .bin / Cuphead Unity)\nLeitura e validação de vertices.csv e arestas.csv", "#e0f3db"),
        (7.0, "2. Pré-processamento Topológico (contract_dead_ends)\nFusão de becos sem saída com coletáveis na sala adjacente", "#ccebc5"),
        (5.2, "3. Expansão em Camadas (L0: Sem Arma -> L1: Com Arma)\nTransição de custo zero na sala de ARMA e Peso Efetivo w > 0", "#a8ddb5"),
        (3.2, "4. Execução Comparativa dos Algoritmos de Busca\n• BFS O(V+E)   • DFS Branch-and-Bound   • Dijkstra O((V+E) log V)", "#7bccc4"),
        (1.2, "5. Auditoria de Rotas e Exportação de Métricas\nCusto Real, Peso Efetivo, Coletáveis Únicos, Estados e Tempo (ms)", "#4eb3d3"),
    ]

    for y_center, text, color in steps:
        box = mpatches.FancyBboxPatch(
            (0.25, y_center - 0.62),
            9.5,
            1.24,
            boxstyle="round,pad=0.10,rounding_size=0.2",
            facecolor=color,
            edgecolor="#084081",
            linewidth=1.1,
        )
        ax.add_patch(box)
        ax.text(5.0, y_center, text, ha="center", va="center", fontsize=7.1, fontweight="bold", color="#081d58")

    for i in range(len(steps) - 1):
        y_top = steps[i][0] - 0.65
        y_bot = steps[i + 1][0] + 0.65
        ax.annotate(
            "",
            xy=(5.0, y_bot),
            xytext=(5.0, y_top),
            arrowprops={"arrowstyle": "->", "lw": 1.4, "color": "#084081"},
        )

    fig.tight_layout(pad=0.2)
    for ext in ("pdf", "png"):
        p = out_dir / f"fluxograma_proposta.{ext}"
        fig.savefig(p, dpi=300)
        generated.append(p)
    plt.close(fig)

    return generated


def main() -> int:
    paths = generate_all_figures()
    for p in paths:
        print(f"Figura gerada: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
        (8.8, "1. Ingestão Genérica (vertices.csv / arestas.csv)\nAlimentada por extratores reais (Celeste .bin / Cuphead Unity) ou sintéticos", "#e0f3db"),
        (7.0, "2. Pré-processamento Topológico (contract_dead_ends)\nContração iterativa de becos com coletáveis na sala adjacente", "#ccebc5"),
        (5.2, "3. Expansão em Camadas (L0: Sem Arma -> L1: Com Arma)\nAresta (u_arma,0)->(u_arma,1) de custo zero e peso heurístico w > 0", "#a8ddb5"),
        (3.2, "4. Execução Comparativa dos Algoritmos de Busca\n• BFS O(V+E)   • DFS Branch-and-Bound   • Dijkstra O((V+E) log V)", "#7bccc4"),
        (1.2, "5. Auditoria de Rotas, Métricas e Exportação Gephi (.gexf)\nCusto Real, Peso Efetivo, Coletáveis Únicos, Modularidade e Tempo (ms)", "#4eb3d3"),
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
        ax.text(5.0, y_center, text, ha="center", va="center", fontsize=6.2, fontweight="bold", color="#081d58")

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

    # 5. Sensibilidade do Parâmetro Alpha e Ablação --no-contract
    sens_path = summary_path.parent / "alpha_sensitivity.json"
    if sens_path.exists():
        sens_rows = json.loads(sens_path.read_text(encoding="utf-8"))
        v150 = [r for r in sens_rows if r["dataset"] == "v_0150"]
        if v150:
            alphas = [float(r["alpha"]) for r in v150]
            c_items = [int(r["contracted_items"]) for r in v150]
            nc_items = [int(r["no_contract_items"]) for r in v150]
            c_real = [float(r["contracted_real_cost"]) for r in v150]
            nc_real = [float(r["no_contract_real_cost"]) for r in v150]
            c_eff = [float(r["contracted_eff_cost"]) for r in v150]

            fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(7.2, 2.65), constrained_layout=True)

            ax_l.plot(alphas, c_items, marker="o", linewidth=1.6, color="#2b8cbe", label="Com Contração (Padrão)")
            ax_l.plot(alphas, nc_items, marker="s", linestyle="--", linewidth=1.6, color="#e34a33", label="Sem Contração (--no-contract)")
            ax_l.set_ylim(5, 48)
            ax_l.set_xlabel("Parâmetro α (Atração por Coletáveis)")
            ax_l.set_ylabel("Itens Coletados na Rota")
            ax_l.set_title("(a) Coleta de Itens vs. α (v_0150)")
            ax_l.grid(True, linestyle="--", alpha=0.5)
            ax_l.legend(loc="lower right", fontsize=7.0)

            ax_r.plot(alphas, c_real, marker="o", linewidth=1.6, color="#08519c", label="Custo Real c/ Contração")
            ax_r.plot(alphas, nc_real, marker="s", linestyle="--", linewidth=1.5, color="#e34a33", label="Custo Real s/ Contração")
            ax_r.plot(alphas, c_eff, marker="^", linestyle=":", linewidth=1.4, color="#31a354", label="Peso Efetivo c/ Contração")
            ax_r.set_xlabel("Parâmetro α (Atração por Coletáveis)")
            ax_r.set_ylabel("Custo da Rota (u.t.)")
            ax_r.set_title("(b) Custo Real vs. Peso Efetivo (v_0150)")
            ax_r.grid(True, linestyle="--", alpha=0.5)
            ax_r.legend(loc="center right", fontsize=6.6, framealpha=0.92)

            for ext in ("pdf", "png"):
                p = out_dir / f"sensibilidade_alpha.{ext}"
                fig.savefig(p, dpi=300)
                generated.append(p)
            plt.close(fig)

    generated.extend(_generate_gephi_topology_figures(out_dir=out_dir))
    return generated


def _generate_gephi_topology_figures(out_dir: Path = Path("article/figures")) -> list[Path]:
    """Calcula métricas topológicas (Louvain Modularity, grau médio, densidade) e gera
    visualizações estruturais estilo Gephi (camadas L0->L1 e subgrafo filtrado de rota).
    """
    import xml.etree.ElementTree as ET
    import networkx as nx
    from networkx.algorithms.community import louvain_communities, modularity

    from src.algorithms import run_bfs, run_dijkstra
    from src.layered_graph import build_layered_graph
    from src.loader import load_graph_from_csv
    from src.preprocessing import contract_dead_ends

    out_paths: list[Path] = []

    # 1. Calcular e persistir métricas topológicas reais dos GEXFs
    topo_targets = [
        ("1-Forsaken City (Base)", Path("results/gephi/1_forsaken_city/1_forsaken_city_base.gexf")),
        ("1-Forsaken City (Camadas)", Path("results/gephi/1_forsaken_city/1_forsaken_city_layered.gexf")),
        ("7-The Summit (Base)", Path("results/gephi/7_summit/7_summit_base.gexf")),
        ("7-The Summit (Camadas)", Path("results/gephi/7_summit/7_summit_layered.gexf")),
        ("2-2F Funhouse (Base)", Path("results/gephi/2_2f_funhouse_frazzle/2_2f_funhouse_frazzle_base.gexf")),
        ("2-2F Funhouse (Camadas)", Path("results/gephi/2_2f_funhouse_frazzle/2_2f_funhouse_frazzle_layered.gexf")),
        ("Celeste Unificado", Path("results/gephi/stratgraph_celeste_all.gexf")),
        ("Cuphead Unificado", Path("results/gephi/stratgraph_cuphead_all.gexf")),
    ]
    topo_metrics: list[dict[str, object]] = []
    for label, gexf_path in topo_targets:
        if not gexf_path.exists():
            continue
        gx = nx.read_gexf(gexf_path)
        ux = gx.to_undirected()
        comms = louvain_communities(ux, seed=42)
        mod_q = modularity(ux, comms)
        avg_deg = sum(dict(gx.degree()).values()) / max(1, gx.number_of_nodes())
        topo_metrics.append(
            {
                "label": label,
                "nodes": gx.number_of_nodes(),
                "edges": gx.number_of_edges(),
                "avg_degree": round(avg_deg, 2),
                "communities": len(comms),
                "modularity_q": round(mod_q, 4),
                "density": round(nx.density(gx), 4),
            }
        )
    if topo_metrics:
        metrics_json = Path("results/gephi/gephi_topology_metrics.json")
        metrics_json.parent.mkdir(parents=True, exist_ok=True)
        metrics_json.write_text(json.dumps(topo_metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Figura 6: Gephi Macro (Comunidades de Modularidade + Expansão em Camadas L0 -> L1 em 1_forsaken_city)
    ch1_dir = Path("datasets/celeste/1_forsaken_city")
    gexf_ch1_layered = Path("results/gephi/1_forsaken_city/1_forsaken_city_layered.gexf")
    if ch1_dir.exists() and gexf_ch1_layered.exists():
        raw_ch1 = load_graph_from_csv(ch1_dir)
        contr_ch1 = contract_dead_ends(raw_ch1)
        layered_ch1 = build_layered_graph(contr_ch1, alpha=0.05)
        dijk_ch1 = run_dijkstra(layered_ch1)

        g_base = nx.DiGraph()
        for rid in raw_ch1.vertices:
            g_base.add_node(rid)
        for u, edges in raw_ch1.adjacency.items():
            for e in edges:
                g_base.add_edge(u, e.destination)
        comms_base = louvain_communities(g_base.to_undirected(), seed=42)
        comm_map = {n: idx for idx, cset in enumerate(comms_base) for n in cset}
        mod_base = modularity(g_base.to_undirected(), comms_base)

        pos_base = nx.spring_layout(g_base.to_undirected(), seed=42, k=0.48, iterations=120)
        palette = ["#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf", "#66c2a5", "#e78ac3"]

        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.4, 3.15), constrained_layout=True)

        nx.draw_networkx_edges(
            g_base, pos_base, ax=ax_a, alpha=0.35, width=0.8,
            edge_color="#636363", arrows=True, arrowsize=7, connectionstyle="arc3,rad=0.06",
        )
        dead_end_ids = {r for children in contr_ch1.contracted_into.values() for r in children}
        spine_ids = [n for n in g_base.nodes if n not in dead_end_ids]
        nx.draw_networkx_nodes(
            g_base, pos_base, nodelist=spine_ids, ax=ax_a,
            node_size=[55 + 16 * g_base.degree(n) for n in spine_ids],
            node_color=[palette[comm_map[n] % len(palette)] for n in spine_ids],
            edgecolors="black", linewidths=0.7,
        )
        nx.draw_networkx_nodes(
            g_base, pos_base, nodelist=[n for n in dead_end_ids if n in g_base], ax=ax_a,
            node_shape="D", node_size=45,
            node_color="#e31a1c", edgecolors="black", linewidths=0.6, alpha=0.88,
        )
        for key_id, lbl in [(raw_ch1.start_id, "INICIO"), (raw_ch1.goal_id, "FIM"), ("lvl_10a", "ARMA")]:
            if key_id in pos_base:
                x, y = pos_base[key_id]
                ax_a.text(x, y + 0.08, lbl, fontsize=6.5, fontweight="bold", ha="center",
                          bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.85, lw=0.5))
        ax_a.set_title(f"(a) Grafo Base + Modularidade (|V|=38, Q={mod_base:.2f})", fontsize=8.5)
        ax_a.axis("off")

        # Painel (b): L0 vs L1 (lendo coordenadas do GEXF e projetando separação clara L0 inferior / L1 superior)
        ns = {"g": "http://www.gexf.net/1.2draft", "viz": "http://www.gexf.net/1.2draft/viz"}
        root_l = ET.parse(gexf_ch1_layered).getroot()
        raw_xy: dict[str, tuple[float, int]] = {}
        for nd in root_l.findall("g:graph/g:nodes/g:node", ns):
            nid = nd.attrib["id"]
            pos_el = nd.find("viz:position", ns)
            x_val = float(pos_el.attrib["x"]) if pos_el is not None else 0.0
            layer_val = 1 if ", L1)" in nid else 0
            raw_xy[nid] = (x_val, layer_val)

        g_lay = nx.DiGraph()
        for u_node, edges in layered_ch1.adjacency.items():
            uid = str(u_node)
            g_lay.add_node(uid, layer=u_node.layer)
            for e in edges:
                g_lay.add_edge(uid, str(e.destination), trans=e.is_weapon_transition)

        opt_nodes = {str(n) for n in dijk_ch1.path}
        opt_edges = {(str(dijk_ch1.path[i]), str(dijk_ch1.path[i + 1])) for i in range(len(dijk_ch1.path) - 1)}

        # Ordenar eixo X topologicamente ao longo da cadeia
        pos_lay: dict[str, tuple[float, float]] = {}
        order_rooms = sorted(contr_ch1.vertices.keys(), key=lambda r: raw_xy.get(f"({r}, L0)", (0.0, 0))[0])
        x_idx = {r: float(i) for i, r in enumerate(order_rooms)}
        for u_node in layered_ch1.adjacency:
            uid = str(u_node)
            rx = x_idx.get(u_node.room_id, 0.0)
            ry = 1.15 if u_node.layer == 1 else 0.0
            # leve jitter deterministico por paridade para reduzir sobreposicao de arestas colineares
            ry += 0.14 if (int(rx) % 2 == 0) else -0.14
            pos_lay[uid] = (rx, ry)

        bg_edges = [(u, v) for u, v in g_lay.edges if (u, v) not in opt_edges]
        trans_edges = [(u, v) for u, v, d in g_lay.edges(data=True) if d.get("trans")]
        route_edges = [e for e in opt_edges if g_lay.has_edge(*e) and not g_lay[e[0]][e[1]].get("trans")]

        nx.draw_networkx_edges(g_lay, pos_lay, edgelist=bg_edges, ax=ax_b, alpha=0.22, width=0.65,
                               edge_color="#969696", arrows=False)
        nx.draw_networkx_edges(g_lay, pos_lay, edgelist=route_edges, ax=ax_b, alpha=0.95, width=1.8,
                               edge_color="#d94701", arrows=True, arrowsize=8, connectionstyle="arc3,rad=0.14")
        nx.draw_networkx_edges(g_lay, pos_lay, edgelist=trans_edges, ax=ax_b, alpha=0.95, width=2.2,
                               style="dashed", edge_color="#f1c40f", arrows=True, arrowsize=10)

        l0_nodes = [n for n in g_lay.nodes if ", L0)" in n]
        l1_nodes = [n for n in g_lay.nodes if ", L1)" in n]
        nx.draw_networkx_nodes(g_lay, pos_lay, nodelist=l0_nodes, ax=ax_b,
                               node_size=[80 if n in opt_nodes else 35 for n in l0_nodes],
                               node_color=["#2b8cbe" if n in opt_nodes else "#bdd7e7" for n in l0_nodes],
                               edgecolors="black", linewidths=0.6)
        nx.draw_networkx_nodes(g_lay, pos_lay, nodelist=l1_nodes, ax=ax_b,
                               node_size=[80 if n in opt_nodes else 35 for n in l1_nodes],
                               node_color=["#238b45" if n in opt_nodes else "#bae4b3" for n in l1_nodes],
                               edgecolors="black", linewidths=0.6)
        ax_b.text(-1.1, 0.0, "L0\n(Sem Arma)", fontsize=6.4, fontweight="bold", color="#08519c", va="center", ha="right")
        ax_b.text(-1.1, 1.15, "L1\n(Armado)", fontsize=6.4, fontweight="bold", color="#006d2c", va="center", ha="right")
        if "(lvl_10a, L0)" in pos_lay and "(lvl_10a, L1)" in pos_lay:
            px, py = pos_lay["(lvl_10a, L0)"]
            ax_b.text(px, 0.58, "lvl_10a\n(L0->L1)", fontsize=6.3, fontweight="bold", ha="center",
                      bbox=dict(boxstyle="round,pad=0.14", facecolor="#fff7bc", edgecolor="#d95f0e", lw=0.7))
        ax_b.set_xlim(-5.2, len(order_rooms) + 0.6)
        ax_b.set_ylim(-0.45, 1.65)
        ax_b.set_title("(b) Camadas Expandidas L0 -> L1 (|V'|=21 -> |V_L|=42)", fontsize=8.5)
        ax_b.axis("off")

        for ext in ("pdf", "png"):
            p = out_dir / f"gephi_camadas_macro.{ext}"
            fig.savefig(p, dpi=300)
            out_paths.append(p)
        plt.close(fig)

    # 3. Figura 7: Subgrafo Filtrado de Rota Comparativa em Cuphead (2_2f_funhouse_frazzle)
    cup_dir = Path("datasets/cuphead/2_2f_funhouse_frazzle")
    if cup_dir.exists():
        raw_cup = load_graph_from_csv(cup_dir)
        contr_cup = contract_dead_ends(raw_cup)
        layered_cup = build_layered_graph(contr_cup, alpha=0.05)
        bfs_cup = run_bfs(layered_cup)
        dijk_cup = run_dijkstra(layered_cup)

        g_sub = nx.DiGraph()
        for rid in raw_cup.vertices:
            g_sub.add_node(rid)
        for u, edges in raw_cup.adjacency.items():
            for e in edges:
                g_sub.add_edge(u, e.destination)

        pos_cup: dict[str, tuple[float, float]] = {}
        for i in range(16):
            pos_cup[f"sec_{i:02d}"] = (float(i), 0.0)
        for nid in raw_cup.vertices:
            if nid in pos_cup:
                continue
            if "arma" in nid:
                pos_cup[nid] = (2.5, 1.15)
            elif "high" in nid:
                pos_cup[nid] = (3.8, -1.0)
            elif "coin" in nid:
                # posiciona moeda abaixo/acima da secao vizinha
                neighs = [n for n in g_sub.neighbors(nid) if n in pos_cup]
                bx = pos_cup[neighs[0]][0] if neighs else 5.0
                pos_cup[nid] = (bx, -1.05 if int(bx) % 2 else 1.05)
            else:
                pos_cup[nid] = (7.5, -1.2)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 3.4), constrained_layout=True)
        bfs_edges = {(bfs_cup.path[i].room_id, bfs_cup.path[i + 1].room_id) for i in range(len(bfs_cup.path) - 1)}
        dijk_edges = {(dijk_cup.path[i].room_id, dijk_cup.path[i + 1].room_id) for i in range(len(dijk_cup.path) - 1) if dijk_cup.path[i].room_id != dijk_cup.path[i + 1].room_id}

        for ax, hl_edges, edge_col, node_col, title_txt in [
            (ax1, bfs_edges, "#e34a33", "#fc8d59",
             f"(a) Filtro BFS (Somente L0): Custo Real = {bfs_cup.real_cost:.1f} | Peso Efetivo = {bfs_cup.effective_cost:.1f}"),
            (ax2, dijk_edges, "#238b45", "#66c2a4",
             f"(b) Filtro Dijkstra em Camadas (L0 -> L1 via Arma): Custo Real = {dijk_cup.real_cost:.1f} (-68,3%) | Peso Efetivo = {dijk_cup.effective_cost:.1f}"),
        ]:
            other_e = [(u, v) for u, v in g_sub.edges if (u, v) not in hl_edges]
            nx.draw_networkx_edges(g_sub, pos_cup, edgelist=other_e, ax=ax, alpha=0.22, width=0.65,
                                   edge_color="#bdbdbd", arrows=False)
            nx.draw_networkx_edges(g_sub, pos_cup, edgelist=list(hl_edges), ax=ax, alpha=0.95, width=2.0,
                                   edge_color=edge_col, arrows=True, arrowsize=8, connectionstyle="arc3,rad=0.12")
            active_nodes = {u for u, _ in hl_edges} | {v for _, v in hl_edges}
            coin_nodes = [n for n in g_sub.nodes if "coin" in n]
            main_nodes = [n for n in g_sub.nodes if "coin" not in n]
            nx.draw_networkx_nodes(
                g_sub, pos_cup, nodelist=main_nodes, ax=ax,
                node_size=[95 if n in active_nodes else 40 for n in main_nodes],
                node_color=[("#f1c40f" if "arma" in n else (node_col if n in active_nodes else "#e0e0e0")) for n in main_nodes],
                edgecolors="black", linewidths=0.6,
            )
            nx.draw_networkx_nodes(
                g_sub, pos_cup, nodelist=coin_nodes, ax=ax, node_shape="D",
                node_size=55, node_color="#984ea3", edgecolors="black", linewidths=0.6,
            )
            ax.text(2.5, 1.52, "Arma (Parry Shrine)", fontsize=6.4, fontweight="bold", ha="center", color="#8c510a")
            ax.text(0.0, 0.36, "S0", fontsize=6.2, fontweight="bold", ha="center")
            ax.text(15.0, 0.36, "FIM", fontsize=6.2, fontweight="bold", ha="center")
            ax.set_xlim(-0.8, 15.8)
            ax.set_ylim(-1.45, 1.82)
            ax.set_title(title_txt, fontsize=8.3)
            ax.axis("off")

        for ext in ("pdf", "png"):
            p = out_dir / f"gephi_rota_comparativa.{ext}"
            fig.savefig(p, dpi=300)
            out_paths.append(p)
        plt.close(fig)

    return out_paths


def main() -> int:
    paths = generate_all_figures()
    for p in paths:
        print(f"Figura gerada: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

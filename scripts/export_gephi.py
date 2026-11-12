"""Exportador de Grafos para Gephi (.gexf) do StratGraph.

Gera arquivos `.gexf` (Graph Exchange XML Format) 100% compativeis com Gephi 0.9 e 0.10:
  1. `<dataset>_base.gexf`: Grafo base com tipos de sala, pesos e coordenadas reais;
  2. `<dataset>_layered.gexf`: Grafo em camadas (L0 = sem arma, L1 = com arma);
  3. `<dataset>_optimal_route.gexf`: Grafo com a rota otima do StratGraph destacada.

Autoria:
    - Heitor Henrique Zonho
    - Kairo Henrique Ferreira Martins
    - Michel Pires da Silva
"""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from src.algorithms import run_bfs, run_dijkstra
from src.layered_graph import build_layered_graph
from src.loader import load_graph_from_csv
from src.models import GameGraph, LayeredNode, RoomType
from src.preprocessing import contract_dead_ends

# Paleta de cores padronizada Gephi (RGB)
COLOR_PALETTE: dict[str, tuple[int, int, int]] = {
    RoomType.INICIO.value: (46, 204, 113),       # Verde Esmeralda
    RoomType.FIM.value: (231, 76, 60),           # Vermelho Alizarin
    RoomType.ARMA.value: (241, 196, 15),          # Amarelo / Ouro
    RoomType.COLETAVEL.value: (155, 89, 182),     # Roxo Ametista
    RoomType.COMUM.value: (52, 152, 219),         # Azul Peter River
    "ROUTE": (230, 126, 34),                     # Laranja Cenoura
    "L0": (41, 128, 185),                        # Azul Escuro
    "L1": (243, 156, 18),                        # Laranja / Dourado
}


def _get_spatial_positions(dataset_dir: Path) -> dict[str, tuple[float, float]]:
    """Tenta extrair coordenadas 2D espaciais reais do mapa, senao calcula layout radial/grade."""
    coords: dict[str, tuple[float, float]] = {}
    chapter_name = dataset_dir.name
    # Tenta obter do .bin de Celeste caso disponivel
    try:
        from scripts.extract_celeste_maps import CHAPTER_FILES, DEFAULT_STEAM_MAPS_DIR, parse_celeste_bin
        bin_name = dict(CHAPTER_FILES).get(chapter_name)
        if bin_name:
            bin_path = DEFAULT_STEAM_MAPS_DIR / bin_name
            if bin_path.is_file():
                _, root = parse_celeste_bin(bin_path)
                for lvl in [c for c in root[2] if c[0] == "levels"][0][2]:
                    attrs = lvl[1]
                    nm = str(attrs.get("name", ""))
                    rid = nm if nm.startswith("lvl_") else f"lvl_{nm}"
                    bx = float(attrs.get("x", 0.0))
                    by = float(attrs.get("y", 0.0))
                    # Inverte eixo Y do Celeste (telas tem Y negativo) para orientacao cartesiana natural
                    coords[rid] = (bx * 0.1, -by * 0.1)
    except Exception:
        pass
    return coords


def export_base_graph_to_gexf(
    graph: GameGraph,
    out_path: Path,
    title: str = "StratGraph Base",
    optimal_path: list[LayeredNode] | None = None,
    positions: dict[str, tuple[float, float]] | None = None,
) -> Path:
    """Gera um arquivo .gexf do grafo base para visualizacao no Gephi."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    positions = positions or {}

    # Identifica arestas percorridas na rota otima
    route_edges: set[tuple[str, str]] = set()
    route_rooms: set[str] = set()
    if optimal_path:
        for i in range(len(optimal_path) - 1):
            u = optimal_path[i].room_id
            v = optimal_path[i + 1].room_id
            if u != v:
                route_edges.add((u, v))
            route_rooms.add(u)
        if optimal_path:
            route_rooms.add(optimal_path[-1].room_id)

    # Layout circular de fallback para nos sem coordenadas espaciais
    fallback_nodes = [nid for nid in graph.vertices if nid not in positions]
    n_fall = max(1, len(fallback_nodes))
    radius = max(300.0, n_fall * 25.0)
    for idx, nid in enumerate(fallback_nodes):
        angle = 2.0 * math.pi * idx / n_fall
        positions[nid] = (radius * math.cos(angle), radius * math.sin(angle))

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://www.gexf.net/1.2draft" '
        'xmlns:viz="http://www.gexf.net/1.2draft/viz" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.gexf.net/1.2draft http://www.gexf.net/1.2draft/gexf.xsd" '
        'version="1.2">',
        '  <meta lastmodifieddate="2026-11-12">',
        f"    <creator>StratGraph (AEDS Games B10)</creator>",
        f"    <description>{html.escape(title)}</description>",
        "  </meta>",
        '  <graph defaultedgetype="directed" mode="static">',
        '    <attributes class="node">',
        '      <attribute id="0" title="tipo_sala" type="string"/>',
        '      <attribute id="1" title="valor_coletavel" type="float"/>',
        '      <attribute id="2" title="tem_arma" type="boolean"/>',
        '      <attribute id="3" title="na_rota_otima" type="boolean"/>',
        "    </attributes>",
        '    <attributes class="edge">',
        '      <attribute id="e0" title="tempo_base" type="float"/>',
        '      <attribute id="e1" title="dif_sem_arma" type="float"/>',
        '      <attribute id="e2" title="dif_com_arma" type="float"/>',
        '      <attribute id="e3" title="na_rota_otima" type="boolean"/>',
        "    </attributes>",
        "    <nodes>",
    ]

    for nid, v in graph.vertices.items():
        t_val = v.room_type.value
        rgb = COLOR_PALETTE.get(t_val, (52, 152, 219))
        in_rt = nid in route_rooms
        x, y = positions.get(nid, (0.0, 0.0))
        node_size = 28.0 if in_rt else (22.0 if t_val in ("INICIO", "FIM", "ARMA") else 16.0)

        lines.append(f'      <node id="{html.escape(nid)}" label="{html.escape(nid)} [{t_val}]">')
        lines.append(f'        <viz:color r="{rgb[0]}" g="{rgb[1]}" b="{rgb[2]}" a="1.0"/>')
        lines.append(f'        <viz:position x="{x:.2f}" y="{y:.2f}" z="0.0"/>')
        lines.append(f'        <viz:size value="{node_size:.1f}"/>')
        lines.append("        <attvalues>")
        lines.append(f'          <attvalue for="0" value="{t_val}"/>')
        lines.append(f'          <attvalue for="1" value="{v.collectible_value:.2f}"/>')
        lines.append(f'          <attvalue for="2" value="{str(v.has_weapon).lower()}"/>')
        lines.append(f'          <attvalue for="3" value="{str(in_rt).lower()}"/>')
        lines.append("        </attvalues>")
        lines.append("      </node>")

    lines.append("    </nodes>")
    lines.append("    <edges>")

    edge_counter = 0
    for u, edges in graph.adjacency.items():
        for e in edges:
            v = e.destination
            in_rt = (u, v) in route_edges
            weight = 4.0 if in_rt else 1.0
            r_col, g_col, b_col = COLOR_PALETTE["ROUTE"] if in_rt else (149, 165, 166)

            lines.append(f'      <edge id="{edge_counter}" source="{html.escape(u)}" target="{html.escape(v)}" weight="{weight:.1f}">')
            lines.append(f'        <viz:color r="{r_col}" g="{g_col}" b="{b_col}" a="{"1.0" if in_rt else "0.6"}"/>')
            lines.append(f'        <viz:thickness value="{weight:.1f}"/>')
            lines.append("        <attvalues>")
            lines.append(f'          <attvalue for="e0" value="{e.base_time:.2f}"/>')
            lines.append(f'          <attvalue for="e1" value="{e.difficulty_no_weapon:.2f}"/>')
            lines.append(f'          <attvalue for="e2" value="{e.difficulty_with_weapon:.2f}"/>')
            lines.append(f'          <attvalue for="e3" value="{str(in_rt).lower()}"/>')
            lines.append("        </attvalues>")
            lines.append("      </edge>")
            edge_counter += 1

    lines.append("    </edges>")
    lines.append("  </graph>")
    lines.append("</gexf>")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def export_layered_graph_to_gexf(
    layered_graph,
    out_path: Path,
    title: str = "StratGraph Layered",
    optimal_path: list[LayeredNode] | None = None,
    positions: dict[str, tuple[float, float]] | None = None,
) -> Path:
    """Gera um arquivo .gexf do grafo em camadas expandido (L0 e L1) para o Gephi."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    positions = positions or {}

    route_edges: set[tuple[str, str]] = set()
    route_nodes: set[str] = set()
    if optimal_path:
        for i in range(len(optimal_path) - 1):
            un = str(optimal_path[i])
            vn = str(optimal_path[i + 1])
            route_edges.add((un, vn))
            route_nodes.add(un)
        if optimal_path:
            route_nodes.add(str(optimal_path[-1]))

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://www.gexf.net/1.2draft" '
        'xmlns:viz="http://www.gexf.net/1.2draft/viz" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.gexf.net/1.2draft http://www.gexf.net/1.2draft/gexf.xsd" '
        'version="1.2">',
        '  <meta lastmodifieddate="2026-11-12">',
        f"    <creator>StratGraph (AEDS Games B10)</creator>",
        f"    <description>{html.escape(title)}</description>",
        "  </meta>",
        '  <graph defaultedgetype="directed" mode="static">',
        '    <attributes class="node">',
        '      <attribute id="0" title="room_id" type="string"/>',
        '      <attribute id="1" title="camada" type="integer"/>',
        '      <attribute id="2" title="na_rota_otima" type="boolean"/>',
        "    </attributes>",
        '    <attributes class="edge">',
        '      <attribute id="e0" title="peso_efetivo" type="float"/>',
        '      <attribute id="e1" title="custo_real" type="float"/>',
        '      <attribute id="e2" title="transicao_de_arma" type="boolean"/>',
        '      <attribute id="e3" title="na_rota_otima" type="boolean"/>',
        "    </attributes>",
        "    <nodes>",
    ]

    all_nodes = set(layered_graph.adjacency.keys())
    for edges in layered_graph.adjacency.values():
        for e in edges:
            all_nodes.add(e.destination)

    for node in sorted(all_nodes, key=lambda n: (n.layer, n.room_id)):
        nid_str = str(node)
        base_x, base_y = positions.get(node.room_id, (0.0, 0.0))
        # No Gephi: separa a camada L1 no eixo Z e com deslocamento vertical no Y
        z_val = 150.0 if node.layer == 1 else 0.0
        y_val = base_y + (120.0 if node.layer == 1 else -120.0)
        rgb = COLOR_PALETTE["L1"] if node.layer == 1 else COLOR_PALETTE["L0"]
        in_rt = nid_str in route_nodes
        size = 26.0 if in_rt else (20.0 if node.layer == 1 else 16.0)

        lines.append(f'      <node id="{html.escape(nid_str)}" label="{html.escape(nid_str)}">')
        lines.append(f'        <viz:color r="{rgb[0]}" g="{rgb[1]}" b="{rgb[2]}" a="1.0"/>')
        lines.append(f'        <viz:position x="{base_x:.2f}" y="{y_val:.2f}" z="{z_val:.2f}"/>')
        lines.append(f'        <viz:size value="{size:.1f}"/>')
        lines.append("        <attvalues>")
        lines.append(f'          <attvalue for="0" value="{html.escape(node.room_id)}"/>')
        lines.append(f'          <attvalue for="1" value="{node.layer}"/>')
        lines.append(f'          <attvalue for="2" value="{str(in_rt).lower()}"/>')
        lines.append("        </attvalues>")
        lines.append("      </node>")

    lines.append("    </nodes>")
    lines.append("    <edges>")

    edge_counter = 0
    for u_node, edges in layered_graph.adjacency.items():
        u_str = str(u_node)
        for e in edges:
            v_str = str(e.destination)
            in_rt = (u_str, v_str) in route_edges
            is_trans = e.is_weapon_transition
            weight = 5.0 if in_rt else (3.0 if is_trans else 1.0)
            if in_rt:
                rgb = COLOR_PALETTE["ROUTE"]
            elif is_trans:
                rgb = COLOR_PALETTE["ARMA"]
            else:
                rgb = (127, 140, 141)

            lines.append(f'      <edge id="{edge_counter}" source="{html.escape(u_str)}" target="{html.escape(v_str)}" weight="{weight:.1f}">')
            lines.append(f'        <viz:color r="{rgb[0]}" g="{rgb[1]}" b="{rgb[2]}" a="{"1.0" if (in_rt or is_trans) else "0.5"}"/>')
            lines.append(f'        <viz:thickness value="{weight:.1f}"/>')
            lines.append("        <attvalues>")
            lines.append(f'          <attvalue for="e0" value="{e.effective_weight:.2f}"/>')
            lines.append(f'          <attvalue for="e1" value="{e.real_cost:.2f}"/>')
            lines.append(f'          <attvalue for="e2" value="{str(is_trans).lower()}"/>')
            lines.append(f'          <attvalue for="e3" value="{str(in_rt).lower()}"/>')
            lines.append("        </attvalues>")
            lines.append("      </edge>")
            edge_counter += 1

    lines.append("    </edges>")
    lines.append("  </graph>")
    lines.append("</gexf>")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def export_dataset_gephi_bundle(dataset_dir: Path, output_dir: Path, alpha: float = 0.05) -> list[Path]:
    """Exporta o trio de arquivos Gephi (.gexf) para um dataset especifico."""
    raw_graph = load_graph_from_csv(dataset_dir)
    contracted = contract_dead_ends(raw_graph)
    layered = build_layered_graph(contracted, alpha=alpha)
    dres = run_dijkstra(layered)

    positions = _get_spatial_positions(dataset_dir)
    ds_name = dataset_dir.name
    out_dir = output_dir / ds_name
    out_dir.mkdir(parents=True, exist_ok=True)

    base_file = out_dir / f"{ds_name}_base.gexf"
    route_file = out_dir / f"{ds_name}_optimal_route.gexf"
    layered_file = out_dir / f"{ds_name}_layered.gexf"

    export_base_graph_to_gexf(
        raw_graph,
        base_file,
        title=f"Grafo Base: {ds_name}",
        positions=positions,
    )
    export_base_graph_to_gexf(
        raw_graph,
        route_file,
        title=f"Rota Otima StratGraph (alpha={alpha}): {ds_name}",
        optimal_path=dres.path,
        positions=positions,
    )
    export_layered_graph_to_gexf(
        layered,
        layered_file,
        title=f"Grafo em Camadas L0/L1 (alpha={alpha}): {ds_name}",
        optimal_path=dres.path,
        positions=positions,
    )

    print(f"  [Gephi] {ds_name:25s} -> {base_file.name}, {route_file.name}, {layered_file.name}")
    return [base_file, route_file, layered_file]


def export_all_datasets(datasets_root: Path = Path("datasets"), output_root: Path = Path("results/gephi")) -> list[Path]:
    """Varre todos os datasets e gera os arquivos .gexf para visualizacao no Gephi."""
    exported: list[Path] = []
    print(f"\n=== Exportando Grafos Gephi (.gexf) para {output_root} ===")
    for vert_path in sorted(datasets_root.rglob("vertices.csv")):
        ds_dir = vert_path.parent
        files = export_dataset_gephi_bundle(ds_dir, output_root)
        exported.extend(files)
    print(f"Total de arquivos .gexf gerados: {len(exported)}")
    return exported


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta grafos do StratGraph para Gephi (.gexf)")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Caminho para uma pasta de dataset (ex: datasets/celeste/1_forsaken_city)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/gephi"),
        help="Diretorio de destino para os arquivos .gexf (padrao: results/gephi)",
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="Parametro alpha do StratGraph")
    parser.add_argument("--all", action="store_true", default=False, help="Exporta todos os datasets")
    args = parser.parse_args()

    if args.dataset:
        export_dataset_gephi_bundle(args.dataset, args.out_dir, alpha=args.alpha)
        return 0

    export_all_datasets(Path("datasets"), args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
